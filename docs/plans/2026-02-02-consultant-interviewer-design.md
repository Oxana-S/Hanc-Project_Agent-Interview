# Design: ConsultantInterviewer v3.0

**Дата:** 2026-02-02
**Статус:** Approved
**Автор:** AI Team + Sergio

---

## Резюме

Полный редизайн Voice Interviewer Agent — переход от "опросника" к "AI-консультанту" с:
- 4 фазами консультации (DISCOVERY → ANALYSIS → PROPOSAL → REFINEMENT)
- Research Engine для внешних данных (web search, RAG, website parser)
- Голосовым интерфейсом (LiveKit + Azure OpenAI Realtime)
- Фиксированной структурой анкеты с расширениями

---

## Принятые решения

| # | Вопрос | Решение |
|---|--------|---------|
| 1 | Интеграция новых фаз | **B.** Новый класс ConsultantInterviewer (с нуля) |
| 2 | Фаза ANALYSIS | **B.** Явная фаза с валидацией пользователем |
| 3 | Формат PROPOSAL | **A.** Структурированное предложение (один блок) |
| 4 | Характер AI | **A.** Эксперт-советник (уверенный, с примерами) |
| 5 | Расширения анкеты | **A.** Поле `extended_data` в каждом AnketaField |
| 6 | Голосовая архитектура | **A.** LiveKit + Azure OpenAI Realtime (полный стек) |
| 7 | Клиентский интерфейс | **A.** Web UI для MVP |
| 8 | Внешние данные | **D.** Всё: Web Search + RAG + Website Parser |
| 9 | Хранение промптов | **A.** YAML файлы (вне кода) |

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    VOICE INTERVIEWER v3.0                        │
│                      AI-Консультант                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   WEB UI     │    │   CLI UI     │    │  (Future)    │       │
│  │  (LiveKit)   │    │   (Rich)     │    │   SIP/Mobile │       │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┘       │
│         │                   │                                    │
│         └─────────┬─────────┘                                    │
│                   ▼                                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              ConsultantInterviewer                       │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐   │    │
│  │  │DISCOVERY│→ │ANALYSIS │→ │PROPOSAL │→ │REFINEMENT │   │    │
│  │  └─────────┘  └─────────┘  └─────────┘  └───────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                   │                                              │
│         ┌─────────┼─────────┬─────────┐                          │
│         ▼         ▼         ▼         ▼                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ DeepSeek │ │  Azure   │ │ LiveKit  │ │ Research │            │
│  │(reasoning)│ │(STT/TTS) │ │(WebRTC)  │ │ Engine   │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│                                                                  │
│  ┌──────────────────────────────────────┐                       │
│  │     CollectedInfo + Extensions       │                       │
│  │  ┌─────────┐  ┌─────────────────┐    │                       │
│  │  │ANKETA   │  │ extended_data   │    │                       │
│  │  │(fixed)  │  │ (per field)     │    │                       │
│  │  └─────────┘  └─────────────────┘    │                       │
│  └──────────────────────────────────────┘                       │
│         │                                                        │
│    ┌────┴────┐                                                   │
│    ▼         ▼                                                   │
│ [Redis]  [PostgreSQL]                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Четыре фазы консультации

### Фаза 1: DISCOVERY (5-15 минут)

**Цель:** Понять бизнес через свободный диалог

**Поведение AI (эксперт-советник):**
- Задаёт открытые вопросы о бизнесе
- Приводит примеры из отрасли
- Предлагает идеи по ходу разговора
- Фоново извлекает данные в CollectedInfo

**Триггеры перехода:**
- Минимум 5 ходов диалога
- Заполнено 30%+ ключевых полей
- ИЛИ пользователь сказал "достаточно"

---

### Фаза 2: ANALYSIS (1-2 минуты)

**Цель:** Показать понимание и получить подтверждение

**AI формирует и показывает:**
- `business_profile`: отрасль, масштаб, специфика
- `pain_points`: выявленные боли (3-5 пунктов)
- `opportunities`: возможности автоматизации
- `constraints`: ограничения (бюджет, системы)

**Research Engine активируется:**
- Парсинг сайта клиента (если указан)
- Web search по отрасли
- Поиск похожих кейсов в RAG

**Действия пользователя:**
- Подтверждает: "Да, всё верно"
- Корректирует: "Нет, боль X важнее Y"
- Дополняет: "Ещё забыл сказать..."

**Триггер перехода:** Явное подтверждение пользователя

---

### Фаза 3: PROPOSAL (3-5 минут)

**Цель:** Предложить оптимальное решение

