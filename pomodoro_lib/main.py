"""CLI entry point — main menu loop, subcommands, and UI flow."""

import re
import sys
import time
from pathlib import Path

from pomodoro_lib.config import (
    BACK_LABEL,
    COUNT_OPTIONS,
    CUSTOM_LABEL,
    DEFAULT_TASKS,
    DURATION_PRESETS,
    HISTORY_FILE,
    INCLUDE_DURATION_FILES,
    PAUSE_FILE,
    POMO_DIR,
    STATE_FILE,
    TASKS_FILE,
    TASKS_UNIQUE,
)
from pomodoro_lib.heatmap import (
    generate_heatmap_data,
    parse_history,
    show_heatmap_rofi,
)
from pomodoro_lib.rofi import (
    numbered_menu,
    pick_video,
    rofi_menu,
    strip_number,
)
from pomodoro_lib.state import PomodoroState
from pomodoro_lib.tasks import TaskManager
from pomodoro_lib.timer import TimerController, notify

# ── Polybar status line ───────────────────────────────────────────────────────


def _status_line() -> str:
    """Polybar status line. Empty string when no session is active."""
    if not STATE_FILE.exists():
        return ""

    state = PomodoroState.load(STATE_FILE)

    if PAUSE_FILE.exists():
        secs = int(PAUSE_FILE.read_text().strip())
        icon = "⏸"
    elif state.phase == "break":
        secs = state.remaining_seconds
        icon = "☕"
    else:
        secs = state.remaining_seconds
        icon = "▶"

    mins = secs // 60
    secs_rem = secs % 60
    return f"{icon} {mins:02d}:{secs_rem:02d}"


# ── Handlers (called from main loop) ──────────────────────────────────────────


def _handle_complete(tm: TaskManager) -> None:
    """Complete pomodoro — pick a task and log it."""
    tasks = tm.all_tasks()
    if not tasks:
        notify("Pomodoro", "No tasks available.")
        return

    choice = numbered_menu("Which pomodoro did you complete?", tasks)
    if choice is None or choice == BACK_LABEL:
        return
    task = strip_number(choice)
    tm.log(task)
    notify("🍅 Pomodoro logged", task)


def _handle_manage(tm: TaskManager) -> None:
    """Manage tasks — two-section display with edit/delete/add."""
    while True:
        everyday = tm.everyday()
        unique = tm.unique()

        # Build menu with section headers
        menu_lines: list[str] = []
        items: list[
            tuple[str, Path]
        ] = []  # (task, file_path) parallel to numbered entries

        idx = 0
        if everyday:
            menu_lines.append("── 📅 Everyday ──")
            for task in everyday:
                idx += 1
                menu_lines.append(f"{idx}. {task}")
                items.append((task, tm.everyday_path))
        if unique:
            menu_lines.append("── 📌 Unique ──")
            for task in unique:
                idx += 1
                menu_lines.append(f"{idx}. {task}")
                items.append((task, tm.unique_path))

        menu_lines.append("➕  Add task")
        menu_lines.append(BACK_LABEL)

        action = rofi_menu("Tasks", menu_lines, no_custom=True)
        if action is None or action == BACK_LABEL:
            break

        if action.startswith("➕"):
            # Add task
            cat_choice = rofi_menu(
                "Add to...", ["📅 Everyday", "📌 Unique", "↩ Cancel"], no_custom=True
            )
            if cat_choice is None or cat_choice == "↩ Cancel":
                continue
            category = "everyday" if "Everyday" in cat_choice else "unique"

            new_task = rofi_menu("New task name", [], no_custom=False)
            if new_task:
                tm.add(new_task, category)
            continue

        # Parse numbered selection
        m = re.match(r"^(\d+)\.", action)
        if not m:
            continue  # section header clicked
        num = int(m.group(1))
        if num < 1 or num > len(items):
            continue

        task, file_path = items[num - 1]

        # Edit / Delete / Cancel
        choice = rofi_menu(
            action, ["✏️  Edit", "🗑  Delete", "↩  Cancel"], no_custom=True
        )
        if choice is None or choice.startswith("↩"):
            continue

        if choice.startswith("✏️"):
            edited = rofi_menu("Edit task", [task], no_custom=False)
            if edited and edited != task:
                tm.edit(task, edited, file_path)
        elif choice.startswith("🗑"):
            tm.delete(task, file_path)


