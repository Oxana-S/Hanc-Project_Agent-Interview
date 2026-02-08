# Методология тестирования и проверки готовности

Полный чек-лист для проверки работоспособности проекта и готовности к запуску.

## Обзор

Этапы упорядочены по принципу зависимостей: **дешёвые оффлайн-проверки → конфигурация → подключения → функциональные тесты**.

| Этап | Что проверяем | Инструмент | Критерий прохождения |
|------|---------------|------------|----------------------|
| 1. Юнит-тесты | Логика модулей | pytest | 100% passed, coverage ≥50% |
| 2. Интеграция | Связи между модулями | pytest + fixtures | Все интеграционные тесты passed |
| 3. Мульти-региональная KB | 968 YAML-профилей, 23 страны | validate scripts | 0 errors, 0 deep warnings |
| 4. Production readiness | .env, директории, API | чек-лист + smoke test | Все проверки пройдены |
| 5. Подключения | DeepSeek, Azure OpenAI, Redis, PostgreSQL, LiveKit | python scripts | Реальные соединения установлены |
| 6. Обогащение контекста | Knowledge Base, Documents, Learnings | python scripts | Профили валидны, контекст генерируется |
| 6.5. Парсинг документов | PDF, DOCX, XLSX, TXT, MD из input/ | test_document_parsing.py | 25/25 файлов, 5 форматов, 5 папок |
| 7. LLM-симуляция | Полный цикл консультации | run_test.py | 4/4 фазы, анкета сгенерирована |
| 7.5. LLM + документы | Симуляция с --input-dir | run_test.py --input-dir | Документы загружены, контекст в консультации |
| 8. Голосовой агент | WebRTC + STT/TTS | e2e_voice_test.js | Все этапы passed |

**Фазы:**
- **Фаза A (Оффлайн):** Этапы 1–3 — не требуют внешних сервисов
- **Фаза B (Конфигурация):** Этап 4 — проверка .env и инфраструктуры
- **Фаза C (Подключения):** Этап 5 — реальные соединения к сервисам
- **Фаза D (Функциональные):** Этапы 6–8 — требуют живых API

---

## Этап 1: Юнит-тесты

### 1.1 Требования

- Python 3.11+ (рекомендуется 3.14)
- Virtual environment активирован
- Зависимости установлены: `pip install -r requirements.txt`

### 1.2 Запуск

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

### 1.3 Критерии прохождения

| Метрика | Минимум | Текущее значение |
|---------|---------|------------------|
| Тесты passed | 100% | 972/972 |
| Coverage | ≥50% | 50% |
| Критические модули | ≥80% | см. таблицу ниже |

### 1.4 Покрытие по модулям

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

### 1.5 Структура тестов

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

### 2.1 Проверка связей

```bash
# Тесты с реальными fixtures
pytest tests/unit/test_api_server.py -v

# Проверка полного flow анкеты
pytest tests/unit/test_data_cleaner.py::TestAnketaPostProcessor -v
```

### 2.2 Критерии

- Все API endpoints возвращают корректные статусы
- Session flow работает: create → update → complete
- Anketa extraction из диалога работает

---

## Этап 3: Мульти-региональная Knowledge Base (валидация и ремонт)

Проект содержит **968 YAML-профилей** (40 отраслей × 23 страны + 40 базовых), покрывающих 7 регионов: EU, NA, LATAM, MENA, SEA, RU и базовые профили (`_base`).

> **Почему этот этап идёт третьим:** KB валидация — полностью оффлайн-операция (не требует API-ключей или внешних сервисов). Выявляет проблемы данных до того, как они повлияют на функциональные тесты в этапах 6–8.

### 3.1 Базовая валидация (L1–L5)

Скрипт `validate_all_profiles.py` проверяет 5 уровней:

| Уровень | Что проверяет |
|---------|---------------|
| L1 | Структурная целостность — обязательные поля, минимальные количества |
| L2 | Полнота контента — наличие v2.0 секций (competitors, pricing_context, market_context) |
| L3 | Корректность метаданных — meta.id, region, country, language, currency |
| L4 | Качество локализации — язык соответствует стране, локальные конкуренты |
| L5 | Валидность значений — severity/priority enums (high/medium/low), числовые цены |

```bash
# Полная базовая валидация (все 968 профилей)
python scripts/validate_all_profiles.py

# С подробным выводом
python scripts/validate_all_profiles.py --verbose

# По конкретному региону
python scripts/validate_all_profiles.py --region eu

# Только ошибки (без предупреждений)
python scripts/validate_all_profiles.py --errors-only
```

