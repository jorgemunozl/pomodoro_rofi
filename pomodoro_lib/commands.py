"""Command runner — trigger shell commands on pomodoro lifecycle events.

Usage
-----
    runner = CommandRunner(EVENT_COMMANDS)
    runner.run(EVENT_POMODORO_DONE, task="read", work_min=25, session=1, total=4)
"""

import logging
import subprocess
from pathlib import Path

# ── Event names ────────────────────────────────────────────────────────────────
# These are the canonical event names. Users reference them in EVENT_COMMANDS.

EVENT_SESSION_START = "session_start"  # A new work session begins
EVENT_POMODORO_DONE = "pomodoro_done"  # Work → break transition
EVENT_BREAK_DONE = "break_done"  # Break → work transition
EVENT_SESSION_COMPLETE = "session_complete"  # All pomodoros finished (reflect done)
EVENT_BELL_30 = "bell_30"  # 30 seconds remaining in work
EVENT_BELL_BEGIN = "bell_begin"  # 3 seconds remaining in work
EVENT_BELL_END = "bell_end"  # Work period fully ended


class CommandRunner:
    """Runs shell commands when pomodoro lifecycle events occur.

    The event→commands mapping is provided as a dict::

        {
            EVENT_POMODORO_DONE: [
                "notify-send '🍅 Pomodoro {session}/{total} done!'",
            ],
            EVENT_SESSION_COMPLETE: [
                "mpv --no-terminal --no-video ~/sounds/cheer.mp3",
            ],
        }

    Commands support ``{variable}`` substitution with context keys passed
    to :meth:`run` (e.g. ``task``, ``work_min``, ``session``, ``total`` …).
    """

    def __init__(self, commands: dict[str, list[str]] | None = None) -> None:
        self._commands: dict[str, list[str]] = commands or {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, event: str, **context: object) -> None:
        """Execute every command registered for *event*, substituting *context*.

        Silently ignores unknown events (no-op).
        """
        cmds = self._commands.get(event)
        if not cmds:
            return
        for raw_cmd in cmds:
            self._execute(raw_cmd, context)

    # ── Config access ──────────────────────────────────────────────────────────

    @property
    def events(self) -> set[str]:
        """Return the set of events this runner has commands for."""
        return set(self._commands.keys())

    def has_commands(self, event: str) -> bool:
        """Return True if *event* has at least one registered command."""
        return bool(self._commands.get(event))

    @classmethod
    def merge(cls, *sources: dict[str, list[str]] | None) -> "CommandRunner":
        """Create a runner that chains commands from multiple dicts.

        Later sources override (are appended after) earlier ones, so
        multiple commands can fire for the same event.
        """
        merged: dict[str, list[str]] = {}
        for src in sources:
            if not src:
                continue
            for event, cmds in src.items():
                merged.setdefault(event, []).extend(
                    cmd for cmd in cmds if cmd not in merged.get(event, [])
                )
        return cls(merged)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _format(self, raw: str, context: dict[str, object]) -> str:
        """Substitute ``{key}`` placeholders with values from *context*.

        Missing keys are left as-is (including the braces) so the user
        can see what wasn't resolved.
        """
        try:
            return raw.format(**context)
        except KeyError:
            return raw  # leave unfilled placeholders as-is

    def _execute(self, raw_cmd: str, context: dict[str, object]) -> None:
        """Run a single formatted command in a subprocess (fire & forget)."""
        cmd = self._format(raw_cmd, context)
        if not cmd.strip():
            return
        try:
            subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logging.warning("CommandRunner: failed to run %r — %s", cmd, exc)
