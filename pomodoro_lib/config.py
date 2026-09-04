"""Presets, chains, and event commands for the pomodoro timer.

Static constants (paths, commands, defaults) live in constants.py;
this module only holds session-level configuration.
"""

from cProfile import label
from dataclasses import dataclass
from tracemalloc import start

from pomodoro_lib.commands import CommandsBuilder
from pomodoro_lib.constants import (
    ARC_CLEANING,
    ARC_SILENCE_SECONDS,
    ARC_SOUNDTRACK,
    ARC_SOUNDTRACKS_PAST,
    ARC_STARTUP,
    POMO_DIR,
    PUSH_UPS_FILE,
    SOUNDS_DIR,
    calendly,
    cleaning,
    even_day_label,
    even_day_social,
    even_day_social_label,
    even_day_zk,
    journal,
    nets,
    odd_day_label,
    odd_day_zk,
    open_chess,
    open_dawn,
    open_shinjuku_2,
    open_tired,
    open_zed,
    open_zk,
    shutdown_command,
)


@dataclass
class StartupPreset:
    """A pre-configured startup pomodoro session."""

    schedule: list  # [[work_min, break_min], ...]  — last break is ignored
    labels: list  # per-phase polybar labels (shorter than schedule → fallback)
    switches: list  # [[at_pomodoro, path, arc_mode?], ...]
    start_dir: str  # initial ARC directory or video path
    silence_secs: int  # silence between ARC tracks
    description: str  # one-line summary for the terminal
    commands: dict[str, list] | None = (
        None  # per-preset event commands (str or [cmd, idx])
    )
    notify_color: str = "default"  # see NOTIFY_COLORS for available names
    notify_title: str = ""  # dunst summary template, "{summary}" substituted
    notify_desc: str = ""  # dunst body template, "{body}" substituted
    notify_timeout: int = 0  # milliseconds (0 = dunst default)
    notify_phases: dict | None = (
        None  # per-phase overrides: {"phase": {"title": ..., "desc": ..., "timeout": ...}}
    )
    say_label: bool = False  # announce each phase's label via gtts (cached mp3s)


@dataclass
class Chain:
    """A sequence of pomodoro sessions that run back-to-back.

    Each step is either:

    * A **video filename** — e.g. ``"study.mp4"``. Runs that video using its
      default rhythm from POMODORO_DEFAULTS (fallback 25-5 × 1). The task name
      is derived from the video stem.
    * A **preset name** — e.g. ``"morning"``. Runs a full STARTUP_PRESETS entry
      with its own schedule, labels, and commands.
    * A **``(task, item)`` tuple** — same as the two above, but with a custom
      task name, e.g. ``("deep work", "brain_fm.mp4")``.
    * A **list of steps** — e.g. ``["dawn_2025_II.mp4", "brain_fm.mp4"]``.
      The element is chosen by day of month: ``day % len(list)`` selects the
      index (a day that is a multiple of the length → first element, +1 →
      second, …). Each element may itself be a video/preset name or a
      ``(task, item)`` tuple. The tuple form also accepts a list as *item*,
      e.g. ``("deep work", ["a.mp4", "b.mp4"])``, to cycle a fixed task
      between videos by day.

    Example::

        Chain(
            steps=["dawn_2025_II.mp4", ["a.mp4", "b.mp4"], "morning"],
            description="dawn → day-cycled study → morning preset",
        )
    """

    steps: list
    description: str = ""


# ── Pomodoro chains ──────────────────────────────────────────────────────
# Run with:  pomodoro <chain_name>

CHAINS: dict[str, Chain] = {
    "morning": Chain(
        steps=[
            "morning_wake_up",
            ["dawn_2025_II.mp4", "golden_morning.webm", "past_arc"],
        ],
        description="morning default",
    ),
    "cleaning_full": Chain(
        steps=["cleaning", "mine_2025_II.webm"],
        description="if you make this chain the house cleaning by itself",
    ),
    "noon": Chain(
        steps=["noon_after_eat", ["shinjuku2.mp4", "study.mp4", "mine_2025_II.webm"]],
        description="covering the second peak of work",
    ),
}


# ── Event-driven commands ────────────────────────────────────────────────────
# Each event maps to a list of entries.  An entry is either:
#
#   * A plain **string** — fires every time the event occurs.
#   * A **list [command, index]** — fires only when `session` equals *index*
#     (0-based: 0 = first pomodoro, 1 = second, …).
#   * A **list [command, "every:N"]** — fires every N sessions
#     (at session 0, N, 2N, …).  Ideal for recurring breaks like push-ups.
#
# Available events (from pomodoro_lib.commands):
#   session_start, pomodoro_begin, pomodoro_done, break_done, session_complete
#   bell_30, bell_begin, bell_end
#
# Context variables available for {variable} substitution:
#   task, work_min, break_min, session, total, phase, video
#
# Example:
#   EVENT_COMMANDS = {
#       "pomodoro_done": [
#           'notify-send "Pomodoro {session}/{total} done!"',
#           ["echo 'first pomodoro!' >> /tmp/pomo.log", 0],  # session 0 only
#           ["notify-send '⚡ Halfway!'", 2],                 # session 2 only
#           ["echo '💪 Push ups!' >> /tmp/pomo.log", "every:2"],  # every 2
#       ],
#       "break_done": [
#           ["notify-send '☕ Break after first pomo'", 0],   # break after session 0
#       ],
#       "session_complete": [
#           'mpv --no-terminal --no-video ~/sounds/cheer.mp3',
#       ],
#   }