**Критерий прохождения:** 928/928 региональных профилей valid, 0 errors.

### 3.2 Глубокая валидация (L6–L11)

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

### 3.3 Инструментарий ремонта профилей

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

### 3.4 Генерация профилей

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

### 3.5 Сводная таблица

| Проверка | Критерий |
|----------|----------|
| Базовая валидация (L1–L5) | 928/928 valid, 0 errors |
| Глубокая валидация (L6–L11) | 0 errors, 0 warnings |
| Покрытие стран | 23/23 страны, все 40 отраслей |
| Enum-значения | Только English: high, medium, low |
| entry_point / budget | Числовые значения, без текста |
| ROI payback_months | 1–36, числовые |
| sales_scripts | ≥3 на профиль, trigger уникальны |
| competitors | ≥2 на профиль, реальные компании |
| Языковая локализация | Контент на языке страны |

---

## Этап 4: Production Readiness

> **Почему этот этап перед подключениями:** Проверяем, что конфигурация корректна **до** попыток подключения к сервисам. Если .env не настроен — подключения гарантированно провалятся. Проверки подключений — см. Этап 5.

### 4.1 Чек-лист конфигурации (.env)

| Параметр | Описание | Проверка |
|----------|----------|----------|
| LLM_PROVIDER | Активный LLM провайдер (`azure` / `deepseek`) | По умолчанию `azure` |
| DEEPSEEK_API_KEY | API ключ DeepSeek | Задан, не пустой (подключение → Этап 5.1) |
| DEEPSEEK_API_ENDPOINT | Endpoint API | По умолчанию `https://api.deepseek.com/v1` |
| AZURE_CHAT_OPENAI_API_KEY | API ключ Azure OpenAI | Задан, не пустой (подключение → Этап 5.5) |
| AZURE_CHAT_OPENAI_ENDPOINT | Endpoint Azure OpenAI | Формат: `https://<resource>.openai.azure.com/` |
| AZURE_CHAT_OPENAI_DEPLOYMENT_NAME | Имя deployment модели | Например: `gpt-4.1-mini-dev-gs-swedencentral` |
| AZURE_CHAT_OPENAI_API_VERSION | Версия API | По умолчанию `2024-12-01-preview` |
| LIVEKIT_URL | WebSocket URL LiveKit | Задан (подключение → Этап 5.4) |
| LIVEKIT_API_KEY | Ключ LiveKit | Задан (подключение → Этап 5.4) |
| LIVEKIT_API_SECRET | Секрет LiveKit | Задан (подключение → Этап 5.4) |
| DATABASE_URL | PostgreSQL connection string | Задан (подключение → Этап 5.3) |
| REDIS_URL | Redis connection string | Задан (подключение → Этап 5.2) |

### 4.2 Чек-лист файлов и директорий

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

### 4.3 Чек-лист API endpoints

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

### 4.4 Запуск

```bash
# Development
python scripts/run_server.py

# Production (с gunicorn)
gunicorn src.web.server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### 4.5 Smoke test после запуска

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

## Этап 5: Проверка подключений к сервисам

**ВАЖНО:** Этот этап проверяет **реальные подключения**, а не просто наличие конфигурации (конфигурация проверяется в Этапе 4).

### 5.0 Предварительные требования

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

### 5.7 Docker Compose (для локальной инфраструктуры)

```bash
# Запуск Redis + PostgreSQL
docker-compose -f config/docker-compose.yml up -d

# Проверка статуса
docker-compose -f config/docker-compose.yml ps

# Логи
docker-compose -f config/docker-compose.yml logs -f
```

---

## Этап 6: Модуль обогащения контекста

> **Требования:** Этапы 3 и 5 пройдены (KB валидна, подключения к LLM работают).

### 6.1 Проверка Knowledge Base

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

### 6.2 Проверка EnrichedContextBuilder

```bash
# Тест генерации контекста для всех фаз
python -c "
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder

manager = IndustryKnowledgeManager()
builder = EnrichedContextBuilder(manager, document_context=None)

dialogue = [{'role': 'user', 'content': 'Мы автосервис, занимаемся ремонтом машин'}]

for phase in ['discovery', 'analysis', 'proposal', 'refinement']:
    context = builder.build_for_phase(phase, dialogue)
    has_learnings = 'НАКОПЛЕННЫЙ ОПЫТ' in context
    has_docs = 'ДОКУМЕНТЫ КЛИЕНТА' in context
    print(f'{phase}: {len(context)} chars, learnings: {has_learnings}, docs: {has_docs}')
