# Быстрый старт

Пошаговая инструкция для запуска Hanc.AI Voice Consultant.

## Предварительные требования

- Python 3.11+
- API ключ DeepSeek (обязательно для всех режимов)
- Для голосового режима:
  - LiveKit Server (cloud или self-hosted)
  - Azure OpenAI с подключением Realtime API
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

Создайте файл `.env` в корне проекта:

```env
# === ОБЯЗАТЕЛЬНО для всех режимов ===
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-reasoner

# === ОБЯЗАТЕЛЬНО для голосового режима ===
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=API...
LIVEKIT_API_SECRET=...

AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-realtime-preview
AZURE_OPENAI_REALTIME_API_VERSION=2024-10-01-preview

# === Опционально: уведомления ===
# Настраиваются в config/notifications.yaml
```

## 3. Запуск текстового режима (CLI)

Не требует LiveKit и Azure. Работает через DeepSeek в терминале.

```bash
python scripts/consultant_demo.py
```

Что произойдёт:

1. Откроется Rich CLI с AI-консультантом
2. 4 фазы: Знакомство → Анализ → Предложение → Финализация
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
uvicorn src.web.server:app --host 0.0.0.0 --port 8000
```

### Шаг 2: Запуск голосового агента

В отдельном терминале:

```bash
python scripts/run_voice_agent.py dev
```

### Шаг 3: Открыть браузер

```
http://localhost:8000
```

Нажмите "Начать консультацию" — система:

1. Создаст сессию в SQLite
2. Сгенерирует LiveKit комнату с agent dispatch
3. Подключит голосового агента
4. Покажет анкету в реальном времени (polling каждые ~2 сек)

## 6. Запуск тестов

### Юнит-тесты (252 теста)

```bash
pytest
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
```

### Pipeline: Тест → Ревью

```bash
# Полный pipeline
python scripts/run_pipeline.py auto_service

# С автоматическим одобрением
python scripts/run_pipeline.py auto_service --auto-approve

# Без этапа ревью
python scripts/run_pipeline.py auto_service --skip-review
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
```

### Batch-генерация для региона

```bash
# Все отрасли для нескольких стран
python scripts/generate_profiles.py --batch eu "de,at,ch" "automotive,medical,logistics"
```

### Wave 1: приоритетные страны

```bash
# Германия, США, ОАЭ, Бразилия × 8 отраслей
python scripts/generate_profiles.py --wave1

# Dry-run (без генерации)
python scripts/generate_profiles.py --wave1 --dry-run
```

Результаты сохраняются в `config/industries/{region}/{country}/{industry}.yaml`.

## 8. Структура результатов

После любого режима результаты сохраняются в:

```
output/
└── 2026-02-05/
    └── avtoprofi_v1/
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
| `DEEPSEEK_API_KEY not set` | Проверьте `.env` файл |
| `Azure OpenAI credentials not configured` | Заполните `AZURE_OPENAI_*` в `.env` |
| Агент не подключается к комнате | Проверьте `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| Нет звука в браузере | Разрешите доступ к микрофону, проверьте HTTPS |
| `ModuleNotFoundError` | Активируйте venv: `source venv/bin/activate` |

## Дальнейшее чтение

- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура и компоненты
- [VOICE_AGENT.md](VOICE_AGENT.md) — голосовой агент (LiveKit + Azure)
- [AGENT_WORKFLOWS.md](AGENT_WORKFLOWS.md) — workflow агентов
- [TESTING.md](TESTING.md) — подробности о тестировании
- [LOGGING.md](LOGGING.md) — система логирования
