"""
Unit tests for PostgreSQLStorageManager.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Try to import SQLAlchemyError, or create a mock if sqlalchemy is not installed
try:
    from sqlalchemy.exc import SQLAlchemyError
except ImportError:
    class SQLAlchemyError(Exception):
        """Mock SQLAlchemy error for testing when sqlalchemy is not installed."""
        pass

from models import (
    InterviewPattern, InterviewStatus, CompletedAnketa, InterviewStatistics
)


class TestPostgreSQLStorageManagerSaveAnketa:
    """Test PostgreSQLStorageManager.save_anketa() method."""

    @pytest.mark.asyncio
    async def test_save_anketa_success(self, mock_postgres_manager, sample_completed_anketa):
        """Test successful anketa save."""
        result = await mock_postgres_manager.save_anketa(sample_completed_anketa)
        assert result == True

    @pytest.mark.asyncio
    async def test_save_anketa_calls_add_and_commit(self, mock_postgres_manager, sample_completed_anketa):
        """Test save_anketa calls session.add and commit."""
        mock_session = mock_postgres_manager._get_session()

        await mock_postgres_manager.save_anketa(sample_completed_anketa)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_anketa_failure_rollback(self, mock_postgres_manager, sample_completed_anketa):
        """Test that failure triggers rollback."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.commit.side_effect = SQLAlchemyError("Database error")

        result = await mock_postgres_manager.save_anketa(sample_completed_anketa)

        assert result == False
        mock_session.rollback.assert_called_once()


class TestPostgreSQLStorageManagerGetAnketa:
    """Test PostgreSQLStorageManager.get_anketa() method."""

    @pytest.mark.asyncio
    async def test_get_anketa_found(self, mock_postgres_manager):
        """Test getting existing anketa."""
        mock_anketa_db = MagicMock()
        mock_anketa_db.anketa_id = "test-anketa-id"
        mock_anketa_db.interview_id = "test-interview-id"
        mock_anketa_db.pattern = InterviewPattern.INTERACTION
        mock_anketa_db.created_at = datetime.utcnow()
        mock_anketa_db.interview_duration_seconds = 1800.0
        mock_anketa_db.company_name = "Test Co"
        mock_anketa_db.industry = "IT"
        mock_anketa_db.language = "Russian"
        mock_anketa_db.agent_purpose = "Testing"
        mock_anketa_db.agent_name = "TestBot"
        mock_anketa_db.tone = "formal"
        mock_anketa_db.contact_person = "John"
        mock_anketa_db.contact_email = "john@test.com"
        mock_anketa_db.contact_phone = "+123456"
        mock_anketa_db.company_website = None
        mock_anketa_db.services = []
        mock_anketa_db.client_types = []
        mock_anketa_db.typical_questions = []
        mock_anketa_db.working_hours = {}
        mock_anketa_db.transfer_conditions = []
        mock_anketa_db.integrations = {}
        mock_anketa_db.example_dialogues = []
        mock_anketa_db.restrictions = []
        mock_anketa_db.compliance_requirements = []
        mock_anketa_db.full_responses = {}
        mock_anketa_db.quality_metrics = {}

        mock_session = mock_postgres_manager._get_session()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_anketa_db

        result = await mock_postgres_manager.get_anketa("test-anketa-id")

        assert result is not None
        assert result.company_name == "Test Co"
        assert result.pattern == InterviewPattern.INTERACTION

    @pytest.mark.asyncio
    async def test_get_anketa_not_found(self, mock_postgres_manager):
        """Test getting non-existent anketa."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = await mock_postgres_manager.get_anketa("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_anketa_exception(self, mock_postgres_manager):
        """Test handling of database exception."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.query.side_effect = SQLAlchemyError("Database error")

        result = await mock_postgres_manager.get_anketa("test-id")

        assert result is None


