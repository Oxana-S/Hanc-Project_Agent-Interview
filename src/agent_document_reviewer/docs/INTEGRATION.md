# Руководство по интеграции

## Интеграция с ConsultantInterviewer

### Базовая интеграция

```python
from document_reviewer import review_anketa
from src.anketa.generator import AnketaGenerator

class ConsultantInterviewer:

    async def finalize_consultation(self, anketa: FinalAnketa) -> FinalAnketa:
        """Завершение консультации с ревью анкеты."""

        # Генерируем Markdown
        generator = AnketaGenerator()
        markdown = generator._render_markdown(anketa)

        # Открываем на ревью
        print("\n📝 Откройте редактор для проверки анкеты...")
        result = review_anketa(markdown)

        if result.is_success:
            if result.changed:
                print("✅ Анкета обновлена")
                # Парсим изменения обратно в модель
                anketa = self._parse_markdown_to_anketa(result.content, anketa)
            else:
                print("✅ Анкета подтверждена без изменений")
        else:
            print(f"⚠️ Ревью завершено со статусом: {result.status.value}")

        return anketa
```

### С кастомным валидатором

```python
from document_reviewer import DocumentReviewer, ReviewConfig, ValidationError

def business_validator(content: str) -> list[ValidationError]:
    """Бизнес-валидация анкеты."""
    errors = []

    # Проверка бюджета
    if "бюджет" in content.lower() and "не указан" in content.lower():
        errors.append(ValidationError(
            field="budget",
            message="Бюджет клиента должен быть указан",
            severity="warning"
        ))

    return errors

# Использование
config = ReviewConfig(
    instructions="Проверьте анкету перед отправкой в CRM",
    validator=business_validator,
    timeout_minutes=15
)

reviewer = DocumentReviewer(config, document_id="anketa_123")
result = reviewer.review(anketa_markdown)
```

---

## Интеграция с CLI

### Click-команда

```python
import click
from document_reviewer import review_document, ReviewConfig

@click.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--timeout', '-t', default=30, help='Timeout в минутах')
def review(file: str, timeout: int):
    """Открыть файл на ревью."""

    with open(file, 'r') as f:
        content = f.read()

    result = review_document(
        content,
        instructions=f"Редактирование: {file}",
        timeout_minutes=timeout
    )

    if result.is_success and result.changed:
        with open(file, 'w') as f:
            f.write(result.content)
        click.echo(f"✅ Сохранено ({result.diff_lines} строк изменено)")
    elif result.status.value == "cancelled":
        click.echo("❌ Отменено")
    else:
        click.echo(f"⚠️ {result.status.value}")

if __name__ == '__main__':
    review()
```

---

## Интеграция с другими агентами

### Паттерн: ReviewableDocument

```python
from abc import ABC, abstractmethod
from document_reviewer import DocumentReviewer, ReviewConfig, ReviewResult

class ReviewableDocument(ABC):
    """Базовый класс для документов с поддержкой ревью."""

    @abstractmethod
    def to_markdown(self) -> str:
        """Конвертировать в Markdown."""
        pass

    @abstractmethod
    def from_markdown(self, content: str) -> 'ReviewableDocument':
        """Создать из Markdown."""
        pass

    def review(self, config: ReviewConfig = None) -> ReviewResult:
        """Открыть на ревью."""
        reviewer = DocumentReviewer(config)
        return reviewer.review(self.to_markdown())


# Пример реализации
class ContractDocument(ReviewableDocument):
    def __init__(self, client: str, terms: list):
        self.client = client
        self.terms = terms

    def to_markdown(self) -> str:
        terms_md = "\n".join(f"- {t}" for t in self.terms)
        return f"# Договор\n\nКлиент: {self.client}\n\n## Условия\n\n{terms_md}"

    def from_markdown(self, content: str) -> 'ContractDocument':
        # Парсинг...
        return self
```

---

## Интеграция с веб-приложением

### FastAPI endpoint

```python
from fastapi import FastAPI, BackgroundTasks
from document_reviewer import DocumentReviewer, ReviewConfig
import asyncio

app = FastAPI()

# Для веб-интеграции используем асинхронную обёртку
async def async_review(content: str, config: ReviewConfig) -> dict:
    """Асинхронный ревью в отдельном потоке."""
    loop = asyncio.get_event_loop()
    reviewer = DocumentReviewer(config)

    result = await loop.run_in_executor(
        None,
        reviewer.review,
        content
    )

    return {
        "status": result.status.value,
        "changed": result.changed,
        "content": result.content if result.changed else None,
        "errors": [str(e) for e in result.errors]
    }

@app.post("/api/review")
async def review_endpoint(content: str, timeout: int = 30):
    config = ReviewConfig(timeout_minutes=timeout)
    return await async_review(content, config)
```

---

## Конфигурация через переменные окружения

```python
import os
from document_reviewer import ReviewConfig

def config_from_env() -> ReviewConfig:
    """Создать конфигурацию из переменных окружения."""
    return ReviewConfig(
        editor=os.getenv("DOCUMENT_EDITOR"),
        timeout_minutes=int(os.getenv("REVIEW_TIMEOUT", "30")),
        enable_history=os.getenv("REVIEW_HISTORY", "true").lower() == "true",
        max_history_versions=int(os.getenv("REVIEW_MAX_VERSIONS", "10")),
    )
```

---

## Обработка ошибок

```python
from document_reviewer import (
    DocumentReviewer,
    ReviewStatus,
    EditorError,
    EditorTimeoutError
)

def safe_review(content: str) -> str:
    """Безопасный ревью с обработкой всех ошибок."""

    try:
        reviewer = DocumentReviewer()
        result = reviewer.review(content)

        match result.status:
            case ReviewStatus.COMPLETED:
                return result.content

            case ReviewStatus.CANCELLED:
                print("Пользователь отменил редактирование")
                return content

            case ReviewStatus.TIMEOUT:
                print("Время редактирования истекло")
                return content

            case ReviewStatus.VALIDATION_FAILED:
                print("Ошибки валидации:")
                for error in result.errors:
                    print(f"  - {error}")
                return result.content  # Возвращаем с ошибками

            case ReviewStatus.ERROR:
                print(f"Ошибка: {result.errors}")
                return content

    except EditorTimeoutError:
        print("Редактор не отвечает")
        return content

    except EditorError as e:
        print(f"Ошибка редактора: {e}")
        return content
```

---

## Тестирование

```python
import pytest
from unittest.mock import patch, MagicMock
from document_reviewer import DocumentReviewer, ReviewConfig, ReviewStatus

class TestDocumentReviewer:

    @patch('document_reviewer.editor.ExternalEditor')
    def test_review_no_changes(self, mock_editor_class):
        """Тест без изменений."""
        mock_editor = MagicMock()
        mock_editor.create_temp_file.return_value = "/tmp/test.md"
        mock_editor.open_editor.return_value = (ReviewStatus.COMPLETED, 10.0)
        mock_editor.read_file.return_value = "# Test"
        mock_editor_class.return_value = mock_editor

        reviewer = DocumentReviewer()
        result = reviewer.review("# Test")

        assert result.is_success
        assert not result.changed

    def test_validator_composition(self):
        """Тест композиции валидаторов."""
        from document_reviewer import compose, not_empty, min_length

        validator = compose(not_empty(), min_length(10))

        errors = validator("")
        assert len(errors) >= 1

        errors = validator("Short")
        assert len(errors) >= 1

        errors = validator("This is long enough")
        assert len(errors) == 0
```
