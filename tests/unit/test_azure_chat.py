"""
Tests for src/llm/azure_chat.py

Comprehensive tests for AzureChatClient class covering initialization,
chat method, _make_request internals, and retry logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx

from src.llm.azure_chat import AzureChatClient, MAX_RETRIES, RETRY_DELAY


# ============ Helper constants ============

VALID_PARAMS = {
    "api_key": "test-api-key",
    "endpoint": "https://my-resource.openai.azure.com",
    "deployment": "gpt-4-deployment",
    "api_version": "2024-12-01-preview",
}

SAMPLE_MESSAGES = [{"role": "user", "content": "Hello"}]


def _make_success_response(content="Hello", finish_reason="stop"):
    """Build a MagicMock that mimics a successful httpx.Response."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": content}, "finish_reason": finish_reason}
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_response.status_code = 200
    return mock_response


def _make_http_status_error(status_code, text="Error"):
    """Build an httpx.HTTPStatusError with the given status code."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    return httpx.HTTPStatusError(
        text, request=MagicMock(), response=mock_resp
    )


def _patch_async_client(mock_response):
    """
    Return a patch context manager for httpx.AsyncClient that yields
    a mock client whose .post() returns the given mock_response.
    """
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    patcher = patch("httpx.AsyncClient")
    return patcher, mock_client


# ============ 1. TestAzureChatClientInit ============


class TestAzureChatClientInit:
    """Tests for AzureChatClient.__init__()."""

    def test_init_with_explicit_params(self):
        """All explicit parameters are stored correctly."""
        client = AzureChatClient(**VALID_PARAMS)
        assert client.api_key == VALID_PARAMS["api_key"]
        assert client.endpoint == VALID_PARAMS["endpoint"]
        assert client.deployment == VALID_PARAMS["deployment"]
        assert client.api_version == VALID_PARAMS["api_version"]

    def test_init_strips_trailing_slash_from_endpoint(self):
        """Trailing slash on the endpoint is stripped."""
        client = AzureChatClient(
            api_key="k", endpoint="https://example.com/", deployment="d"
        )
        assert client.endpoint == "https://example.com"

    @patch.dict(
        "os.environ",
        {
            "AZURE_CHAT_OPENAI_API_KEY": "env-key",
            "AZURE_CHAT_OPENAI_ENDPOINT": "https://env-endpoint.openai.azure.com",
            "AZURE_CHAT_OPENAI_DEPLOYMENT_NAME": "env-deploy",
            "AZURE_CHAT_OPENAI_API_VERSION": "2025-01-01",
        },
    )
    def test_init_uses_env_vars(self):
        """Falls back to environment variables when no explicit params."""
        client = AzureChatClient()
        assert client.api_key == "env-key"
        assert client.endpoint == "https://env-endpoint.openai.azure.com"
        assert client.deployment == "env-deploy"
        assert client.api_version == "2025-01-01"

    def test_init_missing_api_key_raises(self):
        """ValueError when api_key is not provided and env var is absent."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="AZURE_CHAT_OPENAI_API_KEY"):
                AzureChatClient(
                    endpoint="https://e.openai.azure.com", deployment="d"
                )

    def test_init_missing_endpoint_raises(self):
        """ValueError when endpoint is not provided and env var is absent."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="AZURE_CHAT_OPENAI_ENDPOINT"):
                AzureChatClient(api_key="k", deployment="d")

    def test_init_missing_deployment_raises(self):
        """ValueError when deployment is not provided and env var is absent."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="AZURE_CHAT_OPENAI_DEPLOYMENT_NAME"):
                AzureChatClient(
                    api_key="k", endpoint="https://e.openai.azure.com"
                )


# ============ 2. TestAzureChatClientChat ============


