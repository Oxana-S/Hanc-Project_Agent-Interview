# Примеры использования

## Базовые примеры

### 1. Простое редактирование

```python
from document_reviewer import DocumentReviewer

reviewer = DocumentReviewer()
result = reviewer.review("""
# Заметка

Содержимое заметки...
""")

if result.is_success:
    print("Готово!")
    if result.changed:
        print(f"Изменено {result.diff_lines} строк")
        print(result.content)
```

### 2. С инструкциями

```python
from document_reviewer import DocumentReviewer, ReviewConfig

config = ReviewConfig(
    instructions="""
📝 ИНСТРУКЦИЯ:
1. Проверьте правильность данных
2. Исправьте ошибки если есть
3. Сохраните и закройте редактор

Для отмены — удалите всё содержимое
"""
)

reviewer = DocumentReviewer(config)
result = reviewer.review(document)
```

### 3. С timeout

```python
from document_reviewer import ReviewConfig, DocumentReviewer, ReviewStatus

config = ReviewConfig(timeout_minutes=5)
reviewer = DocumentReviewer(config)

result = reviewer.review(content)

if result.status == ReviewStatus.TIMEOUT:
    print("⏰ Время вышло! Изменения не сохранены.")
```

---

## Работа с историей

### 4. Включение истории

```python
from document_reviewer import DocumentReviewer, ReviewConfig

config = ReviewConfig(
    enable_history=True,
    max_history_versions=5
)

reviewer = DocumentReviewer(
    config,
    document_id="my_document",
    persist_history=True,
    history_dir="./history"
)

# Первое редактирование
result1 = reviewer.review("Version 1")

# Второе редактирование
result2 = reviewer.review(result1.content)

# Посмотреть diff
print(reviewer.get_diff())

# Откатиться к версии 1
old_content = reviewer.rollback(1)
```

### 5. Просмотр истории

```python
# Все версии
for version in reviewer.history.versions:
    print(f"v{version.version}: {version.created_at} by {version.author}")
    if version.comment:
        print(f"   Comment: {version.comment}")

# Сравнение версий
comparison = reviewer.history.compare_versions(1, 3)
print(f"Изменение строк: {comparison['lines_diff']}")
```

---

## Валидация

### 6. Встроенные валидаторы

```python
from document_reviewer import (
    ReviewConfig,
    DocumentReviewer,
    compose,
    not_empty,
    min_length,
    markdown_valid,
    no_placeholder_text
)

validator = compose(
    not_empty(),
    min_length(50),
    markdown_valid(),
    no_placeholder_text(["[TODO]", "[ЗАПОЛНИТЬ]"])
)

config = ReviewConfig(validator=validator)
reviewer = DocumentReviewer(config)

result = reviewer.review(content)

if result.errors:
    print("Ошибки/предупреждения:")
    for error in result.errors:
        print(f"  {error}")
```

### 7. Кастомный валидатор

```python
from document_reviewer import ValidationError, ReviewConfig, DocumentReviewer

def my_validator(content: str) -> list[ValidationError]:
    errors = []

    # Проверка наличия заголовка
    if not content.startswith("#"):
        errors.append(ValidationError(
            field="header",
            message="Документ должен начинаться с заголовка"
        ))

    # Проверка длины строк
    for i, line in enumerate(content.split("\n"), 1):
        if len(line) > 120:
            errors.append(ValidationError(
                field="line_length",
                message=f"Строка слишком длинная ({len(line)} символов)",
                line=i,
                severity="warning"
            ))

    return errors

config = ReviewConfig(validator=my_validator)
```

### 8. Retry при ошибках валидации

```python
from document_reviewer import DocumentReviewer, ReviewConfig, strict_anketa_validator

config = ReviewConfig(
    instructions="Заполните все обязательные поля",
    validator=strict_anketa_validator()
)

reviewer = DocumentReviewer(config)

# Автоматический retry до 3 раз
result = reviewer.review_with_retry(anketa, max_retries=3)
```

---

## Readonly секции

### 9. Защита секций от редактирования

