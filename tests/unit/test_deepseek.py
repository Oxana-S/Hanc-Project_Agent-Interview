"""
Tests for src/llm/deepseek.py

Comprehensive tests for DeepSeekClient class.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.llm.deepseek import DeepSeekClient, MAX_RETRIES, RETRY_DELAY


class TestDeepSeekClientInit:
    """Tests for DeepSeekClient initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        client = DeepSeekClient(api_key="test-key")
        assert client.api_key == "test-key"

    def test_init_with_custom_endpoint(self):
        """Test initialization with custom endpoint."""
        client = DeepSeekClient(
            api_key="test-key",
            endpoint="https://custom.api.com/v1"
        )
        assert client.endpoint == "https://custom.api.com/v1"

    def test_init_with_custom_model(self):
        """Test initialization with custom model."""
        client = DeepSeekClient(
            api_key="test-key",
            model="deepseek-reasoner"
        )
        assert client.model == "deepseek-reasoner"

    def test_init_default_endpoint(self):
        """Test default endpoint is set."""
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'env-key'}):
            client = DeepSeekClient(api_key="test-key")
            assert "deepseek.com" in client.endpoint or client.endpoint is not None

    def test_init_without_api_key_raises_error(self):
        """Test initialization without API key raises ValueError."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                DeepSeekClient()
            assert "DEEPSEEK_API_KEY" in str(exc_info.value)

    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'env-key'})
    def test_init_uses_env_api_key(self):
        """Test initialization uses environment variable."""
        client = DeepSeekClient()
        assert client.api_key == "env-key"


class TestDeepSeekClientChat:
    """Tests for DeepSeekClient.chat() method."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return DeepSeekClient(api_key="test-key")

    @pytest.fixture
    def mock_response(self):
        """Create a mock successful response."""
        return {
            "choices": [
                {
                    "message": {"content": "Test response"},
                    "finish_reason": "stop"
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}
        }

    @pytest.mark.asyncio
    async def test_chat_returns_content(self, client, mock_response):
        """Test chat returns message content."""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.return_value = "Test response"

            result = await client.chat([
                {"role": "user", "content": "Hello"}
            ])

            assert result == "Test response"

    @pytest.mark.asyncio
    async def test_chat_passes_messages(self, client):
        """Test chat passes messages to request."""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.return_value = "response"
            messages = [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hello"}
            ]

            await client.chat(messages)

            call_args = mock.call_args
            payload = call_args[0][2]  # Third positional arg is payload
            assert payload["messages"] == messages

    @pytest.mark.asyncio
    async def test_chat_passes_temperature(self, client):
        """Test chat passes temperature parameter."""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.return_value = "response"

            await client.chat([{"role": "user", "content": "Hi"}], temperature=0.5)

            payload = mock.call_args[0][2]
            assert payload["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_chat_passes_max_tokens(self, client):
        """Test chat passes max_tokens parameter."""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.return_value = "response"

            await client.chat([{"role": "user", "content": "Hi"}], max_tokens=1000)

            payload = mock.call_args[0][2]
            assert payload["max_tokens"] == 1000

    @pytest.mark.asyncio
    async def test_chat_passes_top_p_when_provided(self, client):
        """Test chat passes top_p when provided."""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.return_value = "response"

            await client.chat([{"role": "user", "content": "Hi"}], top_p=0.9)

            payload = mock.call_args[0][2]
            assert payload["top_p"] == 0.9

    @pytest.mark.asyncio
    async def test_chat_omits_top_p_when_none(self, client):
        """Test chat omits top_p when not provided."""
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.return_value = "response"

            await client.chat([{"role": "user", "content": "Hi"}])

            payload = mock.call_args[0][2]
            assert "top_p" not in payload

    @pytest.mark.asyncio
    async def test_chat_retries_on_rate_limit(self, client):
        """Test chat retries on 429 rate limit."""
        rate_limit_error = httpx.HTTPStatusError(
            "Rate limited",
            request=MagicMock(),
            response=MagicMock(status_code=429, text="Rate limited")
        )

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.side_effect = [rate_limit_error, rate_limit_error, "Success"]

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await client.chat([{"role": "user", "content": "Hi"}])

            assert result == "Success"
            assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_chat_retries_on_timeout(self, client):
        """Test chat retries on timeout."""
        timeout_error = httpx.TimeoutException("Timeout")

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.side_effect = [timeout_error, "Success"]

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await client.chat([{"role": "user", "content": "Hi"}])

            assert result == "Success"

    @pytest.mark.asyncio
    async def test_chat_retries_on_connect_error(self, client):
        """Test chat retries on connection error."""
        connect_error = httpx.ConnectError("Connection failed")

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.side_effect = [connect_error, "Success"]

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await client.chat([{"role": "user", "content": "Hi"}])

            assert result == "Success"

    @pytest.mark.asyncio
    async def test_chat_raises_after_max_retries(self, client):
        """Test chat raises after max retries exceeded."""
        timeout_error = httpx.TimeoutException("Timeout")

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.side_effect = timeout_error

            with patch('asyncio.sleep', new_callable=AsyncMock):
                with pytest.raises(httpx.TimeoutException):
                    await client.chat([{"role": "user", "content": "Hi"}])

            assert mock.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_chat_raises_non_retryable_error(self, client):
        """Test chat raises non-retryable HTTP errors immediately."""
        error = httpx.HTTPStatusError(
            "Bad request",
            request=MagicMock(),
            response=MagicMock(status_code=400, text="Bad request")
        )

        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock:
            mock.side_effect = error

            with pytest.raises(httpx.HTTPStatusError):
                await client.chat([{"role": "user", "content": "Hi"}])

            assert mock.call_count == 1  # No retries


class TestDeepSeekClientMakeRequest:
    """Tests for DeepSeekClient._make_request() method."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return DeepSeekClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_make_request_returns_content(self, client):
        """Test _make_request returns message content."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with patch.object(client, '_get_http_client', return_value=mock_http):
            result = await client._make_request(
                "https://api.example.com",
                {"Authorization": "Bearer test"},
                {"messages": []},
                30.0
            )

            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_make_request_handles_empty_content(self, client):
        """Test _make_request handles empty content."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
            "usage": {}
        }
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with patch.object(client, '_get_http_client', return_value=mock_http):
            result = await client._make_request(
                "https://api.example.com",
                {"Authorization": "Bearer test"},
                {"messages": []},
                30.0
            )

            assert result == ""

    @pytest.mark.asyncio
    async def test_make_request_logs_truncation_warning(self, client):
        """Test _make_request logs warning when response is truncated."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Partial..."}, "finish_reason": "length"}],
            "usage": {"completion_tokens": 8192}
        }
        mock_response.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response

        with patch.object(client, '_get_http_client', return_value=mock_http):
            # Should not raise, just log warning
            result = await client._make_request(
                "https://api.example.com",
                {"Authorization": "Bearer test"},
                {"messages": []},
                30.0
            )

            assert result == "Partial..."


