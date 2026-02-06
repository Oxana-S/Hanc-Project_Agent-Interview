"""
Unit tests for CLI interface.
"""

import pytest
from unittest.mock import MagicMock
from io import StringIO

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.models import (
    InterviewContext, InterviewPattern, InterviewStatus,
    QuestionStatus, QuestionResponse
)


@pytest.fixture
def mock_agent():
    """Create a mock agent for CLI tests."""
    agent = MagicMock()
    agent.context = None
    return agent


class TestInterviewCLI:
    """Test InterviewCLI class."""

    def test_cli_initialization(self, mock_agent):
        """Test CLI initializes with agent."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)

        assert cli.agent == mock_agent
        assert cli.console is not None

    def test_get_status_emoji_in_progress(self, mock_agent):
        """Test status emoji for IN_PROGRESS."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_status_emoji(InterviewStatus.IN_PROGRESS)

        assert "In Progress" in result

    def test_get_status_emoji_completed(self, mock_agent):
        """Test status emoji for COMPLETED."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_status_emoji(InterviewStatus.COMPLETED)

        assert "Completed" in result

    def test_get_status_emoji_paused(self, mock_agent):
        """Test status emoji for PAUSED."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_status_emoji(InterviewStatus.PAUSED)

        assert "Paused" in result

    def test_get_status_emoji_initiated(self, mock_agent):
        """Test status emoji for INITIATED."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_status_emoji(InterviewStatus.INITIATED)

        assert "Initiated" in result

    def test_get_status_emoji_failed(self, mock_agent):
        """Test status emoji for FAILED."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_status_emoji(InterviewStatus.FAILED)

        assert "Failed" in result

    def test_get_question_status_emoji_pending(self, mock_agent):
        """Test question status emoji for PENDING."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_question_status_emoji(QuestionStatus.PENDING)

        assert "Pending" in result

    def test_get_question_status_emoji_answered(self, mock_agent):
        """Test question status emoji for ANSWERED."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_question_status_emoji(QuestionStatus.ANSWERED)

        assert "Answered" in result

    def test_get_question_status_emoji_complete(self, mock_agent):
        """Test question status emoji for COMPLETE."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_question_status_emoji(QuestionStatus.COMPLETE)

        assert "Complete" in result

    def test_get_section_progress(self, mock_agent, sample_interview_context):
        """Test section progress calculation."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        sections = cli._get_section_progress(sample_interview_context)

        assert "Test Section" in sections
        assert sections["Test Section"][1] == 3  # Total questions in test section

    def test_get_section_progress_with_completed(self, mock_agent, sample_interview_context):
        """Test section progress with completed questions."""
        from src.cli.interface import InterviewCLI

        # Mark one question as COMPLETE (only COMPLETE/SKIPPED count in progress)
        sample_interview_context.questions[0].status = QuestionStatus.COMPLETE

        cli = InterviewCLI(mock_agent)
        sections = cli._get_section_progress(sample_interview_context)

        # Should show 1 completed out of 3
        assert sections["Test Section"][0] == 1

    def test_create_dashboard(self, mock_agent, sample_interview_context):
        """Test dashboard creation."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        mock_agent.context = sample_interview_context

        layout = cli.create_dashboard(sample_interview_context)

        assert layout is not None

    def test_create_dashboard_shows_progress(self, mock_agent, sample_interview_context):
        """Test dashboard shows progress information."""
        from src.cli.interface import InterviewCLI

        sample_interview_context.answered_questions = 5
        sample_interview_context.total_questions = 10

        cli = InterviewCLI(mock_agent)
        layout = cli.create_dashboard(sample_interview_context)

        # Layout should be created successfully
        assert layout is not None

    def test_show_completion_summary_no_context(self, mock_agent, capsys):
        """Test completion summary with no context."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        mock_agent.context = None

        # Should not raise error
        cli.show_completion_summary()