# ── Flags ─────────────────────────────────────────────────────────────────────
# Toggle these to enable/disable common behaviours without editing every preset.

ANNOUNCE_TIME_ON_DONE: bool = False
"""When True, speaks the current time via gtts-cli after every pomodoro.

This is injected into the global EVENT_COMMANDS under ``pomodoro_done``,
so it fires for ALL sessions and presets. Set to ``False`` to disable.
"""


# ── Build EVENT_COMMANDS ──────────────────────────────────────────────────────
# Uses CommandsBuilder for a clean declarative API.

_SAY_TIME = (
    f'F="{SOUNDS_DIR}/say_time_$(date +%I_%M_%p).mp3"; '
    '[ -f "$F" ] || gtts-cli "The time is $(date \'+%I:%M %p\')" --output "$F"; '
    'mpv "$F" --volume=130 --no-terminal'
)
_PUSH_UPS_CMD = f"mpv {PUSH_UPS_FILE} --volume=130 --no-terminal"

cmds = CommandsBuilder()

if ANNOUNCE_TIME_ON_DONE:
    cmds.on("session_start").always(_PUSH_UPS_CMD)
    cmds.on("pomodoro_done").every(2).run(_PUSH_UPS_CMD)

# Push-ups: at session start + every 2 pomodoros
cmds.on("pomodoro_done").always(_SAY_TIME)
cmds.on("session_start").once().run(_SAY_TIME)

EVENT_COMMANDS = cmds.build()


