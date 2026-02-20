# Архитектура Hanc.AI Voice Consultant

Версия: 5.1 | Обновлено: 2026-02-18

## Общая архитектура

Система состоит из двух независимых процессов, текстового CLI-режима и режима Maximum Interview:

```
┌──────────────────────────────────────────────────────────────────────┐
│                      ГОЛОСОВОЙ РЕЖИМ                                 │
│                                                                      │
│  ┌────────────────────┐        ┌────────────────────┐               │
│  │   FastAPI Server   │◄──────►│  LiveKit Agent     │               │
│  │   (src/web/server) │  SQLite │  (src/voice/       │               │
│  │   :8000            │  БД     │   consultant)      │               │
│  └─────────┬──────────┘        └──────────┬─────────┘               │
│            │                               │                         │
│     ┌──────┴──────┐              ┌────────┴────────┐                │
│     │ public/     │              │ Azure OpenAI    │                │
│     │ index.html  │              │ Realtime (WSS)  │                │
│     │ + LiveKit   │              │ STT/TTS         │                │
│     │   JS SDK    │              └────────┬────────┘                │
│     └─────────────┘                       │                         │
│                                  ┌────────┴────────┐                │
│                                  │ DeepSeek LLM    │                │
│                                  │ (анализ анкеты) │                │
│                                  └─────────────────┘                │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                      ТЕКСТОВЫЙ CLI РЕЖИМ                             │
│                                                                      │
│  ┌────────────────────────────────────────────────────┐             │
│  │  ConsultantInterviewer (src/consultant/interviewer) │             │
│  │  4 фазы: Discovery → Analysis → Proposal →         │             │
│  │          Refinement                                  │             │
│  │  Rich CLI интерфейс                                 │             │
│  └─────────────────────────┬──────────────────────────┘             │
│                             │                                        │
│                    ┌────────┴────────┐                               │
│                    │ DeepSeek LLM    │                               │
│                    │ (диалог +       │                               │
│                    │  анкета)        │                               │
│                    └─────────────────┘                               │
└──────────────────────────────────────────────────────────────────────┘
```

## Процессы

### Процесс 1: FastAPI Web Server (`src/web/server.py`)

Запуск:

```bash
./venv/bin/python scripts/run_server.py
# или: ./venv/bin/python -m uvicorn src.web.server:app --host 0.0.0.0 --port 8000
```

Отвечает за:

- Раздачу фронтенда (`public/index.html`)
- REST API для управления сессиями
- Создание LiveKit комнат с agent dispatch
- Генерацию LiveKit токенов для клиентов
- Polling анкеты из SQLite для UI
- Health check голосового агента (PID-файл + `pgrep` fallback)
- Автоочистку старых LiveKit-комнат при старте сервера
- Управление LiveKit-комнатами (список, удаление)

Эндпоинты:

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/` | Главная страница консультации |
| GET | `/session/{link}` | Страница для возврата клиента по ссылке |
| POST | `/api/session/create` | Создание сессии + комнаты LiveKit |
| GET | `/api/session/by-link/{link}` | Получение сессии по уникальной ссылке |
| GET | `/api/session/{id}` | Полные данные сессии |
| GET | `/api/session/{id}/anketa` | Данные анкеты (polling каждые ~2 сек) |
| GET | `/api/session/{id}/reconnect` | Восстановление сессии (новый токен, пересоздание комнаты) |
| PUT | `/api/session/{id}/anketa` | Обновление анкеты из UI |
| POST | `/api/session/{id}/confirm` | Подтверждение анкеты + уведомления |
| POST | `/api/session/{id}/end` | Завершение сессии |
| POST | `/api/session/{id}/kill` | Принудительное завершение (удаление комнаты + статус declined) |
| GET | `/api/agent/health` | Проверка доступности голосового агента |
| GET | `/api/rooms` | Список активных LiveKit-комнат |
| DELETE | `/api/rooms` | Удаление всех LiveKit-комнат |

Startup-событие: `_cleanup_stale_rooms()` — удаляет все LiveKit-комнаты при старте сервера.

Логгеры: `server`, `livekit`, `session`

### Процесс 2: LiveKit Voice Agent (`src/voice/consultant.py`)

Запуск:

```bash
# Рекомендуется: через hanc.sh (управление процессами, PID-файл, логи)
./scripts/hanc.sh start

