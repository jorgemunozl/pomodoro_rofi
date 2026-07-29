"""Command runner — trigger shell commands on pomodoro lifecycle events.

Usage
-----
    runner = CommandRunner(EVENT_COMMANDS)
    runner.run(EVENT_POMODORO_DONE, task="read", work_min=25, session=0, total=4)

Each event maps to a **list of entries**.  An entry is either:

* A plain **string** — fires **every time** the event occurs.

  .. code:: python

      "pomodoro_done": [
          "notify-send '🍅 Pomodoro {session}/{total} done!'",
      ],

* A **list ``[command, index]``** — fires **only when ``session`` equals *index***
  (0-based, so ``0`` = first pomodoro, ``1`` = second, …).

  .. code:: python

      "pomodoro_done": [
          "notify-send '🍅 Another one!'",           # every time
          ["echo 'first!' >> /tmp/pomo.log", 0],     # only session 0
          ["notify-send '⚡ Halfway!'", 2],           # only session 2
      ],

Indexed entries are ignored if the event doesn't provide a ``session``
context variable.
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

# ── Types ──────────────────────────────────────────────────────────────────────
# A command entry is either a plain string (fire always) or [str, int] (fire only
# when session context matches the index).

CommandEntry = str | list  # [cmd_str, session_index]
CommandMap = dict[str, list[CommandEntry]]


class CommandRunner:
    """Runs shell commands when pomodoro lifecycle events occur.

    See module docstring for the entry format.
    """

    def __init__(self, commands: CommandMap | None = None) -> None:
        self._commands: CommandMap = commands or {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, event: str, **context: object) -> None:
        """Execute every command registered for *event*, substituting *context*.

        Silently ignores unknown events (no-op).
        """
        entries = self._commands.get(event)
        if not entries:
            return
        for entry in entries:
            self._execute(entry, context)

    # ── Config access ──────────────────────────────────────────────────────────

    @property
    def events(self) -> set[str]:
        """Return the set of events this runner has commands for."""
        return set(self._commands.keys())

    def has_commands(self, event: str) -> bool:
        """Return True if *event* has at least one registered command."""
        return bool(self._commands.get(event))

    @classmethod
    def merge(cls, *sources: CommandMap | None) -> "CommandRunner":
        """Create a runner that chains commands from multiple dicts.

        Later sources are appended after earlier ones, so multiple
        commands can fire for the same event.
        """
        merged: CommandMap = {}
        for src in sources:
            if not src:
                continue
            for event, entries in src.items():
                merged.setdefault(event, []).extend(
                    e for e in entries if e not in merged.get(event, [])
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

    def _execute(self, entry: CommandEntry, context: dict[str, object]) -> None:
        """Run a single command entry, respecting session-index filtering."""
        # Unpack: plain string → always run,  [str, int] → match session index
        if isinstance(entry, list):
            try:
                cmd_str, target_idx = entry[0], entry[1]
            except (IndexError, TypeError):
                return  # malformed entry, skip
            if not isinstance(target_idx, int):
                return  # not an indexed command, skip
            session = context.get("session")
            if not isinstance(session, int) or session != target_idx:
                return  # session doesn't match → skip
        else:
            cmd_str = str(entry)

        if not cmd_str.strip():
            return

        cmd = self._format(cmd_str, context)
        try:
            subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logging.warning("CommandRunner: failed to run %r — %s", cmd, exc)
