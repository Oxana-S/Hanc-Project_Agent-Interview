# Методология тестирования и проверки готовности

Полный чек-лист для проверки работоспособности проекта и готовности к запуску.

## Обзор

| Этап | Что проверяем | Инструмент | Критерий прохождения |
|------|---------------|------------|----------------------|
| 1. Юнит-тесты | Логика модулей | pytest | 100% passed, coverage ≥50% |
| 2. Интеграция | Связи между модулями | pytest + fixtures | Все интеграционные тесты passed |
| 3. LLM-симуляция | Полный цикл консультации | run_test.py | 4/4 фазы, анкета сгенерирована |
| 4. Голосовой агент | WebRTC + STT/TTS | e2e_voice_test.js | Все этапы passed |
| 5. Подключения | DeepSeek, Redis, PostgreSQL, LiveKit | python scripts | Реальные соединения установлены |
| 6. Production readiness | .env, директории, API | чек-лист + smoke test | Все проверки пройдены |

---

## Этап 1: Юнит-тесты

### Требования

- Python 3.11+ (рекомендуется 3.14)
- Virtual environment активирован
- Зависимости установлены: `pip install -r requirements.txt`

### Запуск

```bash
# Активация venv
source venv/bin/activate

# Все тесты
pytest

# С покрытием
pytest --cov=src --cov-report=term-missing

# Подробный вывод
pytest -v

# Конкретный модуль
pytest tests/unit/test_knowledge.py -v
```

### Критерии прохождения

| Метрика | Минимум | Текущее значение |
|---------|---------|------------------|
| Тесты passed | 100% | 953/953 |
| Coverage | ≥50% | 50% |
| Критические модули | ≥80% | см. таблицу ниже |

### Покрытие по модулям

| Модуль | Coverage | Статус |
|--------|----------|--------|
| src/models.py | 100% | ✅ |
| src/anketa/schema.py | 95% | ✅ |
| src/anketa/data_cleaner.py | 98% | ✅ |
| src/anketa/generator.py | 100% | ✅ |
| src/output/manager.py | 99% | ✅ |
| src/knowledge/ | 88% | ✅ |
| src/documents/ | 77% | ✅ |
| src/storage/redis.py | 96% | ✅ |
| src/storage/postgres.py | 90% | ✅ |
| src/session/manager.py | 100% | ✅ |
| src/web/server.py | 94% | ✅ |
| src/cli/interface.py | 82% | ✅ |
| src/consultant/interviewer.py | 42% | ⚠️ |

### Структура тестов

```text
tests/
├── conftest.py                    # Общие fixtures
├── unit/
│   ├── test_models.py             # Core models
│   ├── test_api_server.py         # FastAPI endpoints
│   ├── test_session_manager.py    # SQLite CRUD
│   ├── test_redis_storage.py      # Redis operations
│   ├── test_postgres_storage.py   # PostgreSQL operations
│   ├── test_data_cleaner.py       # JSON repair, dialogue cleaning
│   ├── test_output_manager.py     # File output, versioning
│   ├── test_consultant_interviewer.py  # Consultation phases
│   ├── test_cli_interface.py      # CLI dashboard
│   ├── test_knowledge.py          # Industry profiles, matching
│   ├── test_documents.py          # Document parsing, analysis
│   └── ...
└── scenarios/                     # YAML для LLM-симуляции
```

---

## Этап 2: Интеграционные тесты

### Проверка связей

```bash
# Тесты с реальными fixtures
pytest tests/unit/test_api_server.py -v

# Проверка полного flow анкеты
pytest tests/unit/test_data_cleaner.py::TestAnketaPostProcessor -v
```

### Критерии

- Все API endpoints возвращают корректные статусы
- Session flow работает: create → update → complete
- Anketa extraction из диалога работает

---

## Этап 3: LLM-симуляция

### Требования

- DEEPSEEK_API_KEY в .env
- Баланс на аккаунте DeepSeek

### Доступные сценарии

| Сценарий | Отрасль | Сложность |
|----------|---------|-----------|
| auto_service | Автосервис | Базовый |
| auto_service_skeptic | Автосервис | Скептик |
| logistics_company | Логистика | Средний |
| medical_center | Медицина | Средний |
| restaurant_italiano | HoReCa | Средний |
| vitalbox | Франшиза | Сложный |

