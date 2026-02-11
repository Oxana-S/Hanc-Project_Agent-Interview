"""
Unit tests for ResearchEngine — website parsing, web search, and LLM synthesis.

Tests cover:
- ResearchResult model defaults and has_data() logic
- ResearchEngine initialization (default/custom clients, flags)
- research() orchestration (task selection, gather, merge, synthesize)
- _parse_website() success and error paths
- _search_industry() success, error, and query format
- _merge_result() for each data type
- _synthesize_insights() including JSON parsing, code-block handling, and errors
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.research.engine import ResearchEngine, ResearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_deepseek():
    """DeepSeek client mock returning valid synthesis JSON."""
    client = AsyncMock()
    client.chat = AsyncMock(return_value=json.dumps({
        "industry_insights": ["insight1", "insight2"],
        "best_practices": ["bp1"],
        "compliance_notes": ["note1"],
    }))
    return client


@pytest.fixture
def mock_web_search():
    """WebSearchClient mock returning a list of search results."""
    client = AsyncMock()
    client.search = AsyncMock(return_value=[
        {"title": "Result 1", "url": "https://example.com/1", "snippet": "snippet 1"},
        {"title": "Result 2", "url": "https://example.com/2", "snippet": "snippet 2"},
    ])
    return client


@pytest.fixture
def mock_website_parser():
    """WebsiteParser mock returning parsed website data."""
    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={
        "title": "Test Company",
        "description": "We do great things",
        "services": ["service1", "service2"],
    })
    return parser


@pytest.fixture
def engine(mock_deepseek, mock_web_search, mock_website_parser):
    """ResearchEngine with all mocked dependencies."""
    eng = ResearchEngine(
        deepseek_client=mock_deepseek,
        web_search_client=mock_web_search,
    )
    eng.website_parser = mock_website_parser
    return eng


# ===========================================================================
# TestResearchResult
# ===========================================================================

class TestResearchResult:
    """Tests for the ResearchResult Pydantic model."""

    @pytest.mark.unit
    def test_research_result_defaults(self):
        """Default ResearchResult has empty fields and zero confidence."""
        result = ResearchResult()
        assert result.website_data is None
        assert result.industry_insights == []
        assert result.competitor_info == []
        assert result.best_practices == []
        assert result.compliance_notes == []
        assert result.similar_cases == []
        assert result.sources_used == []
        assert result.confidence_score == 0.0
        assert isinstance(result.research_timestamp, datetime)

    @pytest.mark.unit
    def test_research_result_has_data_with_website(self):
        """has_data() returns True when website_data is present."""
        result = ResearchResult(website_data={"title": "Site"})
        assert result.has_data() is True

    @pytest.mark.unit
    def test_research_result_has_data_with_insights(self):
        """has_data() returns True when industry_insights is non-empty."""
        result = ResearchResult(industry_insights=["trend1"])
        assert result.has_data() is True

    @pytest.mark.unit
    def test_research_result_has_data_empty(self):
        """has_data() returns False when all checked fields are empty."""
        result = ResearchResult()
        assert result.has_data() is False

    @pytest.mark.unit
    def test_research_result_has_data_with_best_practices(self):
        """has_data() returns True when best_practices is non-empty."""
        result = ResearchResult(best_practices=["practice1"])
        assert result.has_data() is True


# ===========================================================================
# TestResearchEngineInit
# ===========================================================================

class TestResearchEngineInit:
    """Tests for ResearchEngine.__init__."""

    @pytest.mark.unit
    def test_init_defaults(self):
        """Default init creates DeepSeekClient, WebSearchClient, WebsiteParser."""
        with patch("src.research.engine.DeepSeekClient") as MockDS, \
             patch("src.research.engine.WebSearchClient") as MockWS, \
             patch("src.research.engine.WebsiteParser") as MockWP:
            eng = ResearchEngine()
            MockDS.assert_called_once()
            MockWS.assert_called_once()
            MockWP.assert_called_once()
            assert eng.enable_web_search is True
            assert eng.enable_website_parser is True
            assert eng.enable_rag is False

    @pytest.mark.unit
    def test_init_custom_clients(self):
        """Custom clients are used instead of creating new instances."""
        ds = AsyncMock()
        ws = AsyncMock()
        with patch("src.research.engine.WebsiteParser"):
            eng = ResearchEngine(deepseek_client=ds, web_search_client=ws)
        assert eng.deepseek is ds
        assert eng.web_search is ws

    @pytest.mark.unit
    def test_init_flags_disabled(self):
        """Flags can disable web_search, website_parser, enable rag."""
        with patch("src.research.engine.DeepSeekClient"), \
             patch("src.research.engine.WebSearchClient"), \
             patch("src.research.engine.WebsiteParser"):
            eng = ResearchEngine(
                enable_web_search=False,
                enable_website_parser=False,
                enable_rag=True,
            )
        assert eng.enable_web_search is False
        assert eng.enable_website_parser is False
        assert eng.enable_rag is True

    @pytest.mark.unit
    def test_init_website_parser_always_created(self):
        """WebsiteParser is always instantiated regardless of flags."""
        with patch("src.research.engine.DeepSeekClient"), \
             patch("src.research.engine.WebSearchClient"), \
             patch("src.research.engine.WebsiteParser") as MockWP:
            ResearchEngine(enable_website_parser=False)
            MockWP.assert_called_once()


# ===========================================================================
# TestResearch
# ===========================================================================

class TestResearch:
    """Tests for ResearchEngine.research() orchestration."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_website_only(self, engine, mock_website_parser, mock_deepseek):
        """Only website provided -> parses website, no industry search."""
        result = await engine.research(website="https://example.com")

        mock_website_parser.parse.assert_awaited_once_with("https://example.com")
        engine.web_search.search.assert_not_awaited()
        assert result.website_data is not None
        assert isinstance(result, ResearchResult)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_industry_only(self, engine, mock_website_parser):
        """Only industry provided -> web search, no website parsing."""
        result = await engine.research(industry="logistics")

        mock_website_parser.parse.assert_not_awaited()
        engine.web_search.search.assert_awaited()
        assert isinstance(result, ResearchResult)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_both(self, engine, mock_website_parser):
        """Website + industry -> both tasks run."""
        result = await engine.research(
            website="https://example.com",
            industry="logistics",
        )

        mock_website_parser.parse.assert_awaited_once()
        engine.web_search.search.assert_awaited()
        assert isinstance(result, ResearchResult)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_no_params(self, engine, mock_website_parser):
        """No website, no industry -> empty result, no tasks run."""
        result = await engine.research()

        mock_website_parser.parse.assert_not_awaited()
        engine.web_search.search.assert_not_awaited()
        assert result.has_data() is False
        assert result.confidence_score == 0.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_website_disabled(self, mock_deepseek, mock_web_search):
        """enable_website_parser=False -> website is ignored even if provided."""
        eng = ResearchEngine(
            deepseek_client=mock_deepseek,
            web_search_client=mock_web_search,
            enable_website_parser=False,
        )
        mock_parser = AsyncMock()
        eng.website_parser = mock_parser

        result = await eng.research(website="https://example.com")

        mock_parser.parse.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_web_search_disabled(self, mock_deepseek, mock_web_search):
        """enable_web_search=False -> industry search is skipped."""
        eng = ResearchEngine(
            deepseek_client=mock_deepseek,
            web_search_client=mock_web_search,
            enable_web_search=False,
        )
        mock_parser = AsyncMock()
        eng.website_parser = mock_parser

        result = await eng.research(industry="logistics")

        mock_web_search.search.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_exception_handling(self, engine, mock_website_parser):
        """One task raising exception does not prevent others from succeeding."""
        mock_website_parser.parse.side_effect = RuntimeError("Parse failed")

        result = await engine.research(
            website="https://example.com",
            industry="logistics",
        )

        # Website parsing failed but industry search should still produce data
        assert isinstance(result, ResearchResult)
        # web_search was called
        engine.web_search.search.assert_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_research_calls_synthesize_when_has_data(self, engine, mock_deepseek):
        """Synthesis is called when has_data() is True after merge."""
        result = await engine.research(website="https://example.com")

        mock_deepseek.chat.assert_awaited_once()
        assert result.confidence_score == 0.8


