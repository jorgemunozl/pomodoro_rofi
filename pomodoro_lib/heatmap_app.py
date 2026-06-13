"""Textual interactive heatmap — GitHub-style contribution graph.

Launch with:
    python -m pomodoro_lib.heatmap_app

Click any day cell to see a breakdown of pomodoros done that day.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Footer, Header, Label, Static

from pomodoro_lib.config import HISTORY_FILE
from pomodoro_lib.heatmap import generate_heatmap_data, parse_history

# ── Constants ─────────────────────────────────────────────────────────────────

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# GitHub dark-mode green scale
LEVEL_0 = "#161b22"  # no activity / grid background
GREEN_LEVELS = ["#0e4429", "#006d32", "#26a641", "#39d353"]

GREEN_RATIO_CUTOFFS = [0.0, 0.25, 0.50, 0.75]  # lower bounds


def _intensity_color(sessions: int, max_sessions: int) -> str:
    """Map session count to a GitHub-style green hex color."""
    if max_sessions <= 0 or sessions <= 0:
        return LEVEL_0
    ratio = sessions / max_sessions
    # find the highest cutoff this ratio exceeds
    idx = 0
    for i in range(len(GREEN_RATIO_CUTOFFS) - 1, -1, -1):
        if ratio >= GREEN_RATIO_CUTOFFS[i]:
            idx = i
            break
    return GREEN_LEVELS[idx]


def _compute_grid(data: dict) -> tuple[list[date], dict[date, Any]]:
    """Return (week_start_dates, day_info) sorted from past to present."""
    daily: dict[date, Any] = data.get("daily", {})
    if not daily:
        return [], {}

    today = date.today()
    earliest = min(daily.keys())
    start = earliest - timedelta(days=earliest.weekday())  # align to Monday

    weeks: list[date] = []
    cursor = start
    while cursor <= today:
        weeks.append(cursor)
        cursor += timedelta(weeks=1)
    return weeks, daily


def _month_labels(weeks: list[date]) -> list[str]:
    """One label per week; empty string if same month as previous week."""
    labels: list[str] = []
    prev = -1
    for w in weeks:
        if w.month != prev:
            labels.append(w.strftime("%b"))
            prev = w.month
        else:
            labels.append("")
    return labels


# ── Messages ──────────────────────────────────────────────────────────────────


class DaySelected(Message):
    """Sent when a day cell is clicked."""

    def __init__(self, day_date: date, sessions: int, tasks: dict[str, int]) -> None:
        self.day_date = day_date
        self.sessions = sessions
        self.tasks = tasks
        super().__init__()


# ── DayCell widget ────────────────────────────────────────────────────────────


class DayCell(Static):
    """A single clickable day cell in the contribution grid."""

    def __init__(
        self,
        day_date: date,
        sessions: int,
        tasks: dict[str, int],
        max_sessions: int,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.day_date = day_date
        self.sessions = sessions
        self.tasks = tasks
        self.max_sessions = max_sessions

    def on_mount(self) -> None:
        color = _intensity_color(self.sessions, self.max_sessions)
        self.styles.background = color
        self.styles.width = 3
        self.styles.height = 1
        self.styles.margin = (0, 0)
        self.styles.min_width = 3
        self.styles.content_align_horizontal = "center"
        self.styles.content_align_vertical = "middle"
        self.update(" ")

    def on_click(self) -> None:
        self.post_message(DaySelected(self.day_date, self.sessions, self.tasks))

    def on_mouse_enter(self) -> None:
        self.styles.tint = "#ffffff30"

    def on_mouse_leave(self) -> None:
        self.styles.tint = ""


class DayLabel(Static):
    """Row label for a day of the week."""

    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(name, **kwargs)

    def on_mount(self) -> None:
        self.styles.width = 4
        self.styles.height = 1
        self.styles.content_align_horizontal = "right"
        self.styles.content_align_vertical = "middle"
        self.styles.padding = (0, 1)
        self.styles.color = "#8b949e"


# ── Stats Panel ───────────────────────────────────────────────────────────────


class StatsPanel(Static):
    """Shows aggregated statistics."""

    def __init__(self, data: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._data = data

    def on_mount(self) -> None:
        self.styles.padding = (1, 2)
        self.styles.overflow_y = "auto"
        self._render()

    def _render(self) -> None:
        d = self._data
        lines = [
            "[bold white]📊 Statistics[/]",
            "",
            f"Total pomodoros:  [green]{d['total']}[/]",
            f"Current streak:   [green]{d['current_streak']}[/] day(s)",
            f"Longest streak:   [green]{d['longest_streak']}[/] day(s)",
            f"Avg per day:      [green]{d['avg_per_day']}[/]",
            f"This week:        [green]{d['total_this_week']}[/]",
            f"This month:       [green]{d['total_this_month']}[/]",
        ]
        per_task = d.get("per_task", {})
        if per_task:
            lines.append("")
            lines.append("[bold white]── Per task ──[/]")
            for task, count in per_task.items():
                lines.append(f"  [green]{count}[/]  {task}")
        self.update("\n".join(lines))


# ── Detail Panel ──────────────────────────────────────────────────────────────


class DetailPanel(Static):
    """Shows details for a clicked day."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._empty = True

    def on_mount(self) -> None:
        self.styles.padding = (1, 2)
        self.styles.min_height = 5
        self.styles.height = "auto"
        self.styles.dock = "bottom"
        self.styles.border = ("solid", "#30363d")
        self.styles.display = "none"
        self._show_empty()

    def _show_empty(self) -> None:
        self.update("[dim]Click a day in the grid to see details[/]")

    def show_day(self, day_date: date, sessions: int, tasks: dict[str, int]) -> None:
        self.styles.display = "block"
        lines = [
            f"[bold white]📅 {day_date}[/]",
            f"Pomodoros: [green]{sessions}[/]",
        ]
        if tasks:
            lines.append("")
            lines.append("[bold]Tasks done:[/]")
            for task, count in sorted(tasks.items(), key=lambda x: -x[1]):
                lines.append(f"  [green]{count}[/]  {task}")
        self.update("\n".join(lines))
        self._empty = False

    def clear(self) -> None:
        self.styles.display = "none"
        self._empty = True


