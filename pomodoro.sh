#!/usr/bin/env bash
# pomodoro.sh — Rofi-powered pomodoro launcher with multi-session auto-loop
# Deps: rofi, mpv, dunst
POMO_DIR="$HOME/Videos/study"
STATE_FILE="/tmp/pomo_state"
PID_FILE="/tmp/pomo_mpv.pid"
TIMER_FILE="/tmp/pomo_timer"
PAUSE_FILE="/tmp/pomo_pause"
MPV_SOCKET="/tmp/mpvsocket"
TASKS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/pomodoro/tasks"
TASKS_UNIQUE="${XDG_CONFIG_HOME:-$HOME/.config}/pomodoro/tasks_unique"
HISTORY_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/pomodoro/history"

# State file format (| delimited):
#   task||end_ts|work_min|break_min|total|current|video|phase
# phase: "work" or "break"

# ── Duration presets (work-break, break = work/5) ────────────────────────────
declare -A DURATION_WORK DURATION_BREAK
DURATION_PRESETS=(
    "25 min focus  ·  5 min break"
    "30 min focus  ·  6 min break"
    "35 min focus  ·  7 min break"
    "40 min focus  ·  8 min break"
    "45 min focus  ·  9 min break"
    "50 min focus  ·  10 min break"
    "⚡ Custom time"
)
for preset in "${DURATION_PRESETS[@]}"; do
    work=$(echo "$preset" | grep -oP '^\d+')
    DURATION_WORK["$preset"]=$work
    DURATION_BREAK["$preset"]=$(( work / 5 ))
done

# ── Default tasks written on first run ───────────────────────────────────────
DEFAULT_TASKS=(
    "📐 Real analysis"
    "🤖 VLA model — training"
    "🤖 VLA model — reading"
    "📓 Obsidian notes"
    "🧮 ODEs / coursework"
    "📄 Paper / writing"
    "⚙️  Dotfiles / config"
    "📖 Reading"
    "🎯 Free focus"
)

mkdir -p "$(dirname "$TASKS_FILE")"
if [[ ! -f "$TASKS_FILE" ]]; then
    printf '%s\n' "${DEFAULT_TASKS[@]}" > "$TASKS_FILE"
fi
# Unique tasks file — create empty if not present
[[ -f "$TASKS_UNIQUE" ]] || : > "$TASKS_UNIQUE"

# ── Library ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/pomo-core.sh"

# ── Main menu ─────────────────────────────────────────────────────────────────
while true; do
    if [[ -f "$STATE_FILE" ]]; then
        action=$(printf "📊  Current status\n▶  New session\n✅  Complete pomodoro\n📝  Manage tasks\n🔄  Reset everything" | \
            rofi_menu "Pomodoro" -no-custom)
    else
        action=$(printf "▶  New session\n✅  Complete pomodoro\n📝  Manage tasks\n🔄  Reset everything" | \
            rofi_menu "Pomodoro" -no-custom)
    fi

    [[ -z "$action" ]] && exit 0
    case "$action" in
        📊*)  show_status        ;;
        ✅*)  complete_pomodoro; continue ;;
        📝*)  manage_tasks;      continue ;;
        🔄*)  reset_all          ;;
    esac

    # ── Step 1: pick task ─────────────────────────────────────────────────────────
    while true; do
        task=$({ cat "$TASKS_FILE" "$TASKS_UNIQUE" 2>/dev/null | num_tasks; printf '↩ Back\n'; } | \
            rofi_menu "Pick task")
        [[ -z "$task" ]] && exit 0
        [[ "$task" == "↩ Back" ]] && continue 2  # back to main menu
        task=$(strip_num "$task")
        break
    done

    # ── Step 2: pick video ───────────────────────────────────────────────────────
    while true; do
        mapfile -t _videos < <(find "$POMO_DIR" -maxdepth 1 \( -name "*.mp4" -o -name "*.webm" \) -printf '%f\n' | sort)
        [[ ${#_videos[@]} -eq 0 ]] && {
            dunstify -u critical "Pomodoro" "No mp4/webm found in $POMO_DIR"
            exit 1
        }

        _rofi_input=""
        for _f in "${_videos[@]}"; do
            _base="${_f%.*}"
            _thumb="$POMO_DIR/$_base.jpg"
            if [[ -f "$_thumb" ]]; then
                _rofi_input+="${_f}\0icon\x1f${_thumb}\n"
            else
                _rofi_input+="${_f}\n"
            fi
        done

        _video_name=$(printf "%b" "${_rofi_input}↩ Back\n" | \
            rofi -dmenu -p "Pick video" \
                 -show-icons \
                 -theme "$HOME/.config/rofi/pomodoro.rasi" \
                 -theme-str '
                     window { width: 800px; }
                     listview { columns: 2; lines: 2; layout: vertical; spacing: 20px; padding: 20px; fixed-height: true; }
                     element { orientation: vertical; padding: 0px; margin: 0px; border-radius: 0px; border: 0px; }
                     element selected.normal { background-color: #2e2826; border: 3px; border-color: #d9523e; }
                     element-icon { size: 250px; horizontal-align: 0.5; vertical-align: 0.5; cursor: pointer; }
                     element-text { enabled: false; }
                 ')

        [[ -z "$_video_name" ]] && exit 0
        [[ "$_video_name" == "↩ Back" ]] && continue  # back to step 1
        video="$POMO_DIR/$_video_name"
        break
    done

    # ── Step 3: pick duration preset ──────────────────────────────────────────────
    while true; do
        duration_choice=$(printf '%s\n↩ Back\n' "${DURATION_PRESETS[@]}" | rofi_menu "Pick duration")
        [[ -z "$duration_choice" ]] && exit 0
        [[ "$duration_choice" == "↩ Back" ]] && continue  # back to step 2

        if [[ "$duration_choice" == "⚡ Custom time" ]]; then
            while true; do
                custom_input=$(printf '↩ Back\n' | rofi_menu "Work-break (e.g. 10-5)")
                [[ -z "$custom_input" ]] && exit 0
                [[ "$custom_input" == "↩ Back" ]] && break  # back to duration picker
                work_min="${custom_input%-*}"
                break_min="${custom_input#*-}"
                [[ "$work_min" =~ ^[0-9]+$ && "$break_min" =~ ^[0-9]+$ && "$work_min" -gt 0 && "$break_min" -gt 0 ]] && break
                dunstify -u critical "Pomodoro" "Invalid format. Use e.g. 10-5"
            done
            [[ "$custom_input" == "↩ Back" ]] && continue  # back to duration picker
        else
            work_min=${DURATION_WORK["$duration_choice"]}
            break_min=${DURATION_BREAK["$duration_choice"]}
        fi
        break
    done

    # ── Step 4: how many pomodoros? ───────────────────────────────────────────────
    while true; do
        count_choice=$(printf "1 pomodoro\n2 pomodoros\n3 pomodoros\n4 pomodoros\n5 pomodoros\n6 pomodoros\n↩ Back" | rofi_menu "How many?")
        [[ -z "$count_choice" ]] && exit 0
        [[ "$count_choice" == "↩ Back" ]] && continue  # back to step 3
        case "$count_choice" in
            "1 pomodoro")  total=1 ;;
            "2 pomodoros") total=2 ;;
            "3 pomodoros") total=3 ;;
            "4 pomodoros") total=4 ;;
            "5 pomodoros") total=5 ;;
            "6 pomodoros") total=6 ;;
            *)             continue ;;
        esac
        break
    done

    kill_session
    start_timer "$task" "$video" "$work_min" "$break_min" "$total"
    exit 0
done
