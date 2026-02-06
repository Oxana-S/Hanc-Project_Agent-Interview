# Hanc.AI Voice Consultant

Голосовой AI-консультант для сбора требований к голосовым агентам.

Клиент общается с агентом голосом через браузер или текстом через CLI — агент проводит консультацию (4-фазную в режимах Voice/Consultant или 3-фазную в Maximum режиме), формирует анкету и сохраняет результат.

## Три режима работы

| Режим | Интерфейс | Транспорт | Скрипт | Хранение |
|-------|-----------|-----------|--------|----------|
| **Голосовой** | Браузер (WebRTC) | LiveKit + Azure OpenAI Realtime | `scripts/run_voice_agent.py` + `uvicorn` | SQLite |
| **Текстовый CLI (Consultant)** | CLI (Rich) | DeepSeek | `scripts/consultant_demo.py` | Файловая система (output/) |
| **Текстовый CLI (Maximum)** | CLI (Rich) | DeepSeek + Redis + PostgreSQL | `scripts/demo.py` | Redis + PostgreSQL |

Голосовой и Consultant режимы проводят 4-фазную консультацию (DISCOVERY → ANALYSIS → PROPOSAL → REFINEMENT) и генерируют анкету FinalAnketa v2.0. Maximum режим проводит 3-фазную консультацию (DISCOVERY → STRUCTURED → SYNTHESIS) с расширенным сбором данных и MOCK-режимом для тестирования.

## Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│ ГОЛОСОВОЙ РЕЖИМ                                              │
│                                                              │
│  Браузер (LiveKit JS SDK)                                    │
│      │                                                       │
│      ├── WebRTC аудио ──→ LiveKit Cloud ──→ Голосовой агент  │
│      │                                        │              │
│      │                          Azure OpenAI Realtime (STT/TTS)
│      │                          DeepSeek (анализ, анкета)    │
│      │                                                       │
│      └── HTTP/REST ──→ FastAPI (port 8000)                   │
│                           └── SQLite (сессии, анкеты)        │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ ТЕКСТОВЫЙ РЕЖИМ (Consultant)                                 │
│                                                              │
│  CLI (Rich)                                                  │
│      │                                                       │
│      └── ConsultantInterviewer ──→ DeepSeek (диалог, анализ) │
│              │                                               │
│              ├── AnketaExtractor ──→ FinalAnketa             │
│              └── OutputManager ──→ output/{дата}/{компания}/  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ ТЕКСТОВЫЙ РЕЖИМ (Maximum)                                    │
│                                                              │
│  CLI (Rich)                                                  │
│      │                                                       │
│      └── MaximumInterviewer ──→ DeepSeek (диалог, анализ)    │
│              │   3 фазы: DISCOVERY → STRUCTURED → SYNTHESIS  │
│              │                                               │
│              ├── Redis ──→ Кэш активных сессий (TTL 2ч)     │
│              ├── PostgreSQL ──→ Постоянное хранение анкет    │
│              └── OutputManager ──→ output/{дата}/{компания}/  │
└──────────────────────────────────────────────────────────────┘
```

### Компоненты

| Компонент | Технология | Назначение |
|-----------|-----------|------------|
| Веб-интерфейс | Vanilla JS + LiveKit JS SDK | Голосовое подключение, отображение анкеты |
| Веб-сервер | FastAPI + uvicorn | REST API, управление сессиями |
| Голосовой агент | LiveKit Agents SDK | Приём голоса, генерация ответов |
| STT/TTS | Azure OpenAI Realtime API | Распознавание и синтез речи (WebSocket) |
| Текстовая логика (Consultant) | ConsultantInterviewer | 4-фазная консультация (Discovery → Refinement) |
| Текстовая логика (Maximum) | MaximumInterviewer | 3-фазная консультация (Discovery → Structured → Synthesis) |
| Анализ и анкета | DeepSeek LLM | Извлечение данных, формирование анкеты |
| Хранение (голос) | SQLite | Сессии, диалоги, анкеты |
| Хранение (Maximum — кэш) | Redis | Кэш активных сессий (TTL 2ч) |
| Хранение (Maximum — БД) | PostgreSQL | Постоянное хранение анкет |
| Хранение (вывод) | Файловая система | output/{дата}/{компания}/ |
| База знаний | YAML-профили | 8 отраслей с типичными болями и решениями |

## Быстрый старт

### Установка

```bash
git clone <repo-url>
cd Project.\ Agent\ Interview

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Голосовой режим

