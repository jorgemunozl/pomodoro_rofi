"""Paths, presets, and defaults for the pomodoro timer."""

import os
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────


def _find_project_root() -> Path:
    """Locate the repo root (parent of pomodoro_lib/)."""
    own = Path(__file__).resolve().parent  # pomodoro_lib/
    return own.parent  # repo root


# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = _find_project_root() / "data"
POMO_DIR = Path.home() / "Videos" / "study"

FINISH_FILE = POMO_DIR / "finish.mp3"

BELL_30_FILE = POMO_DIR / "bell_30.mp3"
BELL_BEGIN_FILE = POMO_DIR / "bell_begin.mp3"
BELL_END_FILE = POMO_DIR / "bell_end.mp3"

ARC_SOUNDTRACK = Path.home() / "Videos" / "current-arc"
ARC_SILENCE_SECONDS = 35  # seconds of silence between arc tracks
ARC_STARTUP = 10  # shorter silence for the startup preset

ARC_SOUNDTRACKS_PAST = Path.home() / "Videos" / "past-arc"

REFLECTION_SECS = 60  # silence after final pomodoro before finish sound

PAST_ARC_FILE = Path.home() / "Videos" / "music"

# COMMANDS
open_zk = 'i3-msg "workspace --no-auto-back-and-forth 2:🟣" && exec /usr/bin/obsidian "obsidian://open?vault=second-brain"'
open_personal = 'i3-msg "workspace --no-auto-back-and-forth 1:🟢" && exec /usr/bin/obsidian "obsidian://open?vault=personal"'
open_chess = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && firefox --no-remote "https://www.chess.com/member/jorgemunozl"'
open_git = 'i3-msg "workspace --no-auto-back-and-forth 3:🌐" && firefox --no-remote "https://github.com/jorgemunozl"'
open_zed = 'i3-msg "workspace --no-auto-back-and-forth 4:💻" && zed'
open_terminal_riced = 'i3-msg "workspace --no-auto-back-and-forth >_" && alacritty -e bash -c "python3 ~/dotfiles/arc/src/start.py 2; exec bash"'
cleaning = "imv -f ~/Videos/clean.jpg"

STATE_FILE = Path("/tmp/pomo_state.json")
PID_FILE = Path("/tmp/pomo_mpv.pid")
TIMER_PID_FILE = Path("/tmp/pomo_timer.pid")
PAUSE_FILE = Path("/tmp/pomo_pause")
PAUSE_TS = Path("/tmp/pomo_pause_ts")
SKIP_RANDOM_FILE = Path("/tmp/pomo_skip_random")
BELL_30_PLAYED = Path("/tmp/pomo_bell_30_played")
BELL_BEGIN_PLAYED = Path("/tmp/pomo_bell_begin_played")
WORK_BELL_PLAYED = Path("/tmp/pomo_work_bell_played")
FINISH_PLAYED = Path("/tmp/pomo_finish_played")
MPV_SOCKET = Path("/tmp/mpvsocket")

TASKS_FILE = DATA_DIR / "tasks"
TASKS_UNIQUE = DATA_DIR / "tasks_unique"
HISTORY_FILE = DATA_DIR / "history"

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


