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

* A **list ``[command, "every:N"]``** — fires **every N sessions** (at
  ``session`` 0, N, 2N, …). Ideal for recurring breaks like push-ups.

  .. code:: python

      "pomodoro_done": [
          ["echo '💪 Push ups!' >> /tmp/log", "every:2"],  # every 2 pomos
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
EVENT_POMODORO_BEGIN = "pomodoro_begin"  # Each work phase begins
EVENT_POMODORO_DONE = "pomodoro_done"  # Work → break transition
EVENT_BREAK_DONE = "break_done"  # Break → work transition
EVENT_SESSION_COMPLETE = "session_complete"  # All pomodoros finished (reflect done)
EVENT_BELL_30 = "bell_30"  # 30 seconds remaining in work
EVENT_BELL_BEGIN = "bell_begin"  # 3 seconds remaining in work
EVENT_BELL_END = "bell_end"  # Work period fully ended

# ── Types ──────────────────────────────────────────────────────────────────────
# A command entry is either:
#   - str             → fire always
#   - [str, int]      → fire when session == index
#   - [str, "every:N"] → fire when session % N == 0

CommandEntry = str | list  # [cmd_str, session_filter]
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
        # Unpack: plain string → always run,  [str, int|str] → filtered
        if isinstance(entry, list):
            try:
                cmd_str, target = entry[0], entry[1]
            except (IndexError, TypeError):
                return  # malformed entry, skip

            session = context.get("session")
            if not isinstance(session, int):
                return  # no session context, skip all filtered

            if isinstance(target, int):
                # Exact index: fire only when session == target
                if session != target:
                    return
            elif isinstance(target, str) and target.startswith("every:"):
                # Interval: fire when session % N == 0
                try:
                    interval = int(target.split(":", 1)[1])
                except (ValueError, IndexError):
                    return
                if interval < 1 or session % interval != 0:
                    return
            else:
                return  # unknown filter type, skip
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
