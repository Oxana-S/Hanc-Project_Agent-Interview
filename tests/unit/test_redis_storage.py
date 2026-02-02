"""
Unit tests for RedisStorageManager.
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models import InterviewContext, InterviewPattern, InterviewStatus


class TestRedisStorageManagerInit:
    """Test RedisStorageManager initialization."""

    def test_init_creates_client(self, mock_redis_manager):
        """Test that init creates Redis client."""
        assert mock_redis_manager.client is not None

    def test_init_sets_ttl(self, mock_redis_manager):
        """Test that init sets session TTL."""
        assert mock_redis_manager.session_ttl == 7200

    def test_get_key_format(self, mock_redis_manager):
        """Test key format generation."""
        key = mock_redis_manager._get_key("test-session-id")
        assert key == "interview:session:test-session-id"


class TestRedisStorageManagerSaveContext:
    """Test RedisStorageManager.save_context() method."""

    @pytest.mark.asyncio
    async def test_save_context_success(self, mock_redis_manager, sample_interview_context):
        """Test successful context save."""
        result = await mock_redis_manager.save_context(sample_interview_context)
        assert result == True
        mock_redis_manager.client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_context_serialization(self, mock_redis_manager, sample_interview_context):
        """Test context is properly serialized to JSON."""
        await mock_redis_manager.save_context(sample_interview_context)

        call_args = mock_redis_manager.client.setex.call_args
        name = call_args.kwargs['name']
        value = call_args.kwargs['value']

        assert f"interview:session:{sample_interview_context.session_id}" == name
        assert isinstance(value, str)

        # Verify JSON is valid
        data = json.loads(value)
        assert data["session_id"] == sample_interview_context.session_id

    @pytest.mark.asyncio
    async def test_save_context_with_ttl(self, mock_redis_manager, sample_interview_context):
        """Test context is saved with TTL."""
        await mock_redis_manager.save_context(sample_interview_context)

        call_args = mock_redis_manager.client.setex.call_args
        time_arg = call_args.kwargs['time']
        assert time_arg == timedelta(seconds=7200)

    @pytest.mark.asyncio
    async def test_save_context_failure(self, mock_redis_manager, sample_interview_context):
        """Test handling of save failure."""
        mock_redis_manager.client.setex.side_effect = Exception("Redis error")
        result = await mock_redis_manager.save_context(sample_interview_context)
        assert result == False


class TestRedisStorageManagerLoadContext:
    """Test RedisStorageManager.load_context() method."""

    @pytest.mark.asyncio
    async def test_load_context_exists(self, mock_redis_manager, sample_interview_context):
        """Test loading existing context."""
        mock_redis_manager.client.get.return_value = sample_interview_context.model_dump_json()

        result = await mock_redis_manager.load_context(sample_interview_context.session_id)

        assert result is not None
        assert result.session_id == sample_interview_context.session_id

    @pytest.mark.asyncio
    async def test_load_context_not_found(self, mock_redis_manager):
        """Test loading non-existent context."""
        mock_redis_manager.client.get.return_value = None

        result = await mock_redis_manager.load_context("nonexistent-session")

        assert result is None

    @pytest.mark.asyncio
    async def test_load_context_invalid_json(self, mock_redis_manager):
        """Test handling of invalid JSON."""
        mock_redis_manager.client.get.return_value = "invalid json"

        result = await mock_redis_manager.load_context("test-session")

        assert result is None

    @pytest.mark.asyncio
    async def test_load_context_exception(self, mock_redis_manager):
        """Test handling of Redis exception."""
        mock_redis_manager.client.get.side_effect = Exception("Redis error")

        result = await mock_redis_manager.load_context("test-session")

        assert result is None


class TestRedisStorageManagerUpdateContext:
    """Test RedisStorageManager.update_context() method."""

    @pytest.mark.asyncio
    async def test_update_context_calls_save(self, mock_redis_manager, sample_interview_context):
        """Test update_context calls save_context."""
        result = await mock_redis_manager.update_context(sample_interview_context)
        assert result == True
        mock_redis_manager.client.setex.assert_called_once()


class TestRedisStorageManagerDeleteContext:
    """Test RedisStorageManager.delete_context() method."""

    @pytest.mark.asyncio
    async def test_delete_context_success(self, mock_redis_manager):
        """Test successful context deletion."""
        mock_redis_manager.client.delete.return_value = 1

        result = await mock_redis_manager.delete_context("test-session-id")

        assert result == True
        mock_redis_manager.client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_context_not_found(self, mock_redis_manager):
        """Test deletion of non-existent context."""
        mock_redis_manager.client.delete.return_value = 0

        result = await mock_redis_manager.delete_context("nonexistent")

        assert result == False

    @pytest.mark.asyncio
    async def test_delete_context_exception(self, mock_redis_manager):
        """Test handling of deletion exception."""
        mock_redis_manager.client.delete.side_effect = Exception("Redis error")

        result = await mock_redis_manager.delete_context("test-session")

        assert result == False


class TestRedisStorageManagerExtendTTL:
    """Test RedisStorageManager.extend_ttl() method."""

    @pytest.mark.asyncio
    async def test_extend_ttl_success(self, mock_redis_manager):
        """Test successful TTL extension."""
        mock_redis_manager.client.ttl.return_value = 3600

        result = await mock_redis_manager.extend_ttl("test-session", 1800)

        assert result == True
        mock_redis_manager.client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_extend_ttl_nonexistent_key(self, mock_redis_manager):
        """Test TTL extension for non-existent key."""
        mock_redis_manager.client.ttl.return_value = -2  # Key doesn't exist

        result = await mock_redis_manager.extend_ttl("nonexistent", 1800)

        assert result == False

    @pytest.mark.asyncio
    async def test_extend_ttl_calculation(self, mock_redis_manager):
        """Test TTL calculation is correct."""
        mock_redis_manager.client.ttl.return_value = 1000

        await mock_redis_manager.extend_ttl("test-session", 500)

        # Should set new TTL to current(1000) + additional(500) = 1500
        call_args = mock_redis_manager.client.expire.call_args
        assert call_args[0][1] == 1500

    @pytest.mark.asyncio
    async def test_extend_ttl_exception(self, mock_redis_manager):
        """Test handling of TTL extension exception."""
        mock_redis_manager.client.ttl.side_effect = Exception("Redis error")

        result = await mock_redis_manager.extend_ttl("test-session", 1800)

        assert result == False


class TestRedisStorageManagerActiveSessions:
    """Test RedisStorageManager.get_all_active_sessions() method."""

    @pytest.mark.asyncio
    async def test_get_all_active_sessions_empty(self, mock_redis_manager):
        """Test getting active sessions when none exist."""
        mock_redis_manager.client.keys.return_value = []

        result = await mock_redis_manager.get_all_active_sessions()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_active_sessions_multiple(self, mock_redis_manager):
        """Test getting multiple active sessions."""
        mock_redis_manager.client.keys.return_value = [
            "interview:session:abc123",
            "interview:session:def456",
            "interview:session:ghi789"
        ]

        result = await mock_redis_manager.get_all_active_sessions()

        assert len(result) == 3
        assert "abc123" in result
        assert "def456" in result
        assert "ghi789" in result

    @pytest.mark.asyncio
    async def test_get_all_active_sessions_exception(self, mock_redis_manager):
        """Test handling of exception when getting sessions."""
        mock_redis_manager.client.keys.side_effect = Exception("Redis error")

        result = await mock_redis_manager.get_all_active_sessions()

        assert result == []


class TestRedisStorageManagerSessionInfo:
    """Test RedisStorageManager.get_session_info() method."""

    @pytest.mark.asyncio
    async def test_get_session_info_success(self, mock_redis_manager, sample_interview_context):
        """Test getting session info successfully."""
        mock_redis_manager.client.exists.return_value = True
        mock_redis_manager.client.ttl.return_value = 5000
        mock_redis_manager.client.get.return_value = sample_interview_context.model_dump_json()

        result = await mock_redis_manager.get_session_info(sample_interview_context.session_id)

        assert result is not None
        assert result["session_id"] == sample_interview_context.session_id
        assert result["ttl_seconds"] == 5000

    @pytest.mark.asyncio
    async def test_get_session_info_not_exists(self, mock_redis_manager):
        """Test getting info for non-existent session."""
        mock_redis_manager.client.exists.return_value = False

        result = await mock_redis_manager.get_session_info("nonexistent")

        assert result is None


class TestRedisStorageManagerHealthCheck:
    """Test RedisStorageManager.health_check() method."""

    def test_health_check_success(self, mock_redis_manager):
        """Test successful health check."""
        mock_redis_manager.client.ping.return_value = True

        result = mock_redis_manager.health_check()

        assert result == True

    def test_health_check_failure(self, mock_redis_manager):
        """Test failed health check."""
        mock_redis_manager.client.ping.side_effect = Exception("Connection refused")

        result = mock_redis_manager.health_check()

        assert result == False
