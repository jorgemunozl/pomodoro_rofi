"""Rofi menu helpers — pure functions wrapping subprocess calls."""

import subprocess
from pathlib import Path

from pomodoro_lib.config import ROFI_THEME, BACK_LABEL, DURATION_PRESETS, CUSTOM_LABEL, COUNT_OPTIONS


def _rofi(prompt: str, options: list[str], *,
          extra_flags: list[str] | None = None,
          no_custom: bool = False,
          raw_input: str | None = None) -> str | None:
    """Core rofi call. Returns selected string or None on cancel."""
    cmd = ["rofi", "-dmenu", "-p", prompt, "-theme", str(ROFI_THEME)]
    if no_custom:
        cmd.append("-no-custom")
    if extra_flags:
        cmd.extend(extra_flags)

    stdin = raw_input if raw_input is not None else "\n".join(options)
    result = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    out = result.stdout.strip()
    return out if out else None


def rofi_menu(prompt: str, options: list[str], *, no_custom: bool = False) -> str | None:
    """Show a simple text menu. Returns selected string or None."""
    return _rofi(prompt, options, no_custom=no_custom)


def numbered_menu(prompt: str, items: list[str], *, add_back: bool = True) -> str | None:
    """Show numbered list (1. item, 2. item, ...). Returns raw selection or None."""
    lines = [f"{i + 1}. {item}" for i, item in enumerate(items)]
    if add_back:
        lines.append(BACK_LABEL)
    return _rofi(prompt, lines, no_custom=add_back)


def strip_number(selection: str) -> str:
    """Remove leading 'N. ' from a numbered-menu selection."""
    import re
    return re.sub(r"^\d+\.\s*", "", selection)


def pick_task(items: list[str], prompt: str = "Pick task",
              add_back: bool = True) -> str | None:
    """Pick a task from a numbered list."""
    return numbered_menu(prompt, items, add_back=add_back)


def pick_video(videos_dir: Path) -> str | None:
    """Show video grid with thumbnail icons. Returns filename or None."""
    videos = sorted(
        f for f in videos_dir.iterdir()
        if f.suffix in (".mp4", ".webm")
    )
    if not videos:
        return None

    # Build raw input with \0icon\x1f for thumbnails
    parts = []
    for v in videos:
        thumb = videos_dir / f"{v.stem}.jpg"
        if thumb.exists():
            parts.append(f"{v.name}\0icon\x1f{thumb}")
        else:
            parts.append(v.name)
    parts.append(BACK_LABEL)
    raw_input = "\n".join(parts)

    theme_str = (
        "window { width: 800px; }"
        "listview { columns: 2; lines: 2; layout: vertical;"
        " spacing: 20px; padding: 20px; fixed-height: true; }"
        "element { orientation: vertical; padding: 0px; margin: 0px;"
        " border-radius: 0px; border: 0px; }"
        "element selected.normal { background-color: #2e2826;"
        " border: 3px; border-color: #d9523e; }"
        "element-icon { size: 250px; horizontal-align: 0.5;"
        " vertical-align: 0.5; cursor: pointer; }"
        "element-text { enabled: false; }"
    )

    return _rofi(
        "Pick video",
        [],
        extra_flags=["-show-icons", "-theme-str", theme_str],
        raw_input=raw_input,
    )


def pick_duration() -> tuple[int, int] | None:
    """Pick from duration presets + custom. Returns (work_min, break_min) or None."""
    labels = [label for label, _, _ in DURATION_PRESETS] + [CUSTOM_LABEL, BACK_LABEL]
    choice = _rofi("Pick duration", labels)
    if not choice or choice == BACK_LABEL:
        return None

    for label, w, b in DURATION_PRESETS:
        if choice == label:
            return (w, b)

    if choice == CUSTOM_LABEL:
        return _pick_custom_duration()

    return None


def _pick_custom_duration() -> tuple[int, int] | None:
    """Prompt for custom work-break input like '10-5'."""
    choice = _rofi("Work-break (e.g. 10-5)", [BACK_LABEL])
    if not choice or choice == BACK_LABEL:
        return None
    try:
        parts = choice.split("-")
        if len(parts) != 2:
            raise ValueError
        w, b = int(parts[0]), int(parts[1])
        if w <= 0 or b <= 0:
            raise ValueError
        return (w, b)
    except (ValueError, IndexError):
        return None  # caller will re-prompt


def pick_count() -> int | None:
    """Pick number of pomodoros (1-6). Returns count or None."""
    labels = [label for label, _ in COUNT_OPTIONS] + [BACK_LABEL]
    choice = _rofi("How many?", labels)
    if not choice or choice == BACK_LABEL:
        return None
    for label, count in COUNT_OPTIONS:
        if choice == label:
            return count
    return None
