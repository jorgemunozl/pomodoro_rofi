"""CLI entry point — main menu loop, subcommands, and UI flow."""

import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from pomodoro_lib.commands import (
    EVENT_BELL_30,
    EVENT_BELL_BEGIN,
    EVENT_BELL_END,
    CommandRunner,
)
from pomodoro_lib.config import CHAINS, EVENT_COMMANDS, STARTUP_PRESETS
from pomodoro_lib.constants import (
    ARC_SILENCE_SECONDS,
    ARC_SOUNDTRACK,
    BACK_LABEL,
    BELL_30_FILE,
    BELL_30_PLAYED,
    BELL_BEGIN_FILE,
    BELL_BEGIN_PLAYED,
    BELL_END_FILE,
    CLIAMP_LOFI_URL,
    CMD_LOG_FILE,
    COMMANDS,
    COUNT_OPTIONS,
    CUSTOM_LABEL,
    DATA_DIR,
    DEFAULT_TASKS,
    DURATION_PRESETS,
    EXTRA_WORK_SECS,
    HISTORY_FILE,
    INCLUDE_DURATION_FILES,
    MPV_SOCKET,
    PAST_ARC_FILE,
    PAUSE_FILE,
    PAUSE_TS,
    POMO_DIR,
    POMODORO_DEFAULTS,
    SKIP_RANDOM_FILE,
    SOUNDS_DIR,
    STATE_FILE,
    TASKS_FILE,
    TASKS_UNIQUE,
    WORK_BELL_PLAYED,
)
from pomodoro_lib.rofi import (
    numbered_menu,
    pick_video,
    rofi_menu,
    strip_number,
)
from pomodoro_lib.state import PomodoroState
from pomodoro_lib.tasks import TaskManager
from pomodoro_lib.timer import TimerController, fade_arc_volume, notify, play_bell

# ── Shared command runner (wired from EVENT_COMMANDS) ────────────────────────
_cmd_runner = CommandRunner(EVENT_COMMANDS, log_path=CMD_LOG_FILE)


def _runner_for_active_session() -> CommandRunner:
    """Return the command runner for the currently active session.

    Preset sessions persist their merged event commands in STATE_FILE so that
    OTHER processes (polybar's ``pomodoro status``, ``pomodoro next``) can
    rebuild the correct preset-aware runner when they handle phase transitions.
    Falls back to the global EVENT_COMMANDS runner.
    """
    if STATE_FILE.exists():
        state = PomodoroState.load(STATE_FILE)
        if state.commands:
            return CommandRunner(state.commands, log_path=CMD_LOG_FILE)
    return _cmd_runner


# ── Polybar status line ───────────────────────────────────────────────────────


def _status_line() -> str:
    """Polybar status line. Empty string when no session is active.

    Also handles expired phase transitions so that polybar's periodic
    polling keeps the session moving forward even if the background
    timer thread was killed when the UI process exited.
    """
    if not STATE_FILE.exists():
        return ""

    # Auto-unpause if paused for more than 5 minutes
    if PAUSE_FILE.exists() and PAUSE_TS.exists():
        try:
            paused_since = float(PAUSE_TS.read_text().strip())
            if time.time() - paused_since > 300:
                secs_left = int(PAUSE_FILE.read_text().strip())
                PAUSE_FILE.unlink()
                PAUSE_TS.unlink()
                state = PomodoroState.load(STATE_FILE)
                state.end_ts = time.time() + secs_left
                state.save(STATE_FILE)
                import subprocess  # send unpause to mpv socket

                if MPV_SOCKET.exists():
                    subprocess.run(
                        ["socat", "-", str(MPV_SOCKET)],
                        input='{"command": ["set_property", "pause", false]}\n',
                        capture_output=True,
                        text=True,
                    )
        except (ValueError, OSError):
            pass

    # Handle any expired phases BEFORE computing the status line.
    # This is the *reliable* transition mechanism – the daemon timer
    # threads started by the UI are only a best-effort optimisation.
    # Rebuild the preset-aware runner from state so preset commands fire
    # even when this transition is handled by a different process (polybar).
    runner = _runner_for_active_session()
    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    ctrl = TimerController(
        on_session_complete=lambda t, w, c: tm.log(t, f"{w}m × {c}"),
        cmd_runner=runner,
    )
    ctrl.handle_expired()

    # Re-check after transition (e.g. the session may have completed)
    if not STATE_FILE.exists():
        return ""

    state = PomodoroState.load(STATE_FILE)
    # Effective work length includes the artificial extra seconds, so the
    # countdown displays 25:03 instead of 25:00 at phase start.
    work_total = state.work_min * 60 + EXTRA_WORK_SECS

    if PAUSE_FILE.exists():
        raw = int(PAUSE_FILE.read_text().strip())
        if state.phase == "work" and raw > work_total:
            secs = int(raw - work_total)  # remaining warm-up when paused
        else:
            secs = raw
        icon = "⏸"
    elif state.phase == "break":
        secs = state.remaining_seconds
        icon = "🏹☕" if state.arc_mode else "☕"
    elif state.phase == "reflect":
        secs = state.remaining_seconds
        icon = "🤔"
    else:
        raw = state.remaining_seconds
        if raw > work_total:
            secs = int(raw - work_total)  # still in warm-up
            icon = "🔥"
        else:
            secs = raw
            icon = "▶"

    mins = secs // 60
    secs_rem = secs % 60

    # Fade ARC music volume during the last 15 seconds of a work phase
    if (
        state.arc_mode
        and state.phase == "work"
        and not PAUSE_FILE.exists()
        and not (state.remaining_seconds > work_total)  # not in warm-up
    ):
        fade_arc_volume(secs)

    # Bell warnings during breaks
    if state.phase == "break" and not PAUSE_FILE.exists():
        rem = state.remaining_seconds
        if rem <= 30 and not BELL_30_PLAYED.exists():
            try:
                BELL_30_PLAYED.touch(exist_ok=False)
                play_bell(BELL_30_FILE)
                runner.run(
                    EVENT_BELL_30,
                    task=state.task,
                    session=state.current - 2,  # 0-based: break after session N
                    total=state.total,
                )
            except FileExistsError:
                pass
        if rem <= 3 and not BELL_BEGIN_PLAYED.exists():
            try:
                BELL_BEGIN_PLAYED.touch(exist_ok=False)
                play_bell(BELL_BEGIN_FILE)
                runner.run(
                    EVENT_BELL_BEGIN,
                    task=state.task,
                    session=state.current - 2,  # 0-based: break after session N
                    total=state.total,
                )
            except FileExistsError:
                pass

    # Bell 2 s before work ends (ARC mode and INCLUDE_DURATION_FILES only)
    if (
        state.phase == "work"
        and not PAUSE_FILE.exists()
        and not (state.remaining_seconds > work_total)  # not in warm-up
        and (state.arc_mode or Path(state.video).name in INCLUDE_DURATION_FILES)
    ):
        if state.remaining_seconds <= 2 and not WORK_BELL_PLAYED.exists():
            try:
                WORK_BELL_PLAYED.touch(exist_ok=False)
                play_bell(BELL_END_FILE)
                runner.run(
                    EVENT_BELL_END,
                    task=state.task,
                    session=state.current - 1,  # 0-based: work session N
                    total=state.total,
                )
            except FileExistsError:
                pass  # another process already played it

    # Show schedule label if available, otherwise session count
    if state.phase == "reflect":
        return f"{icon} {mins:02d}:{secs_rem:02d}  reflect"
    if state.schedule_labels:
        if state.phase == "break":
            # current was already bumped to next session during transition
            label_idx = (state.current - 2) * 2 + 1
            if (
                label_idx < len(state.schedule_labels)
                and state.schedule_labels[label_idx]
            ):
                return f"{icon} {mins:02d}:{secs_rem:02d}  {state.schedule_labels[label_idx]}"
        else:
            label_idx = (state.current - 1) * 2
            if (
                label_idx < len(state.schedule_labels)
                and state.schedule_labels[label_idx]
            ):
                return f"{icon} {mins:02d}:{secs_rem:02d}  {state.schedule_labels[label_idx]}"
    return f"{icon} {mins:02d}:{secs_rem:02d}  {state.current}/{state.total}"


