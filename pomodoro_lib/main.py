"""CLI entry point — main menu loop, subcommands, and UI flow."""

import re
import sys
import time
from pathlib import Path

from pomodoro_lib.config import (
    BACK_LABEL,
    COUNT_OPTIONS,
    CUSTOM_LABEL,
    DEFAULT_TASKS,
    DURATION_PRESETS,
    HISTORY_FILE,
    PAUSE_FILE,
    POMO_DIR,
    POMODORO_DEFAULTS,
    STATE_FILE,
    TASKS_FILE,
    TASKS_UNIQUE,
)
from pomodoro_lib.rofi import (
    numbered_menu,
    pick_video,
    rofi_menu,
    strip_number,
)
from pomodoro_lib.state import PomodoroState
from pomodoro_lib.tasks import TaskManager
from pomodoro_lib.timer import TimerController, notify

# ── Polybar status line ───────────────────────────────────────────────────────


def _status_line() -> str:
    """Polybar status line. Empty string when no session is active.

    Also handles expired phase transitions so that polybar's periodic
    polling keeps the session moving forward even if the background
    timer thread was killed when the UI process exited.
    """
    if not STATE_FILE.exists():
        return ""

    # Handle any expired phases BEFORE computing the status line.
    # This is the *reliable* transition mechanism – the daemon timer
    # threads started by the UI are only a best-effort optimisation.
    ctrl = TimerController()
    ctrl.handle_expired()

    # Re-check after transition (e.g. the session may have completed)
    if not STATE_FILE.exists():
        return ""

    state = PomodoroState.load(STATE_FILE)
    work_total = state.work_min * 60

    if PAUSE_FILE.exists():
        raw = int(PAUSE_FILE.read_text().strip())
        if state.phase == "work" and raw > work_total:
            secs = raw - work_total  # remaining warm-up when paused
        else:
            secs = raw
        icon = "⏸"
    elif state.phase == "break":
        secs = state.remaining_seconds
        icon = "☕"
    else:
        raw = state.remaining_seconds
        if raw > work_total:
            secs = raw - work_total  # still in warm-up
            icon = "🔥"
        else:
            secs = raw
            icon = "▶"

    mins = secs // 60
    secs_rem = secs % 60
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
    audio_only = False

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
            choice = pick_video(POMO_DIR)
            if choice is None:
                return False  # ESC → exit
            if choice == BACK_LABEL:
                step = 1
                continue
            video_name = choice
            video = str(POMO_DIR / video_name)
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
                    )
                    return True
                # Personalized → fall through to step 4

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
                        audio_only=audio_only,
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
        info = f"☕  {state.task}   •   {mins}m {secs_rem}s break   •   session {state.current}/{state.total} next"
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

    If `name` already has an extension (.mp4, .webm), use it directly.
    Otherwise try .mp4 then .webm.
    """
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
        help="Video filename (e.g. 'study.mp4') or 'random' to pick one randomly",
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

    # ── Resolve video path (or pick random) ───────────────────────────────
    random_picked = parsed.video.lower() == "random"

    if random_picked:
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
    if parsed.audio:
        _ensure_mp3(video_path)

    # ── Determine work/break/count/warmup ─────────────────────────────────
    work_min = 25
    break_min = 5
    total = 1
    warm_up_secs = 0
    schedule = None

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
        warm_up_secs = parsed.warmup or 0
    else:
        # Look up default rhythm from POMODORO_DEFAULTS
        rhythm_data = _lookup_default_rhythm(video_name)
        if rhythm_data is not None:
            work_min, break_min, total, warm_up_secs, schedule = rhythm_data
        else:
            # No preset found — fallback to 25-5 × 4 for random, 25-5 × 1 for explicit
            if random_picked:
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
    )

    rhythm_label = f"{work_min}/{break_min}"
    print(
        f"\U0001f345 Started: {task} | {video_name} | {rhythm_label} | "
        f"{total} pomodoro(s)"
        + (f" | {warm_up_secs}s warm-up" if warm_up_secs else "")
        + (" \U0001f3b2" if random_picked else "")
        + (" \U0001f3b5" if parsed.audio else "")
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


# ── Subcommand dispatch ───────────────────────────────────────────────────────


def _run_subcommand(args: list[str]) -> None:
    """Handle polybar subcommands: status, toggle, stop, next, start."""
    cmd = args[0] if args else ""
    ctrl = TimerController()

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
    else:
        print(
            "usage: pomodoro {status|toggle|stop|next|start [options]}",
            file=sys.stderr,
        )
        sys.exit(1)


# ── Main menu loop ────────────────────────────────────────────────────────────


def _run_ui() -> None:
    """Launch the rofi main menu and dispatch to handlers."""
    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tm.init_defaults(DEFAULT_TASKS)

    ctrl = TimerController(
        on_session_complete=lambda task, w, t: tm.log(task, f"{w}m × {t}")
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
        # If the first argument starts with '-', treat it as a 'start' command
        if args[0].startswith("-"):
            _handle_start(args)
        else:
            _run_subcommand(args)
    else:
        _run_ui()


if __name__ == "__main__":
    main()
