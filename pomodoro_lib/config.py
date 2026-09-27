from dataclasses import dataclass

from pomodoro_lib.commands import CommandsBuilder
from pomodoro_lib.constants import (
    PUSH_UPS_FILE,
    SOUNDS_DIR,
    StartupPreset,
)
from pomodoro_lib.constants import (
    STARTUP_PRESETS_REGISTRY as STARTUP_PRESETS,
)


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
        steps=[
            "noon_after_eat",
            ["shinjuku2.mp4", "study.mp4", "mine_2025_II.webm"],
        ],
        description="covering the second peak of work",
    ),
}

ANNOUNCE_TIME_ON_DONE: bool = False

_SAY_TIME = (
    f'F="{SOUNDS_DIR}/say_time_$(date +%I_%M_%p).mp3"; '
    '[ -f "$F" ] || gtts-cli "The time is $(date '
    "'+%I:%M %p')\""
    ' --output "$F"; '
    'mpv "$F" --volume=130 --no-terminal'
)
_PUSH_UPS_CMD = f"mpv {PUSH_UPS_FILE} --volume=130 --no-terminal"

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
