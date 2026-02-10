# Быстрый старт

Пошаговая инструкция для запуска Hanc.AI Voice Consultant.

## Предварительные требования

- Python 3.9–3.13 (рекомендуется 3.11 или 3.12; Python 3.14+ может иметь проблемы совместимости)
- Для текстового Consultant режима:
  - API ключ DeepSeek
- Для Maximum режима (дополнительно):
  - Docker Compose (для Redis + PostgreSQL)
- Для голосового режима (дополнительно):
  - LiveKit Server (cloud или self-hosted)
  - Azure OpenAI с подключением Realtime API (gpt-4o-realtime-preview)
- Для E2E тестов:
  - Node.js 18+
  - npm/pnpm

## 1. Установка

```bash
# Клонирование
git clone <repo-url>
cd "Project. Agent Interview"

# Виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Зависимости
pip install -r requirements.txt
```

## 2. Конфигурация `.env`

Скопируйте шаблон и заполните свои ключи:

```bash
cp .env.example .env
```

### Минимальная конфигурация (текстовый Consultant)

```env
# === DeepSeek (ОБЯЗАТЕЛЬНО для Consultant режима) ===
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-reasoner
```

### LLM провайдер (для генерации профилей и других модулей)

```env
# === LLM провайдер (используется generate_profiles.py и др.) ===
LLM_PROVIDER=azure  # "azure" (по умолчанию) или "deepseek"

# === Azure Chat OpenAI (если LLM_PROVIDER=azure) ===
AZURE_CHAT_OPENAI_API_KEY=...
AZURE_CHAT_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_CHAT_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini-dev-gs-swedencentral
AZURE_CHAT_OPENAI_API_VERSION=2024-12-01-preview
```

### Голосовой режим (дополнительно)

```env
# === Azure OpenAI Realtime (STT/TTS/LLM для голоса) ===
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-realtime-preview-dev-gs-swedencentral
AZURE_OPENAI_API_VERSION=2024-12-17
AZURE_OPENAI_REALTIME_API_VERSION=2024-10-01-preview

# === LiveKit ===
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=API...
LIVEKIT_API_SECRET=...
```

### Maximum режим (дополнительно)

```env
# === Redis ===
REDIS_URL=redis://localhost:6379

# === PostgreSQL ===
DATABASE_URL=postgresql://interviewer_user:secure_password_123@localhost:5432/voice_interviewer
```

### Общие настройки (опционально)

```env
ENVIRONMENT=development  # development | production
LOG_LEVEL=INFO           # DEBUG | INFO | WARNING | ERROR
```

> Полный список переменных см. в `.env.example`.

## 3. Запуск текстового режима (CLI)

Не требует LiveKit. Работает через DeepSeek API.

```bash
python scripts/consultant_demo.py
```

Что произойдёт:

1. Откроется Rich CLI с AI-консультантом
2. 4 фазы: DISCOVERY → ANALYSIS → PROPOSAL → REFINEMENT
3. Результаты сохранятся в `output/{дата}/{компания}_v{N}/`

## 4. Запуск Maximum Interview режима

Альтернативный текстовый режим с 3-фазной консультацией. Требует Redis и PostgreSQL.

### Шаг 1: Запуск инфраструктуры

```bash
docker compose -f config/docker-compose.yml up -d
```

### Шаг 2: Запуск

```bash
python scripts/demo.py
```

Доступны два подрежима:

1. **MAXIMUM** — полноценный режим с DeepSeek AI (3 фазы: Discovery → Structured → Synthesis)
2. **MOCK** — симуляция без API (для тестирования UI)

Данные сохраняются: Redis (активные сессии) + PostgreSQL (завершённые анкеты).

## 5. Запуск голосового режима

### Шаг 1: Запуск web-сервера

```bash
# Вариант 1: через скрипт (рекомендуется)
./venv/bin/python scripts/run_server.py

# Вариант 2: через uvicorn напрямую
./venv/bin/python -m uvicorn src.web.server:app --host 0.0.0.0 --port 8000

# Вариант 3: активировать venv, потом запускать напрямую
source venv/bin/activate
./scripts/run_server.py
```

При старте сервер автоматически очищает старые LiveKit-комнаты от предыдущих запусков.

### Шаг 2: Запуск голосового агента

В отдельном терминале:

```bash
# Вариант 1: через agent.sh (рекомендуется — управление процессами)
./scripts/agent.sh start

# Вариант 2: напрямую
./venv/bin/python scripts/run_voice_agent.py
```

**Управление агентом через `agent.sh`:**

```bash
./scripts/agent.sh status    # Статус процессов
./scripts/agent.sh stop      # Остановить агент (graceful)
./scripts/agent.sh restart   # Перезапустить
./scripts/agent.sh logs      # Показать логи (tail -f)
./scripts/agent.sh kill-all  # Аварийное завершение всех процессов
```

Агент защищён от дублирования через PID-файл (`.agent.pid`). При попытке запустить второй экземпляр скрипт предупредит и завершится.

### Шаг 3: Открыть браузер

```
http://localhost:8000
```

Нажмите "Начать консультацию" — система:

