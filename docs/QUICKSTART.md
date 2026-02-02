# Quick Start Guide

Минимальная инструкция для быстрого запуска Voice Interviewer Agent.

## За 5 минут

### 1. Клонирование и установка

```bash
git clone <repo-url>
cd voice-interviewer-agent

python3 -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Конфигурация

```bash
cp .env.example .env
```

Отредактируйте `.env` и заполните **МИНИМУМ**:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### 3. Запуск инфраструктуры

```bash
docker-compose -f config/docker-compose.yml up -d
```

Проверка:

```bash
docker-compose -f config/docker-compose.yml ps
# redis и postgres должны быть "Up"
```

### 4. Запуск агента

```bash
python3 scripts/demo.py
```

Выберите режим (MAXIMUM или MOCK) и паттерн (INTERACTION или MANAGEMENT).

---

## Проверка работоспособности

```bash
# Проверка Redis
docker-compose -f config/docker-compose.yml exec redis redis-cli ping
# Ответ: PONG

# Проверка PostgreSQL
docker-compose -f config/docker-compose.yml exec postgres psql -U interviewer_user -d voice_interviewer -c "SELECT 1"
# Ответ: 1

# Проверка Python зависимостей
python3 -c "from src.interview.maximum import MaximumInterviewer; print('OK')"
# Ответ: OK
```

---

## Минимальная конфигурация .env

Для локального тестирования:

```env
# DeepSeek (обязательно для MAXIMUM режима)
DEEPSEEK_API_KEY=your_key
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

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

## Первое интервью

После запуска `python3 scripts/demo.py`:

1. **Выбор режима:**

   ```
   Select mode:
   [1] MAXIMUM - Full AI interview (DeepSeek)
   [2] MOCK - Simulated demo

   Enter choice (1 or 2): 1
   ```

2. **Выбор паттерна:**

   ```
   Select pattern:
   [1] INTERACTION - Agent for customers/clients
   [2] MANAGEMENT - Agent for employees/internal use

   Enter choice (1 or 2): 1
   ```

3. **Maximum Interview Mode:**

   Три фазы:
   - **DISCOVERY** — свободный диалог о бизнесе
   - **STRUCTURED** — сбор недостающих данных
   - **SYNTHESIS** — генерация полной анкеты

4. **Завершение:**

   ```
   Interview completed!

   Files saved:
   - output/anketa_abc123.json
   - output/anketa_abc123.md
   ```

---

## Просмотр результатов

### CLI

```bash
# Статистика интервью
docker-compose -f config/docker-compose.yml exec postgres psql -U interviewer_user -d voice_interviewer -c "SELECT * FROM pattern_statistics;"

# Все завершённые интервью
docker-compose -f config/docker-compose.yml exec postgres psql -U interviewer_user -d voice_interviewer -c "SELECT * FROM completed_interviews;"
```

### Файлы

```bash
# JSON и Markdown файлы
ls -la output/
```

---

## Остановка

```bash
# Остановить инфраструктуру
docker-compose -f config/docker-compose.yml down

# Остановить с удалением данных
docker-compose -f config/docker-compose.yml down -v
```

---

## Известные проблемы

### Port already in use

```bash
# Если порт 6379 занят
docker-compose -f config/docker-compose.yml down
lsof -ti:6379 | xargs kill -9

# Если порт 5432 занят
docker-compose -f config/docker-compose.yml down
lsof -ti:5432 | xargs kill -9
```

### ModuleNotFoundError

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### DeepSeek API Error

```bash
# Проверьте ключ
echo $DEEPSEEK_API_KEY

# Тест API
python3 -c "
from src.llm.deepseek import DeepSeekClient
client = DeepSeekClient()
print('Connection OK')
"
```

---

## Дальше

- Полная документация: [README.md](../README.md)
- Обзор проекта: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- Пример анкеты: [example_anketa.md](example_anketa.md)

---

**Время до первого запуска: ~5 минут**
