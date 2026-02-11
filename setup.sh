#!/bin/bash

# Voice Interviewer Agent - Быстрая установка
# Для Linux и macOS

set -e

echo "🎙️ Voice Interviewer Agent - Quick Setup"
echo "=========================================="
echo ""

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Установите Python 3.9+"
    exit 1
fi

echo "✓ Python найден: $(python3 --version)"

# Проверка Docker
if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker не найден. Для полной функциональности установите Docker"
    echo "   Или используйте локальный Redis и PostgreSQL"
fi

# Создание виртуального окружения
echo ""
echo "📦 Создание виртуального окружения..."
python3 -m venv venv

# Активация
echo "✓ Виртуальное окружение создано"
echo "🔄 Активация окружения..."
source venv/bin/activate

# Установка зависимостей
echo "📥 Установка зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✓ Зависимости установлены"

# Создание .env из примера
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
fi

echo ""
echo "=========================================="
echo "✅ Установка завершена!"
echo "=========================================="
echo ""
echo "Следующие шаги:"
echo ""
echo "1. Отредактируйте .env и заполните API ключи:"
echo "   nano .env"
echo ""
echo "2. Запустите сервер:"
echo "   ./venv/bin/python scripts/run_server.py"
echo ""
echo "3. Запустите голосового агента:"
echo "   ./scripts/hanc.sh start"
echo ""
echo "Документация: README.md"
echo "Быстрый старт: docs/QUICKSTART.md"
echo ""
echo "🎉 Удачи!"
