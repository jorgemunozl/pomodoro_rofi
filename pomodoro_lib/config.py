"""Paths, presets, and defaults for the pomodoro timer."""

from pathlib import Path
import os

# ── Paths ─────────────────────────────────────────────────────────────────────
XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
POMO_CONFIG = XDG_CONFIG / "pomodoro"
POMO_DIR = Path.home() / "Videos" / "study"

STATE_FILE = Path("/tmp/pomo_state.json")
PID_FILE = Path("/tmp/pomo_mpv.pid")
TIMER_PID_FILE = Path("/tmp/pomo_timer.pid")
PAUSE_FILE = Path("/tmp/pomo_pause")
MPV_SOCKET = Path("/tmp/mpvsocket")

TASKS_FILE = POMO_CONFIG / "tasks"
TASKS_UNIQUE = POMO_CONFIG / "tasks_unique"
HISTORY_FILE = POMO_CONFIG / "history"

ROFI_THEME = Path.home() / ".config" / "rofi" / "pomodoro.rasi"

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
DEFAULT_TASKS = [
    "📐 Real analysis",
    "🤖 VLA model — training",
    "🤖 VLA model — reading",
    "📓 Obsidian notes",
    "🧮 ODEs / coursework",
    "📄 Paper / writing",
    "⚙️  Dotfiles / config",
    "📖 Reading",
    "🎯 Free focus",
]

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
