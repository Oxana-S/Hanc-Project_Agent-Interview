# API Reference

## Основные классы

### DocumentReviewer

Главный класс для работы с документами.

```python
class DocumentReviewer:
    def __init__(
        self,
        config: Optional[ReviewConfig] = None,
        document_id: Optional[str] = None,
        persist_history: bool = False,
        history_dir: str = "output/history"
    )
```

**Параметры:**
- `config` — конфигурация (ReviewConfig), по умолчанию DEFAULT_CONFIG
- `document_id` — уникальный идентификатор документа для истории
- `persist_history` — сохранять историю на диск
- `history_dir` — директория для истории

**Методы:**

#### review()

```python
def review(
    self,
    content: str,
    validator: Optional[Validator] = None
) -> ReviewResult
```

Открывает документ в редакторе и возвращает результат.

**Параметры:**
- `content` — содержимое документа
- `validator` — дополнительный валидатор

**Возвращает:** ReviewResult

#### review_with_retry()

```python
def review_with_retry(
    self,
    content: str,
    max_retries: int = 3,
    validator: Optional[Validator] = None
) -> ReviewResult
```

Review с автоматическим повтором при ошибках валидации.

#### get_diff()

```python
def get_diff(
    self,
    version1: Optional[int] = None,
    version2: Optional[int] = None
) -> str
```

Получить diff между версиями.

#### rollback()

```python
def rollback(self, version: int) -> Optional[str]
```

Откатить к указанной версии.

---

### ReviewConfig

Конфигурация сессии редактирования.

```python
@dataclass
class ReviewConfig:
    # Редактор
    editor: Optional[str] = None
    editor_args: List[str] = field(default_factory=list)

    # Timeout
    timeout_minutes: int = 30

    # История
    enable_history: bool = True
    max_history_versions: int = 10

    # Инструкции
    instructions: Optional[str] = None
    instructions_prefix: str = "<!-- ИНСТРУКЦИИ...\n"
    instructions_suffix: str = "\n-->\n\n"

    # Readonly секции
    readonly_sections: List[str] = field(default_factory=list)
    readonly_marker: str = "<!-- READONLY -->"

    # Валидация
    validator: Optional[Callable[[str], List[ValidationError]]] = None
    allow_save_with_warnings: bool = True

    # Файлы
    temp_file_prefix: str = "review_"
    temp_file_suffix: str = ".md"
    encoding: str = "utf-8"

    # Поведение
    show_diff_on_save: bool = False
    confirm_on_large_changes: bool = False
    large_change_threshold: int = 50
```

**Методы:**

```python
def with_instructions(self, text: str) -> ReviewConfig
def with_validator(self, func: Callable) -> ReviewConfig
```

---

### ReviewResult

Результат сессии редактирования.

```python
@dataclass
class ReviewResult:
    status: ReviewStatus
    changed: bool
    content: str
    original_content: str
    version: int
    errors: List[ValidationError] = field(default_factory=list)
    duration_seconds: float = 0.0
```

**Свойства:**

```python
@property
def is_success(self) -> bool:
    """True если статус COMPLETED"""

@property
def diff_lines(self) -> int:
    """Количество изменённых строк"""
```

---

### ReviewStatus

```python
class ReviewStatus(Enum):
    COMPLETED = "completed"           # Успешно завершено
    CANCELLED = "cancelled"           # Отменено (пустой файл)
    TIMEOUT = "timeout"               # Истекло время
    ERROR = "error"                   # Ошибка
    VALIDATION_FAILED = "validation_failed"  # Ошибка валидации
```

---

### ValidationError

```python
@dataclass
class ValidationError:
    field: str
    message: str
    line: Optional[int] = None
    severity: str = "error"  # "error" или "warning"
```

---

### DocumentVersion

```python
@dataclass
class DocumentVersion:
    version: int
    content: str
    created_at: datetime
    author: str = "user"
    comment: Optional[str] = None
```

---

## Валидаторы

### Встроенные валидаторы

```python
# Базовые
not_empty() -> Validator
min_length(length: int) -> Validator
max_length(length: int) -> Validator
markdown_valid() -> Validator
no_placeholder_text(placeholders: List[str] = None) -> Validator

# Структурные
required_sections(section_patterns: List[str]) -> Validator
no_empty_fields(field_patterns: List[str]) -> Validator

# Для анкет
anketa_validator() -> Validator
strict_anketa_validator() -> Validator
```

### Композиция

```python
from document_reviewer import compose, not_empty, min_length

my_validator = compose(
    not_empty(),
    min_length(100),
    markdown_valid()
)
```

### Фабрика

```python
from document_reviewer import create_validator

validator = create_validator("anketa")  # или "strict_anketa", "default", "minimal"
```

---

## Функции-помощники

### review_document()

```python
def review_document(
    content: str,
    instructions: Optional[str] = None,
    validator_type: str = "default",
    timeout_minutes: int = 30
) -> ReviewResult
```

Быстрая функция для разового редактирования.

### review_anketa()

```python
def review_anketa(
    content: str,
    strict: bool = False
) -> ReviewResult
```

Специализированная функция для анкет.

---

## Пресеты конфигурации

```python
from document_reviewer import DEFAULT_CONFIG, STRICT_CONFIG, QUICK_EDIT_CONFIG

# DEFAULT_CONFIG — стандартные настройки
# STRICT_CONFIG — строгая валидация, короткий timeout
# QUICK_EDIT_CONFIG — без истории, минимальный timeout
```