```python
from document_reviewer import ReviewConfig, DocumentReviewer

config = ReviewConfig(
    instructions="Редактируйте только секции с данными клиента",
    readonly_sections=[
        r'^## Метаданные',        # Секция метаданных
        r'^## Системная информация',
        r'^\*Автоматически сгенерировано',  # Футер
    ]
)

reviewer = DocumentReviewer(config)
result = reviewer.review(document)

# Если readonly секции изменены — будет ошибка валидации
if not result.is_success:
    for error in result.errors:
        if error.field == "readonly":
            print(f"Нельзя менять: {error.message}")
```

---

## Работа с анкетами

### 10. Ревью анкеты

```python
from document_reviewer import review_anketa

# Простой вариант
result = review_anketa(anketa_markdown)

# Строгая валидация
result = review_anketa(anketa_markdown, strict=True)

if result.is_success:
    if result.changed:
        # Парсим обратно в Pydantic модель
        updated_anketa = parse_anketa_markdown(result.content)
        save_to_database(updated_anketa)
```

### 11. Полный workflow с анкетой

```python
from document_reviewer import DocumentReviewer, ReviewConfig, anketa_validator
from src.anketa.generator import AnketaGenerator
from src.anketa.schema import FinalAnketa

def finalize_anketa(anketa: FinalAnketa) -> FinalAnketa:
    """Финализация анкеты с ревью пользователем."""

    # Генерируем Markdown
    generator = AnketaGenerator()
    markdown = generator._render_markdown(anketa)

    # Настраиваем ревьювер
    config = ReviewConfig(
        instructions="""
📋 ФИНАЛЬНАЯ ПРОВЕРКА АНКЕТЫ

Пожалуйста, проверьте собранную информацию:
- Корректность данных о компании
- Полноту описания бизнес-проблем
- Правильность функций агента

После проверки сохраните файл (Ctrl+S / :wq)
Для отмены — удалите содержимое и сохраните пустой файл
""",
        validator=anketa_validator(),
        readonly_sections=[r'^## Метаданные'],
        timeout_minutes=20
    )

    reviewer = DocumentReviewer(
        config,
        document_id=f"anketa_{anketa.company_name}",
        persist_history=True
    )

    result = reviewer.review(markdown)

    if result.status.value == "cancelled":
        raise ValueError("Анкета отклонена пользователем")

    if result.is_success and result.changed:
        # Применяем изменения
        anketa = apply_markdown_changes(anketa, result.content)

    return anketa
```

---

## Продвинутые сценарии

### 12. Выбор редактора программно

```python
from document_reviewer import ReviewConfig, is_gui_available

# Выбор редактора в зависимости от окружения
if is_gui_available():
    editor = "code"  # VS Code
    args = ["--wait"]
else:
    editor = "nano"
    args = []

config = ReviewConfig(editor=editor, editor_args=args)
```

### 13. Логирование всех изменений

```python
import structlog
from document_reviewer import DocumentReviewer, ReviewConfig

log = structlog.get_logger()

def reviewed_save(content: str, filepath: str):
    """Сохранение с обязательным ревью и логированием."""

    config = ReviewConfig(enable_history=True)
    reviewer = DocumentReviewer(config, document_id=filepath)

    result = reviewer.review(content)

    log.info(
        "document_reviewed",
        filepath=filepath,
        status=result.status.value,
        changed=result.changed,
        duration=result.duration_seconds,
        version=result.version
    )

    if result.is_success:
        with open(filepath, 'w') as f:
            f.write(result.content)

        if result.changed:
            log.info("document_saved", filepath=filepath, diff_lines=result.diff_lines)

    return result
```

### 14. Batch-обработка документов

```python
from pathlib import Path
from document_reviewer import DocumentReviewer, ReviewConfig, ReviewStatus

def batch_review(directory: str, pattern: str = "*.md"):
    """Последовательный ревью всех документов."""

    config = ReviewConfig(
        instructions="Проверьте документ. Нажмите Ctrl+C для пропуска.",
        timeout_minutes=10
    )

    reviewer = DocumentReviewer(config)
    results = []

    for filepath in Path(directory).glob(pattern):
        print(f"\n📄 {filepath.name}")

        content = filepath.read_text()
        result = reviewer.review(content)

        if result.is_success and result.changed:
            filepath.write_text(result.content)
            print(f"   ✅ Сохранено ({result.diff_lines} изменений)")
        elif result.status == ReviewStatus.CANCELLED:
            print("   ⏭️ Пропущено")
        else:
            print(f"   ⚠️ {result.status.value}")

        results.append((filepath, result))

    return results
```
