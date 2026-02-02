# ⚡ Quick Start Guide

Минимальная инструкция для быстрого запуска Voice Interviewer Agent.

## 🚀 За 5 минут

### 1. Клонирование и установка

```bash
git clone <repo-url>
cd voice-interviewer-agent
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Конфигурация

```bash
cp .env.example .env
```

Отредактируйте `.env` и заполните **МИНИМУМ**:

```env
AZURE_OPENAI_API_KEY=sk-...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
DEEPSEEK_API_KEY=sk-...
```

### 3. Запуск инфраструктуры

```bash
docker-compose up -d
```

Проверка:
```bash
docker-compose ps
# redis и postgres должны быть "Up"
```

### 4. Запуск агента

```bash
python main.py
```

Выберите паттерн (1 или 2) и следуйте инструкциям.

---

## 🧪 Проверка работоспособности

```bash
# Проверка Redis
docker-compose exec redis redis-cli ping
# Ответ: PONG

# Проверка PostgreSQL
docker-compose exec postgres psql -U interviewer_user -d voice_interviewer -c "SELECT 1"
# Ответ: 1

# Проверка Python зависимостей
python -c "import redis, sqlalchemy, rich; print('OK')"
# Ответ: OK
```

---

## 📝 Минимальная конфигурация .env

Для локального тестирования **без реальных API**:

```env
# Azure OpenAI (MOCK для тестирования)
AZURE_OPENAI_API_KEY=test_key
AZURE_OPENAI_ENDPOINT=https://test.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4-realtime-preview
AZURE_OPENAI_API_VERSION=2024-10-01-preview

# DeepSeek (MOCK для тестирования)
DEEPSEEK_API_KEY=test_key
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-reasoner

# Redis (Docker)
REDIS_HOST=localhost
REDIS_PORT=6379

# PostgreSQL (Docker)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=voice_interviewer
POSTGRES_USER=interviewer_user
POSTGRES_PASSWORD=change_me_in_production
```

---

## 🎯 Первое интервью

После запуска `python main.py`:

1. **Выбор паттерна:**
   ```
   Select interview pattern:
   [1] INTERACTION - Agent for customers/clients
   [2] MANAGEMENT - Agent for employees/internal use
   
   Enter choice (1 or 2): 1
   ```

2. **CLI Dashboard:**
   ```
   ╔════════════════════════════════════════════╗
   ║ 📊 Interview Info                          ║
   ║ Session ID: abc12345                       ║
   ║ Pattern: INTERACTION                       ║
   ║ Status: ▶️ In Progress                     ║
   ╚════════════════════════════════════════════╝
   ```

3. **Прохождение интервью:**
   - Агент задаёт вопросы
   - Вы отвечаете (в текущей MOCK версии - автоматически)
   - Агент анализирует и уточняет
   - Прогресс отображается в реальном времени

4. **Завершение:**
   ```
   🎉 Interview completed successfully!
   
   ✨ Anketa has been saved to the database!
   ```

---

## 🔍 Просмотр результатов

### CLI

```bash
# Статистика интервью
docker-compose exec postgres psql -U interviewer_user -d voice_interviewer -c "SELECT * FROM pattern_statistics;"

# Все завершённые интервью
docker-compose exec postgres psql -U interviewer_user -d voice_interviewer -c "SELECT * FROM completed_interviews;"
```

### PgAdmin (опционально)

```bash
# Запустите с tools профилем
docker-compose --profile tools up -d

# Откройте http://localhost:5050
# Email: admin@example.com
# Password: admin

# Подключитесь к PostgreSQL:
# Host: postgres
# Port: 5432
# Database: voice_interviewer
# Username: interviewer_user
# Password: change_me_in_production
```

---

## 🛑 Остановка

```bash
# Остановить инфраструктуру
docker-compose down

# Остановить с удалением данных
docker-compose down -v
```

---

## ⚠️ Известные проблемы

### Port already in use
```bash
# Если порт 6379 занят
docker-compose down
sudo lsof -ti:6379 | xargs kill -9

# Если порт 5432 занят
docker-compose down
sudo lsof -ti:5432 | xargs kill -9
```

### Permission denied
```bash
chmod +x main.py
```

### ModuleNotFoundError
```bash
pip install -r requirements.txt
```

---

## 📚 Дальше

- 📖 Полная документация: [README.md](README.md)
- 🔧 Конфигурация: [.env.example](.env.example)
- 🐛 Проблемы: GitHub Issues

---

**Время до первого запуска: ~5 минут ⚡**