def _handle_new_session(tm: TaskManager, ctrl: TimerController) -> None:
    """New session flow: step-based loop with Back navigation."""
    tasks = tm.all_tasks()
    if not tasks:
        notify("Pomodoro", "No tasks available. Add tasks first.")
        return

    step = 1  # 1=task, 2=video, 3=duration, 4=count
    task = video = ""
    video_name = ""  # scoped for duration-step check
    work_min = break_min = total = 0

    while True:
        if step == 1:
            choice = numbered_menu("Pick task", tasks)
            if choice is None:
                return  # ESC → exit
            if choice == BACK_LABEL:
                return  # back to main menu
            task = strip_number(choice)
            step = 2

        elif step == 2:
            choice = pick_video(POMO_DIR)
            if choice is None:
                return  # ESC → exit
            if choice == BACK_LABEL:
                step = 1
                continue
            video_name = choice
            video = str(POMO_DIR / video_name)
            step = 3

        elif step == 3:
            # Only show duration picker for videos listed in INCLUDE_DURATION_FILES
            if video_name and video_name in INCLUDE_DURATION_FILES:
                labels = [label for label, _, _ in DURATION_PRESETS] + [
                    CUSTOM_LABEL,
                    BACK_LABEL,
                ]
                choice = rofi_menu("Pick duration", labels)
                if choice is None:
                    return  # ESC → exit
                if choice == BACK_LABEL:
                    step = 2
                    continue

                found = False
                for label, w, b in DURATION_PRESETS:
                    if choice == label:
                        work_min, break_min = w, b
                        found = True
                        break

                if not found and choice == CUSTOM_LABEL:
                    while True:
                        custom = rofi_menu("Work-break (e.g. 10-5)", [BACK_LABEL])
                        if custom is None:
                            return  # ESC
                        if custom == BACK_LABEL:
                            break  # back to duration picker
                        try:
                            parts = custom.split("-")
                            if len(parts) != 2:
                                raise ValueError
                            w, b = int(parts[0]), int(parts[1])
                            if w <= 0 or b <= 0:
                                raise ValueError
                            work_min, break_min = w, b
                            found = True
                            break
                        except (ValueError, IndexError):
                            notify(
                                "Pomodoro",
                                "Invalid format. Use e.g. 10-5",
                                urgency="critical",
                            )
                    if not found:
                        continue  # back to duration picker

                if found:
                    step = 4
            else:
                step = 4
                continue

        elif step == 4:
            count_labels = [label for label, _ in COUNT_OPTIONS] + [BACK_LABEL]
            choice = rofi_menu("How many?", count_labels)
            if choice is None:
                return  # ESC → exit
            if choice == BACK_LABEL:
                step = 3
                continue
            for label, c in COUNT_OPTIONS:
                if choice == label:
                    total = c
                    ctrl.start(task, video, work_min, break_min, total)
                    return
            # Invalid → re-prompt