"
```

### 6.3 Проверка Voice интеграции

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

### 6.4 Тесты модуля обогащения

```bash
# Запуск unit-тестов для модуля обогащения
pytest tests/unit/test_enriched_context.py -v

# С покрытием
pytest tests/unit/test_enriched_context.py --cov=src/knowledge --cov-report=term-missing
```

### 6.5 Сводная таблица

| Проверка | Критерий |
|----------|----------|
| Профили валидны | Все профили ≥70% completeness |
| Контекст генерируется | Все 4 фазы возвращают непустой контекст |
| Learnings включены | Контекст содержит накопленный опыт |
| Voice интеграция | Голосовой агент получает отраслевой контекст |
| Тесты проходят | 25/25 tests passed |

---

## Этап 6.5: Парсинг документов из input/

> **Требования:** Библиотеки PyMuPDF, python-docx, openpyxl установлены. Тестовые документы сгенерированы.

### 6.5.1 Описание

Пользователи размещают документы о своей компании в папках `input/{company_name}/`. DocumentParser парсит файлы, DocumentAnalyzer извлекает контекст, который потом используется в консультации (Stage 7 с `--input-dir`).

### 6.5.2 Поддерживаемые форматы

| Формат | Библиотека | Что извлекается |
|--------|-----------|-----------------|
| PDF | PyMuPDF (fitz) | Текст по страницам, метаданные (title, author) |
| DOCX | python-docx | Параграфы по секциям, таблицы, метаданные |
| XLSX/XLS | openpyxl | Данные по листам, формат: `col1 \| col2 \| col3` |
| MD | regex | Секции по заголовкам `#` |
| TXT | regex | Весь текст как один чанк |

### 6.5.3 Структура input/

```text
input/
├── test_docs/           # ГрузовичкоФ (логистика)
│   ├── test_brief.md    # Бриф (16 строк)
│   ├── company_info.txt # Описание компании
│   ├── data.xlsx        # Прайс-лист + скидки
│   ├── commercial_offer.docx  # Коммерческое предложение
│   └── presentation.pdf # Презентация (3 стр.)
├── restaurant_italiano/ # Bella Italia (HoReCa)
│   ├── brief.md
│   ├── company_info.txt
│   ├── data.xlsx        # Меню + статистика
│   ├── commercial_offer.docx
│   └── presentation.pdf
├── beauty_salon/        # Glamour (wellness)
│   ├── brief.md
│   ├── company_info.txt
│   ├── data.xlsx        # Прайс + загрузка филиалов
│   ├── commercial_offer.docx
│   └── presentation.pdf
├── realestate/          # АН ДомСтрой (недвижимость)
│   ├── brief.md
│   ├── company_info.txt
│   ├── data.xlsx        # Объекты + воронка продаж
│   ├── commercial_offer.docx
│   └── presentation.pdf
└── test/                # АвтоПрофи (автосервис)
    ├── brief.md
    ├── company_info.txt
    ├── data.xlsx        # Прайс-лист
    ├── commercial_offer.docx
    └── presentation.pdf
```

### 6.5.4 Генерация тестовых документов

```bash
# Генерация/регенерация всех тестовых файлов (20 файлов, 5 папок)
python scripts/generate_test_documents.py
```

Скрипт создаёт TXT, XLSX, DOCX, PDF для каждой из 5 компаний и проверяет парсинг.

### 6.5.5 Запуск теста

```bash
# Полный тест парсинга (все 5 папок, все форматы)
python scripts/test_document_parsing.py

# С подробным выводом (preview чанков, контакты, промпт)
python scripts/test_document_parsing.py --verbose

# Конкретная папка
python scripts/test_document_parsing.py --dir input/test_docs
```

### 6.5.6 Что проверяется

| # | Проверка | Описание | Критерий |
|---|----------|----------|----------|
| 1 | Парсинг PDF | PyMuPDF извлекает текст | chunks > 0, words > 0 |
| 2 | Парсинг DOCX | python-docx читает параграфы и таблицы | chunks > 0, words > 0 |
| 3 | Парсинг XLSX | openpyxl читает листы и строки | chunks > 0, words > 0 |
| 4 | Парсинг TXT | Текст читается целиком | chunks > 0, words > 0 |
| 5 | Парсинг MD | Разбивка по заголовкам | chunks > 0, words > 0 |
| 6 | DocumentLoader | Загрузка всех файлов из папки | count == кол-во файлов |
| 7 | DocumentAnalyzer | Извлечение контекста | key_facts > 0, contacts > 0 |
| 8 | to_prompt_context() | Генерация строки для промпта | length > 0 |

