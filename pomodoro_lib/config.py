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

ARC_SOUNDTRACK = Path.home() / "Videos" / "current_arc"
ARC_SILENCE_SECONDS = 35  # seconds of silence between arc tracks
ARC_STARTUP = 10  # shorter silence for the startup preset

ARC_SOUNDTRACKS_PAST = Path.home() / "Videos" / "past_arc"

REFLECTION_SECS = 60  # silence after final pomodoro before finish sound


PAST_ARC_FILE = Path.home() / "Videos" / "Music"


STATE_FILE = Path("/tmp/pomo_state.json")
PID_FILE = Path("/tmp/pomo_mpv.pid")
TIMER_PID_FILE = Path("/tmp/pomo_timer.pid")
PAUSE_FILE = Path("/tmp/pomo_pause")
BELL_30_PLAYED = Path("/tmp/pomo_bell_30_played")
BELL_BEGIN_PLAYED = Path("/tmp/pomo_bell_begin_played")
WORK_BELL_PLAYED = Path("/tmp/pomo_work_bell_played")
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


@dataclass
class StartupPreset:
    """A pre-configured startup pomodoro session."""

    schedule: list  # [[work_min, break_min], ...]  — last break is ignored
    labels: list  # per-phase polybar labels (shorter than schedule → fallback)
    switches: list  # [[at_pomodoro, path, arc_mode?], ...]
    start_dir: str  # initial ARC directory or video path
    silence_secs: int  # silence between ARC tracks
    description: str  # one-line summary for the terminal


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
    "startup4": StartupPreset(
        schedule=[[20, 4], [15, 5], [25, 5], [25, 5], [25, 5], [25, 0]],
        labels=["polymath", "set-up", "applications"],
        switches=[[3, str(POMO_DIR / "christmas_2025-I.webm"), False]],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_STARTUP,
        description="20m polymath | 4m set-up | 15m applications  🎶 CURRENT_ARC  →  christmas_2025-I.webm  used on the night",
    ),
    "startup5": StartupPreset(
        schedule=[[20, 4], [15, 0]],
        labels=["polymath", "set-up", "applications"],
        switches=[],
        # start_dir=str(PAST_ARC_FILE),
        start_dir=str(ARC_SOUNDTRACKS_PAST),
        silence_secs=ARC_SILENCE_SECONDS,
        description="noon",
    ),
    "startup6": StartupPreset(
        schedule=[[20, 4], [15, 0]],
        labels=["polymath", "set-up", "applications"],
        switches=[],
        start_dir=str(ARC_SOUNDTRACK),
        silence_secs=ARC_SILENCE_SECONDS,
        description="morning",
    ),
}
