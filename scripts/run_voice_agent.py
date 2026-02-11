#!/usr/bin/env python3
"""
Запуск голосового агента-консультанта.

Использование:
    python scripts/run_voice_agent.py

Агент подключится к LiveKit Cloud и будет ждать клиентов.
Клиенты могут подключиться через:
- Веб-интерфейс (public/index.html)
- LiveKit Meet (https://meet.livekit.io)
- Тестовый скрипт

Требования:
- .env файл с настройками LiveKit и Azure OpenAI
- Установленные зависимости: pip install -r requirements.txt
"""

import sys
import os
import signal

# Добавляем корень проекта в path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# === PID-file: защита от запуска нескольких копий ===
PIDFILE = os.path.join(PROJECT_ROOT, ".agent.pid")


def _is_process_alive(pid: int) -> bool:
    """Проверяет, жив ли процесс с данным PID."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _check_duplicate():
    """Проверяет, не запущен ли уже агент. Если да — предупреждает и выходит."""
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old_pid = int(f.read().strip())
            if old_pid == os.getpid():
                # PID файл от нас самих — не дубль
                pass
            elif _is_process_alive(old_pid):
                print(f"⚠️  Агент уже запущен (PID {old_pid})!")
                print(f"   Остановите его: kill {old_pid}")
                print("   Или используйте: ./scripts/hanc.sh restart agent")
                sys.exit(1)
            else:
                # Stale PID file — процесс мёртв, удаляем
                os.remove(PIDFILE)
        except (ValueError, FileNotFoundError):
            # Некорректный PID file — удаляем
            os.remove(PIDFILE)


def _write_pid():
    """Записывает текущий PID в файл."""
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid(*args):
    """Удаляет PID-файл при завершении."""
    try:
        os.remove(PIDFILE)
    except FileNotFoundError:
        pass


# Регистрируем cleanup на завершение
signal.signal(signal.SIGTERM, lambda sig, frame: (_cleanup_pid(), sys.exit(0)))
import atexit
atexit.register(_cleanup_pid)

# Проверяем необходимые переменные
required_vars = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
]

missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    print(f"❌ Отсутствуют переменные окружения: {', '.join(missing)}")
    print("Проверьте файл .env")
    sys.exit(1)

print("=" * 60)
print("🎤 ГОЛОСОВОЙ АГЕНТ-КОНСУЛЬТАНТ")
print("=" * 60)
print()
print(f"LiveKit URL: {os.getenv('LIVEKIT_URL')}")
print(f"Azure Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
print(f"Azure Deployment: {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')}")
print()
print("Агент готов к подключению клиентов.")
print("Для подключения используйте LiveKit Meet или веб-интерфейс.")
print()
print("Нажмите Ctrl+C для остановки.")
print("=" * 60)

if __name__ == "__main__":
    # Защита от дублей: проверяем PID-файл
    _check_duplicate()
    _write_pid()

    # Python 3.14: asyncio.get_event_loop() raises RuntimeError when no loop exists.
    # LiveKit Agents SDK (cli.py) calls get_event_loop() in dev mode — create one first.
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # Важно: импорт должен быть внутри __main__ блока для multiprocessing
    from src.voice.consultant import run_voice_agent
    run_voice_agent()