**Формат структурированного предложения:**
```
"На основе анализа рекомендую:

1. ОСНОВНАЯ ФУНКЦИЯ: [X]
   Почему: [связь с болью клиента]

2. ДОПОЛНИТЕЛЬНО:
   • [функция A] — [зачем]
   • [функция B] — [зачем]

3. ИНТЕГРАЦИИ:
   ✓ [нужная] — [для чего]
   ✗ [не нужная] — [почему не сейчас]

4. ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
   [метрики из исследования]

Согласны? Что хотите изменить?"
```

**Диалог:** обсуждение и корректировка предложения

**Триггер перехода:** Пользователь согласен с решением

---

### Фаза 4: REFINEMENT (5-10 минут)

**Цель:** Заполнить все поля фиксированной анкеты

**Поведение AI:**
- Показывает что уже заполнено (из предыдущих фаз)
- Задаёт точечные вопросы по пустым полям
- Предлагает значения на основе контекста
- Собирает extended_data для отрасли

**Пример:**
```
"Почти всё готово! Уточним детали:
 1. Email для уведомлений? → [ввод]
 2. Часы работы агента? → [предложение: 9-21]
 3. Имя агента? → [предложение: Алекс]"
```

**Триггер завершения:** Все REQUIRED поля заполнены

**Результат:** Полная анкета + extended_data

---

## Research Engine

```
┌──────────────────────────────────────────────────────────────────┐
│                      RESEARCH ENGINE                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ WEB SEARCH   │  │  RAG BASE    │  │WEBSITE PARSER│            │
│  │              │  │              │  │              │            │
│  │ • Bing API   │  │ • Кейсы      │  │ • Услуги     │            │
│  │ • Tavily     │  │ • Шаблоны    │  │ • Цены       │            │
│  │              │  │ • Compliance │  │ • Контакты   │            │
│  │              │  │ • FAQ        │  │ • О компании │            │
│  │              │  │              │  │              │            │
│  │              │  │ Azure        │  │ httpx +      │            │
│  │              │  │ Cognitive    │  │ BeautifulSoup│            │
│  │              │  │ Search       │  │              │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│         └─────────────────┼─────────────────┘                     │
│                           ▼                                       │
│              ┌─────────────────────────┐                          │
│              │   DeepSeek Synthesizer  │                          │
│              │                         │                          │
│              │  • Объединяет данные    │                          │
│              │  • Выделяет релевантное │                          │
│              │  • Формирует insights   │                          │
│              └───────────┬─────────────┘                          │
│                          ▼                                        │
│              ┌─────────────────────────┐                          │
│              │    ResearchResult       │                          │
│              │                         │                          │
│              │  industry_insights: []  │                          │
│              │  competitor_info: []    │                          │
│              │  best_practices: []     │                          │
│              │  compliance_notes: []   │                          │
│              │  website_data: {}       │                          │
│              └─────────────────────────┘                          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

**Триггеры запуска:**
- Клиент назвал компанию/сайт → парсим сайт
- Определена отрасль → ищем тренды и best practices
- Фаза ANALYSIS → комплексное исследование

---

## Модели данных

### AnketaField с расширениями

```python
class AnketaField(BaseModel):
    """Поле анкеты с поддержкой расширений."""

    # === ФИКСИРОВАННАЯ ЧАСТЬ (неизменна) ===
    field_id: str
    name: str
    display_name: str
    description: str
    priority: FieldPriority  # REQUIRED | IMPORTANT | OPTIONAL
    status: FieldStatus = FieldStatus.EMPTY
    value: Any = None

    # === РАСШИРЕНИЯ (гибкая часть) ===
    extended_data: Dict[str, Any] = {}

    # Метаданные
    source: str = ""           # discovery | analysis | proposal | refinement
    confidence: float = 0.0    # 0-1
    research_backed: bool = False
```

### ResearchResult

```python
class ResearchResult(BaseModel):
    """Результат исследования из Research Engine."""

    website_data: Optional[Dict[str, Any]] = None
    industry_insights: List[str] = []
    competitor_info: List[Dict[str, str]] = []
    best_practices: List[str] = []
    compliance_notes: List[str] = []
    similar_cases: List[Dict[str, Any]] = []
    sources_used: List[str] = []
    research_timestamp: datetime
    confidence_score: float = 0.0
```

### CollectedInfo (обновлённый)

```python
class CollectedInfo(BaseModel):
    """Собранная информация с поддержкой исследований."""

    fields: Dict[str, AnketaField] = {}
    research: Optional[ResearchResult] = None
    business_analysis: Optional[BusinessAnalysis] = None
    proposed_solution: Optional[ProposedSolution] = None
    dialogue_history: List[Dict[str, str]] = []
