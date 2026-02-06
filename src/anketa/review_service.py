"""
AnketaReviewService - orchestrates anketa review workflow.

Provides:
- Preview in CLI before opening editor
- External editor integration via DocumentReviewer
- Validation with retry
- Diff display after editing
- Markdown → FinalAnketa synchronization
"""

from typing import Optional, Literal

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.anketa.schema import FinalAnketa
from src.anketa.generator import AnketaGenerator
from src.anketa.markdown_parser import AnketaMarkdownParser
from src.agent_document_reviewer import (
    DocumentReviewer,
    ReviewConfig,
    ReviewStatus,
    ValidationError,
    strict_anketa_validator,
)
from src.agent_document_reviewer.parser import DocumentParser

logger = structlog.get_logger("anketa")
console = Console()


class AnketaReviewService:
    """
    Service for reviewing and finalizing anketas.

    Orchestrates the complete review workflow:
    1. Show preview
    2. Prompt for action
    3. Open editor (if requested)
    4. Validate with retry
    5. Show diff
    6. Parse changes back to model

    Example:
        ```python
        service = AnketaReviewService()
        final_anketa = service.finalize(anketa)

        if final_anketa:
            save_anketa(final_anketa)
        ```
    """

    MAX_RETRIES = 3

    def __init__(self, config: Optional[ReviewConfig] = None):
        """
        Initialize the review service.

        Args:
            config: Optional ReviewConfig for DocumentReviewer
        """
        self.config = config or self._default_config()
        self.generator = AnketaGenerator()
        self.parser = AnketaMarkdownParser()
        self.doc_parser = DocumentParser(self.config)

    def _default_config(self) -> ReviewConfig:
        """Create default review configuration."""
        return ReviewConfig(
            instructions=self._get_instructions(),
            timeout_minutes=30,
            validator=strict_anketa_validator(),
            readonly_sections=[
                r'^## Метаданные',
                r'^\*Сгенерировано автоматически',
            ],
            enable_history=True,
        )

    def _get_instructions(self, errors: list[ValidationError] = None) -> str:
        """Get instructions text for editor."""
        base = """
ПРОВЕРКА АНКЕТЫ

Пожалуйста, проверьте и при необходимости отредактируйте анкету.

Инструкции:
- Проверьте правильность всех данных
- Исправьте ошибки или дополните информацию
- Не редактируйте секцию "Метаданные"

После проверки:
- Сохраните файл и закройте редактор
- Для отмены — удалите всё содержимое и сохраните пустой файл
"""
        if errors:
            error_lines = "\n".join(f"  • {e}" for e in errors)
            base += f"\n\n⚠️ ОШИБКИ ВАЛИДАЦИИ:\n{error_lines}\n\nИсправьте ошибки и сохраните снова."

        return base

    def finalize(self, anketa: FinalAnketa) -> Optional[FinalAnketa]:
        """
        Complete review workflow for anketa.

        Args:
            anketa: FinalAnketa to review

        Returns:
            Updated FinalAnketa or None if cancelled
        """
        logger.info("Starting anketa review", company=anketa.company_name)

        # Step 1: Show preview
        self.show_preview(anketa)

        # Step 2: Prompt for action
        action = self.prompt_action()

        if action == "cancel":
            console.print("\n[yellow]Отменено[/yellow]")
            return None

        if action == "save":
            console.print("\n[green]✓ Сохраняем без изменений[/green]")
            return anketa

        # Step 3: Open editor with retry
        markdown = self.generator._render_markdown(anketa)
        result_anketa = self._review_with_retry(anketa, markdown)

        return result_anketa

    def _review_with_retry(
        self,
        original_anketa: FinalAnketa,
        original_markdown: str
    ) -> Optional[FinalAnketa]:
        """Review with validation retry loop."""

        current_markdown = original_markdown
        errors = []

        for attempt in range(self.MAX_RETRIES):
            # Update config with errors if retry
            config = self._config_with_errors(errors) if errors else self.config

            reviewer = DocumentReviewer(
                config,
                document_id=f"anketa_{original_anketa.company_name}"
            )

            console.print(f"\n[cyan]Открываю редактор...[/cyan]")
            result = reviewer.review(current_markdown)

            # Handle different statuses
            if result.status == ReviewStatus.CANCELLED:
                return self._handle_cancelled(original_anketa)

            if result.status == ReviewStatus.TIMEOUT:
                console.print("\n[yellow]⏰ Время редактирования истекло[/yellow]")
                return self._handle_cancelled(original_anketa)

            if result.status == ReviewStatus.ERROR:
                console.print(f"\n[red]Ошибка: {result.errors}[/red]")
                return self._handle_cancelled(original_anketa)

            if result.status == ReviewStatus.VALIDATION_FAILED:
                errors = result.errors
                current_markdown = result.content
                console.print(f"\n[yellow]Ошибки валидации (попытка {attempt + 1}/{self.MAX_RETRIES}):[/yellow]")
                for e in errors:
                    console.print(f"  • {e}")

                if attempt < self.MAX_RETRIES - 1:
                    if Confirm.ask("Открыть редактор снова для исправления?", default=True):
                        continue
                    else:
                        return self._handle_cancelled(original_anketa)
                else:
                    console.print("[red]Превышено количество попыток[/red]")
                    return self._handle_cancelled(original_anketa)

            # Success - show diff and confirm
            if result.changed:
                changes = self.show_diff(original_markdown, result.content)

                if not Confirm.ask("Сохранить изменения?", default=True):
                    return self._handle_cancelled(original_anketa)

                # Parse changes back to model
                try:
                    updated_anketa = self.parser.parse(result.content, original_anketa)
                    console.print("\n[green]✓ Анкета обновлена[/green]")
                    return updated_anketa
                except Exception as e:
                    console.print(f"\n[red]Ошибка парсинга: {e}[/red]")
                    return self._handle_cancelled(original_anketa)
            else:
                console.print("\n[green]✓ Без изменений[/green]")
                return original_anketa

        return None

    def _config_with_errors(self, errors: list[ValidationError]) -> ReviewConfig:
        """Create config with error messages in instructions."""
        return ReviewConfig(
            instructions=self._get_instructions(errors),
            timeout_minutes=self.config.timeout_minutes,
            validator=self.config.validator,
            readonly_sections=self.config.readonly_sections,
            enable_history=self.config.enable_history,
        )

    def _handle_cancelled(self, original: FinalAnketa) -> Optional[FinalAnketa]:
        """Handle cancelled review - ask whether to save original."""
        console.print()
        choice = Prompt.ask(
            "Сохранить оригинальную версию?",
            choices=["y", "n"],
            default="y"
        )

        if choice == "y":
            console.print("[green]✓ Сохраняем оригинал[/green]")
            return original
        else:
            console.print("[yellow]Отменено[/yellow]")
            return None

    def show_preview(self, anketa: FinalAnketa) -> None:
        """Display anketa preview in CLI."""
        completion = anketa.completion_rate()
        functions_count = len(anketa.agent_functions)
        integrations_count = len(anketa.integrations)

        # Build preview table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="cyan")
        table.add_column()

        table.add_row("Компания:", anketa.company_name or "—")
        table.add_row("Отрасль:", anketa.industry or "—")
        table.add_row("Функций агента:", str(functions_count))
        table.add_row("Интеграций:", str(integrations_count))
        table.add_row("Заполненность:", f"{completion:.0f}%")

        panel = Panel(
            table,
            title="📋 Сводка анкеты",
            border_style="cyan"
        )

        console.print()
        console.print(panel)

    def prompt_action(self) -> Literal["open", "save", "cancel"]:
        """Prompt user for action."""
        console.print()
        console.print("[O] Открыть редактор")
        console.print("[S] Сохранить как есть")
        console.print("[C] Отмена")
        console.print()

        choice = Prompt.ask(
            "Выберите действие",
            choices=["o", "s", "c"],
            default="o"
        )

        return {"o": "open", "s": "save", "c": "cancel"}[choice]

    def show_diff(self, original: str, edited: str) -> dict:
        """Show diff between original and edited content."""
        changes = self.doc_parser.count_changes(original, edited)

        console.print()
        console.print(Panel(
            f"[green]+{changes['added']}[/green] добавлено  "
            f"[red]-{changes['removed']}[/red] удалено  "
            f"[yellow]~{changes['modified']}[/yellow] изменено",
            title="📝 Изменения",
            border_style="blue"
        ))

        return changes


def create_review_service(strict: bool = True) -> AnketaReviewService:
    """
    Factory function to create review service.

    Args:
        strict: Use strict validation

    Returns:
        Configured AnketaReviewService
    """
    if strict:
        return AnketaReviewService()
    else:
        config = ReviewConfig(
            instructions="Проверьте анкету",
            timeout_minutes=30,
            validator=None,  # No validation
        )
        return AnketaReviewService(config)
