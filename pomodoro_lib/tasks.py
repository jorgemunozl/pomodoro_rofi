"""Task management — everyday tasks, unique tasks, and history."""

from pathlib import Path
from datetime import datetime


class TaskManager:
    def __init__(self, everyday_path: Path, unique_path: Path, history_path: Path):
        self.everyday_path = everyday_path
        self.unique_path = unique_path
        self.history_path = history_path

    # ── Reading ───────────────────────────────────────────────────────────────
    def _read_lines(self, path: Path) -> list[str]:
        if path.exists():
            return [
                line.strip()
                for line in path.read_text().splitlines()
                if line.strip()
            ]
        return []

    def _write_lines(self, path: Path, lines: list[str]) -> None:
        path.write_text("\n".join(lines) + "\n")

    def everyday(self) -> list[str]:
        return self._read_lines(self.everyday_path)

    def unique(self) -> list[str]:
        return self._read_lines(self.unique_path)

    def all_tasks(self) -> list[str]:
        return self.everyday() + self.unique()

    # ── Writing ───────────────────────────────────────────────────────────────
    def add(self, task: str, category: str = "everyday") -> None:
        target = self.everyday_path if category == "everyday" else self.unique_path
        lines = self._read_lines(target)
        lines.append(task)
        self._write_lines(target, lines)

    def edit(self, old_task: str, new_task: str, file_path: Path) -> bool:
        lines = self._read_lines(file_path)
        try:
            idx = lines.index(old_task)
            lines[idx] = new_task
            self._write_lines(file_path, lines)
            return True
        except ValueError:
            return False

    def delete(self, task: str, file_path: Path) -> bool:
        lines = self._read_lines(file_path)
        new_lines = [l for l in lines if l != task]
        if len(new_lines) != len(lines):
            self._write_lines(file_path, new_lines)
            return True
        return False

    def find_file(self, task: str) -> Path | None:
        if task in self.everyday():
            return self.everyday_path
        if task in self.unique():
            return self.unique_path
        return None

    # ── History ───────────────────────────────────────────────────────────────
    def log(self, task: str, extra: str = "") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{timestamp}] {task}"
        if extra:
            entry += f" — {extra}"
        with open(self.history_path, "a") as f:
            f.write(entry + "\n")

    # ── Init ──────────────────────────────────────────────────────────────────
    def init_defaults(self, defaults: list[str]) -> None:
        self.everyday_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.everyday_path.exists():
            self._write_lines(self.everyday_path, defaults)
        if not self.unique_path.exists():
            self.unique_path.touch()
