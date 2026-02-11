# Методология тестирования и проверки готовности

Полный чек-лист для проверки работоспособности проекта и готовности к запуску.

## Оглавление

- [Быстрая проверка (10 минут)](#быстрая-проверка-10-минут)
- [Обзор](#обзор)
- [Этап 1: Юнит-тесты](#этап-1-юнит-тесты)
- [Этап 2: Интеграционные тесты](#этап-2-интеграционные-тесты)
- [Этап 2.5: Wiring Verification](#этап-25-wiring-verification-проверка-подключённости-пайплайнов)
- [Этап 2.6: KB Phase Integration](#этап-26-kb-phase-integration)
- [Этап 3: Мульти-региональная Knowledge Base](#этап-3-мульти-региональная-knowledge-base-валидация-и-ремонт)
- [Этап 4: Production Readiness](#этап-4-production-readiness)
- [Этап 5: Проверка подключений к сервисам](#этап-5-проверка-подключений-к-сервисам)
- [Этап 6: Модуль обогащения контекста](#этап-6-модуль-обогащения-контекста)
- [Этап 6.5: Парсинг документов](#этап-65-парсинг-документов-из-input)
- [Этап 7: LLM-симуляция](#этап-7-llm-симуляция)
- [Этап 7.5: LLM-симуляция с документами](#этап-75-llm-симуляция-с-документами)
- [Этап 8: Голосовой агент (E2E)](#этап-8-голосовой-агент-e2e)
- [Этап 9: Docker-деплой и SSL](#этап-9-docker-деплой-и-ssl)
- [Troubleshooting](#troubleshooting)
- [Автоматизация (CI/CD)](#автоматизация-cicd-planned)

---

## Быстрая проверка (10 минут)

Минимальный набор команд для проверки работоспособности (порядок соответствует этапам):

```bash
# 1. Юнит-тесты + интеграционные (Этап 1 + 2.6 — должны пройти все, 1806 тестов)
./venv/bin/python -m pytest --tb=short

# 2. Покрытие (Этап 1 — должно быть ≥50%)
./venv/bin/python -m pytest --cov=src --cov-report=term | tail -5

# 2.5. Wiring verification (Этап 2.5 — пайплайны подключены, 39 тестов)
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py -v

# 3. Knowledge Base валидация (Этап 3 — 968 профилей)
./venv/bin/python scripts/validate_all_profiles.py --errors-only
./venv/bin/python scripts/validate_deep.py

# 4. DeepSeek API (Этап 5 — реальное подключение)
./venv/bin/python -c "
import asyncio
from src.llm.deepseek import DeepSeekClient
async def test():
    c = DeepSeekClient()
    r = await c.chat([{'role': 'user', 'content': 'ping'}])
    print(f'✅ DeepSeek: {len(r)} chars')
asyncio.run(test())
"

# 5. Azure OpenAI (Этап 5 — реальное подключение)
./venv/bin/python -c "
import asyncio
from src.llm.azure_chat import AzureChatClient
async def test():
    c = AzureChatClient()
    r = await c.chat([{'role': 'user', 'content': 'ping'}], max_tokens=50)
    print(f'✅ Azure OpenAI: {len(r)} chars')
asyncio.run(test())
"

# 6. LiveKit (Этап 5 — реальное подключение)
./venv/bin/python -c "
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
./venv/bin/python scripts/test_document_parsing.py

# 7. LLM-симуляция (Этап 7 — один сценарий)
./venv/bin/python scripts/run_test.py auto_service --quiet

# 7.5. LLM + документы (Этап 7.5 — с input-dir)
./venv/bin/python scripts/run_test.py logistics_company --input-dir input/test_docs/ --quiet
```

---

## Обзор

Этапы упорядочены по принципу зависимостей: **дешёвые оффлайн-проверки → конфигурация → подключения → функциональные тесты**.

| Этап | Что проверяем | Инструмент | Критерий прохождения |
|------|---------------|------------|----------------------|
| 1. Юнит-тесты | Логика модулей | pytest | 100% passed, coverage ≥50% |
| 2. Интеграция | Связи между модулями | pytest + fixtures | Все интеграционные тесты passed |
| **2.5. Wiring** | **Подключённость пайплайнов** | **grep + python** | **Все критические пайплайны подключены** |
| 3. Мульти-региональная KB | 968 YAML-профилей, 23 страны | validate scripts | 0 errors, 0 deep warnings |
| 4. Production readiness | .env, директории, API | чек-лист + smoke test | Все проверки пройдены |
| 5. Подключения | DeepSeek, Azure OpenAI, Redis, PostgreSQL, LiveKit | python scripts | Реальные соединения установлены |
| 6. Обогащение контекста | Knowledge Base, Documents, Learnings | python scripts | Профили валидны, контекст генерируется |
| 6.5. Парсинг документов | PDF, DOCX, XLSX, TXT, MD из input/ | test_document_parsing.py | 11/11 файлов, 5 форматов, 3 папки |
| 7. LLM-симуляция | Полный цикл консультации | run_test.py | 4/4 фазы, анкета сгенерирована |
| 7.5. LLM + документы | Симуляция с --input-dir | run_test.py --input-dir | Документы загружены, контекст в консультации |
| 8. Голосовой агент | WebRTC + STT/TTS | e2e_voice_test.js | Все этапы passed |
| **9. Docker-деплой** | **Сборка, SSL, nginx, healthcheck** | **docker compose + curl** | **6/6 сервисов Up, HTTPS 200** |

**Фазы:**
- **Фаза A (Оффлайн):** Этапы 1–3 — не требуют внешних сервисов
- **Фаза B (Конфигурация):** Этап 4 — проверка .env и инфраструктуры
- **Фаза C (Подключения):** Этап 5 — реальные соединения к сервисам
- **Фаза D (Функциональные):** Этапы 6–8 — требуют живых API
- **Фаза E (Деплой):** Этап 9 — Docker-контейнеры, SSL, nginx reverse proxy

> **ВАЖНО — Урок KB-инцидента (v4.0):** Этапы 1–3 и 6 ранее тестировали компоненты **изолированно**: юнит-тесты проверяли, что `get_enriched_system_prompt()` генерирует контекст, а Этап 6.3 проверял, что KB-контекст создаётся. Но **ни один тест не проверял, что эта функция вызывается** из `entrypoint()` голосового агента. В результате 968 KB-профилей были полностью реализованы, но **не подключены** к голосовому агенту на протяжении всей разработки. Этап 2.5 (Wiring Verification) добавлен для предотвращения подобных инцидентов.

---

## Этап 1: Юнит-тесты

### 1.1 Требования

- Python 3.11+ (рекомендуется 3.14)
- Virtual environment активирован
- Зависимости установлены: `pip install -r requirements.txt`

### 1.2 Запуск

```bash
# Все тесты
./venv/bin/python -m pytest

# С покрытием
./venv/bin/python -m pytest --cov=src --cov-report=term-missing

# Подробный вывод
./venv/bin/python -m pytest -v

# Конкретный модуль
./venv/bin/python -m ./venv/bin/python -m pytest tests/unit/test_knowledge.py -v
```

### 1.3 Критерии прохождения

| Метрика | Минимум | Текущее значение |
|---------|---------|------------------|
| Тесты passed | 100% | 1806/1806 |
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
│   ├── test_api_server.py         # FastAPI endpoints (48 тестов)
│   │   ├── TestCreateSession      # POST /api/session/create
│   │   ├── TestGetSession         # GET /api/session/{id}
│   │   ├── TestGetSessionByLink   # GET /api/session/by-link/{link}
│   │   ├── TestGetAnketa          # GET /api/session/{id}/anketa
│   │   ├── TestUpdateAnketa       # PUT /api/session/{id}/anketa
│   │   ├── TestConfirmSession     # POST /api/session/{id}/confirm
│   │   ├── TestEndSession         # POST /api/session/{id}/end
│   │   ├── TestListSessions       # GET /api/sessions (Dashboard) — 8 тестов
│   │   ├── TestPageRoutes         # GET /, /session/{link}, /session/{link}/review — 5 тестов
│   │   ├── TestDeleteSessions     # POST /api/sessions/delete (Bulk delete) — 4 теста
│   │   └── TestFullLifecycleFlow  # E2E: create→anketa→end→confirm + dashboard lifecycle
│   ├── test_session_manager.py    # SQLite CRUD (39 тестов)
│   │   ├── TestCreateSession      # Создание сессий
│   │   ├── TestGetSession         # Чтение по ID
│   │   ├── TestGetSessionByLink   # Чтение по unique_link
│   │   ├── TestUpdateSession      # Обновление полей
│   │   ├── TestUpdateAnketa       # Anketa CRUD
│   │   ├── TestUpdateStatus       # Статусы: active/paused/confirmed/declined
│   │   ├── TestListSessions       # Фильтрация по статусу (4 теста)
│   │   ├── TestListSessionsSummary # Dashboard-запрос (8 тестов) — фильтры, лимит, сортировка
│   │   ├── TestDeleteSessions     # Bulk delete (5 тестов)
│   │   ├── TestJSONRoundTrip      # Сериализация JSON-полей
│   │   └── TestClose              # Корректное закрытие
│   ├── test_redis_storage.py      # Redis operations
│   ├── test_postgres_storage.py   # PostgreSQL operations
│   ├── test_data_cleaner.py       # JSON repair, dialogue cleaning
│   ├── test_output_manager.py     # File output, versioning
│   ├── test_consultant_interviewer.py  # Consultation phases
│   ├── test_cli_interface.py      # CLI dashboard
│   ├── test_knowledge.py          # Industry profiles, matching
│   ├── test_documents.py          # Document parsing, analysis
│   ├── test_voice_pipeline_wiring.py  # Pipeline wiring (39 тестов)
│   │   ├── TestVoiceConsultationSessionFlags  # Флаги: review_started, research_done, kb_enriched
│   │   ├── TestNotificationManagerWiring      # NotificationManager → _finalize_and_save()
│   │   ├── TestReviewPhaseWiring              # Review phase → _extract_and_update_anketa()
│   │   ├── TestRecordLearningWiring           # record_learning() → _finalize_and_save()
│   │   ├── TestCountryDetectorWiring          # CountryDetector → KB enrichment
│   │   ├── TestResearchEngineWiring           # ResearchEngine → background task
│   │   ├── TestRedisWiring                    # RedisStorageManager → hot cache
│   │   ├── TestFunctionsImportable            # Все pipeline-функции импортируются
│   │   └── TestReviewPhaseHelpers             # format_anketa_for_voice, get_review_system_prompt
│   ├── test_anketa_extractor.py       # AnketaExtractor pipeline (88 тестов)
│   ├── test_anketa_generator.py       # AnketaGenerator markdown/JSON (58 тестов)
│   ├── test_anketa_generator_standalone.py  # LLMAnketaGenerator enrichment (18 тестов)
│   ├── test_azure_chat.py             # Azure OpenAI Chat client (23 теста)
│   ├── test_consultant_core.py        # Voice consultant core functions (118 тестов)
│   │   ├── TestVoiceConsultationSession     # VCS init, add_message, get_duration, get_company_name
│   │   ├── TestGetSystemPrompt              # Загрузка системного промпта
│   │   ├── TestGetEnrichedSystemPrompt      # Обогащённый промпт с KB
│   │   ├── TestBuildResumeContext           # Контекст возобновления сессии
│   │   ├── TestHandleConversationItem       # Обработка событий диалога
│   │   ├── TestRegisterEventHandlers        # Регистрация обработчиков
│   │   ├── TestGetVoiceId                   # voice_gender → Azure voice ID (6 тестов)
│   │   ├── TestApplyVoiceConfigUpdate       # Mid-session speed/silence/voice/verbosity (15 тестов)
│   │   ├── TestGetVerbosityPromptPrefix     # Verbosity prefix strings (5 тестов)
│   │   └── TestApplyVerbosityUpdate         # Async verbosity instruction update (6 тестов)
│   ├── test_country_detector.py       # Country/region detection (34 теста)
│   ├── test_deepseek.py               # DeepSeek LLM client (33 теста)
│   ├── test_enriched_context.py       # EnrichedContextBuilder (25 тестов)
│   ├── test_interview_context.py      # Interview context management (27 тестов)
│   ├── test_llm_factory.py            # LLM client factory (12 тестов)
│   ├── test_locale_loader.py          # YAML locale loader (21 тест)
│   ├── test_markdown_parser.py        # Anketa markdown parser (91 тест)
│   ├── test_maximum_interviewer.py    # Maximum interviewer logic (50 тестов)
│   ├── test_notifications.py          # NotificationManager email+webhook (32 теста)
│   ├── test_prompt_loader.py          # YAML prompt loader (53 теста)
│   ├── test_research_engine.py        # Research engine orchestration (31 тест)
│   ├── test_review_service.py         # Anketa review workflow (32 теста)
│   ├── test_session_models.py         # Session pydantic models (38 тестов)
│   ├── test_synonym_loader.py         # Synonym loader + deep merge (33 теста)
│   ├── test_web_search.py             # Web search client (25 тестов)
│   └── test_website_parser.py         # Website HTML parser (37 тестов)
├── integration/
│   └── test_kb_phase_integration.py   # KB full injection + phase re-injection (26 тестов)
│       ├── TestP1_FullKBInjection           # build_for_voice_full() с синтетическим профилем (11 тестов)
│       ├── TestP1_RealKBProfiles            # Реальные YAML-профили из config/industries/ (3 теста)
│       ├── TestP2_PhaseDetection            # _detect_consultation_phase() переходы (6 тестов)
│       ├── TestP2_SessionPhaseTracking      # VoiceConsultationSession phase fields (3 теста)
│       ├── TestP2_KBReinjection             # E2E: KB реинжекция при смене фазы (3 теста)
│       └── TestP2_EnrichedPromptPhase       # get_enriched_system_prompt() с параметром phase (2 теста)
└── scenarios/                         # YAML для LLM-симуляции
```

**Итого: 39 тестовых файлов, 1806 тестов** (1779 unit + 27 integration).

### 1.6 UI / Dashboard тесты

Тесты покрывают новый Web UI: дашборд, SPA-роутинг, review-экран.

#### SessionManager: `TestListSessionsSummary` (8 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_returns_empty_list_when_no_sessions` | Пустая БД → `[]` |
| 2 | `test_returns_correct_fields` | Ровно 9 lightweight-полей (session_id, unique_link, status, created_at, updated_at, company_name, contact_name, duration_seconds, room_name) |
| 3 | `test_excludes_heavy_fields` | НЕ содержит dialogue_history, anketa_data, anketa_md, document_context |
| 4 | `test_filter_by_status` | Фильтрация по paused / active / confirmed |
| 5 | `test_filter_no_matches` | Фильтр без совпадений → `[]` |
| 6 | `test_limit_and_offset` | Пагинация: limit=2, offset=3, offset за пределами |
| 7 | `test_ordered_by_created_at_desc` | Сортировка: новые сначала |
| 8 | `test_no_filter_returns_all_statuses` | Без фильтра → все статусы |

#### API Server: `TestListSessions` (8 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_returns_200_empty` | `GET /api/sessions` → 200, sessions=[], total=0 |
| 2 | `test_returns_created_sessions` | Созданная сессия появляется в списке |
| 3 | `test_summary_has_expected_fields` | 9 обязательных полей в каждой summary (включая room_name) |
| 4 | `test_summary_excludes_heavy_fields` | Нет dialogue_history, anketa_data, anketa_md |
| 5 | `test_filter_by_status` | `?status=active` / `?status=paused` фильтрует |
| 6 | `test_filter_no_matches` | `?status=confirmed` при 0 confirmed → total=0 |
| 7 | `test_limit_parameter` | `?limit=2` ограничивает результат |
| 8 | `test_multiple_sessions_ordered_newest_first` | Порядок: новые сначала |

#### API Server: `TestPageRoutes` (5 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_index_does_not_500` | `GET /` не возвращает 500 |
| 2 | `test_session_page_invalid_link_returns_404` | `GET /session/{bad_link}` → 404 |
| 3 | `test_session_page_valid_link_does_not_500` | `GET /session/{link}` для существующей сессии |
| 4 | `test_review_page_invalid_link_returns_404` | `GET /session/bad/review` → 404 |
| 5 | `test_review_page_valid_link_does_not_500` | `GET /session/{link}/review` для существующей сессии |

#### SessionManager: `TestDeleteSessions` (5 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_delete_single_session` | Удаление одной сессии — запись исчезает из БД |
| 2 | `test_delete_multiple_sessions` | Удаление нескольких сессий — все удалены, остальные на месте |
| 3 | `test_delete_nonexistent_returns_zero` | Несуществующие ID → rowcount = 0 |
| 4 | `test_delete_empty_list` | Пустой список → 0 без ошибки |
| 5 | `test_deleted_sessions_not_in_summary` | Удалённые сессии не появляются в `list_sessions_summary()` |

#### API Server: `TestDeleteSessions` (4 теста)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_delete_sessions_returns_count` | `POST /api/sessions/delete` → `{"deleted": N}` |
| 2 | `test_delete_empty_returns_zero` | Пустой `session_ids` → `{"deleted": 0}` |
| 3 | `test_deleted_not_in_dashboard` | После удаления сессия не появляется в `GET /api/sessions` |
| 4 | `test_delete_nonexistent_returns_zero` | Несуществующие ID → `{"deleted": 0}` |

#### API Server: `TestFullLifecycleFlow` — `test_dashboard_lifecycle_flow`

Полный сквозной тест жизненного цикла дашборда:

1. `GET /api/sessions` → пустой дашборд (total=0)
2. Создание 2 сессий через `POST /api/session/create`
3. Заполнение анкеты в s1 (company_name="Альфа")
4. `GET /api/sessions` → total=2
5. `POST /api/session/{id}/end` → s1 переходит в paused
6. Фильтрация: `?status=active` → 1, `?status=paused` → 1
7. Review: `GET /api/session/by-link/{link}` → полные данные (с anketa_data, dialogue_history)
8. `POST /api/session/{id}/confirm` → s1 переходит в confirmed
9. Фильтрация: `?status=confirmed` → 1

### 1.7 Mid-session Voice Config тесты (v5.0)

Тесты покрывают применение настроек голоса mid-session при возвращении пользователя в существующую сессию.

#### `TestGetVoiceId` (6 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_none_config_returns_alloy` | `None` voice_config → "alloy" |
| 2 | `test_empty_config_returns_alloy` | `{}` → "alloy" |
| 3 | `test_male_returns_echo` | `voice_gender="male"` → "echo" |
| 4 | `test_female_returns_shimmer` | `voice_gender="female"` → "shimmer" |
| 5 | `test_neutral_returns_alloy` | `voice_gender="neutral"` → "alloy" |
| 6 | `test_unknown_returns_alloy` | Неизвестное значение → "alloy" (fallback) |

#### `TestApplyVoiceConfigUpdate` (15 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_no_session_id_returns_early` | Пустой session_id → нет чтения из БД |
| 2 | `test_session_not_found_returns_early` | Несуществующая сессия → graceful return |
| 3 | `test_unchanged_config_skips_update` | Неизменённый config → нет `update_options()` |
| 4 | `test_speed_change_calls_update_options` | speed 1.0→1.25 → `update_options(speed=1.25)` |
| 5 | `test_silence_change_calls_update_options` | silence 2000→3000 → `TurnDetection(silence=3000)` |
| 6 | `test_voice_change_calls_update_options` | neutral→male → `update_options(voice="echo")` |
| 7 | `test_multiple_changes_combined` | 3 параметра → один вызов `update_options` |
| 8 | `test_config_state_updated_after_apply` | `config_state` обновляется после применения |
| 9 | `test_speed_clamped_to_range` | 5.0 → clamped to 1.5 |
| 10 | `test_silence_clamped_to_range` | 100ms → clamped to 300ms |
| 11 | `test_exception_is_non_fatal` | RuntimeError → `log.warning`, нет propagation |
| 12 | `test_verbosity_change_schedules_async_task` | verbosity normal→concise → `create_task()` |
| 13 | `test_verbosity_unchanged_no_async_task` | verbosity не менялся → `get_running_loop` не вызван |
| 14 | `test_verbosity_change_no_agent_session_skips` | Нет agent_session → async task не планируется |
| 15 | `test_all_five_settings_changed` | Все 5 настроек → `update_options` + async task |

#### `TestGetVerbosityPromptPrefix` (5 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_concise` | "concise" → prefix с "МАКСИМАЛЬНО кратко" |
| 2 | `test_verbose` | "verbose" → prefix с "развёрнутые ответы" |
| 3 | `test_normal_returns_empty` | "normal" → пустая строка |
| 4 | `test_unknown_returns_empty` | Неизвестное значение → пустая строка |
| 5 | `test_prefixes_dict_has_concise_and_verbose` | `_VERBOSITY_PREFIXES` содержит concise/verbose, но не normal |

#### `TestApplyVerbosityUpdate` (6 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_no_activity_logs_warning` | Нет `_activity` → log.warning |
| 2 | `test_strips_old_concise_prefix_adds_verbose` | concise→verbose: strip старый prefix, prepend новый |
| 3 | `test_strips_old_verbose_prefix_adds_nothing_for_normal` | verbose→normal: strip prefix, без нового |
| 4 | `test_no_old_prefix_adds_new` | Нет prefix → prepend новый |
| 5 | `test_preserves_kb_and_resume_context` | KB + resume context сохраняются при смене verbosity |
| 6 | `test_exception_is_non_fatal` | RuntimeError → log.warning, нет propagation |

---

## Этап 2: Интеграционные тесты

### 2.1 Проверка связей

```bash
# Тесты с реальными fixtures
./venv/bin/python -m pytest tests/unit/test_api_server.py -v

# Проверка полного flow анкеты
./venv/bin/python -m pytest tests/unit/test_data_cleaner.py::TestAnketaPostProcessor -v

# Dashboard API + lifecycle
./venv/bin/python -m pytest tests/unit/test_api_server.py::TestListSessions -v
./venv/bin/python -m pytest tests/unit/test_api_server.py::TestPageRoutes -v
./venv/bin/python -m pytest tests/unit/test_api_server.py::TestFullLifecycleFlow::test_dashboard_lifecycle_flow -v

# SessionManager: lightweight dashboard query
./venv/bin/python -m pytest tests/unit/test_session_manager.py::TestListSessionsSummary -v

# Bulk delete — SessionManager
./venv/bin/python -m pytest tests/unit/test_session_manager.py::TestDeleteSessions -v

# Bulk delete — API
./venv/bin/python -m pytest tests/unit/test_api_server.py::TestDeleteSessions -v
```

### 2.2 Критерии

- Все API endpoints возвращают корректные статусы
- Session flow работает: create → update → complete
- Anketa extraction из диалога работает
- Dashboard API: `GET /api/sessions` возвращает lightweight-summaries (без dialogue_history, anketa_data)
- SPA-роутинг: `GET /`, `/session/{link}`, `/session/{link}/review` — корректные статусы (200 или 404)
- Dashboard lifecycle: пустой список → создание → фильтрация → review → confirm
- Bulk delete: `POST /api/sessions/delete` удаляет записи из БД, удалённые сессии не появляются в `GET /api/sessions`
- Dashboard summary содержит 9 lightweight-полей (включая `room_name`)

---

## Этап 2.5: Wiring Verification (Проверка подключённости пайплайнов)

> **Предпосылка:** В v3.5 обнаружено, что база знаний (968 профилей) была полностью реализована, юнит-тесты проходили, Этап 6.3 подтверждал генерацию контекста — но **функция `get_enriched_system_prompt()` никогда не вызывалась** из голосового агента. Все 1000 тестов были зелёными, но в production KB не работала.
>
> **Корневая причина:** Юнит-тесты проверяли компоненты **изолированно** (function works), но не проверяли **wiring** (function is called from the right place). Это классический gap между unit и integration testing.

### 2.5.1 Критические wiring-проверки

Каждая проверка верифицирует, что конкретный пайплайн **реально подключён** к голосовому агенту (не просто существует в коде).

```bash
# Wiring verification: все проверки должны пройти
./venv/bin/python -c "
import ast, sys

# Parse consultant.py AST
with open('src/voice/consultant.py') as f:
    tree = ast.parse(f.read())

# Collect all function/method calls as strings
calls = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)

checks = {
    'update_anketa':               'Анкета сохраняется в БД',
    'update_instructions':         'Промпт обновляется mid-session (KB injection)',
    '_extract_and_update_anketa':  'Экстракция анкеты вызывается',
    '_finalize_and_save':          'Финализация сессии вызывается',
    'on_session_confirmed':        'NotificationManager отправляет уведомления',
    'get_review_system_prompt':    'Review phase переключает агент на проверку анкеты',
    'record_learning':             'Learnings записываются в KB отрасли',
    'get_country_detector':        'CountryDetector определяет страну клиента',
    '_run_background_research':    'ResearchEngine запускает фоновое исследование',
    '_try_get_redis':              'RedisStorageManager кэширует активные сессии',
}

all_ok = True
for func, desc in checks.items():
    found = func in calls
    status = '✅' if found else '❌'
    print(f'{status} {func}() — {desc}')
    if not found:
        all_ok = False

sys.exit(0 if all_ok else 1)
"
```

### 2.5.2 Проверка dead code в voice agent

Обнаруженные функции, которые **определены но НЕ вызываются** — индикатор отключённых пайплайнов:

```bash
# Поиск определённых, но не вызываемых функций в consultant.py
./venv/bin/python -c "
import re

with open('src/voice/consultant.py') as f:
    content = f.read()

# Find function definitions (top-level and nested)
defs = re.findall(r'^(?:async )?def (\w+)\(', content, re.MULTILINE)

# For each definition, check if it's called elsewhere
for func in defs:
    # Count calls (not the definition itself)
    call_pattern = rf'(?<!def ){func}\s*\('
    calls = len(re.findall(call_pattern, content))
    if calls == 0:
        print(f'⚠️  DEAD CODE: {func}() — определена, но не вызывается')
"
```

### 2.5.3 Проверка подключённости модулей к голосовому агенту

| Пайплайн | Файл | Критическая функция | Должна вызываться из | Статус |
| --- | --- | --- | --- | --- |
| KB инъекция | `src/knowledge/enriched_builder.py` | `EnrichedContextBuilder.build_for_voice()` | `_extract_and_update_anketa()` (inline) | ✅ Подключена (v4.1, inline с CountryDetector) |
| Экстракция анкеты | `src/anketa/extractor.py` | `AnketaExtractor.extract()` | `_extract_and_update_anketa()` | ✅ Подключена |
| Сохранение анкеты | `src/session/manager.py` | `update_anketa()` | `_extract_and_update_anketa()` | ✅ Подключена |
| Финализация | `src/voice/consultant.py` | `_finalize_and_save()` | `entrypoint()` | ✅ Подключена |
| Обновление промпта | LiveKit SDK | `activity.update_instructions()` | `_extract_and_update_anketa()` | ✅ Подключена (v4.0) |
| Уведомления | `src/notifications/manager.py` | `on_session_confirmed()` | `_finalize_and_save()` | ✅ Подключена (v4.1) |
| Review phase | `src/voice/consultant.py` | `get_review_system_prompt()` + `format_anketa_for_voice()` | `_extract_and_update_anketa()` | ✅ Подключена (v4.1) |
| Learnings | `src/knowledge/manager.py` | `record_learning()` | `_finalize_and_save()` | ✅ Подключена (v4.1) |
| Country Detection | `src/knowledge/country_detector.py` | `detect()` + `load_regional_profile()` | `_extract_and_update_anketa()` KB enrichment | ✅ Подключена (v4.1) |
| Research Engine | `src/research/engine.py` | `engine.research()` | `_extract_and_update_anketa()` → background task | ✅ Подключена (v4.1) |
| Redis Cache | `src/storage/redis.py` | `client.setex()` / `client.delete()` | `entrypoint()`, `_extract_and_update_anketa()`, `_finalize_and_save()` | ✅ Подключена (v4.1) |

### 2.5.4 Известные отключённые пайплайны

Следующие компоненты **реализованы в коде**, но **НЕ подключены** к голосовому агенту. Это **осознанное решение** (CLI-only) или **запланированная функциональность**:

| Компонент | Файл | Статус | Причина |
| --- | --- | --- | --- |
| `get_enriched_system_prompt()` | `consultant.py:204` | Dead code (v4.1) | Заменена inline KB enrichment с CountryDetector в `_extract_and_update_anketa()`. Используется только в тестах |
| `entrypoint()` | `consultant.py` | Ложный dead code | Вызывается LiveKit SDK через декоратор `@ctx.connect()`, не напрямую |
| `get_industry_faq()` | `knowledge/manager.py:164` | Не вызывается из voice | Только в CLI-режиме (KB инъекция покрывает FAQ) |
| `AnketaReviewService` | `anketa/review_service.py` | CLI-only | Внешний редактор, не для voice |
| `ProfileValidator` | `knowledge/validator.py` | Dev/test | Не используется в runtime |

> **Подключены в v4.1:** NotificationManager, Review phase, record_learning, CountryDetector, ResearchEngine, RedisStorageManager — см. таблицу 2.5.3. **Рекомендация:** При добавлении нового пайплайна — добавьте wiring-проверку в Этап 2.5.1 и обновите таблицу 2.5.3.

### 2.5.5 Дополнительные workflows (не пайплайны)

Эти workflows не являются отдельными пайплайнами, но участвуют в работе голосового агента:

| Workflow | Описание | Точка входа | Тестовое покрытие |
| --- | --- | --- | --- |
| **DocumentContext** | Загруженные документы клиента (`input/`) передаются в `AnketaExtractor` через `DocumentContext` для учёта при извлечении анкеты. Если `db_session.document_context` заполнен, создаётся `DocumentContext` объект. | `_extract_and_update_anketa()`, `_finalize_and_save()` | `test_documents.py` (документы), `test_voice_pipeline_wiring.py` (wiring) |
| **Session Resume** | При повторном подключении к существующей сессии (комната `consultation-{id}`), агент восстанавливает контекст: `dialogue_history`, `anketa_data`, `document_context` из SQLite через `SessionManager.get_session()`. | `entrypoint()` → `_lookup_db_session()` | `test_session_manager.py`, `test_api_server.py` |

### 2.5.6 Автоматические wiring-тесты (39 тестов)

> **Файл:** `tests/unit/test_voice_pipeline_wiring.py`
>
> Эти тесты проверяют, что 7 пайплайнов v4.2 **реально вызываются** голосовым агентом в нужных местах, с правильными параметрами, и корректно обрабатывают ошибки. Каждый тест использует mock-патчинг зависимостей и вызывает реальные функции `_extract_and_update_anketa()` и `_finalize_and_save()` из `consultant.py`.

```bash
# Запуск всех wiring-тестов
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py -v

# Запуск тестов конкретного пайплайна
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestNotificationManagerWiring -v
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestReviewPhaseWiring -v
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestRecordLearningWiring -v
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestCountryDetectorWiring -v
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestResearchEngineWiring -v
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestRedisWiring -v
./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestPostgreSQLWiring -v
```

#### Pipeline 1: NotificationManager (2 теста)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_notification_sent_on_finalize` | `NotificationManager.on_session_confirmed()` вызывается в `_finalize_and_save()` |
| 2 | `test_notification_failure_does_not_crash` | Ошибка SMTP/webhook не ломает финализацию — `update_session()` всё равно вызывается |

**Что значит «подключён»:** При завершении сессии агент отправляет уведомление менеджеру (email + webhook). Конфигурация в `config/notifications.yaml`, по умолчанию `email.enabled: false`.

#### Pipeline 2: Review Phase (4 теста)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_review_phase_triggered` | При `completion_rate >= 0.5` и `>= 16 сообщений` — агент переключается на проверку анкеты: вызываются `get_review_system_prompt()`, `update_instructions()`, `generate_reply()` |
| 2 | `test_review_phase_not_triggered_low_completion` | При `completion_rate < 0.5` — review НЕ запускается |
| 3 | `test_review_phase_not_triggered_few_messages` | При `< 16 сообщений` — review НЕ запускается (даже если completion = 0.8) |
| 4 | `test_review_phase_not_triggered_twice` | Флаг `review_started = True` предотвращает повторный запуск |

**Что значит «подключён»:** Когда анкета достаточно заполнена и прошло минимум 8 обменов (~6 минут), агент зачитывает анкету клиенту для подтверждения/корректировки. Промпт берётся из `prompts/voice/review.yaml`.

#### Pipeline 3: record_learning (2 теста)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_learning_recorded_on_finalize` | `manager.record_learning(industry_id, insight, source)` вызывается при финализации с правильными аргументами: `industry_id = "logistics"`, `source` содержит `session_id` |
| 2 | `test_learning_not_recorded_without_industry` | Если отрасль не определена — `record_learning()` НЕ вызывается (нет бесполезных записей) |

**Что значит «подключён»:** После завершения сессии агент записывает инсайт (компания, кол-во заполненных полей, длительность) в YAML-профиль отрасли для накопления опыта.

#### Pipeline 4: CountryDetector (2 теста)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_country_detector_called_for_kb_enrichment` | `CountryDetector.detect()` вызывается, и при обнаружении страны используется `load_regional_profile(region, country, industry_id)` |
| 2 | `test_fallback_to_base_profile_when_no_country` | Если страна не определена — используется `get_profile(industry_id)` (базовый профиль), `load_regional_profile()` НЕ вызывается |

**Что значит «подключён»:** При KB-обогащении определяется страна клиента (по телефону, языку диалога) и загружается региональный профиль с локальными конкурентами, compliance, ценами. Если региональный профиль не найден — fallback на `_base/`.

**Важно (патчинг):** `get_country_detector` патчится на SOURCE модуле `src.knowledge.country_detector.get_country_detector`, НЕ на `src.voice.consultant.get_country_detector` — потому что это lazy import внутри функции.

#### Pipeline 5: ResearchEngine (5 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_research_launched_when_website_present` | Фоновое исследование запускается, когда `anketa.company_website` заполнен; `research_done = True` |
| 2 | `test_research_not_launched_without_website` | Без сайта исследование НЕ запускается; `research_done = False` |
| 3 | `test_research_not_launched_twice` | Флаг `research_done = True` предотвращает повторный запуск |
| 4 | `test_run_background_research_injects_results` | `_run_background_research()` инжектирует результаты в промпт агента через `update_instructions()`, результат содержит «Данные исследования» |
| 5 | `test_run_background_research_handles_failure` | Ошибка API не ломает функцию — не выбрасывает исключение |

**Что значит «подключён»:** Когда из анкеты извлекается URL сайта клиента, запускается фоновая задача (`asyncio.create_task`) которая парсит сайт + ищет инсайты и обогащает контекст агента. Исследование 5–30 секунд, не блокирует основной поток.

#### Pipeline 6: RedisStorageManager (6 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_try_get_redis_returns_none_when_unavailable` | Если `health_check() = False` — возвращает `None` |
| 2 | `test_try_get_redis_returns_manager_when_available` | Если `health_check() = True` — возвращает `RedisStorageManager` |
| 3 | `test_try_get_redis_caches_result` | Singleton: повторный вызов возвращает тот же объект, не создаёт новый |
| 4 | `test_try_get_redis_handles_import_error` | Если пакет `redis` не установлен — возвращает `None`, не падает |
| 5 | `test_redis_updated_during_extraction` | `client.setex("voice:session:{id}", 7200, ...)` вызывается в `_extract_and_update_anketa()` |
| 6 | `test_redis_deleted_on_finalize` | `client.delete("voice:session:{id}")` вызывается в `_finalize_and_save()` |

**Что значит «подключён»:** Redis используется как горячий кэш активных голосовых сессий. Ключ `voice:session:{session_id}` содержит статус, кол-во сообщений, completion rate. TTL = 2 часа. Redis полностью опционален — если недоступен, всё работает через SQLite.

#### Pipeline 7: PostgreSQLStorageManager (6 тестов)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_try_get_postgres_returns_none_when_unavailable` | Без `DATABASE_URL` → возвращает `None` |
| 2 | `test_try_get_postgres_returns_manager_when_available` | С `health_check() = True` → возвращает `PostgreSQLStorageManager` |
| 3 | `test_try_get_postgres_caches_result` | Singleton: повторный вызов возвращает тот же объект |
| 4 | `test_try_get_postgres_handles_import_error` | Если `psycopg2` не установлен → возвращает `None`, не падает |
| 5 | `test_postgres_saved_on_finalize` | `save_anketa()` + `update_interview_session()` вызываются в `_finalize_and_save()` с правильными параметрами |
| 6 | `test_postgres_not_called_without_anketa_data` | Если `session.anketa_data` пуст — PostgreSQL НЕ вызывается |

**Что значит «подключён»:** PostgreSQL используется для долгосрочного хранения заполненных анкет (таблица `anketas` с JSONB) и истории сессий (таблица `interview_sessions`). Сессия регистрируется при подключении к комнате (`entrypoint()`), анкета сохраняется при финализации (`_finalize_and_save()`). Полностью опционален — если PostgreSQL недоступен, всё работает через SQLite.

#### Вспомогательные тесты (9 тестов)

| Класс | Тесты | Что проверяет |
|-------|-------|---------------|
| `TestVoiceConsultationSessionFlags` | 3 | Флаги `review_started`, `research_done`, `kb_enriched` существуют и инициализированы как `False` |
| `TestFunctionsImportable` | 6 | Все pipeline-функции (`_try_get_redis`, `_try_get_postgres`, `_run_background_research`, `get_review_system_prompt`, `format_anketa_for_voice`, `get_system_prompt`) импортируются без ошибок |

#### Тесты helper-функций Review Phase (3 теста)

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_format_anketa_for_voice_with_data` | Форматирование анкеты для озвучивания: заполненные поля включены, `None` поля пропущены, списки через запятую |
| 2 | `test_format_anketa_for_voice_empty` | Пустая анкета → текст содержит «пуста» |
| 3 | `test_get_review_system_prompt_contains_summary` | Промпт review содержит переданные данные анкеты и слово «проверка» |

### 2.5.7 Ручная верификация пайплайнов (live session)

> **Когда использовать:** После прохождения автоматических тестов (2.5.1 + 2.5.6), для финальной проверки в живой среде. Запустите голосовой агент, проведите разговор ~10 минут, затем проверьте логи.

#### Подготовка

```bash
# Терминал 1: Веб-сервер
./venv/bin/./venv/bin/python scripts/run_server.py

# Терминал 2: Голосовой агент
./scripts/hanc.sh start

# Терминал 3: Мониторинг логов (все пайплайны)
tail -f /tmp/agent_entrypoint.log | grep -E "notification_sent|review_phase_started|learning_recorded|KB context injected|research_launched|research_injected|Redis|redis"
```

#### Сценарий ручного теста

Проведите голосовую консультацию, упоминая:

1. **Название компании** и **отрасль** (для KB enrichment + CountryDetector)
2. **Сайт компании** (для ResearchEngine)
3. **Телефон** (для CountryDetector)
4. Отвечайте на вопросы агента ~6 минут (для trigger Review Phase)
5. Завершите сессию (для NotificationManager + record_learning + Redis cleanup + PostgreSQL save)

#### Ожидаемые лог-сообщения по пайплайнам

| # | Пайплайн | Лог-сообщение | Когда появляется | Команда проверки |
|---|----------|---------------|------------------|------------------|
| 1 | KB + CountryDetector | `KB context injected` с полями `industry=`, `region=`, `country=` | После ~6 сообщений (первая экстракция) | `grep "KB context injected" /tmp/agent_entrypoint.log` |
| 2 | ResearchEngine | `research_launched` + `website=` | Когда клиент называет сайт | `grep "research_launched" /tmp/agent_entrypoint.log` |
| 3 | ResearchEngine | `research_injected` + `sources=` | Через 5–30с после запуска | `grep "research_injected" /tmp/agent_entrypoint.log` |
| 4 | Review Phase | `review_phase_started` + `completion_rate=`, `message_count=` | При `completion >= 0.5` и `messages >= 16` | `grep "review_phase_started" /tmp/agent_entrypoint.log` |
| 5 | NotificationManager | `notification_sent` | При завершении сессии | `grep "notification_sent" /tmp/agent_entrypoint.log` |
| 6 | record_learning | `learning_recorded` + `industry_id=` | При завершении сессии | `grep "learning_recorded" /tmp/agent_entrypoint.log` |
| 7 | Redis (register) | `Session registered in Redis` | При подключении к комнате | `grep "registered in Redis" /tmp/agent_entrypoint.log` |
| 8 | Redis (cleanup) | Отсутствие ключа `voice:session:{id}` | После завершения сессии | `redis-cli KEYS "voice:session:*"` (должно быть пусто) |
| 9 | PostgreSQL (register) | `Session registered in PostgreSQL` | При подключении к комнате | `psql -U interviewer_user -d voice_interviewer -c "SELECT count(*) FROM interview_sessions"` |
| 10 | PostgreSQL (save) | `postgres_saved` | При завершении сессии | `psql -U interviewer_user -d voice_interviewer -c "SELECT anketa_id, company_name FROM anketas ORDER BY created_at DESC LIMIT 1"` |

#### Автоматизированная проверка логов

```bash
# После завершения тестовой сессии — проверить все пайплайны одной командой
echo "=== Pipeline Verification ==="
LOG="/tmp/agent_entrypoint.log"

checks=(
    "KB context injected:CountryDetector + KB enrichment"
    "research_launched:ResearchEngine (запуск)"
    "review_phase_started:Review Phase"
    "notification_sent:NotificationManager"
    "learning_recorded:record_learning"
    "registered in Redis:Redis registration"
    "registered in PostgreSQL:PostgreSQL registration"
    "postgres_saved:PostgreSQL save"
)

pass=0
fail=0
for check in "${checks[@]}"; do
    pattern="${check%%:*}"
    desc="${check##*:}"
    if grep -q "$pattern" "$LOG" 2>/dev/null; then
        echo "✅ $desc — найдено в логах"
        ((pass++))
    else
        echo "❌ $desc — НЕ найдено в логах"
        ((fail++))
    fi
done

echo ""
echo "Результат: $pass/6 пайплайнов подтверждены"
[ "$fail" -eq 0 ] && echo "✅ Все пайплайны функционируют" || echo "⚠️  $fail пайплайн(ов) не подтверждены — проверьте сценарий теста"
```

#### Условия для срабатывания каждого пайплайна

| Пайплайн | Условие | Если не сработал |
|----------|---------|------------------|
| KB + Country | Отрасль определяется из диалога, `kb_enriched = False` | Убедитесь, что клиент явно назвал отрасль |
| ResearchEngine | `anketa.company_website` заполнен, `research_done = False` | Клиент должен назвать URL сайта |
| Review Phase | `completion_rate >= 0.5` + `messages >= 16` + `review_started = False` | Нужно ~8 обменов и заполнить ≥9 из 18 полей анкеты |
| NotificationManager | Сессия завершена через `_finalize_and_save()` | Завершите сессию через UI или `/api/session/{id}/end` |
| record_learning | Отрасль определена + `anketa_data` не пусто | Должна быть заполнена хотя бы часть анкеты |
| Redis | `_try_get_redis()` возвращает не `None` | Запустите Redis: `redis-server` или `docker-compose up -d redis` |

### 2.5.8 Критерии прохождения

| Проверка | Критерий |
| --- | --- |
| AST wiring checks (2.5.1) | 10/10 ✅ |
| Dead code analysis (2.5.2) | 0 неожиданных dead functions (известные — в таблице 2.5.4) |
| Модули подключены (2.5.3) | Все 11 критических пайплайнов ✅ |
| Автоматические wiring-тесты (2.5.6) | 39/39 passed |
| Ручная верификация (2.5.7) | 6/6 пайплайнов подтверждены в логах (при наличии Redis) |

---

## Этап 2.6: KB Phase Integration

> **Предпосылка:** В v4.2 аудит показал, что `build_for_voice()` отдаёт ~200 байт (10% KB данных). FAQ, возражения, скрипты продаж, конкуренты, ценообразование и рынок — 0% использования. KB инжектился один раз за сессию без учёта фазы разговора.
>
> **Решение:** `build_for_voice_full()` собирает полный контекст (~2-5 KB) с учётом фазы. Фаза определяется при каждой extraction и KB реинжектится при смене фазы (discovery → analysis → proposal → refinement).

### 2.6.1 Запуск

```bash
# Все интеграционные тесты KB + фазы (26 тестов)
./venv/bin/python -m pytest tests/integration/test_kb_phase_integration.py -v

# Отдельно P1 (полная KB-инжекция)
./venv/bin/python -m pytest tests/integration/test_kb_phase_integration.py::TestP1_FullKBInjection -v
./venv/bin/python -m pytest tests/integration/test_kb_phase_integration.py::TestP1_RealKBProfiles -v

# Отдельно P2 (фазовая реинжекция)
./venv/bin/python -m pytest tests/integration/test_kb_phase_integration.py::TestP2_PhaseDetection -v
./venv/bin/python -m pytest tests/integration/test_kb_phase_integration.py::TestP2_KBReinjection -v
```

### 2.6.2 P1: Полная KB-инжекция (14 тестов)

**TestP1_FullKBInjection** (11 тестов) — синтетический профиль со всеми v2.0 полями:

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_voice_full_includes_phase_kb_context` | `build_for_voice_full()` возвращает непустой контекст с pain points |
| 2 | `test_voice_full_includes_competitors` | Конкуренты (FedEx, UPS) присутствуют в discovery/analysis фазах |
| 3 | `test_voice_full_includes_pricing` | Ценообразование (бюджет, entry point) в discovery фазе |
| 4 | `test_voice_full_includes_market` | Рыночный контекст ($1.6T, тренды) в discovery фазе |
| 5 | `test_voice_full_includes_sales_scripts_in_proposal` | Скрипты продаж (триггеры) в proposal фазе |
| 6 | `test_voice_full_includes_learnings` | Раздел "НАКОПЛЕННЫЙ ОПЫТ" при наличии learnings |
| 7 | `test_voice_full_respects_token_budget` | Контекст не превышает 4000 символов |
| 8 | `test_voice_full_empty_without_profile` | Пустая строка при отсутствии профиля |
| 9 | `test_voice_full_vs_voice_compact_size` | Full контекст > 2x размер compact контекста |
| 10 | `test_all_four_phases_produce_different_context` | Разные фазы дают разный контекст |

**TestP1_RealKBProfiles** (3 теста) — реальные YAML-профили из `config/industries/`:

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_us_logistics_has_v2_data` | `na/us/logistics.yaml` содержит sales_scripts, competitors, pricing, market |
| 2 | `test_us_logistics_full_context_is_rich` | Реальный профиль даёт >500 символов контекста |
| 3 | `test_de_logistics_full_context` | `eu/de/logistics.yaml` — региональный профиль работает (skip если не найден) |

### 2.6.3 P2: Фазовая реинжекция (12 тестов)

**TestP2_PhaseDetection** (6 тестов) — `_detect_consultation_phase()`:

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_discovery_phase_start` | <8 сообщений, completion <0.15 → discovery |
| 2 | `test_analysis_phase` | 8-14 сообщений или completion 0.15-0.35 → analysis |
| 3 | `test_proposal_phase` | 14-20 сообщений или completion 0.35-0.50 → proposal |
| 4 | `test_refinement_phase` | completion ≥0.50 или review_started → refinement |
| 5 | `test_review_started_overrides_all` | `review_started=True` → refinement при любых метриках |
| 6 | `test_phase_progression_with_increasing_messages` | Фазы прогрессируют монотонно, никогда не идут назад |

**TestP2_SessionPhaseTracking** (3 теста):

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_default_phase_is_discovery` | Новая сессия начинается в discovery |
| 2 | `test_phase_persists_in_messages` | Сообщения записывают текущую фазу |
| 3 | `test_cached_profile_prevents_re_detection` | Кешированный профиль не пересоздаётся |

**TestP2_KBReinjection** (3 теста) — E2E с mocked agent_session:

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_kb_reinjected_on_phase_change` | Первая инжекция: определяется отрасль, страна, фаза; `update_instructions()` вызван |
| 2 | `test_kb_not_reinjected_when_phase_unchanged` | Та же фаза + `kb_enriched=True` → `update_instructions()` НЕ вызван |
| 3 | `test_phase_transition_triggers_reinjection` | Смена analysis→proposal → `update_instructions()` вызван с новым контекстом |

**TestP2_EnrichedPromptPhase** (2 теста):

| # | Тест | Что проверяет |
|---|------|---------------|
| 1 | `test_phase_appears_in_enriched_prompt` | Имя фазы появляется в заголовке промпта |
| 2 | `test_different_phases_call_builder_with_different_phase` | Builder вызывается с правильным phase параметром |

### 2.6.4 Критерии прохождения

| Метрика | Минимум | Текущее значение |
|---------|---------|------------------|
| P1: Full KB injection | 14/14 passed | 14/14 ✅ (1 skip: DE profile) |
| P2: Phase re-injection | 12/12 passed | 12/12 ✅ |
| Полный контекст > компактного | >2x | ✅ |
| Фазы монотонно прогрессируют | Никогда назад | ✅ |
| Реальные YAML-профили загружаются | US logistics | ✅ |

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
./venv/bin/python scripts/validate_all_profiles.py

# С подробным выводом
./venv/bin/python scripts/validate_all_profiles.py --verbose

# По конкретному региону
./venv/bin/python scripts/validate_all_profiles.py --region eu

# Только ошибки (без предупреждений)
./venv/bin/python scripts/validate_all_profiles.py --errors-only
```

**Критерий прохождения:** 920/920 региональных профилей valid, 0 errors.

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
./venv/bin/python scripts/validate_deep.py

# С подробным выводом
./venv/bin/python scripts/validate_deep.py --verbose
```

**Критерий прохождения:** 0 errors, 0 warnings (info — допустимо).

### 3.3 Инструментарий ремонта профилей

> **Примечание:** Эти скрипты были одноразовыми и удалены. Профили уже исправлены.

При обнаружении проблем использовались специализированные скрипты:

| Скрипт | Назначение | Что исправляет |
|--------|------------|----------------|
| `fix_enums.py` | Нормализация enum-значений | hoch→high, mittel→medium, alto→high и т.д. для 11+ языков |
| `fix_aliases.py` | Генерация aliases | Добавляет блок `aliases` с 3–6 синонимами отрасли |
| `fix_entry_points.py` | Числовые entry_point | "150 CHF für..."→150, "$65"→65, "Rp 50.000"→50000 |
| `fix_incomplete_profiles.py` | Дополнение профилей (LLM) | Генерирует отсутствующие секции через Azure OpenAI |
| `fix_l2_subfields.py` | Дополнение sub-fields (LLM) | Добавляет sales_scripts, competitors, seasonality, roi_examples |
| `fix_l10_pricing.py` | Исправление pricing | payback=0→1, non-numeric→число, payback>36→пересчёт |

> Все скрипты ремонта были одноразовыми и удалены после исправления профилей.

### 3.4 Генерация профилей

Для создания новых региональных профилей используется `generate_profiles.py`:

```bash
# Генерация профилей для конкретной страны
./venv/bin/python scripts/generate_profiles.py --country de --provider azure

# Генерация всех профилей для региона
./venv/bin/python scripts/generate_profiles.py --region eu --provider azure

# Список поддерживаемых стран
./venv/bin/python scripts/generate_profiles.py --list-countries
```

**Поддерживаемые провайдеры:** `azure` (по умолчанию), `deepseek`.

### 3.5 Сводная таблица

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
./venv/bin/python -c "
import asyncio
from httpx import ASGITransport, AsyncClient
from src.web.server import app

async def test():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as ac:
        # Root endpoint (Dashboard)
        resp = await ac.get('/')
        print(f'GET /: {resp.status_code}')

        # Dashboard API — список сессий
        resp = await ac.get('/api/sessions')
        print(f'GET /api/sessions: {resp.status_code}')
        if resp.status_code == 200:
            total = resp.json().get('total', 0)
            print(f'  Sessions in dashboard: {total}')

        # Create session
        resp = await ac.post('/api/session/create', json={'pattern': 'interaction'})
        print(f'POST /api/session/create: {resp.status_code}')

        if resp.status_code == 200:
            session_id = resp.json().get('session_id', '')[:8]
            link = resp.json().get('unique_link', '')
            print(f'Session created: {session_id}...')

            # Session page (SPA routing)
            resp = await ac.get(f'/session/{link}')
            print(f'GET /session/{{link}}: {resp.status_code}')

            # Review page (SPA routing)
            resp = await ac.get(f'/session/{link}/review')
            print(f'GET /session/{{link}}/review: {resp.status_code}')

            # Dashboard after creation
            resp = await ac.get('/api/sessions')
            total = resp.json().get('total', 0)
            print(f'GET /api/sessions (after create): total={total}')

            # Filter by status
            resp = await ac.get('/api/sessions?status=active')
            active = resp.json().get('total', 0)
            print(f'GET /api/sessions?status=active: total={active}')

            # Bulk delete
            resp = await ac.post('/api/sessions/delete', json={'session_ids': [session_id]})
            print(f'POST /api/sessions/delete: {resp.status_code}')
            if resp.status_code == 200:
                deleted = resp.json().get('deleted', 0)
                print(f'  Deleted: {deleted}')

asyncio.run(test())
"
```

### 4.4 Запуск

```bash
# Development
./venv/bin/python scripts/run_server.py

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
docker compose -f config/docker-compose.yml up -d redis postgres

# 3. Дождаться готовности (10-15 секунд)
sleep 10

# 4. Проверить статус контейнеров
docker compose -f config/docker-compose.yml ps
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
./venv/bin/python -c "
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
./venv/bin/python -c "
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
./venv/bin/python -c "
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
./venv/bin/python -c "
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
./venv/bin/python -c "
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
./venv/bin/python -c "
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
docker compose -f config/docker-compose.yml up -d

# Проверка статуса
docker compose -f config/docker-compose.yml ps

# Логи
docker compose -f config/docker-compose.yml logs -f
```

---

## Этап 6: Модуль обогащения контекста

> **Требования:** Этапы 3 и 5 пройдены (KB валидна, подключения к LLM работают).

### 6.1 Проверка Knowledge Base

```bash
# Валидация всех профилей отраслей
./venv/bin/python -c "
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
./venv/bin/python -c "
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

### 6.3 Проверка Voice интеграции (KB Enrichment)

> **Контекст (v4.1):** Функция `get_enriched_system_prompt()` — **dead code**. KB-обогащение теперь выполняется inline в `_extract_and_update_anketa()` через `EnrichedContextBuilder.build_for_voice()` + `CountryDetector` + `update_instructions()`. Wiring проверяется в Этапе 2.5.

```bash
# Проверка: KB enrichment pipeline подключён (wiring-тесты)
./venv/bin/python -m ./venv/bin/python -m pytest tests/unit/test_voice_pipeline_wiring.py::TestCountryDetectorWiring -v

# Проверка: EnrichedContextBuilder генерирует контекст
./venv/bin/./venv/bin/python -c "
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder

manager = IndustryKnowledgeManager()
builder = EnrichedContextBuilder(manager, document_context=None)
context = builder.build_for_voice('logistics', dialogue_history=[])
print(f'Voice context length: {len(context)} chars')
print(f'Has content: {bool(context)}')
"
```

### 6.4 Тесты модуля обогащения

```bash
# Запуск unit-тестов для модуля обогащения
./venv/bin/python -m pytest tests/unit/test_enriched_context.py -v

# С покрытием
./venv/bin/python -m pytest tests/unit/test_enriched_context.py --cov=src/knowledge --cov-report=term-missing
```

### 6.5 Сводная таблица

| Проверка | Критерий |
|----------|----------|
| Профили валидны | Все профили ≥70% completeness |
| Контекст генерируется | Все 4 фазы возвращают непустой контекст |
| Learnings включены | Контекст содержит накопленный опыт |
| Voice интеграция | Голосовой агент получает отраслевой контекст |
| Тесты проходят | Enriched context 25/25 passed |

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
├── goodpoint/                     # GoodPoint (Product Description)
│   └── 01_Product_Description_v0.2.md  # Описание продукта (187 чанков, 6518 слов)
├── test_docs/                     # ГрузовичкоФ (логистика)
│   ├── test_brief.md              # Бриф
│   ├── company_info.txt           # Описание компании
│   ├── data.xlsx                  # Прайс-лист + скидки (2 листа)
│   ├── commercial_offer.docx      # Коммерческое предложение
│   └── presentation.pdf           # Презентация (3 стр.)
└── test/                          # АвтоПрофи (автосервис)
    ├── brief.md                   # Бриф
    ├── company_info.txt           # Описание компании
    ├── data.xlsx                  # Прайс-лист
    ├── commercial_offer.docx      # Коммерческое предложение
    └── presentation.pdf           # Презентация (1 стр.)
```

### 6.5.4 Генерация тестовых документов

> Скрипт `generate_test_documents.py` удалён — документы уже сгенерированы и хранятся в `input/`.

### 6.5.5 Запуск теста

```bash
# Полный тест парсинга (все папки, все форматы)
./venv/bin/python scripts/test_document_parsing.py

# С подробным выводом (preview чанков, контакты, промпт)
./venv/bin/python scripts/test_document_parsing.py --verbose

# Конкретная папка
./venv/bin/python scripts/test_document_parsing.py --dir input/test_docs
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
| Файлов распарсено | 11/11 | 11/11 ✅ |
| Форматов покрыто | 5/5 (.pdf, .docx, .xlsx, .txt, .md) | 5/5 ✅ |
| Папок протестировано | 3/3 | 3/3 ✅ |
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
./venv/bin/python scripts/run_test.py --list

# Один сценарий
./venv/bin/python scripts/run_test.py logistics_company

# Тихий режим
./venv/bin/python scripts/run_test.py logistics_company --quiet

# Полный pipeline (тест + ревью анкеты)
./venv/bin/python scripts/run_pipeline.py logistics_company

# С документами клиента
./venv/bin/python scripts/run_test.py logistics_company --input-dir input/test_docs/
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
./venv/bin/python scripts/run_test.py logistics_company --input-dir input/test_docs/

# Автосервис с документами АвтоПрофи
./venv/bin/python scripts/run_test.py auto_service --input-dir input/test/

# Ресторан с документами Bella Italia
./venv/bin/python scripts/run_test.py restaurant_italiano --input-dir input/restaurant_italiano/
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
./venv/bin/python -c "
import importlib.metadata
v = importlib.metadata.version('livekit-plugins-openai')
print(f'livekit-plugins-openai: {v}')
from livekit.plugins.openai.realtime.realtime_model import TurnDetection
print('TurnDetection: OK')
" 2>/dev/null || echo "livekit-plugins-openai: ERROR — run: pip install -U livekit-plugins-openai"

# 5. Веб-сервер и агент не запущены (порт 8000 свободен)
curl -s -o /dev/null http://localhost:8000 && echo "Port 8000: BUSY — kill existing server first" || echo "Port 8000: FREE"
```

### 8.0.1 Аудит и очистка комнат LiveKit

**Цель:** E2E тест должен работать на чистой среде — 0 комнат до начала. Старые комнаты могут блокировать агент-диспетчеризацию, занимать ресурсы и искажать результаты теста.

```bash
# Полный аудит: перечисление, классификация и очистка
./venv/bin/python -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from livekit.api import LiveKitAPI, ListRoomsRequest, DeleteRoomRequest

async def audit_and_cleanup():
    lk = LiveKitAPI(
        url=os.getenv('LIVEKIT_URL'),
        api_key=os.getenv('LIVEKIT_API_KEY'),
        api_secret=os.getenv('LIVEKIT_API_SECRET'),
    )

    result = await lk.room.list_rooms(ListRoomsRequest())
    rooms = result.rooms

    if not rooms:
        print('✅ LiveKit: 0 комнат — среда чистая')
        await lk.aclose()
        return

    print(f'⚠️  Найдено {len(rooms)} комнат:')
    print()

    active = []   # participants > 0
    zombie = []   # participants == 0

    for r in rooms:
        kind = 'ACTIVE' if r.num_participants > 0 else 'ZOMBIE'
        bucket = active if r.num_participants > 0 else zombie
        bucket.append(r)
        print(f'  [{kind}] {r.name}  sid={r.sid}  participants={r.num_participants}  created={r.creation_time}')

    print()
    if active:
        print(f'🔴 Активных комнат (с участниками): {len(active)}')
        for r in active:
            print(f'   → Удаляю {r.name} ({r.num_participants} участников)...')
            await lk.room.delete_room(DeleteRoomRequest(room=r.name))
            print(f'     ✅ Удалена')

    if zombie:
        print(f'💀 Зомби-комнат (0 участников): {len(zombie)}')
        for r in zombie:
            print(f'   → Удаляю {r.name} (пустая, осталась от прошлой сессии)...')
            await lk.room.delete_room(DeleteRoomRequest(room=r.name))
            print(f'     ✅ Удалена')

    # Верификация
    result2 = await lk.room.list_rooms(ListRoomsRequest())
    remaining = len(result2.rooms)
    await lk.aclose()

    print()
    if remaining == 0:
        print(f'✅ Очистка завершена: удалено {len(rooms)}, осталось 0')
    else:
        print(f'❌ После очистки осталось {remaining} комнат — требуется ручная проверка')

asyncio.run(audit_and_cleanup())
"
```

**Альтернативно** через CLI-скрипт или API:

```bash
# CLI (с автоподтверждением)
./venv/bin/python scripts/cleanup_rooms.py --force

# API (при запущенном сервере)
curl -s http://localhost:8000/api/rooms | python -m json.tool   # список
curl -X DELETE http://localhost:8000/api/rooms                   # очистка
```

#### Классификация комнат

| Тип | Признак | Действие | Причина появления |
| --- | --- | --- | --- |
| **Active** | `participants > 0` | Удалить | Незавершённая сессия, забытый тест |
| **Zombie** | `participants == 0` | Удалить | Сессия завершена, но `/end` не удаляет комнату |

> **Zombie-комнаты** — самый частый случай. Эндпоинт `/api/session/{id}/end` меняет статус в SQLite на `paused`, но **не удаляет** LiveKit комнату. Комната остаётся пустой до TTL (по умолчанию — `empty_timeout` в LiveKit, обычно 5 минут). Используйте `/api/session/{id}/kill` вместо `/end` для полной очистки.

#### Критерии прохождения

| Проверка         | Критерий                      |
|------------------|-------------------------------|
| Аудит выполнен   | Скрипт не упал                |
| Комнаты очищены  | 0 комнат после очистки        |
| Среда чистая     | Port 8000 свободен, 0 rooms   |

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
./venv/bin/./venv/bin/python scripts/run_server.py

# Терминал 2: Голосовой агент (рекомендуется через hanc.sh)
./scripts/hanc.sh start

# Терминал 3: E2E тест
node tests/e2e_voice_test.js
```

### 8.4 Критерии прохождения

Проверки разделены на **критические** (блокируют) и **информационные** (зависят от тестового окружения).

#### Критические (must pass — 11/11)

| #  | Проверка                | Описание                                 | Статус |
| -- | ----------------------- | ---------------------------------------- | ------ |
| 1  | Browser launch          | Chrome с fake audio запускается           | ✅     |
| 2  | Page load               | UI загружается без ошибок                 | ✅     |
| 3  | LiveKit connection      | Подключение к комнате успешно             | ✅     |
| 4  | Audio published         | Микрофон опубликован в комнату            | ✅     |
| 5  | Agent greeting          | Агент приветствует пользователя           | ✅     |
| 6  | Track subscribed        | Агент подписался на аудиотрек клиента     | ✅     |
| 7  | Agent received audio    | Агент получает аудиоданные от клиента     | ✅     |
| 8  | Pipeline: Redis reg     | Сессия зарегистрирована в Redis           | ✅     |
| 9  | Pipeline: PG reg        | Сессия зарегистрирована в PostgreSQL      | ✅     |
| 10 | Pipeline: Notifications | Уведомления отправлены при завершении     | ✅     |
| 11 | Pipeline: Finalize      | Сессия финализирована в БД                | ✅     |

#### Информационные (зависят от качества тестового аудио и длительности)

| #   | Проверка           | Описание                               | Статус |
| --- | ------------------ | -------------------------------------- | ------ |
| 12  | STT transcription  | Речь распознаётся в текст              | ⚠️ *   |
| 13  | Agent response     | Агент отвечает на распознанную речь    | ⚠️ *   |
| 14  | Conversation in UI | В UI больше 1 сообщения (диалог)       | ⚠️ *   |

#### Условные пайплайны (зависят от длительности сессии)

| #   | Проверка             | Условие срабатывания                    | Статус |
| --- | -------------------- | --------------------------------------- | ------ |
| 15  | Pipeline: KB enrichment  | >= 6 сообщений + отрасль определена | ⚠️ **  |
| 16  | Pipeline: Learning   | Завершение + отрасль + анкета           | ⚠️ **  |
| 17  | Pipeline: PG save    | Завершение + анкета заполнена           | ⚠️ **  |
| 18  | Pipeline: Research   | Клиент назвал URL сайта                 | ⚠️ *** |
| 19  | Pipeline: Review     | >= 16 сообщений + completion >= 0.5     | ⚠️ *** |

> \* **STT/Conversation:** С `test_speech_ru.wav` (реальная русская речь) STT транскрибирует речь
> и агент отвечает. Проверки #12-14 проходят при работающем Azure OpenAI Realtime.
>
> \*\* **Условные пайплайны (45с тест):** KB enrichment, Learning и PostgreSQL save
> срабатывают если за 45с теста накопится >= 6 пользовательских сообщений (речь зацикливается,
> поэтому обычно 4-8 транскриптов). Вероятность ~70%.
>
> \*\*\* **Research и Review:** Не срабатывают в 45с тесте — Research требует URL сайта
> в речи, Review требует >= 16 сообщений. Для полной проверки используйте LLM-симуляцию
> (Этап 7) или ручной тест >= 6 минут + скрипт `scripts/verify_pipelines.sh --full`.

### 8.4.1 Проверка качества VAD / отсутствия призрачных прерываний

После живого разговора (не Puppeteer) длительностью ≥60 секунд проверяйте логи на призрачные VAD-триггеры:

```bash
# 1. Подсчёт призрачных триггеров (VAD сработал, STT вернул пустоту)
GHOSTS=$(grep "USER SPEECH: ''" logs/agent.log | grep "final=False" | wc -l | tr -d ' ')
echo "Ghost VAD triggers: $GHOSTS"

# 2. Общее количество прерываний агента
INTERRUPTS=$(grep "AGENT STATE: speaking -> listening" logs/agent.log | wc -l | tr -d ' ')
echo "Agent interruptions: $INTERRUPTS"

# 3. Процент призрачных прерываний
if [ "$INTERRUPTS" -gt 0 ]; then
    PCT=$((GHOSTS * 100 / INTERRUPTS))
    echo "Ghost ratio: ${PCT}%"
    if [ "$PCT" -gt 30 ]; then
        echo "❌ FAIL: Ghost ratio > 30% — VAD threshold too low"
    else
        echo "✅ PASS: Ghost ratio acceptable"
    fi
else
    echo "✅ No interruptions recorded"
fi

# 4. Проверка обрезанных ответов (заканчиваются на запятую, предлог, незавершённое слово)
echo "--- Truncated responses (manual review): ---"
grep "CONVERSATION: role=assistant" logs/agent.log | grep -oP "content='.*'" | tail -5
```

| #   | Проверка             | Описание                                  | Критерий          |
| --- | -------------------- | ----------------------------------------- | ----------------- |
| 1   | Ghost triggers       | Пустые VAD-триггеры за сессию (≥60с)      | ≤ 1               |
| 2   | Ghost ratio          | Процент призрачных от общих прерываний    | < 30%             |
| 3   | Truncated responses  | Ответы агента, обрезанные на полуслове    | 0 (visual review) |
| 4   | Greeting complete    | Приветствие произнесено полностью         | Да                |

**Текущие параметры VAD (v4.0):**

| Параметр | Значение | Уровень | Изменения v4.0 |
| --- | --- | --- | --- |
| `threshold` | 0.9 | Server (TurnDetection) | — |
| `silence_duration_ms` | 4000 | Server (TurnDetection) | было 3000 |
| `prefix_padding_ms` | 500 | Server (TurnDetection) | — |
| `min_interruption_duration` | 2.0s | Client (AgentSession) | — |
| `min_interruption_words` | 4 | Client (AgentSession) | — |
| `min_endpointing_delay` | 2.5s | Client (AgentSession) | — |
| `false_interruption_timeout` | 3.0s | Client (AgentSession) | — |
| `resume_false_interruption` | True | Client (AgentSession) | — |
| `greeting_lock` | 3.0s | Custom (consultant.py) | было 1.0s |

> **ВАЖНО:** Параметр `eagerness` удалён — Azure Realtime API его не поддерживает (возвращает `Unknown parameter`). Это параметр только для OpenAI, не Azure.
>
> **Если ghost ratio > 30%:** повысьте `threshold` (до 0.95),
> `min_endpointing_delay` (до 3.0). Проверьте эхо от колонок — используйте наушники.
>
> **Если агент не реагирует на речь:** понизьте `threshold` (до 0.8), уменьшите `silence_duration_ms` (до 2000).

### 8.5 Результаты тестирования

| Дата       | Критические  | Информационные   | Пайплайны        | Итог |
| ---------- | ------------ | ---------------- | ---------------- | ---- |
| 2026-02-08 | 7/7 ✅       | 0/3 (fake audio) | N/A              | PASS |
| 2026-02-10 | 7/7 ✅       | 1/3 (fake audio) | N/A              | PASS |
| 2026-02-10 | 11/11 ✅     | TBD              | 4/4 required     | TBD  |

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

### 8.7 Post-E2E Pipeline Verification

> **Цель:** Верифицировать, что ВСЕ 7 подключённых пайплайнов реально сработали.
>
> Два подхода: **(A)** встроенная проверка в E2E тесте (автоматическая, ~45с),
> **(B)** standalone скрипт после LLM-симуляции или ручного теста (полная, >= 6 минут).

#### Матрица покрытия пайплайнов

| # | Пайплайн | Лог-маркер | E2E 45с | LLM-сим / ручной |
|---|----------|------------|---------|-------------------|
| 1 | Redis registration | `registered in Redis` | ✅ always | ✅ |
| 2 | PostgreSQL registration | `registered in PostgreSQL` | ✅ always | ✅ |
| 3 | KB + CountryDetector | `KB context injected` | ⚠️ ~70% | ✅ |
| 4 | ResearchEngine | `research_launched` | ❌ no URL | ✅ if URL mentioned |
| 5 | Review Phase | `review_phase_started` | ❌ < 16 msgs | ✅ if >= 16 msgs |
| 6 | NotificationManager | `notification_sent` | ✅ always | ✅ |
| 7a | record_learning | `learning_recorded` | ⚠️ ~70% | ✅ |
| 7b | PostgreSQL save | `postgres_saved` | ⚠️ ~70% | ✅ |
| 7c | Redis cleanup | `session_finalized_in_db` | ✅ always | ✅ |

> **Почему ~70%:** KB, Learning и PostgreSQL save требуют, чтобы extraction успела сработать
> (каждые 6 user-сообщений). За 45с с зацикленным WAV Chrome генерирует 4-8 STT-транскриптов.
> Если >= 6 — extraction запускается и пайплайны срабатывают.

#### Подход A: Встроенная проверка в E2E тесте (автоматическая)

E2E тест (`tests/e2e_voice_test.js`) после шагов 1-8 автоматически:

1. Закрывает браузер (disconnect → `_finalize_and_save()` запускается)
2. Ждёт 20с для завершения финализации (DeepSeek extraction + DB saves)
3. Проверяет лог-маркеры всех пайплайнов в `/tmp/agent_entrypoint.log`
4. Проверяет Redis ключи и PostgreSQL строки (если CLI доступны)
5. Выводит отчёт: обязательные пайплайны (must pass) и условные (informational)

**Обязательные проверки** (fail = тест не проходит):

- Redis registration, PostgreSQL registration, Notifications, Finalize

**Условные проверки** (informational):

- KB enrichment, Learning, PostgreSQL save, Research, Review Phase

```bash
# Запуск E2E теста с pipeline verification
node tests/e2e_voice_test.js
```

#### Подход B: Standalone скрипт (после LLM-симуляции или ручного теста)

Скрипт `scripts/verify_pipelines.sh` проверяет все пайплайны по лог-маркерам
и опционально запрашивает Redis/PostgreSQL для live-проверки.

```bash
# Базовая проверка (только логи)
./scripts/verify_pipelines.sh

# Полная проверка (логи + Redis + PostgreSQL queries)
./scripts/verify_pipelines.sh --full

# С кастомным логом
./scripts/verify_pipelines.sh /path/to/agent.log
```

**Рекомендуемый сценарий полной проверки всех 7 пайплайнов:**

```bash
# 1. Запустить LLM-симуляцию (Этап 7) — генерирует >= 20 сообщений
./venv/bin/./venv/bin/python scripts/run_test.py auto_service --quiet

# 2. Или ручной тест через браузер (>= 6 минут, упомянуть URL сайта)
# Открыть http://localhost:8000, провести полную консультацию

# 3. Проверить все пайплайны
./scripts/verify_pipelines.sh --full
```

**Ожидаемый результат полной проверки:**

```text
============================================================
  Pipeline Verification (7 pipelines)
============================================================
--- Log Markers ---
  OK  Redis registration (1 occurrences)
  OK  PostgreSQL registration (1 occurrences)
  OK  KB enrichment (1 occurrences)
  OK  Research (1 occurrences)
  OK  Review Phase (1 occurrences)
  OK  Notifications (1 occurrences)
  OK  Learning recorded (1 occurrences)
  OK  PostgreSQL save (1 occurrences)
  OK  Redis cleanup (finalize) (1 occurrences)
--- Summary ---
  Passed: 9  Failed: 0  Conditional: 0
============================================================
  RESULT: ALL REQUIRED PIPELINES FIRED
============================================================
```

---

## Этап 9: Docker-деплой и SSL

Проверка контейнеризированного деплоя: сборка образа, запуск 6 сервисов, nginx reverse proxy, SSL-сертификат Let's Encrypt.

### 9.1 Требования

- Docker Engine 24+
- Docker Compose v2
- Домен с A-записью на IP сервера
- Порты 80 и 443 открыты на сервере
- `.env` настроен: `DOMAIN`, `CERTBOT_EMAIL`, все API-ключи

### 9.2 Сборка образа

```bash
docker compose build
```

**Критерий:** `Successfully built`, 0 errors. Образ `hanc-ai` собран на базе `python:3.14-slim`.

### 9.3 Первичное получение SSL-сертификата

```bash
./scripts/init-letsencrypt.sh
```

**Критерий:** скрипт завершился с `SUCCESS`, сертификат в `data/certbot/conf/live/$DOMAIN/`.

### 9.4 Запуск контейнеров

```bash
docker compose up -d
docker compose ps
```

**Критерий:** все 6 сервисов в статусе `Up` / `running`:

| Сервис | Контейнер | Ожидаемый статус |
|--------|-----------|------------------|
| nginx | hanc_nginx | Up (ports 80, 443) |
| certbot | hanc_certbot | Up |
| web | hanc_web | Up (expose 8000) |
| agent | hanc_agent | Up |
| redis | hanc_redis | Up (healthy) |
| postgres | hanc_postgres | Up (healthy) |

### 9.5 Healthcheck сервисов

```bash
# Web (FastAPI)
curl -s http://localhost:8000/api/sessions
# Ожидание: JSON с sessions (внутри Docker-сети)

# Agent
docker compose logs agent --tail=5
# Ожидание: "Агент готов к подключению клиентов"

# Redis
docker compose exec redis redis-cli ping
# Ожидание: PONG

# PostgreSQL
docker compose exec postgres pg_isready -U ${POSTGRES_USER:-interviewer_user}
# Ожидание: accepting connections

# Nginx
curl -I https://$DOMAIN
# Ожидание: 200 OK + Strict-Transport-Security header

# Certbot
docker compose logs certbot --tail=5
# Ожидание: "no renewals were attempted" или "renewed successfully"
```

### 9.6 SSL и HTTPS

```bash
# HTTP → HTTPS редирект
curl -I http://$DOMAIN
# Ожидание: 301 Moved Permanently → https://$DOMAIN

# HTTPS работает
curl -I https://$DOMAIN
# Ожидание: 200 OK

# Проверить security headers
curl -sI https://$DOMAIN | grep -E "Strict-Transport|X-Frame|X-Content-Type"
# Ожидание:
#   Strict-Transport-Security: max-age=63072000; includeSubDomains
#   X-Frame-Options: DENY
#   X-Content-Type-Options: nosniff

# Проверить сертификат
openssl s_client -connect $DOMAIN:443 -servername $DOMAIN < /dev/null 2>/dev/null | \
    openssl x509 -noout -dates -issuer
# Ожидание: issuer = Let's Encrypt, notAfter > сегодня + 60 дней
```

### 9.7 API через nginx

```bash
curl -s https://$DOMAIN/api/sessions | jq .
# Ожидание: JSON ответ, не 502 Bad Gateway / 504 Gateway Timeout
```

### 9.8 Микрофон (getUserMedia)

1. Открыть `https://$DOMAIN` в браузере
2. Нажать "Начать консультацию"
3. **Критерий:** браузер запрашивает разрешение на микрофон (НЕ ошибка `getUserMedia is not available`)

> **Напоминание:** `getUserMedia()` работает ТОЛЬКО через HTTPS или localhost. Это главная причина, почему нужен nginx + SSL.

### 9.9 Загрузка документов через nginx

```bash
# Создать тестовый файл
echo "Test document" > /tmp/test.txt

# Загрузить через nginx
curl -X POST https://$DOMAIN/api/session/{session_id}/documents/upload \
    -F "files=@/tmp/test.txt"
# Ожидание: 200 OK, файл обработан
# НЕ 413 Request Entity Too Large (nginx client_max_body_size = 50m)
```

### 9.10 Логи (отсутствие ошибок)

```bash
docker compose logs web --tail=20       # нет tracebacks
docker compose logs agent --tail=20     # нет ModuleNotFoundError
docker compose logs nginx --tail=20     # нет 502/504 ошибок
```

**Критерий:** все логи чистые, нет Python tracebacks или nginx upstream errors.

### 9.11 Перезапуск и устойчивость

```bash
docker compose restart web
sleep 5
curl -s https://$DOMAIN/api/sessions | jq .
# Ожидание: сервис восстановился, ответ 200
```

### 9.12 Troubleshooting Docker

| Проблема | Причина | Решение |
|----------|---------|---------|
| `ModuleNotFoundError: src.output` | `.gitignore` игнорировал `src/output/` | Исправить `.gitignore`: `output/` → `/output/` |
| `ModuleNotFoundError: uvicorn` | Не указан в `requirements.txt` | Добавить `fastapi` и `uvicorn` в requirements.txt |
| nginx: `502 Bad Gateway` | web контейнер не запустился | `docker compose logs web` — смотреть traceback |
| certbot: `challenge failed` | DNS A-запись не указывает на сервер | Проверить `dig $DOMAIN` → IP сервера |
| `getUserMedia undefined` | Сайт открыт по HTTP | Настроить HTTPS (nginx + certbot) |
| `413 Request Entity Too Large` | `client_max_body_size` < размера файла | Увеличить в `nginx.conf.template` |
| SSL certificate expired | Certbot не обновил | `docker compose exec certbot certbot renew --force-renewal` |
| nginx не стартует | Нет сертификатов | Запустить `./scripts/init-letsencrypt.sh` |
| Agent падает в restart loop | Ошибка в коде или env | `docker compose logs agent --tail=50` |

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
| KB валидация: non-numeric entry_point | ~~`./venv/bin/python scripts/fix_entry_points.py`~~ (скрипт удалён, профили уже исправлены) |
| KB валидация: enum не English | ~~`./venv/bin/python scripts/fix_enums.py`~~ (скрипт удалён, профили уже исправлены) |
| KB валидация: payback_months=0 или >36 | ~~`./venv/bin/python scripts/fix_l10_pricing.py`~~ (скрипт удалён, профили уже исправлены) |
| KB валидация: отсутствуют секции | ~~`./venv/bin/python scripts/fix_incomplete_profiles.py --provider=azure`~~ (скрипт удалён, профили уже исправлены) |
| KB: "Rp 50.000" парсится как 50 | Индонезийская точка = разделитель тысяч, исправьте вручную на 50000 |
| PDF не парсится | `pip install pymupdf` (библиотека fitz) |
| DOCX не парсится | `pip install python-docx` |
| XLSX не парсится | `pip install openpyxl` |
| Нет тестовых документов в input/ | ~~`./venv/bin/python scripts/generate_test_documents.py`~~ (скрипт удалён, документы уже сгенерированы) |
| DocumentLoader: 0 documents | Проверьте расширения файлов (.pdf, .docx, .md, .xlsx, .txt) |
| `ServerVadOptions` not found | `livekit-plugins-openai` >= 1.2.18 удалил `ServerVadOptions`. Используйте `TurnDetection(type="server_vad", ...)` из `livekit.plugins.openai.realtime.realtime_model` |
| E2E: STT не транскрибирует | Puppeteer fake audio = синтетический тон. Замените `tests/fixtures/test_speech_ru.wav` на WAV с настоящей речью (см. Этап 8.2) |
| E2E: Agent не отвечает | Проверьте `/tmp/agent_entrypoint.log`. Если `STEP 1/5 FAILED` — ошибка SDK. Если `USER STATE: away` — нет аудио |
| `RuntimeError: aclose(): asynchronous generator is already running` | Python 3.14 ужесточил lifecycle async generators. Monkey-patch в `consultant.py` перехватывает эту ошибку в LiveKit SDK `Tee.aclose()` |
| Анкета не заполняется в UI | Race condition: `update_session(stale)` затирает `update_anketa()`. Исправлено в v4.0 — перечитывание сессии ПОСЛЕ записи анкеты |
| Агент замолкает на полуслове | 303 RuntimeError в `Tee.aclose()` обрывают аудио-поток. Исправлено monkey-patch в v4.0 |
| Ложное прерывание после первой реплики | Эхо 67ms от динамика → Azure VAD. Исправлено: greeting lock 3.0s, silence_duration_ms 4000 |
| KB не подключена к голосовому агенту | `get_enriched_system_prompt()` не вызывалась из `entrypoint()`. Исправлено в v4.0: KB инжектируется через `update_instructions()` после первой экстракции |
| Агент утверждает наличие CRM-интеграции | Галлюцинация из-за мягкого промпта. Исправлено: блок "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО" в `consultant.yaml` |

---

## Автоматизация (CI/CD) *(Planned)*

> **Статус:** CI/CD и pre-commit hooks запланированы, но ещё не настроены. Ниже — рекомендуемая конфигурация.

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
      - run: ./venv/bin/python -m pytest --cov=src --cov-fail-under=50
```

### Pre-commit hook

```bash
# .git/hooks/pre-commit
#!/bin/sh
./venv/bin/python -m pytest --tb=short -q
```

---

## Ручное тестирование v5.0 — чеклист для пользователя

> **Подготовка:** `make start` (или `./scripts/hanc.sh start`), открыть `http://localhost:8000` в Chrome.
> После каждого этапа — проверить DevTools Console на ошибки.
> Обозначения: `[ ]` — не проверено, `[x]` — пройдено, `[!]` — баг.

### 0. Перед началом

```
[ ] Сервер запущен: `make status` → server running, agent running
[ ] В браузере открыт http://localhost:8000
[ ] DevTools Console открыта (F12 → Console), ошибок нет
[ ] localStorage очищен: DevTools → Application → Local Storage → Clear All
```

### 1. Landing Page (первый визит)

```
[ ] Открыть http://localhost:8000 → показывается Landing Page (не Dashboard)
[ ] Hero: заголовок «Голосовой AI, который слушает бизнес» с gradient-текстом
[ ] 3 карточки «Как это работает» (Запустите сессию / Говорите / Заберите результат)
[ ] 2 карточки режимов: AI-Консультант (фиолетовый акцент) и AI-Интервьюер (зелёный)
[ ] 4 карточки «Что под капотом» (Анкета, Аналитика, 40+ отраслей, Экспорт)
[ ] Scroll-анимации: секции fade-in при скролле вниз
[ ] CTA кнопка «Начать бесплатно» → переход на Dashboard
[ ] После клика CTA: localStorage.hasVisited === '1'
[ ] Перезагрузка страницы → сразу Dashboard (не Landing)
[ ] Ссылка «О продукте» в header → возврат на Landing
```

### 2. Settings Panel (Dashboard)

```
[ ] На Dashboard видна панель <details> «Настройки консультации» (раскрыта по умолчанию)
[ ] Клик на заголовок → панель сворачивается/раскрывается
[ ] 3 segmented controls: Тип (Консультация/Интервью), Голос (Жен/Муж/Нейтр), Ответы (Кратко/Норм/Подробно)
[ ] 2 слайдера: Скорость речи (0.75x—2.0x), Задержка тишины (0.5с—4.0с)
[ ] Keyboard: Tab между контролами, стрелки между radio-кнопками
[ ] Изменить настройки → перезагрузить страницу → настройки восстановлены из localStorage
```

### 3. Создание сессии (Консультация)

```
[ ] Настройки: Тип=Консультация, Голос=Нейтральный, Ответы=Нормально, Скорость=1.0x, Тишина=2.0с
[ ] Нажать «+ Новая консультация»
[ ] Loading spinner виден при подключении к комнате
[ ] Spinner исчезает после подключения
[ ] Статус «Подключен» (зелёная точка) в header
[ ] Progress bar: 0% заполнено
[ ] Агент произносит приветствие (первое голосовое сообщение)
[ ] Сообщение AI появляется в чате с timestamp (формат HH:MM)
[ ] Ваш ответ голосом → сообщение «Вы» появляется в чате с timestamp
[ ] ARIA: mic-кнопка имеет aria-label="Микрофон" (DevTools → Elements)
[ ] ARIA: pause-кнопка имеет aria-label="Пауза"
[ ] ARIA: progress-bar имеет role="progressbar"
```

### 4. Пауза и resume

```
[ ] Нажать «Пауза» → overlay «На паузе» (полупрозрачный, opacity ~0.5)
[ ] Диалог ЧИТАЕТСЯ через overlay (не полностью закрыт)
[ ] Снова нажать → пауза снята, overlay убран
[ ] История чата НЕ пропала после resume
```

### 5. Смена настроек mid-session (КЛЮЧЕВОЙ ТЕСТ)

```
[ ] Во время активной сессии: нажать «← Назад» → Dashboard
[ ] Изменить скорость речи на 1.5x
[ ] Изменить голос на «Мужской»
[ ] Изменить Ответы на «Кратко»
[ ] Изменить задержку тишины на 3.0с
[ ] Нажать на сессию в таблице → возврат в сессию
[ ] DevTools Network: PUT /api/session/{id}/voice-config → 200 (body содержит все 5 полей)
[ ] DevTools Network: GET /api/session/{id}/reconnect → 200
[ ] Агент теперь говорит МУЖСКИМ голосом (не нейтральным)
[ ] Агент говорит БЫСТРЕЕ (скорость 1.5x)
[ ] Агент отвечает КРАТКО (1-2 предложения + вопрос, без длинных вступлений)
[ ] Тишина до ответа ~3 секунды (не 2)
```

### 6. Второй цикл смены настроек

```
[ ] Снова выйти на Dashboard
[ ] Изменить голос на «Женский»
[ ] Изменить Ответы на «Подробно»
[ ] Вернуться в сессию
[ ] Агент говорит ЖЕНСКИМ голосом
[ ] Агент даёт РАЗВЁРНУТЫЕ ответы с примерами
```

### 7. Анкета (Консультация)

```
[ ] После 3-4 реплик: анкета начинает заполняться (toast «Анкета заполняется автоматически»)
[ ] Progress bar обновляется (> 0%)
[ ] Поля анкеты видны в правой панели: Контакты, О бизнесе, Голосовой агент, Дополнительно
[ ] Лейблы полей читаемые (font-size 0.875rem, не мелкие)
[ ] Можно редактировать поле вручную → значение сохраняется при следующем polling (не перезаписывается)
```

### 8. Завершение сессии (inline confirm)

```
[ ] Нажать «Завершить» → появляется модальное окно (НЕ нативный confirm())
[ ] Модалка в тёмной теме, кнопки «Да, завершить» и «Отмена»
[ ] «Отмена» → модалка закрывается, сессия продолжается
[ ] «Да, завершить» → сессия завершена, переход на Dashboard
[ ] Сессия в таблице: статус «на паузе» или «завершена»
```

### 9. Review Screen + Export

```
[ ] Клик на сессию в таблице → Interview screen
[ ] Нажать «Подтвердить анкету» → переход на Review screen
[ ] Review: анкета слева, диалог справа
[ ] Все секции анкеты отображаются (Контакты, О бизнесе, Агент, Дополнительно)
[ ] Кнопки экспорта видны: [MD] [PDF] (button group, не dropdown)
[ ] Клик [MD] → скачивается файл .md с данными анкеты
[ ] Клик [PDF] → открывается новая вкладка со стилизованным HTML для печати
[ ] «Продолжить сессию» → возврат в interview screen
[ ] «Копировать ссылку» → ссылка в буфере обмена
```

### 10. Создание сессии (Интервью)

```
[ ] На Dashboard: переключить Тип → «Интервью»
[ ] Нажать «+ Новая консультация»
[ ] Агент представляется как ИНТЕРВЬЮЕР (спрашивает, не советует)
[ ] Агент задаёт открытые вопросы: «Расскажите подробнее...», «Можете привести пример?»
[ ] Агент НЕ даёт советов и рекомендаций
[ ] Анкета: отображаются Q&A пары (Вопросы и ответы), а НЕ бизнес-поля
[ ] Анкета: секции «Респондент», «Вопросы и ответы», «Выявленные темы», «Ключевые цитаты»
[ ] Progress bar: считается по Q&A coverage (не по полям)
```

### 11. Review Screen (Интервью)

```
[ ] Завершить интервью → Review screen
[ ] Review: Q&A пары с тегами тем
[ ] Detected topics: теги-бейджи
[ ] Key quotes: цитаты с фиолетовой полоской слева
[ ] AI-анализ: summary + insights (если сессия длинная)
[ ] Экспорт [MD] → markdown содержит Q&A пары
```

### 12. Responsive (мобильная версия)

```
[ ] DevTools → Toggle Device Toolbar → iPhone SE (375px)
[ ] Landing: карточки стопкой (1 колонка), текст читаемый
[ ] Dashboard: Settings panel стопкой (flex-direction: column)
[ ] Interview: диалог на полную ширину, анкета под ним
[ ] Toast уведомления не обрезаются
```

### 13. Множественные сессии

```
[ ] Создать 3 сессии (2 консультации, 1 интервью)
[ ] Dashboard: таблица показывает все 3
[ ] Фильтры: «Активные» → только активные, «На паузе» → только paused
[ ] Выбрать 2 чекбоксом → кнопка «Удалить выбранные» появляется
[ ] Удалить → сессии пропали из таблицы
```

### 14. DevTools — финальная проверка

```
[ ] Console: 0 ошибок (warnings допустимы)
[ ] Network: нет failed requests (красных)
[ ] Application → Local Storage: hanc_voice_settings и hasVisited сохранены
[ ] Логи агента: cat /tmp/agent_entrypoint.log | grep "voice_config updated" — есть записи mid-session update
[ ] Логи агента: grep "verbosity updated" /tmp/agent_entrypoint.log — есть записи (если менялась словоохотливость)
```

### Итог

| Секция | Пунктов | Пройдено |
|--------|---------|----------|
| 0. Подготовка | 4 | /4 |
| 1. Landing Page | 10 | /10 |
| 2. Settings Panel | 6 | /6 |
| 3. Создание сессии | 13 | /13 |
| 4. Пауза и resume | 4 | /4 |
| 5. Смена настроек mid-session | 12 | /12 |
| 6. Второй цикл смены | 5 | /5 |
| 7. Анкета | 5 | /5 |
| 8. Завершение (inline confirm) | 5 | /5 |
| 9. Review + Export | 9 | /9 |
| 10. Интервью | 8 | /8 |
| 11. Review (Интервью) | 6 | /6 |
| 12. Responsive | 4 | /4 |
| 13. Множественные сессии | 5 | /5 |
| 14. DevTools | 5 | /5 |
| **ИТОГО** | **101** | **/101** |
