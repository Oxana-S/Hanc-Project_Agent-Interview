#!/bin/bash
# ============================================================
# agent.sh — Управление процессами Hanc.AI Voice Agent
# ============================================================
#
# Использование:
#   ./scripts/agent.sh start    — запустить агент (в фоне)
#   ./scripts/agent.sh stop     — остановить агент
#   ./scripts/agent.sh restart  — перезапустить
#   ./scripts/agent.sh status   — статус процессов
#   ./scripts/agent.sh logs     — показать логи (tail -f)
#   ./scripts/agent.sh kill-all — убить ВСЕ процессы агента (аварийно)
#
# ============================================================

set -e

# Определяем корень проекта (родитель папки scripts/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

PIDFILE="$PROJECT_DIR/.agent.pid"
LOGFILE="$PROJECT_DIR/logs/agent.log"
PYTHON="$PROJECT_DIR/venv/bin/python"
AGENT_SCRIPT="$PROJECT_DIR/scripts/run_voice_agent.py"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================
# Функции
# ============================================================

ensure_log_dir() {
    mkdir -p "$(dirname "$LOGFILE")"
}

get_agent_pids() {
    # Ищем процессы run_voice_agent.py (исключая grep и сам скрипт)
    pgrep -f "run_voice_agent.py" 2>/dev/null || true
}

get_server_pids() {
    # Ищем процессы run_server.py / uvicorn
    pgrep -f "run_server.py\|uvicorn.*src.web.server" 2>/dev/null || true
}

show_status() {
    echo ""
    echo "=== Hanc.AI Process Status ==="
    echo ""

    # Voice Agent
    AGENT_PIDS=$(get_agent_pids)
    if [ -n "$AGENT_PIDS" ]; then
        COUNT=$(echo "$AGENT_PIDS" | wc -l | tr -d ' ')
        if [ "$COUNT" -gt 1 ]; then
            echo -e "  ${YELLOW}Voice Agent:  $COUNT процессов (КОНФЛИКТ!)${NC}"
            echo -e "  ${YELLOW}  PIDs: $(echo $AGENT_PIDS | tr '\n' ' ')${NC}"
            echo -e "  ${RED}  ⚠ Должен быть только 1 процесс! Используйте: ./scripts/agent.sh kill-all${NC}"
        else
            echo -e "  ${GREEN}Voice Agent:  running (PID $AGENT_PIDS)${NC}"
        fi
    else
        echo -e "  ${RED}Voice Agent:  stopped${NC}"
    fi

    # Web Server
    SERVER_PIDS=$(get_server_pids)
    if [ -n "$SERVER_PIDS" ]; then
        echo -e "  ${GREEN}Web Server:   running (PID $(echo $SERVER_PIDS | head -1))${NC}"
    else
        echo -e "  ${RED}Web Server:   stopped${NC}"
    fi

    # PID file
    if [ -f "$PIDFILE" ]; then
        SAVED_PID=$(cat "$PIDFILE")
        if kill -0 "$SAVED_PID" 2>/dev/null; then
            echo -e "  PID file:    $PIDFILE (PID $SAVED_PID, ${GREEN}alive${NC})"
        else
            echo -e "  PID file:    $PIDFILE (PID $SAVED_PID, ${RED}stale${NC})"
        fi
    else
        echo "  PID file:    none"
    fi

    echo ""
}

