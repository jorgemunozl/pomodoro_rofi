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
from datetime import datetime
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
EventCommands = dict[str, list[CommandEntry]]


class CommandsBuilder:
    """Fluent builder for EVENT_COMMANDS / preset commands.

    Usage::

        cmds = CommandsBuilder()
        cmds.on("pomodoro_done").always("echo every time")
        cmds.on("pomodoro_done").at(0).run("echo first")
        cmds.on("pomodoro_done").every(2).run("mpv push_ups.mp3")
        cmds.on("session_start").once().run("echo start")
        EVENT_COMMANDS = cmds.build()
    """

    def __init__(self) -> None:
        self._commands: dict[str, list[CommandEntry]] = {}

    def on(self, event: str) -> "_PhaseConfig":
        """Start configuring commands for *event*."""
        return _PhaseConfig(self._commands, event)

    def build(self) -> EventCommands:
        """Return the built command map."""
        return dict(self._commands)


class _PhaseConfig:
    """Fluent config for a single phase's commands."""

    def __init__(self, parent: dict[str, list[CommandEntry]], event: str) -> None:
        self._parent = parent
        self._event = event

    def always(self, cmd: str) -> "_PhaseConfig":
        """Add a command that fires every time."""
        self._parent.setdefault(self._event, []).append(cmd)
        return self

    def at(self, index: int) -> "_FilteredCommand":
        """Add a command that fires only at a specific session index."""
        return _FilteredCommand(self._parent, self._event, index)

    def every(self, interval: int) -> "_FilteredCommand":
        """Add a command that fires every N sessions."""
        return _FilteredCommand(self._parent, self._event, f"every:{interval}")

    def once(self) -> "_FilteredCommand":
        """Add a command that fires on the first session only (index 0)."""
        return _FilteredCommand(self._parent, self._event, 0)


class _FilteredCommand:
    """A command with a session filter, finalized by .run()."""

    def __init__(
        self, parent: dict[str, list[CommandEntry]], event: str, filter_: int | str
    ) -> None:
        self._parent = parent
        self._event = event
        self._filter = filter_

    def run(self, cmd: str) -> None:
        """Register the command with this filter."""
        self._parent.setdefault(self._event, []).append([cmd, self._filter])


class CommandRunner:
    """Runs shell commands when pomodoro lifecycle events occur.

    See module docstring for the entry format.
    """

    def __init__(
        self,
        commands: EventCommands | None = None,
        log_path: Path | None = None,
    ) -> None:
        self._commands: EventCommands = commands or {}
        self._log_path = log_path

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, event: str, **context: object) -> None:
        """Execute every command registered for *event*, substituting *context*.

        Silently ignores unknown events (no-op).
        """
        entries = self._commands.get(event)
        if not entries:
            return
        # DEBUG: dump all entries being processed so we can see the merged list
        if self._log_path:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(self._log_path, "a") as f:
                f.write(f"[{ts}] ═══ {event} — {len(entries)} entry(s) ═══\n")
                for i, e in enumerate(entries):
                    label = e if isinstance(e, str) else e[0][:80]
                    f.write(f"[{ts}]   [{i}] {label}\n")
        for entry in entries:
            try:
                self._execute(entry, context)
            except Exception:
                # Never let one failing command break the rest of the chain.
                logging.warning(
                    "CommandRunner: error executing entry for event %r", event,
                    exc_info=True,
                )

    # ── Config access ──────────────────────────────────────────────────────────

    @property
    def events(self) -> set[str]:
        """Return the set of events this runner has commands for."""
        return set(self._commands.keys())

    def has_commands(self, event: str) -> bool:
        """Return True if *event* has at least one registered command."""
        return bool(self._commands.get(event))

    @classmethod
    def merge(
        cls,
        *sources: EventCommands | None,
        log_path: Path | None = None,
    ) -> "CommandRunner":
        """Create a runner that chains commands from multiple dicts.

        Later sources are appended after earlier ones, so multiple
        commands can fire for the same event.
        """
        merged: EventCommands = {}
        for src in sources:
            if not src:
                continue
            for event, entries in src.items():
                merged.setdefault(event, []).extend(
                    e for e in entries if e not in merged.get(event, [])
                )
        return cls(merged, log_path=log_path)

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
                self._log_skip(f"malformed entry: {entry!r}")
                return

            session = context.get("session")
            if not isinstance(session, int):
                self._log_skip(
                    f"no session context (session={session!r}) for: {cmd_str}"
                )
                return

            if isinstance(target, int):
                if session != target:
                    self._log_skip(
                        f"session={session} ≠ target={target}: {cmd_str}"
                    )
                    return
            elif isinstance(target, str) and target.startswith("every:"):
                try:
                    interval = int(target.split(":", 1)[1])
                except (ValueError, IndexError):
                    self._log_skip(f"bad every filter: {target!r}")
                    return
                if interval < 1 or session % interval != 0:
                    self._log_skip(
                        f"every:{interval} skip session={session}: {cmd_str}"
                    )
                    return
            else:
                self._log_skip(f"unknown filter: {target!r}")
                return
        else:
            cmd_str = str(entry)

        if not cmd_str.strip():
            return

        cmd = self._format(cmd_str, context)

        if self._log_path:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            short = cmd_str.replace("\n", " ")

            # Write header synchronously with regular file I/O (proven reliable).
            with open(self._log_path, "a") as f:
                f.write(f"[{ts}] ▶ {short}\n")

            # Run command directly — no stdout capture, no fd tricks.
            # Commands launch GUI apps, mpv, etc. — they just need to run.
            try:
                subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as exc:
                logging.warning("CommandRunner: failed to run %r — %s", cmd, exc)
        else:
            try:
                subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as exc:
                logging.warning("CommandRunner: failed to run %r — %s", cmd, exc)

    def _log_skip(self, reason: str) -> None:
        """Write a skip notice to the log so the user can see what was filtered."""
        if not self._log_path:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(self._log_path, "a") as f:
            f.write(f"[{ts}] ⏭ SKIP — {reason}\n")