# Или напрямую:
./venv/bin/python scripts/run_voice_agent.py dev
```

Отвечает за:

- Подключение к LiveKit-комнате через WebRTC
- Голосовое общение через Azure OpenAI Realtime (STT/TTS)
- Запись диалога в VoiceConsultationSession
- Извлечение анкеты в реальном времени (после каждого сообщения пользователя, DeepSeek, sliding window 12 msgs)
- Периодическое сохранение dialogue_history (при каждом цикле extraction)
- Проактивное объявление о полученных документах (generate_reply после инъекции)
- Синхронизацию состояния с SQLite через HTTP API (SessionManager)
- Финализацию: полное извлечение анкеты + сохранение файлов
- Защиту от дублирования через PID-файл (`.agent.pid`)

Этапы инициализации (5 шагов):

1. Создание RealtimeModel (Azure OpenAI WSS)
2. Создание VoiceAgent (с системным промптом)
3. Подключение к комнате (`auto_subscribe=AUDIO_ONLY`)
4. Создание AgentSession + регистрация обработчиков событий
5. Запуск сессии (start → agent готов к разговору)

Логгеры: `agent`, `azure`, `dialogue`, `livekit`, `anketa`, `session`

### Текстовый CLI режим (`src/consultant/interviewer.py`)

Запуск:

```bash
python scripts/consultant_demo.py
```

Не требует LiveKit или Azure — работает напрямую с DeepSeek LLM через Rich CLI.

### Режим Maximum Interview (`src/interview/maximum.py`)

Запуск:

```bash
python scripts/demo.py
```

Альтернативный текстовый режим с 3-фазной консультацией и хранением в Redis + PostgreSQL.

Три фазы:

1. **DISCOVERY** — свободный диалог (5-15 ходов)
2. **STRUCTURED** — целенаправленный сбор недостающих данных (до 5 ходов)
3. **SYNTHESIS** — генерация анкеты через LLM

Хранение:

- Redis — активные сессии (InterviewContext, TTL 2 часа)
- PostgreSQL — завершённые анкеты (CompletedAnketa, InterviewSessionDB)

Логгеры: используются default structlog.get_logger() (без именованных категорий)

## Модули

```
src/
├── voice/                       # Голосовой агент
│   ├── consultant.py            # VoiceConsultationSession, entrypoint, finalize
│   └── livekit_client.py        # LiveKitClient (токены)
│
├── web/                         # Web сервер
│   └── server.py                # FastAPI приложение (14 эндпоинтов)
│
├── consultant/                  # Текстовый CLI консультант
│   ├── interviewer.py           # ConsultantInterviewer (4 фазы)
│   ├── phases.py                # ConsultantPhase enum
│   └── models.py                # BusinessAnalysis, ProposedSolution
│
├── anketa/                      # Анкета (генерация, извлечение, валидация)
│   ├── schema.py                # FinalAnketa v2.0 (18 блоков, Pydantic)
│   ├── extractor.py             # AnketaExtractor (LLM → FinalAnketa)
│   ├── generator.py             # AnketaGenerator (FinalAnketa → MD/JSON)
│   ├── data_cleaner.py          # JSONRepair, DialogueCleaner, SmartExtractor
│   ├── markdown_parser.py       # AnketaMarkdownParser (MD → FinalAnketa)
│   └── review_service.py        # AnketaReviewService (CLI preview + editor)
│
├── session/                     # Управление сессиями
│   ├── manager.py               # SessionManager (SQLite CRUD + status validation)
│   ├── models.py                # SessionStatus, RuntimeStatus, ConsultationSession (Pydantic)
│   └── status.py                # State machine (ALLOWED_TRANSITIONS, validate_transition)
│
├── output/                      # Сохранение результатов
│   └── manager.py               # OutputManager (versioned output)
│
├── llm/                         # LLM клиенты
│   ├── deepseek.py              # DeepSeekClient (chat API + retry)
│   └── anketa_generator.py      # LLMAnketaGenerator (LLM → FinalAnketa, 120 строк)
│
├── knowledge/                   # База знаний по отраслям (v2.0: мультирегиональная)
│   ├── models.py                # IndustryProfile, PainPoint, SalesScript, Competitor, ...
│   ├── loader.py                # IndustryProfileLoader (YAML + региональное наследование)
│   ├── manager.py               # IndustryKnowledgeManager
│   ├── matcher.py               # IndustryMatcher (определение отрасли)
│   ├── context_builder.py       # KBContextBuilder
│   ├── enriched_builder.py      # EnrichedContextBuilder (v2.0)
│   ├── country_detector.py      # CountryDetector (телефон + язык → страна)
│   └── validator.py             # ProfileValidator
│
├── documents/                   # Анализ документов клиента
│   ├── models.py                # ParsedDocument, DocumentContext
│   ├── parser.py                # DocumentParser + DocumentLoader
│   └── analyzer.py              # DocumentAnalyzer (LLM-анализ)
│
├── notifications/               # Уведомления
│   ├── manager.py               # NotificationManager (email + webhook)
│   └── models.py                # NotificationConfig
│
├── agent_client_simulator/      # Автоматическое тестирование
│   ├── client.py                # SimulatedClient (LLM-клиент)
│   ├── runner.py                # ConsultationTester + TestResult
│   ├── reporter.py              # TestReporter (console, JSON, MD)
│   └── validator.py             # TestValidator (6 проверок)
│
├── agent_document_reviewer/     # Ревью документов в редакторе
│   ├── reviewer.py              # DocumentReviewer
│   ├── editor.py                # ExternalEditor
│   ├── parser.py                # DocumentParser (diff)
│   ├── history.py               # VersionHistory
│   ├── validators.py            # Валидаторы
│   └── models.py                # ReviewConfig, ReviewResult
│
├── config/                      # Загрузка конфигурации
│   ├── prompt_loader.py         # PromptLoader: YAML промпты с шаблонизацией
│   ├── synonym_loader.py        # Словари синонимов (config/synonyms/)
│   └── locale_loader.py         # Локализация (locales/)
│
├── research/                    # Исследование внешних данных
│   ├── engine.py                # ResearchEngine (веб-поиск + парсинг + RAG)
│   ├── web_search.py            # WebSearchClient
│   └── website_parser.py        # WebsiteParser (парсинг сайтов)
│
├── storage/                     # Хранение (Redis + PostgreSQL)
│   ├── redis.py                 # RedisStorageManager (сессии, TTL 2ч)
│   └── postgres.py              # PostgreSQLStorageManager (анкеты, SQLAlchemy)
│
├── cli/                         # CLI-интерфейсы
│   ├── interface.py             # InterviewCLI (Rich dashboard)
│   └── maximum.py               # CLI для Maximum-режима
│
├── interview/                   # Maximum Interview режим (3 фазы)
│   ├── maximum.py               # MaximumInterviewer (744 строки)
│   ├── phases.py                # InterviewPhase, CollectedInfo, ANKETA_FIELDS
│   └── questions/               # Банки вопросов
│       ├── interaction.py       # 722 строки — вопросы для клиентов
│       └── management.py        # 736 строк — вопросы для сотрудников
│
├── models.py                    # 315 строк: InterviewPattern (INTERACTION, MANAGEMENT),
│                                #   InterviewStatus (INITIATED, IN_PROGRESS, PAUSED, COMPLETED, FAILED),
│                                #   QuestionStatus, AnalysisStatus, AnswerAnalysis, Clarification,
│                                #   QuestionResponse, InterviewContext (сессия для Redis),
│                                #   CompletedAnketa (анкета для PostgreSQL), InterviewStatistics
└── logging_config.py            # Централизованное логирование (14 категорий)
```

## Потоки данных

### Голосовой режим: полный цикл

```
Клиент (браузер)
    │
    ├─► GET / ──────────────► index.html + LiveKit JS SDK
    │
    ├─► POST /api/session/create
    │       │
    │       ├─► SessionManager.create_session() → SQLite
    │       ├─► LiveKitClient.create_token()
    │       └─► LiveKitAPI.create_room(agent_dispatch)
    │               │
    │               └─► LiveKit Server запускает Agent
    │                       │
    │                       └─► entrypoint(ctx)
    │                             │
    │                             ├─► RealtimeModel (Azure WSS)
    │                             ├─► VoiceAgent(instructions=prompt)
    │                             ├─► ctx.connect()
    │                             ├─► AgentSession + event handlers
    │                             └─► session.start()
    │
    ├─► WebRTC аудио ◄────────► LiveKit ◄────────► Azure Realtime
    │                                                (STT → LLM → TTS)
    │
    ├─► Каждое сообщение:
    │       ├─► consultation.add_message()
    │       ├─► _sync_to_db() → SQLite
    │       └─► После каждого сообщения пользователя:
    │               └─► _extract_and_update_anketa()
    │                       ├─► AnketaExtractor.extract() (DeepSeek, sliding window 12 msgs)
    │                       ├─► _update_anketa_via_api() → SQLite
    │                       └─► _update_dialogue_via_api() → SQLite (periodic persistence)
    │
    ├─► GET /api/session/{id}/anketa (polling ~2 сек)
    │       └─► Возвращает текущую анкету из SQLite
    │
    ├─► POST /api/session/{id}/confirm
    │       ├─► SessionManager.update_status("confirmed")
    │       └─► NotificationManager.on_session_confirmed()
    │
    └─► Отключение клиента:
            └─► _finalize_and_save()
                    ├─► AnketaExtractor.extract() (финальное)
                    ├─► OutputManager.save_anketa()
                    ├─► OutputManager.save_dialogue()
                    └─► SessionManager.update_session()