Требуется: LiveKit Cloud, Azure OpenAI, DeepSeek API.

```bash
cp .env.example .env
nano .env  # Заполните API ключи
```

```env
# LiveKit — WebRTC транспорт
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_URL=wss://<ваш-проект>.livekit.cloud

# Azure OpenAI — голос (STT/TTS)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<ресурс>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-realtime-preview
AZURE_OPENAI_REALTIME_API_VERSION=2024-10-01-preview

# DeepSeek — анализ и анкета
DEEPSEEK_API_KEY=...
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-reasoner
```

**Терминал 1 — веб-сервер:**
```bash
./venv/bin/python -m uvicorn src.web.server:app --host 0.0.0.0 --port 8000
```

**Терминал 2 — голосовой агент:**
```bash
./venv/bin/python scripts/run_voice_agent.py dev
```

**Браузер:** откройте `http://localhost:8000`, нажмите «Начать консультацию».

### Текстовый режим — Consultant (CLI)

Требуется: DeepSeek API.

```bash
./venv/bin/python scripts/consultant_demo.py
```

Выберите тип агента (INTERACTION / MANAGEMENT), затем ведите диалог в терминале.

### Текстовый режим — Maximum (CLI)

Требуется: DeepSeek API + Redis + PostgreSQL.

```bash
# Поднять Redis и PostgreSQL
cd config && docker-compose up -d && cd ..

# Запуск Maximum Interview
./venv/bin/python scripts/demo.py
```

Maximum режим проводит 3-фазную консультацию (DISCOVERY → STRUCTURED → SYNTHESIS) с расширенным сбором данных. Поддерживает MOCK-режим для тестирования без LLM.

### Тестовая симуляция

Автоматический прогон консультации через LLM-симулятор клиента:

```bash
# Список доступных сценариев
./venv/bin/python scripts/run_test.py --list

# Запуск сценария
./venv/bin/python scripts/run_test.py auto_service
./venv/bin/python scripts/run_test.py logistics_company
./venv/bin/python scripts/run_test.py medical_center
```

Подробнее: [docs/TESTING.md](docs/TESTING.md)

## Структура проекта

