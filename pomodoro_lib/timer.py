"""Timer controller — background work/break cycles, mpv, notifications."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from pomodoro_lib.config import MPV_SOCKET, PAUSE_FILE, PID_FILE, STATE_FILE
from pomodoro_lib.state import PomodoroState

# ── External tool helpers ─────────────────────────────────────────────────────


def notify(summary: str, body: str = "", urgency: str = "normal") -> None:
    subprocess.run(
        ["dunstify", "-u", urgency, "-i", "timer", summary, body],
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


def start_mpv(video: str) -> None:
    """Launch mpv with the given video file."""
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
        self.state = PomodoroState()

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(
        self, task: str, video: str, work_min: int, break_min: int, total: int
    ) -> None:
        self.stop()
        self.state = PomodoroState(
            task=task,
            end_ts=time.time() + work_min * 60,
            work_min=work_min,
            break_min=break_min,
            total=total,
            current=1,
            video=video,
            phase="work",
        )
        self.save_state()
        start_mpv(video)
        notify(
            "🍅 Pomodoro started",
            f"{task} — session 1/{total}\n{work_min}min — "
            f"{time.strftime('%H:%M', time.localtime(self.state.end_ts))}",
        )

        # Defensive clear to prevent race conditions
        self._stop_event.clear()
        self._run_timer(work_min * 60, self._on_work_end)

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
        # Pause mpv during work phase, kill during break
        if state.phase == "work":
            mpv_cmd('{"command": ["set_property", "pause", true]}\n')
        else:
            kill_mpv()
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

        # Resume/restart mpv based on phase
        if self.state.phase == "work":
            if MPV_SOCKET.exists():
                mpv_cmd('{"command": ["set_property", "pause", false]}\n')
            else:
                start_mpv(self.state.video)

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

        if PAUSE_FILE.exists():
            secs = int(PAUSE_FILE.read_text().strip())
            icon = "⏸"
        elif state.phase == "break":
            secs = state.remaining_seconds
            icon = "☕"
        else:
            secs = state.remaining_seconds
            icon = "▶"

        mins = secs // 60
        secs_rem = secs % 60
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

    # ── Phase transitions ─────────────────────────────────────────────────────
    def _on_phase_end(self) -> None:
        if not STATE_FILE.exists():
            return  # no active session
        self.state = PomodoroState.load(STATE_FILE)
        if not self.state.is_active:
            return
        if self.state.phase == "work":
            self._on_work_end()
        else:
            self._on_break_end()

    def _on_work_end(self) -> None:
        # Kill mpv when work session ends
        kill_mpv()

        if self.state.current >= self.state.total:
            notify(
                "🍅 All done!",
                f'"{self.state.task}" — {self.state.total} session(s) '
                f"of {self.state.work_min}min complete!",
                urgency="critical",
            )
            if self._on_session_complete:
                self._on_session_complete(
                    self.state.task, self.state.work_min, self.state.total
                )
            self.clear_state()
            return

        next_sess = self.state.current + 1
        self.state.phase = "break"
        self.state.end_ts = time.time() + self.state.break_min * 60
        self.state.current = next_sess
        self.save_state()

        notify(
            "🍅 Session done!",
            f'"{self.state.task}" — {self.state.work_min}min complete.\n'
            f"☕ {self.state.break_min}min break — "
            f"session {next_sess}/{self.state.total} next.",
            urgency="critical",
        )

        self._run_timer(self.state.break_min * 60, self._on_phase_end)

    def _on_break_end(self) -> None:
        self.state.phase = "work"
        self.state.end_ts = time.time() + self.state.work_min * 60
        self.save_state()
        start_mpv(self.state.video)

        notify(
            "🍅 Break over!",
            f"Starting session {self.state.current}/{self.state.total} — "
            f"{self.state.work_min}min focus.",
            urgency="critical",
        )

        self._run_timer(self.state.work_min * 60, self._on_phase_end)
