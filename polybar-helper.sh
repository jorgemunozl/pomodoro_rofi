#!/usr/bin/env bash
# pomodoro — polybar helper + minimal daemon
# Also bridges with pomodoro.sh (Rofi launcher) via /tmp/pomo_state
# State format: task||end_ts|work_min|break_min|total|current|video|phase
# usage: pomodoro {start|stop|toggle|next|status}

WORK=25
SHORT=5
LONG=15
LONG_EVERY=4

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/pomodoro"
STATE="$CACHE/state"
DAEMON_PID="$CACHE/pid"
DAEMON_PAUSE="$CACHE/paused"

# ── Rofi session (pomodoro.sh) state files ────────────────────────────────────
ROFI_STATE="/tmp/pomo_state"
ROFI_PID="/tmp/pomo_mpv.pid"
ROFI_TIMER="/tmp/pomo_timer"
ROFI_PAUSE="/tmp/pomo_pause"
MPV_SOCKET="/tmp/mpvsocket"

mkdir -p "$CACHE"

_notify() {
    dunstify -u normal "pomodoro" "$1" 2>/dev/null || \
    notify-send "pomodoro" "$1" 2>/dev/null
}

_write()   { printf "%s" "$1" > "$STATE"; }
_pid()     { cat "$DAEMON_PID" 2>/dev/null; }
_running() { local p; p=$(_pid); [[ -n $p ]] && kill -0 "$p" 2>/dev/null; }

_rofi_active() { [[ -f "$ROFI_STATE" ]]; }
_rofi_paused() { [[ -f "$ROFI_PAUSE" ]]; }

# State format: task||end_ts|work_min|break_min|total|current|video|phase
_rofi_parse() {
    # Sets: TASK END_TS WORK_MIN BREAK_MIN TOTAL CUR VIDEO PHASE
    IFS='|' read -r TASK _ END_TS WORK_MIN BREAK_MIN TOTAL CUR VIDEO PHASE < "$ROFI_STATE"
}

_rofi_task() {
    IFS='|' read -r task _ _ _ _ _ _ _ _ < "$ROFI_STATE"
    printf '%s' "$task"
}

_rofi_remaining() {
    local end_ts
    IFS='|' read -r _ _ end_ts _ < "$ROFI_STATE"
    if _rofi_paused; then
        cat "$ROFI_PAUSE"
    else
        echo $(( end_ts - $(date +%s) ))
    fi
}

_mpv_cmd() {
    echo "$1" | socat - "$MPV_SOCKET" 2>/dev/null
}

_rofi_status() {
    local task phase paused_icon secs mins secs_rem short end_ts total cur
    _rofi_parse
    task="$TASK"; end_ts="$END_TS"; total="${TOTAL:-1}"; cur="${CUR:-1}"; phase="${PHASE:-work}"
    secs=$(_rofi_remaining)
    [[ $secs -lt 0 ]] && secs=0
    mins=$(( secs / 60 ))
    secs_rem=$(( secs % 60 ))

    if _rofi_paused; then
        paused_icon="⏸"
    elif [[ "$phase" == "break" ]]; then
        paused_icon="☕"
    else
        paused_icon="▶"
    fi

    short=$(printf '%s %02d:%02d' "$paused_icon" "$mins" "$secs_rem")
    printf '%s' "$short"
}

_rofi_pause() {
    if _rofi_paused; then return; fi
    local secs_left phase
    secs_left=$(_rofi_remaining)
    IFS='|' read -r _ _ _ _ _ _ _ phase < "$ROFI_STATE"
    echo "$secs_left" > "$ROFI_PAUSE"
    [[ -f "$ROFI_TIMER" ]] && kill "$(cat "$ROFI_TIMER")" 2>/dev/null
    rm -f "$ROFI_TIMER"
    _notify "session paused"
}

