# Дизайн: Генератор анкеты и валидация тестов

**Дата:** 2026-02-03
**Статус:** Готов к реализации

---

## Проблема

После консультации анкета заполняется фрагментами диалога вместо структурированных данных. Нужен механизм:
1. Извлечения чистых данных из диалога
2. Генерации человекочитаемой анкеты (Markdown)
3. Валидации результатов тестов

---

## Решение

### Архитектура

```
src/
├── anketa/                          # Новый модуль
│   ├── __init__.py
│   ├── schema.py                    # FinalAnketa (Pydantic)
│   ├── extractor.py                 # LLM-экстракция данных
│   └── generator.py                 # Генерация Markdown/JSON
│
tests/
└── simulation/
    ├── validator.py                 # Новый: валидация результатов
    └── reporter.py                  # Обновлённый
```

### Поток данных

```
ConsultantInterviewer.run()
    ↓
dialogue_history + business_analysis + proposed_solution
    ↓
AnketaExtractor.extract()           # LLM извлекает данные
    ↓
FinalAnketa (Pydantic модель)
    ↓
AnketaGenerator.to_markdown()       # Генерация документа
    ↓
output/anketas/vitalbox_2026-02-03.md
```

---

## Компоненты

### 1. FinalAnketa (schema.py)

```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class AgentFunction(BaseModel):
    """Функция голосового агента."""
    name: str
    description: str
    priority: str = "medium"  # high, medium, low


class Integration(BaseModel):
    """Интеграция с внешней системой."""
    name: str
    purpose: str
    required: bool = True


class FinalAnketa(BaseModel):
    """Полная анкета для создания голосового агента."""

    # === КОМПАНИЯ ===
    company_name: str
    industry: str
    specialization: str
    website: Optional[str] = None
    contact_name: str
    contact_role: str

    # === БИЗНЕС-КОНТЕКСТ ===
    business_description: str
    services: List[str]
    client_types: List[str]
    current_problems: List[str]
    business_goals: List[str]
    constraints: List[str]

    # === ГОЛОСОВОЙ АГЕНТ ===
    agent_name: str
    agent_purpose: str
    agent_functions: List[AgentFunction]
    typical_questions: List[str]

    # === ПАРАМЕТРЫ ===
    voice_gender: str              # "female" / "male"
    voice_tone: str                # "professional", "friendly", "calm"
    language: str = "ru"
    call_direction: str            # "inbound" / "outbound" / "both"

    # === ИНТЕГРАЦИИ ===
    integrations: List[Integration]

    # === ПРЕДЛОЖЕННОЕ РЕШЕНИЕ ===
    main_function: AgentFunction
    additional_functions: List[AgentFunction]

    # === МЕТАДАННЫЕ ===
    created_at: datetime
    consultation_duration_seconds: float

    def completion_rate(self) -> float:
        """Процент заполненных полей."""
        fields = self.model_dump()
        filled = sum(1 for v in fields.values() if v)
        return filled / len(fields) * 100
```

### 2. AnketaExtractor (extractor.py)

```python
class AnketaExtractor:
    """Извлекает структурированные данные из диалога через LLM."""

    def __init__(self, llm: DeepSeekClient):
        self.llm = llm

    async def extract(
        self,
        dialogue_history: List[Dict],
        business_analysis: BusinessAnalysis,
        proposed_solution: ProposedSolution,
        duration_seconds: float
    ) -> FinalAnketa:
        """
        Извлекает данные из всех источников.

        Args:
            dialogue_history: История диалога
            business_analysis: Результат анализа бизнеса
            proposed_solution: Предложенное решение
            duration_seconds: Длительность консультации

        Returns:
            Заполненная анкета
        """
        prompt = self._build_extraction_prompt(
            dialogue_history,
            business_analysis,
            proposed_solution
        )

        response = await self.llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            response_model=FinalAnketa,
            temperature=0.1  # Низкая температура для точности
        )

        # Добавляем метаданные
        response.created_at = datetime.now()
        response.consultation_duration_seconds = duration_seconds

        return response

    def _build_extraction_prompt(
        self,
        dialogue: List[Dict],
        analysis: BusinessAnalysis,
        solution: ProposedSolution
    ) -> str:
        """Строит промпт для извлечения данных."""

        dialogue_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in dialogue
        ])

        return f"""Извлеки структурированные данные из консультации.

ВАЖНО:
- Извлекай конкретные значения, НЕ копируй фразы целиком
- Для списков указывай краткие пункты
- Если данные не упомянуты — оставь пустым или null

---

ДИАЛОГ КОНСУЛЬТАЦИИ:
{dialogue_text}

---

АНАЛИЗ БИЗНЕСА:
Компания: {analysis.company_name}
Отрасль: {analysis.industry}
Болевые точки: {[p.description for p in analysis.pain_points]}
Возможности: {[o.description for o in analysis.opportunities]}

---

ПРЕДЛОЖЕННОЕ РЕШЕНИЕ:
Основная функция: {solution.main_function.name if solution.main_function else 'N/A'}
Дополнительные: {[f.name for f in solution.additional_functions]}

---

Заполни JSON по схеме FinalAnketa.
Верни ТОЛЬКО валидный JSON без комментариев."""
```

