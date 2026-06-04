# pomo-core.sh — shared functions for pomodoro.sh
# Sourced by pomodoro.sh; expects config variables to be set.

# ── Helpers ───────────────────────────────────────────────────────────────────
rofi_menu() {   # rofi_menu <prompt> [extra_flags...] — reads stdin
    rofi -dmenu -p "$1" -theme "$HOME/.config/rofi/pomodoro.rasi" "${@:2}"
}

num_tasks() {
    # Reads stdin, outputs numbered lines: "1. line1\n2. line2\n..."
    local i=1
    while IFS= read -r line; do
        printf '%d. %s\n' "$i" "$line"
        ((i++))
    done
}

strip_num() {
    sed 's/^[0-9]\+\. //' <<< "$1"
}

parse_state() {
    # Reads STATE_FILE → TASK END_TS WORK BRK TOTAL CUR VIDEO PHASE
    IFS='|' read -r TASK _ END_TS WORK BRK TOTAL CUR VIDEO PHASE < "$STATE_FILE"
    END_TS="${END_TS:-0}"
    WORK="${WORK:-25}"
    BRK="${BRK:-5}"
    TOTAL="${TOTAL:-1}"
    CUR="${CUR:-1}"
    VIDEO="${VIDEO:-}"
    PHASE="${PHASE:-work}"
}

write_state() {
    printf '%s||%s|%s|%s|%s|%s|%s|%s' "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" > "$STATE_FILE"
}

is_paused() { [[ -f "$PAUSE_FILE" ]]; }

kill_mpv() {
    [[ -f "$PID_FILE" ]] && kill "$(cat "$PID_FILE")" 2>/dev/null
    rm -f "$PID_FILE" "$MPV_SOCKET"
}

kill_timer() {
    local pid
    [[ -f "$TIMER_FILE" ]] && {
        pid=$(cat "$TIMER_FILE")
        # Don't kill ourselves — we're called from the timer's own callback
        [[ "$pid" != "$BASHPID" ]] && kill "$pid" 2>/dev/null
    }
    rm -f "$TIMER_FILE"
}

kill_session() {
    kill_timer
    kill_mpv
    rm -f "$STATE_FILE" "$PAUSE_FILE"
}

reset_all() {
    kill_session
    pomodoro stop 2>/dev/null  # also stop polybar daemon if running
    dunstify -u low -i timer "🍅 Pomodoro" "All state cleared."
    exit 0
}

log_pomodoro() {
    # $1 = task name, [$2 = extra info like "25m × 3"]
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M')" "$1${2:+ — $2}" >> "$HISTORY_FILE"
}

complete_pomodoro() {
    local task
    task=$({ cat "$TASKS_FILE" "$TASKS_UNIQUE" 2>/dev/null | num_tasks; printf '↩ Back\n'; } | \
        rofi_menu "Which pomodoro did you complete?")
    [[ -z "$task" || "$task" == "↩ Back" ]] && return
    task=$(strip_num "$task")
    log_pomodoro "$task"
    dunstify -u low -i timer "🍅 Pomodoro logged" "$task"
    exit 0
}

mpv_cmd() { echo "$1" | socat - "$MPV_SOCKET" 2>/dev/null; }

start_mpv() {
    local video="$1"
    if [[ -n "$video" ]] && [[ -f "$video" ]]; then
        mpv --loop --no-terminal --fullscreen --panscan=1.0 --no-video-osd \
            --input-ipc-server="$MPV_SOCKET" "$video" &
        echo $! > "$PID_FILE"
    fi
}

# ── Pause / resume ────────────────────────────────────────────────────────────
pause_session() {
    is_paused && return
    parse_state
    local secs_left=$(( END_TS - $(date +%s) ))
    echo "$secs_left" > "$PAUSE_FILE"
    kill_timer
    dunstify -u low -i timer "🍅 Pomodoro paused" "$(( secs_left / 60 ))m left"
}