```

### Текстовый CLI режим: полный цикл

```
Пользователь (терминал)
    │
    └─► python scripts/consultant_demo.py
            │
            └─► ConsultantInterviewer(document_context=...)
                    │
                    ├─► [DocumentLoader → DocumentAnalyzer → DocumentContext]
                    ├─► [IndustryKnowledgeManager — 40 отраслей]
                    ├─► [EnrichedContextBuilder(KB + Documents + Learnings)]
                    │
                    ├─► ФАЗА 1: DISCOVERY
                    │       └─► DeepSeek + enriched context: диалог, сбор информации
                    │
                    ├─► ФАЗА 2: ANALYSIS
                    │       └─► DeepSeek + enriched context: BusinessAnalysis, PainPoints
                    │
                    ├─► ФАЗА 3: PROPOSAL
                    │       └─► DeepSeek + enriched context: ProposedSolution, functions
                    │
                    ├─► ФАЗА 4: REFINEMENT
                    │       ├─► AnketaExtractor.extract(document_context=...)
                    │       └─► OutputManager.save_anketa() + save_dialogue()
                    │
                    └─► Результат: output/{date}/{company}_v{N}/
                            ├── anketa.md    (содержит данные из документов)
                            ├── anketa.json
                            └── dialogue.md
```

## Модели данных

### FinalAnketa v2.0 (`src/anketa/schema.py`)

18 блоков данных:

| Блок | Тип | Источник |
|------|-----|----------|
| Информация о компании | company_name, industry, services, ... | Клиент |
| Функции агента | agent_functions, main_function | Клиент + AI |
| Параметры | voice_gender, voice_tone, language | Клиент |
| Интеграции | integrations | Клиент |
| FAQ с ответами | faq_items | AI |
| Работа с возражениями | objection_handlers | AI |
| Пример диалога | sample_dialogue | AI |
| Финансовая модель | financial_metrics | Клиент + AI |
| Конкуренты | competitors, market_insights | AI |
| Эскалация | escalation_rules | AI |
| KPI | success_kpis | AI |
| Чеклист запуска | launch_checklist | AI |
| Рекомендации AI | ai_recommendations | AI |
| Целевая аудитория | target_segments | AI |
| Тон общения | tone_of_voice | AI |
| Обработка ошибок | error_handling_scripts | AI |
| Follow-up | follow_up_sequence | AI |
| Метаданные | created_at, anketa_version, ... | Система |

### ConsultationSession (`src/session/models.py`)

Хранится в SQLite (`data/sessions.db`):

| Поле | Тип | Описание |
|------|-----|----------|
| session_id | str | UUID[:8] |
| room_name | str | LiveKit room (consultation-{session_id}) |
| unique_link | str | UUID для возврата клиента |
| status | str | active / paused / reviewing / confirmed / declined |
| runtime_status | str | idle / processing / completing / completed / error (ephemeral) |
| dialogue_history | JSON | [{role, content, timestamp, phase}] |
| anketa_data | JSON | FinalAnketa.model_dump() |
| anketa_md | str | Markdown-версия анкеты |
| company_name | str | Название компании |
| contact_name | str | Контактное лицо |
| duration_seconds | float | Длительность сессии |
| document_context | JSON | Данные из загруженных документов (key_facts, services, contacts) |
| voice_config | JSON | Конфигурация голоса (consultation_type, llm_provider, etc.) |
| output_dir | str | Путь к output/ |

### IndustryProfile v2.0 (`src/knowledge/models.py`)

YAML-профили отраслей в `config/industries/`:

40 отраслей (полный список в `_index.yaml`):

| Профиль | Файл | Профиль | Файл |
|---------|------|---------|------|
| Автобизнес / СТО | automotive.yaml | Страхование | insurance.yaml |
| Образование | education.yaml | Ритейл | retail.yaml |
| Франшизы | franchise.yaml | Строительство | construction.yaml |
| Рестораны / Отели | horeca.yaml | IT-услуги | it_services.yaml |
| Логистика | logistics.yaml | Рекрутинг | recruitment.yaml |
| Медицина | medical.yaml | Туризм | travel.yaml |
| Недвижимость | real_estate.yaml | Производство | manufacturing.yaml |
| Wellness / Красота | wellness.yaml | Сельское хозяйство | agriculture.yaml |
| Юридические услуги | legal.yaml | Ветеринария | veterinary.yaml |
| Финансы | finance.yaml | Клининг | cleaning.yaml |
| ... и ещё 20 отраслей | | | |

**v1.0 поля:** aliases, typical_services, pain_points, recommended_functions, typical_integrations, industry_faq, learnings, success_benchmarks.

**v2.0 новые поля:**

| Поле | Описание |
|------|----------|
| `sales_scripts` | Скрипты продаж для различных ситуаций |
| `competitors` | Анализ конкурентов на рынке |
| `pricing_context` | Ценовой контекст (валюта, ROI примеры) |
| `market_context` | Рыночный контекст (размер, тренды, сезонность) |
| `meta.region` | Код региона (eu, na, latam, mena, sea, ru) |
| `meta.country` | Код страны (de, us, br, etc.) |
| `meta.currency` | Валюта (EUR, USD, BRL, etc.) |
| `meta.phone_codes` | Телефонные коды страны |

### Мультирегиональная структура Knowledge Base

```text
config/industries/
├── _index.yaml              # Глобальный индекс отраслей
├── _countries.yaml          # Метаданные 23 стран (язык, валюта, телефон)
├── _base/                   # Базовые профили (шаблоны для наследования)
│   ├── automotive.yaml
│   ├── medical.yaml
│   └── ...                  # 40 базовых профилей
│
├── eu/                      # Европа
│   ├── de/                  # Германия
│   │   └── automotive.yaml  # Локализованный профиль
│   ├── at/                  # Австрия
│   ├── ch/                  # Швейцария
│   └── ...                  # 11 стран EU (at, bg, ch, es, fr, gr, hu, it, pt, ro)
│
├── na/                      # Северная Америка
│   ├── us/                  # США
│   └── ca/                  # Канада
│
├── latam/                   # Латинская Америка
│   ├── br/                  # Бразилия
│   ├── ar/                  # Аргентина
│   └── mx/                  # Мексика
│
├── mena/                    # Ближний Восток
│   ├── ae/                  # ОАЭ
│   ├── sa/                  # Саудовская Аравия
│   └── qa/                  # Катар
│
├── sea/                     # Юго-Восточная Азия
│   ├── cn/                  # Китай
│   ├── vn/                  # Вьетнам
│   └── id/                  # Индонезия
│
└── ru/                      # Россия (legacy)
```

**Наследование профилей:**

Региональные профили наследуют от базовых через `_extends`:

```yaml
# eu/de/automotive.yaml
_extends: _base/automotive

