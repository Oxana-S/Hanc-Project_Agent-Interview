"""
Unit tests for CLI interface.
"""

import pytest
from unittest.mock import MagicMock
from io import StringIO

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models import (
    InterviewContext, InterviewPattern, InterviewStatus,
    QuestionStatus, QuestionResponse
)


class TestInterviewCLI:
    """Test InterviewCLI class."""

    def test_cli_initialization(self, mock_voice_agent):
        """Test CLI initializes with agent."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)

        assert cli.agent == mock_voice_agent
        assert cli.console is not None

    def test_get_status_emoji_in_progress(self, mock_voice_agent):
        """Test status emoji for IN_PROGRESS."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_status_emoji(InterviewStatus.IN_PROGRESS)

        assert "In Progress" in result

    def test_get_status_emoji_completed(self, mock_voice_agent):
        """Test status emoji for COMPLETED."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_status_emoji(InterviewStatus.COMPLETED)

        assert "Completed" in result

    def test_get_status_emoji_paused(self, mock_voice_agent):
        """Test status emoji for PAUSED."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_status_emoji(InterviewStatus.PAUSED)

        assert "Paused" in result

    def test_get_status_emoji_initiated(self, mock_voice_agent):
        """Test status emoji for INITIATED."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_status_emoji(InterviewStatus.INITIATED)

        assert "Initiated" in result

    def test_get_status_emoji_failed(self, mock_voice_agent):
        """Test status emoji for FAILED."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_status_emoji(InterviewStatus.FAILED)

        assert "Failed" in result

    def test_get_question_status_emoji_pending(self, mock_voice_agent):
        """Test question status emoji for PENDING."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_question_status_emoji(QuestionStatus.PENDING)

        assert "Pending" in result

    def test_get_question_status_emoji_answered(self, mock_voice_agent):
        """Test question status emoji for ANSWERED."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_question_status_emoji(QuestionStatus.ANSWERED)

        assert "Answered" in result

    def test_get_question_status_emoji_complete(self, mock_voice_agent):
        """Test question status emoji for COMPLETE."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        result = cli._get_question_status_emoji(QuestionStatus.COMPLETE)

        assert "Complete" in result

    def test_get_section_progress(self, mock_voice_agent, sample_interview_context):
        """Test section progress calculation."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        sections = cli._get_section_progress(sample_interview_context)

        assert "Test Section" in sections
        assert sections["Test Section"][1] == 3  # Total questions in test section

    def test_get_section_progress_with_completed(self, mock_voice_agent, sample_interview_context):
        """Test section progress with completed questions."""
        from cli_interface import InterviewCLI

        # Mark one question as COMPLETE (only COMPLETE/SKIPPED count in progress)
        sample_interview_context.questions[0].status = QuestionStatus.COMPLETE

        cli = InterviewCLI(mock_voice_agent)
        sections = cli._get_section_progress(sample_interview_context)

        # Should show 1 completed out of 3
        assert sections["Test Section"][0] == 1

    def test_create_dashboard(self, mock_voice_agent, sample_interview_context):
        """Test dashboard creation."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        mock_voice_agent.context = sample_interview_context

        layout = cli.create_dashboard(sample_interview_context)

        assert layout is not None

    def test_create_dashboard_shows_progress(self, mock_voice_agent, sample_interview_context):
        """Test dashboard shows progress information."""
        from cli_interface import InterviewCLI

        sample_interview_context.answered_questions = 5
        sample_interview_context.total_questions = 10

        cli = InterviewCLI(mock_voice_agent)
        layout = cli.create_dashboard(sample_interview_context)

        # Layout should be created successfully
        assert layout is not None

    def test_show_completion_summary_no_context(self, mock_voice_agent, capsys):
        """Test completion summary with no context."""
        from cli_interface import InterviewCLI

        cli = InterviewCLI(mock_voice_agent)
        mock_voice_agent.context = None

        # Should not raise error
        cli.show_completion_summary()


class TestCLIBanners:
    """Test CLI banner functions."""

    def test_print_welcome_banner(self, capsys):
        """Test welcome banner output."""
        from cli_interface import print_welcome_banner

        print_welcome_banner()

        captured = capsys.readouterr()
        assert "VOICE INTERVIEWER AGENT" in captured.out

    def test_print_pattern_selection(self, capsys):
        """Test pattern selection output."""
        from cli_interface import print_pattern_selection

        print_pattern_selection()

        captured = capsys.readouterr()
        assert "INTERACTION" in captured.out
        assert "MANAGEMENT" in captured.out
