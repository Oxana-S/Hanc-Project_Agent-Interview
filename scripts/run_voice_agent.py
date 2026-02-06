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

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

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
    # Важно: импорт должен быть внутри __main__ блока для multiprocessing
    from src.voice.consultant import run_voice_agent
    run_voice_agent()
