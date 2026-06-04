"""Pomodoro state — dataclass with JSON persistence."""

from dataclasses import dataclass, asdict, fields
import json
from pathlib import Path
import time


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
