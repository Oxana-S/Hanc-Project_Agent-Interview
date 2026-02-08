# Методология тестирования и проверки готовности

Полный чек-лист для проверки работоспособности проекта и готовности к запуску.

## Обзор

| Этап | Что проверяем | Инструмент | Критерий прохождения |
|------|---------------|------------|----------------------|
| 1. Юнит-тесты | Логика модулей | pytest | 100% passed, coverage ≥50% |
| 2. Интеграция | Связи между модулями | pytest + fixtures | Все интеграционные тесты passed |
| 3. LLM-симуляция | Полный цикл консультации | run_test.py | 4/4 фазы, анкета сгенерирована |
| 4. Голосовой агент | WebRTC + STT/TTS | e2e_voice_test.js | Все этапы passed |
| 5. Подключения | DeepSeek, Azure OpenAI, Redis, PostgreSQL, LiveKit | python scripts | Реальные соединения установлены |
| 6. Production readiness | .env, директории, API | чек-лист + smoke test | Все проверки пройдены |
| 7. Обогащение контекста | Knowledge Base, Documents, Learnings | python scripts | Профили валидны, контекст генерируется |
| 8. Мульти-региональная KB | 960 YAML-профилей, 23 страны | validate scripts | 0 errors, 0 deep warnings |

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

- **LLM провайдер** (один из):
  - DeepSeek: `DEEPSEEK_API_KEY` в .env, баланс на аккаунте
  - Azure OpenAI: `AZURE_CHAT_OPENAI_KEY`, `AZURE_CHAT_OPENAI_ENDPOINT`, `AZURE_CHAT_OPENAI_DEPLOYMENT_NAME` в .env
- Переменная `LLM_PROVIDER` определяет активного провайдера (`azure` по умолчанию, `deepseek` — альтернативный)
- Фабрика клиентов: `src/llm/factory.py` → `create_llm_client(provider)`

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

### 5.5 Azure OpenAI API

```bash
# Проверка подключения к Azure OpenAI
python -c "
import asyncio
from src.llm.azure_chat import AzureChatClient

async def test():
    client = AzureChatClient()
    try:
        response = await client.chat(
            messages=[{'role': 'user', 'content': 'ping'}],
            max_tokens=50
        )
        print(f'✅ Azure OpenAI: Connected, response length: {len(response)}')
    except Exception as e:
        print(f'❌ Azure OpenAI: {e}')

asyncio.run(test())
"
```

| Проверка | Критерий |
|----------|----------|
| Подключение | Response получен без ошибок |
| API Key | Не возвращает 401/403 |
| Deployment | Указанная модель доступна |

**Альтернативно**, через LLM Factory (универсальная проверка):

```bash
python -c "
import asyncio
from src.llm.factory import create_llm_client

async def test():
    client = create_llm_client('azure')
    r = await client.chat([{'role': 'user', 'content': 'ping'}], max_tokens=50)
    print(f'✅ Azure OpenAI (via factory): {len(r)} chars')

asyncio.run(test())
"
```

### 5.6 Сводная таблица подключений

| Сервис | Текстовый режим | Голосовой режим | High-load prod |
|--------|-----------------|-----------------|----------------|
| LLM API (DeepSeek / Azure OpenAI) | ✅ Обязательно (один из) | ✅ Обязательно | ✅ Обязательно |
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
| LLM_PROVIDER | Активный LLM провайдер (`azure` / `deepseek`) | По умолчанию `azure` |
| DEEPSEEK_API_KEY | API ключ DeepSeek | `python -c "..."` из 5.1 |
| DEEPSEEK_BASE_URL | Endpoint API | По умолчанию `https://api.deepseek.com` |
| AZURE_CHAT_OPENAI_KEY | API ключ Azure OpenAI | `python -c "..."` из 5.5 |
| AZURE_CHAT_OPENAI_ENDPOINT | Endpoint Azure OpenAI | Формат: `https://<resource>.openai.azure.com/` |
| AZURE_CHAT_OPENAI_DEPLOYMENT_NAME | Имя deployment модели | Например: `gpt-4.1-mini-dev-gs-swedencentral` |
| AZURE_CHAT_OPENAI_API_VERSION | Версия API | По умолчанию `2024-12-01-preview` |
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

# 5. Azure OpenAI (реальное подключение)
python -c "
import asyncio
from src.llm.azure_chat import AzureChatClient
async def test():
    c = AzureChatClient()
    r = await c.chat([{'role': 'user', 'content': 'ping'}], max_tokens=50)
    print(f'✅ Azure OpenAI: {len(r)} chars')