def _handle_status(ctrl: TimerController) -> None:
    """Show current session status with pause/resume/stop actions."""
    state = PomodoroState.load(STATE_FILE)
    if not state.is_active:
        return

    paused = PAUSE_FILE.exists()

    if paused:
        secs = int(PAUSE_FILE.read_text().strip())
    else:
        secs = state.remaining_seconds

    mins = secs // 60
    secs_rem = secs % 60
    end_fmt = (
        time.strftime("%H:%M", time.localtime(state.end_ts))
        if state.end_ts
        else "--:--"
    )

    if state.phase == "break":
        info = f"☕  {state.task}   •   {mins}m {secs_rem}s break   •   session {state.current}/{state.total} next"
    else:
        info = f"▶  {state.task}   •   {mins}m {secs_rem}s left   •   ends {end_fmt}   •   {state.current}/{state.total}"

    toggle_label = "▶  Resume" if paused else "⏸  Pause"

    action = rofi_menu(
        "Pomodoro",
        [
            info,
            toggle_label,
            "🔄  Change task",
            "⏹  Stop all",
            "🔄  Reset everything",
        ],
        no_custom=True,
    )

    if action is None:
        return

    if "Resume" in action:
        ctrl.resume()
    elif "Pause" in action:
        ctrl.pause()
    elif "Change task" in action:
        _handle_change_task(ctrl)
    elif action.startswith("⏹"):
        ctrl.clear_state()
    elif "Reset" in action:
        ctrl.clear_state()
        notify("🍅 Pomodoro", "All state cleared.")


def _handle_change_task(ctrl: TimerController) -> None:
    """Change the task for the current session."""
    state = PomodoroState.load(STATE_FILE)
    if not state.is_active:
        return

    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tasks = tm.all_tasks()
    choice = numbered_menu("Change task", tasks)
    if choice is None or choice == BACK_LABEL:
        return
    new_task = strip_number(choice)
    if new_task:
        state.task = new_task
        state.save(STATE_FILE)
        notify("🍅 Task changed", new_task)


def _handle_heatmap() -> None:
    """Show heat map and statistics in a rofi window."""
    records = parse_history(HISTORY_FILE)
    data = generate_heatmap_data(records)
    show_heatmap_rofi(data, HISTORY_FILE)


# ── Subcommand dispatch ───────────────────────────────────────────────────────


def _run_subcommand(args: list[str]) -> None:
    """Handle polybar subcommands: status, toggle, stop, next."""
    cmd = args[0] if args else ""
    ctrl = TimerController()

    if cmd == "status":
        print(_status_line())
    elif cmd == "toggle":
        ctrl.toggle()
    elif cmd == "stop":
        ctrl.clear_state()
    elif cmd == "next":
        ctrl.skip_phase()
    else:
        print("usage: pomodoro {status|toggle|stop|next}", file=sys.stderr)
        sys.exit(1)


# ── Main menu loop ────────────────────────────────────────────────────────────


def _run_ui() -> None:
    """Launch the rofi main menu and dispatch to handlers."""
    tm = TaskManager(TASKS_FILE, TASKS_UNIQUE, HISTORY_FILE)
    tm.init_defaults(DEFAULT_TASKS)

    ctrl = TimerController(
        on_session_complete=lambda task, w, t: tm.log(task, f"{w}m × {t}")
    )

    while True:
        has_session = STATE_FILE.exists()

        if has_session:
            options = [
                "📊  Current status",
                "▶  New session",
                "✅  Complete pomodoro",
                "📝  Manage tasks",
                "🔥  Heat map",
                "🔄  Reset everything",
            ]
        else:
            options = [
                "▶  New session",
                "✅  Complete pomodoro",
                "📝  Manage tasks",
                "🔥  Heat map",
                "🔄  Reset everything",
            ]

        action = rofi_menu("Pomodoro", options, no_custom=True)
        if action is None:
            sys.exit(0)

        if action.startswith("📊"):
            _handle_status(ctrl)
        elif action.startswith("▶"):
            _handle_new_session(tm, ctrl)
        elif action.startswith("✅"):
            _handle_complete(tm)
        elif action.startswith("📝"):
            _handle_manage(tm)
        elif action.startswith("🔥"):
            _handle_heatmap()
        elif action.startswith("🔄"):
            ctrl.clear_state()
            notify("🍅 Pomodoro", "All state cleared.")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    args = sys.argv[1:]
    if args:
        _run_subcommand(args)
    else:
        _run_ui()


if __name__ == "__main__":
    main()
