# Глубокий экспертный анализ сессии 99c5e297

**Дата первичного анализа:** 2026-02-14
**Дата углублённого анализа:** 2026-02-14
**Методология:** Мультиэкспертный аудит (backend, frontend, extraction pipeline, session data)
**Сессия:** 99c5e297, 17 мин, 114 сообщений, consultation mode

---

## ЧАСТЬ 1: АНАЛИЗ ДАННЫХ СЕССИИ

### 1.1 Что извлечено vs. что должно было быть

| Поле | В DB (anketa_data) | Из диалога (ожидаемо) | Статус |
|------|-------|-------------|--------|
| company_name | Редут | Редут | OK |
| industry | ветеринария | ветеринария | OK |
| specialization | вет. услуги для домашних животных | вет. услуги для домашних | OK |
| website | test.test | test.test (ручной ввод) | OK |
| contact_name | Сергей | Сергей | OK |
| contact_email | info@test.test | info@test.test (ручной ввод) | OK |
| contact_phone | +4366475503580 | +43 664 755 03580 | OK |
| contact_role | *(пусто)* | Консультант (msg #74) | MISS |
| business_description | оказание вет. услуг | оказание вет. услуг | OK |
| services | 7 пунктов | 7+ (всё кроме груминга) | OK |
| working_hours | пн-пт 8-19, сб 8-15... | пн-пт 8-19, сб 8-15, дежурный 24/7 | OK |
| call_volume | 80-120 | 80-100-120 | OK |
| voice_tone | дружелюбный, тёплый | дружелюбный, тёплый (msg #70) | OK |
| voice_gender | female | женский (msg #70) | OK |
| agent_name | **Командир** | **неизвестно** | BUG |
| budget | *(пусто)* | Клиент спрашивал агента | MISS |
| integrations | Google Calendar, учёт | Google Calendar, своя система | OK |
| agent_functions | 5 функций | ~5 функций | OK |
| transfer_conditions | сложные случаи... | перевод при сложных случаях (msg #70) | OK |

**Ключевые проблемы с данными:**

1. **`agent_name = "Командир"`** — Это слово пользователя (msg #4: "Командир.") ошибочно извлечено как имя агента. Реальное имя не было указано. Это показывает проблему с ранней extraction: данные из первых сообщений (когда контекст ещё неясен) попадают в anketa и **больше никогда не перезаписываются** (issue: accumulative merge never self-corrects).

2. **`contact_role` пусто** — Несмотря на msg #74 ("Консультант"), роль не извлечена. Возможная причина: sliding window 12 msgs мог не включить этот обмен в момент extraction.

3. **`completion_rate` = 0%** в rendered markdown — При этом JSON anketa содержит ~25 заполненных полей. Это **баг рендеринга** в `anketa_md`, а не проблема extraction.

4. **`dialogue_history` = []** — Диалог НЕ сохранился в DB. Endpoint PUT `/api/session/{id}/dialogue` добавлен в последнем коммите, но для этой сессии он ещё не работал.

5. **`duration_seconds` = 0** — Длительность сессии не записана, хотя сессия длилась 17 минут.

6. **`status` = "active"** — Сессия так и не была переведена в terminal состояние. Пользователь нажал "Остановить", но видимо `on_session_close` не отработал (fire-and-forget task потерялся).

### 1.2 Extraction Timeline — Глубокий анализ

Из первичного анализа: 25 extractions за 17 мин. Паттерн деградации:

```
Extraction#  Messages  Completion  Тренд
1            7         13%         ↑ начальный рост
2            10        27%         ↑
3            16        33%         ↑
4            21        47%         ↑
5            23        53%         ↑ ПИКОВАЯ ТОЧКА
6            28        27%         ↓↓ ОБВАЛ (-26%)
7            31        13%         ↓↓ ОБВАЛ (-14%)
8-25         34-114    7-27%       → СТАГНАЦИЯ (never recovers)
```

**Критическое наблюдение:** Completion достигает 53% на extraction #5 (23 msgs), а затем ПАДАЕТ до 27% и никогда не восстанавливается. Это показывает **катастрофический баг в accumulative merge**: новые extraction результаты с пустыми полями ПЕРЕЗАПИСЫВАЮТ ранее заполненные поля.

Но стоп — accumulative merge **не должен** перезаписывать заполненные поля пустыми (строки 1027-1058 consultant.py). Значит, причина в другом:

**Гипотеза:** При window=12, extraction #6 (28 msgs) видит только сообщения 17-28. В этом окне нет информации о company_name, industry и т.д. (они обсуждались в msgs 1-16). LLM возвращает пустые поля. Accumulative merge **сохраняет** старые значения — но `completion_rate` считается от **нового** extraction результата, а не от accumulated anketa.

**Вывод:** completion_rate в логах показывает completion **текущего extraction**, а не **накопленной anketa**. Это **ошибка метрики**, создающая ложное впечатление деградации.

---

## ЧАСТЬ 2: BACKEND — КРИТИЧЕСКИЕ БАГИ

### B1. [CRITICAL] Review Phase полностью заменяет system prompt

**Файл:** `src/voice/consultant.py` ~ line 1250

Когда review phase активируется, `activity.update_instructions(review_prompt)` **полностью заменяет** system prompt. Review prompt — всего ~25 строк. Теряются:
- Информация о компании Hanc.AI
- 22 роли агента и ценовые планы
- Правила anti-hallucination
- Knowledge Base контекст
- Правила краткости диалога
- Missing fields reminder
- Вся verbosity конфигурация

**Воздействие:** Агент в review phase — это **другой агент**. Если пользователь спросит "какие у вас тарифы?", агент или выдумает ответ, или откажется отвечать.

**Решение:** Дополнить review prompt всеми необходимыми guardrails, или сделать **append** вместо полной замены.

### B2. [CRITICAL] Review Phase не имеет пути выхода

**Файл:** `src/voice/consultant.py`

`consultation.review_started = True` — флаг **никогда не сбрасывается**. Нет:
- Timeout механизма
- Возврата в discovery mode
- Обработки ситуации когда completion_rate падает (пользователь удалил поля)

Missing fields reminder пропускает injection когда `review_started = True`. Агент навсегда застревает в review mode.

**Решение:** Добавить recovery: если completion_rate < 0.8 во время review, сбросить `review_started = False` и вернуть discovery prompt.

### B3. [CRITICAL] `update_dialogue` endpoint обходит state machine

**Файл:** `src/web/server.py` ~ lines 533-552

`PUT /api/session/{session_id}/dialogue` принимает `Optional[str]` status и пишет его в DB **без валидации** через `SessionManager.update_dialogue()`. Это полностью обходит v5.1 state machine:

```python
# В update_dialogue() — прямой SQL UPDATE без валидации
"UPDATE sessions SET ... status = ? ... WHERE session_id = ?", (status, ...)
```

Любой статус ("banana", "processing", "completed") будет записан в DB. Вся работа v5.1 по state machine бесполезна, если этот endpoint используется для обновления статуса.

**Решение:** Убрать status из `UpdateDialogueRequest` или валидировать через `validate_transition()`.

### B4. [CRITICAL] Duplicate `reconnect_session` + POST reconnect обходит state machine

**Файл:** `src/web/server.py` ~ lines 420, 644

Две функции с одинаковым именем `reconnect_session` (GET и POST). POST версия вызывает `session_mgr.update_status(session_id, "active")` без try/except для `InvalidTransitionError`. Если сессия в terminal состоянии (confirmed/declined), endpoint крашится.

### B5. [HIGH] Fire-and-forget задачи при закрытии сессии

**Файл:** `src/voice/consultant.py` ~ lines 1612, 1630

`on_session_close` создаёт `asyncio.create_task()` для финализации и сохранения диалога. Но event loop может завершиться до окончания этих задач (5-10 сек для full extraction + notifications + PostgreSQL). Задачи будут отменены без предупреждения.

**Подтверждение:** В данной сессии `duration_seconds = 0`, `status = "active"`, `dialogue_history = []`. Всё это — признаки того, что finalize task не завершился.

**Решение:** Использовать `asyncio.shield()` или ожидать завершение задач перед выходом из event loop.

### B6. [HIGH] Extraction не может исправить собственные ошибки

**Файл:** `src/voice/consultant.py` ~ lines 1022-1065, `src/anketa/extractor.py` ~ lines 629-674

Accumulative merge **всегда** сохраняет старое значение, если оно непустое. Если первый extraction ошибочно записал `agent_name = "Командир"` (из тестового msg #4), последующие extraction **никогда не смогут** это исправить, даже если LLM правильно определит что это не имя агента.

**Подтверждение:** `agent_name = "Командир"` в DB — прямое следствие этого бага.

**Решение:** Для определённых полей (agent_name, voice_tone, voice_gender) — разрешить перезапись если new confidence > old confidence. Или: не извлекать эти поля из первых 10 сообщений.

### B7. [HIGH] RuntimeStatus не доступен frontend'у

**Файл:** `src/voice/consultant.py` ~ line 98

`VoiceConsultationSession.runtime_status` — ephemeral in-memory поле. Ни один API endpoint его не возвращает. Frontend не может показать "agent is processing" / "agent is completing" / "error".

Вся v5.1 архитектура RuntimeStatus бесполезна для frontend'а.

**Решение:** Добавить `GET /api/session/{id}/runtime-status` или включить runtime_status в ответ anketa endpoint.

### B8. [HIGH] TOCTOU race condition на anketa merge

**Файл:** `src/anketa/extractor.py`, `src/web/server.py`

Frontend `saveAnketa()` и voice agent `_update_anketa_via_api()` могут одновременно:
1. Прочитать anketa из DB
2. Merged с новыми данными
3. Записать обратно

Правка пользователя может быть перезаписана stale extraction результатом.

**Решение:** Добавить optimistic locking (version field) или field-level merge вместо full-record merge.

### B9. [MEDIUM] Double extraction при закрытии сессии

`_finalize_and_save()` вызывает `finalize_consultation()` (full extraction) и затем **ещё одну** extraction внутри себя. Двойная стоимость LLM и 10+ секунд задержки.

### B10. [MEDIUM] `NameError: event_log` в `on_room_metadata_changed`

**Файл:** `src/voice/consultant.py` ~ line 2162

`event_log` определён внутри `_register_event_handlers()`, но `on_room_metadata_changed` определён в `entrypoint()` — другой scope. При загрузке документов handler крашится с `NameError`. Try/except ловит ошибку, но document context injection не работает.

### B11. [MEDIUM] "Greeting lock" — sleep, не lock

`await asyncio.sleep(3.0)` в `entrypoint()` — не блокирует VAD или event handlers. Во время этих 3 секунд echo от greeting может trigger extraction.

---

## ЧАСТЬ 3: FRONTEND — КРИТИЧЕСКИЕ БАГИ

### F1. [CRITICAL] `handleGoToResults()` роутит на неправильный path

**Файл:** `public/app.js` ~ line 1446

```js
this.router.navigate(`/review/${this.uniqueLink}`);
```

Router знает только `/session/:link/review` и `/session/:link`. Path `/review/:link` не match'ится — показывает landing page вместо review.

**Правильный путь:** `/session/${this.uniqueLink}/review`

### F2. [CRITICAL] Отсутствуют CSS стили для `toast-success` и `toast-warning`

**Файл:** `public/styles.css`

Определены только `.toast-info` и `.toast-error`. Код использует `showToast(msg, 'success')` в 5+ местах и `showToast(msg, 'warning')` в 1 месте. Эти toast'ы **невидимы** пользователю (белый текст на прозрачном фоне).

**Затронутые функции:**
- `handleStartSession()` — success toast невидим
- `handleRecordSession()` — success toast невидим
- `handleSaveAnketa()` — success toast невидим
- `saveAndLeave()` — success toast невидим
- `exportAnketa()` — success toast невидим
- `pollAnketa()` — warning toast невидим

### F3. [HIGH] `pauseSession()` не вызывает backend

**Файл:** `public/app.js` ~ lines 2006-2022

Pause делает только UI изменения (overlay, кнопки). Backend НЕ уведомляется. Если пользователь уходит со страницы в паузе и возвращается — backend думает сессия "active".

Compare: `resumeSession()` корректно вызывает `POST /api/session/${id}/resume`.

### F4. [HIGH] `handleStartSession()` использует `data.token`, reconnect — `data.user_token`

**Файл:** `public/app.js` ~ line 1397 vs line 1180

Несоответствие ключей токена между двумя путями подключения. Если reconnect endpoint возвращает `user_token`, то `handleStartSession` получит `undefined` как токен.

### F5. [MEDIUM] Interview mode уничтожает DOM каждые 2 секунды

**Файл:** `public/app.js` ~ line 2586

`updateAnketaFromServerInterview()` делает `container.innerHTML = ''` и перестраивает весь DOM каждые 2 секунды. Последствия:
- Потеря scroll position
- Визуальное мерцание
- Потеря выделения текста
- DOM thrashing каждые 2 секунды

Consultation mode корректно обновляет только изменённые поля.

### F6. [MEDIUM] Нет обратной нормализации при сохранении

`_normalizeAnketaData()` маппит `business_description` → `company_description` для отображения. Но `saveAnketa()` читает DOM поля по frontend именам (`company_description`) и отправляет их на backend. Backend ожидает `business_description`. Ручные правки пользователя в это поле могут теряться.

### F7. [MEDIUM] `messageHistory` undefined в `pollAnketa()`

**Файл:** `public/app.js` ~ line 2292

```js
const messageCount = this.messageHistory?.length || 0;
```

`this.messageHistory` не существует. Класс использует `this.messageCount` (число). Debug panel всегда показывает "Messages: 0".

### F8. [LOW] Нет фильтра "Declined" в dashboard

Filter tabs: All, Active, Paused, Confirmed. Нет "Declined", хотя status badge и label для declined есть.

### F9. [LOW] Нет pre-check микрофона

Разрешение на микрофон запрашивается только при `startRecording()`. Если пользователь откажет, сессия уже создана и подключена к LiveKit — но говорить нельзя. Нет UX для этого случая.

### F10. [LOW] Нет таймера длительности во время сессии

Review screen показывает duration. Во время активной сессии — нет.

### F11. [LOW] Нет auto-reconnect после disconnect

`RoomEvent.Disconnected` показывает toast, но нет автоматического переподключения или кнопки reconnect.

### F12. [LOW] `beforeunload` не сохраняет interview mode anketa

Interview mode пропускает `sendBeacon` save при закрытии вкладки.

---

## ЧАСТЬ 4: EXTRACTION PIPELINE — ГЛУБОКИЙ АУДИТ

### E1. [CRITICAL] Два параллельных extraction prompt'а не синхронизированы

**Prompt A:** `prompts/anketa/extract.yaml` — YAML шаблон (system prompt)
**Prompt B:** `src/anketa/extractor.py` `_build_extraction_prompt()` — hardcoded (user message)

Только system_prompt из YAML используется. User message (со схемой JSON) — всегда hardcoded. Три поля есть в hardcoded, но отсутствуют в YAML: `business_type`, `working_hours`, `transfer_conditions`.

Если кто-то обновит YAML думая что это source of truth — изменения не повлияют на extraction.

### E2. [CRITICAL] Interview mode — полностью hardcoded prompt, нет YAML

Extraction prompt для interview mode (`_extract_interview()`, lines 1477-1531) — единственная строка system prompt + hardcoded JSON schema. Нет YAML файла, нет возможности менять prompt без деплоя.

### E3. [HIGH] SmartExtractor покрывает только 8 из 35+ полей

Regex паттерны есть только для:
- `company_name` (3 паттерна)
- `industry` (2 паттерна)
- `contact_name` (2 паттерна)
- `contact_role` (2 паттерна)
- `employee_count` (2 паттерна) — **поля нет в схеме!**
- `website` (2 паттерна)
- `contact_phone` (5 паттернов)
- `contact_email` (3 паттерна)

**27+ полей** без regex fallback. Если LLM промахнулся — нет запасного варианта.

### E4. [HIGH] `employee_count` — vestigial regex pattern

SmartExtractor имеет паттерны для `employee_count`, но это поле **не существует** в FinalAnketa. Извлечённые данные молча отбрасываются.

### E5. [MEDIUM] 5 полей отсутствуют в missing fields reminder

`_FIELD_LABELS` dict не включает:
- `additional_notes`
- `typical_questions`
- `main_function`
- `additional_functions`
- `language`

Агент **никогда** не будет напоминать собрать эти поля.

### E6. [MEDIUM] DialogueCleaner не чистит list-type поля

`STRICT_FIELDS` и `DESCRIPTION_FIELDS` покрывают строковые поля. Списковые поля (`services`, `current_problems`, `business_goals`, `client_types`) не проходят очистку. Могут содержать артефакты диалога.

### E7. [LOW] `voice_gender` и `voice_tone` имеют hardcoded defaults

Даже если клиент указал "мужской голос", при ошибке LLM extraction defaults ("female", "professional") перезапишут указание.

---

## ЧАСТЬ 5: ROOT CAUSE ANALYSIS — 8 ПРОБЛЕМ ИЗ ПЕРВИЧНОГО АНАЛИЗА

### P1: Агент обрывает фразы на середине (16 жалоб)

**Root Causes (множественные):**

1. **`update_instructions()` вызывается во время speech generation.** Missing fields reminder и KB injection отправляют `session.update` в Azure API во время активной генерации. Azure может прервать текущий ответ.

2. **Review phase `generate_reply()` interrupt.** Когда запускается review phase, `agent_session.generate_reply()` начинает новый ответ, прерывая текущий.

3. **Extraction latency (25.7 sec avg) + concurrent processing.** Voice agent, extraction LLM и update_instructions работают параллельно. При высокой нагрузке CPU/network — задержки в audio streaming.

4. **Azure VAD `silence_duration_ms: 1750` (vs 4000 ранее).** Порог молчания снижен, что заставляет агента быстрее "отпускать" turn. Если агент формирует длинный ответ с паузами > 1.75 сек, Azure считает turn завершённым.

**Примечание:** Из voice_config: `silence_duration_ms: 1750`. В MEMORY.md написано 4000. Значит, конфиг сессии использовал 1750 — гораздо агрессивнее.

### P2: Window=12 вместо 50

**Root Cause:** На момент этой сессии EXTRACTION_WINDOW_SIZE в .env был 12 (или default). Коммит 9d763ec изменил default на 50, но эта сессия прошла ДО коммита.

**Status:** FIXED в 9d763ec.

### P3: 25 extractions за 17 мин

**Root Cause:** Extraction запускается после КАЖДОГО user message (v5.0). При 57 user messages — 25 extraction запусков. Каждый extraction = 25 сек LLM вызов.

**Суммарная стоимость:** ~10.7 мин LLM time из 17 мин сессии (63% времени сессии тратится на extraction).

**Предложение:** Throttle: не чаще 1 extraction в 30 секунд. Или trigger только если новое сообщение содержит потенциально extractable данные.

### P4: Агент не знает о UI/платформе

**Root Cause:** consultant.yaml содержит инструкции о UI ("на экране справа", "нажмите кнопку"). Но НЕ содержит:
- Как работает кнопка "Сохранить"
- Что анкета автоматически сохраняется
- Как экспортировать (markdown/PDF)
- Как вернуться к сессии позже
- Что пользователь может редактировать поля вручную

**Предложение:** Добавить секцию "Платформа и UI" в consultant.yaml с описанием доступных функций.

### P5: Галлюцинация "отправлю на email"

**Root Cause:** Anti-hallucination правила (lines 164-167) запрещают выдумывать данные. Но нет явного правила "не обещай функциональность, которой нет". Агент может пообещать "отправить email", "создать PDF", "позвонить" — даже если этих функций нет.

**Предложение:** Добавить явный запрет: "НИКОГДА не обещай действия, которых нет в системе. У тебя нет возможности отправлять email, звонить, создавать документы."

### P6: Агент зацикливается после review

**Root Cause:** B2 (см. выше). `review_started = True` без пути выхода. Плюс: в review prompt нет инструкций что делать ПОСЛЕ подтверждения. Агент повторяет одни и те же фразы.

### P7: dialogue_history не сохраняется

**Root Cause:** PUT `/api/session/{id}/dialogue` добавлен в коммите 9d763ec, но для этой сессии код ещё не работал. Плюс: `on_session_close` fire-and-forget task мог не завершиться (B5).

**Status:** Partially FIXED в 9d763ec. Но проблема B5 (fire-and-forget) остаётся.

### P8: agent_name="Командир" вместо имени

**Root Cause:** B6 (accumulative merge never self-corrects). Msg #4: "Командир." извлечено как agent_name в первом extraction. Последующие extractions не могут перезаписать это.

**Дополнительно:** Hardcoded defaults для agent_name были убраны в 9d763ec, но merge policy не изменилась.

---

## ЧАСТЬ 6: НОВЫЕ ПРОБЛЕМЫ (не в первичном анализе)

### N1. [CRITICAL] Bidirectional phone/email sync propagates errors

`_merge_anketa_data()` синхронизирует `phone` ↔ `contact_phone` и `email` ↔ `contact_email`. Если одно поле получает ошибочное значение, оно копируется в оба поля и не может быть исправлено extraction'ом (из-за B6).

### N2. [CRITICAL] `completion_rate` в логах — не от accumulated anketa

Extraction timeline показывает completion 53% → 27% → 7%. Но в DB anketa содержит ~25 заполненных полей. `completion_rate` в логах считается от **текущего extraction result**, а не от **накопленных данных**. Это создаёт ложное впечатление деградации и может trigger'ить неправильные решения (например, не запускать review phase).

### N3. [HIGH] Вся v5.1 state machine обходится через update_dialogue

Единственный endpoint который агент использует для обновления статуса (`PUT /dialogue` с `status` полем) — полностью обходит state machine. Вся архитектура v5.1 неэффективна.

### N4. [HIGH] Interview mode `beforeunload` не сохраняет данные

Если пользователь закроет вкладку во время interview — данные потеряны. Consultation mode корректно использует `sendBeacon`.

### N5. [HIGH] Toast success/warning невидимы

5+ мест в коде используют `showToast(msg, 'success')` — но CSS стиля нет. Пользователь не видит подтверждения сохранения анкеты, экспорта, и т.д.

### N6. [MEDIUM] Нет "agent thinking" индикации

Между пользовательским вводом и ответом агента — нет визуального состояния "Агент думает...". Пользователь видит "Слушаю..." и думает что связь потеряна.

### N7. [MEDIUM] Dialogue auto-scroll без guard

Каждый `addMessage()` скроллит к низу. Если пользователь прокрутил вверх перечитать ответ — его выбросит обратно. Anketa form имеет scroll guard (15 сек), dialogue — нет.

### N8. [MEDIUM] Pydantic model создаётся каждые 2 сек на каждый poll

`GET /api/session/{id}/anketa` создаёт `FinalAnketa` Pydantic model (с вложенными AgentFunction, Integration, FAQItem и т.д.) каждые 2 секунды для каждой активной сессии. При множестве сессий — ненужная нагрузка.

---

## ЧАСТЬ 7: ПРИОРИТИЗИРОВАННЫЕ РЕКОМЕНДАЦИИ

### Tier 1: Критические баги (исправить ДО продакшена)

| # | Проблема | Решение | Усилие | Файлы |
|---|----------|---------|--------|-------|
| 1 | B3+N3: update_dialogue обходит state machine | Убрать status из UpdateDialogueRequest, или валидировать через validate_transition() | 30 мин | server.py, manager.py |
| 2 | B1: Review phase заменяет весь prompt | Делать append (base_prompt + review_instructions) вместо полной замены | 1 час | consultant.py, review.yaml |
| 3 | B2: Review phase без выхода | Добавить recovery при completion_rate < 0.8, timeout 5 мин | 1 час | consultant.py |
| 4 | F1: Неправильный route в handleGoToResults | Исправить `/review/` → `/session/.../review` | 5 мин | app.js |
| 5 | F2: Нет CSS для toast-success/warning | Добавить стили | 15 мин | styles.css |
| 6 | E1: Два несинхронизированных extraction prompt | Сделать YAML единственным source of truth, загружать schema из YAML | 2 часа | extractor.py, extract.yaml |

### Tier 2: Высокий приоритет (исправить в ближайшем спринте)

| # | Проблема | Решение | Усилие | Файлы |
|---|----------|---------|--------|-------|
| 7 | B5: Fire-and-forget finalization | asyncio.shield() + await с timeout | 1 час | consultant.py |
| 8 | B6: Merge не позволяет исправлять ошибки | Confidence-based merge: перезаписывать если >80% диалога указывает на новое значение | 3 часа | extractor.py |
| 9 | B7: RuntimeStatus не доступен frontend | Добавить в ответ anketa endpoint | 30 мин | server.py |
| 10 | F3: pauseSession не вызывает backend | Добавить POST /api/session/{id}/pause вызов | 30 мин | app.js |
| 11 | P1: Агент обрывается (update_instructions во время речи) | Буферизовать update_instructions до завершения текущего ответа | 2 часа | consultant.py |
| 12 | P3: 25 extractions/17 мин | Throttle: макс 1 extraction в 30 сек + smart trigger | 1 час | consultant.py |
| 13 | P4: Агент не знает о UI | Добавить секцию "Платформа" в prompt | 30 мин | consultant.yaml |
| 14 | P5: Галлюцинация функций | Явный запрет: "не обещай действий, которых нет" | 15 мин | consultant.yaml |
| 15 | N2: completion_rate считается от extraction, не от accumulated | Логировать completion от accumulated anketa | 30 мин | consultant.py |

### Tier 3: Средний приоритет (следующий спринт)

| # | Проблема | Решение | Усилие | Файлы |
|---|----------|---------|--------|-------|
| 16 | F5: Interview DOM thrashing | Incremental update (как consultation mode) | 2 часа | app.js |
| 17 | F6: Нет обратной нормализации | Добавить reverse mapping в saveAnketa() | 1 час | app.js |
| 18 | B8: TOCTOU race condition | Field-level merge или optimistic locking | 3 часа | server.py, manager.py |
| 19 | B10: NameError event_log | Передать event_log в scope или создать в entrypoint | 15 мин | consultant.py |
| 20 | E4: employee_count vestigial | Удалить паттерн из SmartExtractor | 5 мин | data_cleaner.py |
| 21 | N6: Нет "agent thinking" | Показывать "Обрабатываю..." между user input и agent response | 1 час | app.js |
| 22 | N7: Dialogue auto-scroll | Добавить scroll guard (как в anketa form) | 30 мин | app.js |
| 23 | E5: 5 полей не в reminder | Добавить в _FIELD_LABELS | 15 мин | consultant.py |

### Tier 4: Low priority (бэклог)

| # | Проблема | Решение | Усилие |
|---|----------|---------|--------|
| 24 | F8: Нет фильтра Declined | Добавить tab | 30 мин |
| 25 | F9: Нет pre-check микрофона | MediaDevices.getUserMedia() до создания сессии | 1 час |
| 26 | F10: Нет таймера сессии | Добавить timer component | 30 мин |
| 27 | F11: Нет auto-reconnect | Retry с exponential backoff | 2 часа |
| 28 | F12: Interview beforeunload | Добавить sendBeacon для interview mode | 15 мин |
| 29 | E6: DialogueCleaner не чистит списки | Расширить cleaner | 1 час |
| 30 | N8: Pydantic на каждый poll | Кэшировать или считать completion из raw dict | 1 час |

---

## ЧАСТЬ 8: АРХИТЕКТУРНЫЕ РЕКОМЕНДАЦИИ

### A1. Единый source of truth для extraction prompts

Сейчас: YAML (частично используется) + hardcoded (реально используется) + interview hardcoded.
Рекомендация: Все extraction prompts в YAML. Extractor загружает schema из YAML. Нет hardcoded prompts.

### A2. Event-driven architecture для agent state

Сейчас: Прямые вызовы `update_instructions()` в середине event handlers.
Рекомендация: Очередь инструкций. `update_instructions()` вызывается только между agent turns (когда агент не говорит).

### A3. Optimistic locking для anketa

Сейчас: Last-write-wins.
Рекомендация: `anketa_version` поле, increment при каждом update. Merge отклоняется если version mismatch.

### A4. Extraction throttling + smart triggers

Сейчас: После каждого user message.
Рекомендация:
- Минимальный интервал: 30 секунд
- Smart trigger: запускать только если user message содержит ключевые слова (имя, телефон, email, компания, etc.)
- Batch trigger: запускать после 3+ новых сообщений в тихий момент

### A5. Session finalization guard

Сейчас: fire-and-forget.
Рекомендация: Dedicated finalization service/worker. При disconnect — поставить в очередь. Worker обрабатывает независимо от event loop агента.

---

## ИТОГО

| Категория | Критических | Высоких | Средних | Низких | ВСЕГО |
|-----------|------------|---------|---------|--------|-------|
| Backend | 4 | 4 | 3 | 0 | 11 |
| Frontend | 2 | 2 | 3 | 5 | 12 |
| Extraction | 2 | 2 | 2 | 1 | 7 |
| **ИТОГО** | **8** | **8** | **8** | **6** | **30** |

**Первичный анализ нашёл 8 проблем. Глубокий анализ нашёл 30. Round 2 нашёл ещё 15.**

Оценка трудоёмкости Tier 1+2 (критичное + высокое): **~15 часов работы.**

---

## СТАТУС ИСПРАВЛЕНИЙ (2026-02-14)

### Tier 1 — ВСЕ ИСПРАВЛЕНЫ

| # | Проблема | Статус | Коммит |
|---|----------|--------|--------|
| B3+N3 | update_dialogue обходит state machine | FIXED | pending |
| B1 | Review phase заменяет prompt | FIXED (append) | pending |
| B2 | Review phase без выхода | FIXED (recovery < 0.8) | pending |
| F1 | Неправильный route | FIXED | pending |
| F2 | Нет CSS toast-success/warning | FIXED | pending |
| E1 | Два prompt'а не синхронизированы | FIXED (3 поля добавлены в YAML) | pending |

### Pre-existing test failures — ИСПРАВЛЕНЫ

| Тест | Причина | Фикс |
|------|---------|------|
| test_review_phase_triggered | completion_rate=0.6 (порог 0.9) | → 0.95 + все 15 required fields |
| test_interview_mode_review_phase_still_triggers | completion_rate=0.7 (порог 0.9) | → 0.95 + все 15 required fields |

**Результат:** 1846 passed, 0 failed (было 1815 passed, 2 failed)

---

## ЧАСТЬ 9: ROUND 2 — НОВЫЕ ПРОБЛЕМЫ (Security + Infrastructure)

### NEW-1. [CRITICAL] Path Traversal в file upload

**Файл:** `src/web/server.py` ~ line 938

```python
# БЫЛО:
file_path = upload_dir / file.filename  # filename может содержать ../../etc/passwd
```

**Фикс:** Sanitize через `Path(filename).name` + проверка dot-файлов.

**Статус:** FIXED

### NEW-2. [CRITICAL] Нет аутентификации на endpoint'ах

Все 20+ endpoint'ов доступны без аутентификации. Session ID = 8 символов (uuid4[:8]) — brute-forceable за ~65K попыток.

**Статус:** ACKNOWLEDGED (требует архитектурного решения)

### NEW-3. [HIGH] Нет CORS + sendBeacon incompatibility

`sendBeacon` может быть заблокирован без CORS headers. Сохранение при закрытии вкладки может молча проваливаться.

**Статус:** ACKNOWLEDGED

### NEW-4. [HIGH] SQLite concurrency без locking

`check_same_thread=False` + TOCTOU в `update_anketa()`. Concurrent read-modify-write без locks.

**Статус:** ACKNOWLEDGED (покрывается B8/TOCTOU fix)

### NEW-5. [MEDIUM] FileHandler memory leak

**Файл:** `src/voice/consultant.py` lines ~1526, ~1979

`logging.FileHandler` добавляется при каждом вызове без проверки существующих handlers.

**Фикс:** `if not any(isinstance(h, logging.FileHandler) for h in logger.handlers)`

**Статус:** FIXED

### NEW-6. [MEDIUM] XSS через CSS class injection

**Файл:** `public/app.js` ~ line 1659

```js
// БЫЛО:
<div class="priority-${i.priority}">

// СТАЛО:
const safePriority = ['high', 'medium', 'low'].includes(i.priority) ? i.priority : 'medium';
<div class="priority-${safePriority}">
```

**Статус:** FIXED

### NEW-7. [MEDIUM] `room_exists` может быть unbound

В reconnect endpoint, `room_exists` устанавливается внутри try/except — может остаться undefined при ошибке.

**Статус:** ACKNOWLEDGED

### NEW-8. [MEDIUM] LiveKitAPI.aclose() пропускается при exception

**Файл:** `src/web/server.py` — 9 мест создания `LiveKitAPI()`

В 4 местах `aclose()` находилась в happy path без `try/finally`. При исключении ресурс утекает.

**Фикс:** Заменены на `try/finally` паттерн с `lk_api = None` + `if lk_api: await lk_api.aclose()`.

**Статус:** FIXED (все 9 мест проверены)

### NEW-9. [MEDIUM] Session ID collision probability

`uuid4()[:8]` = 4 hex chars = 16^8 = ~4.3 billion. Но birthday paradox: 50% collision at ~65K sessions.

**Статус:** ACKNOWLEDGED (low risk для текущего масштаба)

### NEW-10. [MEDIUM] delete_sessions принимает untyped dict

**Файл:** `src/web/server.py` ~ line 178

Без Pydantic validation — можно отправить неограниченный массив ID.

**Фикс:** `DeleteSessionsRequest(BaseModel)` с `max_length=100`.

**Статус:** FIXED

### NEW-11. [MEDIUM] voice_config хранит произвольный JSON

**Файл:** `src/web/server.py` ~ line 390

`req: dict` без фильтрации — можно записать произвольные данные в DB.

**Фикс:** `ALLOWED_VOICE_CONFIG_KEYS` whitelist + фильтрация.

**Статус:** FIXED

### NEW-12. [MEDIUM] .env.example содержит медленную модель

`.env.example` рекомендует `deepseek-reasoner` (200+ сек) вместо `deepseek-chat` (2-3 сек).

**Статус:** ACKNOWLEDGED

### NEW-13. [MEDIUM] Dialogue history растёт неограниченно в памяти

`VoiceConsultationSession.dialogue_history` — unbounded list. При очень длинных сессиях (200+ сообщений) может занять значительную память.

**Статус:** ACKNOWLEDGED

### NEW-14. [HIGH] sendBeacon POST → PUT endpoint = 405

**Файл:** `public/app.js` ~ line 499, `src/web/server.py` ~ line 520

`navigator.sendBeacon()` всегда отправляет POST. Endpoint `/api/session/{id}/anketa` был только PUT. Результат: 405 Method Not Allowed — данные при закрытии вкладки НИКОГДА не сохраняются.

**Фикс:** Добавлен `@app.post()` декоратор на тот же endpoint.

**Статус:** FIXED

### NEW-15. [LOW] Content-Disposition filename encoding

При нелатинских символах в filename — могут быть проблемы кодировки в Content-Disposition header.

**Статус:** ACKNOWLEDGED

---

## ОБНОВЛЁННАЯ СВОДКА

| Категория | Критических | Высоких | Средних | Низких | ВСЕГО |
|-----------|------------|---------|---------|--------|-------|
| Backend (Tier 1-3) | 4 | 4 | 3 | 0 | 11 |
| Frontend (Tier 1-4) | 2 | 2 | 3 | 5 | 12 |
| Extraction (Tier 1-4) | 2 | 2 | 2 | 1 | 7 |
| Security (Round 2) | 2 | 1 | 4 | 1 | 8 |
| Infrastructure (Round 2) | 0 | 2 | 5 | 0 | 7 |
| **ИТОГО** | **10** | **11** | **17** | **7** | **45** |

### Статус исправлений:
- **FIXED:** 13 проблем (все Tier 1 + 7 новых)
- **ACKNOWLEDGED:** 8 проблем (требуют архитектурных решений)
- **REMAINING:** 24 проблемы (Tier 2-4)

### Тесты: 1846 passed, 0 failed (100% pass rate для unit tests)
