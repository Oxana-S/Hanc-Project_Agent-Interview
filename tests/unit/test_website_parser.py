"""
Unit tests for WebsiteParser.

Tests cover initialization, URL parsing, HTML extraction methods,
contact/social link extraction, and multi-page parsing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.research.website_parser import WebsiteParser


# ============ HELPERS ============

SAMPLE_HTML = """
<html>
<head>
    <title>Hanc.AI - Voice Agents</title>
    <meta name="description" content="We build intelligent voice agents for business">
</head>
<body>
    <h2>Our Services</h2>
    <h3>AI Voice Consulting</h3>
    <ul>
        <li>Voice agent development and deployment</li>
        <li>Custom AI integration services</li>
        <li>24/7 automated customer support</li>
    </ul>
    <p>Phone: +7 (495) 123-45-67</p>
    <p>Email: info@hanc.ai</p>
    <a href="https://t.me/hancai">Telegram</a>
    <a href="https://wa.me/74951234567">WhatsApp</a>
    <a href="https://vk.com/hancai">VK</a>
    <a href="https://instagram.com/hancai">Instagram</a>
</body>
</html>
"""


def _make_mock_client(html: str = SAMPLE_HTML, raise_error: Exception = None):
    """Create a mock httpx.AsyncClient that returns given HTML or raises error."""
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    if raise_error:
        mock_client.get = AsyncMock(side_effect=raise_error)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return mock_client


# ============ INIT TESTS ============

class TestWebsiteParserInit:
    """Test WebsiteParser initialization."""

    @pytest.mark.unit
    def test_init_default_timeout(self):
        """Test default timeout is 30 seconds."""
        parser = WebsiteParser()
        assert parser.timeout == 30.0

    @pytest.mark.unit
    def test_init_custom_timeout(self):
        """Test custom timeout is stored correctly."""
        parser = WebsiteParser(timeout=15.0)
        assert parser.timeout == 15.0

    @pytest.mark.unit
    def test_init_headers_set(self):
        """Test that User-Agent header is set."""
        parser = WebsiteParser()
        assert "User-Agent" in parser.headers
        assert "VoiceInterviewerBot" in parser.headers["User-Agent"]


# ============ PARSE TESTS ============

class TestParse:
    """Test WebsiteParser.parse() method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_successful(self):
        """Test successful parse returns structured result with correct title."""
        parser = WebsiteParser()
        mock_client = _make_mock_client(SAMPLE_HTML)

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("https://example.com")

        assert result["title"] == "Hanc.AI - Voice Agents"
        assert result["description"] == "We build intelligent voice agents for business"
        assert result["url"] == "https://example.com"
        assert "error" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_adds_https_prefix(self):
        """Test that bare domain gets https:// prefix added."""
        parser = WebsiteParser()
        mock_client = _make_mock_client("<html><title>Test</title></html>")

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("example.com")

        assert result["url"] == "https://example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_preserves_https(self):
        """Test that https:// URL is not modified."""
        parser = WebsiteParser()
        mock_client = _make_mock_client("<html><title>Test</title></html>")

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("https://example.com")

        assert result["url"] == "https://example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_preserves_http(self):
        """Test that http:// URL is not modified to https://."""
        parser = WebsiteParser()
        mock_client = _make_mock_client("<html><title>Test</title></html>")

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("http://example.com")

        assert result["url"] == "http://example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_http_error_returns_error_dict(self):
        """Test that HTTP error returns dict with 'error' key."""
        parser = WebsiteParser()
        error = Exception("404 Not Found")
        mock_client = _make_mock_client(raise_error=error)

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("https://nonexistent.example.com")

        assert "error" in result
        assert "404 Not Found" in result["error"]
        assert result["url"] == "https://nonexistent.example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_timeout_returns_error_dict(self):
        """Test that timeout exception returns error dict."""
        import httpx as real_httpx
        parser = WebsiteParser()
        error = real_httpx.TimeoutException("Connection timed out")
        mock_client = _make_mock_client(raise_error=error)

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("https://slow.example.com")

        assert "error" in result
        assert result["url"] == "https://slow.example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_connection_error_returns_error_dict(self):
        """Test that connection error returns error dict."""
        import httpx as real_httpx
        parser = WebsiteParser()
        error = real_httpx.ConnectError("Connection refused")
        mock_client = _make_mock_client(raise_error=error)

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("https://down.example.com")

        assert "error" in result
        assert result["url"] == "https://down.example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_result_has_all_keys(self):
        """Test that successful parse result contains all expected keys."""
        parser = WebsiteParser()
        mock_client = _make_mock_client(SAMPLE_HTML)

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse("https://example.com")

        expected_keys = {"url", "title", "description", "services", "contacts", "social_links"}
        assert set(result.keys()) == expected_keys

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_follows_redirects(self):
        """Test that AsyncClient is created with follow_redirects=True."""
        parser = WebsiteParser()
        mock_client = _make_mock_client("<html><title>Test</title></html>")

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await parser.parse("https://example.com")

        mock_cls.assert_called_once_with(timeout=30.0, follow_redirects=True)


