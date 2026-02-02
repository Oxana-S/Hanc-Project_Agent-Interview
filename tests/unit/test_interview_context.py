"""
Extended tests for InterviewContext methods.
"""

import pytest
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.models import (
    InterviewContext, InterviewPattern, InterviewStatus,
    QuestionResponse, QuestionStatus, AnswerAnalysis, AnalysisStatus
)


class TestInterviewContextAddResponse:
    """Test InterviewContext.add_response() method."""

    def test_add_response_new_question(self, sample_interview_context):
        """Test adding response to existing question."""
        response = sample_interview_context.add_response(
            question_id="1.1",
            question_text="Sample question 1?",
            answer="This is a test answer with enough words to pass validation"
        )
        assert response.answer == "This is a test answer with enough words to pass validation"
        assert response.status == QuestionStatus.ANSWERED
        assert sample_interview_context.answered_questions == 1

    def test_add_response_creates_question_if_not_exists(self, sample_interview_context):
        """Test that add_response creates question if it doesn't exist."""
        initial_count = len(sample_interview_context.questions)
        response = sample_interview_context.add_response(
            question_id="new.1",
            question_text="New question?",
            answer="New answer"
        )
        assert len(sample_interview_context.questions) == initial_count + 1
        assert response.question_id == "new.1"

    def test_add_response_updates_answered_at(self, sample_interview_context):
        """Test that add_response sets answered_at timestamp."""
        response = sample_interview_context.add_response(
            question_id="1.1",
            question_text="Test?",
            answer="Answer"
        )
        assert response.answered_at is not None
        assert isinstance(response.answered_at, datetime)

    def test_add_response_with_audio_duration(self, sample_interview_context):
        """Test add_response with audio duration."""
        response = sample_interview_context.add_response(
            question_id="1.1",
            question_text="Test?",
            answer="Answer",
            audio_duration=15.5
        )
        assert response.audio_duration_seconds == 15.5

    def test_add_response_updates_context_timestamp(self, sample_interview_context):
        """Test that add_response updates context.updated_at."""
        old_updated_at = sample_interview_context.updated_at
        sample_interview_context.add_response(
            question_id="1.1",
            question_text="Test?",
            answer="Answer"
        )
        assert sample_interview_context.updated_at >= old_updated_at


class TestInterviewContextAddClarification:
    """Test InterviewContext.add_clarification() method."""

    def test_add_clarification_success(self, sample_interview_context):
        """Test adding clarification to existing question."""
        # First add a response
        sample_interview_context.add_response(
            question_id="1.1",
            question_text="Test?",
            answer="Initial answer"
        )

        clarification = sample_interview_context.add_clarification(
            question_id="1.1",
            clarification_text="Please provide more detail",
            answer="Here are more details"
        )

        assert clarification.question == "Please provide more detail"
        assert clarification.answer == "Here are more details"
        assert sample_interview_context.total_clarifications_asked == 1

    def test_add_clarification_without_answer(self, sample_interview_context):
        """Test adding clarification without answer."""
        sample_interview_context.add_response("1.1", "Test?", "Answer")

        clarification = sample_interview_context.add_clarification(
            question_id="1.1",
            clarification_text="More details please?"
        )

        assert clarification.answer is None

    def test_add_clarification_invalid_question(self, sample_interview_context):
        """Test that add_clarification raises error for invalid question."""
        with pytest.raises(ValueError, match="not found"):
            sample_interview_context.add_clarification(
                question_id="invalid_id",
                clarification_text="Test"
            )

    def test_multiple_clarifications_on_question(self, sample_interview_context):
        """Test adding multiple clarifications to same question."""
        sample_interview_context.add_response("1.1", "Test?", "Initial answer")

        for i in range(3):
            sample_interview_context.add_clarification(
                question_id="1.1",
                clarification_text=f"Clarification question {i+1}",
                answer=f"Clarification answer {i+1}"
            )

        question = next(q for q in sample_interview_context.questions if q.question_id == "1.1")
        assert len(question.clarifications) == 3
        assert sample_interview_context.total_clarifications_asked == 3


class TestInterviewContextUpdateAnalysis:
    """Test InterviewContext.update_analysis() method."""

    def test_update_analysis_complete(self, sample_interview_context, sample_answer_analysis):
        """Test update_analysis with complete status."""
        sample_interview_context.add_response("1.1", "Test?", "Test answer")
        sample_interview_context.update_analysis("1.1", sample_answer_analysis)

        question = next(q for q in sample_interview_context.questions if q.question_id == "1.1")
        assert question.analysis == sample_answer_analysis
        assert question.status == QuestionStatus.COMPLETE

    def test_update_analysis_incomplete(self, sample_interview_context, sample_incomplete_analysis):
        """Test update_analysis marks needs_clarification for incomplete."""
        sample_interview_context.add_response("1.1", "Test?", "Short answer")
        sample_interview_context.update_analysis("1.1", sample_incomplete_analysis)

        question = next(q for q in sample_interview_context.questions if q.question_id == "1.1")
        assert question.status == QuestionStatus.NEEDS_CLARIFICATION

    def test_update_analysis_vague(self, sample_interview_context):
        """Test update_analysis with vague status."""
        sample_interview_context.add_response("1.1", "Test?", "Vague answer")

        analysis = AnswerAnalysis(
            status=AnalysisStatus.VAGUE,
            completeness_score=0.5,
            word_count=5,
            has_examples=False,
            has_specifics=False,
            confidence=0.6,
            reasoning="Answer is vague"
        )
        sample_interview_context.update_analysis("1.1", analysis)

        question = next(q for q in sample_interview_context.questions if q.question_id == "1.1")
        assert question.status == QuestionStatus.NEEDS_CLARIFICATION

    def test_update_analysis_invalid_question(self, sample_interview_context, sample_answer_analysis):
        """Test update_analysis raises error for invalid question."""
        with pytest.raises(ValueError, match="not found"):
            sample_interview_context.update_analysis("invalid_id", sample_answer_analysis)


