"""
Unit tests for main.py configuration and startup.
"""

import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestLoadConfiguration:
    """Test configuration loading."""

    def test_load_configuration_defaults(self):
        """Test configuration uses defaults when env vars not set."""
        from main import load_configuration

        with patch.dict(os.environ, {}, clear=True):
            config = load_configuration()

            assert config["redis"]["host"] == "localhost"
            assert config["redis"]["port"] == 6379
            assert config["general"]["environment"] == "development"

    def test_load_configuration_from_env(self):
        """Test configuration reads from environment variables."""
        from main import load_configuration

        env_vars = {
            "REDIS_HOST": "redis.example.com",
            "REDIS_PORT": "6380",
            "AZURE_OPENAI_API_KEY": "test-azure-key",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
            "DEEPSEEK_API_KEY": "test-deepseek-key",
            "ENVIRONMENT": "production"
        }

        with patch.dict(os.environ, env_vars):
            config = load_configuration()

            assert config["redis"]["host"] == "redis.example.com"
            assert config["redis"]["port"] == 6380
            assert config["azure_openai"]["api_key"] == "test-azure-key"
            assert config["deepseek"]["api_key"] == "test-deepseek-key"
            assert config["general"]["environment"] == "production"

    def test_load_configuration_session_ttl(self):
        """Test configuration parses session TTL."""
        from main import load_configuration

        with patch.dict(os.environ, {"REDIS_SESSION_TTL": "3600"}):
            config = load_configuration()

            assert config["redis"]["session_ttl"] == 3600

    def test_load_configuration_postgres_url(self):
        """Test configuration builds PostgreSQL URL."""
        from main import load_configuration

        env_vars = {
            "POSTGRES_HOST": "db.example.com",
            "POSTGRES_PORT": "5433",
            "POSTGRES_USER": "testuser",
            "POSTGRES_PASSWORD": "testpass",
            "POSTGRES_DB": "testdb"
        }

        with patch.dict(os.environ, env_vars):
            config = load_configuration()

            assert "db.example.com" in config["postgres"]["database_url"]
            assert "5433" in config["postgres"]["database_url"]
            assert "testuser" in config["postgres"]["database_url"]


class TestValidateConfiguration:
    """Test configuration validation."""

    def test_validate_configuration_valid(self):
        """Test validation passes with required fields."""
        from main import validate_configuration

        config = {
            "azure_openai": {
                "api_key": "test-key",
                "endpoint": "https://test.openai.azure.com"
            },
            "deepseek": {
                "api_key": "test-deepseek"
            }
        }

        result = validate_configuration(config)

        assert result == True

    def test_validate_configuration_missing_azure_key(self):
        """Test validation fails without Azure key."""
        from main import validate_configuration

        config = {
            "azure_openai": {
                "api_key": None,
                "endpoint": "https://test.openai.azure.com"
            },
            "deepseek": {
                "api_key": "test"
            }
        }

        result = validate_configuration(config)

        assert result == False

    def test_validate_configuration_missing_deepseek_key(self):
        """Test validation fails without DeepSeek key."""
        from main import validate_configuration

        config = {
            "azure_openai": {
                "api_key": "test-key",
                "endpoint": "https://test.openai.azure.com"
            },
            "deepseek": {
                "api_key": None
            }
        }

        result = validate_configuration(config)

        assert result == False

    def test_validate_configuration_empty_values(self):
        """Test validation fails with empty string values."""
        from main import validate_configuration

        config = {
            "azure_openai": {
                "api_key": "",
                "endpoint": "https://test.openai.azure.com"
            },
            "deepseek": {
                "api_key": "test"
            }
        }

        result = validate_configuration(config)

        assert result == False


class TestInitializeStorageManagers:
    """Test storage manager initialization."""

    @pytest.mark.asyncio
    async def test_initialize_storage_success(self):
        """Test successful storage initialization."""
        from main import initialize_storage_managers

        config = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "password": None,
                "db": 0,
                "session_ttl": 7200
            },
            "postgres": {
                "database_url": "postgresql://test:test@localhost:5432/test"
            }
        }

        with patch('main.RedisStorageManager') as MockRedis, \
             patch('main.PostgreSQLStorageManager') as MockPostgres:

            mock_redis = MagicMock()
            mock_redis.health_check.return_value = True
            MockRedis.return_value = mock_redis

            mock_postgres = MagicMock()
            mock_postgres.health_check.return_value = True
            MockPostgres.return_value = mock_postgres

            redis_mgr, postgres_mgr = await initialize_storage_managers(config)

            assert redis_mgr is not None
            assert postgres_mgr is not None

    @pytest.mark.asyncio
    async def test_initialize_storage_redis_failure(self):
        """Test handling of Redis initialization failure."""
        from main import initialize_storage_managers

        config = {
            "redis": {
                "host": "localhost",
                "port": 6379,
                "password": None,
                "db": 0,
                "session_ttl": 7200
            },
            "postgres": {
                "database_url": "postgresql://test:test@localhost:5432/test"
            }
        }

        with patch('main.RedisStorageManager') as MockRedis:
            MockRedis.side_effect = Exception("Connection failed")

            redis_mgr, postgres_mgr = await initialize_storage_managers(config)

            assert redis_mgr is None
            assert postgres_mgr is None


class TestSelectPattern:
    """Test pattern selection."""

    @pytest.mark.asyncio
    async def test_select_pattern_interaction(self):
        """Test selecting INTERACTION pattern."""
        from main import select_pattern
        from models import InterviewPattern

        with patch('builtins.input', return_value='1'):
            pattern = await select_pattern()

            assert pattern == InterviewPattern.INTERACTION

    @pytest.mark.asyncio
    async def test_select_pattern_management(self):
        """Test selecting MANAGEMENT pattern."""
        from main import select_pattern
        from models import InterviewPattern

        with patch('builtins.input', return_value='2'):
            pattern = await select_pattern()

            assert pattern == InterviewPattern.MANAGEMENT

    @pytest.mark.asyncio
    async def test_select_pattern_invalid_then_valid(self):
        """Test invalid input followed by valid input."""
        from main import select_pattern
        from models import InterviewPattern

        # First return invalid, then valid
        with patch('builtins.input', side_effect=['3', 'invalid', '1']):
            pattern = await select_pattern()

            assert pattern == InterviewPattern.INTERACTION