# ── Legend ────────────────────────────────────────────────────────────────────


class Legend(Static):
    """Color legend for the heatmap."""

    def __init__(self, max_sessions: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self._max = max_sessions

    def on_mount(self) -> None:
        self.styles.padding = (0, 2)
        dots = "".join(f"[on {c}] [/]" for c in [LEVEL_0] + GREEN_LEVELS)
        self.update(f"Less  {dots}  More    (max {self._max}/day)")


# ── Main grid ─────────────────────────────────────────────────────────────────


class ContributionGrid(Static):
    """The main contribution graph grid."""

    def __init__(self, data: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._data = data
        self._weeks: list[date] = []
        self._daily: dict[date, Any] = {}
        self._max_sessions: int = 0
        self._cells: dict[date, DayCell] = {}

    def on_mount(self) -> None:
        self._weeks, self._daily = _compute_grid(self._data)
        self._max_sessions = max(
            (info["sessions"] for info in self._daily.values()), default=0
        )
        self._build_grid()

    def _build_grid(self) -> None:
        if not self._weeks:
            self.update("[yellow]No data yet. Start using pomodoro![/]")
            return

        month_lbls = _month_labels(self._weeks)

        # Build rows
        rows: list[list[Widget]] = []

        # ── Header row (month labels) ──
        header_widgets: list[Widget] = [DayLabel("")]
        for ml in month_lbls:
            lbl = Static(ml, id=f"month-{ml}")
            lbl.styles.width = 3
            lbl.styles.content_align_horizontal = "center"
            lbl.styles.color = "#8b949e"
            header_widgets.append(lbl)
        rows.append(header_widgets)

        # ── Day rows ──
        for dow in range(7):
            row_widgets: list[Widget] = [DayLabel(DAY_NAMES[dow])]
            for week_start in self._weeks:
                d = week_start + timedelta(days=dow)
                today = date.today()
                if d > today:
                    # Empty placeholder
                    cell = Static("")
                    cell.styles.width = 3
                    cell.styles.height = 1
                else:
                    info = self._daily.get(d)
                    sessions = info["sessions"] if info else 0
                    tasks = dict(info["tasks"]) if info and info.get("tasks") else {}
                    cell = DayCell(
                        d,
                        sessions,
                        tasks,
                        self._max_sessions,
                        id=f"cell-{d.isoformat()}",
                    )
                    self._cells[d] = cell
                row_widgets.append(cell)
            rows.append(row_widgets)

        v = Vertical()
        v.styles.overflow_y = "auto"
        for r_idx, row in enumerate(rows):
            h = Horizontal(*row)
            h.styles.height = 1
            v.mount(h)

        self.mount(v)


class HeatmapApp(App):
    """Textual heatmap app — GitHub-style contribution graph."""

    CSS = """
    HeatmapApp {
        background: #0d1117;
    }

    Screen {
        background: #0d1117;
    }

    Container#main-layout {
        layout: horizontal;
        height: 100%;
    }

    Container#grid-area {
        width: 1fr;
        height: 100%;
        overflow-y: auto;
        padding: 1 2;
    }

    Container#sidebar {
        width: 36;
        height: 100%;
        dock: right;
        border-left: solid #30363d;
        background: #161b22;
    }

    DetailPanel {
        background: #161b22;
        color: #c9d1d9;
    }

    StatsPanel {
        background: #161b22;
        color: #c9d1d9;
    }

    DayCell:hover {
        tint: #ffffff30;
    }

    DayCell:focus {
        border: solid #58a6ff;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, history_path: Path = HISTORY_FILE, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history_path = history_path
        self._load_data()

    def on_mount(self) -> None:
        self.title = "Pomodoro Heatmap"

    def _load_data(self) -> None:
        records = parse_history(self._history_path)
        self._data = generate_heatmap_data(records)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="main-layout"):
            with Container(id="grid-area"):
                if not self._data.get("daily"):
                    yield Label("[yellow]No data yet. Start using pomodoro![/]")
                else:
                    yield ContributionGrid(self._data)
                    yield DetailPanel()

            with Vertical(id="sidebar"):
                yield StatsPanel(self._data)

        # Legend below the grid
        max_s = max(
            (info["sessions"] for info in self._data.get("daily", {}).values()),
            default=0,
        )
        yield Legend(max_s)
        yield Footer()

    def on_day_selected(self, message: DaySelected) -> None:
        """Handle a day cell click."""
        try:
            detail = self.query_one(DetailPanel)
            detail.show_day(message.day_date, message.sessions, message.tasks)
        except NoMatches:
            pass

    def action_refresh(self) -> None:
        """Reload history and rebuild the grid."""
        self._load_data()
        grid = self.query_one(ContributionGrid)
        grid.remove()
        self.mount(ContributionGrid(self._data))
        stats = self.query_one(StatsPanel)
        stats.remove()
        self.mount(StatsPanel(self._data))
        try:
            detail = self.query_one(DetailPanel)
            detail.clear()
        except NoMatches:
            pass


def main() -> None:
    app = HeatmapApp()
    app.run()


if __name__ == "__main__":
    main()
