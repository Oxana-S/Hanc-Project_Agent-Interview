"""
AnketaGenerator - generates documents from FinalAnketa.

Supports:
- Markdown format (human-readable)
- JSON format (machine-readable)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import structlog

from src.anketa.schema import FinalAnketa, AgentFunction, Integration

logger = structlog.get_logger()


class AnketaGenerator:
    """Generates documents from FinalAnketa."""

    def __init__(self, output_dir: str = "output/anketas"):
        """
        Initialize generator.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_markdown(self, anketa: FinalAnketa, filename: Optional[str] = None) -> Path:
        """
        Generate Markdown document from anketa.

        Args:
            anketa: Populated FinalAnketa instance
            filename: Optional custom filename

        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._safe_filename(anketa.company_name)
            filename = f"{safe_name}_{timestamp}.md"

        content = self._render_markdown(anketa)
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info("Markdown anketa saved", path=str(filepath))
        return filepath

    def to_json(self, anketa: FinalAnketa, filename: Optional[str] = None) -> Path:
        """
        Save anketa as JSON file.

        Args:
            anketa: Populated FinalAnketa instance
            filename: Optional custom filename

        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._safe_filename(anketa.company_name)
            filename = f"{safe_name}_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(anketa.model_dump_json(indent=2, ensure_ascii=False))

        logger.info("JSON anketa saved", path=str(filepath))
        return filepath

    def _safe_filename(self, name: str) -> str:
        """Convert name to safe filename."""
        if not name:
            return "unnamed"
        # Replace spaces and special chars
        safe = name.lower().replace(" ", "_")
        # Keep only alphanumeric and underscore
        safe = "".join(c for c in safe if c.isalnum() or c == "_")
        return safe[:50] if safe else "unnamed"

    def _render_markdown(self, anketa: FinalAnketa) -> str:
        """Render Markdown content from anketa."""

        completion_rate = anketa.completion_rate()
        duration_min = anketa.consultation_duration_seconds / 60

        return f"""# Анкета: {anketa.company_name}

**Дата создания:** {anketa.created_at.strftime('%Y-%m-%d %H:%M')}
**Длительность консультации:** {duration_min:.1f} мин
**Заполненность:** {completion_rate:.0f}%

---

## 1. Информация о компании

| Поле | Значение |
|------|----------|
| Компания | {anketa.company_name} |
| Отрасль | {anketa.industry} |
| Специализация | {anketa.specialization or '—'} |
| Сайт | {anketa.website or '—'} |
| Контактное лицо | {anketa.contact_name or '—'} |
| Должность | {anketa.contact_role or '—'} |

### Описание бизнеса

{anketa.business_description or '*Не указано*'}

### Услуги / Продукты

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
| Имя агента | {anketa.agent_name or '—'} |
| Назначение | {anketa.agent_purpose or '—'} |
| Голос | {anketa.voice_gender}, {anketa.voice_tone} |
| Язык | {anketa.language} |
| Тип звонков | {self._format_call_direction(anketa.call_direction)} |

### Основная функция

{self._render_main_function(anketa.main_function)}

### Дополнительные функции

{self._render_functions(anketa.additional_functions)}

### Типичные вопросы (FAQ)

{self._render_list(anketa.typical_questions)}

---

## 4. Все функции агента

{self._render_functions(anketa.agent_functions)}

---

## 5. Интеграции

{self._render_integrations(anketa.integrations)}

---

## Метаданные

- **Создано:** {anketa.created_at.strftime('%Y-%m-%d %H:%M:%S')}
- **Длительность консультации:** {anketa.consultation_duration_seconds:.0f} сек
- **Заполненность анкеты:** {completion_rate:.0f}%

---

*Сгенерировано автоматически системой ConsultantInterviewer*
"""

    def _render_list(self, items: List[str]) -> str:
        """Render list as markdown bullets."""
        if not items:
            return "*Не указано*"
        return "\n".join(f"- {item}" for item in items if item)

    def _render_main_function(self, func: Optional[AgentFunction]) -> str:
        """Render main function block."""
        if not func:
            return "*Не определена*"

        return f"""**{func.name}**

{func.description}

*Приоритет: {func.priority}*"""

    def _render_functions(self, functions: List[AgentFunction]) -> str:
        """Render list of functions."""
        if not functions:
            return "*Не указано*"

        lines = []
        for i, func in enumerate(functions, 1):
            lines.append(f"### {i}. {func.name}")
            lines.append("")
            lines.append(func.description)
            lines.append("")
            lines.append(f"*Приоритет: {func.priority}*")
            lines.append("")

        return "\n".join(lines)

    def _render_integrations(self, integrations: List[Integration]) -> str:
        """Render integrations as table."""
        if not integrations:
            return "*Интеграции не требуются*"

        lines = [
            "| Система | Назначение | Обязательно |",
            "|---------|------------|-------------|"
        ]

        for intg in integrations:
            required = "Да" if intg.required else "Нет"
            lines.append(f"| {intg.name} | {intg.purpose} | {required} |")

        return "\n".join(lines)

    def _format_call_direction(self, direction: str) -> str:
        """Format call direction for display."""
        mapping = {
            "inbound": "Входящие",
            "outbound": "Исходящие",
            "both": "Входящие и исходящие"
        }
        return mapping.get(direction, direction)


def generate_anketa_files(anketa: FinalAnketa, output_dir: str = "output/anketas") -> dict:
    """
    Convenience function to generate both Markdown and JSON files.

    Args:
        anketa: Populated FinalAnketa instance
        output_dir: Output directory

    Returns:
        Dict with paths: {'markdown': Path, 'json': Path}
    """
    generator = AnketaGenerator(output_dir=output_dir)

    return {
        'markdown': generator.to_markdown(anketa),
        'json': generator.to_json(anketa)
    }