STARTUP_PRESETS: dict[str, StartupPreset] = {
    "night_outside": StartupPreset(
        schedule=[
            [10, 10],  # 20 pomodoro
            [14, 6],  # 20 pomodoro
            [12, 8],  # 20 pomodoro
        ],  # total 60 min
        labels=[
            "leaving uni, going for eat",  # 10 min
            "eating, thinking on following tasks",  # 10 min
            # After 20 min for the eating time phone use
            "journaling",  # 14 min
            "reflect",  # 6 min
            "chess",  # 12 min
            "walk to home quickly",  # 8 min
            # After 40 min reach home 9 pm
        ],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=30,
        description="Preset for 8.00 to 9.30, a light short version of night",
    ),
    "night_blitz": StartupPreset(
        schedule=[
            [
                5,
            ],  # 5 pomodoro
            [
                14,
            ],  # 14 pomodoro
            [
                12,
            ],  # 12 pomodoro
        ],  # total 30 min
        labels=[
            "set up",  # 10 min
            "eating, thinking on following tasks",  # 10 min
            # After 20 min for the eating time phone use
            "going home time/journaling",  # 14 min
            "going home time/reflect",  # 6 min
            "going home time/chess",  # 12 min
            "going home time/walk to home",  # 8 min
            # After 40 min reach home 9 pm
        ],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=30,
        description="",
    ),
    "night": StartupPreset(
        schedule=[
            [7, 7],  # 14 journal
            [6, 0],  # 6 reflect
            [40, 1],  # 41 tasks
            [15, 1],  # 16 applications
            [7, 1],  # 8 budget
            [12, 6],  # 18 chess and metrics
            [9, 8],  # 17 review arc, write core task for tomorrow
            [4, 2],  # 6 tidy around,
            [2, 2],  # 4 pray at bed
        ],  # 130
        labels=[
            "journal/day",  # 7 min
            "journal/work",  # 7 min
            "reflect two notes",  # 6 min
            "gap",  # 0
            "personal tasks",  # 40 min
            "prepare applications",  # 1
            "applications",  # 10 min
            "prepare budget",  # 1 min
            "budget",  # 5 min
            "prepare chess",  # 1 min
            "chess",  # 12 min
            "log metrics/write night task for tomorrow and save them",  # 6 min
            "review arc",  # 9 min
            "write core task for tomorrow",  # 8 min
            "prepare room to go to bed/tidy around/prepare wake up",  # 4 min
            "go bed",  # 2 min, auto turn off in 10 min
            "pray at bed",  # 2
            "plan thinking tomorrow",  # 2
        ],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_SILENCE_SECONDS,
        description="night when at home, begin programatically at 7:30 pm finish at 9:30, thus wake up at 5:00",
        commands={
            "session_complete": [f"sleep 60; {shutdown_command}"],
            "session_start": [journal],
            "pomodoro_done": [
                [open_chess, 4],
            ],
        },
        notify_color="blue",
    ),
    "noon_after_eat": StartupPreset(
        schedule=[
            [5, 1],  # 6
            [17, 4],  # 21
            [16, 4],  # 20
            [13, 0],  # 12
        ],
        labels=[
            "pray meditation",  # 3
            "set-up for personal matter reading",  # 3
            "personal matter reading",  # 17
            "first break, next code/polymath session",  # 4
            "code/polymath first session",  # 17
            "second, preparation for the afternoon",  # 4
            "code/polymath second session to begin the afternoon",  # 17
            "",
        ],
        switches=[],
        start_dir=str(ARC_SOUNDTRACKS_PAST),
        silence_secs=ARC_SILENCE_SECONDS,
        description="noon, 12:40 until 1:40 then around 4:30 meaning ends 6:10",
        notify_color="blue",
        commands={
            "session_start": [
                open_zed
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [open_zk, 1],  # after 3rd pomodoro
            ],
            "session_complete": [
                f"sleep 60 ;{open_tired}",
            ],
        },
    ),
    "morning_ready": StartupPreset(
        schedule=[
            [18, 2],  # 20
            [18, 2],  # 20
            [18, 2],  # 20
        ],  # total 60 min
        labels=[
            "first",
            "break",
            "second",
            "break",
            "third",
        ],
        switches=[],
        commands={
            "session_start": [
                open_zk
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [nets, 2],  # after 3rd pomodoro
            ],
        },
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_SILENCE_SECONDS,
        description="one hour morning",
    ),
    "morning_wake_up": StartupPreset(
        schedule=[
            [4, 3],  # 7
            [21, 5],  # 27
            [21, 5],  # 26
        ],  # total 60 min
        labels=[
            "pray",  # 4
            "prepare myself for the morning",  # 3
            "polymath first session",  # 22
            "nets break",  # 5
            "polymath second session, morning warm up",  # 21
            "schedule the morning",  # 4
        ],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_SILENCE_SECONDS,
        description="morning winter ritual",
        notify_color="yellow",
        commands={
            "session_start": [
                open_zk
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [nets, 2],  # after 3rd pomodoro
            ],
        },
    ),
    "afternoon_problem_solving": StartupPreset(
        schedule=[[29, 1], [29, 1]],
        labels=["problem solving", "review", "problem solving", "review"],
        switches=[],
        start_dir=str(ARC_SOUNDTRACKS_PAST),
        silence_secs=ARC_SILENCE_SECONDS,
        description="afternoon of problem solving from four to six, once each two days I think that is proper",
    ),
    "test": StartupPreset(
        schedule=[[0.1, 0.1], [0.1, 0.1], [0.1, 0.1]],
        labels=["test"],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=0,
        notify_color="green",
        notify_desc="eso tilin",
        notify_title="a la mrd",
        description="asd",
        commands={
            "session_start": [
                calendly
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [calendly, 1],  # after 1st pomodoro
                [open_zed, 2],  # after 2rd pomodoro
                [open_chess, 3],  # after 3rd pomodoro
            ],
            "session_complete": [
                f"sleep 2; {open_dawn}",
            ],
        },
        notify_phases={
            # Same style as commands: plain dict → always, [dict, int] → indexed
            "pomodoro_done": [
                {"title": "✅ wow tilin", "timeout": 4000},
                [{"desc": "{body}\neso tilin"}, 0],
                [{"desc": "{body}\nal la mrd", "timeout": 12000}, 1],
            ],
            "break_done": [
                [{"title": "⏰ no tilin"}, 0],
            ],
        },
    ),
    "cleaning": StartupPreset(
        schedule=[[25, 0]],
        labels=["cleaning, washing"],
        switches=[],
        start_dir=str(ARC_CLEANING),
        silence_secs=20,
        description="cleaning",
        commands={
            "session_start": [cleaning],
        },
    ),
    "phone_morning": StartupPreset(
        schedule=[
            [10, 10],  # 20 min
            [40, 30],  # 70 min
            [20, 10],  # 10 min
        ],  # Total 120
        labels=[
            # Arriving at the university, 60 min
            "wake up and prepare for going to the university",  # 10 min
            "walk at metropolitan/praying",  # 10 min
            "being at the metro/core task develop, ai what phone tools I could use in the morning to advance the work?",  # 40
            # Eating time and brush teeth, 60 min
            "wait to eat/core task develop",  # 30 min
            "eating",  # 20 min
            "brush teeth",  # 10 min
            # One hour with the laptop, morning ritual, switch to laptop with warm up preset
        ],
        switches=[],
        start_dir=str(ARC_SOUNDTRACKS_PAST),
        silence_secs=40,
        description="Phone morning when going to the university",
        commands={},
    ),
}