asyncio.run(test())
"

# 6. LLM-симуляция (один сценарий)
python scripts/run_test.py auto_service --quiet

# 7. Knowledge Base валидация (960 профилей)
python scripts/validate_all_profiles.py --errors-only
python scripts/validate_deep.py
```

---

## Этап 7: Модуль обогащения контекста

### 7.1 Проверка Knowledge Base

```bash
# Валидация всех профилей отраслей
python -c "
from src.knowledge import IndustryKnowledgeManager
from src.knowledge.validator import ProfileValidator

manager = IndustryKnowledgeManager()
validator = ProfileValidator()

for industry_id in manager.get_all_industries():
    profile = manager.get_profile(industry_id)
    result = validator.validate(profile)
    status = '✅' if result.is_valid else '⚠️'
    print(f'{status} {industry_id}: {result.completeness_score:.0%}')
    for w in result.warnings[:2]:
        print(f'   └─ {w}')
"
```

### 7.2 Проверка EnrichedContextBuilder

```bash
# Тест генерации контекста для всех фаз
python -c "
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder

manager = IndustryKnowledgeManager()
builder = EnrichedContextBuilder(manager)

dialogue = [{'role': 'user', 'content': 'Мы автосервис, занимаемся ремонтом машин'}]

for phase in ['discovery', 'analysis', 'proposal', 'refinement']:
    context = builder.build_for_phase(phase, dialogue)
    has_learnings = 'НАКОПЛЕННЫЙ ОПЫТ' in context
    print(f'{phase}: {len(context)} chars, learnings: {has_learnings}')
"
```

### 7.3 Проверка Voice интеграции

```bash
# Проверка что Voice Agent получает отраслевой контекст
python -c "
from src.voice.consultant import get_enriched_system_prompt

dialogue = [
    {'role': 'assistant', 'content': 'Здравствуйте! Расскажите о вашем бизнесе.'},
    {'role': 'user', 'content': 'У нас клиника, записываем пациентов на приём'}
]

prompt = get_enriched_system_prompt(dialogue)
print(f'Prompt length: {len(prompt)} chars')
has_context = 'Контекст отрасли' in prompt
print(f'Contains industry context: {has_context}')
"
```

### 7.4 Тесты модуля обогащения

```bash
# Запуск unit-тестов для модуля обогащения
pytest tests/unit/test_enriched_context.py -v

# С покрытием
pytest tests/unit/test_enriched_context.py --cov=src/knowledge --cov-report=term-missing
```

### 7.5 Сводная таблица

| Проверка | Критерий |
|----------|----------|
| Профили валидны | Все профили ≥70% completeness |
| Контекст генерируется | Все 4 фазы возвращают непустой контекст |
| Learnings включены | Контекст содержит накопленный опыт |
| Voice интеграция | Голосовой агент получает отраслевой контекст |
| Тесты проходят | 25/25 tests passed |

---

## Этап 8: Мульти-региональная Knowledge Base (валидация и ремонт)

Проект содержит **960 YAML-профилей** (40 отраслей × 23 страны + 40 базовых), покрывающих 7 регионов: EU, NA, LATAM, MENA, SEA, RU и базовые профили (`_base`).

### 8.1 Базовая валидация (L1–L5)

Скрипт `validate_all_profiles.py` проверяет 5 уровней:

| Уровень | Что проверяет |
|---------|---------------|
| L1 | Структурная целостность — обязательные поля, минимальные количества |
| L2 | Полнота контента — наличие v2.0 секций (competitors, pricing_context, market_context) |
| L3 | Корректность метаданных — meta.id, region, country, language, currency |
| L4 | Качество локализации — язык соответствует стране, локальные конкуренты |
| L5 | Валидность значений — severity/priority enums (high/medium/low), числовые цены |

```bash
# Полная базовая валидация (все 960 профилей)
python scripts/validate_all_profiles.py

# С подробным выводом
python scripts/validate_all_profiles.py --verbose

# По конкретному региону
python scripts/validate_all_profiles.py --region eu

# Только ошибки (без предупреждений)
python scripts/validate_all_profiles.py --errors-only
```

**Критерий прохождения:** 920/920 региональных профилей valid, 0 errors.

### 8.2 Глубокая валидация (L6–L11)

Скрипт `validate_deep.py` выполняет расширенные проверки:

| Уровень | Что проверяет |
|---------|---------------|
| L6 | Качество контента — дубликаты, минимальная длина, обрезанные описания |
| L7 | Глубина локализации — эвристики языкового соответствия по Unicode-скриптам |
| L8 | Кросс-профильная консистентность — матрица покрытия, идентичные профили, _extends |
| L9 | Качество sales scripts — уникальность trigger, effectiveness, длина скриптов |
| L10 | Когерентность pricing — entry_point в range, payback_months (1–36), ROI-примеры |
| L11 | Целостность данных — размер файлов, None-значения, YAML re-serializability |

```bash
# Глубокая валидация
python scripts/validate_deep.py

