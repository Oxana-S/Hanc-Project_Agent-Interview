# Workflow Агентов

Документ описывает workflow всех агентов и режимов системы.

## Содержание

1. [Голосовой агент — VoiceConsultant](#1-голосовой-агент--voiceconsultant)
2. [Текстовый CLI — ConsultantInterviewer](#2-текстовый-cli--consultantinterviewer)
3. [Maximum Interview — MaximumInterviewer](#3-maximum-interview--maximuminterviewer)
4. [agent_client_simulator — Агент Тестирования](#4-agent_client_simulator--агент-тестирования)
5. [agent_document_reviewer — Агент Ревью Документов](#5-agent_document_reviewer--агент-ревью-документов)
6. [Интегрированный Pipeline: Test → Review](#6-интегрированный-pipeline-test--review)

---

## 1. Голосовой агент — VoiceConsultant

### 1.1 Назначение

Голосовая консультация через браузер: клиент говорит, AI-агент отвечает голосом, анкета заполняется в реальном времени на экране.

### 1.2 Компоненты

```text
src/voice/
├── consultant.py           # VoiceConsultationSession, entrypoint, finalize
└── livekit_client.py       # LiveKitClient (генерация токенов)

src/web/
└── server.py               # FastAPI (14 эндпоинтов)

public/
└── index.html              # Фронтенд + LiveKit JS SDK
```

### 1.3 Workflow схема

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        VOICE CONSULTANT                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  КЛИЕНТ (браузер)                    СЕРВЕР + АГЕНТ                 │
│                                                                      │
│  1. Открывает /                      FastAPI отдаёт index.html      │
│                                                                      │
│  2. Нажимает "Начать"                                               │
│     │                                                                │
│     ├─► GET /api/agent/health (проверка агента)                     │
│     └─► POST /api/session/create                                    │
│              │                                                       │
│              ├─► SessionManager.create_session() → SQLite           │
│              ├─► LiveKitClient.create_token()                       │
│              └─► LiveKitAPI.create_room(agent_dispatch)             │
│                       │                                              │
│                       └─► LiveKit запускает Voice Agent             │
│                                                                      │
│  3. WebRTC аудио ◄──────────► LiveKit ◄──────► Azure Realtime      │
│     Клиент говорит               │              (STT → LLM → TTS)  │
│     Агент отвечает               │                                  │
│                                  │                                  │
│  4. При каждом сообщении:        │                                  │
│     │                            ▼                                  │
│     │                   consultation.add_message()                  │
│     │                   _sync_to_db() → SQLite                     │
│     │                   Каждые 6 сообщений:                        │
│     │                     _extract_and_update_anketa()              │
│     │                       ├─► AnketaExtractor.extract()           │
│     │                       └─► SessionManager.update_anketa()      │
│     │                                                                │
│     └─► GET /api/session/{id}/anketa (polling ~2 сек)              │
│              └─► Анкета обновляется на экране                       │
│                                                                      │
│  5. Фаза проверки анкеты:                                           │
│     • Агент предлагает голосовую или визуальную проверку            │
│     • Голосовая: зачитывает разделы один за другим                  │
│     • Визуальная: клиент редактирует на экране                     │
│                                                                      │
│  6. Подтверждение:                                                  │
│     └─► POST /api/session/{id}/confirm                             │
│              ├─► status → "confirmed"                               │
│              └─► NotificationManager (email + webhook)              │
│                                                                      │
│  7. Отключение клиента:                                             │
│     └─► _finalize_and_save()                                       │
│              ├─► AnketaExtractor.extract() (финальное)              │
│              ├─► OutputManager.save_anketa()                        │
│              ├─► OutputManager.save_dialogue()                      │
│              └─► SessionManager.update_session()                    │
│                                                                      │
│  РЕЗУЛЬТАТ: output/{date}/{company}_v{N}/                           │
│             ├── anketa.md                                            │
│             ├── anketa.json                                          │
│             └── dialogue.md                                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.4 Инициализация агента (5 шагов)

```text
entrypoint(ctx: JobContext)
    │
    ├─► STEP 1/5: _create_realtime_model()
    │       Azure OpenAI WSS endpoint, deployment, api_key
    │       → lk_openai.realtime.RealtimeModel.with_azure()
    │
    ├─► STEP 2/5: VoiceAgent(instructions=get_system_prompt())
    │       Системный промпт с 5 фазами консультации
    │
    ├─► STEP 3/5: ctx.connect(auto_subscribe=AUDIO_ONLY)
    │       Подключение к LiveKit комнате
    │
    ├─► STEP 4/5: AgentSession + _register_event_handlers()
    │       ├─► on("conversation_item_added")
    │       │       └─► запись диалога, sync DB, periodic extraction
    │       └─► on("close")
    │               └─► _finalize_and_save()
    │
    └─► STEP 5/5: session.start(agent=agent, room=ctx.room, model=model)
            Агент готов к разговору
```

### 1.5 Периодическое извлечение анкеты

Каждые 6 сообщений агент запускает `_extract_and_update_anketa()`:

1. `AnketaExtractor.extract(dialogue_history)` — DeepSeek LLM
2. `SessionManager.update_anketa(session_id, data, md)` — SQLite
3. Обновление `company_name`, `contact_name` если найдены
4. Фронтенд подхватывает изменения через polling

### 1.6 Статусы сессии

```text
active → paused → active → reviewing → confirmed
                                     → declined
```

| Статус | Описание |
|--------|----------|
| active | Разговор идёт |
| paused | Клиент отключился, может вернуться по ссылке |
| reviewing | Анкета на проверке |
| confirmed | Анкета подтверждена |
| declined | Клиент отказался |

### 1.7 Запуск

```bash
# Процесс 1: Web сервер
./venv/bin/python scripts/run_server.py

# Процесс 2: Голосовой агент (через hanc.sh — рекомендуется)
./scripts/hanc.sh start

# Управление агентом
./scripts/hanc.sh status    # Статус процессов
./scripts/hanc.sh stop      # Остановить
./scripts/hanc.sh restart   # Перезапустить
./scripts/hanc.sh logs      # Логи
./scripts/hanc.sh kill-all  # Аварийное завершение
```

При старте сервера автоматически очищаются старые LiveKit-комнаты. Агент защищён от дублирования через PID-файл (`.agent.pid`).

---

## 2. Текстовый CLI — ConsultantInterviewer

### 2.1 Назначение

Консультация через текстовый интерфейс в терминале. Не требует LiveKit и Azure.

### 2.2 Компоненты

```text
src/consultant/
├── interviewer.py           # ConsultantInterviewer (основной класс)
├── phases.py                # ConsultantPhase enum
└── models.py                # BusinessAnalysis, ProposedSolution
```

### 2.3 Workflow схема

```text
┌──────────────────────────────────────────────────────────────────────┐
│                     CONSULTANT INTERVIEWER                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ИНИЦИАЛИЗАЦИЯ                                              │    │
│  │  ├─► Загрузка IndustryKnowledgeManager (40 отраслей)       │    │
│  │  ├─► Загрузка документов из input/ → DocumentContext      │    │
│  │  ├─► EnrichedContextBuilder(KB + Documents + Learnings)   │    │
│  │  └─► ConsultationConfig (профиль: fast/standard/thorough)  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           │                                                          │
│           ▼                                                          │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌──────────┐  │
│  │ DISCOVERY  │──▶│  ANALYSIS  │──▶│  PROPOSAL  │──▶│REFINEMENT│  │
│  │            │   │            │   │            │   │          │  │
│  │ Знакомство │   │ Анализ     │   │ Предложение│   │Финализац.│  │
│  │ 5-15 ходов │   │ ≤5 ходов   │   │ ≤5 ходов   │   │ ≤10 ходов│  │
│  └────────────┘   └────────────┘   └────────────┘   └──────────┘  │
│                                                          │          │
│  Каждая фаза:                                            ▼          │
│  • DeepSeek LLM для генерации ответов             ┌───────────┐   │
│  • Rich CLI для отображения                        │ EXTRACTION│   │
│  • CollectedInfo для сбора данных                  │           │   │
│  • IndustryProfile для обогащения контекста        │ Anketa    │   │
│                                                     │ Extractor │   │
│                                                     └─────┬─────┘   │
│                                                           │         │
│                                                           ▼         │
│                                                     ┌───────────┐   │
│                                                     │  OUTPUT   │   │
│                                                     │  MANAGER  │   │
│                                                     └───────────┘   │
│                                                                      │
│  РЕЗУЛЬТАТ: output/{date}/{company}_v{N}/                           │
│             ├── anketa.md                                            │
│             ├── anketa.json                                          │
│             └── dialogue.md                                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.4 Фазы консультации

| Фаза | Цель | Лимит ходов |
|------|------|-------------|
| DISCOVERY | Узнать о компании, отрасли, услугах | 5-15 |
| ANALYSIS | Выявить боли, сформировать BusinessAnalysis | до 5 |
| PROPOSAL | Предложить ProposedSolution с функциями | до 5 |
| REFINEMENT | Уточнить детали, извлечь FinalAnketa | до 10 |

### 2.5 ConsultationConfig

Три профиля скорости:

| Параметр | FAST | STANDARD | THOROUGH |
|----------|------|----------|----------|
| discovery_min_turns | 3 | 5 | 8 |
| discovery_max_turns | 8 | 15 | 20 |
| total_max_turns | 25 | 50 | 80 |
| temperature | 0.5 | 0.7 | 0.8 |

### 2.6 Обогащение контекста (EnrichedContextBuilder)

Три источника контекста объединяются для каждой фазы консультации:

1. **IndustryKnowledgeManager** (40 отраслей, 968 профилей): определяет отрасль из диалога, подгружает pain_points, recommended_functions, typical_integrations, competitors, pricing_context, sales_scripts
2. **DocumentContext**: если в `input/` есть документы — парсит PDF/DOCX/XLSX/MD/TXT и извлекает services, contacts, key_facts, FAQ
3. **Learnings**: накопленный опыт из предыдущих консультаций (до 5 последних)

```text
EnrichedContextBuilder.build_for_phase(phase, dialogue_history)
    │
    ├─► IndustryProfile (из KBContextBuilder)
    │       pain_points, functions, integrations, competitors
    │
    ├─► DocumentContext.to_prompt_context()
    │       key_facts, services, contacts, questions_to_clarify
    │
    ├─► Learnings (из profile.learnings)
    │       + успешные стратегии, • инсайты
    │
    └─► → Единая строка контекста для промпта LLM
```

Контекст передаётся во все 4 фазы и в AnketaExtractor:

```text
ConsultantInterviewer(document_context=doc_ctx)
    ├─► DISCOVERY:   _get_kb_context() → EnrichedContextBuilder
    ├─► ANALYSIS:    _get_kb_context() → EnrichedContextBuilder
    ├─► PROPOSAL:    _get_kb_context() → EnrichedContextBuilder
    ├─► REFINEMENT:  _get_kb_context() → EnrichedContextBuilder
    └─► AnketaExtractor.extract(document_context=doc_ctx)
```

### 2.7 Запуск

```bash
./venv/bin/python scripts/consultant_demo.py
```

---

## 3. Maximum Interview — MaximumInterviewer

### 3.1 Назначение

Альтернативный текстовый режим консультации с 3-фазной структурой интервью. Использует Redis для хранения активных сессий и PostgreSQL для завершённых анкет. Также доступен MOCK-режим без API (для тестирования UI).

### 3.2 Компоненты

```text
src/interview/
├── maximum.py              # MaximumInterviewer (746 строк) — основной класс
├── phases.py               # InterviewPhase enum, CollectedInfo (21 ANKETA_FIELDS)
└── questions/
    ├── interaction.py      # Банк вопросов для клиентов
    └── management.py       # Банк вопросов для сотрудников

src/llm/
└── anketa_generator.py     # LLMAnketaGenerator → FinalAnketa dataclass

src/cli/
├── interface.py            # Rich dashboard (визуальный интерфейс)
└── maximum.py              # CLI-обёртка для Maximum Interview

src/storage/
├── redis.py                # InterviewContext (активные сессии)
└── postgres.py             # CompletedAnketa (завершённые анкеты)

scripts/
└── demo.py                 # Точка входа
```

### 3.3 Workflow схема

```text
┌──────────────────────────────────────────────────────────────────────┐
│                     MAXIMUM INTERVIEWER                               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ИНИЦИАЛИЗАЦИЯ                                              │    │
│  │  ├─► Загрузка банков вопросов (interaction / management)    │    │
│  │  ├─► Подключение к Redis + PostgreSQL                      │    │
│  │  └─► Выбор режима: MAXIMUM или MOCK                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           │                                                          │
│           ▼                                                          │
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────────┐  │
│  │   DISCOVERY    │──▶│   STRUCTURED   │──▶│     SYNTHESIS      │  │
│  │                │   │                │   │                    │  │
│  │ Свободный      │   │ Целевой сбор   │   │ LLM-генерация     │  │
│  │ диалог         │   │ данных         │   │ анкеты            │  │
│  │ 5-15 ходов     │   │ до 5 ходов     │   │ (автоматически)   │  │
│  └────────────────┘   └────────────────┘   └────────┬───────────┘  │
│                                                       │              │
│  Каждая фаза:                                         ▼              │
│  • DeepSeek LLM для генерации ответов          ┌───────────────┐   │
│  • CollectedInfo (21 ANKETA_FIELDS)             │LLMAnketa      │   │
│  • Rich CLI dashboard                           │Generator      │   │
│                                                  │→ FinalAnketa  │   │
│                                                  └───────┬───────┘   │
│                                                          │           │
│                                                          ▼           │
│                                                  ┌───────────────┐   │
│  Хранение:                                       │   STORAGE     │   │
│  • Redis — InterviewContext (активные сессии)     │ Redis + PG    │   │
│  • PostgreSQL — CompletedAnketa (завершённые)    └───────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.4 Фазы интервью

| Фаза | Цель | Лимит ходов |
|------|------|-------------|
| DISCOVERY | Свободный диалог, выявление потребностей | 5-15 |
| STRUCTURED | Целевой сбор недостающих данных по ANKETA_FIELDS | до 5 |
| SYNTHESIS | Автоматическая генерация FinalAnketa через LLM | — |

### 3.5 Режимы запуска

| Режим | Описание |
|-------|----------|
| MAXIMUM | Полноценный режим с DeepSeek AI, Redis и PostgreSQL |
| MOCK | Симуляция без API-вызовов (для тестирования UI) |

### 3.6 Запуск

```bash
# Запуск инфраструктуры
docker compose -f config/docker-compose.yml up -d

# Запуск интервью
./venv/bin/python scripts/demo.py
```

### 3.7 MOCK-режим

MOCK-режим позволяет тестировать UI и логику без реальных API-вызовов к DeepSeek.

#### Когда использовать

- Разработка и отладка UI
- Тестирование без затрат на API
- Демонстрация без настройки инфраструктуры
- CI/CD пайплайны

#### Как работает

```python
# В MOCK-режиме:
# - DeepSeek API не вызывается
# - Ответы генерируются из шаблонов
# - Redis/PostgreSQL опциональны
# - Анкета заполняется тестовыми данными
```

#### Запуск MOCK-режима

```bash
# Через переменную окружения
MOCK_MODE=true ./venv/bin/python scripts/demo.py

# Или через CLI-флаг (если поддерживается)
./venv/bin/python scripts/demo.py --mock
```

#### Отличия от MAXIMUM режима

| Аспект | MAXIMUM | MOCK |
|--------|---------|------|
| DeepSeek API | Реальные вызовы | Шаблонные ответы |
| Redis | Требуется | Опционально (in-memory fallback) |
| PostgreSQL | Требуется | Опционально |
| Стоимость | ~$0.05-0.15 за сессию | Бесплатно |
| Качество диалога | Естественный | Скриптованный |
| Скорость | ~2-5 сек/ответ | Мгновенно |

---

## 4. agent_client_simulator — Агент Тестирования

### 4.1 Назначение

Автоматическое тестирование ConsultantInterviewer через LLM-симуляцию клиента.

### 4.2 Компоненты

```text
src/agent_client_simulator/
├── client.py             # SimulatedClient — LLM-симулятор клиента
├── runner.py             # ConsultationTester — оркестратор тестов
├── reporter.py           # TestReporter — генерация отчётов
└── validator.py          # TestValidator — валидация результатов

tests/scenarios/          # 12 YAML-сценариев + шаблон
```

### 4.3 Workflow схема

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        AGENT_CLIENT_SIMULATOR                        │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐                                                │
│  │  YAML Scenario  │  (persona, goals, pain_points, etc.)           │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ SimulatedClient │  • Загружает персону из YAML                   │
│  │   (LLM-клиент)  │  • Генерирует ответы через DeepSeek            │
│  │                 │  • Поддерживает историю диалога                 │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ConsultationTester                        │    │
│  │                                                              │    │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────┐          │    │
│  │  │ DISCOVERY  │──▶│  ANALYSIS  │──▶│  PROPOSAL  │──┐       │    │
│  │  └────────────┘   └────────────┘   └────────────┘  │       │    │
│  │                                                     │       │    │
│  │  ┌────────────┐◀──────────────────────────────────┘       │    │
│  │  │ REFINEMENT │                                            │    │
│  │  └─────┬──────┘                                            │    │
│  └────────┼───────────────────────────────────────────────────┘    │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ AnketaExtractor │  LLM извлекает структурированные данные        │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐  6 проверок:                                   │
│  │  TestValidator  │  • completeness (обязательные поля)             │
│  │                 │  • data_quality (валидность данных)             │
│  │                 │  • scenario_match (соответствие сценарию)       │
│  │                 │  • phases (все фазы пройдены)                   │
│  │                 │  • no_loops (нет зацикливания)                  │
│  │                 │  • metrics (лимиты ходов/времени)               │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐  • Console (Rich)                              │
│  │  TestReporter   │  • JSON файл                                   │
│  │                 │  • Markdown отчёт                               │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐  Итоговый объект:                              │
│  │   TestResult    │  status, duration, turn_count,                 │
│  │                 │  anketa, final_anketa, validation, errors       │
│  └─────────────────┘                                                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.4 Доступные сценарии (12)

| Сценарий | Отрасль | Особенности |
|----------|---------|-------------|
| auto_service | Автосервис | Базовый B2B |
| auto_service_skeptic | Автосервис | Скептически настроенный клиент |
| beauty_salon_glamour | Салон красоты | B2C, wellness |
| logistics_company | Логистика | Грузоперевозки |
| medical_center | Медицинский центр | Запись на приём |
| medical_clinic | Клиника | Здравоохранение |
| online_school | Онлайн-школа | Образование |
| real_estate_agency | Недвижимость | Агентство |
| realestate_domstroy | Недвижимость | Застройщик |
| restaurant_delivery | Ресторан + доставка | HoReCa |
| restaurant_italiano | Ресторан | Итальянская кухня |
| vitalbox | Франшиза wellness | Квалификация партнёров |

### 4.5 Запуск

```bash
# CLI через скрипт
./venv/bin/python scripts/run_test.py auto_service
./venv/bin/python scripts/run_test.py --list
./venv/bin/python scripts/run_test.py auto_service --quiet --no-save

# С документами клиента (Stage 7.5)
./venv/bin/python scripts/run_test.py logistics_company --input-dir input/test_docs/
./venv/bin/python scripts/run_test.py auto_service --input-dir input/test/

# Программно
from src.agent_client_simulator import SimulatedClient, ConsultationTester

client = SimulatedClient.from_yaml("tests/scenarios/auto_service.yaml")
tester = ConsultationTester(client=client, verbose=True)
result = await tester.run("auto_service")
```

При использовании `--input-dir`:
- Документы загружаются через `DocumentLoader` → `DocumentAnalyzer`
- `DocumentContext` передаётся в `ConsultantInterviewer` и далее во все 4 фазы
- `AnketaExtractor.extract()` получает `document_context` для обогащения анкеты
- В отчёте `TestResult` появляется поле `documents_loaded` со списком файлов

---

## 5. agent_document_reviewer — Агент Ревью Документов

### 5.1 Назначение

Интерактивное редактирование документов во внешнем редакторе с валидацией.

### 5.2 Компоненты

```text
src/agent_document_reviewer/
├── reviewer.py           # DocumentReviewer — главный класс
├── editor.py             # ExternalEditor — работа с редактором
├── parser.py             # DocumentParser — парсинг и diff
├── history.py            # VersionHistory — история версий
├── validators.py         # Валидаторы для разных типов документов
└── models.py             # ReviewConfig, ReviewResult, ReviewStatus
```

### 5.3 Workflow схема

```text
┌──────────────────────────────────────────────────────────────────────┐
│                     AGENT_DOCUMENT_REVIEWER                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Input: Markdown / текст документа                                  │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ DocumentReviewer │  ReviewConfig:                                │
│  │                 │  • instructions — текст для пользователя       │
│  │                 │  • timeout_minutes — лимит времени             │
│  │                 │  • validator — функция валидации               │
│  │                 │  • readonly_sections — защищённые секции       │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  1. VersionHistory.add_version() — сохранить оригинал       │    │
│  │  2. DocumentParser.prepare_for_edit() — добавить инструкции │    │
│  │  3. ExternalEditor.create_temp_file()                       │    │
│  │  4. ExternalEditor.open_editor()                            │    │
│  │     ┌────────────────────────────────┐                      │    │
│  │     │  ВНЕШНИЙ РЕДАКТОР              │                      │    │
│  │     │  (VS Code / Sublime / nano)    │                      │    │
│  │     │  Пользователь редактирует      │                      │    │
│  │     └────────────────────────────────┘                      │    │
│  │  5. DocumentParser.extract_after_edit() — убрать инструкции │    │
│  │  6. Validator(content) — валидация                          │    │
│  │  7. VersionHistory.add_version() — сохранить версию         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │  ReviewResult   │  status: COMPLETED / CANCELLED / TIMEOUT /     │
│  │                 │          VALIDATION_FAILED / ERROR              │
│  │                 │  changed: bool                                  │
│  │                 │  content: str (edited)                          │
│  │                 │  errors: List[ValidationError]                  │
│  └─────────────────┘                                                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.4 AnketaReviewService

Обёртка над DocumentReviewer для анкет:

1. `show_preview()` — CLI-превью анкеты (Rich Panel)
2. `prompt_action()` — выбор: [O] Открыть / [S] Сохранить / [C] Отмена
3. Редактирование с retry (до 3 попыток при ошибках валидации)
4. `show_diff()` — отображение изменений
5. `AnketaMarkdownParser.parse()` — парсинг MD обратно в FinalAnketa

### 5.5 Использование

```python
from src.agent_document_reviewer import DocumentReviewer, ReviewConfig

config = ReviewConfig(
    instructions="Проверьте данные клиента",
    timeout_minutes=15,
    validator=my_validator,
    readonly_sections=[r'^## Метаданные'],
)

reviewer = DocumentReviewer(config, document_id="anketa_001")
result = reviewer.review(content)

if result.is_success and result.changed:
    save_document(result.content)
```

---

## 6. Интегрированный Pipeline: Test → Review

### 6.1 Общая схема

```text
┌─────────────────────────────────────────────────────────────────────┐
│                 PIPELINE: TEST → REVIEW                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐                                                │
│  │  YAML Scenario  │                                                │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ╔═════════════════════════════════════════════╗                     │
│  ║  STAGE 1: AGENT_CLIENT_SIMULATOR            ║                     │
│  ║                                             ║                     │
│  ║  SimulatedClient → ConsultationTester →     ║                     │
│  ║  AnketaExtractor → TestValidator            ║                     │
│  ║                                             ║                     │
│  ║  Output: TestResult + FinalAnketa           ║                     │
│  ╚══════════════════════╤══════════════════════╝                     │
│                          │                                           │
│                          ▼                                           │
│                 ┌────────────────┐                                   │
│                 │ Validation OK? │                                   │
│                 └───────┬────────┘                                   │
│                    YES  │   NO → Log errors, exit                    │
│                         ▼                                            │
│  ╔═════════════════════════════════════════════╗                     │
│  ║  STAGE 2: AGENT_DOCUMENT_REVIEWER           ║                     │
│  ║                                             ║                     │
│  ║  AnketaReviewService:                       ║                     │
│  ║  1. show_preview()                          ║                     │
│  ║  2. prompt_action() → Open editor           ║                     │
│  ║  3. Validate with retry (до 3 попыток)     ║                     │
│  ║  4. show_diff()                             ║                     │
│  ║  5. Parse → FinalAnketa                     ║                     │
│  ╚══════════════════════╤══════════════════════╝                     │
│                          │                                           │
│                          ▼                                           │
│                 ┌────────────────┐                                   │
│                 │ Final Output:  │                                   │
│                 │ anketa.md      │                                   │
│                 │ anketa.json    │                                   │
│                 └────────────────┘                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 Запуск

```bash
# Полный pipeline
./venv/bin/python scripts/run_pipeline.py auto_service

# С автоматическим одобрением (без ревью)
./venv/bin/python scripts/run_pipeline.py auto_service --auto-approve

# Без этапа ревью
./venv/bin/python scripts/run_pipeline.py auto_service --skip-review

# С указанием выходной папки
./venv/bin/python scripts/run_pipeline.py auto_service --output-dir output/final
```

---

## Архитектурные заметки

### Независимость агентов

Все агенты полностью независимы и могут использоваться отдельно:

- **VoiceConsultant** — не требует ConsultantInterviewer
- **ConsultantInterviewer** — не требует LiveKit или Azure
- **MaximumInterviewer** — не требует LiveKit или Azure; требует Redis + PostgreSQL (или MOCK-режим без них)
- **agent_client_simulator** — не требует agent_document_reviewer
- **agent_document_reviewer** — не требует agent_client_simulator

### Точки интеграции

Агенты интегрируются через общие модели:

1. **FinalAnketa** — единая модель анкеты (10 блоков + доп. поля + метаданные)
2. **AnketaGenerator** — конвертация FinalAnketa → Markdown/JSON
3. **AnketaMarkdownParser** — парсинг Markdown обратно в FinalAnketa
4. **OutputManager** — единая структура output/
5. **SessionManager** — общая SQLite БД (для voice + web)

### Расширяемость

- Новые сценарии: добавьте YAML в `tests/scenarios/`
- Новые отрасли: добавьте YAML в `config/industries/`
- Новые валидаторы: расширьте `validators.py`
- Новые форматы отчётов: расширьте `TestReporter`
