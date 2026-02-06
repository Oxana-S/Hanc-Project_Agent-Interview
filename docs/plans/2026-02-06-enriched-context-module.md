# План доработки модуля обогащения контекста

**Дата:** 2026-02-06
**Версия:** 1.0
**Статус:** Approved

## Обзор

Полная доработка модуля обогащения контекста для закрытия 12 выявленных пробелов.

### Выявленные пробелы

| # | Критичность | Пробел | Файл |
|---|-------------|--------|------|
| 1 | 🔴 Critical | Learnings НЕ включены в контекст | `context_builder.py:109-120` |
| 2 | 🔴 Critical | `get_enriched_context()` нигде не вызывается | `interviewer.py:1189` |
| 3 | 🔴 Critical | Document context НЕ используется в фазах | `interviewer.py` |
| 4 | 🔴 Critical | Voice Agent НЕ использует Knowledge Base | `voice/consultant.py` |
| 5 | 🟠 Medium | Refinement phase не использует KB context | `interviewer.py:733-841` |
| 6 | 🟠 Medium | Нет механизма записи успешных кейсов | `manager.py` |
| 7 | 🟠 Medium | usage_stats в _index.yaml не обновляются | `_index.yaml:62-66` |
| 8 | 🟠 Medium | Нет валидации полноты профилей | — |
| 9 | 🟡 Low | Нет приоритизации данных из документов | `analyzer.py` |
| 10 | 🟡 Low | Контекст одинаковый для всех клиентов | `context_builder.py` |
| 11 | 🟡 Low | Нет кеширования загруженных профилей | `loader.py` |
| 12 | 🟡 Low | industry_specifics не используется | `models.py:115` |

---

## Задача 1: EnrichedContextBuilder

**Пробелы:** #1, #2, #3, #10

### Описание
Создать новый класс `EnrichedContextBuilder`, который объединяет все источники контекста:
- Knowledge Base (профили отраслей)
- Documents (документы клиента)
- Learnings (накопленный опыт)

### Файлы
- `src/knowledge/enriched_builder.py` — новый файл

### Интерфейс

```python
class EnrichedContextBuilder:
    """
    Unified context builder combining KB, Documents, and Learnings.
    """

    def __init__(
        self,
        knowledge_manager: IndustryKnowledgeManager,
        document_context: Optional[DocumentContext] = None
    ):
        self.kb_manager = knowledge_manager
        self.doc_context = document_context
        self._kb_builder = KBContextBuilder()

    def build_for_phase(
        self,
        phase: str,
        dialogue_history: List[Dict],
        industry_profile: Optional[IndustryProfile] = None
    ) -> str:
        """
        Build enriched context for a consultation phase.

        Args:
            phase: discovery, analysis, proposal, refinement
            dialogue_history: Current dialogue
            industry_profile: Pre-detected industry profile

        Returns:
            Formatted context string for prompt injection
        """

    def build_for_voice(
        self,
        dialogue_history: List[Dict]
    ) -> str:
        """
        Build compact context for voice agent.

        Returns shorter context optimized for voice interactions.
        """

    def _include_learnings(
        self,
        profile: IndustryProfile,
        max_learnings: int = 5
    ) -> str:
        """Include recent learnings in context."""

    def _include_documents(self) -> str:
        """Include document context if available."""

    def _prioritize_by_dialogue(
        self,
        context: str,
        dialogue_history: List[Dict]
    ) -> str:
        """Filter context by relevance to dialogue."""
```

### Критерии готовности
- [ ] Контекст включает learnings из профиля
- [ ] Контекст включает данные из документов клиента
- [ ] Контекст фильтруется по релевантности диалогу
- [ ] Метод `build_for_voice()` возвращает компактный контекст

---

## Задача 2: Интеграция в ConsultantInterviewer

**Пробелы:** #2, #3, #5

### Описание
Заменить разрозненные вызовы `_get_kb_context()` на единый `EnrichedContextBuilder`.

### Файлы
- `src/consultant/interviewer.py`

### Изменения

```python
# В __init__():
self.context_builder = EnrichedContextBuilder(
    self.knowledge_manager,
    self.document_context
)

# В _discovery_phase() строка ~348:
# Было:
kb_context = self._get_kb_context("discovery")

# Стало:
enriched_context = self.context_builder.build_for_phase(
    "discovery",
    self.dialogue_history,
    self.industry_profile
)

# В _analysis_phase() строка ~453:
# Аналогично

# В _proposal_phase() строка ~641:
# Аналогично

# В _refinement_phase() строка ~733:
# ДОБАВИТЬ (сейчас отсутствует):
enriched_context = self.context_builder.build_for_phase(
    "refinement",
    self.dialogue_history,
    self.industry_profile
)
```