### 6.5.7 Критерии прохождения

| Метрика | Критерий | Текущее |
|---------|----------|---------|
| Файлов распарсено | 25/25 | 25/25 ✅ |
| Форматов покрыто | 5/5 (.pdf, .docx, .xlsx, .txt, .md) | 5/5 ✅ |
| Папок протестировано | 5/5 | 5/5 ✅ |
| Analyzer: контакты | ≥1 на папку | 3/папку ✅ |
| Analyzer: prompt context | >0 chars на папку | 1000-1400 chars ✅ |

---

## Этап 7: LLM-симуляция

> **Требования:** Этап 5 пройден (подключение к LLM API работает).

### 7.1 Требования

- **LLM провайдер** (один из):
  - DeepSeek: `DEEPSEEK_API_KEY` в .env, баланс на аккаунте
  - Azure OpenAI: `AZURE_CHAT_OPENAI_KEY`, `AZURE_CHAT_OPENAI_ENDPOINT`, `AZURE_CHAT_OPENAI_DEPLOYMENT_NAME` в .env
- Переменная `LLM_PROVIDER` определяет активного провайдера (`azure` по умолчанию, `deepseek` — альтернативный)
- Фабрика клиентов: `src/llm/factory.py` → `create_llm_client(provider)`

### 7.2 Доступные сценарии

| Сценарий | Отрасль | Сложность |
|----------|---------|-----------|
| auto_service | Автосервис | Базовый |
| auto_service_skeptic | Автосервис | Скептик |
| beauty_salon_glamour | Салон красоты | С документами |
| logistics_company | Логистика | Средний |
| medical_center | Медицина | Средний |
| medical_clinic | Медицина | Детальный |
| online_school | Образование | Средний |
| real_estate_agency | Недвижимость | Средний |
| realestate_domstroy | Недвижимость | С документами |
| restaurant_delivery | HoReCa | Средний |
| restaurant_italiano | HoReCa | Средний |
| vitalbox | Франшиза | Сложный |

### 7.3 Запуск

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

### 7.4 Критерии прохождения

| Проверка | Описание | Критерий |
|----------|----------|----------|
| completeness | Обязательные поля заполнены | ≥90% полей |
| data_quality | Данные валидны (не мусор) | 0 ошибок |
| scenario_match | Соответствие YAML-сценарию | ≥80% match |
| phases | Все 4 фазы пройдены | 4/4 |
| no_loops | Нет зацикливания | <50 turns |
| validation_score | Общий скор | ≥0.8 |

### 7.5 Результаты

После успешного теста:
- `output/tests/{scenario}_{timestamp}.json` — полный отчёт
- `output/tests/{scenario}_{timestamp}.md` — человекочитаемый отчёт
- Console: Rich-таблица с результатами

---

## Этап 7.5: LLM-симуляция с документами

> **Требования:** Этапы 6.5 и 7 пройдены (документы парсятся, симуляция без документов работает).

### 7.5.1 Описание

Проверяет, что документы из `input/` реально подгружаются и влияют на консультацию. Используется флаг `--input-dir`.

### 7.5.2 Запуск

```bash
# Логистика с документами ГрузовичкоФ
python scripts/run_test.py logistics_company --input-dir input/test_docs/

# Автосервис с документами АвтоПрофи
python scripts/run_test.py auto_service --input-dir input/test/

# Ресторан с документами Bella Italia
python scripts/run_test.py restaurant_italiano --input-dir input/restaurant_italiano/
```

### 7.5.3 Что проверяется

| # | Проверка | Описание | Критерий |
|---|----------|----------|----------|
| 1 | Документы загружены | В логе видно `Загружено N документов` | N > 0 |
| 2 | Все форматы прочитаны | MD + TXT + XLSX + DOCX + PDF | 5 файлов |
| 3 | Контекст создан | DocumentAnalyzer возвращает DocumentContext | summary не пустая |
| 4 | Контакты извлечены | Телефон, email из документов | contacts > 0 |
| 5 | Консультация завершена | 4/4 фазы, анкета 100% | status = completed |
| 6 | documents_loaded в отчёте | TestResult содержит список файлов | list не пуст |

