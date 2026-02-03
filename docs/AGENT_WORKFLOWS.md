# Workflow Агентов

Документ описывает архитектуру и workflow двух независимых агентов проекта.

---

## Содержание

1. [agent_client_simulator — Агент Тестирования](#1-agent_client_simulator--агент-тестирования)
2. [agent_document_reviewer — Агент Ревью Документов](#2-agent_document_reviewer--агент-ревью-документов)
3. [Интегрированный Pipeline: Test → Review](#3-интегрированный-pipeline-test--review)
4. [Примеры Использования](#4-примеры-использования)

---

## 1. agent_client_simulator — Агент Тестирования

### 1.1 Назначение

Автоматическое тестирование ConsultantInterviewer через симуляцию клиента.

### 1.2 Компоненты

```
src/agent_client_simulator/
├── __init__.py           # Публичный API модуля
├── client.py             # SimulatedClient — LLM-симулятор клиента
├── runner.py             # ConsultationTester — оркестратор тестов
├── reporter.py           # TestReporter — генерация отчётов
└── validator.py          # TestValidator — валидация результатов
```

### 1.3 Workflow Схема

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AGENT_TEST_CLIENT                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────┐                                                 │
│  │  YAML Scenario  │  (persona, goals, pain_points, etc.)            │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                 │
│  │ SimulatedClient │                                                 │
│  │                 │  • Загружает персону из YAML                   │
│  │   LLM-клиент    │  • Генерирует ответы через DeepSeek            │
│  │                 │  • Поддерживает историю диалога                 │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ConsultationTester                        │    │
│  │                                                              │    │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────┐          │    │
│  │  │ DISCOVERY  │──▶│  ANALYSIS  │──▶│  PROPOSAL  │──┐       │    │
│  │  │   phase    │   │   phase    │   │   phase    │  │       │    │
│  │  └────────────┘   └────────────┘   └────────────┘  │       │    │
│  │                                                     │       │    │
│  │  ┌────────────┐◀──────────────────────────────────┘       │    │
│  │  │ REFINEMENT │                                            │    │
│  │  │   phase    │                                            │    │
│  │  └─────┬──────┘                                            │    │
│  │        │                                                   │    │
│  └────────┼───────────────────────────────────────────────────┘    │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                 │
│  │  AnketaExtractor│  LLM извлекает структурированные данные        │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                 │
│  │  TestValidator  │  6 проверок:                                   │
│  │                 │  • completeness (обязательные поля)             │
│  │                 │  • data_quality (валидность данных)             │
│  │                 │  • scenario_match (соответствие сценарию)       │
│  │                 │  • phases (все фазы пройдены)                   │
│  │                 │  • no_loops (нет зацикливания)                  │
│  │                 │  • metrics (лимиты ходов/времени)               │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                 │
│  │  TestReporter   │                                                 │
│  │                 │  • Console (Rich)                               │
│  │                 │  • JSON файл                                    │
│  │                 │  • Markdown отчёт                               │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                 │
│  │   TestResult    │  Итоговый объект с:                            │
│  │                 │  • status, duration, turn_count                 │
│  │                 │  • anketa, final_anketa                         │
│  │                 │  • validation, errors                           │
│  └─────────────────┘                                                 │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.4 Запуск

```bash
# CLI через скрипт
python scripts/run_test.py vitalbox
python scripts/run_test.py --list
python scripts/run_test.py vitalbox --quiet --no-save

# Программно
from src.agent_client_simulator import SimulatedClient, ConsultationTester

client = SimulatedClient.from_yaml("tests/scenarios/vitalbox.yaml")
tester = ConsultationTester(client=client, verbose=True)
result = await tester.run("vitalbox")
```

### 1.5 Output

- `output/tests/<scenario>_<timestamp>.json` — полный результат
- `output/tests/<scenario>_<timestamp>.md` — Markdown отчёт
- `output/tests/<scenario>_anketa.md` — сгенерированная анкета

---

## 2. agent_document_reviewer — Агент Ревью Документов

### 2.1 Назначение

Интерактивное редактирование документов во внешнем редакторе с валидацией.

### 2.2 Компоненты

```
src/agent_document_reviewer/
├── __init__.py           # Публичный API модуля
├── models.py             # ReviewConfig, ReviewResult, ReviewStatus
├── reviewer.py           # DocumentReviewer — главный класс
├── editor.py             # ExternalEditor — работа с редактором
├── parser.py             # DocumentParser — парсинг и diff
├── history.py            # VersionHistory — история версий
├── validators.py         # Валидаторы для разных типов документов
└── docs/                 # Документация модуля
```

### 2.3 Workflow Схема

```
┌──────────────────────────────────────────────────────────────────────┐
│                     AGENT_DOCUMENT_REVIEWER                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────┐                                                 │
│  │  Input Content  │  Markdown / текст документа                     │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                 │
│  │ DocumentReviewer│                                                 │
│  │                 │                                                 │
│  │   ReviewConfig: │                                                 │
│  │   • instructions│  Инструкции для пользователя                   │
│  │   • timeout     │  Лимит времени редактирования                  │
│  │   • validator   │  Функция валидации                              │
│  │   • readonly    │  Секции, защищённые от изменения               │
│  └────────┬────────┘                                                 │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      REVIEW WORKFLOW                         │    │
│  │                                                              │    │
│  │  1. Save Original                                            │    │
│  │     └─▶ VersionHistory.add_version()                         │    │
│  │                                                              │    │
│  │  2. Prepare Document                                         │    │
│  │     └─▶ DocumentParser.prepare_for_edit()                    │    │
│  │         (добавляет инструкции в начало)                      │    │
│  │                                                              │    │
│  │  3. Create Temp File                                         │    │
│  │     └─▶ ExternalEditor.create_temp_file()                    │    │
│  │                                                              │    │
│  │  4. Open Editor                                              │    │
│  │     └─▶ ExternalEditor.open_editor()                         │    │
│  │         ┌────────────────────────────────┐                   │    │
│  │         │  ВНЕШНИЙ РЕДАКТОР              │                   │    │
│  │         │  (VS Code / Sublime / nano)    │                   │    │
│  │         │                                │                   │    │
│  │         │  Пользователь:                 │                   │    │
│  │         │  • читает инструкции           │                   │    │
│  │         │  • редактирует документ        │                   │    │
│  │         │  • сохраняет и закрывает       │                   │    │
│  │         └────────────────────────────────┘                   │    │
│  │                                                              │    │
│  │  5. Read & Extract                                           │    │
│  │     └─▶ DocumentParser.extract_after_edit()                  │    │
│  │         (удаляет инструкции)                                 │    │
│  │                                                              │    │
│  │  6. Validate                                                 │    │
│  │     └─▶ Validator(content)                                   │    │
│  │         • readonly_preserved?                                │    │
│  │         • custom validation                                  │    │
│  │                                                              │    │
│  │  7. Save to History (if changed)                             │    │
│  │     └─▶ VersionHistory.add_version()                         │    │
│  │                                                              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                 │
│  │  ReviewResult   │                                                 │
│  │                 │  • status: COMPLETED / CANCELLED / ERROR        │
│  │                 │  • changed: bool                                │
│  │                 │  • content: str (edited)                        │
│  │                 │  • original_content: str                        │
│  │                 │  • version: int                                 │
│  │                 │  • errors: List[ValidationError]                │
│  │                 │  • duration_seconds: float                      │
│  └─────────────────┘                                                 │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.4 Статусы ReviewResult

```
┌─────────────────┬────────────────────────────────────────────────────┐
│     Status      │                    Описание                         │
├─────────────────┼────────────────────────────────────────────────────┤
│ COMPLETED       │ Редактирование завершено успешно                   │
│ CANCELLED       │ Пользователь отменил (пустой файл)                 │
│ TIMEOUT         │ Превышено время редактирования                     │
│ VALIDATION_FAILED│ Ошибки валидации                                  │
│ ERROR           │ Системная ошибка                                   │
└─────────────────┴────────────────────────────────────────────────────┘
```

### 2.5 Использование

```python
from src.agent_document_reviewer import (
    DocumentReviewer,
    ReviewConfig,
    review_anketa
)

# Простой вариант для анкеты
result = review_anketa(anketa_markdown, strict=True)

# С кастомной конфигурацией
config = ReviewConfig(
    instructions="Проверьте данные клиента",
    timeout_minutes=15,
    validator=my_custom_validator,
    readonly_sections=[r'^## Метаданные'],
)

reviewer = DocumentReviewer(config, document_id="anketa_001")
result = reviewer.review(content)

if result.is_success and result.changed:
    save_document(result.content)
```

---

## 3. Интегрированный Pipeline: Test → Review

### 3.1 Общая Схема

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INTEGRATED PIPELINE: TEST → REVIEW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐                                                        │
│  │  YAML Scenario  │                                                        │
│  │  (vitalbox.yaml)│                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           ▼                                                                  │
│  ╔═══════════════════════════════════════════════════════════════════╗      │
│  ║              STAGE 1: AGENT_TEST_CLIENT                           ║      │
│  ║                                                                   ║      │
│  ║  SimulatedClient ──▶ ConsultationTester ──▶ AnketaExtractor      ║      │
│  ║                                                                   ║      │
│  ║  Output:                                                          ║      │
│  ║  • TestResult (validation, metrics)                               ║      │
│  ║  • FinalAnketa (v2.0)                                             ║      │
│  ║  • Markdown файл                                                  ║      │
│  ╚════════════════════════════════════╤══════════════════════════════╝      │
│                                       │                                      │
│                                       ▼                                      │
│                              ┌─────────────────┐                            │
│                              │   Decision      │                            │
│                              │   Gate          │                            │
│                              │                 │                            │
│                              │  validation.    │                            │
│                              │  passed?        │                            │
│                              └────────┬────────┘                            │
│                                       │                                      │
│                    ┌─────────────────┴─────────────────┐                    │
│                    │ YES                               │ NO                  │
│                    ▼                                   ▼                     │
│  ╔═══════════════════════════════════╗    ┌───────────────────┐            │
│  ║  STAGE 2: AGENT_DOCUMENT_REVIEWER ║    │  Log Errors       │            │
│  ║                                   ║    │  Generate Report  │            │
│  ║  AnketaReviewService:             ║    │  Exit             │            │
│  ║  1. show_preview()                ║    └───────────────────┘            │
│  ║  2. prompt_action()               ║                                      │
│  ║  3. Open external editor          ║                                      │
│  ║  4. Validate with retry           ║                                      │
│  ║  5. show_diff()                   ║                                      │
│  ║  6. Parse → FinalAnketa           ║                                      │
│  ╚════════════════════════════╤══════╝                                      │
│                               │                                              │
│                               ▼                                              │
│                    ┌─────────────────┐                                      │
│                    │  Final Output   │                                      │
│                    │                 │                                      │
│                    │  • Reviewed     │                                      │
│                    │    FinalAnketa  │                                      │
│                    │  • JSON export  │                                      │
│                    │  • MD export    │                                      │
│                    └─────────────────┘                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Пример Кода Pipeline

```python
"""
Интегрированный pipeline: Test → Review
"""
import asyncio
from pathlib import Path

from src.agent_client_simulator import SimulatedClient, ConsultationTester, TestReporter
from src.agent_document_reviewer import DocumentReviewer, ReviewConfig, ReviewStatus
from src.anketa.generator import AnketaGenerator
from src.anketa.review_service import AnketaReviewService


async def run_test_and_review_pipeline(
    scenario_path: str,
    auto_approve: bool = False
) -> dict:
    """
    Запускает полный pipeline: тестирование → ревью анкеты.

    Args:
        scenario_path: Путь к YAML сценарию
        auto_approve: Автоматически принять без ревью

    Returns:
        dict с результатами обоих этапов
    """
    results = {
        "test": None,
        "review": None,
        "final_anketa": None,
        "status": "pending"
    }

    # ═══════════════════════════════════════════════════════════
    # STAGE 1: Автоматическое тестирование
    # ═══════════════════════════════════════════════════════════

    print("=" * 60)
    print("STAGE 1: Автоматическое тестирование")
    print("=" * 60)

    client = SimulatedClient.from_yaml(scenario_path)
    tester = ConsultationTester(client=client, verbose=True)

    test_result = await tester.run(
        scenario_name=Path(scenario_path).stem
    )
    results["test"] = test_result.to_dict()

    # Проверяем валидацию
    if test_result.validation and not test_result.validation.get("passed", False):
        print(f"\n[!] Тест не прошёл валидацию:")
        for error in test_result.validation.get("errors", []):
            print(f"    - {error}")
        results["status"] = "validation_failed"
        return results

    if test_result.status != "completed":
        print(f"\n[!] Тест завершился с ошибкой: {test_result.status}")
        results["status"] = "test_failed"
        return results

    print("\n[OK] Тестирование успешно завершено")

    # ═══════════════════════════════════════════════════════════
    # STAGE 2: Ревью анкеты
    # ═══════════════════════════════════════════════════════════

    if auto_approve:
        print("\n[AUTO] Автоматическое одобрение без ревью")
        results["final_anketa"] = test_result.final_anketa
        results["status"] = "completed"
        return results

    print("\n" + "=" * 60)
    print("STAGE 2: Ревью анкеты")
    print("=" * 60)

    # Загружаем сгенерированную анкету
    from src.anketa.schema import FinalAnketa

    if not test_result.final_anketa:
        print("[!] Анкета не была сгенерирована")
        results["status"] = "no_anketa"
        return results

    anketa = FinalAnketa(**test_result.final_anketa)

    # Запускаем сервис ревью
    review_service = AnketaReviewService()
    reviewed_anketa = review_service.finalize(anketa)

    if reviewed_anketa:
        results["review"] = {"status": "completed", "changed": True}
        results["final_anketa"] = reviewed_anketa.model_dump()
        results["status"] = "completed"

        # Сохраняем финальную версию
        generator = AnketaGenerator(output_dir="output/final")
        generator.to_markdown(reviewed_anketa)
        generator.to_json(reviewed_anketa)

        print("\n[OK] Анкета проверена и сохранена")
    else:
        results["review"] = {"status": "cancelled"}
        results["status"] = "review_cancelled"
        print("\n[!] Ревью отменено")

    return results


# Точка входа
if __name__ == "__main__":
    import sys

    scenario = sys.argv[1] if len(sys.argv) > 1 else "tests/scenarios/vitalbox.yaml"

    results = asyncio.run(run_test_and_review_pipeline(scenario))

    print("\n" + "=" * 60)
    print(f"ИТОГОВЫЙ СТАТУС: {results['status']}")
    print("=" * 60)
```

### 3.3 CLI Скрипт для Pipeline

Создайте `scripts/run_pipeline.py`:

```bash
# Запуск полного pipeline
python scripts/run_pipeline.py vitalbox

# С автоматическим одобрением (без ревью)
python scripts/run_pipeline.py vitalbox --auto-approve

# Только тест без ревью
python scripts/run_test.py vitalbox
```

---

## 4. Примеры Использования

### 4.1 Только тестирование

```bash
python scripts/run_test.py vitalbox
```

### 4.2 Только ревью существующей анкеты

```python
from src.agent_document_reviewer import review_anketa

with open("output/anketas/vitalbox.md") as f:
    content = f.read()

result = review_anketa(content, strict=True)

if result.changed:
    with open("output/anketas/vitalbox_reviewed.md", "w") as f:
        f.write(result.content)
```

### 4.3 Полный pipeline

```python
results = await run_test_and_review_pipeline(
    "tests/scenarios/vitalbox.yaml",
    auto_approve=False
)
```

---

## Архитектурные Заметки

### Независимость агентов

Оба агента полностью независимы и могут использоваться отдельно:

- **agent_client_simulator** — не требует agent_document_reviewer
- **agent_document_reviewer** — не требует agent_client_simulator

### Точки интеграции

Pipeline интегрирует их через:
1. `FinalAnketa` — общая модель данных
2. `AnketaGenerator` — конвертация в Markdown
3. `AnketaMarkdownParser` — парсинг обратно в модель

### Расширяемость

- Новые сценарии: добавьте YAML в `tests/scenarios/`
- Новые валидаторы: расширьте `validators.py`
- Новые форматы отчётов: расширьте `TestReporter`
