"""Paths, presets, and defaults for the pomodoro timer."""
import tempfile
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────


def _find_project_root() -> Path:
    """Locate the repo root (parent of pomodoro_lib/)."""
    own = Path(__file__).resolve().parent  # pomodoro_lib/
    return own.parent  # repo root


# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = _find_project_root() / "data"
POMO_DIR = Path.home() / "Videos" / "study"
SOUNDS_DIR = POMO_DIR / "sound_effects"

FINISH_FILE = SOUNDS_DIR / "finish.mp3"

BELL_30_FILE = SOUNDS_DIR / "bell_30.mp3"
BELL_BEGIN_FILE = SOUNDS_DIR / "bell_begin.mp3"
BELL_END_FILE = SOUNDS_DIR / "bell_end.mp3"

PUSH_UPS_FILE = SOUNDS_DIR / "push_ups.mp3"

ARC_SOUNDTRACK = Path.home() / "Videos" / "current-arc"
ARC_SILENCE_SECONDS = 35  # seconds of silence between arc tracks
ARC_STARTUP = 10  # shorter silence for the startup preset

ARC_SOUNDTRACKS_PAST = Path.home() / "Videos" / "past-arc"

REFLECTION_SECS = 60  # silence after final pomodoro before finish sound

PAST_ARC_FILE = Path.home() / "Videos" / "music"

# COMMANDS
tabbed = 'i3-msg layout tabbed'
open_zk = 'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && exec /usr/bin/obsidian "obsidian://open?vault=second-brain"'
open_personal = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && exec /usr/bin/obsidian "obsidian://open?vault=personal"'
open_chess = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && firefox --no-remote "https://www.chess.com/play"'
open_git = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && firefox --no-remote "https://github.com/jorgemunozl"'
open_zed = 'i3-msg "workspace --no-auto-back-and-forth 4:💻" && zed'
open_terminal_riced = 'i3-msg "workspace --no-auto-back-and-forth >_" && alacritty -e bash -c "python3 ~/dotfiles/arc/src/start.py 2; exec bash"'
cleaning = "imv -f ~/Videos/clean.jpg"
open_dawn= 'pomodoro --task "golden morning" --video dawn_2025_II.mp4'
open_mine = 'pomodoro --task "golden afternoon" --video mine_2025_II.webm'
open_shinjuku_2 = 'pomodoro --task "golden afternoon" --video shinjuku2.mp4'
open_tired = "/home/jorge/dotfiles/tired/tired.sh"
i3_tab = 'i3-msg  '
shutdown_command = "python3 ~/dotfiles/alarm/alarm.py"
calendly ='i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=canvas%2Fdays-of-the-week-researchy"'
open_gmail = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  firefox --no-remote "https://mail.google.com/mail/u/0/#inbox"'
open_gmail_uni = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  firefox --no-remote "https://mail.google.com/mail/u/1/#inbox"'
open_huggingface = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  firefox --no-remote "https://huggingface.co/blog"'
slack='slack'
nchat='alacritty -e nchat'

# ── Runtime state files ────────────────────────────────────────────────────
# Termux has no /tmp — tempfile.gettempdir() resolves $TMPDIR there
# and /tmp on regular Linux desktops.
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
MPV_SOCKET = TMP_DIR / "mpvsocket"

TASKS_FILE = DATA_DIR / "tasks"
TASKS_UNIQUE = DATA_DIR / "tasks_unique"
HISTORY_FILE = DATA_DIR / "history"
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


# ── Duration presets ──────────────────────────────────────────────────────────
# (label, work_min, break_min)
DURATION_PRESETS = [
    ("25 min focus  ·  5 min break", 25, 5),
    ("30 min focus  ·  6 min break", 30, 6),
    ("35 min focus  ·  7 min break", 35, 7),
    ("40 min focus  ·  8 min break", 40, 8),
    ("45 min focus  ·  9 min break", 45, 9),
    ("50 min focus  ·  10 min break", 50, 10),
]
CUSTOM_LABEL = "⚡ Custom time"

# ── Default tasks ─────────────────────────────────────────────────────────────
DEFAULT_TASKS = []

# ── Pomodoro count options ────────────────────────────────────────────────────
COUNT_OPTIONS = [
    ("1 pomodoro", 1),
    ("2 pomodoros", 2),
    ("3 pomodoros", 3),
    ("4 pomodoros", 4),
    ("5 pomodoros", 5),
    ("6 pomodoros", 6),
]

BACK_LABEL = "↩ Back"


# ── Startup presets ────────────────────────────────────────────────────────────