### Удалить мёртвый код
- `get_enriched_context()` — строка 1189
- `get_document_context()` — строка 1177

### Критерии готовности
- [ ] Все 4 фазы используют EnrichedContextBuilder
- [ ] Мёртвый код удалён
- [ ] Refinement phase получает KB контекст для подсказок

---

## Задача 3: Интеграция в Voice Agent

**Пробел:** #4

### Описание
Добавить отраслевой контекст в голосовой агент.

### Файлы
- `src/voice/consultant.py`

### Изменения

```python
# Добавить импорты
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder

# Новая функция
def get_enriched_system_prompt(dialogue_history: List[Dict]) -> str:
    """
    Get system prompt with industry context.

    Detects industry from dialogue and enriches prompt.
    """
    base_prompt = get_prompt("voice/consultant", "system_prompt")

    if len(dialogue_history) < 2:
        return base_prompt

    manager = IndustryKnowledgeManager()
    builder = EnrichedContextBuilder(manager)

    voice_context = builder.build_for_voice(dialogue_history)

    if voice_context:
        return f"{base_prompt}\n\n{voice_context}"
    return base_prompt

# В entrypoint() — обновлять промпт каждые N сообщений
# См. существующую логику periodic extraction
```

### Критерии готовности
- [ ] Voice agent получает отраслевой контекст
- [ ] Контекст обновляется по мере накопления диалога
- [ ] Контекст компактный (оптимизирован для голоса)

---

## Задача 4: Feedback Loop

**Пробел:** #6

### Описание
Добавить механизм записи успешных паттернов, не только ошибок.

### Файлы
- `src/knowledge/manager.py`

### Изменения

```python
def record_success(
    self,
    industry_id: str,
    pattern: str,
    source: str
):
    """
    Record a successful pattern.

    Args:
        industry_id: Industry ID
        pattern: What worked well
        source: Session ID or test name
    """
    self.record_learning(
        industry_id,
        f"[SUCCESS] {pattern}",
        source
    )

def get_recent_learnings(
    self,
    industry_id: str,
    limit: int = 10,
    include_success: bool = True
) -> List[Learning]:
    """
    Get recent learnings for industry.

    Args:
        industry_id: Industry ID
        limit: Max learnings to return
        include_success: Include [SUCCESS] tagged learnings

    Returns:
        List of Learning objects, newest first
    """
```

### Вызовы
- В `_refinement_phase()` — когда completion_rate > 80%
- В `finalize_consultation()` — при успешном завершении

### Критерии готовности
- [ ] Метод `record_success()` реализован
- [ ] Успешные кейсы записываются с тегом [SUCCESS]
- [ ] Метод `get_recent_learnings()` возвращает последние записи

---

## Задача 5: Usage Stats

**Пробел:** #7

### Описание
Обновлять статистику использования отраслей в _index.yaml.

### Файлы
- `src/knowledge/manager.py`
- `src/knowledge/loader.py`

### Изменения

```python
# В manager.py
def increment_usage(self, industry_id: str):
    """Increment usage counter for industry."""
    self.loader.increment_usage_stats(industry_id)

# В loader.py
def increment_usage_stats(self, industry_id: str):
    """Update usage stats in _index.yaml."""
    index_path = self._config_dir / "_index.yaml"
    # Load, update, save
```

### Структура _index.yaml

```yaml
usage_stats:
  total_tests: 15
  last_test_date: "2026-02-06"
  most_used_industry: "automotive"
  industry_usage:
    automotive: 5
    logistics: 4
    medical: 3
```

### Критерии готовности
- [ ] Счётчик обновляется при детекции отрасли
- [ ] _index.yaml содержит актуальную статистику

---

## Задача 6: Валидатор профилей

**Пробел:** #8

### Описание
Создать валидатор полноты профилей отраслей.

### Файлы
- `src/knowledge/validator.py` — новый файл

### Интерфейс

