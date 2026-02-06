"""
DocumentReviewer - Main class for document review functionality.

Orchestrates:
- External editor integration
- Document parsing and validation
- Version history management
- Review workflow
"""

from pathlib import Path
from typing import Optional, List, Callable

import structlog

from .models import (
    ReviewConfig,
    ReviewResult,
    ReviewStatus,
    ValidationError,
    DEFAULT_CONFIG
)
from .editor import ExternalEditor, EditorError
from .parser import DocumentParser
from .history import VersionHistory, create_history
from .validators import create_validator, Validator

logger = structlog.get_logger("anketa")


class DocumentReviewer:
    """
    Main class for reviewing and editing documents.

    Provides a complete workflow for:
    1. Preparing document with instructions
    2. Opening in external editor
    3. Validating changes
    4. Managing version history
    5. Returning results

    Example:
        ```python
        from document_reviewer import DocumentReviewer, ReviewConfig

        config = ReviewConfig(
            instructions="Проверьте анкету и внесите правки",
            timeout_minutes=15
        )

        reviewer = DocumentReviewer(config)
        result = reviewer.review(anketa_content)

        if result.is_success and result.changed:
            save_anketa(result.content)
        ```
    """

    def __init__(
        self,
        config: Optional[ReviewConfig] = None,
        document_id: Optional[str] = None,
        persist_history: bool = False,
        history_dir: str = "output/history"
    ):
        """
        Initialize DocumentReviewer.

        Args:
            config: Review configuration (uses DEFAULT_CONFIG if None)
            document_id: Unique identifier for this document
            persist_history: Whether to persist version history to disk
            history_dir: Directory for history persistence
        """
        self.config = config or DEFAULT_CONFIG
        self.document_id = document_id

        # Initialize components
        self.editor = ExternalEditor(self.config)
        self.parser = DocumentParser(self.config)
        self.history = create_history(
            self.config,
            document_id,
            persist=persist_history,
            storage_dir=history_dir
        )

        logger.info(
            "DocumentReviewer initialized",
            document_id=document_id,
            editor=self.editor.editor_cmd,
            history_enabled=self.config.enable_history
        )

    def review(
        self,
        content: str,
        validator: Optional[Validator] = None
    ) -> ReviewResult:
        """
        Open document for review and return result.

        This is the main entry point. It:
        1. Saves original to history
        2. Prepares document with instructions
        3. Opens external editor
        4. Extracts and validates changes
        5. Saves new version to history
        6. Returns result

        Args:
            content: Document content to review
            validator: Optional custom validator function

        Returns:
            ReviewResult with status, content, and metadata
        """
        original_content = content
        temp_file = None

        try:
            # Save original version
            if self.config.enable_history:
                self.history.add_version(content, author="system", comment="Original")

            # Prepare document with instructions
            prepared_content = self.parser.prepare_for_edit(content)

            # Create temp file
            temp_file = self.editor.create_temp_file(prepared_content)

            # Open editor
            status, duration = self.editor.open_editor(temp_file)

            if status != ReviewStatus.COMPLETED:
                return ReviewResult(
                    status=status,
                    changed=False,
                    content=original_content,
                    original_content=original_content,
                    version=self.history.current_version,
                    duration_seconds=duration
                )

            # Read edited content
            edited_raw = self.editor.read_file(temp_file)

            # Check if user cancelled (empty file)
            if not edited_raw.strip():
                logger.info("Review cancelled - empty file")
                return ReviewResult(
                    status=ReviewStatus.CANCELLED,
                    changed=False,
                    content=original_content,
                    original_content=original_content,
                    version=self.history.current_version,
                    duration_seconds=duration
                )

            # Extract content (remove instructions)
            edited_content = self.parser.extract_after_edit(edited_raw)

            # Check for changes
            changed = edited_content.strip() != original_content.strip()

            # Validate
            validation_errors = self._validate(
                edited_content,
                original_content,
                validator
            )

            # Check for blocking errors
            has_errors = any(e.severity == "error" for e in validation_errors)

            if has_errors:
                logger.warning("Validation failed", errors=len(validation_errors))
                return ReviewResult(
                    status=ReviewStatus.VALIDATION_FAILED,
                    changed=changed,
                    content=edited_content,
                    original_content=original_content,
                    version=self.history.current_version,
                    errors=validation_errors,
                    duration_seconds=duration
                )

            # Save to history if changed
            if changed and self.config.enable_history:
                self.history.add_version(edited_content, author="user", comment="Edited")

            return ReviewResult(
                status=ReviewStatus.COMPLETED,
                changed=changed,
                content=edited_content,
                original_content=original_content,
                version=self.history.current_version,
                errors=validation_errors,  # warnings only
                duration_seconds=duration
            )

        except EditorError as e:
            logger.error("Editor error", error=str(e))
            return ReviewResult(
                status=ReviewStatus.ERROR,
                changed=False,
                content=original_content,
                original_content=original_content,
                version=self.history.current_version,
                errors=[ValidationError(field="editor", message=str(e))]
            )

        except Exception as e:
            logger.exception("Review failed", error=str(e))
            return ReviewResult(
                status=ReviewStatus.ERROR,
                changed=False,
                content=original_content,
                original_content=original_content,
                version=self.history.current_version,
                errors=[ValidationError(field="system", message=str(e))]
            )

        finally:
            # Cleanup temp file
            if temp_file:
                self.editor.cleanup(temp_file)

    def review_with_retry(
        self,
        content: str,
        max_retries: int = 3,
        validator: Optional[Validator] = None
    ) -> ReviewResult:
        """
        Review with automatic retry on validation failure.

        Re-opens editor with error messages if validation fails,
        allowing user to fix issues.

        Args:
            content: Document content
            max_retries: Maximum retry attempts
            validator: Optional custom validator

        Returns:
            ReviewResult from final attempt
        """
        current_content = content
        last_result = None

        for attempt in range(max_retries):
            # Add error feedback to instructions if retry
            if last_result and last_result.errors:
                error_text = self._format_errors_for_display(last_result.errors)
                retry_config = self.config.with_instructions(
                    f"{self.config.instructions or ''}\n\n"
                    f"⚠️ ОШИБКИ ВАЛИДАЦИИ (попытка {attempt + 1}):\n{error_text}"
                )
                self.config = retry_config

            result = self.review(current_content, validator)

            if result.status != ReviewStatus.VALIDATION_FAILED:
                return result

            last_result = result
            current_content = result.content

            logger.info("Retry review", attempt=attempt + 1, errors=len(result.errors))

        return last_result

    def _validate(
        self,
        content: str,
        original: str,
        custom_validator: Optional[Validator]
    ) -> List[ValidationError]:
        """Run all validations."""
        errors = []

        # Check readonly sections
        readonly_errors = self.parser.validate_readonly_preserved(original, content)
        for msg in readonly_errors:
            errors.append(ValidationError(field="readonly", message=msg))

        # Run config validator
        if self.config.validator:
            errors.extend(self.config.validator(content))

        # Run custom validator
        if custom_validator:
            errors.extend(custom_validator(content))

        return errors

    def _format_errors_for_display(self, errors: List[ValidationError]) -> str:
        """Format errors for display in instructions."""
        lines = []
        for e in errors:
            icon = "❌" if e.severity == "error" else "⚠️"
            lines.append(f"{icon} {e}")
        return "\n".join(lines)

    def get_diff(self, version1: Optional[int] = None, version2: Optional[int] = None) -> str:
        """
        Get diff between two versions.

        Args:
            version1: First version (default: previous)
            version2: Second version (default: current)

        Returns:
            Unified diff string
        """
        v2 = version2 or self.history.current_version
        v1 = version1 or v2 - 1

        ver1 = self.history.get_version(v1)
        ver2 = self.history.get_version(v2)

        if not ver1 or not ver2:
            return ""

        return self.parser.generate_diff(ver1.content, ver2.content)

    def rollback(self, version: int) -> Optional[str]:
        """
        Rollback to specific version.

        Args:
            version: Version number to rollback to

        Returns:
            Content of rolled back version or None
        """
        rolled_back = self.history.rollback_to(version)
        if rolled_back:
            return rolled_back.content
        return None


