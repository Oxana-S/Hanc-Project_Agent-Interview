"""
Tests for src/research/web_search.py

Comprehensive tests for WebSearchClient class.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.research.web_search import WebSearchClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tavily_response(results=None):
    """Create a mock httpx response for Tavily API."""
    if results is None:
        results = [
            {
                "title": "Tavily Result 1",
                "url": "https://example.com/tavily1",
                "content": "Snippet from Tavily search result one.",
            },
            {
                "title": "Tavily Result 2",
                "url": "https://example.com/tavily2",
                "content": "Snippet from Tavily search result two.",
            },
        ]
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": results}
    return mock_response


def _make_bing_response(results=None):
    """Create a mock httpx response for Bing API."""
    if results is None:
        results = [
            {
                "name": "Bing Result 1",
                "url": "https://example.com/bing1",
                "snippet": "Snippet from Bing search result one.",
            },
            {
                "name": "Bing Result 2",
                "url": "https://example.com/bing2",
                "snippet": "Snippet from Bing search result two.",
            },
        ]
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"webPages": {"value": results}}
    return mock_response


def _make_async_client(mock_response):
    """Wrap a mock response into a mock httpx.AsyncClient with context manager."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ===================================================================
# TestWebSearchClientInit
# ===================================================================

class TestWebSearchClientInit:
    """Tests for WebSearchClient initialization."""

    def test_init_with_explicit_keys(self):
        """Test initialization with explicit API keys."""
        client = WebSearchClient(
            tavily_api_key="tavily-key-123",
            bing_api_key="bing-key-456",
        )
        assert client.tavily_api_key == "tavily-key-123"
        assert client.bing_api_key == "bing-key-456"

    @patch.dict("os.environ", {
        "TAVILY_API_KEY": "env-tavily-key",
        "BING_API_KEY": "env-bing-key",
    })
    def test_init_from_env_vars(self):
        """Test initialization from environment variables when no explicit keys provided."""
        client = WebSearchClient()
        assert client.tavily_api_key == "env-tavily-key"
        assert client.bing_api_key == "env-bing-key"

    @patch.dict("os.environ", {}, clear=True)
    def test_init_no_keys_both_none(self):
        """Test initialization with no keys results in None for both."""
        client = WebSearchClient()
        assert client.tavily_api_key is None
        assert client.bing_api_key is None

    @patch.dict("os.environ", {}, clear=True)
    def test_init_partial_keys_only_tavily(self):
        """Test initialization with only Tavily key provided."""
        client = WebSearchClient(tavily_api_key="tavily-only")
        assert client.tavily_api_key == "tavily-only"
        assert client.bing_api_key is None


# ===================================================================
# TestSearch
# ===================================================================

class TestSearch:
    """Tests for WebSearchClient.search() orchestration method."""

    @pytest.mark.asyncio
    async def test_search_uses_tavily_first(self):
        """Test that search() prefers Tavily when both keys are available."""
        client = WebSearchClient(
            tavily_api_key="tavily-key",
            bing_api_key="bing-key",
        )

        mock_http = _make_async_client(_make_tavily_response())

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client.search("test query")

        assert len(results) == 2
        assert all(r["source"] == "tavily" for r in results)
        # Bing should NOT have been called (GET)
        mock_http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_fallback_to_bing_on_tavily_failure(self):
        """Test that search() falls back to Bing when Tavily raises an exception."""
        client = WebSearchClient(
            tavily_api_key="tavily-key",
            bing_api_key="bing-key",
        )

        tavily_client = _make_async_client(MagicMock())
        tavily_client.post = AsyncMock(side_effect=Exception("Tavily API down"))

        bing_response = _make_bing_response()
        bing_client = _make_async_client(bing_response)

        call_count = 0

        def side_effect_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tavily_client
            return bing_client

        with patch("src.research.web_search.httpx.AsyncClient", side_effect=side_effect_factory):
            results = await client.search("test query")

        assert len(results) == 2
        assert all(r["source"] == "bing" for r in results)

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_no_keys(self):
        """Test that search() returns empty list when no API keys are configured."""
        client = WebSearchClient()
        client.tavily_api_key = None
        client.bing_api_key = None

        results = await client.search("test query")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_both_fail(self):
        """Test that search() returns empty list when both APIs fail."""
        client = WebSearchClient(
            tavily_api_key="tavily-key",
            bing_api_key="bing-key",
        )

        failing_client = _make_async_client(MagicMock())
        failing_client.post = AsyncMock(side_effect=Exception("Tavily error"))
        failing_client.get = AsyncMock(side_effect=Exception("Bing error"))

        with patch("src.research.web_search.httpx.AsyncClient", return_value=failing_client):
            results = await client.search("test query")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_passes_params_to_tavily(self):
        """Test that search() passes max_results and search_depth to Tavily."""
        client = WebSearchClient(tavily_api_key="tavily-key")

        mock_response = _make_tavily_response()
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            await client.search("query", max_results=10, search_depth="advanced")

        call_args = mock_http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["query"] == "query"
        assert payload["max_results"] == 10
        assert payload["search_depth"] == "advanced"

    @pytest.mark.asyncio
    async def test_search_passes_params_to_bing(self):
        """Test that search() passes max_results to Bing when Tavily is unavailable."""
        client = WebSearchClient(bing_api_key="bing-key")

        mock_response = _make_bing_response()
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            await client.search("query", max_results=7)

        call_args = mock_http.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params")
        assert params["q"] == "query"
        assert params["count"] == 7