### 7.5.4 Критерии прохождения

| Метрика | Критерий |
|---------|----------|
| Документы загружены | 5 файлов из input/test_docs/ |
| Консультация | 4/4 фазы, анкета ≥90% |
| documents_loaded | Непустой список в TestResult |
| Ошибки | 0 ошибок загрузки документов |

### 7.5.5 Конфигурация документов в YAML-сценарии

Альтернативно, можно указать `input_dir` прямо в YAML-сценарии:

```yaml
# tests/scenarios/logistics_company.yaml
persona:
  name: "Дмитрий Волков"
  company: "ГрузовикОнлайн"
  # ...

documents:
  input_dir: "input/test_docs/"
```

При наличии `documents.input_dir` в YAML, флаг `--input-dir` не нужен.

---

## Этап 8: Голосовой агент (E2E)

> **Требования:** Этапы 5–7 пройдены (LiveKit подключён, LLM работает, обогащение контекста валидно).

### 8.0 Проверка окружения

Перед запуском E2E теста убедитесь, что все зависимости установлены:

```bash
# 1. Node.js (требуется v18+)
node --version && echo "Node.js: OK" || echo "Node.js: NOT INSTALLED"

# 2. Puppeteer
node -e "require('puppeteer'); console.log('Puppeteer: OK')" 2>/dev/null || echo "Puppeteer: NOT INSTALLED — run: npm install puppeteer"

# 3. Тестовый аудиофайл
test -f tests/fixtures/test_speech_ru.wav && echo "Test audio: OK" || echo "Test audio: MISSING — see section 8.2"

# 4. livekit-plugins-openai (требуется >= 1.2.18, TurnDetection вместо ServerVadOptions)
python -c "
import importlib.metadata
v = importlib.metadata.version('livekit-plugins-openai')
print(f'livekit-plugins-openai: {v}')
from livekit.plugins.openai.realtime.realtime_model import TurnDetection
print('TurnDetection: OK')
" 2>/dev/null || echo "livekit-plugins-openai: ERROR — run: pip install -U livekit-plugins-openai"

# 5. Веб-сервер и агент не запущены (порт 8000 свободен)
curl -s -o /dev/null http://localhost:8000 && echo "Port 8000: BUSY — kill existing server first" || echo "Port 8000: FREE"
```

### 8.1 Требования

- LiveKit Server запущен (LiveKit Cloud или self-hosted)
- Azure OpenAI Realtime API настроен (`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`)
- Node.js v18+ и Puppeteer установлены
- `livekit-plugins-openai` >= 1.2.18 (используется `TurnDetection` вместо устаревшего `ServerVadOptions`)

### 8.2 Подготовка

```bash
# Установка Puppeteer
npm install puppeteer

# Создание тестового аудио с настоящей речью (macOS)
# ВАЖНО: Puppeteer fake audio отправляет синтетический тон (440 Hz),
# который VAD детектирует, но STT не может транскрибировать.
# Для полноценного теста STT нужен WAV с реальной речью:
say -v Yuri "Привет, меня зовут Иван. Мы занимаемся логистикой." -o test.aiff
ffmpeg -i test.aiff -ar 48000 -ac 1 tests/fixtures/test_speech_ru.wav -y
```

### 8.3 Запуск

```bash
# Терминал 1: Веб-сервер
python -m uvicorn src.web.server:app --host 0.0.0.0 --port 8000

# Терминал 2: Голосовой агент
python scripts/run_voice_agent.py dev

# Терминал 3: E2E тест
node tests/e2e_voice_test.js
```

### 8.4 Критерии прохождения

Проверки разделены на **критические** (блокируют) и **информационные** (зависят от тестового окружения).

#### Критические (must pass — 7/7)

| #   | Проверка             | Описание                                | Статус |
| --- | -------------------- | --------------------------------------- | ------ |
| 1   | Browser launch       | Chrome с fake audio запускается         | ✅     |
| 2   | Page load            | UI загружается без ошибок               | ✅     |
| 3   | LiveKit connection   | Подключение к комнате успешно           | ✅     |
| 4   | Audio published      | Микрофон опубликован в комнату          | ✅     |
| 5   | Agent greeting       | Агент приветствует пользователя         | ✅     |
| 6   | Track subscribed     | Агент подписался на аудиотрек клиента   | ✅     |
| 7   | Agent received audio | Агент получает аудиоданные от клиента   | ✅     |

#### Информационные (зависят от качества тестового аудио)

