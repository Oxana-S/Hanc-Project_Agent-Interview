"""
Unit tests for Pydantic models in models.py
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.models import (
    InterviewPattern, InterviewStatus, QuestionStatus, AnalysisStatus,
    AnswerAnalysis, Clarification, QuestionResponse, InterviewContext,
    InterviewStatistics
)
from src.anketa.schema import FinalAnketa


class TestEnums:
    """Test enum definitions."""

    def test_interview_pattern_values(self):
        assert InterviewPattern.INTERACTION.value == "interaction"
        assert InterviewPattern.MANAGEMENT.value == "management"

    def test_interview_pattern_from_string(self):
        assert InterviewPattern("interaction") == InterviewPattern.INTERACTION
        assert InterviewPattern("management") == InterviewPattern.MANAGEMENT

    def test_interview_status_values(self):
        assert InterviewStatus.INITIATED.value == "initiated"
        assert InterviewStatus.IN_PROGRESS.value == "in_progress"
        assert InterviewStatus.PAUSED.value == "paused"
        assert InterviewStatus.COMPLETED.value == "completed"
        assert InterviewStatus.FAILED.value == "failed"

    def test_question_status_values(self):
        assert QuestionStatus.PENDING.value == "pending"
        assert QuestionStatus.ASKED.value == "asked"
        assert QuestionStatus.ANSWERED.value == "answered"
        assert QuestionStatus.NEEDS_CLARIFICATION.value == "needs_clarification"
        assert QuestionStatus.COMPLETE.value == "complete"
        assert QuestionStatus.SKIPPED.value == "skipped"

    def test_analysis_status_values(self):
        assert AnalysisStatus.COMPLETE.value == "complete"
        assert AnalysisStatus.INCOMPLETE.value == "incomplete"
        assert AnalysisStatus.VAGUE.value == "vague"
        assert AnalysisStatus.CONTRADICTORY.value == "contradictory"
        assert AnalysisStatus.NEEDS_EXAMPLES.value == "needs_examples"


class TestAnswerAnalysis:
    """Test AnswerAnalysis model."""

    def test_valid_answer_analysis(self, sample_answer_analysis):
        assert sample_answer_analysis.status == AnalysisStatus.COMPLETE
        assert 0 <= sample_answer_analysis.completeness_score <= 1
        assert sample_answer_analysis.word_count > 0

    def test_answer_analysis_creation(self):
        analysis = AnswerAnalysis(
            status=AnalysisStatus.COMPLETE,
            completeness_score=0.8,
            word_count=20,
            has_examples=True,
            has_specifics=True,
            confidence=0.9,
            reasoning="Good answer"
        )
        assert analysis.status == AnalysisStatus.COMPLETE
        assert analysis.completeness_score == 0.8

    def test_completeness_score_validation_max(self):
        """Test that completeness_score must be <= 1."""
        with pytest.raises(ValidationError):
            AnswerAnalysis(
                status=AnalysisStatus.COMPLETE,
                completeness_score=1.5,
                word_count=10,
                has_examples=True,
                has_specifics=True,
                confidence=0.9,
                reasoning="test"
            )

    def test_completeness_score_validation_min(self):
        """Test that completeness_score must be >= 0."""
        with pytest.raises(ValidationError):
            AnswerAnalysis(
                status=AnalysisStatus.COMPLETE,
                completeness_score=-0.1,
                word_count=10,
                has_examples=True,
                has_specifics=True,
                confidence=0.9,
                reasoning="test"
            )

    def test_confidence_validation_max(self):
        """Test that confidence must be <= 1."""
        with pytest.raises(ValidationError):
            AnswerAnalysis(
                status=AnalysisStatus.COMPLETE,
                completeness_score=0.8,
                word_count=10,
                has_examples=True,
                has_specifics=True,
                confidence=1.5,
                reasoning="test"
            )

    def test_confidence_validation_min(self):
        """Test that confidence must be >= 0."""
        with pytest.raises(ValidationError):
            AnswerAnalysis(
                status=AnalysisStatus.COMPLETE,
                completeness_score=0.8,
                word_count=10,
                has_examples=True,
                has_specifics=True,
                confidence=-0.1,
                reasoning="test"
            )

    def test_default_timestamp(self):
        """Test that timestamp defaults to current time."""
        analysis = AnswerAnalysis(
            status=AnalysisStatus.COMPLETE,
            completeness_score=0.8,
            word_count=10,
            has_examples=True,
            has_specifics=True,
            confidence=0.9,
            reasoning="test"
        )
        assert analysis.timestamp is not None
        assert isinstance(analysis.timestamp, datetime)

    def test_default_lists(self):
        """Test that lists default to empty."""
        analysis = AnswerAnalysis(
            status=AnalysisStatus.COMPLETE,
            completeness_score=0.8,
            word_count=10,
            has_examples=True,
            has_specifics=True,
            confidence=0.9,
            reasoning="test"
        )
        assert analysis.contradictions == []
        assert analysis.missing_details == []
        assert analysis.clarification_questions == []

    def test_incomplete_analysis_with_clarifications(self, sample_incomplete_analysis):
        assert sample_incomplete_analysis.status == AnalysisStatus.INCOMPLETE
        assert len(sample_incomplete_analysis.clarification_questions) == 2
        assert len(sample_incomplete_analysis.missing_details) == 2


class TestClarification:
    """Test Clarification model."""

    def test_clarification_creation(self):
        clarification = Clarification(
            question="Can you elaborate?",
            answer="Here are more details..."
        )
        assert clarification.clarification_id is not None
        assert clarification.question == "Can you elaborate?"
        assert clarification.answer == "Here are more details..."

    def test_clarification_without_answer(self):
        clarification = Clarification(question="Please explain more")
        assert clarification.answer is None

    def test_clarification_uuid_generation(self):
        c1 = Clarification(question="Q1")
        c2 = Clarification(question="Q2")
        assert c1.clarification_id != c2.clarification_id

    def test_clarification_timestamp(self):
        clarification = Clarification(question="Test?")
        assert clarification.timestamp is not None
        assert isinstance(clarification.timestamp, datetime)

    def test_clarification_with_analysis(self, sample_answer_analysis):
        clarification = Clarification(
            question="More details?",
            answer="Here are details",
            analysis=sample_answer_analysis
        )
        assert clarification.analysis is not None
        assert clarification.analysis.status == AnalysisStatus.COMPLETE


class TestQuestionResponse:
    """Test QuestionResponse model."""

    def test_question_response_creation(self, sample_question_response):
        assert sample_question_response.status == QuestionStatus.PENDING
        assert sample_question_response.answer is None
        assert sample_question_response.question_id == "1.1"

    def test_question_response_with_answer(self):
        response = QuestionResponse(
            question_id="1.1",
            question_text="What is your company?",
            answer="TechCorp",
            status=QuestionStatus.ANSWERED
        )
        assert response.answer == "TechCorp"
        assert response.status == QuestionStatus.ANSWERED

    def test_question_response_default_status(self):
        response = QuestionResponse(
            question_id="2.1",
            question_text="Test question?"
        )
        assert response.status == QuestionStatus.PENDING

    def test_question_response_with_metadata(self):
        response = QuestionResponse(
            question_id="1.1",
            question_text="Test?",
            metadata={"section": "Basic", "priority": "required"}
        )
        assert response.metadata["section"] == "Basic"
        assert response.metadata["priority"] == "required"

    def test_question_response_with_clarifications(self):
        clarification = Clarification(question="More?", answer="Details")
        response = QuestionResponse(
            question_id="1.1",
            question_text="Test?",
            clarifications=[clarification]
        )
        assert len(response.clarifications) == 1

    def test_question_response_timestamps(self):
        response = QuestionResponse(
            question_id="1.1",
            question_text="Test?",
            asked_at=datetime.now(timezone.utc),
            answered_at=datetime.now(timezone.utc)
        )
        assert response.asked_at is not None
        assert response.answered_at is not None


class TestInterviewContext:
    """Test InterviewContext model creation."""

    def test_context_creation(self, sample_interview_context):
        assert sample_interview_context.status == InterviewStatus.IN_PROGRESS
        assert sample_interview_context.pattern == InterviewPattern.INTERACTION
        assert len(sample_interview_context.questions) == 3

    def test_context_default_values(self):
        context = InterviewContext(pattern=InterviewPattern.MANAGEMENT)
        assert context.status == InterviewStatus.INITIATED
        assert context.current_question_index == 0
        assert context.answered_questions == 0
        assert context.total_clarifications_asked == 0

    def test_context_uuid_generation(self):
        c1 = InterviewContext(pattern=InterviewPattern.INTERACTION)
        c2 = InterviewContext(pattern=InterviewPattern.INTERACTION)
        assert c1.session_id != c2.session_id
        assert c1.interview_id != c2.interview_id

    def test_context_timestamps(self):
        context = InterviewContext(pattern=InterviewPattern.INTERACTION)
        assert context.started_at is not None
        assert context.updated_at is not None
        assert context.completed_at is None

    def test_context_json_serialization(self, sample_interview_context):
        json_str = sample_interview_context.model_dump_json()
        assert isinstance(json_str, str)
        assert "session_id" in json_str
        assert "pattern" in json_str


class TestFinalAnketa:
    """Test FinalAnketa model."""

    def test_anketa_creation(self, sample_final_anketa):
        assert sample_final_anketa.company_name == "TechSolutions Inc."
        assert sample_final_anketa.pattern == "interaction"

    def test_anketa_required_fields(self):
        anketa = FinalAnketa(
            interview_id="test",
            pattern="interaction",
            company_name="Test Co",
            industry="IT"
        )
        assert anketa.company_name == "Test Co"

    def test_anketa_default_values(self):
        anketa = FinalAnketa(
            company_name="Test Co",
            industry="IT"
        )
        assert anketa.pattern == "interaction"
        assert anketa.language == "ru"
        assert anketa.voice_tone == "professional"
        assert anketa.integrations == []

    def test_anketa_uuid_generation(self):
        a1 = FinalAnketa(
            interview_id="test1",
            pattern="interaction",
            company_name="Test Co",
            industry="IT"
        )
        a2 = FinalAnketa(
            interview_id="test2",
            pattern="interaction",
            company_name="Test Co",
            industry="IT"
        )
        assert a1.anketa_id != a2.anketa_id

    def test_anketa_json_serialization(self, sample_final_anketa):
        json_str = sample_final_anketa.model_dump_json()
        assert isinstance(json_str, str)
        assert "company_name" in json_str


class TestInterviewStatistics:
    """Test InterviewStatistics model."""

    def test_default_statistics(self):
        stats = InterviewStatistics()
        assert stats.total_interviews == 0
        assert stats.completed_interviews == 0
        assert stats.completion_rate == 0.0
        assert stats.average_duration_minutes == 0.0

    def test_statistics_with_values(self):
        stats = InterviewStatistics(
            total_interviews=100,
            completed_interviews=80,
            average_duration_minutes=25.5,
            completion_rate=80.0,
            pattern_breakdown={"interaction": 60, "management": 40},
            industry_breakdown={"IT": 50, "Finance": 30, "Other": 20}
        )
        assert stats.total_interviews == 100
        assert stats.completion_rate == 80.0
        assert stats.pattern_breakdown["interaction"] == 60