# ── Handlers (called from main loop) ──────────────────────────────────────────


def _handle_complete(tm: TaskManager) -> None:
    """Complete pomodoro — pick a task and log it."""
    tasks = tm.all_tasks()
    if not tasks:
        notify("Pomodoro", "No tasks available.")
        return

    choice = numbered_menu("Which pomodoro did you complete?", tasks)
    if choice is None or choice == BACK_LABEL:
        return
    task = strip_number(choice)
    tm.log(task)
    notify("🍅 Pomodoro logged", task)


def _handle_manage(tm: TaskManager) -> None:
    """Manage tasks — two-section display with edit/delete/add."""
    while True:
        everyday = tm.everyday()
        unique = tm.unique()

        # Build menu with section headers
        menu_lines: list[str] = []
        items: list[
            tuple[str, Path]
        ] = []  # (task, file_path) parallel to numbered entries

        idx = 0
        if everyday:
            menu_lines.append("── 📅 Everyday ──")
            for task in everyday:
                idx += 1
                menu_lines.append(f"{idx}. {task}")
                items.append((task, tm.everyday_path))
        if unique:
            menu_lines.append("── 📌 Unique ──")
            for task in unique:
                idx += 1
                menu_lines.append(f"{idx}. {task}")
                items.append((task, tm.unique_path))

        menu_lines.append("➕  Add task")
        menu_lines.append(BACK_LABEL)

        action = rofi_menu("Tasks", menu_lines, no_custom=True)
        if action is None or action == BACK_LABEL:
            break

        if action.startswith("➕"):
            # Add task
            cat_choice = rofi_menu(
                "Add to...", ["📅 Everyday", "📌 Unique", "↩ Cancel"], no_custom=True
            )
            if cat_choice is None or cat_choice == "↩ Cancel":
                continue
            category = "everyday" if "Everyday" in cat_choice else "unique"

            new_task = rofi_menu("New task name", [], no_custom=False)
            if new_task:
                tm.add(new_task, category)
            continue

        # Parse numbered selection
        m = re.match(r"^(\d+)\.", action)
        if not m:
            continue  # section header clicked
        num = int(m.group(1))
        if num < 1 or num > len(items):
            continue

        task, file_path = items[num - 1]

        # Edit / Delete / Cancel
        choice = rofi_menu(
            action, ["✏️  Edit", "🗑  Delete", "↩  Cancel"], no_custom=True
        )
        if choice is None or choice.startswith("↩"):
            continue

        if choice.startswith("✏️"):
            edited = rofi_menu("Edit task", [task], no_custom=False)
            if edited and edited != task:
                tm.edit(task, edited, file_path)
        elif choice.startswith("🗑"):
            tm.delete(task, file_path)


def _lookup_default_rhythm(
    video_name: str,
) -> tuple[int, int, int, int, list] | None:
    """Return (work_min, break_min, total, warm_up_secs, schedule) if video
    has a default rhythm.

    `schedule` is a list of [work, break] pairs for each pomodoro in order.
    For regular (uniform) entries the list is empty; the caller uses the
    scalar work_min/break_min instead.
    """
    for entry in POMODORO_DEFAULTS:
        if entry[0] == video_name:
            if isinstance(entry[1], list):
                # brain_fm style: list ends with warm_up int, rest are
                # (work, break) or (work, break, repetitions) tuples
                warm_up = entry[1][-1]  # last element is the warm-up seconds
                schedule_tuples = entry[1][:-1]
                schedule: list[list[int]] = []
                for tup in schedule_tuples:
                    work, break_ = tup[0], tup[1]
                    reps = tup[2] if len(tup) >= 3 else 1
                    for _ in range(reps):
                        schedule.append([work, break_])
                total = len(schedule)
                first_work, first_break = schedule[0]
                return (first_work, first_break, total, warm_up, schedule)
            warm_up = entry[4] if len(entry) >= 5 else 0
            return (entry[1], entry[2], entry[3], warm_up, [])
    return None


def _handle_new_session(tm: TaskManager, ctrl: TimerController) -> bool:
    """New session flow: step-based loop with Back navigation.

    Returns True if a session was started, False if the user cancelled.
    """
    tasks = tm.all_tasks()
    if not tasks:
        notify("Pomodoro", "No tasks available. Add tasks first.")
        return False

    step = 1  # 1=task, 2=video, 3=audio, 4=duration, 5=count
    task = video = ""
    video_name = ""
    work_min = break_min = total = 0
    warm_up_secs = 0
    audio_only = False
    arc_mode = False
    cliamp_mode = False

    while True:
        if step == 1:
            choice = numbered_menu("Pick task", tasks)
            if choice is None:
                return False  # ESC → exit
            if choice == BACK_LABEL:
                return False  # back to main menu
            task = strip_number(choice)
            step = 2

        elif step == 2:
            arc_thumb = _ensure_arc_thumb()
            past_arc_thumb = _ensure_past_arc_thumb()
            cliamp_thumb = _ensure_cliamp_thumb()
            choice = pick_video(
                POMO_DIR,
                arc_thumb=arc_thumb,
                past_arc_thumb=past_arc_thumb,
                cliamp_thumb=cliamp_thumb,
            )
            if choice is None:
                return False  # ESC → exit
            if choice == BACK_LABEL:
                step = 1
                continue

            if choice == "CURRENT_ARC":
                # ARC mode — audio-only, no video file
                arc_mode = True
                video = str(ARC_SOUNDTRACK)
                video_name = "CURRENT_ARC"
                step = 4  # skip mode selection, go straight to duration
                continue

            if choice == "PAST_ARC":
                # PAST ARC mode — audio-only from ~/Videos/Music
                arc_mode = True
                video = str(PAST_ARC_FILE)
                video_name = "PAST_ARC"
                step = 4  # skip mode selection, go straight to duration
                continue

            if choice == "CLIAMP":
                # CLIAMP lofi radio — audio from the cliamp daemon, no mpv
                cliamp_mode = True
                video = "CLIAMP"
                video_name = "CLIAMP"
                step = 4  # skip mode selection, go straight to duration
                continue

            video_name = choice
            video = str(POMO_DIR / video_name)
            arc_mode = False
            step = 3

        elif step == 3:
            mode_choice = rofi_menu(
                "Mode",
                ["🖥  Play video (fullscreen)", "🎵  Audio only", BACK_LABEL],
                no_custom=True,
            )
            if mode_choice is None:
                return False  # ESC → exit
            if mode_choice == BACK_LABEL:
                step = 2
                continue
            audio_only = "Audio only" in mode_choice
            if audio_only:
                _ensure_mp3(Path(video))

            # Check if this video has a default rhythm in POMODORO_DEFAULTS
            rhythm = _lookup_default_rhythm(video_name)
            if rhythm is not None:
                work_min, break_min, total, warm_up_secs, schedule = rhythm
                rhythm_choice = rofi_menu(
                    "Rhythm",
                    ["🎯  Default rhythm", "✏️  Personalized rhythm", BACK_LABEL],
                    no_custom=True,
                )
                if rhythm_choice is None:
                    return False  # ESC → exit
                if rhythm_choice == BACK_LABEL:
                    step = 2  # back to video selection
                    continue
                if "Default" in rhythm_choice:
                    ctrl.start(
                        task,
                        video,
                        work_min,
                        break_min,
                        total,
                        warm_up_secs,
                        schedule=schedule or None,
                        audio_only=audio_only,
                        arc_mode=arc_mode,
                        cliamp_mode=cliamp_mode,
                    )
                    return True
                # Personalized → fall through to step 4, keep warm_up_secs

            else:
                # No preset — reset warm_up_secs
                warm_up_secs = 0

            # For personalized rhythm or non-default videos, show duration picker
            step = 4

        elif step == 4:
            labels = [label for label, _, _ in DURATION_PRESETS] + [
                CUSTOM_LABEL,
                BACK_LABEL,
            ]
            choice = rofi_menu("Pick duration", labels)
            if choice is None:
                return False  # ESC → exit
            if choice == BACK_LABEL:
                step = 3
                continue

            found = False
            for label, w, b in DURATION_PRESETS:
                if choice == label:
                    work_min, break_min = w, b
                    found = True
                    break

            if not found and choice == CUSTOM_LABEL:
                while True:
                    custom = rofi_menu("Work-break (e.g. 10-5)", [BACK_LABEL])
                    if custom is None:
                        return False  # ESC
                    if custom == BACK_LABEL:
                        break  # back to duration picker
                    try:
                        parts = custom.split("-")
                        if len(parts) != 2:
                            raise ValueError
                        w, b = int(parts[0]), int(parts[1])
                        if w <= 0 or b <= 0:
                            raise ValueError
                        work_min, break_min = w, b
                        found = True
                        break
                    except (ValueError, IndexError):
                        notify(
                            "Pomodoro",
                            "Invalid format. Use e.g. 10-5",
                            urgency="critical",
                        )
                if not found:
                    continue  # back to duration picker

            if found:
                step = 5

        elif step == 5:
            count_labels = [label for label, _ in COUNT_OPTIONS] + [BACK_LABEL]
            choice = rofi_menu("How many?", count_labels)
            if choice is None:
                return False  # ESC → exit
            if choice == BACK_LABEL:
                step = 4
                continue
            for label, c in COUNT_OPTIONS:
                if choice == label:
                    total = c
                    ctrl.start(
                        task,
                        video,
                        work_min,
                        break_min,
                        total,
                        warm_up_secs,
                        audio_only=audio_only,
                        arc_mode=arc_mode,
                        cliamp_mode=cliamp_mode,
                    )
                    return True


