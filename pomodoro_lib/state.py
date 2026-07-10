"""Pomodoro state — dataclass with JSON persistence."""

import json
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class PomodoroState:
    task: str = ""
    end_ts: float = 0.0
    work_min: int = 25
    break_min: int = 5
    total: int = 1
    current: int = 1
    video: str = ""
    phase: str = "work"  # "work" | "break"
    warm_up_secs: int = 0  # video intro seconds before actual focus begins
    audio_only: bool = False  # play mp3 instead of video
    arc_mode: bool = False  # playlist from ARC_SOUNDTRACK with silence gaps
    schedule: list = field(
        default_factory=list
    )  # [[work, break], ...] per pomodoro, empty if uniform
    schedule_labels: list = field(
        default_factory=list
    )  # per-phase labels shown in polybar status

    @property
    def is_active(self) -> bool:
        return self.end_ts > 0

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.end_ts - time.time()))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self)))

    @classmethod
    def load(cls, path: Path) -> "PomodoroState":
        if path.exists():
            try:
                data = json.loads(path.read_text())
                # Only pass keys that exist on the dataclass
                valid_keys = {f.name for f in fields(cls)}
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                return cls(**filtered)
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        return cls()

    def delete(self, path: Path) -> None:
        path.unlink(missing_ok=True)