_rofi_resume() {
    if ! _rofi_paused; then return; fi
    local secs_left task end_ts work_min break_min total cur video phase
    secs_left=$(cat "$ROFI_PAUSE")
    rm -f "$ROFI_PAUSE"
    IFS='|' read -r task _ end_ts work_min break_min total cur video phase < "$ROFI_STATE"
    local new_end=$(( $(date +%s) + secs_left ))
    printf '%s||%s|%s|%s|%s|%s|%s|%s' "$task" "$new_end" "$work_min" "$break_min" "$total" "$cur" "$video" "$phase" > "$ROFI_STATE"
    (
        sleep "$secs_left"
        # pomodoro.sh handles on_phase_end via its own background timer
    ) &
    echo $! > "$ROFI_TIMER"
    _notify "session resumed"
}

_rofi_stop() {
    [[ -f "$ROFI_PID" ]]   && kill "$(cat "$ROFI_PID")"   2>/dev/null
    [[ -f "$ROFI_TIMER" ]]  && kill "$(cat "$ROFI_TIMER")" 2>/dev/null
    rm -f "$ROFI_PID" "$ROFI_TIMER" "$ROFI_STATE" "$ROFI_PAUSE" "$MPV_SOCKET"
    _notify "session stopped"
}

_arc() {
    SILENCE_SECONDS=30 MUSIC_DIR=/home/jorge/Music_arc/2026_I /home/jorge/dotfiles/scripts/sound_silence.sh
    :
}

_run_daemon() {
    echo $$ > "$DAEMON_PID"
    rm -f "$DAEMON_PAUSE"
    local session=0
    local skip=false
    local arc="${1:-}"

    trap 'rm -f "$DAEMON_PID" "$DAEMON_PAUSE" "$STATE"; exit 0' SIGTERM SIGINT
    trap 'skip=true' SIGUSR1

    _countdown() {
        local total=$(( $1 * 60 ))
        local label="$2"
        skip=false

        while (( total > 0 )); do
            $skip && return
            if [[ -f "$DAEMON_PAUSE" ]]; then
                _write "$(printf '⏸ %02d:%02d' $((total/60)) $((total%60)))"
            else
                _write "$(printf '%s %02d:%02d' "$label" $((total/60)) $((total%60)))"
                (( total-- ))
            fi
            sleep 1
        done
    }

    while true; do
        (( session++ ))
        [[ "$arc" == "arc" ]] && _arc &
        _countdown $WORK "▶"
        _notify "session $session done"

        if (( session % LONG_EVERY == 0 )); then
            _countdown $LONG "☕"
            _notify "long break over"
        else
            _countdown $SHORT "·"
            _notify "break over"
        fi
    done
}

case "${1:-status}" in
    start)
        _running && { echo "already running (pid $(_pid))"; exit 1; }
        if [[ "${2:-}" == "arc" ]]; then
            "$0" _daemon arc &
        else
            "$0" _daemon &
        fi
        disown
        ;;
    stop)
        if _running; then
            kill "$(_pid)"
            rm -f "$DAEMON_PID" "$DAEMON_PAUSE" "$STATE"
        elif _rofi_active; then
            _rofi_stop
        fi
        ;;
    toggle)
        if _running; then
            if [[ -f "$DAEMON_PAUSE" ]]; then
                rm -f "$DAEMON_PAUSE"
            else
                touch "$DAEMON_PAUSE"
            fi
        elif _rofi_active; then
            if _rofi_paused; then
                _rofi_resume
            else
                _rofi_pause
            fi
        else
            "$0" _daemon &
            disown
        fi
        ;;
    next)
        if _running; then
            kill -SIGUSR1 "$(_pid)"
        fi
        ;;
    status)
        if _running; then
            cat "$STATE" 2>/dev/null || echo ""
        elif _rofi_active; then
            _rofi_status
        else
            printf ''
        fi
        ;;
    _daemon)
        _run_daemon "${2:-}"
        ;;
    *)
        printf "usage: pomodoro {start|stop|toggle|next|status}\n"
        ;;
esac