### 3. AnketaGenerator (generator.py)

```python
class AnketaGenerator:
    """Генерирует документы из анкеты."""

    def __init__(self, output_dir: str = "output/anketas"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_markdown(self, anketa: FinalAnketa, filename: Optional[str] = None) -> Path:
        """Генерирует Markdown-документ."""

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = anketa.company_name.lower().replace(" ", "_")
            filename = f"{safe_name}_{timestamp}.md"

        content = self._render_markdown(anketa)
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return filepath

    def to_json(self, anketa: FinalAnketa, filename: Optional[str] = None) -> Path:
        """Сохраняет как JSON."""

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = anketa.company_name.lower().replace(" ", "_")
            filename = f"{safe_name}_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(anketa.model_dump_json(indent=2, ensure_ascii=False))

        return filepath

    def _render_markdown(self, anketa: FinalAnketa) -> str:
        """Рендерит Markdown из анкеты."""

        return f"""# Анкета: {anketa.company_name}

**Дата создания:** {anketa.created_at.strftime('%Y-%m-%d %H:%M')}
**Длительность консультации:** {anketa.consultation_duration_seconds:.0f} сек

---

## 1. Информация о компании

| Поле | Значение |
|------|----------|
| Компания | {anketa.company_name} |
| Отрасль | {anketa.industry} |
| Специализация | {anketa.specialization} |
| Сайт | {anketa.website or '—'} |
| Контактное лицо | {anketa.contact_name} |
| Должность | {anketa.contact_role} |

### Описание бизнеса

{anketa.business_description}

### Услуги/продукты

{self._render_list(anketa.services)}

### Типы клиентов

{self._render_list(anketa.client_types)}

---

## 2. Бизнес-контекст

### Текущие проблемы

{self._render_list(anketa.current_problems)}

### Цели автоматизации

{self._render_list(anketa.business_goals)}

### Ограничения

{self._render_list(anketa.constraints)}

---

## 3. Голосовой агент

| Параметр | Значение |
|----------|----------|
| Имя агента | {anketa.agent_name} |
| Назначение | {anketa.agent_purpose} |
| Голос | {anketa.voice_gender}, {anketa.voice_tone} |
| Язык | {anketa.language} |
| Тип звонков | {anketa.call_direction} |

### Основная функция

**{anketa.main_function.name}**

{anketa.main_function.description}

### Дополнительные функции

{self._render_functions(anketa.additional_functions)}

### Типичные вопросы (FAQ)

{self._render_list(anketa.typical_questions)}

---

## 4. Интеграции

{self._render_integrations(anketa.integrations)}

---

## 5. Все функции агента

{self._render_functions(anketa.agent_functions)}

---

*Сгенерировано автоматически системой ConsultantInterviewer*
"""

    def _render_list(self, items: List[str]) -> str:
        if not items:
            return "*Не указано*"
        return "\n".join(f"- {item}" for item in items)

    def _render_functions(self, functions: List[AgentFunction]) -> str:
        if not functions:
            return "*Не указано*"
        lines = []
        for f in functions:
            lines.append(f"**{f.name}** ({f.priority})")
            lines.append(f"  {f.description}")
            lines.append("")
        return "\n".join(lines)

    def _render_integrations(self, integrations: List[Integration]) -> str:
        if not integrations:
            return "*Не указано*"
        lines = []
        for i in integrations:
            req = "обязательно" if i.required else "опционально"
            lines.append(f"- **{i.name}** ({req}): {i.purpose}")
        return "\n".join(lines)
```

