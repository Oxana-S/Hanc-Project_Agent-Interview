"""
Unit tests for VoiceInterviewerAgent.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models import (
    InterviewPattern, InterviewStatus, QuestionStatus,
    AnswerAnalysis, AnalysisStatus, QuestionResponse
)


class TestVoiceInterviewerAgentInit:
    """Test VoiceInterviewerAgent initialization."""

    def test_agent_initialization_interaction(self, mock_voice_agent):
        """Test agent initializes with INTERACTION pattern."""
        assert mock_voice_agent.pattern == InterviewPattern.INTERACTION
        assert len(mock_voice_agent.questions) > 0
        assert mock_voice_agent.context is None

    def test_agent_initialization_management(
        self, mock_redis_manager, mock_postgres_manager, mock_agent_dependencies
    ):
        """Test agent initializes with MANAGEMENT pattern."""
        from voice_interviewer_agent import VoiceInterviewerAgent

        agent = VoiceInterviewerAgent(
            pattern=InterviewPattern.MANAGEMENT,
            redis_manager=mock_redis_manager,
            postgres_manager=mock_postgres_manager,
            **mock_agent_dependencies
        )

        assert agent.pattern == InterviewPattern.MANAGEMENT
        assert len(agent.questions) > 0

    def test_agent_has_max_clarifications(self, mock_voice_agent):
        """Test agent has max_clarifications parameter."""
        assert mock_voice_agent.max_clarifications == 3

    def test_agent_has_min_answer_length(self, mock_voice_agent):
        """Test agent has min_answer_length parameter."""
        assert mock_voice_agent.min_answer_length == 15

    def test_agent_loads_questions(self, mock_voice_agent):
        """Test agent loads questions based on pattern."""
        assert len(mock_voice_agent.questions) > 0
        assert all(hasattr(q, 'id') and hasattr(q, 'text') for q in mock_voice_agent.questions)


class TestVoiceInterviewerAgentStartInterview:
    """Test VoiceInterviewerAgent.start_interview() method."""

    @pytest.mark.asyncio
    async def test_start_interview_new(self, mock_voice_agent):
        """Test starting new interview."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        context = await mock_voice_agent.start_interview()

        assert context is not None
        assert context.status == InterviewStatus.IN_PROGRESS
        assert mock_voice_agent.context == context
        mock_voice_agent.redis_manager.save_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_interview_sets_total_questions(self, mock_voice_agent):
        """Test start_interview sets correct total_questions."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        context = await mock_voice_agent.start_interview()

        assert context.total_questions == len(mock_voice_agent.questions)

    @pytest.mark.asyncio
    async def test_start_interview_initializes_questions(self, mock_voice_agent):
        """Test start_interview initializes questions list."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        context = await mock_voice_agent.start_interview()

        assert len(context.questions) > 0
        assert all(q.status == QuestionStatus.PENDING for q in context.questions)

    @pytest.mark.asyncio
    async def test_start_interview_resume_existing(self, mock_voice_agent, sample_interview_context):
        """Test resuming existing interview by session_id."""
        mock_voice_agent.redis_manager.load_context = AsyncMock(return_value=sample_interview_context)

        context = await mock_voice_agent.start_interview(session_id="existing-session")

        assert context == sample_interview_context
        mock_voice_agent.redis_manager.load_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_interview_resume_not_found_creates_new(self, mock_voice_agent):
        """Test that missing session creates new interview."""
        mock_voice_agent.redis_manager.load_context = AsyncMock(return_value=None)
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        context = await mock_voice_agent.start_interview(session_id="nonexistent")

        assert context is not None
        assert context.status == InterviewStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_start_interview_saves_to_postgres(self, mock_voice_agent):
        """Test that start_interview saves session to PostgreSQL."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        context = await mock_voice_agent.start_interview()

        mock_voice_agent.postgres_manager.save_interview_session.assert_called_once()


class TestVoiceInterviewerAgentPauseResume:
    """Test VoiceInterviewerAgent pause/resume methods."""

    @pytest.mark.asyncio
    async def test_pause_interview(self, mock_voice_agent):
        """Test pausing interview."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.redis_manager.update_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        await mock_voice_agent.start_interview()
        await mock_voice_agent.pause_interview()

        assert mock_voice_agent.context.status == InterviewStatus.PAUSED

    @pytest.mark.asyncio
    async def test_resume_interview(self, mock_voice_agent):
        """Test resuming interview."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.redis_manager.update_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        await mock_voice_agent.start_interview()
        mock_voice_agent.context.status = InterviewStatus.PAUSED

        await mock_voice_agent.resume_interview()

        assert mock_voice_agent.context.status == InterviewStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_pause_updates_redis(self, mock_voice_agent):
        """Test pause_interview updates Redis."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.redis_manager.update_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        await mock_voice_agent.start_interview()
        await mock_voice_agent.pause_interview()

        mock_voice_agent.redis_manager.update_context.assert_called()


