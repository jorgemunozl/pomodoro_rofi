"""Timer controller — background work/break cycles, mpv, notifications."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from pomodoro_lib.config import (
    ARC_SILENCE_SECONDS,
    ARC_SOUNDTRACK,
    BELL_30_FILE,
    BELL_30_PLAYED,
    BELL_BEGIN_FILE,
    BELL_BEGIN_PLAYED,
    FINISH_FILE,
    MPV_SOCKET,
    PAUSE_FILE,
    PID_FILE,
    REFLECTION_SECS,
    STATE_FILE,
)
from pomodoro_lib.state import PomodoroState


def ensure_silence_mp3(silence_secs: int = ARC_SILENCE_SECONDS) -> Path:
    """Generate or return cached silence mp3."""
    path = Path(f"/tmp/{silence_secs}s-silence.mp3")
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


# ── External tool helpers ─────────────────────────────────────────────────────


def notify(summary: str, body: str = "", urgency: str = "normal") -> None:
    subprocess.run(
        ["dunstify", "-u", "critical", summary, body],
        capture_output=True,
    )


def i3_workspace() -> None:
    subprocess.run(
        ["i3-msg", "workspace --no-auto-back-and-forth 🍅"],
        capture_output=True,
    )


def mpv_cmd(json_cmd: str) -> None:
    """Send a command to the MPV IPC socket."""
    if MPV_SOCKET.exists():
        subprocess.run(
            ["socat", "-", str(MPV_SOCKET)],
            input=json_cmd,
            capture_output=True,
            text=True,
        )


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
                "x11-name=no_reg",
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
    """Kill the mpv process and clean up."""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError, FileNotFoundError):
            pass
    PID_FILE.unlink(missing_ok=True)
    MPV_SOCKET.unlink(missing_ok=True)


# ── TimerController ───────────────────────────────────────────────────────────


class TimerController:
    """Manages background timer thread for work/break cycles."""

    def __init__(
        self, on_session_complete: Callable[[str, int, int], None] | None = None
    ):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = PomodoroState()
        self._on_session_complete = on_session_complete

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
            self._thread.join(timeout=1.0)
        self._stop_event.clear()
        self._thread = None
        kill_mpv()
        STATE_FILE.unlink(missing_ok=True)
        PAUSE_FILE.unlink(missing_ok=True)
        BELL_30_PLAYED.unlink(missing_ok=True)
        BELL_BEGIN_PLAYED.unlink(missing_ok=True)
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
        silence_secs: int = ARC_SILENCE_SECONDS,
    ) -> None:
        self.stop()
        total_first_secs = warm_up_secs + work_min * 60
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
        )
        self.save_state()
        start_mpv(video, audio_only, arc_mode, silence_secs)
        warmup_note = f"🔥 {warm_up_secs}s warm-up, then " if warm_up_secs else ""
        notify(
            "🍅 Pomodoro started",
            f"{task} — session 1/{total}\n"
            f"{warmup_note}{work_min}min focus — "
            f"{time.strftime('%H:%M', time.localtime(self.state.end_ts))}",
        )

        # Defensive clear to prevent race conditions
        self._stop_event.clear()
        self._run_timer(total_first_secs, self._on_work_end)

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
        self._stop_event.set()
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=1.0)
        self._stop_event.clear()
        self._thread = None
        # Pause mpv (video plays continuously across all phases)
        mpv_cmd('{"command": ["set_property", "pause", true]}\n')
        notify("🍅 Pomodoro paused", f"{secs_left // 60}m left")

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
        self.state = PomodoroState.load(STATE_FILE)
        self.state.end_ts = time.time() + secs_left
        self.save_state()

        # Unpause mpv (video was paused, never killed)
        if MPV_SOCKET.exists():
            mpv_cmd('{"command": ["set_property", "pause", false]}\n')

        notify(
            "🍅 Pomodoro resumed",
            f"{secs_left // 60}m left — "
            f"{time.strftime('%H:%M', time.localtime(self.state.end_ts))}",
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
        work_total = state.work_min * 60

        if PAUSE_FILE.exists():
            raw = int(PAUSE_FILE.read_text().strip())
            if state.phase == "work" and raw > work_total:
                # Paused during warm-up
                secs = raw - work_total
                icon = "⏸"
            else:
                secs = raw
                icon = "⏸"
        elif state.phase == "break":
            secs = state.remaining_seconds
            icon = "🏹" if state.arc_mode else "☕"
        elif state.phase == "reflect":
            secs = state.remaining_seconds
            icon = "🤔"
        else:
            raw = state.remaining_seconds
            if raw > work_total:
                # Still in warm-up
                secs = raw - work_total
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
                label = (
                    state.schedule_labels[label_idx]
                    if label_idx < len(state.schedule_labels)
                    else ""
                )
            else:
                label_idx = (state.current - 1) * 2
                label = (
                    state.schedule_labels[label_idx]
                    if label_idx < len(state.schedule_labels)
                    else ""
                )
            return f"{icon} {mins:02d}:{secs_rem:02d}  {label}"
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

    def _transition_work_to_break(self) -> None:
        """Work → break: update state, notify. Does NOT start a timer.
        The video keeps playing uninterrupted across work/break cycles."""

        idx = self.state.current - 1  # 0-based index of the session just completed

        # Look up the break_min for this session from schedule, if present
        if self.state.schedule and idx < len(self.state.schedule):
            self.state.break_min = self.state.schedule[idx][1]

        if self.state.current >= self.state.total:
            # Enter reflection period before finishing
            self.state.phase = "reflect"
            self.state.end_ts = time.time() + REFLECTION_SECS
            self.save_state()
            mpv_cmd('{"command": ["set_property", "pause", true]}\n')
            notify(
                "🍅 All sessions complete!",
                f'"{self.state.task}" — {self.state.total} session(s) '
                f"of {self.state.work_min}min complete.\n"
                f"🤔 Take a minute to reflect…",
                urgency="critical",
            )
            return

        next_sess = self.state.current + 1
        self.state.phase = "break"
        self.state.end_ts = time.time() + self.state.break_min * 60
        self.state.current = next_sess
        self.save_state()

        # Pause video/audio during breaks for full silence
        mpv_cmd('{"command": ["set_property", "pause", true]}\n')

        notify(
            "🍅 Session done!",
            f'"{self.state.task}" — {self.state.work_min}min complete.\n'
            f"☕ {self.state.break_min}min break — "
            f"session {next_sess}/{self.state.total} next.",
            urgency="critical",
        )

    def _transition_break_to_work(self) -> None:
        """Break → work: update state, notify. Does NOT start a timer.
        The video is already playing from the initial `start()` call."""

        idx = self.state.current - 1  # 0-based index of the upcoming session

        # Look up work_min for this session from schedule, if present
        if self.state.schedule and idx < len(self.state.schedule):
            self.state.work_min = self.state.schedule[idx][0]

        self.state.phase = "work"
        self.state.end_ts = time.time() + self.state.work_min * 60
        self.save_state()

        # Restore volume (ARC fade) and unpause for the next work phase
        if self.state.arc_mode:
            mpv_cmd('{"command": ["set_property", "volume", 100]}\n')
        mpv_cmd('{"command": ["set_property", "pause", false]}\n')
        # Clean up bell flags from the just-ended break
        BELL_30_PLAYED.unlink(missing_ok=True)
        BELL_BEGIN_PLAYED.unlink(missing_ok=True)

        notify(
            "🍅 Break over!",
            f"Starting session {self.state.current}/{self.state.total} — "
            f"{self.state.work_min}min focus.",
            urgency="critical",
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
        play_finish_sound()
        notify(
            "🍅 Time's up!",
            f'"{self.state.task}" — {self.state.total} session(s) complete!',
            urgency="critical",
        )
        if self._on_session_complete:
            self._on_session_complete(
                self.state.task, self.state.work_min, self.state.total
            )
        self.clear_state()

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
