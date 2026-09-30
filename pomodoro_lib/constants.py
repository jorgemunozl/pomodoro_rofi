# flake8: noqa
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pomodoro_lib.commands import (
    EVENT_BREAK_DONE,
    EVENT_POMODORO_BEGIN,
    EVENT_POMODORO_DONE,
    EVENT_SESSION_START,
)

ScheduleEntry = (
    tuple[list, tuple[str, str]] | tuple[list, tuple[str, str], tuple[str, str] | None]
)


def _find_project_root() -> Path:
    """Locate the repo root (parent of pomodoro_lib/)."""
    own = Path(__file__).resolve().parent  # pomodoro_lib/
    return own.parent  # repo root


DATA_DIR = _find_project_root() / "data"
POMO_DIR = Path.home() / "Videos" / "study"
SOUNDS_DIR = POMO_DIR / "sound_effects"

FINISH_FILE = SOUNDS_DIR / "finish.mp3"

BELL_30_FILE = SOUNDS_DIR / "bell_30.mp3"
BELL_BEGIN_FILE = SOUNDS_DIR / "bell_begin.mp3"
BELL_END_FILE = SOUNDS_DIR / "bell_end.mp3"

PUSH_UPS_FILE = SOUNDS_DIR / "push_ups.mp3"

ARC_SOUNDTRACK = Path.home() / "Videos" / "current-arc"
ARC_CLEANING = Path.home() / "Videos" / "workout" / "rollouts" / "cleaning"
ARC_SILENCE_SECONDS = 240  # seconds of silence between arc tracks
ARC_STARTUP = 10  # shorter silence for the startup preset


@dataclass
class StartupPreset:
    """Preset schedule entries hold timing, phase labels, and optional event command."""

    schedule: list[ScheduleEntry] = field(default_factory=list)
    start_dir: str | None = None
    description: str = ""
    switches: list = field(default_factory=list, kw_only=True)
    silence_secs: int = field(default=ARC_SILENCE_SECONDS, kw_only=True)
    commands: dict[str, list] | None = field(default=None, kw_only=True)
    notify_color: str = field(default="default", kw_only=True)
    notify_title: str = field(default="", kw_only=True)
    notify_desc: str = field(default="", kw_only=True)
    notify_timeout: int = field(default=0, kw_only=True)
    notify_phases: dict | None = field(default=None, kw_only=True)
    say_label: bool = field(default=True, kw_only=True)

    @property
    def timing_schedule(self) -> list[list]:
        return [entry[0] for entry in self.schedule]

    @property
    def phase_labels(self) -> list[str]:
        return [label for entry in self.schedule for label in entry[1]]

    @property
    def schedule_commands(self) -> dict[str, list]:
        """Return event commands filtered to their matching schedule entry."""
        commands: dict[str, list] = {}
        for index, entry in enumerate(self.schedule):
            if len(entry) < 3 or entry[2] is None:
                continue
            command, event = entry[2]
            event_index = index
            if event == "pomodoro_done" and index == len(self.schedule) - 1:
                event_index += 1  # the final pomodoro_done event is 1-based
            commands.setdefault(event, []).append([command, event_index])
        return commands


ARC_SOUNDTRACKS_PAST = Path.home() / "Videos" / "past-arc"

REFLECTION_SECS = 60  # silence after final pomodoro before finish sound

EXTRA_WORK_SECS = 2.5  # extra seconds added to every work phase (25:00 → 25:03)

TEST_PHASE_SECS = 7  # phase length in a preset's --test run

PAST_ARC_FILE = Path.home() / "Videos" / "music"

# ── Commands ────────────────────────────────────────────────────────────────
tabbed = 'alacritty -e "i3-msg layout tabbed"'

journal = (
    'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && '
    '/usr/bin/obsidian "obsidian://open?vault=personal&'
    'file=project-notes%2Fdays-of-the-week"'
)

open_zk = (
    'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && '
    'exec /usr/bin/obsidian "obsidian://open?vault=second-brain"'
)

current_arc = (
    'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && '
    '/usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2FArc Spring 2026 III Infinite Thinker"'
)

open_personal = (
    'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && '
    'exec /usr/bin/obsidian "obsidian://open?vault=personal"'
)
open_social = (
    'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && '
    'exec /usr/bin/obsidian "obsidian://open?vault=social"'
)
open_network = (
    'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && '
    'exec /usr/bin/obsidian "obsidian://open?vault=networking"'
)

mlpdft_workspace = 'i3-msg "workspace --no-auto-back-and-forth 4:💻" && zed ~/project/mlpdft && i3-msg "workspace --no-auto-back-and-forth 2:🟣" && /usr/bin/obsidian "obsidian://open?vault=social&file=project-notes%2Fmlpdft" & i3-msg "workspace --no-auto-back-and-forth 2:🟣" && /usr/bin/obsidian "obsidian://open?vault=second-brain&file=project-notes%2Fmlpdft"'