class TestInterviewContextProgress:
    """Test InterviewContext progress methods."""

    def test_get_progress_percentage_zero(self, sample_interview_context):
        """Test progress is 0 when no questions answered."""
        sample_interview_context.total_questions = 10
        sample_interview_context.answered_questions = 0
        assert sample_interview_context.get_progress_percentage() == 0.0

    def test_get_progress_percentage_partial(self, sample_interview_context):
        """Test progress calculation with partial completion."""
        sample_interview_context.total_questions = 10
        sample_interview_context.answered_questions = 5
        assert sample_interview_context.get_progress_percentage() == 50.0

    def test_get_progress_percentage_complete(self, sample_interview_context):
        """Test progress is 100 when all questions answered."""
        sample_interview_context.total_questions = 10
        sample_interview_context.answered_questions = 10
        assert sample_interview_context.get_progress_percentage() == 100.0

    def test_get_progress_percentage_no_questions(self, sample_interview_context):
        """Test progress is 0 when total_questions is 0."""
        sample_interview_context.total_questions = 0
        assert sample_interview_context.get_progress_percentage() == 0.0


class TestInterviewContextCurrentQuestion:
    """Test InterviewContext.get_current_question() method."""

    def test_get_current_question_first(self, sample_interview_context):
        """Test getting first question."""
        current = sample_interview_context.get_current_question()
        assert current is not None
        assert current.question_id == "1.1"

    def test_get_current_question_after_advance(self, sample_interview_context):
        """Test getting question after advancing index."""
        sample_interview_context.current_question_index = 1
        current = sample_interview_context.get_current_question()
        assert current.question_id == "1.2"

    def test_get_current_question_out_of_bounds(self, sample_interview_context):
        """Test None returned when index out of bounds."""
        sample_interview_context.current_question_index = 100
        current = sample_interview_context.get_current_question()
        assert current is None


class TestInterviewContextMarkComplete:
    """Test InterviewContext.mark_question_complete() method."""

    def test_mark_question_complete(self, sample_interview_context):
        """Test marking question as complete advances index."""
        initial_index = sample_interview_context.current_question_index
        sample_interview_context.add_response("1.1", "Test?", "Answer")
        sample_interview_context.mark_question_complete("1.1")

        question = next(q for q in sample_interview_context.questions if q.question_id == "1.1")
        assert question.status == QuestionStatus.COMPLETE
        assert sample_interview_context.current_question_index == initial_index + 1

    def test_mark_question_complete_updates_timestamp(self, sample_interview_context):
        """Test mark_question_complete updates updated_at."""
        old_updated = sample_interview_context.updated_at
        sample_interview_context.add_response("1.1", "Test?", "Answer")
        sample_interview_context.mark_question_complete("1.1")
        assert sample_interview_context.updated_at >= old_updated

    def test_mark_nonexistent_question_complete(self, sample_interview_context):
        """Test marking nonexistent question doesn't crash."""
        initial_index = sample_interview_context.current_question_index
        sample_interview_context.mark_question_complete("nonexistent")
        # Should not advance index for nonexistent question
        assert sample_interview_context.current_question_index == initial_index


class TestInterviewContextRequiredFields:
    """Test InterviewContext.all_required_fields_filled() method."""

    def test_all_required_fields_filled_empty(self, sample_interview_context):
        """Test returns True when no required questions exist."""
        # Remove 'required' priority from all questions
        for q in sample_interview_context.questions:
            q.metadata["priority"] = "optional"
        assert sample_interview_context.all_required_fields_filled() == True

    def test_all_required_fields_filled_with_required_complete(self, sample_interview_context):
        """Test returns True when all required questions are complete."""
        # First question is required, mark it complete
        sample_interview_context.questions[0].status = QuestionStatus.COMPLETE
        assert sample_interview_context.all_required_fields_filled() == True

    def test_all_required_fields_not_filled(self, sample_interview_context):
        """Test returns False when required question not complete."""
        # First question is required and pending
        sample_interview_context.questions[0].metadata["priority"] = "required"
        sample_interview_context.questions[0].status = QuestionStatus.PENDING
        assert sample_interview_context.all_required_fields_filled() == False


class TestInterviewContextConversationHistory:
    """Test conversation history tracking."""

    def test_conversation_history_tracking(self, sample_interview_context):
        """Test adding to conversation history."""
        sample_interview_context.conversation_history.append({
            "role": "assistant",
            "content": "Hello, how can I help?",
            "timestamp": datetime.utcnow().isoformat()
        })
        sample_interview_context.conversation_history.append({
            "role": "user",
            "content": "I need to fill out a form",
            "timestamp": datetime.utcnow().isoformat()
        })

        assert len(sample_interview_context.conversation_history) == 2
        assert sample_interview_context.conversation_history[0]["role"] == "assistant"
        assert sample_interview_context.conversation_history[1]["role"] == "user"