# ================== Convenience functions ==================

def review_document(
    content: str,
    instructions: Optional[str] = None,
    validator_type: str = "default",
    timeout_minutes: int = 30
) -> ReviewResult:
    """
    Quick function to review a document.

    Args:
        content: Document content
        instructions: Instructions to show
        validator_type: Type of validator ("default", "anketa", "strict_anketa", "minimal")
        timeout_minutes: Timeout for editing session

    Returns:
        ReviewResult
    """
    config = ReviewConfig(
        instructions=instructions,
        timeout_minutes=timeout_minutes,
        validator=create_validator(validator_type)
    )

    reviewer = DocumentReviewer(config)
    return reviewer.review(content)


def review_anketa(content: str, strict: bool = False) -> ReviewResult:
    """
    Review an anketa document.

    Args:
        content: Anketa markdown content
        strict: Use strict validation

    Returns:
        ReviewResult
    """
    validator_type = "strict_anketa" if strict else "anketa"

    config = ReviewConfig(
        instructions=(
            "Пожалуйста, проверьте и при необходимости отредактируйте анкету.\n"
            "После проверки сохраните файл и закройте редактор.\n"
            "Если хотите отменить изменения - удалите всё содержимое и сохраните пустой файл."
        ),
        timeout_minutes=30,
        validator=create_validator(validator_type),
        readonly_sections=[
            r'^## Метаданные',
            r'^\*Сгенерировано автоматически',
        ]
    )

    reviewer = DocumentReviewer(config, document_id="anketa")
    return reviewer.review(content)