pain_points:
  - description: "Kunden rufen wegen Reparaturstatus an"
    severity: high
```

**Детекция страны:**

```python
from src.knowledge import get_country_detector

detector = get_country_detector()

# По телефону
region, country = detector.detect(phone="+49 151 12345678")
# → ("eu", "de")

# По языку текста
region, country = detector.detect(dialogue_text="Wir sind ein Autohaus in München")
# → ("eu", "de")

# Явный override
region, country = detector.detect(explicit_country="us")
# → ("na", "us")
```

**Загрузка региональных профилей:**

```python
from src.knowledge.loader import IndustryProfileLoader

loader = IndustryProfileLoader()

# Загрузка регионального профиля (с fallback на базовый)
profile = loader.load_regional_profile("eu", "de", "automotive")

print(profile.language)  # "de"
print(profile.currency)  # "EUR"
print(profile.competitors)  # [ATU, Vertragshändler, ...]
```

## Поток документов клиента (Document Pipeline)

```text
input/{company}/
├── brief.md
├── company_info.txt
├── data.xlsx
├── commercial_offer.docx
└── presentation.pdf
        │
        ▼
┌─────────────────┐
│ DocumentParser   │  PyMuPDF (PDF), python-docx (DOCX),
│ DocumentLoader   │  openpyxl (XLSX), regex (MD/TXT)
└────────┬────────┘
         │  List[ParsedDocument]
         ▼