class TestCLIBanners:
    """Test CLI banner functions."""

    def test_print_welcome_banner(self, capsys):
        """Test welcome banner output."""
        from src.cli.interface import print_welcome_banner

        print_welcome_banner()

        captured = capsys.readouterr()
        assert "VOICE INTERVIEWER AGENT" in captured.out

    def test_print_pattern_selection(self, capsys):
        """Test pattern selection output."""
        from src.cli.interface import print_pattern_selection

        print_pattern_selection()

        captured = capsys.readouterr()
        assert "INTERACTION" in captured.out
        assert "MANAGEMENT" in captured.out


class TestStatusEmojiMapping:
    """Test all status emoji mappings."""

    def test_get_status_emoji_unknown(self, mock_agent):
        """Test status emoji for unknown/None status."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_status_emoji(None)

        assert "Unknown" in result

    def test_get_question_status_emoji_asked(self, mock_agent):
        """Test question status emoji for ASKED."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_question_status_emoji(QuestionStatus.ASKED)

        assert "Asked" in result

    def test_get_question_status_emoji_needs_clarification(self, mock_agent):
        """Test question status emoji for NEEDS_CLARIFICATION."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_question_status_emoji(QuestionStatus.NEEDS_CLARIFICATION)

        assert "Clarification" in result

    def test_get_question_status_emoji_skipped(self, mock_agent):
        """Test question status emoji for SKIPPED."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_question_status_emoji(QuestionStatus.SKIPPED)

        assert "Skipped" in result

    def test_get_question_status_emoji_unknown(self, mock_agent):
        """Test question status emoji for unknown/None."""
        from src.cli.interface import InterviewCLI

        cli = InterviewCLI(mock_agent)
        result = cli._get_question_status_emoji(None)

        assert "Unknown" in result


class TestSectionProgressAdvanced:
    """Advanced tests for section progress calculation."""

    def test_get_section_progress_empty_questions(self, mock_agent):
        """Test section progress with empty question list."""
        from src.cli.interface import InterviewCLI

        mock_context = MagicMock()
        mock_context.questions = []

        cli = InterviewCLI(mock_agent)
        result = cli._get_section_progress(mock_context)

        assert result == {}

    def test_get_section_progress_missing_metadata(self, mock_agent):
        """Test section progress when section metadata is missing."""
        from src.cli.interface import InterviewCLI

        mock_context = MagicMock()
        q = MagicMock()
        q.metadata = {}  # No section key
        q.status = QuestionStatus.PENDING
        mock_context.questions = [q]

        cli = InterviewCLI(mock_agent)
        result = cli._get_section_progress(mock_context)

        assert "Unknown" in result
        assert result["Unknown"] == [0, 1]

    def test_get_section_progress_multiple_sections(self, mock_agent):
        """Test section progress with multiple sections."""
        from src.cli.interface import InterviewCLI

        mock_context = MagicMock()
        q1 = MagicMock()
        q1.metadata = {"section": "Section A"}
        q1.status = QuestionStatus.COMPLETE

        q2 = MagicMock()
        q2.metadata = {"section": "Section B"}
        q2.status = QuestionStatus.PENDING

        q3 = MagicMock()
        q3.metadata = {"section": "Section A"}
        q3.status = QuestionStatus.SKIPPED

        mock_context.questions = [q1, q2, q3]

        cli = InterviewCLI(mock_agent)
        result = cli._get_section_progress(mock_context)

        assert "Section A" in result
        assert "Section B" in result
        assert result["Section A"] == [2, 2]  # Both COMPLETE and SKIPPED count
        assert result["Section B"] == [0, 1]