# Pomodoro minutes, break minutes, repetitions, warm up time seconds
POMODORO_DEFAULTS = [
    ("christmas_2025-I.webm", 25, 5, 4, 77.5),
    ("dawn_2025_II.mp4", 25, 5, 8, 80),
    ("mine_2025_II.webm", 25, 5, 4, 59),
    ("shinjuku2.mp4", 25, 5, 8, 81),
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

ANNOUNCE_TIME_ON_DONE: bool = True
"""When True, speaks the current time via gtts-cli after every pomodoro.

This is injected into the global EVENT_COMMANDS under ``pomodoro_done``,
so it fires for ALL sessions and presets. Set to ``False`` to disable.
"""


# ── Build EVENT_COMMANDS ──────────────────────────────────────────────────────
# EVENT_COMMANDS is the global command registry.  It's merged with each
# preset's own ``commands`` field at runtime so both layers fire.

_EVENT_COMMANDS: dict[str, list] = {}

if ANNOUNCE_TIME_ON_DONE:
    _EVENT_COMMANDS.setdefault("pomodoro_done", []).append(
        'gtts-cli "The time is $(date "+%I:%M %p")" '
        "--output /tmp/say_time.mp3 "
        "&& mpv /tmp/say_time.mp3 --volume=130 --no-terminal"
    )

# Push-ups reminder — every 2 pomodoros (≈ each hour)
_EVENT_COMMANDS.setdefault("pomodoro_done", []).append(
    [
        'gtts-cli "10 push ups time!" '
        "--output /tmp/push_reminder.mp3 "
        "&& mpv /tmp/push_reminder.mp3 --volume=130 --no-terminal",
        "every:2",
    ]
)

EVENT_COMMANDS: dict[str, list] = _EVENT_COMMANDS


STARTUP_PRESETS: dict[str, StartupPreset] = {
    "startup": StartupPreset(
        schedule=[[15, 2], [13, 5], [25, 5], [25, 5], [25, 0]],
        labels=["polymath", "set-up", "applications"],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_STARTUP,
        description="15m polymath | 2m set-up | 13m applications | 3× 25/5  🎶 CURRENT_ARC",
    ),
    "startup2": StartupPreset(
        schedule=[[20, 4], [15, 5], [25, 5], [25, 5], [25, 0]],
        labels=["polymath", "set-up", "applications"],
        switches=[[3, str(PAST_ARC_FILE)]],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_STARTUP,
        description="20m polymath | 4m set-up | 15m applications  🎶 CURRENT_ARC  →  3× 25/5  🎶 PAST_ARC",
    ),
    "startup3": StartupPreset(
        schedule=[[20, 4], [15, 5], [25, 5], [25, 5], [25, 0]],
        labels=["polymath", "set-up", "applications"],
        switches=[
            [3, str(ARC_SOUNDTRACKS_PAST)],
            [4, str(PAST_ARC_FILE)],
        ],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_STARTUP,
        description="20m polymath | 4m set-up | 15m applications  🎶 CURRENT_ARC  →  25/5  🎶 PAST_ARC  →  2× 25/5  🎶 MUSIC",
    ),
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
        schedule=[[25, 5], [25, 5], [25, 5], [25, 1]],
        labels=["polymath / applications", "wash teeth", "pomodoro", "prepare for tomorrow", "pomodoro", "prepare for tomorrow", "pomodoro", "grab a book to read"],
        switches=[],
        start_dir=str(POMO_DIR / "christmas_2025-I.webm"),
        silence_secs=ARC_SILENCE_SECONDS,
        description="night good one",
        notify_color="blue",
    ),
    "noon": StartupPreset(
        schedule=[[15, 3], [15, 1], [10, 1], [10, 0]],
        labels=["polymath", "set-up", "applications", "time","github issue","time", "fix code"],
        switches=[],
        # start_dir=str(PAST_ARC_FILE),
        start_dir=str(ARC_SOUNDTRACKS_PAST),
        silence_secs=ARC_SILENCE_SECONDS,
        description="noon after eat/nap",
        notify_color="blue",
        commands={
            "session_start": [
                open_zk
            ],  # only once, at the very beginning (plain string)
            "pomodoro_done": [
                [open_personal, 1],  # after 1st pomodoro
                [open_git, 2],  # after 3rd pomodoro
                [open_zed, 3],  # after 4th pomodoro
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
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_SILENCE_SECONDS,
        description="morning winter ritual",
        notify_color="yellow",
        commands={
                    "session_start": [
                        open_zk
                    ],  # only once, at the very beginning (plain string)
                    "pomodoro_done": [
                        [open_personal, 1],  # after 1st pomodoro
                        [open_terminal_riced, 2],  # after 3rd pomodoro
                    ],
                    "pomodoro_begin": [
                        [open_chess, 2],  # before 1st pomodoro
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
        schedule=[[0.2, 0.2], [0.2, 0.2], [0.2, 0.2]],
        labels=["test"],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=0,
        notify_color="green",
        notify_desc="eso tilin",
        notify_title="a la mrd",
        description="asd",
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
}
