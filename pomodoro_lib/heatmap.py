"""Heat map tracker and statistics display for the pomodoro app.

Parses the history file, aggregates pomodoro data by day/week/task,
formats a Unicode heat map grid and statistics summary, and displays
them in a rofi window.
"""

import re
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def parse_history(history_path: Path) -> list[dict[str, Any]]:
    """Parse history file, returning list of dicts with date, task, duration_min, sessions.

    The expected line format is:
        [YYYY-MM-DD HH:MM] task name — Xm × Y
    or (when logged via the "complete pomodoro" handler without extra info):
        [YYYY-MM-DD HH:MM] task name

    Returns an empty list if the file does not exist.
    """
    records: list[dict[str, Any]] = []

    if not history_path.exists():
        return records

    # Regex: capture date, task, and the optional " — Xm × Y" suffix
    pattern = re.compile(
        r"^\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}\] (.+?)(?: — (\d+)m × (\d+))?$"
    )

    for line in history_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        m = pattern.match(line)
        if not m:
            # Skip unparseable lines gracefully
            continue

        date_str = m.group(1)
        task = m.group(2).strip()

        if m.group(3) and m.group(4):
            duration_min = int(m.group(3))
            sessions = int(m.group(4))
        else:
            # Default: a single 25-minute pomodoro
            duration_min = 25
            sessions = 1

        records.append(
            {
                "date": datetime.strptime(date_str, "%Y-%m-%d").date(),
                "task": task,
                "duration_min": duration_min,
                "sessions": sessions,
            }
        )

    return records


def generate_heatmap_data(records: list[dict]) -> dict[str, Any]:
    """Aggregate parsed records into a statistics dictionary.

    Returns a dict with:
        daily          – {date: {"sessions": int, "tasks": {task: count}}}
        weekly         – {iso-week-key: total_sessions}
        per_task       – {task: total_sessions}  (sorted descending)
        current_streak – consecutive days ending today/yesterday with activity
        longest_streak – all-time longest run of consecutive days with activity
        total_this_week
        total_this_month
        total
        avg_per_day
    """
    if not records:
        return {
            "daily": {},
            "weekly": {},
            "per_task": {},
            "current_streak": 0,
            "longest_streak": 0,
            "total_this_week": 0,
            "total_this_month": 0,
            "total": 0,
            "avg_per_day": 0.0,
        }

    # Per-date aggregation
    daily: dict[date, dict] = {}
    per_task: dict[str, int] = defaultdict(int)

    for rec in records:
        d = rec["date"]
        if d not in daily:
            daily[d] = {"sessions": 0, "tasks": defaultdict(int)}
        daily[d]["sessions"] += rec["sessions"]
        daily[d]["tasks"][rec["task"]] += rec["sessions"]
        per_task[rec["task"]] += rec["sessions"]

    today = date.today()

    # Weekly totals (ISO week)
    weekly: dict[str, int] = defaultdict(int)
    for d, info in daily.items():
        iso_year, iso_week, _ = d.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly[week_key] += info["sessions"]

    # This week / this month
    iso_year, iso_week, _ = today.isocalendar()
    this_week_key = f"{iso_year}-W{iso_week:02d}"
    total_this_week = weekly.get(this_week_key, 0)

    total_this_month = sum(
        info["sessions"]
        for d, info in daily.items()
        if d.year == today.year and d.month == today.month
    )

    # Overall totals and daily average
    total = sum(info["sessions"] for info in daily.values())
    num_days = len(daily)
    avg_per_day = round(total / num_days, 1) if num_days > 0 else 0.0

    # ── Streaks ──────────────────────────────────────────────
    sorted_dates = sorted(daily.keys())

    # Longest streak: walk forward counting consecutive days
    longest_streak = 0
    current_run = 0
    prev_date: date | None = None

    for d in sorted_dates:
        if prev_date is None or (d - prev_date).days == 1:
            current_run += 1
        else:
            current_run = 1
        prev_date = d
        if current_run > longest_streak:
            longest_streak = current_run

    # Current streak: walk backwards from the most recent date,
    # but only count it if that date is today or yesterday.
    current_streak = 0
    if sorted_dates:
        last_date = sorted_dates[-1]
        days_since_last = (today - last_date).days
        if days_since_last <= 1:
            d = last_date
            while d in daily:
                current_streak += 1
                d -= timedelta(days=1)

    # Sort per-task by count descending (ties broken alphabetically)
    per_task_sorted = dict(sorted(per_task.items(), key=lambda kv: (-kv[1], kv[0])))

    return {
        "daily": daily,
        "weekly": weekly,
        "per_task": per_task_sorted,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_this_week": total_this_week,
        "total_this_month": total_this_month,
        "total": total,
        "avg_per_day": avg_per_day,
    }