def _handle_status(ctrl: TimerController) -> None:
    """Show current session status with pause/resume/stop actions."""
    state = PomodoroState.load(STATE_FILE)
    if not state.is_active:
        return

    paused = PAUSE_FILE.exists()

    work_total = state.work_min * 60

    if paused:
        raw = int(PAUSE_FILE.read_text().strip())
    else:
        raw = state.remaining_seconds

    in_warmup = state.phase == "work" and raw > work_total
    display_secs = (raw - work_total) if in_warmup else raw

    mins = display_secs // 60
    secs_rem = display_secs % 60
    end_fmt = (
        time.strftime("%H:%M", time.localtime(state.end_ts))
        if state.end_ts
        else "--:--"
    )

    if state.phase == "break":
        break_icon = "🏹" if state.arc_mode else "☕"
        info = f"{break_icon}  {state.task}   •   {mins}m {secs_rem}s break   •   session {state.current}/{state.total} next"
    elif state.phase == "reflect":
        info = f"🤔  {state.task}   •   {mins}m {secs_rem}s reflection   •   all sessions complete"
    elif in_warmup:
        info = f"🔥  {state.task}   •   {mins}m {secs_rem}s warm-up   •   {state.current}/{state.total}"
    else:
        info = f"▶  {state.task}   •   {mins}m {secs_rem}s left   •   ends {end_fmt}   •   {state.current}/{state.total}"

    toggle_label = "▶  Resume" if paused else "⏸  Pause"

    action = rofi_menu(
        "Pomodoro",
        [
            info,
            toggle_label,
            "🔄  Change task",
            "⏹  Stop all",
            "🔄  Reset everything",
        ],
        no_custom=True,
    )

    if action is None:
        return

    if "Resume" in action:
        ctrl.resume()
    elif "Pause" in action:
        ctrl.pause()
    elif "Change task" in action:
        _handle_change_task(ctrl)
    elif action.startswith("⏹"):
        ctrl.clear_state()
    elif "Reset" in action:
        ctrl.clear_state()
        notify("🍅 Pomodoro", "All state cleared.")


def _handle_change_task(ctrl: TimerController) -> None:
    """Change the task for the current session."""
    state = PomodoroState.load(STATE_FILE)
    if not state.is_active:
        return

    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tasks = tm.all_tasks()
    choice = numbered_menu("Change task", tasks)
    if choice is None or choice == BACK_LABEL:
        return
    new_task = strip_number(choice)
    if new_task:
        state.task = new_task
        state.save(STATE_FILE)
        notify("🍅 Task changed", new_task)


def _handle_heatmap() -> None:
    """Launch the Textual interactive heatmap in a new terminal."""
    import subprocess
    import sys
    from pathlib import Path

    # Find project root (same logic as pomodoro script)
    root = Path(__file__).resolve().parent.parent
    if not (root / "pomodoro_lib").is_dir():
        root = Path.home() / "project" / "pomodoro_rofi"

    subprocess.Popen(
        [
            "alacritty",
            "-e",
            sys.executable,
            "-m",
            "pomodoro_lib.heatmap_app",
        ],
        cwd=str(root),
    )


# ── CLI start subcommand ────────────────────────────────────────────────────


def _resolve_video(name: str) -> Path | None:
    """Resolve a video name to a full path in POMO_DIR.

    Returns None for 'arc' / 'CURRENT_ARC' (handled by caller).
    If `name` already has an extension (.mp4, .webm), use it directly.
    Otherwise try .mp4 then .webm.
    """
    if name.lower() in (
        "arc",
        "current_arc",
        "past_arc",
        "cliamp",
        "lofi",
        "cliamp_lofi",
    ):
        return None  # sentinel: caller should use arc/cliamp mode
    p = Path(name)
    if p.suffix in (".mp4", ".webm"):
        full = POMO_DIR / p
        return full if full.exists() else None
    # Try with extension
    for ext in (".mp4", ".webm"):
        full = POMO_DIR / f"{name}{ext}"
        if full.exists():
            return full
    return None


def _list_videos() -> list[Path]:
    """List all video files in POMO_DIR."""
    if not POMO_DIR.is_dir():
        return []
    return sorted(f for f in POMO_DIR.iterdir() if f.suffix in (".mp4", ".webm"))


def _pick_random_video() -> Path | None:
    """Pick a random video from POMO_DIR.

    Returns None if no videos are found.
    """
    import random

    videos = _list_videos()
    if not videos:
        return None
    return random.choice(videos)