# ===================================================================
# TestSearchTavily
# ===================================================================

class TestSearchTavily:
    """Tests for WebSearchClient._search_tavily() private method."""

    @pytest.mark.asyncio
    async def test_search_tavily_successful(self):
        """Test successful Tavily search returns parsed results."""
        client = WebSearchClient(tavily_api_key="test-key")

        mock_response = _make_tavily_response()
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client._search_tavily("test query", 5, "basic")

        assert len(results) == 2
        assert results[0]["title"] == "Tavily Result 1"
        assert results[0]["url"] == "https://example.com/tavily1"

    @pytest.mark.asyncio
    async def test_search_tavily_result_format(self):
        """Test that Tavily results have all required fields with correct structure."""
        client = WebSearchClient(tavily_api_key="test-key")

        mock_response = _make_tavily_response([
            {"title": "Title", "url": "https://example.com", "content": "Snippet text"}
        ])
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client._search_tavily("query", 5, "basic")

        assert len(results) == 1
        result = results[0]
        assert "title" in result
        assert "url" in result
        assert "snippet" in result
        assert "source" in result
        assert result["source"] == "tavily"
        assert result["title"] == "Title"
        assert result["url"] == "https://example.com"
        assert result["snippet"] == "Snippet text"

    @pytest.mark.asyncio
    async def test_search_tavily_truncates_snippet_to_500(self):
        """Test that Tavily snippets are truncated to 500 characters."""
        client = WebSearchClient(tavily_api_key="test-key")

        long_content = "A" * 1000
        mock_response = _make_tavily_response([
            {"title": "Title", "url": "https://example.com", "content": long_content}
        ])
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client._search_tavily("query", 5, "basic")

        assert len(results[0]["snippet"]) == 500

    @pytest.mark.asyncio
    async def test_search_tavily_http_error(self):
        """Test that Tavily raises exception on HTTP error."""
        client = WebSearchClient(tavily_api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(Exception, match="HTTP 500"):
                await client._search_tavily("query", 5, "basic")

    @pytest.mark.asyncio
    async def test_search_tavily_empty_results(self):
        """Test that Tavily returns empty list when API returns no results."""
        client = WebSearchClient(tavily_api_key="test-key")

        mock_response = _make_tavily_response([])
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client._search_tavily("query", 5, "basic")

        assert results == []


# ===================================================================
# TestSearchBing
# ===================================================================

class TestSearchBing:
    """Tests for WebSearchClient._search_bing() private method."""

    @pytest.mark.asyncio
    async def test_search_bing_successful(self):
        """Test successful Bing search returns parsed results."""
        client = WebSearchClient(bing_api_key="test-key")

        mock_response = _make_bing_response()
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client._search_bing("test query", 5)

        assert len(results) == 2
        assert results[0]["title"] == "Bing Result 1"
        assert results[0]["url"] == "https://example.com/bing1"

    @pytest.mark.asyncio
    async def test_search_bing_result_format(self):
        """Test that Bing results have all required fields with correct structure."""
        client = WebSearchClient(bing_api_key="test-key")

        mock_response = _make_bing_response([
            {"name": "Title", "url": "https://example.com", "snippet": "Snippet text"}
        ])
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client._search_bing("query", 5)

        assert len(results) == 1
        result = results[0]
        assert "title" in result
        assert "url" in result
        assert "snippet" in result
        assert "source" in result
        assert result["source"] == "bing"
        assert result["title"] == "Title"
        assert result["url"] == "https://example.com"
        assert result["snippet"] == "Snippet text"

    @pytest.mark.asyncio
    async def test_search_bing_uses_ru_market(self):
        """Test that Bing search uses Russian market parameter."""
        client = WebSearchClient(bing_api_key="test-key")

        mock_response = _make_bing_response()
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            await client._search_bing("query", 5)

        call_args = mock_http.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params")
        assert params["mkt"] == "ru-RU"

        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert headers["Ocp-Apim-Subscription-Key"] == "test-key"

    @pytest.mark.asyncio
    async def test_search_bing_http_error(self):
        """Test that Bing raises exception on HTTP error."""
        client = WebSearchClient(bing_api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 403")
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            with pytest.raises(Exception, match="HTTP 403"):
                await client._search_bing("query", 5)

    @pytest.mark.asyncio
    async def test_search_bing_empty_results(self):
        """Test that Bing returns empty list when API returns no results."""
        client = WebSearchClient(bing_api_key="test-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"webPages": {"value": []}}
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client._search_bing("query", 5)

        assert results == []


# ===================================================================
# TestSearchIndustryInsights
# ===================================================================

class TestSearchIndustryInsights:
    """Tests for WebSearchClient.search_industry_insights() method."""

    @pytest.mark.asyncio
    async def test_search_industry_insights_default_topics(self):
        """Test that default topics are used when none are provided."""
        client = WebSearchClient(tavily_api_key="test-key")

        mock_response = _make_tavily_response([])
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client.search_industry_insights("IT")

        expected_topics = [
            "тренды автоматизации",
            "голосовые боты кейсы",
            "проблемы и решения",
        ]
        assert set(results.keys()) == set(expected_topics)

    @pytest.mark.asyncio
    async def test_search_industry_insights_custom_topics(self):
        """Test that custom topics are used when provided."""
        client = WebSearchClient(tavily_api_key="test-key")

        mock_response = _make_tavily_response([])
        mock_http = _make_async_client(mock_response)

        custom_topics = ["ROI анализ", "конкуренты"]

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client.search_industry_insights("Retail", topics=custom_topics)

        assert set(results.keys()) == {"ROI анализ", "конкуренты"}

    @pytest.mark.asyncio
    async def test_search_industry_insights_results_by_topic(self):
        """Test that each topic key maps to its search results."""
        client = WebSearchClient(tavily_api_key="test-key")

        tavily_results = [
            {"title": "Insight", "url": "https://example.com", "content": "Text"}
        ]
        mock_response = _make_tavily_response(tavily_results)
        mock_http = _make_async_client(mock_response)

        with patch("src.research.web_search.httpx.AsyncClient", return_value=mock_http):
            results = await client.search_industry_insights("Healthcare")

        for topic, topic_results in results.items():
            assert isinstance(topic_results, list)
            assert len(topic_results) == 1
            assert topic_results[0]["title"] == "Insight"
            assert topic_results[0]["source"] == "tavily"

    @pytest.mark.asyncio
    async def test_search_industry_insights_builds_correct_queries(self):
        """Test that queries are formed as '{industry} {topic}'."""
        client = WebSearchClient(tavily_api_key="test-key")

        captured_queries = []

        async def mock_search(query, max_results=5):
            captured_queries.append(query)
            return []

        with patch.object(client, "search", side_effect=mock_search):
            await client.search_industry_insights(
                "Финтех", topics=["тренды", "риски"]
            )

        assert captured_queries == ["Финтех тренды", "Финтех риски"]

    @pytest.mark.asyncio
    async def test_search_industry_insights_handles_search_errors(self):
        """Test that industry insights handles errors gracefully from underlying search."""
        client = WebSearchClient()
        client.tavily_api_key = None
        client.bing_api_key = None

        results = await client.search_industry_insights("Unknown Industry")

        # With no keys, search() returns [] for each topic
        assert len(results) == 3
        for topic_results in results.values():
            assert topic_results == []