### Запуск

```bash
# Список сценариев
python scripts/run_test.py --list

# Один сценарий
python scripts/run_test.py logistics_company

# Тихий режим
python scripts/run_test.py logistics_company --quiet

# Полный pipeline (тест + ревью анкеты)
python scripts/run_pipeline.py logistics_company

# С документами клиента
python scripts/run_test.py logistics_company --input-dir input/test_docs/
```

### Критерии прохождения

| Проверка | Описание | Критерий |
|----------|----------|----------|
| completeness | Обязательные поля заполнены | ≥90% полей |
| data_quality | Данные валидны (не мусор) | 0 ошибок |
| scenario_match | Соответствие YAML-сценарию | ≥80% match |
| phases | Все 4 фазы пройдены | 4/4 |
| no_loops | Нет зацикливания | <50 turns |
| validation_score | Общий скор | ≥0.8 |

### Результаты

После успешного теста:
- `output/tests/{scenario}_{timestamp}.json` — полный отчёт
- `output/tests/{scenario}_{timestamp}.md` — человекочитаемый отчёт
- Console: Rich-таблица с результатами

---

## Этап 4: Голосовой агент (E2E)

### Требования

- LiveKit Server запущен
- Azure OpenAI Realtime API настроен
- Node.js + Puppeteer установлены

### Подготовка

```bash
# Установка Puppeteer
npm install puppeteer

# Создание тестового аудио (macOS)
say -v Yuri "Привет, меня зовут Иван" -o test.aiff
ffmpeg -i test.aiff -ar 48000 -ac 1 tests/fixtures/test_speech_ru.wav -y
```

### Запуск

```bash
# Терминал 1: Сервер
python scripts/run_server.py

# Терминал 2: Голосовой агент
python scripts/run_voice_agent.py dev

# Терминал 3: E2E тест
node tests/e2e_voice_test.js
```

### Критерии прохождения

| Этап | Проверка |
|------|----------|
| Browser launch | Chrome с fake audio запускается |
| Page load | UI загружается без ошибок |
| LiveKit connection | Подключение к комнате успешно |
| Audio published | Микрофон опубликован |
| Agent greeting | Агент приветствует пользователя |
| STT transcription | Речь распознаётся |
| Agent response | Агент отвечает на вопросы |

---

## Этап 5: Проверка подключений к сервисам

**ВАЖНО:** Этот этап проверяет **реальные подключения**, а не просто наличие конфигурации.

### Предварительные требования

Перед проверкой Redis и PostgreSQL необходимо запустить сервисы:

```bash
# 1. Проверить что Docker установлен и запущен
docker --version
docker info > /dev/null 2>&1 && echo "Docker: ✅ Running" || echo "Docker: ❌ Not running"

# 2. Запустить Redis и PostgreSQL через Docker Compose
docker-compose -f config/docker-compose.yml up -d redis postgres

# 3. Дождаться готовности (10-15 секунд)
sleep 10

# 4. Проверить статус контейнеров
docker-compose -f config/docker-compose.yml ps
```

**Альтернатива без Docker (локальная установка):**

```bash
# macOS
brew install redis postgresql
brew services start redis
brew services start postgresql

# Ubuntu/Debian
sudo apt install redis-server postgresql
sudo systemctl start redis postgresql
```

### 5.1 DeepSeek API

```bash
# Проверка подключения к DeepSeek
python -c "
import asyncio
from src.llm.deepseek import DeepSeekClient

async def test():
    client = DeepSeekClient()
    try:
        response = await client.chat([{'role': 'user', 'content': 'ping'}])
        print(f'✅ DeepSeek API: Connected, response length: {len(response)}')
    except Exception as e:
        print(f'❌ DeepSeek API: {e}')

asyncio.run(test())
"
```

| Проверка | Критерий |
|----------|----------|
| Подключение | Response получен |
| API Key | Не возвращает 401/403 |

### 5.2 Redis

```bash
# Проверка подключения к Redis
python -c "
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

async def test():
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    print(f'REDIS_URL: {redis_url}')
    try:
        import redis.asyncio as redis
        client = redis.from_url(redis_url)
        await client.ping()
        print('✅ Redis: Connected')
        await client.close()
    except Exception as e:
        print(f'❌ Redis: {e}')

asyncio.run(test())
"
```