def _ensure_mp3(video_path: Path) -> Path:
    """Generate an mp3 from a video file if it doesn't exist yet.

    Returns the path to the mp3 file.
    """
    mp3_path = video_path.with_suffix(".mp3")
    if mp3_path.exists():
        return mp3_path

    print(
        f"\U0001f3b5 Generating {mp3_path.name} from {video_path.name}...", flush=True
    )
    try:
        import subprocess

        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "libmp3lame",
                "-q:a",
                "2",
                "-y",
                str(mp3_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"Error generating mp3: {result.stderr.strip()}",
                file=sys.stderr,
            )
            sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: ffmpeg not found. Install it to use audio-only mode.",
            file=sys.stderr,
        )
        sys.exit(1)

    return mp3_path


def _ensure_cliamp_thumb() -> str:
    """Return a cached square lofi-girl thumbnail for the CLIAMP picker entry.

    Downloads the Lofi Girl stream art and crops it to a 250x250 square,
    cached at data/cliamp_lofi.jpg. Falls back to a generated placeholder
    if the download fails.
    """
    thumb = DATA_DIR / "cliamp_lofi.jpg"
    if thumb.exists():
        return str(thumb)

    try:
        import urllib.request

        tmp = DATA_DIR / "cliamp_lofi_raw.jpg"
        with (
            urllib.request.urlopen(
                "https://i.ytimg.com/vi/jfKfPfyJRdk/hqdefault.jpg", timeout=15
            ) as resp,
            open(tmp, "wb") as fh,
        ):
            fh.write(resp.read())
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-loglevel",
                "error",
                "-i",
                str(tmp),
                "-vf",
                "crop=360:360,scale=250:250",
                "-frames:v",
                "1",
                str(thumb),
            ],
            capture_output=True,
            text=True,
        )
        tmp.unlink(missing_ok=True)
        if result.returncode == 0 and thumb.exists():
            return str(thumb)
    except Exception:
        pass

    # Fallback: dark 250x250 tile with "LOFI" text
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x1e1e2e:s=250x250",
                "-vf",
                (
                    "drawtext=fontfile=/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
                    ":text='LOFI':fontcolor=0xf9e2af:fontsize=48"
                    ":x=(w-text_w)/2:y=(h-text_h)/2"
                ),
                "-frames:v",
                "1",
                str(thumb),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and thumb.exists():
            return str(thumb)
    except Exception:
        pass

    # Last resort: 1x1 dark pixel
    try:
        from PIL import Image

        img = Image.new("RGB", (1, 1), color=(30, 30, 46))
        img.save(thumb, "JPEG")
        return str(thumb)
    except ImportError:
        pass

    return ""


