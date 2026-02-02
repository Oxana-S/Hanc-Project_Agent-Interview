# Voice Interviewer Agent

Голосовой агент-интервьюер с активным анализом и уточнениями для создания анкет голосовых помощников.

## Описание

Система для проведения интервью с клиентами или сотрудниками компании для сбора требований к голосовому агенту.

**Maximum Interview Mode** — единый режим с тремя фазами:
1. **DISCOVERY** — свободный консультативный диалог
2. **STRUCTURED** — целенаправленный сбор недостающих данных
3. **SYNTHESIS** — генерация полной анкеты

### Ключевые возможности:
- **Активный анализ** через DeepSeek LLM
- **Уточняющие вопросы** при неполных ответах
- **Визуализация прогресса** в реальном времени (Rich CLI)
- **Сохранение контекста** в Redis и PostgreSQL
- **Два паттерна**: INTERACTION (клиенты) и MANAGEMENT (сотрудники)

## Быстрый старт

### 1. Установка

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
nano .env  # Заполните API ключи
```

**Обязательные параметры:**
```env
DEEPSEEK_API_KEY=your_key
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### 3. Запуск инфраструктуры

```bash
docker-compose -f config/docker-compose.yml up -d
```

### 4. Запуск

```bash
# Maximum Interview Mode (с DeepSeek AI)
python3 scripts/demo.py

# Проверка здоровья системы
python3 scripts/healthcheck.py
```

## Структура проекта

```
voice_interviewer/
├── src/                          # Исходный код
│   ├── __init__.py
│   ├── models.py                 # Базовые модели (Pydantic)
│   │
│   ├── interview/                # Логика интервью
│   │   ├── maximum.py            # MaximumInterviewer (главный класс)
│   │   ├── phases.py             # InterviewPhase, FieldStatus, CollectedInfo
│   │   └── questions/            # Вопросы по паттернам
│   │       ├── interaction.py    # 40 вопросов для клиентов
│   │       └── management.py     # 38 вопросов для сотрудников
│   │
│   ├── storage/                  # Хранение данных
│   │   ├── redis.py              # RedisStorageManager
│   │   └── postgres.py           # PostgreSQLStorageManager
│   │
│   ├── llm/                      # LLM клиенты
│   │   ├── deepseek.py           # DeepSeekClient
│   │   └── anketa_generator.py   # Генерация полной анкеты
│   │
│   └── cli/                      # CLI интерфейсы
│       ├── interface.py          # Базовый CLI
│       └── maximum.py            # CLI для Maximum режима
│
├── scripts/                      # Точки входа
│   ├── demo.py                   # Главный скрипт запуска
│   └── healthcheck.py            # Проверка системы
│
├── docs/                         # Документация
│   ├── QUICKSTART.md
│   ├── PROJECT_OVERVIEW.md
│   └── example_anketa.md
│
├── config/                       # Конфигурация
│   ├── docker-compose.yml
│   └── init_db.sql
│
├── tests/                        # Тесты (123 теста)
├── output/                       # Результаты интервью
│
├── .env.example
├── requirements.txt
└── README.md
```

## Maximum Interview Mode

### Три фазы

```
DISCOVERY → STRUCTURED → SYNTHESIS
   │            │           │
   ▼            ▼           ▼
Свободный   Сбор       Генерация
диалог      данных     анкеты
```

### Discovery Phase
- Консультативный диалог без жёсткой структуры
- Клиент рассказывает о бизнесе в свободной форме
- AI извлекает информацию из контекста
- 5-15 ходов (настраивается)

### Structured Phase
- Целенаправленные вопросы по недостающим полям
- Приоритизация: REQUIRED → IMPORTANT → OPTIONAL
- До 3 уточнений на вопрос

### Synthesis Phase
- Генерация полной анкеты через DeepSeek
- Экспорт в JSON и Markdown
- Сохранение в PostgreSQL

## Паттерны интервью

### INTERACTION (Клиенты компании)
Для агентов, работающих с внешними клиентами:
- Продажи и запись на услуги
- Бронирование
- Техподдержка
- Справочная

### MANAGEMENT (Сотрудники компании)
Для внутренних агентов:
- HR и рекрутинг
- IT поддержка
- Координация задач
- Секретарь руководителя

## CLI Dashboard

```
╔════════════════════════════════════════════╗
║     MAXIMUM INTERVIEW MODE                 ║
║     TechSolutions Inc.                     ║
║                                            ║
║     discovery → [STRUCTURED] → synthesis   ║
╚════════════════════════════════════════════╝

📊 bas: ✓✓✓✓ | agt: ✓◐○○ | cli: ○○○ | oth: ○○○

╔════════════════════════════════════════════╗
║ Progress: 45% [████████░░░░░░░░░]          ║
║ Required: 8/15  Important: 3/10  Optional: 0/5 ║
╚════════════════════════════════════════════╝
```

## Анализ ответов

DeepSeek анализирует каждый ответ:

```python
{
    "completeness_score": 0.75,      # 0-1
    "needs_clarification": True,
    "extracted_fields": {...},
    "clarification_questions": [
        "Какие конкретно услуги вы предлагаете?",
        "Каков ценовой диапазон?"
    ]
}
```

## Конфигурация

### DeepSeek API
```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### Storage
```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_SESSION_TTL=7200

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=voice_interviewer
POSTGRES_USER=interviewer_user
POSTGRES_PASSWORD=your_password
```

## Тестирование

```bash
# Все тесты
python3 -m pytest tests/ -v

# С покрытием
python3 -m pytest tests/ -v --cov=src
```

## Разработка

### Импорты
```python
from src.interview.maximum import MaximumInterviewer
from src.models import InterviewPattern
from src.llm.deepseek import DeepSeekClient

# Создание интервьюера
interviewer = MaximumInterviewer(
    pattern=InterviewPattern.INTERACTION,
    deepseek_client=DeepSeekClient()
)

# Запуск
result = await interviewer.run()
```

## Troubleshooting

### Redis connection failed
```bash
docker-compose -f config/docker-compose.yml ps
docker-compose -f config/docker-compose.yml restart redis
```

### DeepSeek API errors
```bash
# Проверьте API ключ
echo $DEEPSEEK_API_KEY

# Тест подключения
python3 -c "from src.llm.deepseek import DeepSeekClient; print('OK')"
```

## Лицензия

MIT

---

**Создано для автоматизации сбора требований к голосовым агентам**