from dataclasses import dataclass

# ── Notification colors ────────────────────────────────────────────────────────
# Map color names to dunst urgency levels. Configure your dunstrc per urgency.

NOTIFY_COLORS: dict[str, str] = {
    "default": "critical",
    "red": "critical",
    "yellow": "normal",
    "blue": "low",
    "green": "normal",
    "purple": "normal",
}


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

from pomodoro_lib.commands import CommandsBuilder

_TMP = Path(tempfile.gettempdir())

_SAY_TIME = (
    f'F="{SOUNDS_DIR}/say_time_$(date +%I_%M_%p).mp3"; '
    "[ -f \"$F\" ] || gtts-cli \"The time is $(date '+%I:%M %p')\" --output \"$F\"; "
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
    "night_hardcore": StartupPreset(
        schedule=[
            [15, 2],
            [15, 1],
            [25, 5],
            [25, 5],
            [25, 5],
            [25, 0],
        ],  # TODO: Warm up time lacking
        labels=["polymath", "set-up", "applications"],
        switches=[[3, str(POMO_DIR / "christmas_2025-I.webm"), False]],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_STARTUP,
        notify_color="blue",
        description="night hardcore",
    ),
    "night_light": StartupPreset(
        schedule=[[25, 5], [25, 5], [25, 5], [25, 1], [25, 1]],
        labels=["polymath / applications 1/5",
            "wash teeth",
            "blue pomodoro 2/5",
            "prepare for tomorrow",
            "blue pomodoro 3/5",
            "log metrics",
            "blue pomodoro 4/5",
            "last chess of the day and grab a book to read",
            "practicing next arc night 5/5"
        ],

        switches=[],
        start_dir=str(POMO_DIR / "christmas_2025-I.webm"),
        silence_secs=ARC_SILENCE_SECONDS,
        description="night good one, from seven 7.40 to 7.55 turn it on",
        commands={
            "session_complete": [f"{open_chess}, sleep 420, {shutdown_command}"],
            "session_start": [calendly],
        },
        notify_color="blue",
    ),
    "noon": StartupPreset(
        schedule=[[15, 3], [15, 1], [17, 1], [6, 2]],
        labels=["polymath", "set-up", "applications", "prepare code","coding", "prepare chess","six min chess", "plan plan"],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_SILENCE_SECONDS,
        description="noon after eat around preparing ourselves for the nap",
        notify_color="blue",
        commands={
            "session_start": [
                open_zk
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [calendly, 1],  # after 1st pomodoro
                [open_zed, 2],  # after 2rd pomodoro
                [open_chess, 3]  # after 3rd pomodoro
            ],
            "session_complete": [
                f"sleep 60 ;{open_tired}; {open_shinjuku_2}",
            ],
        },
    ),
    "morning": StartupPreset(
        schedule=[
            [18, 3],
            [17, 2],
            [10, 1],
            [5, 4],
        ],  # Plan means also review the weekly days from obsidian, so give more time, 1.05 I dont like that
        labels=[
            "polymath",
            "set-up",
            "applications",
            "vault",
            "chess/review",
            "chess review",
            "stretch",
            "plan, plan",
        ],
        switches=[],
        start_dir=str(ARC_SOUNDTRACKS_PAST),
        silence_secs=ARC_SILENCE_SECONDS,
        description="morning winter ritual",
        notify_color="yellow",
        commands={
                    "session_start": [
                        open_zk
                    ],  # only once, at the very beginning (plain string)
                    "pomodoro_done": [
                        [calendly, 1],  # after 1st pomodoro
                        [f"{open_gmail} ; {open_huggingface} ; {open_gmail_uni} ; {slack} ; {nchat} ; {open_terminal_riced}; {tabbed}", 2],  # after 3rd pomodoro
                    ],
                    "pomodoro_begin": [
                        [open_chess, 2],  # before 1st pomodoro
                    ],
                    "session_complete": [
                        f"sleep 60 ;{open_dawn}",
                    ],
                },
    ),
    "afternoon": StartupPreset(
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
                        [open_chess, 3]  # after 3rd pomodoro
                    ],
                    "session_complete": [
                        f"sleep 1 ;{open_tired} ; {open_shinjuku_2}",
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
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=20,
        description="cleaning",
        commands={
            "session_start": [cleaning],
        },
    ),
    "phone_morning": StartupPreset(
        schedule=[[]],
        labels=["going to take the bus", "wait the bus", "using the bus", "leaving the bus"],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=0,
        description="Phone morning when going to the university",
        commands={},
    ),
}