class TestVoiceInterviewerAgentAnalysis:
    """Test VoiceInterviewerAgent answer analysis."""

    @pytest.mark.asyncio
    async def test_analyze_answer_short(self, mock_voice_agent, sample_question_response):
        """Test analysis of short answer returns incomplete."""
        analysis = await mock_voice_agent._analyze_answer(
            sample_question_response,
            "Short"
        )

        assert analysis.status == AnalysisStatus.INCOMPLETE
        assert analysis.word_count < 15

    @pytest.mark.asyncio
    async def test_analyze_answer_sufficient_length(self, mock_voice_agent, sample_question_response):
        """Test analysis of sufficient length answer."""
        long_answer = "This is a comprehensive answer with many words that should be considered complete because it provides enough detail and context for the question being asked."

        analysis = await mock_voice_agent._analyze_answer(
            sample_question_response,
            long_answer
        )

        assert analysis.status == AnalysisStatus.COMPLETE
        assert analysis.word_count >= 15

    @pytest.mark.asyncio
    async def test_analyze_answer_empty(self, mock_voice_agent, sample_question_response):
        """Test analysis of empty answer."""
        analysis = await mock_voice_agent._analyze_answer(
            sample_question_response,
            ""
        )

        assert analysis.status == AnalysisStatus.INCOMPLETE
        assert analysis.word_count == 0


class TestVoiceInterviewerAgentClarifications:
    """Test VoiceInterviewerAgent clarification handling."""

    @pytest.mark.asyncio
    async def test_handle_clarifications_none_needed(self, mock_voice_agent, sample_question_response, sample_answer_analysis):
        """Test no clarifications when analysis is complete."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        await mock_voice_agent.start_interview()

        # Analysis with no clarification questions
        await mock_voice_agent._handle_clarifications(
            sample_question_response,
            sample_answer_analysis
        )

        # Should not call speak for clarifications (analysis has no clarification_questions)
        # Note: speak might be called 0 times if no clarifications needed

    @pytest.mark.asyncio
    async def test_handle_clarifications_with_questions(
        self, mock_voice_agent, sample_question_response, sample_incomplete_analysis
    ):
        """Test handling clarifications when needed."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        await mock_voice_agent.start_interview()

        # Add the question to context first
        mock_voice_agent.context.questions.append(sample_question_response)
        mock_voice_agent.context.add_response(
            sample_question_response.question_id,
            sample_question_response.question_text,
            "Initial answer"
        )

        await mock_voice_agent._handle_clarifications(
            sample_question_response,
            sample_incomplete_analysis
        )

        # Should have called speak for clarifications
        assert mock_voice_agent._speak.call_count > 0


class TestVoiceInterviewerAgentRunCycle:
    """Test VoiceInterviewerAgent.run_interview_cycle() method."""

    @pytest.mark.asyncio
    async def test_run_interview_cycle_requires_start(self, mock_voice_agent):
        """Test run_interview_cycle raises error if not started."""
        with pytest.raises(ValueError, match="Interview not started"):
            await mock_voice_agent.run_interview_cycle()

    @pytest.mark.asyncio
    async def test_run_interview_cycle_calls_greeting(self, mock_voice_agent):
        """Test run_interview_cycle calls greeting."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.redis_manager.update_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.update_interview_session = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_anketa = AsyncMock(return_value=True)

        # Start with just 1 question for speed
        mock_voice_agent.questions = mock_voice_agent.questions[:1]

        await mock_voice_agent.start_interview()
        await mock_voice_agent.run_interview_cycle()

        # Speak should have been called (for greeting and question)
        assert mock_voice_agent._speak.call_count >= 1


class TestVoiceInterviewerAgentComplete:
    """Test VoiceInterviewerAgent completion methods."""

    @pytest.mark.asyncio
    async def test_complete_interview_generates_anketa(self, mock_voice_agent):
        """Test _complete_interview generates anketa."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.update_interview_session = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_anketa = AsyncMock(return_value=True)

        await mock_voice_agent.start_interview()

        # Add some responses
        for q in mock_voice_agent.context.questions[:3]:
            mock_voice_agent.context.add_response(
                q.question_id,
                q.question_text,
                "Test answer with enough words for validation"
            )
            mock_voice_agent.context.mark_question_complete(q.question_id)

        await mock_voice_agent._complete_interview()

        assert mock_voice_agent.context.status == InterviewStatus.COMPLETED
        mock_voice_agent.postgres_manager.save_anketa.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_anketa(self, mock_voice_agent):
        """Test _generate_anketa creates proper anketa."""
        mock_voice_agent.redis_manager.save_context = AsyncMock(return_value=True)
        mock_voice_agent.postgres_manager.save_interview_session = AsyncMock(return_value=True)

        await mock_voice_agent.start_interview()

        # Add minimum required responses
        for q in mock_voice_agent.context.questions:
            mock_voice_agent.context.add_response(
                q.question_id,
                q.question_text,
                "Test answer"
            )

        anketa = await mock_voice_agent._generate_anketa()

        assert anketa is not None
        assert anketa.interview_id == mock_voice_agent.context.interview_id
        assert anketa.pattern == mock_voice_agent.pattern