def _intensity(count: int, max_count: int) -> str:
    """Map a count to a Unicode fill character based on ratio of max."""
    if max_count <= 0:
        return "  "
    ratio = count / max_count
    if ratio >= 0.75:
        return "██"  # full
    if ratio >= 0.50:
        return "▓▓"  # medium
    if ratio >= 0.25:
        return "▒▒"  # low
    return "░░"  # very low


def format_heatmap_table(data: dict[str, Any]) -> str:
    """Format a Unicode heat map grid showing weeks with data.

    Columns are days (Mon–Sun), rows are weeks.
    Each cell uses a fill character to indicate relative intensity.
    Only weeks containing data (plus one buffer week before) are shown.
    """
    daily = data.get("daily", {})
    today = date.today()

    if not daily:
        return "No data yet."

    active_dates = list(daily.keys())
    max_sessions = max(info["sessions"] for info in daily.values())

    # Find the range: one week before earliest data through today
    earliest_data = min(active_dates)

    # Align to Monday
    start = earliest_data - timedelta(days=earliest_data.weekday())
    end = today

    lines: list[str] = []

    def _label(d: date) -> str:
        """Short week label like 'Jun  2' or 'Jun  9'."""
        return d.strftime("%b %d").replace(" 0", "  ")

    cursor = start
    while cursor <= end:
        cells: list[str] = []
        has_data_this_week = False
        for i in range(7):
            d = cursor + timedelta(days=i)
            if d > today:
                cells.append("  ")  # future – blank
            elif d in daily:
                count = daily[d]["sessions"]
                cells.append(_intensity(count, max_sessions))
                has_data_this_week = True
            else:
                cells.append("  ")  # no activity

        # Skip this row if it has no activity and isn't the current week
        if not has_data_this_week and cursor < today - timedelta(weeks=1):
            cursor += timedelta(weeks=1)
            continue

        # Show date label on the left
        lines.append(f"{_label(cursor)}  " + " ".join(cells))
        cursor += timedelta(weeks=1)

    # Legend
    lines.append("")
    lines.append(
        "██ ≥75%  ▓▓ ≥50%  ▒▒ ≥25%  ░░ <25%    (of max {}/day)".format(max_sessions)
    )

    return "\n".join(lines)


def format_stats(data: dict[str, Any]) -> str:
    """Format statistics as a human-readable string."""
    lines: list[str] = []

    lines.append(f"Total pomodoros:  {data['total']}")
    lines.append(f"Current streak:   {data['current_streak']} day(s)")
    lines.append(f"Longest streak:   {data['longest_streak']} day(s)")
    lines.append(f"Average per day:  {data['avg_per_day']}")
    lines.append(f"This week:         {data['total_this_week']}")
    lines.append(f"This month:        {data['total_this_month']}")

    per_task = data.get("per_task", {})
    if per_task:
        lines.append("")
        lines.append("── Per task ──")
        # Determine max count for alignment padding
        max_count = max(per_task.values())
        pad = len(str(max_count))
        for task, count in per_task.items():
            lines.append(f"  {count:>{pad}}  {task}")

    return "\n".join(lines)


def show_heatmap_rofi(data: dict[str, Any], history_path: Path) -> None:
    """Display the heat map and statistics in a rofi window.

    The combined output (heat map grid + stats + OK button) is piped
    to ``rofi -dmenu -no-custom``.  The user can select any line (or
    press Escape) to dismiss the window.
    """
    table = format_heatmap_table(data)
    stats = format_stats(data)

    # Build the full display string:
    #   heat map rows
    #   blank line
    #   stats
    #   blank line
    #   OK button
    display_text = table + "\n\n" + stats + "\n\n── OK ──"

    cmd = [
        "rofi",
        "-dmenu",
        "-p",
        "Heatmap",
        "-no-custom",
    ]

    subprocess.run(
        cmd,
        input=display_text,
        capture_output=True,
        text=True,
    )