class TestAzureChatClientChat:
    """Tests for AzureChatClient.chat() method."""

    @pytest.fixture
    def client(self):
        return AzureChatClient(**VALID_PARAMS)

    @pytest.mark.asyncio
    async def test_chat_success(self, client):
        """chat() returns the string produced by _make_request."""
        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = "response text"

            result = await client.chat(SAMPLE_MESSAGES)

            assert result == "response text"
            mock_req.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_includes_top_p_when_set(self, client):
        """Payload includes top_p when explicitly provided."""
        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = "ok"

            await client.chat(SAMPLE_MESSAGES, top_p=0.95)

            # Third positional arg is the payload dict
            payload = mock_req.call_args[0][2]
            assert payload["top_p"] == 0.95

    @pytest.mark.asyncio
    async def test_chat_omits_top_p_when_none(self, client):
        """Payload does NOT include top_p when it is None (default)."""
        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = "ok"

            await client.chat(SAMPLE_MESSAGES)

            payload = mock_req.call_args[0][2]
            assert "top_p" not in payload

    @pytest.mark.asyncio
    async def test_chat_builds_correct_url(self, client):
        """The URL passed to _make_request contains endpoint, deployment, api_version."""
        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = "ok"

            await client.chat(SAMPLE_MESSAGES)

            url = mock_req.call_args[0][0]
            assert VALID_PARAMS["endpoint"] in url
            assert VALID_PARAMS["deployment"] in url
            assert VALID_PARAMS["api_version"] in url
            assert "/openai/deployments/" in url
            assert "/chat/completions" in url

    @pytest.mark.asyncio
    async def test_chat_retries_on_429(self, client):
        """chat() retries when _make_request raises a 429 HTTPStatusError."""
        error_429 = _make_http_status_error(429, "Rate limited")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = [error_429, "Success after retry"]

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await client.chat(SAMPLE_MESSAGES)

            assert result == "Success after retry"
            assert mock_req.call_count == 2
            mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_retries_on_timeout(self, client):
        """chat() retries when _make_request raises a TimeoutException."""
        timeout_err = httpx.TimeoutException("Timed out")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = [timeout_err, "Recovered"]

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.chat(SAMPLE_MESSAGES)

            assert result == "Recovered"
            assert mock_req.call_count == 2

    @pytest.mark.asyncio
    async def test_chat_raises_non_429_http_error(self, client):
        """Non-429 HTTP errors (e.g. 500) propagate immediately without retry."""
        error_500 = _make_http_status_error(500, "Internal Server Error")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = error_500

            with pytest.raises(httpx.HTTPStatusError):
                await client.chat(SAMPLE_MESSAGES)

            assert mock_req.call_count == 1  # no retry


# ============ 3. TestAzureChatClientMakeRequest ============


