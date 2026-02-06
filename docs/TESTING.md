# Методология тестирования и проверки готовности

Полный чек-лист для проверки работоспособности проекта и готовности к запуску.

## Обзор

| Этап | Что проверяем | Инструмент | Критерий прохождения |
|------|---------------|------------|---------------------|
| 1. Юнит-тесты | Логика модулей | pytest | 100% passed, coverage ≥50% |
| 2. Интеграция | Связи между модулями | pytest + fixtures | Все интеграционные тесты passed |
| 3. LLM-симуляция | Полный цикл консультации | run_test.py | validation score ≥0.8 |
| 4. Голосовой агент | WebRTC + STT/TTS | e2e_voice_test.js | Все этапы passed |
| 5. Инфраструктура | Redis, PostgreSQL, LiveKit | health checks | Все сервисы online |
| 6. Production readiness | .env, логи, мониторинг | manual check | Чек-лист выполнен |

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

## Этап 5: Инфраструктура

### Проверка сервисов

```bash
# Redis
redis-cli ping
# Ожидаемый ответ: PONG

# PostgreSQL
psql -U postgres -c "SELECT 1"
# Ожидаемый ответ: 1

# LiveKit (если локально)
curl http://localhost:7880/healthcheck
# Ожидаемый ответ: OK
```

### Docker Compose (опционально)

```bash
# Запуск всех сервисов
docker-compose -f config/docker-compose.yml up -d

# Проверка статуса
docker-compose -f config/docker-compose.yml ps
```

### Health endpoints

| Сервис | Endpoint | Ожидаемый ответ |
|--------|----------|-----------------|
| FastAPI | GET /health | `{"status": "ok"}` |
| Redis | redis-cli ping | PONG |
| PostgreSQL | SELECT 1 | 1 |

---

## Этап 6: Production Readiness

### Чек-лист перед запуском

#### Конфигурация (.env)

- [ ] DEEPSEEK_API_KEY — валидный ключ
- [ ] DEEPSEEK_BASE_URL — правильный endpoint
- [ ] LIVEKIT_URL — URL LiveKit сервера
- [ ] LIVEKIT_API_KEY — ключ LiveKit
- [ ] LIVEKIT_API_SECRET — секрет LiveKit
- [ ] AZURE_OPENAI_ENDPOINT — endpoint Azure (для голоса)
- [ ] AZURE_OPENAI_API_KEY — ключ Azure
- [ ] DATABASE_URL — PostgreSQL connection string
- [ ] REDIS_URL — Redis connection string

#### Файлы и директории

- [ ] `output/` — создана, права на запись
- [ ] `logs/` — создана, права на запись
- [ ] `data/` — создана (для SQLite)
- [ ] `.env` — существует, не в git

#### Базы данных

- [ ] PostgreSQL: таблицы созданы (`psql -f config/init_db.sql`)
- [ ] Redis: доступен, ping работает
- [ ] SQLite: `data/sessions.db` создаётся автоматически

#### Логирование

- [ ] `logs/` содержит файлы после запуска
- [ ] Ошибки пишутся в `logs/errors.log`
- [ ] Уровень логов настроен (INFO для prod)

### Запуск

```bash
# Development
python scripts/run_server.py

# Production (с gunicorn)
gunicorn src.web.server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Smoke test после запуска

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Создание сессии
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"pattern": "interaction"}'

# 3. Открыть UI в браузере
open http://localhost:8000/
```

---

## Быстрая проверка (5 минут)

Минимальный набор команд для проверки работоспособности:

```bash
# 1. Юнит-тесты (должны пройти все)
pytest --tb=short

# 2. Покрытие (должно быть ≥50%)
pytest --cov=src --cov-report=term | tail -5

# 3. Сервер запускается
timeout 10 python scripts/run_server.py &
sleep 3
curl -s http://localhost:8000/health | grep ok

# 4. LLM работает (нужен API key)
python -c "from src.llm.deepseek import DeepSeekClient; import asyncio; c = DeepSeekClient(); print(asyncio.run(c.chat([{'role': 'user', 'content': 'ping'}]))[:50])"
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