core_tasks = 'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && /usr/bin/obsidian "obsidian://open?vault=social&file=permanent-notes%2Fmlpdft Core task to advance at light speed"'

metrics = "python ~/project/metrics/metrics_server.py & firefox http://127.0.0.1:8000"

applications = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=project-notes%2Fapplications"'

budget = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=project-notes%2Fmoney-management"'

open_chess = (
    'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && '
    'firefox --no-remote "https://www.chess.com/home"'
)
open_git = (
    'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && '
    'firefox --no-remote "https://github.com/jorgemunozl"'
)
open_zed = 'i3-msg "workspace --no-auto-back-and-forth 4:💻" && zed'
open_uta = (
    'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && '
    "mpv --fullscreen /home/jorge/Videos/kamado.webm"
)
open_terminal_riced = (
    'alacritty -e bash -c "python3 ~/dotfiles/arc/src/start.py 2; exec bash"'
)

cleaning = "imv -f ~/Videos/clean.jpg"

open_dawn = 'pomodoro --video "dawn_2025_II.mp4"'
open_mine = 'pomodoro --video "mine_2025_II.webm"'
open_shinjuku_2 = 'pomodoro --video "shinjuku2.mp4"'
open_tired = "/home/jorge/dotfiles/tired/tired.sh"

monday = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2FInfinite Thinker Mondays are about assist to classes and talk with Jeff"'

thursday = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2FInfinite Thinker Thursdays is for advance the MACE paper and classical mechanics duty"'

wednesday = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2FInfinite Thinker Wednesdays is about assist to classes and advance MACE paper"'

tuesday = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2FInfinite Thinker Tuesdays are about advance MACE paper at the morning and mathematical methods exam"'

friday = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2FInfinite Thinker Fridays is about classes morning and modern exam or advance with the thesis, cooking something for tomorrow morning"'

saturday = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2finfinite thinker saturdays i go to the library to advance the paper and prepare ourselves for the sunday at night"'

sunday = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=permanent-notes%2finfinite thinker sundays are about do trivial task try hard and reset the week"'

open_week = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://adv-uri?vault=personal&commandid=periodic-notes%3Aopen-weekly-note"'

current_day = datetime.now().astimezone().day


def return_day_of_week() -> str:
    """Return the current day of the week as a string."""
    return datetime.now().astimezone().strftime("%A").lower()


open_journal_work = str(eval(return_day_of_week()))

countdown = "firefox /home/jorge/dotfiles/warmup-ritual/led-countdown.html & mpv --input-ipc-server=/tmp/mpvsocket --no-video /home/jorge/Videos/tired/kamado.webm"

shutdown_command = "python3 /home/jorge/dotfiles/alarm/alarm.py"
turn_off_command = "python3 ~/dotfiles/alarm/turn_off.py"


calendly = (
    'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && '
    '/usr/bin/obsidian "obsidian://open?vault=personal&'
    'file=canvas%2Fdays-of-the-week-researchy"'
)
open_gmail = (
    'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  '
    'firefox --no-remote "https://mail.google.com/mail/u/0/#inbox"'
)
open_gmail_uni = (
    'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  '
    'firefox --no-remote "https://mail.google.com/mail/u/1/#inbox"'
)
open_huggingface = (
    'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  '
    'firefox --no-remote "https://huggingface.co/blog"'
)
slack = "slack"
nchat = "alacritty -e nchat"
nets = (
    f"{tabbed}; {open_gmail} & {open_huggingface} & {open_git} & "
    f"{open_gmail_uni} & {slack} & {nchat} & {open_terminal_riced}"
)

CLIAMP_LOFI_URL = "http://radio.cliamp.stream/lofi/stream"
CLIAMP_PLAYLIST = "lofi"

cliamp_start = "cliamp --daemon"
cliamp_pause = "cliamp pause"
cliamp_play = "cliamp play"
cliamp_stop = "cliamp stop"


COMMANDS: dict[str, str] = {
    name: globals()[name]
    for name in (
        "tabbed",
        "open_journal_work",
        "open_zk",
        "open_personal",
        "open_social",
        "open_week",
        "open_network",
        "open_chess",
        "open_git",
        "open_zed",
        "open_uta",
        "open_terminal_riced",
        "cleaning",
        "open_dawn",
        "open_mine",
        "open_shinjuku_2",
        "open_tired",
        "shutdown_command",
        "calendly",
        "open_gmail",
        "open_gmail_uni",
        "open_huggingface",
        "slack",
        "nchat",
        "nets",
        "cliamp_start",
        "cliamp_pause",
        "cliamp_play",
        "cliamp_stop",
    )
}