# ============ EXTRACT TITLE TESTS ============

class TestExtractTitle:
    """Test WebsiteParser._extract_title() method."""

    @pytest.mark.unit
    def test_extract_title_found(self):
        """Test title extraction from valid HTML."""
        parser = WebsiteParser()
        result = parser._extract_title("<html><title>My Website</title></html>")
        assert result == "My Website"

    @pytest.mark.unit
    def test_extract_title_not_found(self):
        """Test returns None when no title tag present."""
        parser = WebsiteParser()
        result = parser._extract_title("<html><body>No title here</body></html>")
        assert result is None

    @pytest.mark.unit
    def test_extract_title_strips_whitespace(self):
        """Test that extracted title has whitespace stripped."""
        parser = WebsiteParser()
        result = parser._extract_title("<html><title>  Spaced Title  </title></html>")
        assert result == "Spaced Title"

    @pytest.mark.unit
    def test_extract_title_case_insensitive(self):
        """Test that title tag matching is case-insensitive."""
        parser = WebsiteParser()
        result = parser._extract_title("<html><TITLE>Upper Case</TITLE></html>")
        assert result == "Upper Case"


# ============ EXTRACT META DESCRIPTION TESTS ============

class TestExtractMetaDescription:
    """Test WebsiteParser._extract_meta_description() method."""

    @pytest.mark.unit
    def test_extract_meta_description_standard_format(self):
        """Test extraction with name before content attribute."""
        parser = WebsiteParser()
        html = '<meta name="description" content="A great website about AI">'
        result = parser._extract_meta_description(html)
        assert result == "A great website about AI"

    @pytest.mark.unit
    def test_extract_meta_description_reversed_format(self):
        """Test extraction with content before name attribute."""
        parser = WebsiteParser()
        html = '<meta content="Reversed attribute order" name="description">'
        result = parser._extract_meta_description(html)
        assert result == "Reversed attribute order"

    @pytest.mark.unit
    def test_extract_meta_description_not_found(self):
        """Test returns None when no meta description present."""
        parser = WebsiteParser()
        html = '<html><head><meta name="viewport" content="width=device-width"></head></html>'
        result = parser._extract_meta_description(html)
        assert result is None

    @pytest.mark.unit
    def test_extract_meta_description_strips_whitespace(self):
        """Test that extracted description has whitespace stripped."""
        parser = WebsiteParser()
        html = '<meta name="description" content="  Spaced description  ">'
        result = parser._extract_meta_description(html)
        assert result == "Spaced description"


# ============ EXTRACT SERVICES TESTS ============

class TestExtractServices:
    """Test WebsiteParser._extract_services() method."""

    @pytest.mark.unit
    def test_extract_services_from_list_items(self):
        """Test extraction of services from <li> tags."""
        parser = WebsiteParser()
        html = """
        <ul>
            <li>Voice agent development and deployment</li>
            <li>Custom AI integration services</li>
        </ul>
        """
        result = parser._extract_services(html)
        assert len(result) >= 1
        assert any("Voice agent" in s or "AI integration" in s for s in result)

    @pytest.mark.unit
    def test_extract_services_from_headings(self):
        """Test extraction of services from <h2> and <h3> tags."""
        parser = WebsiteParser()
        html = """
        <h2>Cloud Solutions</h2>
        <h3>Data Analytics</h3>
        """
        result = parser._extract_services(html)
        assert "Cloud Solutions" in result
        assert "Data Analytics" in result

    @pytest.mark.unit
    def test_extract_services_deduplication(self):
        """Test that duplicate services are removed."""
        parser = WebsiteParser()
        html = """
        <h2>Cloud Solutions</h2>
        <h3>Cloud Solutions</h3>
        """
        result = parser._extract_services(html)
        assert result.count("Cloud Solutions") == 1

    @pytest.mark.unit
    def test_extract_services_max_ten(self):
        """Test that maximum 10 services are returned."""
        parser = WebsiteParser()
        items = "\n".join(
            f"<li>Service number {i:02d} with extra description text</li>"
            for i in range(20)
        )
        html = f"<ul>{items}</ul>"
        result = parser._extract_services(html)
        assert len(result) <= 10

    @pytest.mark.unit
    def test_extract_services_filters_short_items(self):
        """Test that <li> items shorter than required length are filtered out."""
        parser = WebsiteParser()
        html = """
        <ul>
            <li>Short</li>
            <li>Also a bit short item</li>
            <li>This is a sufficiently long service description item</li>
        </ul>
        """
        result = parser._extract_services(html)
        # "Short" is < 10 chars so won't match the regex
        # Items matching regex but with cleaned length <= 5 are also filtered
        for service in result:
            assert len(service) > 5