```python
@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    completeness_score: float  # 0.0 - 1.0


class ProfileValidator:
    """Validates industry profile completeness."""

    REQUIRED_FIELDS = ['pain_points', 'typical_services', 'recommended_functions']
    MIN_ITEMS = {
        'pain_points': 3,
        'typical_services': 5,
        'recommended_functions': 3,
        'typical_integrations': 2,
        'industry_faq': 3
    }

    def validate(self, profile: IndustryProfile) -> ValidationResult:
        """Validate profile completeness."""

    def validate_all(self, manager: IndustryKnowledgeManager) -> Dict[str, ValidationResult]:
        """Validate all profiles."""
```

### Критерии готовности
- [ ] Валидатор проверяет обязательные поля
- [ ] Возвращает completeness_score
- [ ] Выводит warnings для неполных профилей

---

## Задача 7: Кеширование профилей

**Пробел:** #11

### Описание
Добавить кеширование загруженных профилей.

### Файлы
- `src/knowledge/loader.py`

### Изменения

```python
class IndustryProfileLoader:
    def __init__(self, config_dir: Optional[Path] = None):
        self._config_dir = config_dir or Path("config/industries")
        self._cache: Dict[str, IndustryProfile] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 300  # 5 minutes

    def load_profile(self, industry_id: str) -> Optional[IndustryProfile]:
        """Load profile with caching."""
        now = time.time()

        if industry_id in self._cache:
            if now - self._cache_time[industry_id] < self._cache_ttl:
                return self._cache[industry_id]

        profile = self._load_from_file(industry_id)
        if profile:
            self._cache[industry_id] = profile
            self._cache_time[industry_id] = now

        return profile

    def invalidate_cache(self, industry_id: Optional[str] = None):
        """Invalidate cache for industry or all."""
```

### Критерии готовности
- [ ] Профили кешируются в памяти
- [ ] TTL 5 минут
- [ ] Метод invalidate_cache() для сброса

---

## Задача 8: Industry Specifics

**Пробел:** #12

### Описание
Использовать поле `industry_specifics` в контексте.

### Файлы
- `src/knowledge/context_builder.py`
- `config/consultant/kb_context.yaml`

### Изменения

```python
# В context_builder.py _get_profile_data():
key_mapping = {
    # ... existing
    'industry_specifics': profile.industry_specifics,
}

# В kb_context.yaml добавить:
sections:
  discovery:
    blocks:
      - key: industry_specifics
        label: "Специфика отрасли"
        format: specifics_list
```

### Критерии готовности
- [ ] industry_specifics включено в контекст
- [ ] Форматируется корректно (compliance, tone, peak_times)

---

## Задача 9: Тесты

### Файлы
- `tests/unit/test_enriched_context.py` — новый файл

### Тесты

```python
class TestEnrichedContextBuilder:
    """Tests for EnrichedContextBuilder."""

    def test_build_for_discovery_phase(self):
        """Context for discovery includes pain_points and services."""

    def test_build_for_analysis_phase(self):
        """Context for analysis includes integrations."""

    def test_build_for_proposal_phase(self):
        """Context for proposal includes recommended_functions."""

    def test_build_for_refinement_phase(self):
        """Context for refinement includes FAQ and objections."""

    def test_includes_learnings(self):
        """Learnings are included in context."""

    def test_includes_document_context(self):
        """Document context is included."""

    def test_build_for_voice(self):
        """Compact context for voice mode."""

    def test_prioritize_by_dialogue(self):
        """Context filtered by dialogue relevance."""


class TestProfileValidator:
    """Tests for profile validator."""

    def test_validate_complete_profile(self):
        """Complete profile passes validation."""

    def test_validate_incomplete_profile(self):
        """Incomplete profile returns warnings."""

    def test_completeness_score(self):
        """Score calculation is correct."""


class TestFeedbackLoop:
    """Tests for feedback loop."""

    def test_record_success(self):
        """Success patterns are recorded."""

    def test_increment_usage(self):
        """Usage counter is updated."""

    def test_get_recent_learnings(self):
        """Recent learnings are retrieved."""


class TestProfileCaching:
    """Tests for profile caching."""

    def test_cache_hit(self):
        """Cached profile is returned."""

    def test_cache_expiry(self):
        """Expired cache triggers reload."""

    def test_invalidate_cache(self):
        """Cache invalidation works."""
```

### Критерии готовности
- [ ] Покрытие EnrichedContextBuilder ≥90%
- [ ] Покрытие ProfileValidator ≥90%
- [ ] Все тесты проходят

---

## Задача 10: Обновление TESTING.md