def _ensure_arc_thumb() -> str:
    """Generate a thumbnail image for the CURRENT_ARC entry.

    Creates a simple 250x250 image with a musical note background
    at ~/Videos/current_arc/thumbnail.jpg if it doesn't exist.
    Returns the path to the thumbnail.
    """
    thumb = ARC_SOUNDTRACK / "current_arc.jpg"
    if thumb.exists():
        return str(thumb)

    # Generate with ffmpeg — draw a dark background with text
    try:
        import subprocess

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                (
                    "color=c=0x1e1e2e:s=250x250"
                    ":drawtext=fontfile=/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
                    ":text='CURRENT ARC'"
                    ":fontcolor=0xcdd6f4:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2-10"
                    ":drawtext=fontfile=/usr/share/fonts/TTF/DejaVuSans.ttf"
                    ":text='🎶':fontcolor=0xf9e2af:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2+20"
                ),
                "-frames:v",
                "1",
                str(thumb),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and thumb.exists():
            return str(thumb)
    except Exception:
        pass

    # Fallback: create a minimal valid JPEG (1x1 red pixel)
    # Using Pillow if available, otherwise a raw minimal JPEG
    try:
        from PIL import Image

        img = Image.new("RGB", (1, 1), color=(30, 30, 46))
        img.save(thumb, "JPEG")
        return str(thumb)
    except ImportError:
        pass

    # Last resort: 1x1 blue JPEG as raw bytes
    minimal_jpg = bytes(
        [
            0xFF,
            0xD8,
            0xFF,
            0xE0,
            0x00,
            0x10,
            0x4A,
            0x46,
            0x49,
            0x46,
            0x00,
            0x01,
            0x01,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x00,
            0xFF,
            0xDB,
            0x00,
            0x43,
            0x00,
            0x08,
            0x06,
            0x06,
            0x07,
            0x06,
            0x05,
            0x08,
            0x07,
            0x07,
            0x07,
            0x09,
            0x09,
            0x08,
            0x0A,
            0x0C,
            0x14,
            0x0D,
            0x0C,
            0x0B,
            0x0B,
            0x0C,
            0x19,
            0x12,
            0x13,
            0x0F,
            0x14,
            0x1D,
            0x1A,
            0x1F,
            0x1E,
            0x1D,
            0x1A,
            0x1C,
            0x1C,
            0x20,
            0x24,
            0x2E,
            0x27,
            0x20,
            0x22,
            0x2C,
            0x23,
            0x1C,
            0x1C,
            0x28,
            0x37,
            0x29,
            0x2C,
            0x30,
            0x31,
            0x34,
            0x34,
            0x34,
            0x1F,
            0x27,
            0x39,
            0x3D,
            0x38,
            0x32,
            0x3C,
            0x2E,
            0x33,
            0x34,
            0x32,
            0xFF,
            0xDB,
            0x00,
            0x43,
            0x01,
            0x09,
            0x09,
            0x09,
            0x0C,
            0x0B,
            0x0C,
            0x18,
            0x0D,
            0x0D,
            0x18,
            0x32,
            0x21,
            0x1C,
            0x21,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0x32,
            0xFF,
            0xC0,
            0x00,
            0x11,
            0x08,
            0x00,
            0x01,
            0x00,
            0x01,
            0x03,
            0x01,
            0x22,
            0x00,
            0x02,
            0x11,
            0x01,
            0x03,
            0x11,
            0x01,
            0xFF,
            0xC4,
            0x00,
            0x1F,
            0x00,
            0x00,
            0x01,
            0x05,
            0x01,
            0x01,
            0x01,
            0x01,
            0x01,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x01,
            0x02,
            0x03,
            0x04,
            0x05,
            0x06,
            0x07,
            0x08,
            0x09,
            0x0A,
            0x0B,
            0xFF,
            0xC4,
            0x00,
            0xB5,
            0x10,
            0x00,
            0x02,
            0x01,
            0x03,
            0x03,
            0x02,
            0x04,
            0x03,
            0x05,
            0x05,
            0x04,
            0x04,
            0x00,
            0x00,
            0x01,
            0x7D,
            0x01,
            0x02,
            0x03,
            0x00,
            0x04,
            0x11,
            0x05,
            0x12,
            0x21,
            0x31,
            0x41,
            0x06,
            0x13,
            0x51,
            0x61,
            0x07,
            0x22,
            0x71,
            0x14,
            0x32,
            0x81,
            0x91,
            0xA1,
            0x08,
            0x23,
            0x42,
            0xB1,
            0xC1,
            0x15,
            0x52,
            0xD1,
            0xF0,
            0x24,
            0x33,
            0x62,
            0x72,
            0x82,
            0x09,
            0x0A,
            0x16,
            0x17,
            0x18,
            0x19,
            0x1A,
            0x25,
            0x26,
            0x27,
            0x28,
            0x29,
            0x2A,
            0x34,
            0x35,
            0x36,
            0x37,
            0x38,
            0x39,
            0x3A,
            0x43,
            0x44,
            0x45,
            0x46,
            0x47,
            0x48,
            0x49,
            0x4A,
            0x53,
            0x54,
            0x55,
            0x56,
            0x57,
            0x58,
            0x59,
            0x5A,
            0x63,
            0x64,
            0x65,
            0x66,
            0x67,
            0x68,
            0x69,
            0x6A,
            0x73,
            0x74,
            0x75,
            0x76,
            0x77,
            0x78,
            0x79,
            0x7A,
            0x83,
            0x84,
            0x85,
            0x86,
            0x87,
            0x88,
            0x89,
            0x8A,
            0x92,
            0x93,
            0x94,
            0x95,
            0x96,
            0x97,
            0x98,
            0x99,
            0x9A,
            0xA2,
            0xA3,
            0xA4,
            0xA5,
            0xA6,
            0xA7,
            0xA8,
            0xA9,
            0xAA,
            0xB2,
            0xB3,
            0xB4,
            0xB5,
            0xB6,
            0xB7,
            0xB8,
            0xB9,
            0xBA,
            0xC2,
            0xC3,
            0xC4,
            0xC5,
            0xC6,
            0xC7,
            0xC8,
            0xC9,
            0xCA,
            0xD2,
            0xD3,
            0xD4,
            0xD5,
            0xD6,
            0xD7,
            0xD8,
            0xD9,
            0xDA,
            0xE1,
            0xE2,
            0xE3,
            0xE4,
            0xE5,
            0xE6,
            0xE7,
            0xE8,
            0xE9,
            0xEA,
            0xF1,
            0xF2,
            0xF3,
            0xF4,
            0xF5,
            0xF6,
            0xF7,
            0xF8,
            0xF9,
            0xFA,
            0xFF,
            0xC4,
            0x00,
            0x1F,
            0x01,
            0x00,
            0x03,
            0x01,
            0x01,
            0x01,
            0x01,
            0x01,
            0x01,
            0x01,
            0x01,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x01,
            0x02,
            0x03,
            0x04,
            0x05,
            0x06,
            0x07,
            0x08,
            0x09,
            0x0A,
            0x0B,
            0xFF,
            0xC4,
            0x00,
            0xB5,
            0x11,
            0x00,
            0x02,
            0x01,
            0x02,
            0x04,
            0x04,
            0x03,
            0x04,
            0x07,
            0x05,
            0x04,
            0x04,
            0x00,
            0x01,
            0x02,
            0x77,
            0x00,
            0x01,
            0x02,
            0x03,
            0x11,
            0x04,
            0x05,
            0x21,
            0x31,
            0x06,
            0x12,
            0x41,
            0x51,
            0x07,
            0x61,
            0x71,
            0x13,
            0x22,
            0x32,
            0x81,
            0x08,
            0x14,
            0x42,
            0x91,
            0xA1,
            0xB1,
            0xC1,
            0x09,
            0x23,
            0x33,
            0x52,
            0xF0,
            0x15,
            0x62,
            0x72,
            0xD1,
            0x0A,
            0x16,
            0x24,
            0x34,
            0xE1,
            0x25,
            0xF1,
            0x17,
            0x18,
            0x19,
            0x1A,
            0x26,
            0x27,
            0x28,
            0x29,
            0x2A,
            0x35,
            0x36,
            0x37,
            0x38,
            0x39,
            0x3A,
            0x43,
            0x44,
            0x45,
            0x46,
            0x47,
            0x48,
            0x49,
            0x4A,
            0x53,
            0x54,
            0x55,
            0x56,
            0x57,
            0x58,
            0x59,
            0x5A,
            0x63,
            0x64,
            0x65,
            0x66,
            0x67,
            0x68,
            0x69,
            0x6A,
            0x73,
            0x74,
            0x75,
            0x76,
            0x77,
            0x78,
            0x79,
            0x7A,
            0x82,
            0x83,
            0x84,
            0x85,
            0x86,
            0x87,
            0x88,
            0x89,
            0x8A,
            0x92,
            0x93,
            0x94,
            0x95,
            0x96,
            0x97,
            0x98,
            0x99,
            0x9A,
            0xA2,
            0xA3,
            0xA4,
            0xA5,
            0xA6,
            0xA7,
            0xA8,
            0xA9,
            0xAA,
            0xB2,
            0xB3,
            0xB4,
            0xB5,
            0xB6,
            0xB7,
            0xB8,
            0xB9,
            0xBA,
            0xC2,
            0xC3,
            0xC4,
            0xC5,
            0xC6,
            0xC7,
            0xC8,
            0xC9,
            0xCA,
            0xD2,
            0xD3,
            0xD4,
            0xD5,
            0xD6,
            0xD7,
            0xD8,
            0xD9,
            0xDA,
            0xE2,
            0xE3,
            0xE4,
            0xE5,
            0xE6,
            0xE7,
            0xE8,
            0xE9,
            0xEA,
            0xF2,
            0xF3,
            0xF4,
            0xF5,
            0xF6,
            0xF7,
            0xF8,
            0xF9,
            0xFA,
            0xFF,
            0xDA,
            0x00,
            0x0C,
            0x03,
            0x01,
            0x00,
            0x02,
            0x11,
            0x03,
            0x11,
            0x00,
            0x3F,
            0x00,
            0xF2,
            0x40,
            0x00,
            0x04,
            0x0E,
            0x31,
            0xC0,
            0x00,
            0x7D,
            0x28,
            0xA2,
            0x8F,
            0xF5,
            0x7F,
            0x8D,
            0x7F,
            0xFF,
            0xD9,
        ]
    )
    try:
        with open(thumb, "wb") as f:
            f.write(minimal_jpg)
        return str(thumb)
    except Exception:
        return ""


def _ensure_past_arc_thumb() -> str:
    """Return the path to the PAST_ARC thumbnail if it exists.

    Expected at ~/Videos/Music/Music.jpg (already placed by the user).
    """
    thumb = PAST_ARC_FILE / "music.jpg"
    return str(thumb) if thumb.exists() else ""


