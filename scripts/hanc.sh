#!/bin/bash
# ============================================================
# hanc.sh — Управление сервисами Hanc.AI
# ============================================================
#
# Использование:
#   ./scripts/hanc.sh start            — запустить server + agent
#   ./scripts/hanc.sh stop             — остановить всё
#   ./scripts/hanc.sh restart          — перезапустить всё
#   ./scripts/hanc.sh status           — статус процессов
#   ./scripts/hanc.sh logs             — логи (tail -f)
#
#   ./scripts/hanc.sh start server     — только сервер
#   ./scripts/hanc.sh start agent      — только агент
#   ./scripts/hanc.sh stop server      — остановить сервер
#   ./scripts/hanc.sh stop agent       — остановить агент
#   ./scripts/hanc.sh restart server   — перезапустить сервер
#   ./scripts/hanc.sh restart agent    — перезапустить агент
#   ./scripts/hanc.sh logs server      — логи сервера
#   ./scripts/hanc.sh logs agent       — логи агента
#
#   ./scripts/hanc.sh kill-all         — аварийно убить всё (SIGKILL)
#
# ============================================================

set -e

# -- Пути --
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

PYTHON="$PROJECT_DIR/venv/bin/python"
AGENT_SCRIPT="$PROJECT_DIR/scripts/run_voice_agent.py"
SERVER_SCRIPT="$PROJECT_DIR/scripts/run_server.py"

AGENT_PIDFILE="$PROJECT_DIR/.agent.pid"
SERVER_PIDFILE="$PROJECT_DIR/.server.pid"

AGENT_LOGFILE="$PROJECT_DIR/logs/agent.log"
SERVER_LOGFILE="$PROJECT_DIR/logs/server.log"

# -- Цвета --
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ============================================================
# Утилиты
# ============================================================

ensure_log_dir() {
    mkdir -p "$PROJECT_DIR/logs"
}

is_pid_alive() {
    kill -0 "$1" 2>/dev/null
}

get_agent_pids() {
    pgrep -f "run_voice_agent.py" 2>/dev/null || true
}

get_server_pids() {
    pgrep -f "run_server.py\|uvicorn.*src.web.server" 2>/dev/null || true
}

# Универсальная остановка процесса по PID-файлу + pgrep
# $1 = имя ("server" / "agent")
# $2 = pidfile
# $3 = pgrep-функция
stop_service() {
    local name="$1"
    local pidfile="$2"
    local pids_fn="$3"

    local stopped=false

    # 1. PID-файл
    if [ -f "$pidfile" ]; then
        local saved_pid
        saved_pid=$(cat "$pidfile" 2>/dev/null)
        if [ -n "$saved_pid" ] && is_pid_alive "$saved_pid"; then
            echo "Stopping $name (PID $saved_pid)..."
            kill "$saved_pid"
            for _ in $(seq 1 10); do
                is_pid_alive "$saved_pid" || break
                sleep 1
            done
            if is_pid_alive "$saved_pid"; then
                echo "  SIGTERM не помог, SIGKILL..."
                kill -9 "$saved_pid" 2>/dev/null || true
            fi
            stopped=true
        fi
        rm -f "$pidfile"
    fi

    # 2. Подчищаем оставшиеся процессы через pgrep
    local remaining
    remaining=$($pids_fn)
    if [ -n "$remaining" ]; then
        echo "Killing remaining $name processes: $(echo $remaining | tr '\n' ' ')"
        echo "$remaining" | xargs kill 2>/dev/null || true
        sleep 2
        remaining=$($pids_fn)
        if [ -n "$remaining" ]; then
            echo "$remaining" | xargs kill -9 2>/dev/null || true
        fi
        stopped=true
    fi

    if [ "$stopped" = true ]; then
        echo -e "  ${GREEN}$name stopped${NC}"
    else
        echo "  $name not running"
    fi
}

# ============================================================
# Server
# ============================================================