```
.
├── public/                          # Фронтенд (vanilla HTML/JS/CSS)
│   ├── index.html                   # Главная страница
│   └── app.js                       # Клиентская логика + LiveKit SDK
│
├── src/
│   ├── voice/                       # Голосовой агент
│   │   ├── consultant.py            # VoiceConsultant — основной модуль (entrypoint)
│   │   ├── handler.py               # Обработчик голосовых сессий
│   │   ├── livekit_client.py        # JWT-токены и утилиты LiveKit
│   │   └── azure_realtime.py        # Клиент Azure OpenAI Realtime
│   │
│   ├── web/
│   │   └── server.py                # FastAPI сервер (REST API)
│   │
│   ├── consultant/                  # Текстовый AI-консультант (Consultant режим)
│   │   ├── interviewer.py           # ConsultantInterviewer (4 фазы)
│   │   ├── phases.py                # ConsultantPhase enum (5 фаз: DISCOVERY, ANALYSIS, PROPOSAL, REFINEMENT, COMPLETED)
│   │   └── models.py                # BusinessAnalysis, ProposedSolution
│   │
│   ├── interview/                   # Maximum-интервьюер (Maximum режим)
│   │   ├── maximum.py               # MaximumInterviewer (744 строки, 3 фазы: DISCOVERY → STRUCTURED → SYNTHESIS)
│   │   ├── phases.py                # InterviewPhase, CollectedInfo, ANKETA_FIELDS (326 строк)
│   │   └── questions/               # Банки вопросов по паттернам
│   │       ├── interaction.py       # Вопросы для паттерна INTERACTION (722 строки)
│   │       └── management.py        # Вопросы для паттерна MANAGEMENT (736 строк)
│   │
│   ├── anketa/                      # FinalAnketa v2.0
│   │   ├── schema.py                # Pydantic-модели (18 секций)
│   │   ├── extractor.py             # AnketaExtractor (LLM → структура)
│   │   ├── generator.py             # AnketaGenerator (структура → MD/JSON)
│   │   ├── data_cleaner.py          # Очистка и ремонт JSON
│   │   ├── markdown_parser.py       # MD → структура (для ревью)
│   │   └── review_service.py        # AnketaReviewService
│   │
│   ├── session/                     # Управление сессиями
│   │   ├── manager.py               # SessionManager (SQLite)
│   │   └── models.py                # ConsultationSession
│   │
│   ├── llm/
│   │   ├── deepseek.py              # DeepSeek LLM клиент
│   │   └── anketa_generator.py      # LLM-генерация анкеты (507 строк, отличается от src/anketa/generator.py)
│   │
│   ├── output/
│   │   └── manager.py               # OutputManager (структура output/)
│   │
│   ├── knowledge/                   # База знаний по отраслям
│   │   ├── manager.py               # IndustryKnowledgeManager
│   │   ├── loader.py                # Загрузчик YAML-профилей
│   │   ├── matcher.py               # Определение отрасли из текста
│   │   ├── context_builder.py       # Построение контекста для LLM
│   │   └── models.py                # IndustryProfile, PainPoint
│   │
│   ├── documents/                   # Анализ документов клиента
│   │   ├── parser.py                # Парсеры PDF/DOCX/MD
│   │   ├── analyzer.py              # LLM-анализ документов
│   │   └── models.py                # ParsedDocument, DocumentContext
│   │
│   ├── notifications/               # Уведомления
│   │   ├── manager.py               # Email, webhooks
│   │   └── models.py                # NotificationConfig
│   │
│   ├── agent_client_simulator/      # Автоматическое тестирование
│   │   ├── client.py                # SimulatedClient (LLM-симулятор)
│   │   ├── runner.py                # ConsultationTester
│   │   ├── reporter.py              # TestReporter (консоль, JSON, MD)
│   │   └── validator.py             # TestValidator (6 проверок)
│   │
│   ├── agent_document_reviewer/     # Ревью документов в редакторе
│   │   ├── reviewer.py              # DocumentReviewer
│   │   ├── editor.py                # ExternalEditor (VS Code/nano)
│   │   ├── parser.py                # DocumentParser
│   │   ├── history.py               # VersionHistory
│   │   └── validators.py            # Валидаторы анкет
│   │
│   ├── research/                    # Исследование внешних данных
│   │   ├── engine.py                # ResearchEngine
│   │   ├── web_search.py            # Tavily/Bing веб-поиск
│   │   └── website_parser.py        # Парсинг сайтов
│   │
│   ├── config/                      # Загрузчики конфигурации
│   │   ├── prompt_loader.py         # Загрузка YAML-промптов
│   │   ├── synonym_loader.py        # Словари синонимов
│   │   └── locale_loader.py         # Локализация UI
│   │
│   ├── cli/                         # CLI-интерфейсы
│   │   ├── interface.py             # Базовый CLI (Rich)
│   │   └── maximum.py               # CLI для Maximum-режима
│   │
│   ├── storage/                     # Хранение (Redis + PostgreSQL для Maximum режима)
│   │   ├── redis.py                 # RedisStorageManager (кэш сессий, TTL 2ч)
│   │   └── postgres.py              # PostgreSQLStorageManager (постоянное хранение анкет)
│   │
│   ├── logging_config.py            # Централизованное логирование
│   └── models.py                    # Базовые модели (315 строк: InterviewPattern, InterviewContext, CompletedAnketa, QuestionResponse и др.)
│
├── scripts/                         # Точки входа
│   ├── run_voice_agent.py           # Запуск голосового агента
│   ├── run_server.py                # Запуск FastAPI сервера
│   ├── consultant_demo.py           # Текстовый AI-консультант (CLI)
│   ├── run_test.py                  # Запуск тестовых симуляций
│   ├── run_pipeline.py              # Pipeline: тест → ревью
│   ├── demo.py                      # Maximum Interview режим + MOCK-режим (Redis + PostgreSQL)
│   ├── healthcheck.py               # Проверка системы
│   └── test_deepseek_api.py         # Тест DeepSeek API
│
├── config/                          # YAML-конфигурация
│   ├── industries/                  # Профили 8 отраслей
│   ├── synonyms/                    # Словари (base, ru, en)
│   ├── consultant/                  # Контекст для KB
│   ├── personas/                    # Персоны и трейты
│   ├── notifications.yaml           # Настройки уведомлений
│   ├── docker-compose.yml           # Redis 7 + PostgreSQL 16 (для Maximum режима)
│   └── init_db.sql                  # SQL-схема PostgreSQL
│
├── prompts/consultant/              # Промпты по фазам
│   ├── discovery.yaml
│   ├── analysis.yaml
│   ├── proposal.yaml
│   └── refinement.yaml
│
├── tests/                           # Тесты (252 юнит-теста)
│   ├── unit/                        # Юнит-тесты (9 модулей)
│   └── scenarios/                   # YAML-сценарии (12 штук)
│
├── input/                           # Документы клиентов (для анализа)
├── output/                          # Результаты консультаций
├── logs/                            # Логи (10 файлов по направлениям)
├── locales/                         # Локализация (ru, en)
│
├── .env                             # Конфигурация (не коммитить!)
├── .env.example                     # Пример конфигурации (копия .env)
├── requirements.txt                 # Все зависимости
├── requirements-minimal.txt         # Минимальные зависимости (Python 3.14)
└── Makefile                         # Единая точка входа (make help)
```