def _handle_start(args: list[str]) -> None:
    """Start a session directly from CLI arguments (no Rofi UI)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="pomodoro start",
        description="Start a pomodoro session from the command line.",
    )
    parser.add_argument(
        "--task",
        "-t",
        required=True,
        help="Task name (e.g. 'read', 'write')",
    )
    parser.add_argument(
        "--video",
        "-v",
        required=True,
        help="Video filename (e.g. 'study.mp4'), 'random', or 'arc' for CURRENT_ARC soundtrack",
    )
    parser.add_argument(
        "--rhythm",
        "-r",
        default="default",
        help='Rhythm: "default" to use the video\'s preset, or "work-break" like "25-5"',
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=None,
        help="Number of pomodoros (default: from rhythm preset or 1)",
    )
    parser.add_argument(
        "--warmup",
        "-w",
        type=int,
        default=None,
        help="Warm-up seconds (default: from rhythm preset or 0)",
    )
    parser.add_argument(
        "--audio",
        "-a",
        action="store_true",
        help="Play audio only (no video window, generates mp3 from video)",
    )

    parsed = parser.parse_args(args)

    task = parsed.task
    arc_mode = parsed.video.lower() in ("arc", "current_arc")
    past_arc_mode = parsed.video.lower() == "past_arc"
    cliamp_mode = parsed.video.lower() in ("cliamp", "lofi", "cliamp_lofi")
    random_picked = parsed.video.lower() == "random"

    # ── Resolve video path (or pick random / arc / cliamp) ────────────────
    if past_arc_mode:
        video_name = "PAST_ARC"
        video_path = PAST_ARC_FILE
        parsed.audio = True
        arc_mode = True
    elif cliamp_mode:
        # CLIAMP lofi radio — audio comes from the cliamp daemon, not mpv
        video_name = "CLIAMP"
        video_path = Path("CLIAMP")  # used as identifier in state
        parsed.audio = True
    elif arc_mode:
        # Current arc soundtrack — no video file needed
        video_name = "CURRENT_ARC"
        video_path = ARC_SOUNDTRACK  # used as identifier in state
        parsed.audio = True  # arc is always audio-only
    elif random_picked:
        video_path = _pick_random_video()
        if video_path is None:
            print(
                f"Error: No video files found in {POMO_DIR}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        video_path = _resolve_video(parsed.video)
        if video_path is None:
            print(
                f"Error: Video '{parsed.video}' not found in {POMO_DIR}",
                file=sys.stderr,
            )
            sys.exit(1)

    video_name = video_path.name

    # ---- Generate mp3 for audio-only mode ----
    if parsed.audio and not arc_mode and not cliamp_mode:
        _ensure_mp3(video_path)

    # ── Determine work/break/count/warmup ─────────────────────────────────
    work_min = 25
    break_min = 5
    total = 1
    warm_up_secs = 0
    schedule = None

    # Look up video preset first (to get warm_up_secs regardless of mode)
    rhythm_data = _lookup_default_rhythm(video_name)
    if rhythm_data is not None:
        _preset_work, _preset_break, _preset_total, warm_up_secs, schedule = rhythm_data

    if parsed.rhythm and parsed.rhythm.lower() != "default":
        # User passed a custom rhythm like "25-5" or "50-10"
        try:
            parts = parsed.rhythm.split("-")
            work_min = int(parts[0])
            break_min = int(parts[1])
        except (ValueError, IndexError):
            print(
                f"Error: Invalid rhythm '{parsed.rhythm}'. "
                f"Use 'default' or 'work-break' (e.g. '25-5').",
                file=sys.stderr,
            )
            sys.exit(1)
        total = parsed.count or 1
        if parsed.warmup is not None:
            warm_up_secs = parsed.warmup
    else:
        if rhythm_data is not None:
            work_min, break_min, total, warm_up_secs, schedule = rhythm_data
        else:
            # No preset found — fallback to 25-5 × 4 for random/arc/cliamp,
            # 25-5 × 1 for explicit
            if random_picked or arc_mode or cliamp_mode:
                work_min, break_min, total, warm_up_secs = 25, 5, 4, 0
        if parsed.count is not None:
            total = parsed.count
        if parsed.warmup is not None:
            warm_up_secs = parsed.warmup

    # ── Check for existing active session ─────────────────────────────────
    if STATE_FILE.exists():
        state = PomodoroState.load(STATE_FILE)
        print(
            f"Error: A session is already active ({state.task}). "
            f"Stop it first with 'pomodoro stop'.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Start the session ─────────────────────────────────────────────────
    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tm.init_defaults(DEFAULT_TASKS)

    ctrl = TimerController(
        on_session_complete=lambda t, w, c: tm.log(t, f"{w}m \u00d7 {c}")
    )

    ctrl.start(
        task,
        str(video_path),
        work_min,
        break_min,
        total,
        warm_up_secs,
        schedule=schedule or None,
        audio_only=parsed.audio,
        arc_mode=arc_mode,
        cliamp_mode=cliamp_mode,
    )

    rhythm_label = f"{work_min}/{break_min}"
    print(
        f"\U0001f345 Started: {task} | {video_name} | {rhythm_label} | "
        f"{total} pomodoro(s)"
        + (f" | {warm_up_secs}s warm-up" if warm_up_secs else "")
        + (" \U0001f3b2" if random_picked else "")
        + (" \U0001f3b5" if parsed.audio else "")
        + (" \U0001f3b6 ARC" if arc_mode else "")
        + (" \U0001f3a7 CLIAMP lofi" if cliamp_mode else "")
    )

    # ── Stay alive to handle transitions ──────────────────────────────────
    # The timer runs on a daemon thread, so we must keep this process alive
    # to allow phase transitions (work -> break -> work -> done).
    # We poll periodically, identical to what polybar's `pomodoro status` does.
    try:
        while STATE_FILE.exists():
            ctrl.handle_expired()
            # Print a compact status line (carriage-return to overwrite)
            line = _status_line()
            if not line:
                break
            print(f"\r{line}  ", end="", flush=True)
            time.sleep(1)
        print()  # newline after session ends
    except KeyboardInterrupt:
        print("\nInterrupted. Stopping session...")
        ctrl.clear_state()


# ── Startup preset handler ──────────────────────────────────────────────────────


def _run_session_loop(ctrl: TimerController) -> bool:
    """Poll a running session until it finishes or Ctrl-C stops it.

    Returns True if the user interrupted the session.
    """
    try:
        while STATE_FILE.exists():
            ctrl.handle_expired()
            line = _status_line()
            if not line:
                break
            print(f"\r{line}  ", end="", flush=True)
            time.sleep(1)
        print()
        return False
    except KeyboardInterrupt:
        print("\nInterrupted. Stopping session...")
        ctrl.clear_state()
        return True


def _start_preset_session(preset_name: str, tm: TaskManager) -> TimerController:
    """Start a startup preset session. Returns the controller (no polling)."""
    preset = STARTUP_PRESETS[preset_name]

    # Merge global EVENT_COMMANDS with the preset's own commands
    preset_runner = CommandRunner.merge(
        EVENT_COMMANDS,
        getattr(preset, "commands", None),
        log_path=CMD_LOG_FILE,
    )

    ctrl = TimerController(
        on_session_complete=lambda t, w, c: tm.log(t, f"{w}m × {c}"),
        cmd_runner=preset_runner,
    )

    first_work, first_break = preset.schedule[0]
    total = len(preset.schedule)

    # ── Determine start mode from start_dir ────────────────────────────────
    # Directory → arc_mode (build shuffled playlist from directory contents)
    # File      → audio_only (play a single video's audio track)
    start_path = Path(preset.start_dir) if preset.start_dir else None

    if start_path is not None and start_path.is_dir():
        arc_mode = True
        audio_only = True
        silence_secs = preset.silence_secs
        warm_up_secs = 0
    elif start_path is not None and start_path.is_file():
        arc_mode = False
        audio_only = False
        silence_secs = ARC_SILENCE_SECONDS
        # Look up warm-up from video presets
        rhythm_data = _lookup_default_rhythm(start_path.name)
        if rhythm_data is not None:
            *_, warm_up_secs, _ = rhythm_data
        else:
            warm_up_secs = 0
    else:
        # Empty or invalid — no audio
        arc_mode = False
        audio_only = False
        silence_secs = 0
        warm_up_secs = 0

    ctrl.start(
        task="startup",
        video=preset.start_dir,
        work_min=first_work,
        break_min=first_break,
        total=total,
        warm_up_secs=warm_up_secs,
        schedule=preset.schedule,
        schedule_labels=preset.labels,
        audio_only=audio_only,
        arc_mode=arc_mode,
        silence_secs=silence_secs,
        notify_color=preset.notify_color,
        notify_title=preset.notify_title,
        notify_desc=preset.notify_desc,
        notify_timeout=preset.notify_timeout,
        notify_phases=preset.notify_phases or {},
        say_label=preset.say_label,
        say_dir=str(SOUNDS_DIR / preset_name) if preset.say_label else "",
    )

    # Persist merged commands + audio switches into state so OTHER processes
    # (polybar status, pomodoro next) rebuild the same preset-aware runner.
    state = PomodoroState.load(STATE_FILE)
    state.commands = preset_runner._commands
    if preset.switches:
        state.arc_switches = preset.switches
    state.save(STATE_FILE)

    print(f"\U0001f345 {preset_name}: {preset.description}")
    return ctrl


def _start_video_session(
    task: str, video_name: str, tm: TaskManager
) -> TimerController:
    """Start a session for a single video using its default rhythm.

    Falls back to 25-5 × 1 when the video has no POMODORO_DEFAULTS entry.
    """
    rhythm_data = _lookup_default_rhythm(video_name)
    if rhythm_data is None:
        work_min, break_min, total, warm_up_secs, schedule = 25, 5, 1, 0, None
    else:
        work_min, break_min, total, warm_up_secs, schedule = rhythm_data

    video_path = _resolve_video(video_name)
    if video_path is None:
        raise FileNotFoundError(f"Video '{video_name}' not found in {POMO_DIR}")

    ctrl = TimerController(
        on_session_complete=lambda t, w, c: tm.log(t, f"{w}m × {c}"),
        cmd_runner=_cmd_runner,
    )

    ctrl.start(
        task=task,
        video=str(video_path),
        work_min=work_min,
        break_min=break_min,
        total=total,
        warm_up_secs=warm_up_secs,
        schedule=schedule or None,
    )

    print(f"\U0001f345 {task}: {video_name} — {work_min}/{break_min} × {total}")
    return ctrl


def _resolve_chain_step(step) -> tuple[str | None, str, str | None]:
    """Resolve one Chain step into (task, item) plus a day-cycle note.

    A step may be a string (video/preset name), a ``(task, item)`` tuple, or
    a list of steps whose element is chosen by day of month: ``day % n`` picks
    the index (a day that is a multiple of ``n`` → first element, +1 → second,
    …). Lists may appear inside tuples too, e.g. ``("deep work", [a, b])``.
    """
    day = datetime.now().day

    if isinstance(step, list):
        n = len(step)
        if n == 0:
            raise ValueError(f"empty day-cycle list: {step!r}")
        picked = step[day % n]
        task, item, _ = _resolve_chain_step(picked)
        return task, item, f"day {day} % {n} = {day % n} → {item}"

    if isinstance(step, tuple):
        task, item = step
        if isinstance(item, list):
            n = len(item)
            if n == 0:
                raise ValueError(f"empty day-cycle list: {step!r}")
            picked = item[day % n]
            inner_task, inner_item, note = _resolve_chain_step(picked)
            return inner_task or task, inner_item, note
        return task, item, None

    return None, step, None


def _handle_chain(name: str) -> None:
    """Run a Chain: each step starts when the previous one completes."""
    chain = CHAINS[name]

    if STATE_FILE.exists():
        state = PomodoroState.load(STATE_FILE)
        print(
            f"Error: A session is already active ({state.task}). "
            f"Stop it first with 'pomodoro stop'.",
            file=sys.stderr,
        )
        sys.exit(1)

    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tm.init_defaults(DEFAULT_TASKS)

    print(f"⛓  Chain: {name}")
    if chain.description:
        print(f"   {chain.description}")

    for i, step in enumerate(chain.steps, 1):
        try:
            task, item, day_note = _resolve_chain_step(step)
        except ValueError as exc:
            raise ValueError(f"Chain '{name}' step {i}: {exc}") from exc
        if day_note:
            print(f"\n⛓  [{i}/{len(chain.steps)}] {day_note}")

        if item in STARTUP_PRESETS:
            print(f"\n⛓  [{i}/{len(chain.steps)}] Preset: {item}")
            ctrl = _start_preset_session(item, tm)
        else:
            video_name = str(item)
            task_name = task or Path(video_name).stem
            print(f"\n⛓  [{i}/{len(chain.steps)}] Video: {video_name}")
            ctrl = _start_video_session(task_name, video_name, tm)

        interrupted = _run_session_loop(ctrl)
        if interrupted:
            print(f"\n⛓  Chain '{name}' stopped at step {i}/{len(chain.steps)}.")
            return

    print(f"\n⛓  Chain '{name}' complete! \U0001f389")


def _handle_startup_preset(name: str) -> None:
    """Start a pre-configured startup pomodoro session."""
    if STATE_FILE.exists():
        state = PomodoroState.load(STATE_FILE)
        print(
            f"Error: A session is already active ({state.task}). "
            f"Stop it first with 'pomodoro stop'.",
            file=sys.stderr,
        )
        sys.exit(1)

    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tm.init_defaults(DEFAULT_TASKS)

    ctrl = _start_preset_session(name, tm)
    _run_session_loop(ctrl)


# ── Subcommand dispatch ───────────────────────────────────────────────────────


def _handle_random() -> None:
    """Play through all available videos randomly, one pomodoro each.

    Detaches into the background.  Run ``pomodoro skip_random`` to skip
    to the next video, or ``pomodoro stop`` to quit."""
    import os
    import random

    # ── Fork to background ─────────────────────────────────────────────────
    pid = os.fork()
    if pid > 0:
        print(f"🎲 Random pomodoro started (PID {pid})")
        print(f"   pomodoro skip_random  →  skip to next video")
        print(f"   pomodoro stop         →  stop completely")
        return  # parent exits, terminal is free

    os.setsid()  # detach from terminal

    # Redirect output to /dev/null (no terminal attached)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, sys.stdin.fileno())
    os.dup2(devnull, sys.stdout.fileno())
    os.dup2(devnull, sys.stderr.fileno())
    os.close(devnull)

    # ── Main loop ──────────────────────────────────────────────────────────

    if STATE_FILE.exists():
        state = PomodoroState.load(STATE_FILE)
        print(
            f"Error: A session is already active ({state.task}). "
            f"Stop it first with 'pomodoro stop'.",
            file=sys.stderr,
        )
        sys.exit(1)

    videos = _list_videos()
    if not videos:
        print(f"Error: No video files found in {POMO_DIR}", file=sys.stderr)
        sys.exit(1)

    random.shuffle(videos)
    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tm.init_defaults(DEFAULT_TASKS)

    SKIP_RANDOM_FILE.unlink(missing_ok=True)  # clean from previous runs

    for v in videos:
        rhythm_data = _lookup_default_rhythm(v.name)
        if rhythm_data is None:
            work_min, break_min, total, warm_up_secs, schedule = 25, 5, 1, 0, None
        else:
            work_min, break_min, total, warm_up_secs, schedule = rhythm_data

        print(
            f"\n🎲 {v.name}  —  {work_min}min × {total}  (pomodoro skip_random to skip)",
            flush=True,
        )

        ctrl = TimerController(
            on_session_complete=lambda t, w, c: tm.log(t, f"{w}m × {c}"),
            cmd_runner=_cmd_runner,
        )

        ctrl.start(
            task="random",
            video=str(v),
            work_min=work_min,
            break_min=break_min,
            total=total,
            warm_up_secs=warm_up_secs,
            schedule=schedule or None,
        )

        # Poll until session ends or skip_random is run
        try:
            while STATE_FILE.exists():
                ctrl.handle_expired()
                line = _status_line()
                if not line:
                    break
                print(f"\r{line}  ", end="", flush=True)

                if SKIP_RANDOM_FILE.exists():
                    SKIP_RANDOM_FILE.unlink()
                    print("\n⏭ Skipping…")
                    ctrl.clear_state()
                    break

                time.sleep(0.9)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            ctrl.clear_state()
            sys.exit(0)

    notify("🎲 Random pomodoro", "All videos finished!")


def _handle_log() -> None:
    """Print session history followed by today's command-execution logs."""
    today_str = time.strftime("%Y-%m-%d")

    # ── Session history ────────────────────────────────────────────────────
    if HISTORY_FILE.exists():
        lines = [l.strip() for l in HISTORY_FILE.read_text().splitlines() if l.strip()]
        if lines:
            print(f"{'Date':12} {'Time':7}  Task / Info")
            print("-" * 70)
            for line in lines:
                try:
                    # [YYYY-MM-DD HH:MM] task — duration_info
                    bracket, rest = line.split("] ", 1)
                    date_time = bracket[1:]
                    date_str, time_str = date_time.split(" ", 1)
                    if not rest or rest.startswith("—"):
                        rest = "(no task) " + rest
                    print(f"{date_str:12} {time_str:7}  {rest}")
                except (ValueError, IndexError):
                    print(line)
            print()

    # ── Today's command-execution log ───────────────────────────────────────
    if CMD_LOG_FILE.exists():
        cmd_lines = [
            l.strip()
            for l in CMD_LOG_FILE.read_text().splitlines()
            if l.strip() and l.startswith(f"[{today_str} ")
        ]
        if cmd_lines:
            print(f"── Commands run today ({today_str}) ──")
            for line in cmd_lines:
                print(line)
            print()

    if not HISTORY_FILE.exists() and not CMD_LOG_FILE.exists():
        print("No history yet.")