resume_session() {
    is_paused || return
    local secs_left; secs_left=$(cat "$PAUSE_FILE")
    rm -f "$PAUSE_FILE"
    parse_state
    local new_end=$(( $(date +%s) + secs_left ))
    write_state "$TASK" "$new_end" "$WORK" "$BRK" "$TOTAL" "$CUR" "$VIDEO" "$PHASE"
    (
        sleep "$secs_left"
        on_phase_end
    ) &
    echo $! > "$TIMER_FILE"
    dunstify -u low -i timer "🍅 Pomodoro resumed" \
        "$(( secs_left / 60 ))m left — ends $(date -d @$new_end +%H:%M)"
}

# ── Phase transitions ─────────────────────────────────────────────────────────
on_phase_end() {
    kill_timer
    parse_state 2>/dev/null || return
    case "$PHASE" in
        work)  on_work_end ;;
        break) on_break_end ;;
    esac
}

on_work_end() {
    local next=$(( CUR + 1 ))
    if (( next > TOTAL )); then
        dunstify -u critical -i timer "🍅 All done!" \
            "\"$TASK\" — $TOTAL session(s) of ${WORK}min complete!"
        log_pomodoro "$TASK" "${WORK}m × $TOTAL"
        kill_session
        return
    fi
    local break_end=$(( $(date +%s) + BRK * 60 ))
    write_state "$TASK" "$break_end" "$WORK" "$BRK" "$TOTAL" "$next" "$VIDEO" "break"
    dunstify -u critical -i timer "🍅 Session $CUR/$TOTAL done!" \
        "\"$TASK\" — ${WORK}min complete.\n☕ ${BRK}min break — session $next/$TOTAL next."
    (
        sleep $(( BRK * 60 ))
        on_phase_end
    ) &
    echo $! > "$TIMER_FILE"
}

on_break_end() {
    local work_end=$(( $(date +%s) + WORK * 60 ))
    write_state "$TASK" "$work_end" "$WORK" "$BRK" "$TOTAL" "$CUR" "$VIDEO" "work"
    dunstify -u critical -i timer "🍅 Break over!" \
        "Starting session $CUR/$TOTAL — ${WORK}min focus."
    (
        sleep $(( WORK * 60 ))
        on_phase_end
    ) &
    echo $! > "$TIMER_FILE"
}

# ── Status window ─────────────────────────────────────────────────────────────
show_status() {
    parse_state
    local paused=false secs_left mins_left secs_rem end_fmt info

    if is_paused; then
        paused=true
        secs_left=$(cat "$PAUSE_FILE")
    else
        secs_left=$(( END_TS - $(date +%s) ))
    fi
    mins_left=$(( secs_left / 60 ))
    secs_rem=$(( secs_left % 60 ))
    end_fmt=$(date -d "@$END_TS" +%H:%M 2>/dev/null || echo "--:--")

    if [[ "$PHASE" == "break" ]]; then
        info="☕  $TASK   •   ${mins_left}m ${secs_rem}s break   •   session $CUR/$TOTAL next"
    else
        info="▶  $TASK   •   ${mins_left}m ${secs_rem}s left   •   ends $end_fmt   •   $CUR/$TOTAL"
    fi

    local toggle_label
    $paused && toggle_label="▶  Resume" || toggle_label="⏸  Pause"

    local action
    action=$(printf "%s\n%s\n%s\n%s\n%s" \
        "$info" \
        "$toggle_label" \
        "🔄  Change task" \
        "⏹  Stop all" \
        "🔄  Reset everything" | \
        rofi_menu "Pomodoro" -no-custom)

    case "$action" in
        *"Resume"*)      resume_session ;;
        *"Pause"*)       pause_session  ;;
        *"Change task"*) change_task    ;;
        ⏹*)              kill_session   ;;
        🔄*Reset*)        reset_all      ;;
    esac
    exit 0
}