### 4. TestValidator (validator.py)

```python
@dataclass
class ValidationResult:
    """Результат валидации теста."""
    passed: bool
    checks: List[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]
    score: float  # 0-100


class TestValidator:
    """Валидирует результаты тестов консультации."""

    def validate(
        self,
        result: TestResult,
        scenario: Dict[str, Any],  # Из YAML
        anketa: FinalAnketa
    ) -> ValidationResult:
        """
        Выполняет все проверки.

        Проверки:
        1. Заполненность полей
        2. Качество данных
        3. Соответствие сценарию
        4. Прохождение всех фаз
        5. Отсутствие зацикливания
        6. Метрики в пределах нормы
        """
        checks = []
        errors = []
        warnings = []

        # 1. Заполненность
        checks.append(self._check_completeness(anketa))

        # 2. Качество данных
        checks.append(self._check_data_quality(anketa))

        # 3. Соответствие сценарию
        checks.append(self._check_scenario_match(anketa, scenario))

        # 4. Прохождение фаз
        checks.append(self._check_phases(result))

        # 5. Зацикливание
        checks.append(self._check_no_loops(result))

        # 6. Метрики
        checks.append(self._check_metrics(result))

        # Собираем ошибки и предупреждения
        for check in checks:
            if check.get('status') == 'error':
                errors.append(check['message'])
            elif check.get('status') == 'warning':
                warnings.append(check['message'])

        # Считаем score
        passed_checks = sum(1 for c in checks if c['status'] == 'ok')
        score = (passed_checks / len(checks)) * 100

        return ValidationResult(
            passed=len(errors) == 0,
            checks=checks,
            errors=errors,
            warnings=warnings,
            score=score
        )

    def _check_completeness(self, anketa: FinalAnketa) -> Dict:
        """Проверка заполненности обязательных полей."""
        required = [
            'company_name', 'industry', 'agent_name',
            'agent_purpose', 'main_function'
        ]
        missing = [f for f in required if not getattr(anketa, f, None)]

        if missing:
            return {
                'name': 'completeness',
                'status': 'error',
                'message': f"Не заполнены обязательные поля: {missing}"
            }
        return {'name': 'completeness', 'status': 'ok'}

    def _check_data_quality(self, anketa: FinalAnketa) -> Dict:
        """Проверка качества данных (не мусор)."""
        issues = []

        # Проверяем что название компании не содержит диалог
        if len(anketa.company_name) > 100:
            issues.append("company_name слишком длинное")

        # Проверяем что цель агента осмысленная
        if anketa.agent_purpose and len(anketa.agent_purpose) > 500:
            issues.append("agent_purpose похоже на кусок диалога")

        if issues:
            return {
                'name': 'data_quality',
                'status': 'warning',
                'message': f"Проблемы с качеством: {issues}"
            }
        return {'name': 'data_quality', 'status': 'ok'}

    def _check_scenario_match(self, anketa: FinalAnketa, scenario: Dict) -> Dict:
        """Проверка соответствия YAML-сценарию."""
        persona = scenario.get('persona', {})
        issues = []

        # Проверяем компанию
        expected_company = persona.get('company', '').lower()
        if expected_company and expected_company not in anketa.company_name.lower():
            issues.append(f"Компания не совпадает: ожидали '{expected_company}'")

        # Проверяем отрасль
        expected_industry = persona.get('industry', '').lower()
        if expected_industry and expected_industry not in anketa.industry.lower():
            issues.append(f"Отрасль не совпадает: ожидали '{expected_industry}'")

        if issues:
            return {
                'name': 'scenario_match',
                'status': 'error',
                'message': "; ".join(issues)
            }
        return {'name': 'scenario_match', 'status': 'ok'}

    def _check_phases(self, result: TestResult) -> Dict:
        """Проверка прохождения всех фаз."""
        required_phases = ['discovery', 'analysis', 'proposal', 'refinement']
        missing = [p for p in required_phases if p not in result.phases_completed]

        if missing:
            return {
                'name': 'phases',
                'status': 'error',
                'message': f"Не пройдены фазы: {missing}"
            }
        return {'name': 'phases', 'status': 'ok'}

    def _check_no_loops(self, result: TestResult) -> Dict:
        """Проверка отсутствия зацикливания в диалоге."""
        if not result.dialogue_history:
            return {'name': 'no_loops', 'status': 'ok'}

        # Ищем повторяющиеся сообщения
        messages = [m.get('content', '')[:100] for m in result.dialogue_history]
        duplicates = len(messages) - len(set(messages))

        if duplicates > 5:
            return {
                'name': 'no_loops',
                'status': 'warning',
                'message': f"Обнаружено {duplicates} повторяющихся сообщений"
            }
        return {'name': 'no_loops', 'status': 'ok'}

    def _check_metrics(self, result: TestResult) -> Dict:
        """Проверка метрик в разумных пределах."""
        issues = []

        if result.turn_count > 50:
            issues.append(f"Слишком много ходов: {result.turn_count}")

        if result.duration_seconds > 600:  # 10 минут
            issues.append(f"Слишком долго: {result.duration_seconds:.0f} сек")

        if issues:
            return {
                'name': 'metrics',
                'status': 'warning',
                'message': "; ".join(issues)
            }
        return {'name': 'metrics', 'status': 'ok'}
```