def _handle_list() -> None:
    """Print the video presets, arc sources, startup presets, and chains."""
    # ── Video presets ──────────────────────────────────────────────────────
    print("🎬 Video presets (POMODORO_DEFAULTS)")
    print(f"  {'video':<28} {'rhythm':<34} {'warmup':>8}  file")
    print("-" * 72)
    for entry in POMODORO_DEFAULTS:
        video = entry[0]
        if isinstance(entry[1], list):
            # rhythm-list style: [(work, break[, reps]), ..., warm_up]
            warm_up = entry[1][-1]
            parts = []
            for tup in entry[1][:-1]:
                work, break_ = tup[0], tup[1]
                reps = tup[2] if len(tup) >= 3 else 1
                seg = f"{work}/{break_}"
                if reps > 1:
                    seg += f" ×{reps}"
                parts.append(seg)
            rhythm = " → ".join(parts)
        else:
            work, break_, reps = entry[1], entry[2], entry[3]
            warm_up = entry[4] if len(entry) >= 5 else 0
            rhythm = f"{work}/{break_} ×{reps}"
        status = "✓" if (POMO_DIR / video).exists() else "✗ missing"
        print(f"  {video:<28} {rhythm:<34} {f'{warm_up:g}s':>8}  {status}")

    # ── Special video sources ──────────────────────────────────────────────
    print()
    print("📀 Special video sources (--video <value>)")
    arc_status = "✓" if ARC_SOUNDTRACK.exists() else "✗ missing"
    print(f"  {'arc / CURRENT_ARC':<20} ARC soundtrack  {ARC_SOUNDTRACK}  {arc_status}")
    past_status = "✓" if PAST_ARC_FILE.exists() else "✗ missing"
    print(
        f"  {'past_arc / PAST_ARC':<20} music folder    {PAST_ARC_FILE}  {past_status}"
    )
    print(f"  {'cliamp / lofi':<20} CLIAMP lofi radio ({CLIAMP_LOFI_URL})")
    print(f"  {'random':<20} random video from {POMO_DIR}")

    # ── Startup presets ────────────────────────────────────────────────────
    print()
    print("🚀 Startup presets (pomodoro <preset>)")
    for name, preset in STARTUP_PRESETS.items():
        marker = " 🔊" if preset.say_label else ""
        print(f"  {name:<20} {preset.description}{marker}")

    # ── Chains ─────────────────────────────────────────────────────────────
    print()
    print("⛓  Chains (pomodoro <chain>)")
    for name, chain in CHAINS.items():
        print(f"  {name:<20} {chain.description or '—'}")

    # ── Commands ─────────────────────────────────────────────────────────────
    print()
    print("🖥  Commands (pomodoro --command <name>)")
    for name, cmd in COMMANDS.items():
        print(f"  {name:<20} {cmd}")


