"""Static constants: paths, commands, rhythms, and day-derived values.

Kept separate from config.py, which defines session-level configuration
(StartupPreset / Chain definitions and event commands).
"""

import tempfile
from datetime import datetime
from pathlib import Path


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
ARC_CLEANING = Path.home() / "Videos" / "workout" / "rollouts" / "cleaning"
ARC_SILENCE_SECONDS = 35  # seconds of silence between arc tracks
ARC_STARTUP = 10  # shorter silence for the startup preset

ARC_SOUNDTRACKS_PAST = Path.home() / "Videos" / "past-arc"

REFLECTION_SECS = 60  # silence after final pomodoro before finish sound

EXTRA_WORK_SECS = 2.5  # extra seconds added to every work phase (25:00 → 25:03)

PAST_ARC_FILE = Path.home() / "Videos" / "music"

# ── Commands ──────────────────────────────────────────────────────────────────
tabbed = 'alacritty -e "i3-msg layout tabbed"'

journal = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=project-notes%2Fdays-of-the-week"'

open_zk = 'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && exec /usr/bin/obsidian "obsidian://open?vault=second-brain"'
open_personal = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && exec /usr/bin/obsidian "obsidian://open?vault=personal"'
open_social = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && exec /usr/bin/obsidian "obsidian://open?vault=social"'
open_network = 'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && exec /usr/bin/obsidian "obsidian://open?vault=networking"'

open_chess = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && firefox --no-remote "https://www.chess.com/home"'
open_git = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && firefox --no-remote "https://github.com/jorgemunozl"'
open_zed = 'i3-msg "workspace --no-auto-back-and-forth 4:💻" && zed'
open_uta = 'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && mpv --fullscreen /home/jorge/Videos/kamado.webm'
open_terminal_riced = (
    'alacritty -e bash -c "python3 ~/dotfiles/arc/src/start.py 2; exec bash"'
)

cleaning = "imv -f ~/Videos/clean.jpg"

open_dawn = 'pomodoro --task "golden morning" --video dawn_2025_II.mp4'
open_mine = 'pomodoro --task "golden afternoon" --video mine_2025_II.webm'
open_shinjuku_2 = 'pomodoro --task "golden afternoon" --video shinjuku2.mp4'
open_tired = "/home/jorge/dotfiles/tired/tired.sh"

shutdown_command = "python3 /home/jorge/dotfiles/alarm/alarm.py"

calendly = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && /usr/bin/obsidian "obsidian://open?vault=personal&file=canvas%2Fdays-of-the-week-researchy"'
open_gmail = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  firefox --no-remote "https://mail.google.com/mail/u/0/#inbox"'
open_gmail_uni = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  firefox --no-remote "https://mail.google.com/mail/u/1/#inbox"'
open_huggingface = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" &&  firefox --no-remote "https://huggingface.co/blog"'
slack = "slack"
nchat = "alacritty -e nchat"
nets = f"{tabbed}; {open_gmail} & {open_huggingface} & {open_git} & {open_gmail_uni} & {slack} & {nchat} & {open_terminal_riced}"

# ── Day-derived values ────────────────────────────────────────────────────────
current_day = datetime.now().day

even_day = current_day % 2 == 0

# Rotating morning pomodoro by day of month (currently unused by the app).
if current_day % 3 == 0:
    choseed = open_dawn
elif current_day % 3 == 1:
    choseed = 2
else:
    choseed = 2  # golden morning

morning_pomodoro = choseed

even_day_zk = even_day * open_zk + (not even_day) * calendly
even_day_social = even_day * open_social + (not even_day) * open_network
even_day_label = even_day * "polymath" + (not even_day) * "applications"

odd_day_zk = (not even_day) * open_zk + even_day * calendly
odd_day_social = (not even_day) * open_social + even_day * open_network
odd_day_label = (not even_day) * "polymath" + even_day * "applications"

even_day_social_label = even_day * "social" + (not even_day) * "networking"


# ── Command registry (for `pomodoro --command <name>`) ────────────────────────
# Every shell command defined above, plus the day-derived shortcuts. Kept after
# the definitions so all names exist when this dict is built.
COMMANDS: dict[str, str] = {
    name: globals()[name]
    for name in (
        "tabbed",
        "journal",
        "open_zk",
        "open_personal",
        "open_social",
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
        # Day-derived shortcuts (resolve to a concrete command at import time)
        "even_day_zk",
        "even_day_social",
        "odd_day_zk",
        "odd_day_social",
    )
}


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
TRANSITION_LOCK = TMP_DIR / "pomo_transition_lock"
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