┌─────────────────┐
│ DocumentAnalyzer │  Извлечение: services, contacts,
│ (sync)           │  key_facts, FAQ, prices
└────────┬────────┘
         │  DocumentContext
         ▼
┌─────────────────────────────────────────────────┐
│              EnrichedContextBuilder               │
│                                                   │
│  Industry KB  +  DocumentContext  +  Learnings   │
│       │               │                │          │
│       └───────────────┼────────────────┘          │
│                       ▼                           │
│              Enriched Prompt Context              │
└────────────────────────┬──────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────────┐
   │ DISCOVERY │   │ ANALYSIS │   │ PROPOSAL /   │
   │ phase     │   │ phase    │   │ REFINEMENT   │
   └──────────┘   └──────────┘   └──────┬───────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │AnketaExtractor│
                                  │(+doc_context) │
                                  └──────┬───────┘
                                         │
                                         ▼
                                  ┌──────────────┐
                                  │ FinalAnketa  │
                                  │ (с данными   │
                                  │  из документов)│
                                  └──────────────┘
```

### EnrichedContextBuilder (`src/knowledge/enriched_builder.py`)

Объединяет три источника контекста для каждой фазы консультации:

1. **Industry KB** — профиль отрасли (pain_points, recommended_functions, competitors, pricing_context)
2. **DocumentContext** — данные из документов клиента (services, contacts, key_facts)
3. **Learnings** — накопленный опыт из предыдущих консультаций

```python
from src.knowledge import EnrichedContextBuilder, IndustryKnowledgeManager

