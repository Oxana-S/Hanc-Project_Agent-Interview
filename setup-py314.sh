#!/bin/bash

# Voice Interviewer Agent - Установка для Python 3.14+
# Используйте этот скрипт если у вас Python 3.14+

set -e

echo "🎙️ Voice Interviewer Agent - Python 3.14+ Setup"
echo "================================================"
echo ""

# Проверка Python
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python найден: Python $PYTHON_VERSION"

# Удаление старого окружения
if [ -d "venv" ]; then
    echo "🗑️  Удаление старого виртуального окружения..."
    rm -rf venv
fi

# Создание виртуального окружения
echo "📦 Создание виртуального окружения..."
python3 -m venv venv

# Активация
echo "🔄 Активация окружения..."
source venv/bin/activate

# Установка зависимостей
echo "📥 Установка минимальных зависимостей (совместимых с Python 3.14)..."
pip install --upgrade pip

# Установка по одному пакету для лучшей диагностики
echo ""
echo "Установка основных пакетов..."

pip install openai
pip install httpx requests
pip install redis hiredis
pip install psycopg2-binary sqlalchemy alembic
pip install pydantic pydantic-settings pyyaml python-dateutil
pip install rich click
pip install aiohttp websockets
pip install structlog
pip install python-dotenv tenacity

echo ""
echo "✓ Все зависимости установлены"

# Создание .env
if [ ! -f .env ]; then
    echo ""
    echo "📝 Создание .env файла..."
    cp .env.example .env
    echo "✓ Файл .env создан"
    echo ""
    echo "⚠️  ВАЖНО: Отредактируйте .env и заполните API ключи:"
    echo "   - AZURE_OPENAI_API_KEY"
    echo "   - DEEPSEEK_API_KEY"
    echo ""
    echo "   Откройте файл: nano .env"
fi

# Запуск Docker Compose
if command -v docker &> /dev/null; then
    echo ""
    echo "🐳 Запуск Redis и PostgreSQL..."
    docker-compose up -d
    
    echo "⏳ Ждём запуска баз данных (5 сек)..."
    sleep 5
    
    echo "✓ Инфраструктура запущена"
    echo ""
    docker-compose ps
else
    echo ""
    echo "⚠️  Docker не найден. Установите и запустите Redis и PostgreSQL вручную"
fi

echo ""
echo "================================================"
echo "✅ Установка завершена для Python 3.14!"
echo "================================================"
echo ""
echo "Следующие шаги:"
echo ""
echo "1. Отредактируйте .env и заполните API ключи:"
echo "   nano .env"
echo ""
echo "2. Проверьте установку:"
echo "   ./venv/bin/python -m pytest --tb=short -q"
echo ""
echo "3. Запустите сервер:"
echo "   ./venv/bin/python scripts/run_server.py"
echo ""
echo "4. Запустите голосового агента:"
echo "   ./scripts/hanc.sh start"
echo ""
echo "📚 Документация: docs/PYTHON_3.14_SETUP.md"
echo ""