1. Проверит, что голосовой агент запущен (health check)
2. Создаст сессию в SQLite
3. Сгенерирует LiveKit комнату с agent dispatch
4. Подключит голосового агента
5. Покажет анкету в реальном времени (polling каждые ~2 сек)
6. Обновит URL страницы — при перезагрузке сессия восстановится

## 6. Запуск тестов

### Юнит-тесты (972 теста)

```bash
pytest
```

### Парсинг документов клиента (Stage 6.5)

```bash
# Генерация тестовых документов (PDF, DOCX, XLSX, TXT, MD)
python scripts/generate_test_documents.py

# Тест парсинга всех форматов
python scripts/test_document_parsing.py

# Подробный вывод
python scripts/test_document_parsing.py --verbose
```

### Симуляция консультации (12 сценариев)

```bash
# Список доступных сценариев
python scripts/run_test.py --list

# Запуск конкретного сценария
python scripts/run_test.py auto_service

# Тихий режим (без детального вывода)
python scripts/run_test.py auto_service --quiet

# Без сохранения отчётов
python scripts/run_test.py auto_service --no-save

# С документами клиента (Stage 7.5)
python scripts/run_test.py logistics_company --input-dir input/test_docs/
```

### Pipeline: Тест → Ревью

```bash
# Полный pipeline
python scripts/run_pipeline.py auto_service

# С автоматическим одобрением
python scripts/run_pipeline.py auto_service --auto-approve

# Без этапа ревью
python scripts/run_pipeline.py auto_service --skip-review

# Тихий режим + свой output
python scripts/run_pipeline.py auto_service --quiet --output-dir output/custom/
```

### E2E тесты голосового агента

```bash
# Установка Puppeteer
npm install puppeteer

# Запуск (требует работающий сервер и агент)
node tests/e2e_voice_test.js
```

## 7. Генерация региональных профилей

Для расширения базы знаний на новые страны используйте LLM-генератор профилей.

### Генерация одного профиля

```bash
python scripts/generate_profiles.py --region eu --country de --industry automotive

# Явный выбор LLM-провайдера
python scripts/generate_profiles.py --region eu --country de --industry automotive --provider deepseek
```

### Batch-генерация для региона

```bash
# Все отрасли для нескольких стран
python scripts/generate_profiles.py --batch eu "de,at,ch" "automotive,medical,logistics"
```

### Wave 1: приоритетные страны

```bash
# Германия, США, ОАЭ, Бразилия × 40 отраслей
python scripts/generate_profiles.py --wave1

# Dry-run (без генерации)
python scripts/generate_profiles.py --wave1 --dry-run
```

Результаты сохраняются в `config/industries/{region}/{country}/{industry}.yaml`.

## 8. Структура результатов

После любого режима результаты сохраняются в:

```
output/
└── {дата}/
    └── {компания}_v{N}/
        ├── anketa.md        # Анкета в Markdown
        ├── anketa.json      # Анкета в JSON
        └── dialogue.md      # Лог диалога
```

## 9. Проверка работоспособности

### Логи

После запуска проверьте `logs/`:

```bash
ls -la logs/
# Должны появиться файлы: server.log, agent.log, livekit.log и др.
```

### База данных

```bash
sqlite3 data/sessions.db "SELECT session_id, status, company_name FROM sessions;"
```

## Решение проблем

| Проблема | Решение |
|----------|---------|
| `DEEPSEEK_API_KEY not set` | Проверьте `.env` файл или переключите `LLM_PROVIDER=azure` |
| `Azure OpenAI credentials not configured` | Заполните `AZURE_CHAT_OPENAI_*` в `.env` |
| `Azure Realtime credentials not configured` | Заполните `AZURE_OPENAI_*` в `.env` (для голосового режима) |
| Агент не подключается к комнате | Проверьте `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| «Голосовой агент не запущен» в браузере | Запустите агент: `./scripts/agent.sh start`, проверьте: `./scripts/agent.sh status` |
| Нет звука в браузере | Разрешите доступ к микрофону, проверьте HTTPS |
| `ModuleNotFoundError` | Активируйте venv: `source venv/bin/activate` |
| Redis/PostgreSQL connection refused | `docker compose -f config/docker-compose.yml up -d` |
| Несколько процессов агента (конфликт) | `./scripts/agent.sh kill-all` и затем `./scripts/agent.sh start` |
| Порт 8000 занят | `lsof -ti:8000 \| xargs kill -9` или `./scripts/kill_8000.sh` |
| Старые комнаты LiveKit | Перезапустите сервер (очистка при старте) или: `curl -X DELETE http://localhost:8000/api/rooms` |

## Дальнейшее чтение

- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура и компоненты
- [VOICE_AGENT.md](VOICE_AGENT.md) — голосовой агент (LiveKit + Azure)
- [AGENT_WORKFLOWS.md](AGENT_WORKFLOWS.md) — workflow агентов
- [TESTING.md](TESTING.md) — подробности о тестировании
- [DEPLOYMENT.md](DEPLOYMENT.md) — деплой и production
- [LOGGING.md](LOGGING.md) — система логирования
- [ERROR_HANDLING.md](ERROR_HANDLING.md) — обработка ошибок
- [PHILOSOPHY.md](PHILOSOPHY.md) — философия проекта
