"""Timer controller — background work/break cycles, mpv, notifications."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from pomodoro_lib.commands import CommandRunner
from pomodoro_lib.constants import (
    ARC_SILENCE_SECONDS,
    ARC_SOUNDTRACK,
    BELL_30_PLAYED,
    BELL_BEGIN_PLAYED,
    CLIAMP_LOFI_URL,
    CLIAMP_PLAYLIST,
    EXTRA_WORK_SECS,
    FINISH_FILE,
    FINISH_PLAYED,
    INCLUDE_DURATION_FILES,
    MPV_SOCKET,
    NOTIFY_COLORS,
    PAUSE_FILE,
    PAUSE_TS,
    PID_FILE,
    POMODORO_DEFAULTS,
    REFLECTION_SECS,
    STATE_FILE,
    TMP_DIR,
    TRANSITION_LOCK,
    WORK_BELL_PLAYED,
    cliamp_pause,
    cliamp_play,
    cliamp_start,
    cliamp_stop,
)
from pomodoro_lib.state import PomodoroState


def ensure_silence_mp3(silence_secs: int = ARC_SILENCE_SECONDS) -> Path:
    """Generate or return cached silence mp3."""
    path = TMP_DIR / f"{silence_secs}s-silence.mp3"
    if not path.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=44100:cl=stereo",
                "-t",
                str(silence_secs),
                "-q:a",
                "14",
                "-acodec",
                "libmp3lame",
                str(path),
            ],
            capture_output=True,
        )
    return path


def build_arc_playlist(
    directory: Path = ARC_SOUNDTRACK, silence_secs: int = ARC_SILENCE_SECONDS
) -> Path | None:
    """Build a shuffled playlist of arc tracks interleaved with silence.

    Returns a temporary playlist file path, or None if no tracks found.
    """
    import random
    import tempfile

    if not directory.is_dir():
        return None

    tracks = sorted(
        f
        for f in directory.iterdir()
        if f.suffix.lower()
        in (".mp3", ".m4a", ".ogg", ".flac", ".wav", ".opus", ".aac")
    )
    if not tracks:
        return None

    random.shuffle(tracks)
    silence = ensure_silence_mp3(silence_secs)

    pl = tempfile.NamedTemporaryFile(mode="w", suffix=".m3u", delete=False)
    # M3U format: one path per line
    for track in tracks:
        pl.write(f"{silence}\n")
        pl.write(f"{track}\n")
    pl.close()

    return Path(pl.name)


def play_finish_sound() -> None:
    """Play the finish sound in a one-shot mpv process (no window)."""
    if not FINISH_FILE.exists():
        return
    subprocess.Popen(
        ["mpv", "--no-terminal", "--no-video", str(FINISH_FILE)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def play_bell(path: Path) -> None:
    """Play a bell sound in a one-shot mpv process (no window)."""
    if not path.exists():
        return
    subprocess.Popen(
        ["mpv", "--no-terminal", "--no-video", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _slugify(text: str) -> str:
    """Turn a label into a safe mp3 filename (non-alnum runs → single _)."""
    slug = "".join(c if c.isalnum() else "_" for c in text)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")[:60] or "label"


def say_label(say_dir: str, label: str) -> None:
    """Speak a phase label with gtts, caching the mp3 under say_dir.

    Generates the mp3 with gtts-cli the first time a label is needed, then
    plays it with a one-shot mpv process. Missing generation (no network)
    is silently skipped.
    """
    if not label or not say_dir:
        return
    out_dir = Path(say_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{_slugify(label)}.mp3"
    if not (out.exists() and out.stat().st_size > 0):
        subprocess.run(
            ["gtts-cli", label, "--output", str(out)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not out.exists():
            return
    subprocess.Popen(
        ["mpv", "--no-terminal", "--no-video", "--volume=130", str(out)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ── External tool helpers ─────────────────────────────────────────────────────


def notify(
    summary: str,
    body: str = "",
    urgency: str = "normal",
    color: str | None = None,
    timeout: int = 0,
) -> None:
    """Send a dunst notification.

    *urgency* is a direct dunst urgency level (low|normal|critical).
    *color* is a named color (default|red|yellow|blue|…) from NOTIFY_COLORS.
    *timeout* is milliseconds (0 = dunst default).
    If both urgency and color are given, *color* wins.

    Falls back to ``termux-notification`` when dunstify is unavailable
    (e.g. Termux), and to a plain stdout line when neither exists.
    """
    if color:
        urgency = NOTIFY_COLORS.get(color, urgency)
    cmd = ["dunstify", "-u", urgency]
    if timeout:
        cmd += ["-t", str(timeout)]
    cmd += [summary, body]
    try:
        subprocess.run(cmd, capture_output=True)
        return
    except FileNotFoundError:
        pass  # dunstify not installed

    # Termux fallback
    try:
        subprocess.run(
            [
                "termux-notification",
                "--title",
                summary,
                "--content",
                body or summary,
                "--priority",
                "high" if urgency == "critical" else "normal",
            ],
            capture_output=True,
        )
    except FileNotFoundError:
        # No notification daemon at all — log instead of crashing
        print(f"[pomodoro] {summary} — {body}")


def i3_workspace() -> None:
    try:
        subprocess.run(
            ["i3-msg", "workspace --no-auto-back-and-forth 🍅"],
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # not running under i3 (e.g. Termux)


def mpv_cmd(json_cmd: str) -> bool:
    """Send a command to the MPV IPC socket.

    Returns True if the command was sent successfully, False if the
    socket was stale or the mpv process is no longer alive.
    """
    if not MPV_SOCKET.exists():
        return False
    # Always ensure the command ends with a newline (mpv requires it)
    if not json_cmd.endswith("\n"):
        json_cmd += "\n"
    try:
        result = subprocess.run(
            ["socat", "-", str(MPV_SOCKET)],
            input=json_cmd,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return False
    except FileNotFoundError:
        # socat not installed
        return False
    if result.returncode != 0:
        # Stale socket — clean it up so callers don't keep trying
        MPV_SOCKET.unlink(missing_ok=True)
        return False
    return True


def run_cliamp(cmd: str) -> None:
    """Fire a CLIAMP control command (fire and forget).

    ``start_new_session=True`` detaches the daemon into its own session so
    it survives the pomodoro process (e.g. the rofi UI exiting after start,
    or a terminal being closed).
    """
    subprocess.Popen(
        cmd,
        shell=True,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _cliamp_running() -> bool:
    """True if a cliamp daemon is up and reachable via its IPC socket.

    Uses the ``cliamp status`` exit code rather than socket-file existence:
    a stale socket left by a daemon that died without cleaning up would
    otherwise make us skip launching a new one.
    """
    return (
        subprocess.run(
            ["cliamp", "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _ensure_cliamp_playlist() -> None:
    """Write the lofi playlist that cliamp loads to play the lofi radio.

    `cliamp load <name>` reads ~/.config/cliamp/playlists/<name>.toml, so a
    tiny playlist points it at the lofi stream. ``realtime = true`` tells
    cliamp to treat the URL as live radio (reconnect after pause/disconnect).
    """
    path = Path.home() / ".config" / "cliamp" / "playlists" / f"{CLIAMP_PLAYLIST}.toml"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[[track]]\n"
        f'path = "{CLIAMP_LOFI_URL}"\n'
        'title = "Lofi Stream"\n'
        "realtime = true\n"
    )


def start_cliamp() -> None:
    """Start CLIAMP playback of the lofi station.

    Launches the daemon if needed, then explicitly loads the lofi playlist.
    Never relies on ``--auto-play`` resume, which would replay whatever
    station was last playing (resume.json).
    """
    _ensure_cliamp_playlist()
    if not _cliamp_running():
        run_cliamp(cliamp_start)
        for _ in range(30):  # wait up to 3s for the daemon socket
            if _cliamp_running():
                break
            time.sleep(0.1)
    run_cliamp(f"cliamp load {CLIAMP_PLAYLIST} --auto-play")


def pause_cliamp() -> None:
    """Pause CLIAMP playback."""
    run_cliamp(cliamp_pause)


def resume_cliamp() -> None:
    """Resume CLIAMP playback."""
    run_cliamp(cliamp_play)


def stop_cliamp() -> None:
    """Stop CLIAMP playback."""
    run_cliamp(cliamp_stop)


def fade_arc_volume(remaining_secs: int, fade_window: int = 15) -> None:
    """Fade mpv volume proportional to remaining seconds in the fade window.

    At remaining_secs >= fade_window  → volume = 100%
    At remaining_secs = 0            → volume = 0%
    Only used for ARC-mode work phases.
    """
    if remaining_secs >= fade_window:
        return  # no fade needed
    vol = max(0, int((remaining_secs / fade_window) * 100))
    mpv_cmd(f'{{"command": ["set_property", "volume", {vol}]}}\n')


def start_mpv(
    video: str,
    audio_only: bool = False,
    arc_mode: bool = False,
    silence_secs: int = ARC_SILENCE_SECONDS,
) -> None:
    """Launch mpv with the given video file (or playlist for arc_mode)."""
    if arc_mode:
        pl = build_arc_playlist(Path(video), silence_secs)
        if pl is None:
            return
        proc = subprocess.Popen(
            [
                "mpv",
                "--no-terminal",
                "--no-video",
                "--input-ipc-server=" + str(MPV_SOCKET),
                "--playlist=" + str(pl),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif audio_only:
        audio_path = Path(video).with_suffix(".mp3")
        if not audio_path.exists():
            return
        proc = subprocess.Popen(
            [
                "mpv",
                "--loop",
                "--no-terminal",
                "--no-video",
                "--input-ipc-server=" + str(MPV_SOCKET),
                str(audio_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        i3_workspace()
        if video and Path(video).exists():
            proc = subprocess.Popen(
                [
                    "mpv",
                    "--loop",
                    "--no-terminal",
                    "--fullscreen",
                    "--panscan=1.0",
                    "--no-video-osd",
                    "--input-ipc-server=" + str(MPV_SOCKET),
                    video,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            return
    PID_FILE.write_text(str(proc.pid))


def kill_mpv() -> None:
    """Kill the mpv process and clean up.  Brief wait for graceful exit."""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            # Brief wait — up to 0.5s max (10 × 50ms)
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.05)
                except OSError:
                    break
            else:
                # Still alive — force kill
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        except (ProcessLookupError, ValueError, FileNotFoundError):
            pass
    PID_FILE.unlink(missing_ok=True)
    MPV_SOCKET.unlink(missing_ok=True)


# ── TimerController ───────────────────────────────────────────────────────────


class TimerController:
    """Manages background timer thread for work/break cycles."""

    def __init__(
        self,
        on_session_complete: Callable[[str, int, int], None] | None = None,
        cmd_runner: CommandRunner | None = None,
    ):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = PomodoroState()
        self._on_session_complete = on_session_complete
        self._cmd_runner = cmd_runner or CommandRunner()

    def _notify(
        self,
        summary: str,
        body: str = "",
        urgency: str | None = None,
        phase: str = "",
        session: int | None = None,
    ) -> None:
        """Send a notification using the session's notify settings.

        *phase* is a key into ``notify_phases`` for per-event overrides
        (``start``, ``pomodoro_done``, ``break_done``, ``reflect``, ``finished``, ``resumed``).

        Each value in ``notify_phases`` is a **list of entries** matching
        the command-runner style:
          * A plain **dict** — applies every time.
          * A **list ``[dict, int]``** — only at that session index.
          * A **list ``[dict, "every:N"]``** — interval filtering.

        If *session* is None, filtered entries are silently skipped.
        """
        if urgency:
            notify(summary, body, urgency=urgency)
            return

        # Start with global overrides
        title = self.state.notify_title
        desc = self.state.notify_desc
        timeout = self.state.notify_timeout

        # Apply matching per-phase entries (later entries win for conflicts)
        entries = self.state.notify_phases.get(phase, [])
        for entry in entries:
            override: dict | None = None

            if isinstance(entry, list):
                try:
                    override, target = entry[0], entry[1]
                except (IndexError, TypeError):
                    continue
                if session is None:
                    continue  # can't filter, skip
                if isinstance(target, int):
                    if session != target:
                        continue
                elif isinstance(target, str) and target.startswith("every:"):
                    try:
                        interval = int(target.split(":", 1)[1])
                    except (ValueError, IndexError):
                        continue
                    if interval < 1 or session % interval != 0:
                        continue
                else:
                    continue  # unknown filter
            elif isinstance(entry, dict):
                override = entry
            else:
                continue

            if override is not None:
                title = override.get("title", title)
                desc = override.get("desc", desc)
                timeout = override.get("timeout", timeout)

        if title:
            summary = title.replace("{summary}", summary)
        if desc:
            body = desc.replace("{body}", body)
        notify(
            summary,
            body,
            color=self.state.notify_color,
            timeout=timeout,
        )

    # ── State persistence ─────────────────────────────────────────────────────
    def load_state(self) -> bool:
        self.state = PomodoroState.load(STATE_FILE)
        return self.state.is_active

    def save_state(self) -> None:
        self.state.save(STATE_FILE)

    def clear_state(self) -> None:
        self._stop_event.set()
        # Only join if called from a *different* thread (not the timer itself)
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=0.5)
        self._stop_event.clear()
        self._thread = None
        # CLIAMP sessions stop the daemon; mpv sessions kill the player
        if STATE_FILE.exists() and PomodoroState.load(STATE_FILE).cliamp_mode:
            stop_cliamp()
        kill_mpv()
        STATE_FILE.unlink(missing_ok=True)
        PAUSE_FILE.unlink(missing_ok=True)
        PAUSE_TS.unlink(missing_ok=True)
        BELL_30_PLAYED.unlink(missing_ok=True)
        BELL_BEGIN_PLAYED.unlink(missing_ok=True)
        WORK_BELL_PLAYED.unlink(missing_ok=True)
        FINISH_PLAYED.unlink(missing_ok=True)
        self.state = PomodoroState()

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(
        self,
        task: str,
        video: str,
        work_min: int,
        break_min: int,
        total: int,
        warm_up_secs: int = 0,
        schedule: list | None = None,
        schedule_labels: list | None = None,
        audio_only: bool = False,
        arc_mode: bool = False,
        cliamp_mode: bool = False,
        silence_secs: int = ARC_SILENCE_SECONDS,
        notify_color: str = "default",
        notify_title: str = "",
        notify_desc: str = "",
        notify_timeout: int = 0,
        notify_phases: dict | None = None,
        say_label: bool = False,
        say_dir: str = "",
    ) -> None:
        self.stop()
        # Fresh start: clear the finish guard from any previous session
        FINISH_PLAYED.unlink(missing_ok=True)
        total_first_secs = warm_up_secs + work_min * 60 + EXTRA_WORK_SECS
        self.state = PomodoroState(
            task=task,
            end_ts=time.time() + total_first_secs,
            work_min=work_min,
            break_min=break_min,
            total=total,
            current=1,
            video=video,
            phase="work",
            warm_up_secs=warm_up_secs,
            schedule=schedule or [],
            schedule_labels=schedule_labels or [],
            audio_only=audio_only,
            arc_mode=arc_mode,
            cliamp_mode=cliamp_mode,
            notify_color=notify_color,
            notify_title=notify_title,
            notify_desc=notify_desc,
            notify_timeout=notify_timeout,
            notify_phases=notify_phases or {},
            say_label=say_label,
            say_dir=say_dir,
        )
        self.save_state()
        if cliamp_mode:
            start_cliamp()
        else:
            start_mpv(video, audio_only, arc_mode, silence_secs)
        self._cmd_runner.run(
            "session_start",
            task=task,
            work_min=work_min,
            break_min=break_min,
            total=total,
            session=0,
            video=video,
        )
        # First pomodoro begins
        self._cmd_runner.run(
            "pomodoro_begin",
            task=task,
            work_min=work_min,
            break_min=break_min,
            total=total,
            session=0,
            video=video,
        )
        warmup_note = f"🔥 {warm_up_secs}s warm-up, then " if warm_up_secs else ""
        self._notify(
            "🍅 Pomodoro started",
            f"{task} — session 1/{total}\n"
            f"{warmup_note}{work_min}min focus — "
            f"{time.strftime('%H:%M', time.localtime(self.state.end_ts))}",
            phase="start",
            session=0,
        )

        # Defensive clear to prevent race conditions
        self._stop_event.clear()
        self._run_timer(total_first_secs, self._on_work_end)
        # Announce the first phase's label (startup presets with say_label)
        self._say_current_label()

    def stop(self) -> None:
        self._stop_event.set()
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=1.0)
        self._stop_event.clear()
        self._thread = None

    def pause(self) -> None:
        if PAUSE_FILE.exists():
            return
        state = PomodoroState.load(STATE_FILE)
        secs_left = state.remaining_seconds
        PAUSE_FILE.write_text(str(secs_left))
        PAUSE_TS.write_text(str(time.time()))
        self._stop_event.set()
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=1.0)
        self._stop_event.clear()
        self._thread = None
        # Pause playback (mpv IPC or CLIAMP)
        if state.cliamp_mode:
            pause_cliamp()
        else:
            mpv_cmd('{"command": ["set_property", "pause", true]}\n')
        notify(
            "🍅 Pomodoro paused",
            f"{secs_left // 60}m left",
            color=state.notify_color,
        )

    def resume(self) -> None:
        if not PAUSE_FILE.exists():
            return

        # Stop any lingering timer thread first
        self._stop_event.set()
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=1.0)
        self._thread = None

        secs_left = int(PAUSE_FILE.read_text().strip())
        PAUSE_FILE.unlink()
        PAUSE_TS.unlink(missing_ok=True)
        self.state = PomodoroState.load(STATE_FILE)
        self.state.end_ts = time.time() + secs_left
        self.save_state()

        # Unpause playback (mpv was paused, never killed)
        if self.state.cliamp_mode:
            resume_cliamp()
        elif MPV_SOCKET.exists():
            mpv_cmd('{"command": ["set_property", "pause", false]}\n')

        self._notify(
            "🍅 Pomodoro resumed",
            f"{secs_left // 60}m left — "
            f"{time.strftime('%H:%M', time.localtime(self.state.end_ts))}",
            phase="resumed",
            session=self.state.current - 1,
        )

        # Ensure a clean stop event before running the new timer
        self._stop_event.clear()
        self._run_timer(secs_left, self._on_phase_end)

    def toggle(self) -> None:
        if PAUSE_FILE.exists():
            self.resume()
        else:
            self.pause()

    def skip_phase(self) -> None:
        """Skip the current phase (work→break or break→work).

        No-op when no session is active.
        """
        if not STATE_FILE.exists():
            return
        self._stop_event.set()
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=1.0)
        self._stop_event.clear()
        self._thread = None
        # Trigger the phase transition — _on_phase_end will load state and
        # route to the correct transition handler based on current phase.
        self._on_phase_end()

    # ── Status (for polybar) ──────────────────────────────────────────────────
    def status_line(self) -> str:
        if not STATE_FILE.exists():
            return ""

        state = PomodoroState.load(STATE_FILE)
        work_total = state.work_min * 60 + EXTRA_WORK_SECS

        if PAUSE_FILE.exists():
            raw = int(PAUSE_FILE.read_text().strip())
            if state.phase == "work" and raw > work_total:
                # Paused during warm-up
                secs = int(raw - work_total)
                icon = "⏸"
            else:
                secs = raw
                icon = "⏸"
        elif state.phase == "break":
            secs = state.remaining_seconds
            icon = "🏹" if state.arc_mode else "🎧" if state.cliamp_mode else "☕"
        elif state.phase == "reflect":
            secs = state.remaining_seconds
            icon = "🤔"
        else:
            raw = state.remaining_seconds
            if raw > work_total:
                # Still in warm-up
                secs = int(raw - work_total)
                icon = "🔥"
            else:
                secs = raw
                icon = "▶"

        mins = secs // 60
        secs_rem = secs % 60
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

    # ── Internal timer ────────────────────────────────────────────────────────
    def _run_timer(self, seconds: int, callback: Callable[[], None]) -> None:
        self._thread = threading.Thread(
            target=self._timer_thread, args=(seconds, callback), daemon=True
        )
        self._thread.start()

    def _timer_thread(self, seconds: int, callback: Callable[[], None]) -> None:
        if self._stop_event.wait(seconds):
            return  # stopped by pause/stop
        callback()

    # ── Phase transitions (side effects, no timer management) ─────────────────

    def _pause_on_break(self) -> bool:
        """Whether to pause video/audio during breaks.

        True for ARC mode, CLIAMP mode, or videos listed in
        INCLUDE_DURATION_FILES.
        """
        if self.state.arc_mode or self.state.cliamp_mode:
            return True
        video_name = Path(self.state.video).name
        return video_name in INCLUDE_DURATION_FILES

    def _pause_audio(self) -> None:
        """Pause playback for a break (mpv IPC or CLIAMP)."""
        if self.state.cliamp_mode:
            pause_cliamp()
        else:
            mpv_cmd('{"command": ["set_property", "pause", true]}')

    def _resume_audio(self) -> None:
        """Resume playback for a work phase (mpv IPC or CLIAMP)."""
        if self.state.cliamp_mode:
            resume_cliamp()
        else:
            mpv_cmd('{"command": ["set_property", "pause", false]}')

    def _say_current_label(self) -> None:
        """Announce the current phase's label via gtts, if enabled.

        Label indexing matches the status line: work N is label[2(N-1)],
        break N is label[2(N-1)+1]. Only fires for startup presets that
        opt in with ``say_label=True`` (their mp3 cache dir is in state).
        """
        if not (self.state.say_label and self.state.say_dir):
            return
        labels = self.state.schedule_labels or []
        if not labels or self.state.phase not in ("work", "break"):
            return
        if self.state.phase == "break":
            idx = (self.state.current - 2) * 2 + 1
        else:
            idx = (self.state.current - 1) * 2
        if 0 <= idx < len(labels) and labels[idx]:
            say_label(self.state.say_dir, str(labels[idx]))

    def _transition_work_to_break(self) -> None:
        """Work → break: update state, notify. Does NOT start a timer.
        The video keeps playing uninterrupted across work/break cycles."""

        # Idempotency guard: the timer daemon thread and the polybar-driven
        # handle_expired can race and both trigger this transition. Only the
        # first caller wins; the second returns immediately.
        try:
            TRANSITION_LOCK.touch(exist_ok=False)
        except FileExistsError:
            return

        try:
            self._transition_work_to_break_locked()
        finally:
            TRANSITION_LOCK.unlink(missing_ok=True)

    def _transition_work_to_break_locked(self) -> None:
        idx = self.state.current - 1  # 0-based index of the session just completed

        # Look up the break_min for this session from schedule, if present
        if self.state.schedule and idx < len(self.state.schedule):
            self.state.break_min = self.state.schedule[idx][1]

        if self.state.current >= self.state.total:
            # Enter reflection period before finishing
            self.state.phase = "reflect"
            self.state.end_ts = time.time() + REFLECTION_SECS
            self.save_state()
            if self._pause_on_break():
                self._pause_audio()
            WORK_BELL_PLAYED.unlink(missing_ok=True)
            self._notify(
                "🍅 All sessions complete!",
                f'"{self.state.task}" — {self.state.total} session(s) '
                f"of {self.state.work_min}min complete.\n"
                f"🤔 Take a minute to reflect…",
                phase="reflect",
                session=self.state.current - 1,
            )

            # Fire pomodoro_done so indexed commands also run for the final
            # pomodoro. `session` is 1-based here (matching the branch below):
            # the last pomodoro is `current` (== total), not `current - 1`.
            # Using `current - 1` would reuse the previous pomodoro's index and
            # fire commands like `[open_chess, 3]` twice.
            self._cmd_runner.run(
                "pomodoro_done",
                task=self.state.task,
                work_min=self.state.work_min,
                break_min=self.state.break_min,
                session=self.state.current,
                total=self.state.total,
                phase=self.state.phase,
            )

            return

        next_sess = self.state.current + 1
        self.state.phase = "break"
        self.state.end_ts = time.time() + self.state.break_min * 60
        self.state.current = next_sess
        self.save_state()

        # Pause video/audio during breaks for ARC mode, CLIAMP, and
        # INCLUDE_DURATION_FILES
        if self._pause_on_break():
            self._pause_audio()
        WORK_BELL_PLAYED.unlink(missing_ok=True)

        # Announce the break's label (startup presets with say_label)
        self._say_current_label()

        # Fire event AFTER state is saved so commands see the updated phase
        self._cmd_runner.run(
            "pomodoro_done",
            task=self.state.task,
            work_min=self.state.work_min,
            break_min=self.state.break_min,
            session=self.state.current - 1,
            total=self.state.total,
            phase=self.state.phase,
        )

        self._notify(
            "🍅 Session done!",
            f'"{self.state.task}" — {self.state.work_min}min complete.\n'
            f"☕ {self.state.break_min}min break — "
            f"session {next_sess}/{self.state.total} next.",
            phase="pomodoro_done",
            session=self.state.current - 1,
        )

    def _transition_break_to_work(self) -> None:
        """Break → work: update state, notify. Does NOT start a timer.
        The video is already playing from the initial `start()` call."""

        # Idempotency guard: the timer daemon thread and the polybar-driven
        # handle_expired can race and both trigger this transition. Only the
        # first caller wins; the second returns immediately.
        try:
            TRANSITION_LOCK.touch(exist_ok=False)
        except FileExistsError:
            return

        try:
            self._transition_break_to_work_locked()
        finally:
            TRANSITION_LOCK.unlink(missing_ok=True)

    def _transition_break_to_work_locked(self) -> None:
        idx = self.state.current - 1  # 0-based index of the upcoming session

        # Look up work_min for this session from schedule, if present
        if self.state.schedule and idx < len(self.state.schedule):
            self.state.work_min = self.state.schedule[idx][0]

        self.state.phase = "work"
        self.state.end_ts = time.time() + self.state.work_min * 60 + EXTRA_WORK_SECS

        # Switch ARC audio source mid-session if configured
        # Format: [at_pomodoro, path, arc_mode?]
        #   arc_mode=True  → ARC directory (build playlist)
        #   arc_mode=False → regular video file
        # When omitted, infer it from the path (directory → True, file → False).
        if self.state.arc_switches:
            at, target_path = (
                self.state.arc_switches[0][0],
                self.state.arc_switches[0][1],
            )
            target_arc = (
                self.state.arc_switches[0][2]
                if len(self.state.arc_switches[0]) >= 3
                else Path(target_path).is_dir()
            )
            if self.state.current >= at:
                kill_mpv()
                start_mpv(target_path, audio_only=True, arc_mode=target_arc)
                self.state.video = target_path
                self.state.arc_mode = target_arc
                self.state.arc_switches.pop(0)

                # Look up warm-up seconds if switching to a known video
                if not target_arc:
                    video_name = Path(target_path).name
                    for entry in POMODORO_DEFAULTS:
                        if entry[0] == video_name:
                            warm_up = entry[4] if len(entry) >= 5 else 0
                            if warm_up:
                                self.state.warm_up_secs = int(warm_up)
                                self.state.end_ts = (
                                    time.time()
                                    + warm_up
                                    + self.state.work_min * 60
                                    + EXTRA_WORK_SECS
                                )
                            break

        self.save_state()

        # Fire event AFTER state is saved so commands see the updated phase
        self._cmd_runner.run(
            "break_done",
            task=self.state.task,
            work_min=self.state.work_min,
            break_min=self.state.break_min,
            session=self.state.current - 2,
            total=self.state.total,
            phase=self.state.phase,
        )

        # This work phase begins (0-based: current-1)
        self._cmd_runner.run(
            "pomodoro_begin",
            task=self.state.task,
            work_min=self.state.work_min,
            break_min=self.state.break_min,
            total=self.state.total,
            session=self.state.current - 1,
            phase=self.state.phase,
        )

        # Restore volume (ARC fade) and unpause for the next work phase
        if self.state.arc_mode:
            mpv_cmd('{"command": ["set_property", "volume", 100]}')
        if self._pause_on_break():
            self._resume_audio()
        # If the socket was stale (mpv died), restart it (not for CLIAMP mode)
        if not MPV_SOCKET.exists() and STATE_FILE.exists():
            state = PomodoroState.load(STATE_FILE)
            if not state.cliamp_mode:
                start_mpv(
                    state.video,
                    audio_only=state.audio_only,
                    arc_mode=state.arc_mode,
                )
        # Clean up bell flags from the just-ended break
        BELL_30_PLAYED.unlink(missing_ok=True)
        BELL_BEGIN_PLAYED.unlink(missing_ok=True)

        # Announce the new work phase's label (startup presets with say_label)
        self._say_current_label()

        self._notify(
            "🍅 Break over!",
            f"Starting session {self.state.current}/{self.state.total} — "
            f"{self.state.work_min}min focus.",
            phase="break_done",
            session=self.state.current - 2,
        )

    # ── Phase transitions (full: side effects + timer management) ────────────

    def _on_phase_end(self) -> None:
        if not STATE_FILE.exists():
            return  # no active session
        self.state = PomodoroState.load(STATE_FILE)
        if not self.state.is_active:
            return
        self._dispatch_transition()

    def _dispatch_transition(self) -> None:
        """Perform the transition for the current phase and start a timer for the
        new phase.  This is only reliable when the calling process stays alive."""
        if PAUSE_FILE.exists():
            return  # paused – do not advance (polybar-driven handle_expired will)
        if self.state.phase == "work":
            self._transition_work_to_break()
            if STATE_FILE.exists() and self.state.phase == "break":
                self._run_timer(self.state.break_min * 60, self._on_phase_end)
        elif self.state.phase == "break":
            self._transition_break_to_work()
            if STATE_FILE.exists() and self.state.phase == "work":
                self._run_timer(self.state.work_min * 60, self._on_phase_end)
        elif self.state.phase == "reflect":
            self._on_reflect_end()

    def _on_work_end(self) -> None:
        """Called by the timer thread when a work period expires."""
        if not STATE_FILE.exists():
            return
        self.state = PomodoroState.load(STATE_FILE)
        if not self.state.is_active or self.state.phase != "work":
            return
        self._dispatch_transition()

    def _on_break_end(self) -> None:
        """Called by the timer thread when a break period expires."""
        if not STATE_FILE.exists():
            return
        self.state = PomodoroState.load(STATE_FILE)
        if not self.state.is_active or self.state.phase != "break":
            return
        self._dispatch_transition()

    def _on_reflect_end(self) -> None:
        """Called when the reflection period expires — finish the session."""
        if not STATE_FILE.exists():
            return
        self.state = PomodoroState.load(STATE_FILE)
        if not self.state.is_active:
            return

        # Idempotency guard: several callers can race here (daemon timer
        # thread, startup loop, _status_line, polybar poll). Only the first
        # plays the finish sound and cleans up.
        try:
            FINISH_PLAYED.touch(exist_ok=False)
        except FileExistsError:
            return  # another process is already finishing

        play_finish_sound()

        # Capture context before clearing state
        task = self.state.task
        work_min = self.state.work_min
        total = self.state.total

        self._notify(
            "🍅 Time's up!",
            f'"{task}" — {total} session(s) complete!',
            phase="finished",
            session=total - 1,
        )
        if self._on_session_complete:
            self._on_session_complete(task, work_min, total)

        # Clear state BEFORE firing session_complete so commands that start a
        # new session (e.g. "pomodoro random") find a clean state.
        self.clear_state()

        self._cmd_runner.run(
            "session_complete",
            task=task,
            work_min=work_min,
            total=total,
        )

    # ── Expired-phase check (polybar-driven transitions) ─────────────────────

    def handle_expired(self) -> None:
        """Check if the current phase has expired *since the last check* and
        transition if needed.  Safe to call from the polybar status subcommand
        (which runs in a fresh, short-lived process).

        This is the *reliable* transition mechanism.  The daemon timer threads
        are a best-effort optimisation for immediate notifications when the
        original UI process is still alive.
        """
        if not STATE_FILE.exists():
            return
        if PAUSE_FILE.exists():
            return  # paused – do not advance

        state = PomodoroState.load(STATE_FILE)
        if not state.is_active:
            return
        if state.remaining_seconds > 0:
            return  # not yet expired

        self.state = state
        if state.phase == "work":
            self._transition_work_to_break()
        elif state.phase == "reflect":
            self._on_reflect_end()
        else:
            self._transition_break_to_work()