| Проверка | Критерий |
|----------|----------|
| Подключение | PING возвращает PONG |
| Статус | Для dev — опционально, для prod — обязательно |

### 5.3 PostgreSQL

```bash
# Проверка подключения к PostgreSQL
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

db_url = os.getenv('DATABASE_URL', '')
print(f'DATABASE_URL: {db_url[:50]}...' if len(db_url) > 50 else f'DATABASE_URL: {db_url or \"Not set\"}')

if not db_url or 'sqlite' in db_url.lower():
    print('⚠️ PostgreSQL: Not configured (using SQLite fallback)')
else:
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
            print('✅ PostgreSQL: Connected')
    except Exception as e:
        print(f'❌ PostgreSQL: {e}')
"
```

| Проверка | Критерий |
|----------|----------|
| Подключение | SELECT 1 выполняется |
| Таблицы | `psql -f config/init_db.sql` выполнен |
| Статус | Для dev — SQLite OK, для prod — PostgreSQL обязателен |

### 5.4 LiveKit

```bash
# Проверка подключения к LiveKit
python -c "
import os
import asyncio
from dotenv import load_dotenv
load_dotenv()

async def test():
    livekit_url = os.getenv('LIVEKIT_URL', '')
    livekit_key = os.getenv('LIVEKIT_API_KEY', '')
    livekit_secret = os.getenv('LIVEKIT_API_SECRET', '')

    print(f'LIVEKIT_URL: {livekit_url}')
    print(f'LIVEKIT_API_KEY: {\"✅ Set\" if livekit_key else \"❌ Missing\"}')
    print(f'LIVEKIT_API_SECRET: {\"✅ Set\" if livekit_secret else \"❌ Missing\"}')

    if not all([livekit_url, livekit_key, livekit_secret]):
        print('⚠️ LiveKit: Incomplete configuration')
        return

    try:
        from livekit import api
        lkapi = api.LiveKitAPI(livekit_url, livekit_key, livekit_secret)
        rooms = await lkapi.room.list_rooms(api.ListRoomsRequest())
        print(f'✅ LiveKit: Connected, {len(rooms.rooms)} active rooms')
        await lkapi.aclose()
    except Exception as e:
        print(f'❌ LiveKit: {e}')

asyncio.run(test())
"
```

| Проверка | Критерий |
|----------|----------|
| Подключение | list_rooms выполняется |
| Credentials | API Key + Secret валидны |
| Статус | Для голосового режима — обязательно |

### 5.5 Сводная таблица подключений

| Сервис | Текстовый режим | Голосовой режим | High-load prod |
|--------|-----------------|-----------------|----------------|
| DeepSeek API | ✅ Обязательно | ✅ Обязательно | ✅ Обязательно |
| SQLite | ✅ Достаточно | ✅ Достаточно | ❌ Недостаточно |
| PostgreSQL | ⚠️ Опционально | ⚠️ Опционально | ✅ Обязательно |
| Redis | ⚠️ Опционально | ⚠️ Опционально | ✅ Обязательно |
| LiveKit | ❌ Не нужен | ✅ Обязательно | ✅ Обязательно |

### Docker Compose (для локальной инфраструктуры)

```bash
# Запуск Redis + PostgreSQL
docker-compose -f config/docker-compose.yml up -d

# Проверка статуса
docker-compose -f config/docker-compose.yml ps

# Логи
docker-compose -f config/docker-compose.yml logs -f
```

---

## Этап 6: Production Readiness

### 6.1 Чек-лист конфигурации (.env)

| Параметр | Описание | Проверка |
|----------|----------|----------|
| DEEPSEEK_API_KEY | API ключ DeepSeek | `python -c "..."` из 5.1 |
| DEEPSEEK_BASE_URL | Endpoint API | По умолчанию `https://api.deepseek.com` |
| LIVEKIT_URL | WebSocket URL LiveKit | `python -c "..."` из 5.4 |
| LIVEKIT_API_KEY | Ключ LiveKit | Проверяется в 5.4 |
| LIVEKIT_API_SECRET | Секрет LiveKit | Проверяется в 5.4 |
| DATABASE_URL | PostgreSQL connection string | `python -c "..."` из 5.3 |
| REDIS_URL | Redis connection string | `python -c "..."` из 5.2 |