class TestDashboardComponents:
    """Test individual dashboard components."""

    def test_create_dashboard_with_current_question(self, mock_agent):
        """Test dashboard creation with current question."""
        from src.cli.interface import InterviewCLI

        # Create a real context with a current question at index 0
        context = InterviewContext(
            pattern=InterviewPattern.INTERACTION,
            status=InterviewStatus.IN_PROGRESS,
            total_questions=5,
            current_question_index=0
        )
        # Add a question with ASKED status and long text
        question = QuestionResponse(
            question_id="1.1",
            question_text="What is your company name? " * 10,  # Long text
            status=QuestionStatus.ASKED,
            metadata={"section": "Company Info"}
        )
        context.questions.append(question)

        cli = InterviewCLI(mock_agent)
        layout = cli.create_dashboard(context)

        assert layout is not None

    def test_create_dashboard_without_current_question(self, mock_agent):
        """Test dashboard creation without current question."""
        from src.cli.interface import InterviewCLI

        # Create context with index out of bounds (no current question)
        context = InterviewContext(
            pattern=InterviewPattern.INTERACTION,
            status=InterviewStatus.IN_PROGRESS,
            total_questions=0,
            current_question_index=0
        )
        # No questions added, so get_current_question() returns None

        cli = InterviewCLI(mock_agent)
        layout = cli.create_dashboard(context)

        assert layout is not None

    def test_create_dashboard_progress_calculation(self, mock_agent):
        """Test progress bar calculation in dashboard."""
        from src.cli.interface import InterviewCLI

        # Create context with specific progress (3 answered out of 4 = 75%)
        context = InterviewContext(
            pattern=InterviewPattern.INTERACTION,
            status=InterviewStatus.IN_PROGRESS,
            total_questions=4,
            answered_questions=3
        )
        # Add a question so there's something to display
        question = QuestionResponse(
            question_id="1.1",
            question_text="Sample question?",
            status=QuestionStatus.PENDING,
            metadata={"section": "Test"}
        )
        context.questions.append(question)

        cli = InterviewCLI(mock_agent)
        layout = cli.create_dashboard(context)

        assert layout is not None
        # Verify the progress calculation (use approx for float comparison)
        assert context.get_progress_percentage() == pytest.approx(75.0)


class TestCompletionSummary:
    """Test completion summary display."""

    def test_show_completion_summary_with_context(self, mock_agent):
        """Test completion summary with valid context."""
        from src.cli.interface import InterviewCLI

        mock_context = MagicMock()
        mock_context.interview_id = "test-interview-123"
        mock_context.total_duration_seconds = 300  # 5 minutes
        mock_context.answered_questions = 10
        mock_context.total_questions = 12
        mock_context.total_clarifications_asked = 3
        mock_context.completeness_score = 0.85

        mock_agent.context = mock_context

        cli = InterviewCLI(mock_agent)
        # Should not raise error
        cli.show_completion_summary()


class TestMonitorInterviewAsync:
    """Test async monitor_interview method."""

    @pytest.mark.asyncio
    async def test_monitor_exits_when_no_context(self, mock_agent):
        """Test monitor exits when agent has no context."""
        from src.cli.interface import InterviewCLI
        from unittest.mock import patch

        mock_agent.context = None

        cli = InterviewCLI(mock_agent)

        with patch("src.cli.interface.Live"):
            await cli.monitor_interview(update_interval=0.01)
            # Should complete without error

    @pytest.mark.asyncio
    async def test_monitor_exits_when_completed(self, mock_agent):
        """Test monitor exits when interview is completed."""
        from src.cli.interface import InterviewCLI
        from unittest.mock import patch

        # Use a real InterviewContext with COMPLETED status
        context = InterviewContext(
            pattern=InterviewPattern.INTERACTION,
            status=InterviewStatus.COMPLETED,
            total_questions=5
        )
        mock_agent.context = context

        cli = InterviewCLI(mock_agent)

        with patch("src.cli.interface.Live"):
            await cli.monitor_interview(update_interval=0.01)
            # Should complete without error


class TestCLIIntegration:
    """Integration tests for CLI."""

    def test_full_cli_workflow(self, mock_agent, sample_interview_context):
        """Test full CLI workflow from init to dashboard."""
        from src.cli.interface import InterviewCLI

        mock_agent.context = sample_interview_context

        cli = InterviewCLI(mock_agent)
        assert cli.agent == mock_agent

        # Create dashboard
        dashboard = cli.create_dashboard(sample_interview_context)
        assert dashboard is not None

        # Get section progress
        progress = cli._get_section_progress(sample_interview_context)
        assert isinstance(progress, dict)