### Файлы
- `docs/TESTING.md`

### Добавить секцию

```markdown
## Этап 7: Модуль обогащения контекста

### 7.1 Проверка Knowledge Base

```bash
# Валидация всех профилей отраслей
python -c "
from src.knowledge import IndustryKnowledgeManager
from src.knowledge.validator import ProfileValidator

manager = IndustryKnowledgeManager()
validator = ProfileValidator()

for industry_id in manager.get_all_industries():
    profile = manager.get_profile(industry_id)
    result = validator.validate(profile)
    status = '✅' if result.is_valid else '⚠️'
    print(f'{status} {industry_id}: {result.completeness_score:.0%}')
    for w in result.warnings:
        print(f'   └─ {w}')
"
```

### 7.2 Проверка EnrichedContextBuilder

```bash
# Тест генерации контекста для всех фаз
python -c "
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder

manager = IndustryKnowledgeManager()
builder = EnrichedContextBuilder(manager)

dialogue = [{'role': 'user', 'content': 'Мы автосервис, занимаемся ремонтом машин'}]

for phase in ['discovery', 'analysis', 'proposal', 'refinement']:
    context = builder.build_for_phase(phase, dialogue)
    has_learnings = 'learnings' in context.lower() or '[SUCCESS]' in context
    print(f'{phase}: {len(context)} chars, learnings: {has_learnings}')
"
```

### 7.3 Проверка Voice интеграции

```bash
# Проверка что Voice Agent получает отраслевой контекст
python -c "
from src.voice.consultant import get_enriched_system_prompt

dialogue = [
    {'role': 'assistant', 'content': 'Здравствуйте! Расскажите о вашем бизнесе.'},
    {'role': 'user', 'content': 'У нас клиника, записываем пациентов на приём'}
]

prompt = get_enriched_system_prompt(dialogue)
print(f'Prompt length: {len(prompt)} chars')
has_context = 'medical' in prompt.lower() or 'клиника' in prompt.lower()
print(f'Contains industry context: {has_context}')
"
```

### 7.4 Сводная таблица

| Проверка | Критерий |
|----------|----------|
| Профили валидны | Все профили ≥70% completeness |
| Контекст генерируется | Все 4 фазы возвращают непустой контекст |
| Learnings включены | Контекст содержит накопленный опыт |
| Voice интеграция | Голосовой агент получает отраслевой контекст |
```

### Обновить таблицу обзора

В начале TESTING.md добавить строку:

```markdown
| 7. Обогащение контекста | Knowledge Base, Documents, Learnings | python scripts | Профили валидны, контекст генерируется |
```

### Критерии готовности
- [ ] Секция "Этап 7" добавлена
- [ ] Таблица обзора обновлена
- [ ] Скрипты проверки работают

---

## Порядок реализации

1. **Задача 6** — ProfileValidator (независимый модуль)
2. **Задача 7** — Кеширование (независимый модуль)
3. **Задача 1** — EnrichedContextBuilder (зависит от существующих модулей)
4. **Задача 4** — Feedback Loop (расширение manager.py)
5. **Задача 5** — Usage Stats (расширение loader.py)
6. **Задача 8** — Industry Specifics (расширение context_builder.py)
7. **Задача 2** — Интеграция в Interviewer (зависит от Задачи 1)
8. **Задача 3** — Интеграция в Voice (зависит от Задачи 1)
9. **Задача 9** — Тесты (после реализации)
10. **Задача 10** — TESTING.md (после тестов)

---

## Файлы для изменения

| Файл | Действие |
|------|----------|
| `src/knowledge/enriched_builder.py` | Создать |
| `src/knowledge/validator.py` | Создать |
| `src/knowledge/manager.py` | Изменить |
| `src/knowledge/loader.py` | Изменить |
| `src/knowledge/context_builder.py` | Изменить |
| `src/knowledge/__init__.py` | Изменить (экспорты) |
| `src/consultant/interviewer.py` | Изменить |
| `src/voice/consultant.py` | Изменить |
| `config/consultant/kb_context.yaml` | Изменить |
| `tests/unit/test_enriched_context.py` | Создать |
| `docs/TESTING.md` | Изменить |

---

## Критерии завершения

- [ ] Все 12 пробелов закрыты
- [ ] Все тесты проходят
- [ ] Покрытие модуля knowledge ≥80%
- [ ] TESTING.md содержит Этап 7
- [ ] Документация актуальна
