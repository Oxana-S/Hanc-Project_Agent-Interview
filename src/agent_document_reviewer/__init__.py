"""
DocumentReviewer - Universal document review module.

A reusable module for opening documents in external editors,
managing version history, and validating changes.

Basic usage:
    ```python
    from document_reviewer import DocumentReviewer, ReviewConfig

    # Simple review
    reviewer = DocumentReviewer()
    result = reviewer.review(my_document)

    if result.is_success:
        print("Document reviewed successfully")
        if result.changed:
            save(result.content)

    # With configuration
    config = ReviewConfig(
        instructions="Please review and edit this document",
        timeout_minutes=15,
        enable_history=True
    )
    reviewer = DocumentReviewer(config)
    result = reviewer.review(content)
    ```

For anketa documents:
    ```python
    from document_reviewer import review_anketa

    result = review_anketa(anketa_markdown)
    if result.is_success:
        # Save updated anketa
        pass
    ```
"""

from .models import (
    ReviewConfig,
    ReviewResult,
    ReviewStatus,
    ValidationError,
    DocumentVersion,
    DEFAULT_CONFIG,
    STRICT_CONFIG,
    QUICK_EDIT_CONFIG,
)

from .reviewer import (
    DocumentReviewer,
    review_document,
    review_anketa,
)

from .editor import (
    ExternalEditor,
    EditorError,
    EditorTimeoutError,
    detect_terminal_editor,
    is_gui_available,
)

from .parser import (
    DocumentParser,
    ParsedDocument,
    strip_markdown_comments,
    extract_markdown_sections,
)

from .history import (
    VersionHistory,
    InMemoryHistory,
    create_history,
)

from .validators import (
    Validator,
    create_validator,
    compose,
    not_empty,
    min_length,
    max_length,
    required_sections,
    no_empty_fields,
    markdown_valid,
    no_placeholder_text,
    anketa_validator,
    strict_anketa_validator,
)

__version__ = "1.0.0"
__author__ = "Hanc.AI"

__all__ = [
    # Main class
    "DocumentReviewer",

    # Models
    "ReviewConfig",
    "ReviewResult",
    "ReviewStatus",
    "ValidationError",
    "DocumentVersion",

    # Preset configs
    "DEFAULT_CONFIG",
    "STRICT_CONFIG",
    "QUICK_EDIT_CONFIG",

    # Convenience functions
    "review_document",
    "review_anketa",

    # Editor
    "ExternalEditor",
    "EditorError",
    "EditorTimeoutError",
    "detect_terminal_editor",
    "is_gui_available",

    # Parser
    "DocumentParser",
    "ParsedDocument",
    "strip_markdown_comments",
    "extract_markdown_sections",

    # History
    "VersionHistory",
    "InMemoryHistory",
    "create_history",

    # Validators
    "Validator",
    "create_validator",
    "compose",
    "not_empty",
    "min_length",
    "max_length",
    "required_sections",
    "no_empty_fields",
    "markdown_valid",
    "no_placeholder_text",
    "anketa_validator",
    "strict_anketa_validator",
]