## Фазы консультации

### Режимы Voice и Consultant (4 фазы)

```
DISCOVERY → ANALYSIS → PROPOSAL → REFINEMENT
```

| Фаза | Описание |
|------|----------|
| **Discovery** | Свободный диалог о бизнесе, выявление отрасли и контекста |
| **Analysis** | Анализ болей и потребностей, формирование BusinessAnalysis |
| **Proposal** | Предложение решения — функции агента, интеграции |
| **Refinement** | Уточнение деталей, генерация FAQ/KPI, финализация анкеты |

### Режим Maximum (3 фазы)

```
DISCOVERY → STRUCTURED → SYNTHESIS
```

| Фаза | Описание |
|------|----------|
| **Discovery** | Свободный диалог, сбор контекста о бизнесе и задачах |
| **Structured** | Структурированные вопросы из банка (INTERACTION / MANAGEMENT) |
| **Synthesis** | Синтез собранных данных, генерация анкеты |

Результат — **FinalAnketa v2.0** с 18 секциями (компания, агент, функции, интеграции, FAQ, KPI и др.).

## Хранение данных

| Хранилище | Используется в | Назначение |
|-----------|---------------|------------|
| **SQLite** (`data/sessions.db`) | Голосовой режим, ConsultantInterviewer (веб-сессии) | Сессии, диалоги, анкеты |
| **Redis** | Maximum режим | Кэш активных сессий (TTL 2ч) |
| **PostgreSQL** | Maximum режим | Постоянное хранение анкет |
| **Файловая система** (`output/`) | Все режимы | Финальный вывод: MD, JSON, логи диалогов |

Redis и PostgreSQL поднимаются через `config/docker-compose.yml` (Redis 7 + PostgreSQL 16). Схема БД — `config/init_db.sql`.

## API эндпоинты (голосовой режим)