manager = IndustryKnowledgeManager()
builder = EnrichedContextBuilder(manager, document_context=doc_context)

# Генерация контекста для фазы
context = builder.build_for_phase("discovery", dialogue_history)
# → строка для добавления в промпт LLM
```

## Хранилища данных

| Хранилище | Путь | Содержимое | Режим |
|-----------|------|------------|-------|
| SQLite | `data/sessions.db` | Сессии, диалоги, анкеты | Voice + Consultant |
| Redis | `localhost:6379` | Активные InterviewContext (TTL 2ч) | Maximum |
| PostgreSQL | `localhost:5432` | CompletedAnketa, InterviewSessionDB | Maximum |
| Output | `output/{date}/{company}_v{N}/` | anketa.md, anketa.json, dialogue.md | Все |
| Логи | `logs/*.log` | 14 файлов по направлениям | Voice + Server |
| База знаний | `config/industries/` | 40 базовых + 928 региональных профилей (968 всего) | Все |
| Сценарии | `tests/scenarios/*.yaml` | 12 тестовых сценариев | Тестирование |
| Промпты | `prompts/` | YAML промпты для LLM | Все |
| Конфигурация | `config/` | профили отраслей, словари, уведомления | Все |

**Docker Compose:**

- `config/docker-compose.yml` — dev-инфраструктура (Redis + PostgreSQL + pgAdmin + Redis Commander)
- `docker-compose.yml` (корень) — production (Nginx + Certbot + Web + Agent + Redis + PostgreSQL)

Подробнее: [DEPLOYMENT.md](DEPLOYMENT.md)

## Внешние зависимости

| Сервис | Назначение | Переменная окружения |
|--------|------------|---------------------|
| LiveKit Server | WebRTC транспорт | LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET |
| Azure OpenAI Realtime | STT/TTS (голосовой режим) | AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY |
| DeepSeek API | LLM для диалога и анализа | DEEPSEEK_API_KEY |
| Redis Server | Кэш активных сессий (Maximum режим) | REDIS_HOST, REDIS_PORT |
| PostgreSQL | Долгосрочное хранение анкет (Maximum режим) | POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD |

Внешние Python-зависимости:

| Пакет | Назначение |
|-------|------------|
| livekit-agents | LiveKit Agents SDK |
| livekit-plugins-openai | Azure OpenAI Realtime плагин |
| fastapi + uvicorn | Web сервер |
| pydantic | Модели данных |
| structlog | Структурированное логирование |
| httpx | HTTP клиент (DeepSeek API) |
| rich | CLI интерфейс |
| pyyaml | Конфигурация |
| python-dotenv | Переменные окружения |

## Система промптов и конфигурации

Проект разделяет **данные** (`config/`) и **инструкции для LLM** (`prompts/`):

| Папка      | Содержит                            | Пример                                   |
|------------|-------------------------------------|------------------------------------------|
| `config/`  | **Данные** — что использовать       | Профили отраслей, словари синонимов      |
| `prompts/` | **Инструкции** — как общаться с LLM | Системные промпты для фаз консультации   |

### Структура config/

```text
config/
├── industries/                  # База знаний по отраслям (v2.0: мультирегиональная)
│   ├── _index.yaml              # Индекс: id → file, name, aliases
│   ├── _countries.yaml          # Метаданные стран (язык, валюта, телефон)
│   ├── _base/                   # Базовые профили (шаблоны)
│   │   ├── automotive.yaml
│   │   └── ...                  # 40 базовых профилей
│   ├── eu/de/                   # Региональные профили
│   │   └── automotive.yaml      # Локализованный профиль (наследует от _base/)
│   └── ...                      # 6 регионов, 23 страны
├── synonyms/                    # Словари нормализации полей анкеты
│   ├── base.yaml                # Общие синонимы (название → company_name)
│   ├── ru.yaml                  # Русские варианты
│   └── en.yaml                  # Английские варианты
├── personas/                    # Симулятор клиентов (для тестирования)
│   ├── traits.yaml              # Черты характера (терпеливый, нетерпеливый...)
│   └── prompts.yaml             # Промпты для генерации поведения
├── consultant/
│   └── kb_context.yaml          # Шаблоны форматирования KB → prompt
└── notifications.yaml           # SMTP настройки, шаблоны email
```

#### Использование config/

```python
# Загрузка профиля отрасли
from src.knowledge.manager import get_knowledge_manager
manager = get_knowledge_manager()
profile = manager.get_profile("logistics")
pain_points = profile.pain_points

# Загрузка синонимов
from src.config.synonym_loader import get_synonym_loader
loader = get_synonym_loader()
canonical = loader.normalize("название компании")  # → "company_name"
```

### Структура prompts/

Все промпты для LLM загружаются через `PromptLoader` (`src/config/prompt_loader.py`).

```text
prompts/
├── consultant/                  # Текстовая консультация (4 фазы)
│   ├── discovery.yaml           # Свободный диалог о бизнесе
│   ├── analysis.yaml            # Анализ болей
│   ├── proposal.yaml            # Предложение решения
│   └── refinement.yaml          # Уточнение деталей
├── voice/                       # Голосовой агент
│   ├── consultant.yaml          # Системный промпт + управление диалогом
│   └── review.yaml              # Фаза ревью анкеты
├── llm/                         # DeepSeek анализ
│   ├── analyze_answer.yaml      # Анализ ответа пользователя
│   ├── complete_anketa.yaml     # Генерация анкеты из ответов
│   └── generation.yaml          # Генерация диалогов/ограничений
└── anketa/                      # Генерация анкеты
    ├── extract.yaml             # Извлечение данных из диалога
    └── expert.yaml              # Генерация FAQ, KPI, рекомендаций
```

### Использование PromptLoader

```python
from src.config.prompt_loader import get_prompt, render_prompt

# Получить промпт
system_prompt = get_prompt("voice/consultant", "system_prompt")

# Рендеринг с переменными
user_prompt = render_prompt(
    "llm/analyze_answer", "user_prompt_template",
    question="Как называется ваша компания?",
    answer="Рестоклиника",
    section="Общие"
)
```

### Поддерживаемый синтаксис шаблонов

- `{{variable}}` — простая подстановка
- `{{#if condition}}...{{/if}}` — условный блок
- `{{#each items}}...{{/each}}` — цикл

## Безопасность

- API ключи хранятся в `.env` (не коммитится)
- SQLite база в `data/` (не коммитится)
- LiveKit токены генерируются с ограниченным TTL
- Уникальные ссылки сессий — полные UUID
- SMTP credentials в `config/notifications.yaml` (не коммитится)