# ===========================================================================
# TestParseWebsite
# ===========================================================================

class TestParseWebsite:
    """Tests for ResearchEngine._parse_website()."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_website_success(self, engine, mock_website_parser):
        """Successful parse returns dict with type=website and data."""
        result = await engine._parse_website("https://example.com")

        assert result["type"] == "website"
        assert "data" in result
        assert result["data"]["title"] == "Test Company"
        mock_website_parser.parse.assert_awaited_once_with("https://example.com")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_website_error(self, engine, mock_website_parser):
        """Parser exception returns dict with type=website and error string."""
        mock_website_parser.parse.side_effect = ConnectionError("Timeout")

        result = await engine._parse_website("https://bad-site.com")

        assert result["type"] == "website"
        assert "error" in result
        assert "Timeout" in result["error"]
        assert "data" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_website_returns_full_data(self, engine, mock_website_parser):
        """Parsed data is passed through without modification."""
        mock_website_parser.parse.return_value = {
            "title": "Acme Corp",
            "description": "Leading provider",
            "services": ["consulting"],
            "contacts": {"email": "info@acme.com"},
        }

        result = await engine._parse_website("https://acme.com")

        assert result["data"]["contacts"]["email"] == "info@acme.com"


# ===========================================================================
# TestSearchIndustry
# ===========================================================================

class TestSearchIndustry:
    """Tests for ResearchEngine._search_industry()."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_industry_success(self, engine):
        """Successful search returns type=web_search with aggregated data."""
        result = await engine._search_industry("logistics")

        assert result["type"] == "web_search"
        assert "data" in result
        # Two queries -> 2 calls, each returns 2 results -> 4 total
        assert len(result["data"]) == 4

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_industry_error(self, engine):
        """Search exception returns dict with type=web_search and error."""
        engine.web_search.search.side_effect = RuntimeError("API limit")

        result = await engine._search_industry("healthcare")

        assert result["type"] == "web_search"
        assert "error" in result
        assert "API limit" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_industry_queries_format(self, engine):
        """Exactly 2 queries are sent, both containing the industry name."""
        await engine._search_industry("retail")

        assert engine.web_search.search.await_count == 2
        calls = engine.web_search.search.call_args_list
        # First query: "{industry} голосовой агент автоматизация"
        assert "retail" in calls[0].args[0]
        assert "голосовой агент автоматизация" in calls[0].args[0]
        # Second query: "{industry} тренды автоматизации 2026"
        assert "retail" in calls[1].args[0]
        assert "тренды автоматизации 2026" in calls[1].args[0]


