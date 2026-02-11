"""
Tests for src/llm/factory.py

Comprehensive tests for create_llm_client factory function.
Covers provider selection, case/whitespace normalization,
env-var defaults, and error propagation.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.llm.factory import create_llm_client, get_available_providers


# ---------------------------------------------------------------------------
# Helpers: env dicts that satisfy each client's constructor requirements
# ---------------------------------------------------------------------------

DEEPSEEK_ENV = {
    "DEEPSEEK_API_KEY": "test-deepseek-key",
}

AZURE_ENV = {
    "AZURE_CHAT_OPENAI_API_KEY": "test-azure-key",
    "AZURE_CHAT_OPENAI_ENDPOINT": "https://test.openai.azure.com",
    "AZURE_CHAT_OPENAI_DEPLOYMENT_NAME": "gpt-4",
}


def _clean_env():
    """Return a copy of os.environ without any provider-specific keys."""
    env = os.environ.copy()
    for key in [
        "DEEPSEEK_API_KEY",
        "AZURE_CHAT_OPENAI_API_KEY",
        "AZURE_CHAT_OPENAI_ENDPOINT",
        "AZURE_CHAT_OPENAI_DEPLOYMENT_NAME",
        "LLM_PROVIDER",
    ]:
        env.pop(key, None)
    return env


# ===================================================================
# 1. TestCreateLLMClientDeepSeek
# ===================================================================

class TestCreateLLMClientDeepSeek:
    """Tests for creating a DeepSeek client via the factory."""

    def test_create_deepseek_returns_deepseek_client(self):
        """Explicit 'deepseek' provider returns a DeepSeekClient instance."""
        with patch.dict(os.environ, DEEPSEEK_ENV):
            client = create_llm_client("deepseek")

        from src.llm.deepseek import DeepSeekClient
        assert isinstance(client, DeepSeekClient)

    def test_create_deepseek_case_insensitive(self):
        """Provider name is case-insensitive: 'DeepSeek' works."""
        with patch.dict(os.environ, DEEPSEEK_ENV):
            client = create_llm_client("DeepSeek")

        from src.llm.deepseek import DeepSeekClient
        assert isinstance(client, DeepSeekClient)

    def test_create_deepseek_with_spaces(self):
        """Leading/trailing whitespace is stripped: ' deepseek ' works."""
        with patch.dict(os.environ, DEEPSEEK_ENV):
            client = create_llm_client("  deepseek  ")

        from src.llm.deepseek import DeepSeekClient
        assert isinstance(client, DeepSeekClient)


# ===================================================================
# 2. TestCreateLLMClientAzure
# ===================================================================

class TestCreateLLMClientAzure:
    """Tests for creating an Azure client via the factory."""

    def test_create_azure_returns_azure_client(self):
        """Explicit 'azure' provider returns an AzureChatClient instance."""
        with patch.dict(os.environ, AZURE_ENV):
            client = create_llm_client("azure")

        from src.llm.azure_chat import AzureChatClient
        assert isinstance(client, AzureChatClient)

    def test_create_azure_openai_alias(self):
        """'azure_openai' is accepted as an alias for 'azure'."""
        with patch.dict(os.environ, AZURE_ENV):
            client = create_llm_client("azure_openai")

        from src.llm.azure_chat import AzureChatClient
        assert isinstance(client, AzureChatClient)

    def test_create_openai_returns_openai_client(self):
        """'openai' provider returns an OpenAICompatibleClient (not Azure)."""
        env = {"OPENAI_API_KEY": "test-openai-key"}
        with patch.dict(os.environ, env):
            client = create_llm_client("openai")

        from src.llm.openai_client import OpenAICompatibleClient
        assert isinstance(client, OpenAICompatibleClient)


# ===================================================================
# 3. TestCreateLLMClientDefault
# ===================================================================

class TestCreateLLMClientDefault:
    """Tests for default provider resolution via env var."""

    def test_default_provider_from_env(self):
        """When provider is None, LLM_PROVIDER env var is used."""
        env = {**DEEPSEEK_ENV, "LLM_PROVIDER": "deepseek"}
        with patch.dict(os.environ, env):
            client = create_llm_client()  # provider=None

        from src.llm.deepseek import DeepSeekClient
        assert isinstance(client, DeepSeekClient)

    def test_default_provider_deepseek_when_no_env(self):
        """When provider is None and LLM_PROVIDER not set, defaults to 'deepseek'."""
        clean = _clean_env()
        clean.update(DEEPSEEK_ENV)  # need DeepSeek keys so constructor succeeds
        with patch.dict(os.environ, clean, clear=True):
            client = create_llm_client()  # provider=None, no LLM_PROVIDER

        from src.llm.deepseek import DeepSeekClient
        assert isinstance(client, DeepSeekClient)


# ===================================================================
# 4. TestCreateLLMClientErrors
# ===================================================================

class TestCreateLLMClientErrors:
    """Tests for error handling in the factory."""

    def test_unknown_provider_raises_value_error(self):
        """An unrecognised provider name raises ValueError."""
        with pytest.raises(ValueError):
            create_llm_client("google_gemini")

    def test_error_message_contains_provider_name(self):
        """The ValueError message includes the bad provider name."""
        with pytest.raises(ValueError, match="nonexistent_provider"):
            create_llm_client("nonexistent_provider")

    def test_deepseek_missing_api_key_propagates(self):
        """If DeepSeekClient raises ValueError (no API key), it propagates."""
        clean = _clean_env()
        with patch.dict(os.environ, clean, clear=True):
            with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
                create_llm_client("deepseek")

    def test_azure_missing_config_propagates(self):
        """If AzureChatClient raises ValueError (no config), it propagates."""
        clean = _clean_env()
        with patch.dict(os.environ, clean, clear=True):
            with pytest.raises(ValueError, match="AZURE_CHAT_OPENAI"):
                create_llm_client("azure")


# ===================================================================
# 5. TestGetAvailableProviders
# ===================================================================

class TestGetAvailableProviders:
    """Tests for get_available_providers() helper."""

    def test_returns_all_five_providers(self):
        """Result always contains all 5 registered providers."""
        result = get_available_providers()
        ids = [p["id"] for p in result["providers"]]
        assert ids == ["deepseek", "azure", "openai", "anthropic", "xai"]

    def test_available_true_when_key_set(self):
        """Provider is available when its env key is non-empty."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "key123"}):
            result = get_available_providers()
        ds = next(p for p in result["providers"] if p["id"] == "deepseek")
        assert ds["available"] is True

    def test_available_false_when_key_empty(self):
        """Provider is unavailable when its env key is empty."""
        clean = _clean_env()
        clean["OPENAI_API_KEY"] = ""
        with patch.dict(os.environ, clean, clear=True):
            result = get_available_providers()
        oai = next(p for p in result["providers"] if p["id"] == "openai")
        assert oai["available"] is False

    def test_default_from_env(self):
        """Default provider comes from LLM_PROVIDER env var."""
        with patch.dict(os.environ, {"LLM_PROVIDER": "azure"}):
            result = get_available_providers()
        assert result["default"] == "azure"

    def test_default_fallback_deepseek(self):
        """Without LLM_PROVIDER, default is 'deepseek'."""
        clean = _clean_env()
        with patch.dict(os.environ, clean, clear=True):
            result = get_available_providers()
        assert result["default"] == "deepseek"

    def test_provider_names_present(self):
        """Each provider entry has a human-readable name."""
        result = get_available_providers()
        for p in result["providers"]:
            assert "name" in p
            assert len(p["name"]) > 0