def _handle_command(name: str) -> None:
    """Run a named command from the COMMANDS registry (fire and forget)."""
    cmd = COMMANDS.get(name)
    if cmd is None:
        print(
            f"Unknown command: {name!r}. Available: {', '.join(COMMANDS)}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"▶ Running '{name}'...")
    subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_subcommand(args: list[str]) -> None:
    """Handle polybar subcommands: status, toggle, stop, next, start."""
    cmd = args[0] if args else ""
    ctrl = TimerController(cmd_runner=_runner_for_active_session())

    if cmd == "status":
        print(_status_line())
    elif cmd == "toggle":
        ctrl.toggle()
    elif cmd == "stop":
        ctrl.clear_state()
    elif cmd == "next":
        ctrl.skip_phase()
    elif cmd == "start":
        _handle_start(args[1:])
    elif cmd == "log":
        _handle_log()
    elif cmd == "random":
        _handle_random()
    elif cmd == "skip_random":
        SKIP_RANDOM_FILE.touch()
    elif cmd in STARTUP_PRESETS:
        _handle_startup_preset(cmd)
    elif cmd in CHAINS:
        _handle_chain(cmd)
    else:
        print(
            "usage: pomodoro {status|toggle|stop|next|start|random|log|<chain>|<preset>}",
            file=sys.stderr,
        )
        sys.exit(1)


# ── Main menu loop ────────────────────────────────────────────────────────────


def _run_ui() -> None:
    """Launch the rofi main menu and dispatch to handlers."""
    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tm.init_defaults(DEFAULT_TASKS)

    ctrl = TimerController(
        on_session_complete=lambda task, w, t: tm.log(task, f"{w}m × {t}"),
        cmd_runner=_cmd_runner,
    )

    while True:
        has_session = STATE_FILE.exists()

        if has_session:
            options = [
                "📊  Current status",
                "▶  New session",
                "✅  Complete pomodoro",
                "📝  Manage tasks",
                "🔥  Heat map",
                "🔄  Reset everything",
            ]
        else:
            options = [
                "▶  New session",
                "✅  Complete pomodoro",
                "📝  Manage tasks",
                "🔥  Heat map",
                "🔄  Reset everything",
            ]

        action = rofi_menu("Pomodoro", options, no_custom=True)
        if action is None:
            sys.exit(0)

        if action.startswith("📊"):
            _handle_status(ctrl)
        elif action.startswith("▶"):
            if _handle_new_session(tm, ctrl):
                sys.exit(0)
        elif action.startswith("✅"):
            _handle_complete(tm)
        elif action.startswith("📝"):
            _handle_manage(tm)
        elif action.startswith("🔥"):
            _handle_heatmap()
        elif action.startswith("🔄"):
            ctrl.clear_state()
            notify("🍅 Pomodoro", "All state cleared.")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    args = sys.argv[1:]
    if args:
        # -log / --log  →  show session history
        if args[0] in ("-log", "--log"):
            _handle_log()
        # -list / --list  →  show video presets
        elif args[0] in ("-list", "--list"):
            _handle_list()
        # --command <name>  →  run a named command
        elif args[0] in ("--command", "-command"):
            if len(args) < 2:
                print("usage: pomodoro --command <name>", file=sys.stderr)
                sys.exit(1)
            _handle_command(args[1])
        elif args[0].startswith("-"):
            _handle_start(args)
        else:
            _run_subcommand(args)
    else:
        _run_ui()


if __name__ == "__main__":
    main()