class TestAzureChatClientMakeRequest:
    """Tests for AzureChatClient._make_request()."""

    @pytest.fixture
    def client(self):
        return AzureChatClient(**VALID_PARAMS)

    @pytest.mark.asyncio
    async def test_make_request_success(self, client):
        """_make_request returns content from a well-formed JSON response."""
        mock_response = _make_success_response("Hello world")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client_inst = AsyncMock()
            mock_client_inst.post.return_value = mock_response
            mock_cls.return_value.__aenter__.return_value = mock_client_inst

            result = await client._make_request(
                "https://api.example.com",
                {"api-key": "k"},
                {"messages": []},
                30.0,
            )

        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_make_request_empty_content_returns_empty(self, client):
        """When content is None, _make_request returns empty string."""
        mock_response = _make_success_response(content=None)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client_inst = AsyncMock()
            mock_client_inst.post.return_value = mock_response
            mock_cls.return_value.__aenter__.return_value = mock_client_inst

            result = await client._make_request(
                "https://api.example.com",
                {"api-key": "k"},
                {"messages": []},
                30.0,
            )

        assert result == ""

    @pytest.mark.asyncio
    async def test_make_request_truncated_response(self, client):
        """finish_reason='length' still returns content (with a warning logged)."""
        mock_response = _make_success_response(
            content="Partial answer...", finish_reason="length"
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client_inst = AsyncMock()
            mock_client_inst.post.return_value = mock_response
            mock_cls.return_value.__aenter__.return_value = mock_client_inst

            result = await client._make_request(
                "https://api.example.com",
                {"api-key": "k"},
                {"messages": []},
                30.0,
            )

        assert result == "Partial answer..."

    @pytest.mark.asyncio
    async def test_make_request_http_error_raises(self, client):
        """HTTPStatusError is re-raised by _make_request."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = _make_http_status_error(
            500, "Server error"
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client_inst = AsyncMock()
            mock_client_inst.post.return_value = mock_response
            mock_cls.return_value.__aenter__.return_value = mock_client_inst

            with pytest.raises(httpx.HTTPStatusError):
                await client._make_request(
                    "https://api.example.com",
                    {"api-key": "k"},
                    {"messages": []},
                    30.0,
                )

    @pytest.mark.asyncio
    async def test_make_request_generic_error_raises(self, client):
        """Unexpected exceptions are re-raised by _make_request."""
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client_inst = AsyncMock()
            mock_client_inst.post.side_effect = RuntimeError("Something broke")
            mock_cls.return_value.__aenter__.return_value = mock_client_inst

            with pytest.raises(RuntimeError, match="Something broke"):
                await client._make_request(
                    "https://api.example.com",
                    {"api-key": "k"},
                    {"messages": []},
                    30.0,
                )

    @pytest.mark.asyncio
    async def test_make_request_parses_json_correctly(self, client):
        """Verifies the JSON structure is parsed and the right fields are read."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "id": "chatcmpl-abc123",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Parsed OK"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client_inst = AsyncMock()
            mock_client_inst.post.return_value = mock_response
            mock_cls.return_value.__aenter__.return_value = mock_client_inst

            result = await client._make_request(
                "https://api.example.com",
                {"api-key": "k"},
                {"messages": []},
                30.0,
            )

        assert result == "Parsed OK"
        mock_response.json.assert_called_once()


# ============ 4. TestAzureChatClientRetry ============


class TestAzureChatClientRetry:
    """Tests focused on retry / backoff behaviour in chat()."""

    @pytest.fixture
    def client(self):
        return AzureChatClient(**VALID_PARAMS)

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises_last_error(self, client):
        """After MAX_RETRIES failures the last error is raised."""
        timeout_err = httpx.TimeoutException("Persistent timeout")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = timeout_err

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(httpx.TimeoutException, match="Persistent timeout"):
                    await client.chat(SAMPLE_MESSAGES)

            assert mock_req.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self, client):
        """Sleep durations follow exponential backoff: 2, 4, 8 seconds."""
        error_429 = _make_http_status_error(429, "Rate limited")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = error_429  # always fail

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.chat(SAMPLE_MESSAGES)

            # RETRY_DELAY=2.0 => 2*2^0=2, 2*2^1=4, 2*2^2=8
            expected_waits = [
                RETRY_DELAY * (2**i) for i in range(MAX_RETRIES)
            ]
            actual_waits = [c.args[0] for c in mock_sleep.call_args_list]
            assert actual_waits == expected_waits

    @pytest.mark.asyncio
    async def test_retry_on_connect_error(self, client):
        """ConnectError triggers retry, and success on second attempt works."""
        connect_err = httpx.ConnectError("Connection refused")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = [connect_err, "Connected"]

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client.chat(SAMPLE_MESSAGES)

            assert result == "Connected"
            assert mock_req.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_400_error(self, client):
        """A 400 Bad Request is NOT retried -- it raises immediately."""
        error_400 = _make_http_status_error(400, "Bad request")

        with patch.object(
            client, "_make_request", new_callable=AsyncMock
        ) as mock_req:
            mock_req.side_effect = error_400

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(httpx.HTTPStatusError):
                    await client.chat(SAMPLE_MESSAGES)

            assert mock_req.call_count == 1
            mock_sleep.assert_not_awaited()