```

---

## Структура YAML конфигурации

```
prompts/
├── consultant/
│   ├── discovery.yaml
│   ├── analysis.yaml
│   ├── proposal.yaml
│   └── refinement.yaml
│
├── research/
│   ├── web_search.yaml
│   ├── website_parser.yaml
│   └── rag_queries.yaml
│
├── analysis/
│   ├── extract_info.yaml
│   ├── business_profile.yaml
│   └── answer_analysis.yaml
│
└── generation/
    ├── anketa.yaml
    └── dialogues.yaml

locales/
├── ru/
│   ├── ui.yaml
│   ├── phases.yaml
│   └── errors.yaml
│
└── en/
    ├── ui.yaml
    ├── phases.yaml
    └── errors.yaml
```

**Принцип:** Вся лексика вынесена из кода. Промпты и тексты — в YAML файлах.

---

## Голосовой интерфейс

### Архитектура

```
Клиент (браузер)
       │ WebRTC
       ▼
LiveKit Cloud (wss://hancai-demo.livekit.cloud)
       │
       ▼
Agent Server (Python)
       │
       ├──► LiveKit Agent SDK (audio I/O)
       ├──► Azure OpenAI Realtime (STT/TTS)
       └──► ConsultantInterviewer (логика)
```

### Credentials (из .env)

| Сервис | Статус |
|--------|--------|
| Azure OpenAI | ✅ gpt-4o-realtime-preview, Sweden Central |
| LiveKit | ✅ Cloud instance (hancai-demo) |
| DeepSeek | ✅ deepseek-reasoner |

### Поток данных

```
Пользователь говорит
    → LiveKit (WebRTC)
    → Agent Server
    → Azure STT (speech → text)
    → ConsultantInterviewer (обработка)
    → DeepSeek (reasoning, если нужен)
    → Azure TTS (text → speech)
    → LiveKit → Браузер
Пользователь слышит ответ
```

---

## Файловая структура (новая)

```
voice_interviewer/
├── src/
│   ├── consultant/              # НОВЫЙ главный модуль
│   │   ├── __init__.py
│   │   ├── interviewer.py       # ConsultantInterviewer
│   │   ├── phases.py            # 4 фазы
│   │   └── models.py            # BusinessAnalysis, ProposedSolution
│   │
│   ├── research/                # НОВЫЙ Research Engine
│   │   ├── __init__.py
│   │   ├── engine.py            # ResearchEngine
│   │   ├── web_search.py        # Bing/Tavily
│   │   ├── website_parser.py    # httpx + BeautifulSoup
│   │   └── rag.py               # Azure Cognitive Search
│   │
│   ├── voice/                   # НОВЫЙ голосовой модуль
│   │   ├── __init__.py
│   │   ├── handler.py           # VoiceHandler
│   │   ├── livekit_client.py    # LiveKit SDK
│   │   └── azure_realtime.py    # Azure OpenAI Realtime
│   │
│   ├── config/                  # НОВЫЙ загрузчик конфигов
│   │   ├── __init__.py
│   │   ├── prompt_loader.py     # Загрузка YAML промптов
│   │   └── locale_loader.py     # Загрузка локализации
│   │
│   ├── interview/               # Существующий (сохраняем)
│   ├── storage/                 # Существующий
│   ├── llm/                     # Существующий
│   └── cli/                     # Существующий
│
├── prompts/                     # НОВЫЙ: YAML промпты
│   ├── consultant/
│   ├── research/
│   └── generation/
│
├── locales/                     # НОВЫЙ: локализация
│   ├── ru/
│   └── en/
│
├── public/                      # НОВЫЙ: Web UI
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
├── scripts/
├── docs/
├── config/
├── tests/
└── ...
```

---

## Следующие шаги

1. **Создать структуру директорий** — prompts/, locales/, src/consultant/, src/research/, src/voice/, public/

2. **Реализовать ConsultantInterviewer** — новый класс с 4 фазами

3. **Создать Research Engine** — web search, website parser, RAG интеграция

4. **Вынести промпты в YAML** — все существующие промпты из кода

5. **Реализовать голосовой интерфейс** — LiveKit + Azure интеграция

6. **Создать Web UI** — минимальный MVP для тестирования голоса

---

## Метрики успеха

| Метрика | Цель |
|---------|------|
| Полнота анкеты | 100% REQUIRED полей |
| Качество данных | 80%+ с примерами |
| Ценность консультации | NPS > 8 |
| Время сессии | 15-30 мин |
| Точность заполнения | < 5% ручных правок |

---

*Документ создан в результате brainstorm-сессии 2026-02-02*