class TestPostgreSQLStorageManagerSaveInterviewSession:
    """Test PostgreSQLStorageManager.save_interview_session() method."""

    @pytest.mark.asyncio
    async def test_save_interview_session_success(self, mock_postgres_manager):
        """Test successful interview session save."""
        result = await mock_postgres_manager.save_interview_session(
            session_id="test-session",
            interview_id="test-interview",
            pattern=InterviewPattern.INTERACTION,
            status="in_progress"
        )

        assert result == True

    @pytest.mark.asyncio
    async def test_save_interview_session_with_metadata(self, mock_postgres_manager):
        """Test saving session with metadata."""
        result = await mock_postgres_manager.save_interview_session(
            session_id="test-session",
            interview_id="test-interview",
            pattern=InterviewPattern.MANAGEMENT,
            status="initiated",
            metadata={"source": "web", "user_agent": "Chrome"}
        )

        assert result == True

    @pytest.mark.asyncio
    async def test_save_interview_session_failure(self, mock_postgres_manager):
        """Test handling of save failure."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.commit.side_effect = SQLAlchemyError("Database error")

        result = await mock_postgres_manager.save_interview_session(
            session_id="test-session",
            interview_id="test-interview",
            pattern=InterviewPattern.INTERACTION,
            status="in_progress"
        )

        assert result == False
        mock_session.rollback.assert_called_once()


class TestPostgreSQLStorageManagerUpdateInterviewSession:
    """Test PostgreSQLStorageManager.update_interview_session() method."""

    @pytest.mark.asyncio
    async def test_update_interview_session_success(self, mock_postgres_manager):
        """Test successful session update."""
        mock_session = mock_postgres_manager._get_session()
        mock_session_db = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_session_db

        result = await mock_postgres_manager.update_interview_session(
            session_id="test-session",
            completed_at=datetime.utcnow(),
            duration=1800.0,
            status="completed"
        )

        assert result == True
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_interview_session_not_found(self, mock_postgres_manager):
        """Test updating non-existent session."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = await mock_postgres_manager.update_interview_session(
            session_id="nonexistent",
            status="completed"
        )

        assert result == False

    @pytest.mark.asyncio
    async def test_update_interview_session_partial(self, mock_postgres_manager):
        """Test partial session update."""
        mock_session = mock_postgres_manager._get_session()
        mock_session_db = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_session_db

        result = await mock_postgres_manager.update_interview_session(
            session_id="test-session",
            questions_asked=10,
            questions_answered=8
        )

        assert result == True

    @pytest.mark.asyncio
    async def test_update_interview_session_failure(self, mock_postgres_manager):
        """Test handling of update failure."""
        mock_session = mock_postgres_manager._get_session()
        mock_session_db = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_session_db
        mock_session.commit.side_effect = SQLAlchemyError("Database error")

        result = await mock_postgres_manager.update_interview_session(
            session_id="test-session",
            status="completed"
        )

        assert result == False
        mock_session.rollback.assert_called_once()


class TestPostgreSQLStorageManagerStatistics:
    """Test PostgreSQLStorageManager.get_statistics() method."""

    @pytest.mark.asyncio
    async def test_get_statistics_empty(self, mock_postgres_manager):
        """Test getting statistics with no data."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.query.return_value.count.return_value = 0
        mock_session.query.return_value.filter.return_value.count.return_value = 0
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.query.return_value.all.return_value = []

        result = await mock_postgres_manager.get_statistics()

        assert result.total_interviews == 0
        assert result.completion_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_statistics_exception(self, mock_postgres_manager):
        """Test handling of statistics exception."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.query.side_effect = SQLAlchemyError("Database error")

        result = await mock_postgres_manager.get_statistics()

        # Should return empty statistics on error
        assert result.total_interviews == 0


class TestPostgreSQLStorageManagerHealthCheck:
    """Test PostgreSQLStorageManager.health_check() method."""

    def test_health_check_success(self, mock_postgres_manager):
        """Test successful health check."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.execute.return_value = MagicMock()

        result = mock_postgres_manager.health_check()

        assert result == True

    def test_health_check_failure(self, mock_postgres_manager):
        """Test failed health check."""
        mock_session = mock_postgres_manager._get_session()
        mock_session.execute.side_effect = Exception("Connection failed")

        result = mock_postgres_manager.health_check()

        assert result == False