change_task() {
    parse_state 2>/dev/null || return
    mapfile -t _tasks < "$TASKS_FILE"
    local new_task
    new_task=$(printf '%s\n' "${_tasks[@]}" | num_tasks | rofi_menu "Change task")
    new_task=$(strip_num "$new_task")
    [[ -z "$new_task" ]] && return
    write_state "$new_task" "$END_TS" "$WORK" "$BRK" "$TOTAL" "$CUR" "$VIDEO" "$PHASE"
    dunstify -u low -i timer "🍅 Task changed" "$new_task"
}

# ── Task management ───────────────────────────────────────────────────────────
manage_tasks() {
    while true; do
        mapfile -t _everyday < "$TASKS_FILE"
        mapfile -t _unique  < "$TASKS_UNIQUE"

        # Build menu with two sections; track index → (item, file)
        local _menu="" _idx=0
        declare -a _task_items=() _task_files=()

        if [[ ${#_everyday[@]} -gt 0 ]]; then
            _menu+="── 📅 Everyday ──\n"
            for _t in "${_everyday[@]}"; do
                ((_idx++))
                _task_items[_idx]="$_t"
                _task_files[_idx]="$TASKS_FILE"
                _menu+="$_idx. $_t\n"
            done
        fi
        if [[ ${#_unique[@]} -gt 0 ]]; then
            _menu+="── 📌 Unique ──\n"
            for _t in "${_unique[@]}"; do
                ((_idx++))
                _task_items[_idx]="$_t"
                _task_files[_idx]="$TASKS_UNIQUE"
                _menu+="$_idx. $_t\n"
            done
        fi
        _menu+="➕  Add task\n↩ Back\n"

        local action
        action=$(printf "%b" "$_menu" | rofi_menu "Tasks" -no-custom)
        [[ -z "$action" || "$action" == "↩ Back" ]] && break

        case "$action" in
            ➕*Add*)
                local category target
                category=$(printf "📅 Everyday\n📌 Unique\n↩ Cancel" | rofi_menu "Add to..." -no-custom)
                case "$category" in
                    📅*) target="$TASKS_FILE" ;;
                    📌*) target="$TASKS_UNIQUE" ;;
                    *)   continue ;;
                esac
                local new_task
                new_task=$(printf '' | rofi_menu "New task name")
                [[ -n "$new_task" ]] && echo "$new_task" >> "$target"
                ;;
            *)
                local _num; _num=$(echo "$action" | grep -oP '^\d+')
                local _task="${_task_items[$_num]}"
                local _file="${_task_files[$_num]}"
                [[ -z "$_task" ]] && continue  # section header clicked

                local choice
                choice=$(printf "✏️  Edit\n🗑  Delete\n↩  Cancel" | \
                    rofi_menu "$action" -no-custom)
                case "$choice" in
                    ✏️*Edit*)
                        local edited
                        edited=$(printf '%s' "$_task" | rofi_menu "Edit task")
                        [[ -n "$edited" ]] && {
                            grep -vxF "$_task" "$_file" > "${_file}.tmp"
                            printf '%s\n' "$edited" >> "${_file}.tmp"
                            mv "${_file}.tmp" "$_file"
                        }
                        ;;
                    🗑*Delete*)
                        grep -vxF "$_task" "$_file" > "${_file}.tmp" && \
                            mv "${_file}.tmp" "$_file"
                        ;;
                esac
                ;;
        esac
    done
    return
}

# ── Start timer ───────────────────────────────────────────────────────────────
start_timer() {
    local task="$1" video="$2" work_min="$3" break_min="$4" total="$5"
    local end_ts=$(( $(date +%s) + work_min * 60 ))
    write_state "$task" "$end_ts" "$work_min" "$break_min" "$total" "1" "$video" "work"

    i3-msg "workspace --no-auto-back-and-forth pomodoro 🍅"
    start_mpv "$video"
    (
        sleep $(( work_min * 60 ))
        on_phase_end
    ) &
    echo $! > "$TIMER_FILE"
    dunstify -u normal -i timer "🍅 Pomodoro started" \
        "$task — session 1/$total\n${work_min}min — $(date -d @$end_ts +%H:%M)"
}
