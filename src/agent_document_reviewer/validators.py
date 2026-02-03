"""
Validators for DocumentReviewer.

Provides:
- Built-in validators for common cases
- Validator composition utilities
- Anketa-specific validators
"""

import re
from typing import List, Callable, Optional

from .models import ValidationError


# Type alias for validator functions
Validator = Callable[[str], List[ValidationError]]


def not_empty() -> Validator:
    """Validate that content is not empty."""

    def validate(content: str) -> List[ValidationError]:
        if not content or not content.strip():
            return [ValidationError(
                field="content",
                message="Документ не может быть пустым"
            )]
        return []

    return validate


def min_length(length: int) -> Validator:
    """Validate minimum content length."""

    def validate(content: str) -> List[ValidationError]:
        if len(content.strip()) < length:
            return [ValidationError(
                field="content",
                message=f"Документ должен содержать минимум {length} символов"
            )]
        return []

    return validate


def max_length(length: int) -> Validator:
    """Validate maximum content length."""

    def validate(content: str) -> List[ValidationError]:
        if len(content) > length:
            return [ValidationError(
                field="content",
                message=f"Документ не должен превышать {length} символов",
                severity="warning"
            )]
        return []

    return validate


def required_sections(section_patterns: List[str]) -> Validator:
    """Validate that required sections are present."""

    def validate(content: str) -> List[ValidationError]:
        errors = []

        for pattern in section_patterns:
            if not re.search(pattern, content, re.MULTILINE):
                # Extract readable section name from pattern
                name = pattern.replace(r'^', '').replace(r'\s*', ' ').strip()
                errors.append(ValidationError(
                    field="sections",
                    message=f"Отсутствует обязательная секция: {name}"
                ))

        return errors

    return validate


def no_empty_fields(field_patterns: List[str]) -> Validator:
    """Validate that specified fields are not empty."""

    def validate(content: str) -> List[ValidationError]:
        errors = []

        for pattern in field_patterns:
            # Pattern should capture the field value
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                if not value.strip() or value.strip() in ('—', '-', 'N/A', 'n/a'):
                    field_name = pattern.split('|')[0].replace(r'\|', '').strip()
                    errors.append(ValidationError(
                        field=field_name,
                        message="Поле не должно быть пустым",
                        severity="warning"
                    ))

        return errors

    return validate


def markdown_valid() -> Validator:
    """Basic Markdown structure validation."""

    def validate(content: str) -> List[ValidationError]:
        errors = []

        lines = content.split('\n')

        # Check for unclosed code blocks
        code_block_count = content.count('```')
        if code_block_count % 2 != 0:
            errors.append(ValidationError(
                field="markdown",
                message="Незакрытый блок кода (```)"
            ))

        # Check for broken tables
        table_lines = [i for i, line in enumerate(lines, 1)
                       if line.strip().startswith('|')]
        for i, line_num in enumerate(table_lines):
            if i > 0 and table_lines[i] - table_lines[i-1] > 2:
                errors.append(ValidationError(
                    field="markdown",
                    message="Возможно нарушена структура таблицы",
                    line=line_num,
                    severity="warning"
                ))

        return errors

    return validate


def no_placeholder_text(placeholders: Optional[List[str]] = None) -> Validator:
    """Check for placeholder text that should be replaced."""

    default_placeholders = [
        r'\[TODO\]',
        r'\[ЗАПОЛНИТЬ\]',
        r'\[УКАЖИТЕ\]',
        r'XXX',
        r'\.\.\.',
    ]

    def validate(content: str) -> List[ValidationError]:
        patterns = placeholders or default_placeholders
        errors = []

        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(ValidationError(
                        field="placeholder",
                        message=f"Найден незаполненный placeholder",
                        line=i,
                        severity="warning"
                    ))
                    break  # One error per line

        return errors

    return validate


def compose(*validators: Validator) -> Validator:
    """Compose multiple validators into one."""

    def validate(content: str) -> List[ValidationError]:
        errors = []
        for validator in validators:
            errors.extend(validator(content))
        return errors

    return validate


def only_warnings(validator: Validator) -> Validator:
    """Convert all errors from validator to warnings."""

    def validate(content: str) -> List[ValidationError]:
        errors = validator(content)
        for error in errors:
            error.severity = "warning"
        return errors

    return validate


# ================== Anketa-specific validators ==================

def anketa_validator() -> Validator:
    """
    Validator for FinalAnketa documents.

    Checks:
    - Required sections present
    - Company name filled
    - At least one agent function defined
    - Integrations section present
    """
    required = required_sections([
        r'^## 1\. Информация о компании',
        r'^## 2\. Бизнес-контекст',
        r'^## 3\. Голосовой агент',
        r'^## 4\. Все функции агента',
        r'^## 5\. Интеграции',
    ])

    def validate(content: str) -> List[ValidationError]:
        errors = []

        # Check required sections
        errors.extend(required(content))

        # Check company name
        match = re.search(r'\| Компания \| (.+?) \|', content)
        if not match or match.group(1).strip() in ('—', '-', ''):
            errors.append(ValidationError(
                field="company_name",
                message="Название компании обязательно"
            ))

        # Check for at least one agent function
        if '### 1.' not in content:
            errors.append(ValidationError(
                field="agent_functions",
                message="Должна быть определена хотя бы одна функция агента",
                severity="warning"
            ))

        # Basic markdown validation
        errors.extend(markdown_valid()(content))

        return errors

    return validate


def strict_anketa_validator() -> Validator:
    """Strict validator for production anketas."""

    base_validator = anketa_validator()

    def validate(content: str) -> List[ValidationError]:
        errors = base_validator(content)

        # Additional strict checks

        # Must have industry
        match = re.search(r'\| Отрасль \| (.+?) \|', content)
        if not match or match.group(1).strip() in ('—', '-', ''):
            errors.append(ValidationError(
                field="industry",
                message="Отрасль обязательна"
            ))

        # Must have current problems
        problems_section = re.search(
            r'### Текущие проблемы\n\n(.+?)(?=###|\n---)',
            content,
            re.DOTALL
        )
        if not problems_section or 'Не указано' in problems_section.group(1):
            errors.append(ValidationError(
                field="current_problems",
                message="Должны быть указаны текущие проблемы"
            ))

        # Must have integrations
        integ_section = re.search(r'## 5\. Интеграции\n\n(.+?)(?=---|$)', content, re.DOTALL)
        if integ_section and 'не требуются' in integ_section.group(1).lower():
            errors.append(ValidationError(
                field="integrations",
                message="Рекомендуется указать хотя бы одну интеграцию",
                severity="warning"
            ))

        return errors

    return validate


# ================== Factory functions ==================

def create_validator(
    validator_type: str = "default"
) -> Validator:
    """
    Factory function for creating validators.

    Args:
        validator_type: Type of validator
            - "default": Basic validation
            - "anketa": Anketa document validation
            - "strict_anketa": Strict anketa validation
            - "minimal": Only check not empty

    Returns:
        Validator function
    """
    validators = {
        "default": compose(
            not_empty(),
            markdown_valid(),
            no_placeholder_text()
        ),
        "anketa": anketa_validator(),
        "strict_anketa": strict_anketa_validator(),
        "minimal": not_empty(),
    }

    return validators.get(validator_type, validators["default"])