# ===========================================================================
# TestMergeResult
# ===========================================================================

class TestMergeResult:
    """Tests for ResearchEngine._merge_result()."""

    @pytest.mark.unit
    def test_merge_website_data(self, engine):
        """Website data is set on result.website_data and source is recorded."""
        result = ResearchResult()
        engine._merge_result(result, {
            "type": "website",
            "data": {"title": "My Site", "description": "Desc"},
        })

        assert result.website_data == {"title": "My Site", "description": "Desc"}
        assert "website_parser" in result.sources_used

    @pytest.mark.unit
    def test_merge_web_search_data(self, engine):
        """Web search adds source but does not directly populate fields."""
        result = ResearchResult()
        engine._merge_result(result, {
            "type": "web_search",
            "data": [{"title": "t", "url": "u", "snippet": "s"}],
        })

        assert "web_search" in result.sources_used

    @pytest.mark.unit
    def test_merge_rag_data(self, engine):
        """RAG data is set on result.similar_cases and source is recorded."""
        result = ResearchResult()
        cases = [{"case_id": "1", "summary": "Similar project"}]
        engine._merge_result(result, {
            "type": "rag",
            "data": cases,
        })

        assert result.similar_cases == cases
        assert "rag" in result.sources_used

    @pytest.mark.unit
    def test_merge_empty_data_skipped(self, engine):
        """If data content is falsy (None, empty list), merge is a no-op."""
        result = ResearchResult()
        engine._merge_result(result, {"type": "website", "data": None})
        engine._merge_result(result, {"type": "web_search", "data": []})
        engine._merge_result(result, {"type": "rag", "data": []})

        assert result.website_data is None
        assert result.sources_used == []
        assert result.similar_cases == []


# ===========================================================================
# TestSynthesizeInsights
# ===========================================================================

class TestSynthesizeInsights:
    """Tests for ResearchEngine._synthesize_insights()."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_synthesize_success(self, engine, mock_deepseek):
        """Valid JSON response populates insights, practices, notes."""
        result = ResearchResult(website_data={"title": "Site"})

        result = await engine._synthesize_insights(result, "logistics", "extra context")

        assert result.industry_insights == ["insight1", "insight2"]
        assert result.best_practices == ["bp1"]
        assert result.compliance_notes == ["note1"]
        mock_deepseek.chat.assert_awaited_once()
        # Verify temperature=0.3 is passed
        _, kwargs = mock_deepseek.chat.call_args
        assert kwargs.get("temperature") == 0.3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_synthesize_with_json_code_block(self, engine, mock_deepseek):
        """Handles ```json ... ``` wrapper around the JSON response."""
        mock_deepseek.chat.return_value = """Some preamble text
```json
{
    "industry_insights": ["from_code_block"],
    "best_practices": ["bp_code_block"],
    "compliance_notes": []
}
```
Some trailing text"""

        result = ResearchResult(website_data={"title": "Site"})
        result = await engine._synthesize_insights(result, "retail", None)

        assert result.industry_insights == ["from_code_block"]
        assert result.best_practices == ["bp_code_block"]
        assert result.compliance_notes == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_synthesize_error(self, engine, mock_deepseek):
        """DeepSeek failure leaves result unchanged (silent catch)."""
        mock_deepseek.chat.side_effect = RuntimeError("LLM down")

        original_insights = ["pre-existing"]
        result = ResearchResult(
            website_data={"title": "Site"},
            industry_insights=original_insights.copy(),
        )
        result = await engine._synthesize_insights(result, "finance", None)

        # Result is returned unchanged on error
        assert result.industry_insights == original_insights
        assert result.confidence_score == 0.0  # Not set to 0.8

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_synthesize_sets_confidence_score(self, engine, mock_deepseek):
        """Successful synthesis sets confidence_score to 0.8."""
        result = ResearchResult(website_data={"title": "Site"})

        result = await engine._synthesize_insights(result, "healthcare", None)

        assert result.confidence_score == 0.8
