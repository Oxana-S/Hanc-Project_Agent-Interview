"""
Data models for DocumentReviewer module.

Contains:
- ReviewResult: Result of document review
- ReviewConfig: Configuration for review session
- DocumentVersion: Version history entry
- ValidationError: Validation error details
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Any, Dict
from enum import Enum


class ReviewStatus(Enum):
    """Status of review session."""
    COMPLETED = "completed"      # User finished editing
    CANCELLED = "cancelled"      # User cancelled (empty file)
    TIMEOUT = "timeout"          # Session timed out
    ERROR = "error"              # Error occurred
    VALIDATION_FAILED = "validation_failed"  # Validation failed


@dataclass
class ValidationError:
    """Validation error details."""
    field: str
    message: str
    line: Optional[int] = None
    severity: str = "error"  # "error", "warning"

    def __str__(self) -> str:
        loc = f" (line {self.line})" if self.line else ""
        return f"[{self.severity.upper()}] {self.field}{loc}: {self.message}"


@dataclass
class DocumentVersion:
    """Single version in document history."""
    version: int
    content: str
    created_at: datetime
    author: str = "user"
    comment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "author": self.author,
            "comment": self.comment
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentVersion":
        """Create from dictionary."""
        return cls(
            version=data["version"],
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
            author=data.get("author", "user"),
            comment=data.get("comment")
        )


@dataclass
class ReviewResult:
    """Result of document review session."""
    status: ReviewStatus
    changed: bool
    content: str
    original_content: str
    version: int
    errors: List[ValidationError] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        """Check if review completed successfully."""
        return self.status == ReviewStatus.COMPLETED

    @property
    def diff_lines(self) -> int:
        """Count of changed lines."""
        if not self.changed:
            return 0
        original_lines = set(self.original_content.splitlines())
        new_lines = set(self.content.splitlines())
        return len(original_lines.symmetric_difference(new_lines))


@dataclass
class ReviewConfig:
    """Configuration for document review session."""

    # Editor settings
    editor: Optional[str] = None  # None = auto-detect from $EDITOR
    editor_args: List[str] = field(default_factory=list)

    # Timeout
    timeout_minutes: int = 30

    # History
    enable_history: bool = True
    max_history_versions: int = 10

    # Instructions shown at top of document
    instructions: Optional[str] = None
    instructions_prefix: str = "<!-- ИНСТРУКЦИИ (не редактируйте этот блок)\n"
    instructions_suffix: str = "\n-->\n\n"

    # Readonly sections (patterns)
    readonly_sections: List[str] = field(default_factory=list)
    readonly_marker: str = "<!-- READONLY -->"

    # Validation
    validator: Optional[Callable[[str], List[ValidationError]]] = None
    allow_save_with_warnings: bool = True

    # File settings
    temp_file_prefix: str = "review_"
    temp_file_suffix: str = ".md"
    encoding: str = "utf-8"

    # Behavior
    show_diff_on_save: bool = False
    confirm_on_large_changes: bool = False
    large_change_threshold: int = 50  # lines

    def with_instructions(self, text: str) -> "ReviewConfig":
        """Return new config with instructions set."""
        import copy
        new_config = copy.copy(self)
        new_config.instructions = text
        return new_config

    def with_validator(self, func: Callable[[str], List[ValidationError]]) -> "ReviewConfig":
        """Return new config with validator set."""
        import copy
        new_config = copy.copy(self)
        new_config.validator = func
        return new_config


# Default configurations for common use cases
DEFAULT_CONFIG = ReviewConfig()

STRICT_CONFIG = ReviewConfig(
    timeout_minutes=15,
    allow_save_with_warnings=False,
    confirm_on_large_changes=True
)

QUICK_EDIT_CONFIG = ReviewConfig(
    timeout_minutes=5,
    enable_history=False,
    instructions=None
)