start_server() {
    local existing
    existing=$(get_server_pids)
    if [ -n "$existing" ]; then
        echo -e "${YELLOW}Server уже запущен (PID $(echo $existing | head -1))${NC}"
        echo "  Используйте: ./scripts/hanc.sh restart server"
        return 1
    fi

    ensure_log_dir

    echo "Starting web server..."
    cd "$PROJECT_DIR"
    nohup "$PYTHON" "$SERVER_SCRIPT" > "$SERVER_LOGFILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$SERVER_PIDFILE"

    sleep 2
    if is_pid_alive "$pid"; then
        echo -e "  ${GREEN}Server started (PID $pid) — http://localhost:8000${NC}"
    else
        echo -e "  ${RED}Server failed to start! Logs:${NC}"
        tail -20 "$SERVER_LOGFILE"
        rm -f "$SERVER_PIDFILE"
        return 1
    fi
}

stop_server() {
    stop_service "Server" "$SERVER_PIDFILE" get_server_pids
}

# ============================================================
# Agent
# ============================================================

start_agent() {
    local existing
    existing=$(get_agent_pids)
    if [ -n "$existing" ]; then
        local count
        count=$(echo "$existing" | wc -l | tr -d ' ')
        echo -e "${YELLOW}Agent уже запущен ($count процесс, PID $(echo $existing | tr '\n' ' '))${NC}"
        echo "  Используйте: ./scripts/hanc.sh restart agent"
        return 1
    fi

    ensure_log_dir

    echo "Starting voice agent..."
    cd "$PROJECT_DIR"
    nohup "$PYTHON" "$AGENT_SCRIPT" > "$AGENT_LOGFILE" 2>&1 &
    local pid=$!

    sleep 2
    if is_pid_alive "$pid"; then
        # Python может сам записать PID, но подстрахуемся
        if [ ! -f "$AGENT_PIDFILE" ]; then
            echo "$pid" > "$AGENT_PIDFILE"
        fi
        echo -e "  ${GREEN}Agent started (PID $pid)${NC}"
    else
        echo -e "  ${RED}Agent failed to start! Logs:${NC}"
        tail -20 "$AGENT_LOGFILE"
        rm -f "$AGENT_PIDFILE"
        return 1
    fi
}

stop_agent() {
    stop_service "Agent" "$AGENT_PIDFILE" get_agent_pids
}

# ============================================================
# Status
# ============================================================

show_status() {
    echo ""
    echo -e "${BOLD}=== Hanc.AI — Status ===${NC}"
    echo ""

    # Server
    local server_pids
    server_pids=$(get_server_pids)
    if [ -n "$server_pids" ]; then
        local server_pid
        server_pid=$(echo "$server_pids" | head -1)
        local server_uptime
        server_uptime=$(ps -o etime= -p "$server_pid" 2>/dev/null | tr -d ' ')
        echo -e "  Web Server:   ${GREEN}running${NC}  PID $server_pid  uptime $server_uptime  http://localhost:8000"
    else
        echo -e "  Web Server:   ${RED}stopped${NC}"
    fi

    # Agent
    local agent_pids
    agent_pids=$(get_agent_pids)
    if [ -n "$agent_pids" ]; then
        local count
        count=$(echo "$agent_pids" | wc -l | tr -d ' ')
        local agent_pid
        agent_pid=$(echo "$agent_pids" | head -1)
        local agent_uptime
        agent_uptime=$(ps -o etime= -p "$agent_pid" 2>/dev/null | tr -d ' ')
        if [ "$count" -gt 1 ]; then
            echo -e "  Voice Agent:  ${YELLOW}$count processes (CONFLICT!)${NC}  PIDs: $(echo $agent_pids | tr '\n' ' ')"
        else
            echo -e "  Voice Agent:  ${GREEN}running${NC}  PID $agent_pid  uptime $agent_uptime"
        fi
    else
        echo -e "  Voice Agent:  ${RED}stopped${NC}"
    fi

    # Port 8000
    local port_pid
    port_pid=$(lsof -ti:8000 2>/dev/null | head -1)
    if [ -n "$port_pid" ]; then
        echo -e "  Port 8000:    ${GREEN}in use${NC}  (PID $port_pid)"
    else
        echo -e "  Port 8000:    ${CYAN}free${NC}"
    fi

    echo ""
}

# ============================================================
# Logs
# ============================================================