---

## Интеграция

### В ConsultantInterviewer

```python
# src/consultant/interviewer.py

async def run(self) -> Dict[str, Any]:
    # ... существующая логика ...

    # После завершения всех фаз
    if self.phase == ConsultantPhase.COMPLETED:
        # Генерируем финальную анкету
        extractor = AnketaExtractor(self.llm)
        anketa = await extractor.extract(
            dialogue_history=self.dialogue_history,
            business_analysis=self.business_analysis,
            proposed_solution=self.proposed_solution,
            duration_seconds=self.duration_seconds
        )

        # Сохраняем
        generator = AnketaGenerator()
        md_path = generator.to_markdown(anketa)
        json_path = generator.to_json(anketa)

        console.print(f"[green]Анкета сохранена:[/green] {md_path}")

        return {
            'status': 'completed',
            'anketa': anketa,
            'files': {'markdown': md_path, 'json': json_path}
        }
```

### В тестах

```python
# tests/simulation/runner.py

async def run(self, scenario_name: str = "test") -> TestResult:
    # ... существующая логика ...

    # После завершения
    if self.interviewer:
        # Извлекаем анкету
        extractor = AnketaExtractor(DeepSeekClient())
        anketa = await extractor.extract(...)

        # Валидируем
        validator = TestValidator()
        validation = validator.validate(
            result=test_result,
            scenario=self.client.scenario,
            anketa=anketa
        )

        test_result.anketa = anketa.model_dump()
        test_result.validation = validation

    return test_result
```

---

## Пример вывода (Markdown)

```markdown
# Анкета: Vitalbox

**Дата создания:** 2026-02-03 12:30
**Длительность консультации:** 482 сек

---

## 1. Информация о компании

| Поле | Значение |
|------|----------|
| Компания | Vitalbox |
| Отрасль | Wellness / Услуги для населения |
| Специализация | Сеть массажных боксов "массаж за 15 минут" |
| Контактное лицо | Алексей Петров |
| Должность | Руководитель отдела развития |

### Текущие проблемы

- Менеджеры не успевают обрабатывать 15-30 звонков в день
- Много времени на ответы на типовые вопросы
- Путаница между звонками клиентов и партнёров

---

## 3. Голосовой агент

| Параметр | Значение |
|----------|----------|
| Имя агента | Анна |
| Назначение | Квалификация франчайзи и обработка входящих |
| Голос | female, professional |
| Тип звонков | inbound |

### Основная функция

**Квалификация партнёров**

Определение цели звонка, сбор данных (город, бюджет, опыт),
отправка PDF-гида, запись обратного звонка менеджера.

---

## 4. Интеграции

- **Google Таблицы** (обязательно): Сохранение данных лидов
- **Telegram** (обязательно): Уведомления менеджерам
- **Email** (опционально): Отправка PDF-гида
```

---

## План реализации

1. **Создать `src/anketa/schema.py`** — Pydantic модели
2. **Создать `src/anketa/extractor.py`** — LLM-экстракция
3. **Создать `src/anketa/generator.py`** — Markdown/JSON генерация
4. **Создать `tests/simulation/validator.py`** — Валидация
5. **Обновить `ConsultantInterviewer`** — интеграция генератора
6. **Обновить `TestReporter`** — использование генератора
7. **Запустить тест** — проверка на сценарии Vitalbox