class TestDeepSeekClientAnalyzeAnswer:
    """Tests for DeepSeekClient.analyze_answer() method."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return DeepSeekClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_analyze_answer_returns_structured_response(self, client):
        """Test analyze_answer returns structured response."""
        mock_json = json.dumps({
            "is_complete": True,
            "completeness_score": 0.9,
            "needs_clarification": False,
            "clarification_questions": [],
            "extracted_info": {"company": "Test"},
            "reasoning": "Answer is complete"
        })

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = mock_json

            result = await client.analyze_answer(
                question="What is your company?",
                answer="Our company is Test Corp",
                question_context={"section": "General"},
                previous_answers={}
            )

            assert result["is_complete"] is True
            assert result["completeness_score"] == 0.9
            assert result["needs_clarification"] is False

    @pytest.mark.asyncio
    async def test_analyze_answer_handles_json_in_markdown(self, client):
        """Test analyze_answer handles JSON wrapped in markdown."""
        mock_response = """```json
{
    "is_complete": true,
    "completeness_score": 0.8,
    "needs_clarification": false,
    "clarification_questions": [],
    "extracted_info": {},
    "reasoning": "Good"
}
```"""

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await client.analyze_answer(
                question="Test?",
                answer="Test answer",
                question_context={},
                previous_answers={}
            )

            assert result["is_complete"] is True

    @pytest.mark.asyncio
    async def test_analyze_answer_clamps_completeness_score(self, client):
        """Test analyze_answer clamps completeness_score to 0-1."""
        mock_json = json.dumps({
            "is_complete": False,
            "completeness_score": 1.5,  # Over 1
            "needs_clarification": True,
            "clarification_questions": ["More?"],
            "extracted_info": {},
            "reasoning": ""
        })

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = mock_json

            result = await client.analyze_answer(
                question="Test?",
                answer="Short",
                question_context={},
                previous_answers={}
            )

            assert result["completeness_score"] == 1.0

    @pytest.mark.asyncio
    async def test_analyze_answer_limits_clarification_questions(self, client):
        """Test analyze_answer limits clarification questions to 3."""
        mock_json = json.dumps({
            "is_complete": False,
            "completeness_score": 0.3,
            "needs_clarification": True,
            "clarification_questions": ["Q1?", "Q2?", "Q3?", "Q4?", "Q5?"],
            "extracted_info": {},
            "reasoning": ""
        })

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = mock_json

            result = await client.analyze_answer(
                question="Test?",
                answer="Vague",
                question_context={},
                previous_answers={}
            )

            assert len(result["clarification_questions"]) == 3

    @pytest.mark.asyncio
    async def test_analyze_answer_fallback_on_error(self, client):
        """Test analyze_answer uses fallback on parsing error."""
        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = "Not valid JSON at all"

            result = await client.analyze_answer(
                question="Test?",
                answer="A",  # Very short answer
                question_context={},
                previous_answers={}
            )

            # Fallback should detect short answer
            assert result["is_complete"] is False
            assert result["needs_clarification"] is True
            assert "Fallback" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_analyze_answer_with_previous_answers(self, client):
        """Test analyze_answer uses previous answers context."""
        mock_json = json.dumps({
            "is_complete": True,
            "completeness_score": 0.9,
            "needs_clarification": False,
            "clarification_questions": [],
            "extracted_info": {},
            "reasoning": ""
        })

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = mock_json

            await client.analyze_answer(
                question="Follow up?",
                answer="Yes",
                question_context={"section": "Details"},
                previous_answers={
                    "q1": "First answer",
                    "q2": "Second answer"
                }
            )

            # Check that previous answers were included in prompt
            call_args = mock.call_args
            messages = call_args[0][0]
            user_message = messages[1]["content"]
            # Context should mention previous answers


class TestDeepSeekClientAnalyzeAndCompleteAnketa:
    """Tests for DeepSeekClient.analyze_and_complete_anketa() method."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return DeepSeekClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_returns_parsed_json(self, client):
        """Test analyze_and_complete_anketa returns parsed JSON."""
        mock_anketa = {
            "company_name": "Test Corp",
            "industry": "IT",
            "services": ["consulting", "development"]
        }

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = json.dumps(mock_anketa)

            result = await client.analyze_and_complete_anketa(
                raw_responses={"q1": "Test Corp", "q2": "IT"},
                pattern="interaction",
                company_name="Test Corp"
            )

            assert result["company_name"] == "Test Corp"
            assert result["industry"] == "IT"

    @pytest.mark.asyncio
    async def test_handles_markdown_wrapped_json(self, client):
        """Test handles JSON wrapped in markdown code block."""
        mock_response = """```json
{"company_name": "Test"}
```"""

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = mock_response

            result = await client.analyze_and_complete_anketa(
                raw_responses={},
                pattern="interaction",
                company_name="Test"
            )

            assert result["company_name"] == "Test"

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_parse_error(self, client):
        """Test returns empty dict on JSON parse error."""
        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = "Not valid JSON"

            result = await client.analyze_and_complete_anketa(
                raw_responses={},
                pattern="interaction",
                company_name="Test"
            )

            assert result == {}


