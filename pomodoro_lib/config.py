from dataclasses import dataclass, field

from pomodoro_lib.commands import CommandsBuilder
from pomodoro_lib.constants import (
    PUSH_UPS_FILE,
    SOUNDS_DIR,
    StartupPreset,
)
from pomodoro_lib.constants import (
    HOUR_PRESETS,
)
from pomodoro_lib.constants import (
    STARTUP_PRESETS_REGISTRY as STARTUP_PRESETS,
)


@dataclass
class Chain:
    steps: list
    description: str = ""
    # Random chain: when set, ``random_count`` steps are sampled from this
    # pool (no repeats) every time the chain runs, instead of ``steps``.
    random_pool: list = field(default_factory=list)
    random_count: int = 0


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
        steps=[
            "noon_after_eat",
            ["shinjuku2.mp4", "study.mp4", "mine_2025_II.webm"],
        ],
        description="covering the second peak of work",
    ),
    # ── ~5 h: ritual → golden (25/5 × 4) → 1 h lofi → 1 h steven ──────────
    "five_hours": Chain(
        steps=[
            "morning_ritual_spring_thinker",
            "golden.webm",
            "hour_lofi",
            "hour_steven",
        ],
        description="5 h: morning ritual, golden, lofi 50-10, steven 50-10",
    ),
    # ── ~3 h: energyzed soundtracks around a dr hour ───────────────────────
    "deep_focus": Chain(
        steps=[
            "hour_current_arc_energyzed",
            "hour_dr",
            "hour_music_ost_energyzed",
        ],
        description="3 h: energyzed arc, dr, energyzed ost",
    ),
    # ── ~4 h: every soundtrack flavour, calm → energyzed ───────────────────
    "soundtrack_marathon": Chain(
        steps=[
            "hour_music_ost",
            "hour_current_arc",
            "hour_music_ost_energyzed",
            "hour_current_arc_energyzed",
        ],
        description="4 h: ost, arc, then their energyzed versions",
    ),
    # ── ~3 h: mine video (25/5 × 4) then a lofi hour ───────────────────────
    "mine_lofi": Chain(
        steps=["mine_2025_II.webm", "hour_lofi"],
        description="3 h: mine video pomodoros, then lofi 50-10",
    ),
    # ── ~2 h: calm evening ─────────────────────────────────────────────────
    "evening_calm": Chain(
        steps=["hour_nate", "hour_darkacademia"],
        description="2 h: nate, then dark academia",
    ),
    # ── ~4 h: four random music hours, re-drawn on every run ───────────────
    "random_hours": Chain(
        steps=[],
        description="4 h: four random one-hour music blocks",
        random_pool=list(HOUR_PRESETS),
        random_count=4,
    ),
}

ANNOUNCE_TIME_ON_DONE: bool = False

_SAY_TIME = (
    f'F="{SOUNDS_DIR}/say_time_$(date +%I_%M_%p).mp3"; '
    '[ -f "$F" ] || gtts-cli "The time is $(date '
    "'+%I:%M %p')\""
    ' --output "$F"; '
    'mpv "$F" --no-terminal'
)
_PUSH_UPS_CMD = f"mpv {PUSH_UPS_FILE} --no-terminal"

cmds = CommandsBuilder()

if ANNOUNCE_TIME_ON_DONE:
    cmds.on("session_start").always(_PUSH_UPS_CMD)
    cmds.on("pomodoro_done").every(2).run(_PUSH_UPS_CMD)
    cmds.on("pomodoro_done").always(_SAY_TIME)
    cmds.on("session_start").once().run(_SAY_TIME)

EVENT_COMMANDS = cmds.build()

__all__ = [
    "ANNOUNCE_TIME_ON_DONE",
    "CHAINS",
    "EVENT_COMMANDS",
    "STARTUP_PRESETS",
    "Chain",
    "StartupPreset",
]
