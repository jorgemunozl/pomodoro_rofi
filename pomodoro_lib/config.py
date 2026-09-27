# flake8: noqa
from dataclasses import dataclass

from pomodoro_lib.commands import CommandsBuilder
from pomodoro_lib.constants import (
    ARC_CLEANING,
    ARC_SILENCE_SECONDS,
    ARC_SOUNDTRACK,
    ARC_SOUNDTRACKS_PAST,
    PUSH_UPS_FILE,
    SOUNDS_DIR,
    calendly,
    cleaning,
    journal,
    nets,
    open_chess,
    open_dawn,
    open_tired,
    open_zed,
    open_zk,
    shutdown_command,
)


@dataclass
class StartupPreset:
    """A pre-configured startup pomodoro session."""
    schedule: list  
    labels: list
    switches: list 
    start_dir: str
    silence_secs: int
    description: str 
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
    steps: list
    description: str = ""


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

ANNOUNCE_TIME_ON_DONE: bool = False

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
        schedule=[  # begin at 8.3
            [7,  7],  # 14 min
            [7,  7],  # 14 min
            [6, 10],  # 16 min
            [12, 8],  # 20 min
        ],  # total 64 min
        labels=[
            "leaving university, going to eat",                 # 10 min
            "eating, thinking on journaling while at the bus",  # 10 min
            "journaling day time",                              # 7 min
            "journaling work time",                             # 7 min min
            "reflect one note time",                            # 6 min
            "ten minutes daily chess time",                     # 12 min
            "walk to home, thinking on following",              # 8 min
            # After 40 min reach home 9 pm
        ],
        switches     = [],
        say_label    = True,
        start_dir    = str(ARC_SOUNDTRACK),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "Preset for 8.00 to 9.00, a light short version of night",
    ),
    "night_blitz": StartupPreset(
        schedule=[
            [7,  1],  # 5 pomodoro
            [14, 2],  # 14 pomodoro
            [12, 1],  # 12 pomodoro
        ],  # total 30 min
        labels=[
            "cleaning hands, face, teeth, and put ourselves light clothes",  # 7 min
            "prepare backpack for tomorrow",                                 # 10 min
            "",                                                              # 14 min
        ],
        say_label    = True,
        switches     = [],
        start_dir    = str(ARC_SOUNDTRACK),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "Home 40 min between arrive and sleep",
    ),
    "night": StartupPreset(
        schedule=[
            [7,  7],  # 14 :journal
            [6,  1],  # 6  :reflect
            [15, 1],  # 16 :applications
            [7,  6],  # 13 :budget
            [6,  1],  # 7  :break and metrics
            [9,  8],  # 17 :review arc, write core task for tomorrow
            [4,  2],  # 6  :tidy around,
            [2,  2],  # 4  :pray at bed
        ],  # 124
        labels=[
            "journal/day",                 # 7
            "journal/work",                # 7
            "reflect a single note",       # 6
            "gap",                         # 0
            "applications",                # 15
            "prepare budget",              # 1
            "budget",                      # 7
            "break 6 min",                 # 6
            "log metrics",                 # 6
            "prepare review arc",          # 1
            "review arc",                  # 9
            "write core task for tomorrow",  # 8
            "tidy",                        # 4
            "go bed",                      # 2
            "pray at bed",                 # 2
            "plan thinking tomorrow",      # 2
        ],                                 # total: 20
        switches     = [],
        start_dir    = str(ARC_SOUNDTRACK),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "night when at home, begin programatically" \
        " at 7:30 pm finish at 9:30, thus wake up at 5:00",
        commands     =
        {
            "session_complete": [f"sleep 60; {shutdown_command}"],
            "session_start": [journal],
        },
        notify_color  = "blue",
    ),
    "noon_main": StartupPreset(
        schedule=[
            [5,  7],  # 12
            [13, 2],  # 15
            [11, 2],  # 13
            [19, 1],  # 20
        ],  # 60 min
        say_label    = True,
        labels=[
            "personal matter reading",  # 14
            "predict the future work",  # 7
            "spaced repetition session one",  # 13
            "spaced repetition break",  # 2
            "spaced repetition session two",  # 13
            "set up for the afternoon",  # 4
            "code/polymath anticipating the afternoon",  # 17
            "afternoon warm up",
        ],
        switches     = [],
        start_dir    = str(ARC_SOUNDTRACKS_PAST),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "after nap",
    ),
    "noon_after_eat": StartupPreset(
        schedule=[
            [5,  1],  # 6
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
        switches     = [],
        start_dir    = str(ARC_SOUNDTRACKS_PAST),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "noon, 12:40 until 1:40 then around 4:30 meaning ends 6:10",
        notify_color = "blue",
        say_label    = True,
        commands     = {
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
        switches     = [],
        commands     = {
            "session_start": [
                open_zk
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [nets, 2],  # after 3rd pomodoro
            ],
        },
        start_dir    = str(ARC_SOUNDTRACK),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "one hour morning",
    ),
    "morning_wake_up": StartupPreset(
        schedule=[
            [4,  3],  # 7
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
        switches     = [],
        start_dir    = str(ARC_SOUNDTRACK),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "morning winter ritual",
        notify_color = "yellow",
        commands     = {
            "session_start": [
                open_zk
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [nets, 2],  # after 3rd pomodoro
            ],
        },
    ),
    "afternoon_problem_solving": StartupPreset(
        schedule=[
            [29, 1],
            [29, 1],
        ],
        labels=[
            "problem solving",
            "review",
            "problem solving",
            "review",
        ],
        switches     = [],
        start_dir    = str(ARC_SOUNDTRACKS_PAST),
        silence_secs = ARC_SILENCE_SECONDS,
        description  = "afternoon of problem solving from four to six, once each two days I think that is proper",
    ),
    "test": StartupPreset(
        schedule=[
            [0.1, 0.1],
            [0.1, 0.1],
            [0.1, 0.1],
        ],
        labels=[
            "test",
        ],
        switches      = [],
        start_dir     = str(ARC_SOUNDTRACK),
        silence_secs  = 0,
        notify_color  = "green",
        notify_desc   = "eso tilin",
        notify_title  = "a la mrd",
        description   = "asd",
        commands      = {
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
        notify_phases = {
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
        schedule=[
            [25, 0],
        ],
        labels=[
            "cleaning, washing",
        ],
        switches     = [],
        start_dir    = str(ARC_CLEANING),
        silence_secs = 20,
        description  = "cleaning",
        commands     = {
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
        switches     = [],
        start_dir    = str(ARC_SOUNDTRACKS_PAST),
        silence_secs = 40,
        description  = "Phone morning when going to the university",
        commands     = {},
    ),
}
