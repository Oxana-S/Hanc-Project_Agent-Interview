"""
Tests for src/anketa/review_service.py

Comprehensive tests for AnketaReviewService and create_review_service factory.
Covers: initialization, instructions, finalize workflow, review-with-retry loop,
cancellation handling, preview, prompt actions, factory function, and config-with-errors.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

# Guard: agent_document_reviewer may not be importable in every environment
try:
    from src.agent_document_reviewer import (
        ReviewConfig,
        ReviewStatus,
        ValidationError,
    )
    from src.agent_document_reviewer.parser import DocumentParser

    HAS_REVIEWER = True
except ImportError:
    HAS_REVIEWER = False

pytestmark = pytest.mark.skipif(
    not HAS_REVIEWER,
    reason="agent_document_reviewer not installed",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anketa(**overrides):
    """Create a minimal FinalAnketa for testing."""
    from src.anketa.schema import FinalAnketa

    defaults = dict(
        interview_id="test-123",
        company_name="TestCorp",
        industry="IT",
    )
    defaults.update(overrides)
    return FinalAnketa(**defaults)


def _make_review_result(
    status=ReviewStatus.COMPLETED,
    changed=False,
    content="# Markdown",
    errors=None,
):
    """Build a mock ReviewResult with the given attributes."""
    result = MagicMock()
    result.status = status
    result.changed = changed
    result.content = content
    result.errors = errors or []
    return result


def _build_service(config=None):
    """
    Build an AnketaReviewService while mocking heavy dependencies
    (AnketaGenerator, AnketaMarkdownParser, DocumentParser) so we
    avoid filesystem and real editor interaction.
    """
    with patch("src.anketa.review_service.AnketaGenerator"), \
         patch("src.anketa.review_service.AnketaMarkdownParser"), \
         patch("src.anketa.review_service.DocumentParser"):
        from src.anketa.review_service import AnketaReviewService
        return AnketaReviewService(config=config)


# ===========================================================================
# 1. TestAnketaReviewServiceInit (4 tests)
# ===========================================================================

class TestAnketaReviewServiceInit:
    """Tests for AnketaReviewService.__init__."""

    def test_init_with_default_config(self):
        """Default config is created when none is supplied."""
        service = _build_service()
        assert service.config is not None
        assert isinstance(service.config, ReviewConfig)

    def test_init_with_custom_config(self):
        """A supplied config is used as-is."""
        custom = ReviewConfig(
            instructions="Custom instructions",
            timeout_minutes=10,
        )
        service = _build_service(config=custom)
        assert service.config is custom
        assert service.config.timeout_minutes == 10

    def test_default_config_has_validator(self):
        """The default config includes a validator callable."""
        service = _build_service()
        assert service.config.validator is not None
        assert callable(service.config.validator)

    def test_default_config_has_readonly_sections(self):
        """The default config protects Metadata and auto-generated sections."""
        service = _build_service()
        assert len(service.config.readonly_sections) >= 1
        joined = " ".join(service.config.readonly_sections)
        assert "Метаданные" in joined


# ===========================================================================
# 2. TestGetInstructions (3 tests)
# ===========================================================================

class TestGetInstructions:
    """Tests for AnketaReviewService._get_instructions."""

    def test_instructions_without_errors(self):
        """Base instructions are returned when no errors given."""
        service = _build_service()
        text = service._get_instructions()
        assert "ПРОВЕРКА АНКЕТЫ" in text
        assert "ОШИБКИ" not in text

    def test_instructions_with_errors_appends_error_list(self):
        """When validation errors are passed, they appear in the text."""
        service = _build_service()
        errors = [
            ValidationError(field="company_name", message="Required"),
            ValidationError(field="industry", message="Too short"),
        ]
        text = service._get_instructions(errors)
        assert "ОШИБКИ ВАЛИДАЦИИ" in text
        # Each error's __str__ should be present
        for e in errors:
            assert str(e) in text

    def test_instructions_with_empty_errors_list(self):
        """An empty errors list behaves like no errors (falsy list)."""
        service = _build_service()
        text = service._get_instructions(errors=[])
        assert "ОШИБКИ" not in text


# ===========================================================================
# 3. TestFinalize (6 tests)
# ===========================================================================

class TestFinalize:
    """Tests for AnketaReviewService.finalize."""

    def test_finalize_cancel_returns_none(self):
        """Choosing 'cancel' returns None."""
        service = _build_service()
        anketa = _make_anketa()

        with patch.object(service, "show_preview"), \
             patch.object(service, "prompt_action", return_value="cancel"), \
             patch("src.anketa.review_service.console"):
            result = service.finalize(anketa)

        assert result is None

    def test_finalize_save_returns_anketa(self):
        """Choosing 'save' returns the original anketa unchanged."""
        service = _build_service()
        anketa = _make_anketa()

        with patch.object(service, "show_preview"), \
             patch.object(service, "prompt_action", return_value="save"), \
             patch("src.anketa.review_service.console"):
            result = service.finalize(anketa)

        assert result is anketa

    def test_finalize_open_calls_review_with_retry(self):
        """Choosing 'open' delegates to _review_with_retry."""
        service = _build_service()
        anketa = _make_anketa()
        sentinel = _make_anketa(company_name="Updated")

        with patch.object(service, "show_preview"), \
             patch.object(service, "prompt_action", return_value="open"), \
             patch.object(service.generator, "_render_markdown", return_value="# MD"), \
             patch.object(service, "_review_with_retry", return_value=sentinel) as mock_rwr, \
             patch("src.anketa.review_service.console"):
            result = service.finalize(anketa)

        mock_rwr.assert_called_once_with(anketa, "# MD")
        assert result is sentinel

    def test_finalize_calls_show_preview(self):
        """show_preview is called exactly once."""
        service = _build_service()
        anketa = _make_anketa()

        with patch.object(service, "show_preview") as mock_sp, \
             patch.object(service, "prompt_action", return_value="save"), \
             patch("src.anketa.review_service.console"):
            service.finalize(anketa)

        mock_sp.assert_called_once_with(anketa)

    def test_finalize_calls_prompt_action(self):
        """prompt_action is called exactly once."""
        service = _build_service()
        anketa = _make_anketa()

        with patch.object(service, "show_preview"), \
             patch.object(service, "prompt_action", return_value="cancel") as mock_pa, \
             patch("src.anketa.review_service.console"):
            service.finalize(anketa)

        mock_pa.assert_called_once()

    def test_finalize_generates_markdown_for_editor(self):
        """When action is 'open', generator._render_markdown is called."""
        service = _build_service()
        anketa = _make_anketa()

        with patch.object(service, "show_preview"), \
             patch.object(service, "prompt_action", return_value="open"), \
             patch.object(
                 service.generator, "_render_markdown", return_value="# MD"
             ) as mock_render, \
             patch.object(service, "_review_with_retry", return_value=anketa), \
             patch("src.anketa.review_service.console"):
            service.finalize(anketa)

        mock_render.assert_called_once_with(anketa)


# ===========================================================================
# 4. TestReviewWithRetry (8 tests)
# ===========================================================================

class TestReviewWithRetry:
    """Tests for AnketaReviewService._review_with_retry."""

    # --- Cancellation / Timeout / Error ----------------------------------

    def test_review_cancelled_returns_handle_cancelled(self):
        """CANCELLED status delegates to _handle_cancelled."""
        service = _build_service()
        anketa = _make_anketa()
        mock_result = _make_review_result(status=ReviewStatus.CANCELLED)

        with patch("src.anketa.review_service.DocumentReviewer") as MockRev, \
             patch.object(service, "_handle_cancelled", return_value=anketa) as mock_hc, \
             patch("src.anketa.review_service.console"):
            MockRev.return_value.review.return_value = mock_result
            result = service._review_with_retry(anketa, "# md")

        mock_hc.assert_called_once_with(anketa)
        assert result is anketa

    def test_review_timeout_returns_handle_cancelled(self):
        """TIMEOUT status delegates to _handle_cancelled."""
        service = _build_service()
        anketa = _make_anketa()
        mock_result = _make_review_result(status=ReviewStatus.TIMEOUT)

        with patch("src.anketa.review_service.DocumentReviewer") as MockRev, \
             patch.object(service, "_handle_cancelled", return_value=None) as mock_hc, \
             patch("src.anketa.review_service.console"):
            MockRev.return_value.review.return_value = mock_result
            result = service._review_with_retry(anketa, "# md")

        mock_hc.assert_called_once_with(anketa)
        assert result is None

    def test_review_error_returns_handle_cancelled(self):
        """ERROR status delegates to _handle_cancelled."""
        service = _build_service()
        anketa = _make_anketa()
        mock_result = _make_review_result(
            status=ReviewStatus.ERROR,
            errors=["Something broke"],
        )

        with patch("src.anketa.review_service.DocumentReviewer") as MockRev, \
             patch.object(service, "_handle_cancelled", return_value=anketa) as mock_hc, \
             patch("src.anketa.review_service.console"):
            MockRev.return_value.review.return_value = mock_result
            result = service._review_with_retry(anketa, "# md")

        mock_hc.assert_called_once_with(anketa)
        assert result is anketa

    # --- Validation failures ---------------------------------------------

    def test_review_validation_failed_retries(self):
        """VALIDATION_FAILED + user confirms retry -> opens editor again."""
        service = _build_service()
        anketa = _make_anketa()

        fail_result = _make_review_result(
            status=ReviewStatus.VALIDATION_FAILED,
            content="# fixed",
            errors=[ValidationError(field="x", message="bad")],
        )
        ok_result = _make_review_result(
            status=ReviewStatus.COMPLETED,
            changed=False,
            content="# fixed",
        )

        mock_reviewer_instance = MagicMock()
        mock_reviewer_instance.review.side_effect = [fail_result, ok_result]

        with patch("src.anketa.review_service.DocumentReviewer", return_value=mock_reviewer_instance), \
             patch("src.anketa.review_service.Confirm.ask", return_value=True), \
             patch("src.anketa.review_service.console"):
            result = service._review_with_retry(anketa, "# md")

        # Two calls: first fails validation, second succeeds
        assert mock_reviewer_instance.review.call_count == 2
        assert result is anketa  # no changes -> returns original

    def test_review_validation_failed_max_retries_exceeded(self):
        """All MAX_RETRIES exhausted with VALIDATION_FAILED -> _handle_cancelled."""
        service = _build_service()
        anketa = _make_anketa()

        fail_result = _make_review_result(
            status=ReviewStatus.VALIDATION_FAILED,
            content="# bad",
            errors=[ValidationError(field="x", message="bad")],
        )

        mock_reviewer_instance = MagicMock()
        mock_reviewer_instance.review.return_value = fail_result

        with patch("src.anketa.review_service.DocumentReviewer", return_value=mock_reviewer_instance), \
             patch("src.anketa.review_service.Confirm.ask", return_value=True), \
             patch.object(service, "_handle_cancelled", return_value=None) as mock_hc, \
             patch("src.anketa.review_service.console"):
            result = service._review_with_retry(anketa, "# md")

        assert mock_reviewer_instance.review.call_count == service.MAX_RETRIES
        mock_hc.assert_called_once_with(anketa)
        assert result is None

    # --- Success paths ---------------------------------------------------

    def test_review_success_with_changes_confirmed(self):
        """Changed content + user confirms -> parser.parse returns updated anketa."""
        service = _build_service()
        anketa = _make_anketa()
        updated = _make_anketa(company_name="NewCorp")

        ok_result = _make_review_result(
            status=ReviewStatus.COMPLETED,
            changed=True,
            content="# edited",
        )

        with patch("src.anketa.review_service.DocumentReviewer") as MockRev, \
             patch("src.anketa.review_service.Confirm.ask", return_value=True), \
             patch.object(service, "show_diff", return_value={"added": 1, "removed": 0, "modified": 0, "total": 1}), \
             patch.object(service.parser, "parse", return_value=updated) as mock_parse, \
             patch("src.anketa.review_service.console"):
            MockRev.return_value.review.return_value = ok_result
            result = service._review_with_retry(anketa, "# md")

        mock_parse.assert_called_once_with("# edited", anketa)
        assert result is updated

    def test_review_success_with_changes_declined(self):
        """Changed content + user declines -> _handle_cancelled."""
        service = _build_service()
        anketa = _make_anketa()

        ok_result = _make_review_result(
            status=ReviewStatus.COMPLETED,
            changed=True,
            content="# edited",
        )

        with patch("src.anketa.review_service.DocumentReviewer") as MockRev, \
             patch("src.anketa.review_service.Confirm.ask", return_value=False), \
             patch.object(service, "show_diff", return_value={"added": 1, "removed": 0, "modified": 0, "total": 1}), \
             patch.object(service, "_handle_cancelled", return_value=anketa) as mock_hc, \
             patch("src.anketa.review_service.console"):
            MockRev.return_value.review.return_value = ok_result
            result = service._review_with_retry(anketa, "# md")

        mock_hc.assert_called_once_with(anketa)
        assert result is anketa

    def test_review_success_no_changes_returns_original(self):
        """No changes -> returns original anketa immediately."""
        service = _build_service()
        anketa = _make_anketa()

        ok_result = _make_review_result(
            status=ReviewStatus.COMPLETED,
            changed=False,
            content="# md",
        )

        with patch("src.anketa.review_service.DocumentReviewer") as MockRev, \
             patch("src.anketa.review_service.console"):
            MockRev.return_value.review.return_value = ok_result
            result = service._review_with_retry(anketa, "# md")

        assert result is anketa


# ===========================================================================
# 5. TestHandleCancelled (2 tests)
# ===========================================================================

class TestHandleCancelled:
    """Tests for AnketaReviewService._handle_cancelled."""

    def test_handle_cancelled_save_original(self):
        """User chooses 'y' -> returns the original anketa."""
        service = _build_service()
        anketa = _make_anketa()

        with patch("src.anketa.review_service.Prompt.ask", return_value="y"), \
             patch("src.anketa.review_service.console"):
            result = service._handle_cancelled(anketa)

        assert result is anketa

    def test_handle_cancelled_discard(self):
        """User chooses 'n' -> returns None."""
        service = _build_service()
        anketa = _make_anketa()

        with patch("src.anketa.review_service.Prompt.ask", return_value="n"), \
             patch("src.anketa.review_service.console"):
            result = service._handle_cancelled(anketa)

        assert result is None


# ===========================================================================
# 6. TestShowPreview (2 tests)
# ===========================================================================

class TestShowPreview:
    """Tests for AnketaReviewService.show_preview."""

    def test_show_preview_does_not_raise(self):
        """show_preview runs without raising for a valid anketa."""
        service = _build_service()
        anketa = _make_anketa(company_name="PreviewCo", industry="Finance")

        with patch("src.anketa.review_service.console"):
            service.show_preview(anketa)  # should not raise

    def test_show_preview_uses_anketa_fields(self):
        """show_preview accesses company_name and industry from the anketa."""
        service = _build_service()
        anketa = _make_anketa(company_name="Acme", industry="Retail")

        with patch("src.anketa.review_service.console") as mock_console:
            service.show_preview(anketa)

        # console.print is called at least once (for the Panel)
        assert mock_console.print.called


# ===========================================================================
# 7. TestPromptAction (3 tests)
# ===========================================================================

class TestPromptAction:
    """Tests for AnketaReviewService.prompt_action."""

    def test_prompt_action_open(self):
        """Choice 'o' maps to 'open'."""
        service = _build_service()
        with patch("src.anketa.review_service.Prompt.ask", return_value="o"), \
             patch("src.anketa.review_service.console"):
            assert service.prompt_action() == "open"

    def test_prompt_action_save(self):
        """Choice 's' maps to 'save'."""
        service = _build_service()
        with patch("src.anketa.review_service.Prompt.ask", return_value="s"), \
             patch("src.anketa.review_service.console"):
            assert service.prompt_action() == "save"

    def test_prompt_action_cancel(self):
        """Choice 'c' maps to 'cancel'."""
        service = _build_service()
        with patch("src.anketa.review_service.Prompt.ask", return_value="c"), \
             patch("src.anketa.review_service.console"):
            assert service.prompt_action() == "cancel"


# ===========================================================================
# 8. TestCreateReviewService (2 tests)
# ===========================================================================

class TestCreateReviewService:
    """Tests for the create_review_service factory function."""

    def test_create_strict_service(self):
        """strict=True creates a service with a validator."""
        with patch("src.anketa.review_service.AnketaGenerator"), \
             patch("src.anketa.review_service.AnketaMarkdownParser"), \
             patch("src.anketa.review_service.DocumentParser"):
            from src.anketa.review_service import create_review_service

            service = create_review_service(strict=True)

        assert service.config.validator is not None

    def test_create_non_strict_service_no_validator(self):
        """strict=False creates a service without a validator."""
        with patch("src.anketa.review_service.AnketaGenerator"), \
             patch("src.anketa.review_service.AnketaMarkdownParser"), \
             patch("src.anketa.review_service.DocumentParser"):
            from src.anketa.review_service import create_review_service

            service = create_review_service(strict=False)

        assert service.config.validator is None


# ===========================================================================
# 9. TestConfigWithErrors (2 tests)
# ===========================================================================

class TestConfigWithErrors:
    """Tests for AnketaReviewService._config_with_errors."""

    def test_config_with_errors_creates_new_config(self):
        """_config_with_errors returns a NEW ReviewConfig containing error text."""
        service = _build_service()
        errors = [ValidationError(field="name", message="Missing")]
        new_config = service._config_with_errors(errors)

        assert new_config is not service.config
        assert isinstance(new_config, ReviewConfig)
        assert "ОШИБКИ ВАЛИДАЦИИ" in new_config.instructions

    def test_config_with_errors_preserves_timeout(self):
        """The new config preserves timeout_minutes from the original config."""
        custom = ReviewConfig(
            instructions="base",
            timeout_minutes=42,
        )
        service = _build_service(config=custom)
        errors = [ValidationError(field="x", message="y")]
        new_config = service._config_with_errors(errors)

        assert new_config.timeout_minutes == 42