# ============ EXTRACT CONTACTS TESTS ============

class TestExtractContacts:
    """Test WebsiteParser._extract_contacts() method."""

    @pytest.mark.unit
    def test_extract_contacts_russian_phone(self):
        """Test extraction of Russian +7 phone format."""
        parser = WebsiteParser()
        html = '<p>Call us: +7 (495) 123-45-67</p>'
        result = parser._extract_contacts(html)
        assert result["phone"] is not None
        assert "+7" in result["phone"]

    @pytest.mark.unit
    def test_extract_contacts_eight_format(self):
        """Test extraction of Russian 8-xxx phone format."""
        parser = WebsiteParser()
        html = '<p>Phone: 8 (495) 123-45-67</p>'
        result = parser._extract_contacts(html)
        assert result["phone"] is not None
        assert result["phone"].startswith("8")

    @pytest.mark.unit
    def test_extract_contacts_international_phone(self):
        """Test extraction of international phone format."""
        parser = WebsiteParser()
        html = '<p>Phone: +1 (212) 555-1234</p>'
        result = parser._extract_contacts(html)
        assert result["phone"] is not None
        assert "+1" in result["phone"]

    @pytest.mark.unit
    def test_extract_contacts_email(self):
        """Test extraction of email address."""
        parser = WebsiteParser()
        html = '<p>Write to us: contact@example.com</p>'
        result = parser._extract_contacts(html)
        assert result["email"] == "contact@example.com"

    @pytest.mark.unit
    def test_extract_contacts_empty_html(self):
        """Test that empty HTML returns all None contacts."""
        parser = WebsiteParser()
        result = parser._extract_contacts("<html><body>No contacts here</body></html>")
        assert result["phone"] is None
        assert result["email"] is None
        assert result["address"] is None


# ============ EXTRACT SOCIAL LINKS TESTS ============

class TestExtractSocialLinks:
    """Test WebsiteParser._extract_social_links() method."""

    @pytest.mark.unit
    def test_extract_social_links_telegram(self):
        """Test extraction of Telegram link."""
        parser = WebsiteParser()
        html = '<a href="https://t.me/hancai">Telegram</a>'
        result = parser._extract_social_links(html, "https://example.com")
        assert result["telegram"] == "https://t.me/hancai"

    @pytest.mark.unit
    def test_extract_social_links_whatsapp(self):
        """Test extraction of WhatsApp link."""
        parser = WebsiteParser()
        html = '<a href="https://wa.me/74951234567">WhatsApp</a>'
        result = parser._extract_social_links(html, "https://example.com")
        assert result["whatsapp"] == "https://wa.me/74951234567"

    @pytest.mark.unit
    def test_extract_social_links_vk(self):
        """Test extraction of VK link."""
        parser = WebsiteParser()
        html = '<a href="https://vk.com/hancai">VK</a>'
        result = parser._extract_social_links(html, "https://example.com")
        assert result["vk"] == "https://vk.com/hancai"

    @pytest.mark.unit
    def test_extract_social_links_instagram(self):
        """Test extraction of Instagram link."""
        parser = WebsiteParser()
        html = '<a href="https://instagram.com/hancai">Instagram</a>'
        result = parser._extract_social_links(html, "https://example.com")
        assert result["instagram"] == "https://instagram.com/hancai"

    @pytest.mark.unit
    def test_extract_social_links_none_found(self):
        """Test that all social links are None when none present in HTML."""
        parser = WebsiteParser()
        html = '<html><body>No social links</body></html>'
        result = parser._extract_social_links(html, "https://example.com")
        assert result["telegram"] is None
        assert result["whatsapp"] is None
        assert result["vk"] is None
        assert result["instagram"] is None


# ============ PARSE MULTIPLE PAGES TESTS ============

class TestParseMultiplePages:
    """Test WebsiteParser.parse_multiple_pages() method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_multiple_pages_delegates_to_parse(self):
        """Test that parse_multiple_pages delegates to parse and returns its result."""
        parser = WebsiteParser()
        mock_client = _make_mock_client(SAMPLE_HTML)

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse_multiple_pages("https://example.com", max_pages=5)

        assert result["title"] == "Hanc.AI - Voice Agents"
        assert result["url"] == "https://example.com"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_multiple_pages_error_handling(self):
        """Test that parse_multiple_pages propagates errors from parse."""
        parser = WebsiteParser()
        error = Exception("Connection failed")
        mock_client = _make_mock_client(raise_error=error)

        with patch("src.research.website_parser.httpx.AsyncClient", return_value=mock_client):
            result = await parser.parse_multiple_pages("https://down.example.com")

        assert "error" in result
        assert "Connection failed" in result["error"]