TMP_DIR = Path(tempfile.gettempdir())

STATE_FILE = TMP_DIR / "pomo_state.json"
PID_FILE = TMP_DIR / "pomo_mpv.pid"
TIMER_PID_FILE = TMP_DIR / "pomo_timer.pid"
PAUSE_FILE = TMP_DIR / "pomo_pause"
PAUSE_TS = TMP_DIR / "pomo_pause_ts"
SKIP_RANDOM_FILE = TMP_DIR / "pomo_skip_random"
BELL_30_PLAYED = TMP_DIR / "pomo_bell_30_played"
BELL_BEGIN_PLAYED = TMP_DIR / "pomo_bell_begin_played"
WORK_BELL_PLAYED = TMP_DIR / "pomo_work_bell_played"
FINISH_PLAYED = TMP_DIR / "pomo_finish_played"
TRANSITION_LOCK = TMP_DIR / "pomo_transition_lock"
MPV_SOCKET = TMP_DIR / "mpvsocket"

CMD_LOG_FILE = DATA_DIR / "cmd_history"

ROFI_THEME = Path.home() / ".config" / "rofi" / "pomodoro.rasi"


INCLUDE_DURATION_FILES = [
    "dr.mp4",
    "nate.mp4",
    "steven.mp4",
    "math.mp4",
    "darkacademia.mp4",
]

# Variable pomodoro, one of 25-5, two 50-10-2, and 25-5, warm up offset time
brain_fm = [(25, 5), (50, 10, 2), (25, 5), 110]
shinjuku = [(50, 10, 2), (50, 20), (50, 10, 2), 72]
shinjuku2 = [(25, 5, 3), (25, 15), (25, 5, 4), 81]


# Pomodoro minutes, break minutes, repetitions, warm up time seconds
POMODORO_DEFAULTS = [
    ("christmas_2025-I.webm", 25, 5, 4, 77.5),
    ("dawn_2025_II.mp4", 25, 5, 8, 80),
    ("mine_2025_II.webm", 25, 5, 4, 59),
    ("shinjuku2.mp4", shinjuku2),
    ("study.mp4", 25, 5, 5, 70),
    ("shinjuku.mp4", 25, 5, 8, 72),
    ("golden.webm", 25, 5, 4, 79),
    ("brain_fm.mp4", brain_fm),
    ("shinjuku.webm", shinjuku),
]


# ── Duration presets ────────────────────────────────────────────────────────
# (label, work_min, break_min)
DURATION_PRESETS = [
    ("50 min focus  ·  10 min break", 50, 10),
    ("25 min focus  ·  5 min break", 25, 5),
    ("30 min focus  ·  6 min break", 30, 6),
    ("35 min focus  ·  7 min break", 35, 7),
    ("40 min focus  ·  8 min break", 40, 8),
    ("45 min focus  ·  9 min break", 45, 9),
]
CUSTOM_LABEL = "⚡ Custom time"

# ── Pomodoro count options ──────────────────────────────────────────────────
COUNT_OPTIONS = [
    ("2 pomodoros", 2),
    ("1 pomodoro", 1),
    ("3 pomodoros", 3),
    ("4 pomodoros", 4),
    ("5 pomodoros", 5),
    ("6 pomodoros", 6),
]

BACK_LABEL = "↩ Back"

NOTIFY_COLORS: dict[str, str] = {
    "default": "critical",
    "red": "critical",
    "yellow": "normal",
    "blue": "low",
    "green": "normal",
    "purple": "normal",
}