| #   | Проверка           | Описание                               | Статус |
| --- | ------------------ | -------------------------------------- | ------ |
| 8   | STT transcription  | Речь распознаётся в текст              | ⚠️ *   |
| 9   | Agent response     | Агент отвечает на распознанную речь    | ⚠️ *   |
| 10  | Conversation in UI | В UI больше 1 сообщения (диалог)       | ⚠️ *   |

> \* **Ожидаемое ограничение:** Puppeteer `--use-fake-device-for-media-stream` генерирует
> синтетический тон (440 Hz), а не речь. VAD детектирует его как аудио (проверка #7 проходит),
> но Whisper/STT не может транскрибировать тон в слова (проверка #8 не проходит).
> Без транскрипции агенту не на что отвечать (#9, #10).
>
> **Для 10/10:** замените `tests/fixtures/test_speech_ru.wav` на WAV-файл
> с настоящей речью (см. раздел 8.2).

### 8.5 Результаты тестирования

| Дата       | Критические | Информационные   | Итог |
| ---------- | ----------- | ---------------- | ---- |
| 2026-02-08 | 7/7 ✅      | 0/3 (fake audio) | PASS |

### 8.6 Лог агента

Для диагностики проверяйте `/tmp/agent_entrypoint.log`:

```bash
# Проверка подписки на трек
grep "Track subscribed" /tmp/agent_entrypoint.log

# Проверка состояния пользователя
grep "USER STATE" /tmp/agent_entrypoint.log

# Проверка транскрипции
grep "USER SPEECH" /tmp/agent_entrypoint.log

# Проверка ответов агента
grep "AGENT SPEECH" /tmp/agent_entrypoint.log
```

---

## Быстрая проверка (10 минут)

Минимальный набор команд для проверки работоспособности (порядок соответствует этапам):

```bash
# 1. Юнит-тесты (Этап 1 — должны пройти все)
pytest --tb=short

# 2. Покрытие (Этап 1 — должно быть ≥50%)
pytest --cov=src --cov-report=term | tail -5

# 3. Knowledge Base валидация (Этап 3 — 968 профилей)
python scripts/validate_all_profiles.py --errors-only
python scripts/validate_deep.py

# 4. DeepSeek API (Этап 5 — реальное подключение)
python -c "
import asyncio
from src.llm.deepseek import DeepSeekClient
async def test():
    c = DeepSeekClient()
    r = await c.chat([{'role': 'user', 'content': 'ping'}])
    print(f'✅ DeepSeek: {len(r)} chars')
asyncio.run(test())
"

# 5. Azure OpenAI (Этап 5 — реальное подключение)
python -c "
import asyncio
from src.llm.azure_chat import AzureChatClient
async def test():
    c = AzureChatClient()
    r = await c.chat([{'role': 'user', 'content': 'ping'}], max_tokens=50)
    print(f'✅ Azure OpenAI: {len(r)} chars')
asyncio.run(test())
"

# 6. LiveKit (Этап 5 — реальное подключение)
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

# 6.5. Парсинг документов (Этап 6.5 — все форматы)
python scripts/test_document_parsing.py

# 7. LLM-симуляция (Этап 7 — один сценарий)
python scripts/run_test.py auto_service --quiet

# 7.5. LLM + документы (Этап 7.5 — с input-dir)
python scripts/run_test.py logistics_company --input-dir input/test_docs/ --quiet
```

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
| PDF не парсится | `pip install pymupdf` (библиотека fitz) |
| DOCX не парсится | `pip install python-docx` |
| XLSX не парсится | `pip install openpyxl` |
| Нет тестовых документов в input/ | `python scripts/generate_test_documents.py` |
| DocumentLoader: 0 documents | Проверьте расширения файлов (.pdf, .docx, .md, .xlsx, .txt) |
| `ServerVadOptions` not found | `livekit-plugins-openai` >= 1.2.18 удалил `ServerVadOptions`. Используйте `TurnDetection(type="server_vad", ...)` из `livekit.plugins.openai.realtime.realtime_model` |
| E2E: STT не транскрибирует | Puppeteer fake audio = синтетический тон. Замените `tests/fixtures/test_speech_ru.wav` на WAV с настоящей речью (см. Этап 8.2) |
| E2E: Agent не отвечает | Проверьте `/tmp/agent_entrypoint.log`. Если `STEP 1/5 FAILED` — ошибка SDK. Если `USER STATE: away` — нет аудио |

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