### 6.2 Чек-лист файлов и директорий

```bash
# Проверка директорий и прав
echo "=== Directories ===" && \
[ -d "output" ] && [ -w "output" ] && echo "output/: ✅" || echo "output/: ❌" && \
[ -d "logs" ] && [ -w "logs" ] && echo "logs/: ✅" || echo "logs/: ❌" && \
[ -d "data" ] && [ -w "data" ] && echo "data/: ✅" || echo "data/: ❌"

# Проверка .env безопасности
echo "=== Security ===" && \
grep -q "^\.env$" .gitignore && echo ".env in .gitignore: ✅" || echo ".env in .gitignore: ❌" && \
git ls-files --error-unmatch .env 2>/dev/null && echo ".env tracked: ❌ DANGER!" || echo ".env NOT tracked: ✅"
```

### 6.3 Чек-лист API endpoints

```bash
# Проверка работы API (требует запущенный сервер)
python -c "
import asyncio
from httpx import ASGITransport, AsyncClient
from src.web.server import app

async def test():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        # Root endpoint
        resp = await ac.get('/')
        print(f'GET /: {resp.status_code}')

        # Create session
        resp = await ac.post('/api/session/create', json={'pattern': 'interaction'})
        print(f'POST /api/session/create: {resp.status_code}')

        if resp.status_code == 200:
            session_id = resp.json().get('session_id', '')[:8]
            print(f'Session created: {session_id}...')

asyncio.run(test())
"
```

### 6.4 Запуск

```bash
# Development
python scripts/run_server.py

# Production (с gunicorn)
gunicorn src.web.server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### 6.5 Smoke test после запуска

```bash
# При запущенном сервере (localhost:8000)

# 1. Создание сессии
curl -X POST http://localhost:8000/api/session/create \
  -H "Content-Type: application/json" \
  -d '{"pattern": "interaction"}'

# 2. Открыть UI в браузере
open http://localhost:8000/
```

---

## Быстрая проверка (10 минут)

Минимальный набор команд для проверки работоспособности:

```bash
# 1. Юнит-тесты (должны пройти все)
pytest --tb=short

# 2. Покрытие (должно быть ≥50%)
pytest --cov=src --cov-report=term | tail -5

# 3. DeepSeek API (реальное подключение)
python -c "
import asyncio
from src.llm.deepseek import DeepSeekClient
async def test():
    c = DeepSeekClient()
    r = await c.chat([{'role': 'user', 'content': 'ping'}])
    print(f'✅ DeepSeek: {len(r)} chars')
asyncio.run(test())
"

# 4. LiveKit (реальное подключение)
python -c "
import asyncio, os
from dotenv import load_dotenv
from livekit import api
load_dotenv()
async def test():
    lk = api.LiveKitAPI(os.getenv('LIVEKIT_URL'), os.getenv('LIVEKIT_API_KEY'), os.getenv('LIVEKIT_API_SECRET'))
    rooms = await lk.room.list_rooms(api.ListRoomsRequest())
    print(f'✅ LiveKit: {len(rooms.rooms)} rooms')
    await lk.aclose()
asyncio.run(test())
"

# 5. LLM-симуляция (один сценарий)
python scripts/run_test.py auto_service --quiet
```

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError` | Активируйте venv: `source venv/bin/activate` |
| `pytest: command not found` | `pip install pytest pytest-cov pytest-asyncio` |
| `DeepSeek API error 400` | Проверьте DEEPSEEK_API_KEY в .env |
| `Redis connection refused` | Запустите Redis: `redis-server` |
| `PostgreSQL connection failed` | Проверьте DATABASE_URL и что postgres запущен |
| `LiveKit connection failed` | Проверьте LIVEKIT_URL и что сервер запущен |
| Тест зависает | Добавьте `--timeout=60` к pytest |
| Пустая анкета после теста | Проверьте логи в `logs/anketa.log` |

---

## Автоматизация (CI/CD)

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install -r requirements.txt
      - run: pytest --cov=src --cov-fail-under=50
```

### Pre-commit hook

```bash
# .git/hooks/pre-commit
#!/bin/sh
pytest --tb=short -q
```