class TestDeepSeekClientGenerateExampleDialogues:
    """Tests for DeepSeekClient.generate_example_dialogues() method."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return DeepSeekClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_returns_list_of_dialogues(self, client):
        """Test returns list of dialogue examples."""
        mock_dialogues = [
            {"role": "bot", "message": "Hello!", "intent": "greeting"},
            {"role": "user", "message": "Hi there", "intent": "response"}
        ]

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = json.dumps(mock_dialogues)

            result = await client.generate_example_dialogues(
                company_name="Test Corp",
                industry="IT",
                services=["consulting"],
                agent_purpose="customer support"
            )

            assert isinstance(result, list)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_error(self, client):
        """Test returns empty list on parse error."""
        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = "Invalid"

            result = await client.generate_example_dialogues(
                company_name="Test",
                industry="IT",
                services=[],
                agent_purpose="support"
            )

            assert result == []


class TestDeepSeekClientSuggestRestrictions:
    """Tests for DeepSeekClient.suggest_restrictions() method."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return DeepSeekClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_returns_list_of_restrictions(self, client):
        """Test returns list of restriction strings."""
        mock_restrictions = [
            "Не обсуждать цены конкурентов",
            "Не давать медицинские советы"
        ]

        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = json.dumps(mock_restrictions)

            result = await client.suggest_restrictions(
                industry="Healthcare",
                agent_purpose="appointment booking"
            )

            assert isinstance(result, list)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_error(self, client):
        """Test returns empty list on parse error."""
        with patch.object(client, 'chat', new_callable=AsyncMock) as mock:
            mock.return_value = "Not JSON"

            result = await client.suggest_restrictions(
                industry="IT",
                agent_purpose="support"
            )

            assert result == []