# С подробным выводом
python scripts/validate_deep.py --verbose
```

**Критерий прохождения:** 0 errors, 0 warnings (info — допустимо).

### 8.3 Инструментарий ремонта профилей

При обнаружении проблем используются специализированные скрипты:

| Скрипт | Назначение | Что исправляет |
|--------|------------|----------------|
| `fix_enums.py` | Нормализация enum-значений | hoch→high, mittel→medium, alto→high и т.д. для 11+ языков |
| `fix_aliases.py` | Генерация aliases | Добавляет блок `aliases` с 3–6 синонимами отрасли |
| `fix_entry_points.py` | Числовые entry_point | "150 CHF für..."→150, "$65"→65, "Rp 50.000"→50000 |
| `fix_incomplete_profiles.py` | Дополнение профилей (LLM) | Генерирует отсутствующие секции через Azure OpenAI |
| `fix_l2_subfields.py` | Дополнение sub-fields (LLM) | Добавляет sales_scripts, competitors, seasonality, roi_examples |
| `fix_l10_pricing.py` | Исправление pricing | payback=0→1, non-numeric→число, payback>36→пересчёт |

```bash
# Примеры запуска
python scripts/fix_enums.py
python scripts/fix_aliases.py
python scripts/fix_entry_points.py
python scripts/fix_l10_pricing.py

# LLM-скрипты (требуют Azure OpenAI API)
python scripts/fix_incomplete_profiles.py --provider=azure
python scripts/fix_l2_subfields.py --provider=azure
```

### 8.4 Генерация профилей

Для создания новых региональных профилей используется `generate_profiles.py`:

```bash
# Генерация профилей для конкретной страны
python scripts/generate_profiles.py --country de --provider azure

# Генерация всех профилей для региона
python scripts/generate_profiles.py --region eu --provider azure

# Список поддерживаемых стран
python scripts/generate_profiles.py --list-countries
```

**Поддерживаемые провайдеры:** `azure` (по умолчанию), `deepseek`.

### 8.5 Сводная таблица

| Проверка | Критерий |
|----------|----------|
| Базовая валидация (L1–L5) | 920/920 valid, 0 errors |
| Глубокая валидация (L6–L11) | 0 errors, 0 warnings |
| Покрытие стран | 23/23 страны, все 40 отраслей |
| Enum-значения | Только English: high, medium, low |
| entry_point / budget | Числовые значения, без текста |
| ROI payback_months | 1–36, числовые |
| sales_scripts | ≥3 на профиль, trigger уникальны |
| competitors | ≥2 на профиль, реальные компании |
| Языковая локализация | Контент на языке страны |

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError` | Активируйте venv: `source venv/bin/activate` |
| `pytest: command not found` | `pip install pytest pytest-cov pytest-asyncio` |
| `DeepSeek API error 400` | Проверьте DEEPSEEK_API_KEY в .env |
| `Azure OpenAI 401/403` | Проверьте AZURE_CHAT_OPENAI_KEY и AZURE_CHAT_OPENAI_ENDPOINT в .env |
| `Azure OpenAI deployment not found` | Проверьте AZURE_CHAT_OPENAI_DEPLOYMENT_NAME — должно совпадать с deployment в Azure Portal |
| `Redis connection refused` | Запустите Redis: `redis-server` |
| `PostgreSQL connection failed` | Проверьте DATABASE_URL и что postgres запущен |
| `LiveKit connection failed` | Проверьте LIVEKIT_URL и что сервер запущен |
| Тест зависает | Добавьте `--timeout=60` к pytest |
| Пустая анкета после теста | Проверьте логи в `logs/anketa.log` |
| KB валидация: non-numeric entry_point | Запустите `python scripts/fix_entry_points.py` |
| KB валидация: enum не English | Запустите `python scripts/fix_enums.py` |
| KB валидация: payback_months=0 или >36 | Запустите `python scripts/fix_l10_pricing.py` |
| KB валидация: отсутствуют секции | Запустите `python scripts/fix_incomplete_profiles.py --provider=azure` |
| KB: "Rp 50.000" парсится как 50 | Индонезийская точка = разделитель тысяч, исправьте вручную на 50000 |

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