show_logs() {
    local target="${1:-all}"

    case "$target" in
        server)
            if [ -f "$SERVER_LOGFILE" ]; then
                echo -e "${BOLD}=== Server Logs (Ctrl+C to exit) ===${NC}"
                tail -f "$SERVER_LOGFILE"
            else
                echo "No server log: $SERVER_LOGFILE"
            fi
            ;;
        agent)
            if [ -f "$AGENT_LOGFILE" ]; then
                echo -e "${BOLD}=== Agent Logs (Ctrl+C to exit) ===${NC}"
                tail -f "$AGENT_LOGFILE"
            else
                echo "No agent log: $AGENT_LOGFILE"
            fi
            ;;
        all|*)
            echo -e "${BOLD}=== All Logs (Ctrl+C to exit) ===${NC}"
            local files=""
            [ -f "$SERVER_LOGFILE" ] && files="$SERVER_LOGFILE"
            [ -f "$AGENT_LOGFILE" ] && files="$files $AGENT_LOGFILE"
            if [ -n "$files" ]; then
                tail -f $files
            else
                echo "No log files found in logs/"
            fi
            ;;
    esac
}

# ============================================================
# Kill all
# ============================================================

kill_all() {
    echo -e "${RED}=== Emergency Kill ===${NC}"

    local agent_pids server_pids
    agent_pids=$(get_agent_pids)
    server_pids=$(get_server_pids)

    if [ -n "$agent_pids" ]; then
        echo "  Killing agent: $(echo $agent_pids | tr '\n' ' ')"
        echo "$agent_pids" | xargs kill -9 2>/dev/null || true
    fi

    if [ -n "$server_pids" ]; then
        echo "  Killing server: $(echo $server_pids | tr '\n' ' ')"
        echo "$server_pids" | xargs kill -9 2>/dev/null || true
    fi

    # На всякий случай порт 8000
    local port_pids
    port_pids=$(lsof -ti:8000 2>/dev/null)
    if [ -n "$port_pids" ]; then
        echo "  Killing port 8000: $port_pids"
        echo "$port_pids" | xargs kill -9 2>/dev/null || true
    fi

    rm -f "$AGENT_PIDFILE" "$SERVER_PIDFILE"

    if [ -z "$agent_pids" ] && [ -z "$server_pids" ] && [ -z "$port_pids" ]; then
        echo "  Nothing running"
    else
        echo -e "  ${GREEN}Done${NC}"
    fi
}

# ============================================================
# Help
# ============================================================

show_help() {
    echo ""
    echo -e "${BOLD}Hanc.AI — Service Manager${NC}"
    echo ""
    echo "  Usage: $0 <command> [service]"
    echo ""
    echo "  Commands:"
    echo "    start   [server|agent]   Start services (default: both)"
    echo "    stop    [server|agent]   Stop services (default: both)"
    echo "    restart [server|agent]   Restart services (default: both)"
    echo "    status                   Show process status"
    echo "    logs    [server|agent]   Tail log files (default: all)"
    echo "    kill-all                 Emergency SIGKILL everything"
    echo ""
    echo "  Examples:"
    echo "    $0 start                 # Start server + agent"
    echo "    $0 restart agent         # Restart only voice agent"
    echo "    $0 logs server           # Tail server logs"
    echo "    $0 status                # Show all process status"
    echo ""
}

# ============================================================
# Main
# ============================================================

CMD="${1:-help}"
TARGET="${2:-all}"

case "$CMD" in
    start)
        case "$TARGET" in
            server)  start_server ;;
            agent)   start_agent ;;
            all|*)   start_server; echo ""; start_agent ;;
        esac
        echo ""
        show_status
        ;;
    stop)
        case "$TARGET" in
            server)  stop_server ;;
            agent)   stop_agent ;;
            all|*)   stop_agent; stop_server ;;
        esac
        ;;
    restart)
        case "$TARGET" in
            server)  stop_server; sleep 1; start_server ;;
            agent)   stop_agent; sleep 1; start_agent ;;
            all|*)   stop_agent; stop_server; sleep 1; start_server; echo ""; start_agent ;;
        esac
        echo ""
        show_status
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$TARGET"
        ;;
    kill-all)
        kill_all
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $CMD${NC}"
        show_help
        exit 1
        ;;
esac