| Метод | URL | Назначение |
|-------|-----|-----------|
| `GET` | `/` | Главная страница консультации |
| `GET` | `/session/{link}` | Страница возврата по уникальной ссылке |
| `POST` | `/api/session/create` | Создать сессию + LiveKit-комнату |
| `GET` | `/api/session/by-link/{link}` | Получить сессию по ссылке |
| `GET` | `/api/session/{id}` | Данные сессии |
| `GET` | `/api/session/{id}/anketa` | Данные анкеты (polling каждые 2 сек) |
| `PUT` | `/api/session/{id}/anketa` | Обновить анкету (клиент редактирует) |
| `POST` | `/api/session/{id}/confirm` | Подтвердить анкету |
| `POST` | `/api/session/{id}/end` | Завершить сессию |

Автоматическая документация (Swagger UI): `http://localhost:8000/docs`

## Тестирование

```bash
# Юнит-тесты (252 теста)
./venv/bin/python -m pytest tests/ -v

# Тестовая симуляция
./venv/bin/python scripts/run_test.py auto_service

# Pipeline: тест → ревью в редакторе
./venv/bin/python scripts/run_pipeline.py auto_service
```

12 готовых сценариев: auto_service, beauty_salon_glamour, logistics_company, medical_center, medical_clinic, online_school, real_estate_agency, realestate_domstroy, restaurant_delivery, restaurant_italiano, vitalbox и др.

Подробнее: [docs/TESTING.md](docs/TESTING.md)

## Логирование

Логи разделены на 10 файлов по направлениям + общий файл ошибок:

```
logs/
├── server.log          # HTTP API запросы
├── agent.log           # Жизненный цикл агента
├── livekit.log         # LiveKit (комнаты, токены, подключения)
├── dialogue.log        # Сообщения диалога
├── anketa.log          # Извлечение и обновление анкеты
├── azure.log           # Azure OpenAI Realtime (WSS)
├── session.log         # Сессии (создание, статусы)
├── deepseek.log        # DeepSeek API вызовы
├── notifications.log   # Email, webhooks
├── output.log          # Сохранение файлов
└── errors.log          # ВСЕ ошибки из всех компонентов (ERROR+)
```

Каждый процесс создаёт только свои логи:
- **Сервер** (`setup_logging("server")`): server, livekit, session, notifications
- **Агент** (`setup_logging("agent")`): agent, livekit, dialogue, anketa, azure, session, deepseek, output

Подробнее: [docs/LOGGING.md](docs/LOGGING.md)

## Troubleshooting

### Агент подключается, но молчит
```bash
# Проверьте логи агента на ошибки Azure WSS
grep -E "FAILED|ERROR|404" logs/azure.log

# Частая причина: неправильная API-версия для Realtime
# В .env должно быть: AZURE_OPENAI_REALTIME_API_VERSION=2024-10-01-preview
```

### Порт 8000 занят
```bash
lsof -ti:8000 | xargs kill -9
```

### Нет звука в браузере
Откройте F12 → Console, фильтр `[HANC]`. Если `muted: true` — кликните в любое место страницы (autoplay policy).

### DeepSeek API ошибки
```bash
# Проверка подключения
./venv/bin/python scripts/test_deepseek_api.py
```

## Документация

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура, компоненты, потоки данных
- [QUICKSTART.md](docs/QUICKSTART.md) — пошаговый запуск всех трёх режимов
- [VOICE_AGENT.md](docs/VOICE_AGENT.md) — голосовой агент (LiveKit + Azure OpenAI Realtime)
- [AGENT_WORKFLOWS.md](docs/AGENT_WORKFLOWS.md) — workflow агентов и pipeline
- [TESTING.md](docs/TESTING.md) — юнит-тесты, симуляция, E2E тесты
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — деплой и production-конфигурация
- [ERROR_HANDLING.md](docs/ERROR_HANDLING.md) — обработка ошибок
- [LOGGING.md](docs/LOGGING.md) — система логирования
- [PYTHON_3.14_SETUP.md](docs/PYTHON_3.14_SETUP.md) — установка с Python 3.14
- [PHILOSOPHY.md](docs/PHILOSOPHY.md) — философия проекта (AI-консультант, не опросник)

## Лицензия

MIT