STARTUP_PRESETS_SPRING_THINKER: dict[str, StartupPreset] = {
    "morning_ritual_spring_thinker": StartupPreset(
        [
            (
                [4, 1],
                ("clean myself", "set up"),
                (f"{countdown} && {mlpdft_workspace}", EVENT_SESSION_START),
            ),
            ([15, 5], ("first", "nets time"), (nets, EVENT_POMODORO_DONE)),
            ([16, 1], ("second", "break")),
            ([16, 1], ("third", "it's over")),
        ],
        str(ARC_SOUNDTRACK),
        "one hour morning, at cec, from seven to eigth",
    ),
    "morning_bus_spring_thinker": StartupPreset(
        [
            ([16, 3], ("read", "phase")),
            ([6, 1], ("arrive uni", "phase")),
            ([20, 1], ("laptop mace", "phase")),
            ([11, 1], ("claude", "home arrive protocol")),
        ],
        str(ARC_SOUNDTRACK),
        "bus and walking, morning, 5:20 from 6.30",
    ),
    "noon_ritual_spring_thinker": StartupPreset(
        [
            (
                [11, 2],
                ("spaced repetition session one", "spaced repetition break"),
                (open_zk, EVENT_SESSION_START),
            ),
            ([11, 2], ("spaced repetition session two", "spaced repetition break")),
            (
                [11, 2],
                ("spaced repetition session three", "spaced repetition break"),
                (open_personal, EVENT_BREAK_DONE),
            ),
            ([6, 2], ("predict the future work", "personal prepared")),
            ([8, 0], ("personal read", "")),
        ],
        str(ARC_SOUNDTRACKS_PAST),
        "after nap, pray already did it,1:05 to 2",
    ),
    "afternoon_bus_spring_thinker": StartupPreset(
        [
            ([9, 4], ("leaving uni", "bus task")),
            ([5, 1], ("chess", "phase")),
            ([20, 3], ("read", "phase")),
            ([12, 4], ("walk to home", "home arrive protocol")),
        ],
        str(ARC_SOUNDTRACK),
        "bus and walking, afternoon, 5:20 from 5:50",
    ),
    "night_jeff_spring_thinker": StartupPreset(
        [
            ([11, 10], ("greet", "science")),
            ([8, 5], ("special", "break")),
            ([22, 2], ("chess", "goodbye"), (open_chess, EVENT_POMODORO_BEGIN)),
        ],
        str(None),
        "Monday and thursday call to Jeff",
    ),
    "night_fast_ritual_spring_thinker": StartupPreset(
        [
            ([8, 0], ("core tasks", ""), (core_tasks, "pomodoro_done")),
            ([8, 0], ("applications", ""), (applications, "pomodoro_done")),
            ([1, 0], ("log metrics", ""), (metrics, "pomodoro_done")),
            (
                [7, 6],
                ("journal/work", "journal/day"),
                (open_journal_work, "pomodoro_done"),
            ),
            ([6, 4], ("reflect a note", "tidy")),
        ],
        str(ARC_SOUNDTRACK),
        "40 min, fast version of night ritual",
    ),
    "night_ritual_spring_thinker": StartupPreset(
        [
            ([15, 1], ("applications", "phase"), (applications, EVENT_SESSION_START)),
            ([8, 6], ("core task time", "tidy"), (core_tasks, EVENT_POMODORO_BEGIN)),
            ([8, 1], ("review arc", "phase"), (current_arc, EVENT_POMODORO_BEGIN)),
            ([8, 1], ("budget", "phase"), (budget, EVENT_POMODORO_BEGIN)),
            ([2, 6], ("log metrics", "break 6 min"), (metrics, EVENT_POMODORO_BEGIN)),
            (
                [7, 1],
                ("journal/work", "phase"),
                (open_journal_work, EVENT_POMODORO_BEGIN),
            ),
            (
                [6, 1],
                ("journal/day", "phase"),
                (open_week, EVENT_POMODORO_BEGIN),
            ),
            ([7, 3], ("reflect a note", "tidy")),
            (
                [4, 1],
                ("going to sleep", "turn off"),
                (turn_off_command, "pomodoro_done"),
            ),
        ],  # 87
        str(ARC_SOUNDTRACK),
        "spring night begin at eight",
    ),
}

STARTUP_PRESETS_REGISTRY: dict[str, StartupPreset] = STARTUP_PRESETS_SPRING_THINKER

STARTUP_PRESETS_REGISTRY_RESEARCHY: dict[str, StartupPreset] = {
    "morning_wakeup_winter_researchy": StartupPreset(
        [
            ([4, 3], ("pray", "prepare myself for the morning")),
            ([21, 5], ("polymath first session", "nets break")),
            (
                [21, 5],
                ("polymath second session, morning warm up", "schedule the morning"),
            ),
        ],
        str(ARC_SOUNDTRACK),
        "morning winter ritual",
    ),
    "afternoon_problem_solving_researchy": StartupPreset(
        [
            ([29, 1], ("problem solving", "review")),
            ([29, 1], ("problem solving", "review")),
        ],
        str(ARC_SOUNDTRACKS_PAST),
        (
            "afternoon of problem solving from four to six, once each two "
            "days I think that is proper"
        ),
    ),
    "cleaning_researchy": StartupPreset(
        [([25, 0], ("cleaning, washing", ""))],
        str(ARC_CLEANING),
        "cleaning",
    ),
}


def preset_duration_minutes(preset: StartupPreset) -> int | float:
    """Return the total work and break time for a startup preset."""
    return sum(sum(entry[0]) for entry in preset.schedule)


def print_preset_times() -> None:
    """Print the total work and break minutes for each startup preset."""
    for name, preset in STARTUP_PRESETS_REGISTRY.items():
        print(f"{name}: {preset_duration_minutes(preset):g} minutes")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preset_time",
        "--preset-time",
        action="store_true",
        help="print total work and break time for every startup preset",
    )
    args = parser.parse_args()
    if args.preset_time:
        print_preset_times()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
