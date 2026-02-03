# Voice Interviewer Agent - Полное описание проекта

**Версия: 3.0.0**
**Дата: 2026-02-03**

---

## Что создано

Система AI-консультанта для сбора требований к голосовым агентам.
Включает два независимых агента для автоматизированного тестирования и ревью документов.

### Ключевые возможности

- **ConsultantInterviewer** — 4-фазная консультация (Discovery → Analysis → Proposal → Refinement)
- **FinalAnketa v2.0** — расширенная анкета с 18 секциями и AI-генерируемым контентом
- **agent_client_simulator** — автоматизированное тестирование через LLM-симуляцию клиента
- **agent_document_reviewer** — интерактивное ревью документов во внешнем редакторе
- **Integrated Pipeline** — связка Test → Review для полного цикла тестирования
- **Rich CLI** — визуализация прогресса в реальном времени

---

## Структура проекта

```
voice_interviewer/
│
├── src/                              # Исходный код
│   ├── __init__.py                   # Экспорты пакета
│   ├── models.py                     # Базовые модели (InterviewPattern, etc.)
│   │
│   ├── consultant/                   # ConsultantInterviewer (главный модуль)
│   │   ├── __init__.py
│   │   ├── interviewer.py            # ConsultantInterviewer (4-фазная консультация)
│   │   ├── phases.py                 # ConsultantPhase, CollectedData
│   │   └── prompts.py                # Промпты для LLM
│   │
│   ├── anketa/                       # FinalAnketa v2.0
│   │   ├── __init__.py
│   │   ├── schema.py                 # FinalAnketa, AgentFunction, Integration
│   │   ├── extractor.py              # AnketaExtractor (LLM → структура)
│   │   ├── generator.py              # AnketaGenerator (структура → Markdown/JSON)
│   │   ├── markdown_parser.py        # AnketaMarkdownParser (Markdown → структура)
│   │   └── review_service.py         # AnketaReviewService
│   │
│   ├── agent_client_simulator/            # Агент автоматизированного тестирования
│   │   ├── __init__.py
│   │   ├── client.py                 # SimulatedClient (LLM-симулятор клиента)
│   │   ├── runner.py                 # ConsultationTester (оркестратор)
│   │   ├── reporter.py               # TestReporter (отчёты)
│   │   └── validator.py              # TestValidator (6 проверок)
│   │
│   ├── agent_document_reviewer/      # Агент ревью документов
│   │   ├── __init__.py
│   │   ├── models.py                 # ReviewConfig, ReviewResult, ReviewStatus
│   │   ├── reviewer.py               # DocumentReviewer
│   │   ├── editor.py                 # ExternalEditor
│   │   ├── parser.py                 # DocumentParser
│   │   ├── history.py                # VersionHistory
│   │   └── validators.py             # Валидаторы
│   │
│   ├── interview/                    # Устаревший модуль (Maximum режим)
│   │   ├── maximum.py                # MaximumInterviewer
│   │   └── questions/                # Вопросы по паттернам
│   │
│   ├── storage/                      # Хранение данных
│   │   ├── redis.py                  # RedisStorageManager
│   │   └── postgres.py               # PostgreSQLStorageManager
│   │
│   ├── llm/                          # LLM клиенты
│   │   ├── deepseek.py               # DeepSeekClient
│   │   └── anketa_generator.py       # LLM генерация анкеты
│   │
│   └── cli/                          # CLI интерфейсы
│       ├── interface.py              # Базовый CLI
│       └── maximum.py                # CLI для Maximum режима
│
├── scripts/                          # Точки входа
│   ├── demo.py                       # Запуск ConsultantInterviewer
│   ├── run_test.py                   # Запуск тестовой симуляции
│   ├── run_pipeline.py               # Интегрированный pipeline
│   └── healthcheck.py                # Проверка системы
│
├── tests/                            # Тесты
│   ├── scenarios/                    # YAML сценарии для симуляции
│   │   ├── vitalbox.yaml
│   │   └── _template.yaml
│   └── ...
│
├── docs/                             # Документация
│   ├── PROJECT_OVERVIEW.md           # Этот файл
│   ├── AGENT_WORKFLOWS.md            # Схемы агентов и pipeline
│   ├── QUICKSTART.md
│   ├── TESTING.md
│   └── plans/                        # Архитектурные планы
│
├── output/                           # Результаты
│   ├── anketas/                      # Сгенерированные анкеты
│   ├── tests/                        # Результаты тестов
│   └── final/                        # Финальные (после ревью)
│
├── config/
│   ├── docker-compose.yml
│   └── init_db.sql
│
├── .env.example
├── requirements.txt
└── README.md
```

---

## ConsultantInterviewer: 4-фазная консультация

### Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONSULTANT INTERVIEWER                        │
│                                                                  │
│   DISCOVERY ──▶ ANALYSIS ──▶ PROPOSAL ──▶ REFINEMENT            │
│       │            │            │             │                 │
│       ▼            ▼            ▼             ▼                 │
│   Свободный    Анализ       Предло-       Уточнение            │
│   диалог       бизнеса      жение         деталей              │
│   о бизнесе    и болей      решения       и FAQ                │
└─────────────────────────────────────────────────────────────────┘
```

### Фаза 1: Discovery (Открытие)

- Консультативный диалог о бизнесе
- LLM извлекает информацию из контекста
- Определяет pain points и цели клиента
- 5-15 ходов диалога

### Фаза 2: Analysis (Анализ)

- Формирование BusinessAnalysis
- Выявление болевых точек и возможностей
- Определение рекомендуемых функций агента
- Показ результатов клиенту для подтверждения

### Фаза 3: Proposal (Предложение)

- Формирование ProposedSolution
- Главная функция + дополнительные
- Интеграции и архитектура
- Клиент выбирает или корректирует

### Фаза 4: Refinement (Уточнение)

- Сбор недостающих данных для анкеты
- Генерация экспертного контента (FAQ, возражения, KPI)
- Финализация FinalAnketa v2.0

---

## FinalAnketa v2.0: 18 секций

### Структура анкеты

| # | Секция | Описание |
|---|--------|----------|
| 1 | Информация о компании | company_name, industry, website, services |
| 2 | Голосовой агент | agent_name, agent_purpose, communication_style |
| 3 | Основная функция | main_function (AgentFunction) |
| 4 | Дополнительные функции | additional_functions[] |
| 5 | Интеграции | integrations[] (Integration) |
| 6 | Целевая аудитория | target_audience |
| 7 | Типичные вопросы | typical_questions[] |
| 8 | FAQ для агента | faq_entries[] (AI-generated) |
| 9 | Работа с возражениями | objection_handlers[] (AI-generated) |
| 10 | Примеры диалогов | sample_dialogues[] (AI-generated) |
| 11 | KPI и метрики | success_kpis[] (AI-generated) |
| 12 | Ограничения | limitations[] |
| 13 | Эскалация | escalation_rules |
| 14 | Часы работы | working_hours |
| 15 | Языки | languages[] |
| 16 | Текущие проблемы | current_problems[] |
| 17 | Ожидания от агента | expectations |
| 18 | Метаданные | created_at, version, duration |

### AI-генерируемые секции

Секции 8-11 генерируются LLM на основе контекста:

- **FAQ** — типичные вопросы и ответы
- **Objection Handlers** — сценарии работы с возражениями
- **Sample Dialogues** — примеры диалогов агента
- **KPIs** — метрики успеха с целевыми значениями

---

## Агенты

### agent_client_simulator — Автоматизированное тестирование

```
YAML Scenario → SimulatedClient → ConsultationTester → TestValidator → Report
```

**Компоненты:**
- `SimulatedClient` — LLM-симулятор клиента по персоне из YAML
- `ConsultationTester` — оркестратор тестов, патчит Rich.Prompt
- `TestValidator` — 6 проверок (completeness, quality, scenario match, phases, loops, metrics)
- `TestReporter` — Console, JSON, Markdown отчёты

**Запуск:**
```bash
python scripts/run_test.py vitalbox
python scripts/run_test.py --list
```

### agent_document_reviewer — Ревью документов

```
Content → DocumentReviewer → External Editor → Validate → Result
```

**Компоненты:**
- `DocumentReviewer` — главный класс workflow
- `ExternalEditor` — интеграция с VS Code/Sublime/nano
- `DocumentParser` — prepare/extract инструкции
- `VersionHistory` — история версий
- `Validators` — валидация анкет

**Использование:**
```python
from src.agent_document_reviewer import review_anketa

result = review_anketa(markdown_content, strict=True)
if result.changed:
    save(result.content)
```

---

## Интегрированный Pipeline

```bash
python scripts/run_pipeline.py vitalbox
```

**Workflow:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTEGRATED PIPELINE                           │
│                                                                  │
│  YAML ──▶ agent_client_simulator ──▶ FinalAnketa ──▶ agent_document_reviewer
│                                                                  │
│  Stage 1: Автоматическое тестирование                           │
│  Stage 2: Ревью в редакторе (опционально)                       │
│  Output: Проверенная анкета в output/final/                     │
└─────────────────────────────────────────────────────────────────┘
```

**Опции:**
- `--auto-approve` — без ревью
- `--skip-review` — пропустить ревью
- `--output-dir` — директория для результатов

---

## Технологии

| Компонент | Технология |
|-----------|------------|
| Runtime | Python 3.9+ |
| LLM | DeepSeek API (deepseek-chat) |
| Validation | Pydantic v2 |
| CLI | Rich |
| Caching | Redis |
| Storage | PostgreSQL |
| Logging | structlog |
| Testing | pytest |

---

## Быстрый старт

```bash
# 1. Установка
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Конфигурация
cp .env.example .env
# Заполните DEEPSEEK_API_KEY

# 3. Запуск консультации
python scripts/demo.py

# 4. Запуск тестирования
python scripts/run_test.py vitalbox

# 5. Полный pipeline
python scripts/run_pipeline.py vitalbox
```

---

## Метрики успеха

| Метрика | Цель |
|---------|------|
| Полнота анкеты | 100% обязательных полей |
| Качество данных | Нет диалоговых маркеров в значениях |
| Соответствие сценарию | Company/Industry совпадают |
| Все фазы | 4/4 (Discovery → Refinement) |
| Без зацикливания | < 5 повторных сообщений |
| Время | < 600 сек, < 50 ходов |

---

## Roadmap

### Готово (v3.0)

- [x] ConsultantInterviewer (4-фазная консультация)
- [x] FinalAnketa v2.0 (18 секций)
- [x] AI-генерируемый контент (FAQ, возражения, диалоги, KPI)
- [x] agent_client_simulator (автоматизированное тестирование)
- [x] agent_document_reviewer (ревью в редакторе)
- [x] Integrated Pipeline (Test → Review)

### Планируется

- [ ] WebSocket API для web интерфейса
- [ ] Экспорт анкет в PDF/DOCX
- [ ] Multi-язычная поддержка
- [ ] Голосовой интерфейс (Azure OpenAI Realtime)
- [ ] Dashboard для мониторинга тестов

---

## Документация

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — этот файл
- [AGENT_WORKFLOWS.md](AGENT_WORKFLOWS.md) — схемы агентов
- [QUICKSTART.md](QUICKSTART.md) — быстрый старт
- [TESTING.md](TESTING.md) — руководство по тестированию