start_agent() {
    # Проверяем, не запущен ли уже
    EXISTING=$(get_agent_pids)
    if [ -n "$EXISTING" ]; then
        COUNT=$(echo "$EXISTING" | wc -l | tr -d ' ')
        echo -e "${YELLOW}Agent уже запущен ($COUNT процессов, PIDs: $(echo $EXISTING | tr '\n' ' '))${NC}"
        echo "Используйте: ./scripts/agent.sh restart"
        exit 1
    fi

    ensure_log_dir

    echo "Starting voice agent..."
    cd "$PROJECT_DIR"
    nohup "$PYTHON" "$AGENT_SCRIPT" > "$LOGFILE" 2>&1 &
    AGENT_PID=$!
    # PID-файл пишет сам Python (run_voice_agent.py)
    # Не дублируем здесь, иначе Python увидит свой PID и решит что дубль

    # Ждём 2 секунды и проверяем, что процесс жив
    sleep 2
    if kill -0 "$AGENT_PID" 2>/dev/null; then
        # Проверяем что Python записал PID-файл
        if [ ! -f "$PIDFILE" ]; then
            echo "$AGENT_PID" > "$PIDFILE"
        fi
        echo -e "${GREEN}Agent started (PID $AGENT_PID)${NC}"
        echo "Logs: $LOGFILE"
        echo "Stop: ./scripts/agent.sh stop"
    else
        echo -e "${RED}Agent failed to start! Check logs:${NC}"
        tail -20 "$LOGFILE"
        rm -f "$PIDFILE"
        exit 1
    fi
}

stop_agent() {
    # Сначала пробуем PID file
    if [ -f "$PIDFILE" ]; then
        SAVED_PID=$(cat "$PIDFILE")
        if kill -0 "$SAVED_PID" 2>/dev/null; then
            echo "Stopping agent (PID $SAVED_PID)..."
            kill "$SAVED_PID"
            # Ждём завершения (до 10 сек)
            for i in $(seq 1 10); do
                if ! kill -0 "$SAVED_PID" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            # Если всё ещё жив — SIGKILL
            if kill -0 "$SAVED_PID" 2>/dev/null; then
                echo "Process didn't stop gracefully, sending SIGKILL..."
                kill -9 "$SAVED_PID" 2>/dev/null || true
            fi
            echo -e "${GREEN}Agent stopped${NC}"
        else
            echo "PID $SAVED_PID already dead (stale PID file)"
        fi
        rm -f "$PIDFILE"
    fi

    # Убиваем оставшиеся процессы (если есть)
    REMAINING=$(get_agent_pids)
    if [ -n "$REMAINING" ]; then
        echo "Killing remaining agent processes: $REMAINING"
        echo "$REMAINING" | xargs kill 2>/dev/null || true
        sleep 2
        # SIGKILL если не умерли
        STILL=$(get_agent_pids)
        if [ -n "$STILL" ]; then
            echo "$STILL" | xargs kill -9 2>/dev/null || true
        fi
        echo -e "${GREEN}All agent processes stopped${NC}"
    elif [ ! -f "$PIDFILE" ] || [ -z "$(cat "$PIDFILE" 2>/dev/null)" ]; then
        echo "No agent processes running"
    fi
}

kill_all() {
    echo -e "${RED}Killing ALL agent processes...${NC}"
    PIDS=$(get_agent_pids)
    if [ -n "$PIDS" ]; then
        echo "Found PIDs: $(echo $PIDS | tr '\n' ' ')"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        rm -f "$PIDFILE"
        echo -e "${GREEN}Done. All killed.${NC}"
    else
        echo "No agent processes found"
    fi
}

show_logs() {
    if [ -f "$LOGFILE" ]; then
        echo "=== Agent Logs (Ctrl+C to exit) ==="
        tail -f "$LOGFILE"
    else
        echo "No log file found at $LOGFILE"
        echo "Agent may not have been started via this script"
    fi
}

# ============================================================
# Main
# ============================================================

case "${1:-status}" in
    start)
        start_agent
        ;;
    stop)
        stop_agent
        ;;
    restart)
        stop_agent
        sleep 1
        start_agent
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    kill-all)
        kill_all
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|kill-all}"
        echo ""
        echo "  start     — Start voice agent in background"
        echo "  stop      — Graceful stop (SIGTERM, then SIGKILL after 10s)"
        echo "  restart   — Stop + Start"
        echo "  status    — Show running processes"
        echo "  logs      — Tail agent logs"
        echo "  kill-all  — Emergency kill ALL agent processes (SIGKILL)"
        exit 1
        ;;
esac
