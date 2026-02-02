"""
Shared fixtures for Voice Interviewer Agent tests
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Generator

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import (
    InterviewContext, InterviewPattern, InterviewStatus,
    QuestionResponse, QuestionStatus, AnswerAnalysis, AnalysisStatus,
    Clarification, CompletedAnketa, InterviewStatistics
)


# ============ SAMPLE DATA FIXTURES ============

@pytest.fixture
def sample_answer_analysis():
    """Create a sample complete AnswerAnalysis."""
    return AnswerAnalysis(
        status=AnalysisStatus.COMPLETE,
        completeness_score=0.85,
        word_count=25,
        has_examples=True,
        has_specifics=True,
        contradictions=[],
        missing_details=[],
        clarification_questions=[],
        confidence=0.9,
        reasoning="Answer is comprehensive and includes examples."
    )


@pytest.fixture
def sample_incomplete_analysis():
    """Create an incomplete AnswerAnalysis."""
    return AnswerAnalysis(
        status=AnalysisStatus.INCOMPLETE,
        completeness_score=0.4,
        word_count=8,
        has_examples=False,
        has_specifics=False,
        contradictions=[],
        missing_details=["Specific details needed", "Examples required"],
        clarification_questions=[
            "Can you provide a specific example?",
            "Please elaborate on the details."
        ],
        confidence=0.7,
        reasoning="Answer is too brief and lacks specifics."
    )


@pytest.fixture
def sample_question_response():
    """Create a sample QuestionResponse."""
    return QuestionResponse(
        question_id="1.1",
        question_text="What is your company name?",
        answer=None,
        status=QuestionStatus.PENDING,
        metadata={
            "section": "Basic Information",
            "priority": "required",
            "type": "text",
            "min_answer_length": 15
        }
    )


@pytest.fixture
def sample_interview_context():
    """Create a sample InterviewContext with questions."""
    context = InterviewContext(
        pattern=InterviewPattern.INTERACTION,
        status=InterviewStatus.IN_PROGRESS,
        total_questions=10
    )

    # Add sample questions
    for i in range(3):
        question = QuestionResponse(
            question_id=f"1.{i+1}",
            question_text=f"Sample question {i+1}?",
            status=QuestionStatus.PENDING,
            metadata={
                "section": "Test Section",
                "priority": "required" if i == 0 else "optional",
                "type": "text",
                "min_answer_length": 15
            }
        )
        context.questions.append(question)

    return context


@pytest.fixture
def sample_completed_anketa():
    """Create a sample CompletedAnketa."""
    return CompletedAnketa(
        interview_id="test-interview-123",
        pattern=InterviewPattern.INTERACTION,
        interview_duration_seconds=1800.0,
        company_name="TechSolutions Inc.",
        industry="IT / Technology",
        language="Russian",
        agent_purpose="Customer support and appointment booking",
        agent_name="Alex",
        tone="adaptive",
        contact_person="John Doe",
        contact_email="john@techsolutions.com",
        contact_phone="+79991234567",
        company_website="https://techsolutions.com",
        full_responses={"1.1": "TechSolutions Inc."},
        quality_metrics={
            "completeness_score": 0.87,
            "total_clarifications": 2,
            "average_answer_length": 25.4
        }
    )


# ============ MOCK REDIS CLIENT ============

@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = MagicMock()
    client.ping.return_value = True
    client.setex.return_value = True
    client.get.return_value = None
    client.delete.return_value = 1
    client.ttl.return_value = 7200
    client.expire.return_value = True
    client.keys.return_value = []
    client.exists.return_value = True
    client.info.return_value = {"redis_version": "7.0.0"}
    return client


@pytest.fixture
def mock_redis_manager(mock_redis_client):
    """Create a RedisStorageManager with mocked client."""
    with patch('redis.Redis', return_value=mock_redis_client):
        from src.storage.redis import RedisStorageManager
        manager = RedisStorageManager(
            host="localhost",
            port=6379,
            password=None,
            db=0,
            session_ttl=7200
        )
        manager.client = mock_redis_client
        return manager


# ============ MOCK POSTGRESQL ============

@pytest.fixture
def mock_db_session():
    """Create a mock SQLAlchemy session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    session.query = MagicMock()
    session.execute = MagicMock()
    return session


@pytest.fixture
def mock_postgres_manager(mock_db_session):
    """Create a PostgreSQLStorageManager with mocked session."""
    with patch('src.storage.postgres.create_engine') as mock_engine, \
         patch('src.storage.postgres.sessionmaker') as mock_sessionmaker, \
         patch('src.storage.postgres.Base'):

        mock_sessionmaker.return_value = lambda: mock_db_session

        from src.storage.postgres import PostgreSQLStorageManager
        manager = PostgreSQLStorageManager(
            database_url="postgresql://test:test@localhost:5432/test"
        )
        manager._get_session = lambda: mock_db_session
        return manager


# ============ ASYNC HELPERS ============

@pytest.fixture
def run_async():
    """Helper to run async functions in sync tests."""
    def _run_async(coro):
        return asyncio.get_event_loop().run_until_complete(coro)
    return _run_async
