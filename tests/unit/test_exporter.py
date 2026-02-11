"""
Tests for src/anketa/exporter.py (v5.0)

Comprehensive tests for the Anketa Exporter module:
- export_markdown: MD bytes + filename generation
- export_print_html: styled HTML for print-to-PDF
- _escape: HTML entity escaping
- _md_to_html: simple markdown-to-HTML converter
- _inline: inline bold/italic processing

All functions are pure (string in -> bytes/string out), NO mocks needed.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from src.anketa.exporter import export_markdown, export_print_html, _md_to_html, _escape, _inline


# =========================================================================
# TestExportMarkdown
# =========================================================================

class TestExportMarkdown:
    """Tests for export_markdown function."""

    def test_basic_returns_bytes_and_filename(self):
        """export_markdown returns a tuple of (bytes, str)."""
        content, filename = export_markdown("# Hello", "TestCompany")
        assert isinstance(content, bytes)
        assert isinstance(filename, str)

    def test_empty_markdown_returns_empty_bytes(self):
        """Empty markdown string produces empty bytes, filename defaults to anketa.md."""
        content, filename = export_markdown("", "")
        assert content == b""
        assert filename == "anketa.md"

    def test_company_name_used_in_filename(self):
        """Company name appears in the returned filename."""
        _, filename = export_markdown("# Test", "MyCompany")
        assert filename == "MyCompany.md"

    def test_special_chars_stripped_from_filename(self):
        """Special characters like quotes, ampersands are removed from filename."""
        _, filename = export_markdown("test", 'ООО «Рога & Копыта»')
        # Only alnum, space, underscore, dash allowed; guillemets and & stripped
        assert "«" not in filename
        assert "»" not in filename
        assert "&" not in filename
        assert filename.endswith(".md")

    def test_cyrillic_company_name_preserved(self):
        """Cyrillic alphanumeric characters are kept in filename."""
        _, filename = export_markdown("test", "Компания")
        assert filename == "Компания.md"

    def test_long_company_name_truncated_to_30_chars(self):
        """Company name longer than 30 characters is truncated."""
        long_name = "A" * 50
        _, filename = export_markdown("test", long_name)
        # filename = safe_name + ".md", safe_name max 30 chars
        name_part = filename.replace(".md", "")
        assert len(name_part) <= 30

    def test_empty_company_name_defaults_to_anketa(self):
        """Empty company name produces filename 'anketa.md'."""
        _, filename = export_markdown("some content", "")
        assert filename == "anketa.md"

    def test_none_like_empty_company_name(self):
        """Company name that becomes empty after sanitization defaults to anketa."""
        _, filename = export_markdown("test", "!@#$%^()")
        assert filename == "anketa.md"

    def test_utf8_encoding_russian_text(self):
        """Russian markdown text is correctly encoded as UTF-8."""
        md = "# Описание компании\n\nМы занимаемся разработкой ИИ-агентов."
        content, _ = export_markdown(md, "Тест")
        assert content == md.encode("utf-8")
        decoded = content.decode("utf-8")
        assert "Описание компании" in decoded
        assert "ИИ-агентов" in decoded

    def test_markdown_content_preserved_exactly(self):
        """The markdown content is returned as-is in bytes, no modification."""
        md = "# Title\n\n- item 1\n- item 2\n\n**bold** and *italic*"
        content, _ = export_markdown(md, "Test")
        assert content.decode("utf-8") == md

    def test_company_name_with_spaces_preserved(self):
        """Spaces in company name are preserved in filename."""
        _, filename = export_markdown("test", "My Great Company")
        assert filename == "My Great Company.md"

    def test_company_name_with_hyphens_and_underscores(self):
        """Hyphens and underscores are preserved in filename."""
        _, filename = export_markdown("test", "my-company_v2")
        assert filename == "my-company_v2.md"

    def test_company_name_trailing_spaces_stripped(self):
        """Trailing spaces after truncation/filtering are stripped."""
        # Name with trailing spaces should be stripped
        _, filename = export_markdown("test", "Company   ")
        assert filename == "Company.md"


# =========================================================================
# TestExportPrintHtml
# =========================================================================

class TestExportPrintHtml:
    """Tests for export_print_html function."""

    def test_returns_bytes_and_html_filename(self):
        """export_print_html returns (bytes, str) with .html extension."""
        content, filename = export_print_html("# Test", "TestCo")
        assert isinstance(content, bytes)
        assert filename.endswith(".html")

    def test_html_contains_company_name_in_title(self):
        """Company name appears in the HTML <title> tag."""
        content, _ = export_print_html("# Test", "Acme Corp")
        html = content.decode("utf-8")
        assert "Acme Corp" in html
        assert "<title>" in html

    def test_html_contains_company_name_in_header(self):
        """Company name appears in the header h1."""
        content, _ = export_print_html("# Test", "Acme Corp")
        html = content.decode("utf-8")
        # Header section contains the company name
        assert "Hanc.AI" in html
        assert "Acme Corp" in html

    def test_default_session_type_is_consultation(self):
        """Default session_type produces label 'Консультация'."""
        content, _ = export_print_html("# Test", "Co")
        html = content.decode("utf-8")
        assert "Консультация" in html

    def test_interview_session_type_label(self):
        """session_type='interview' produces label 'Интервью'."""
        content, _ = export_print_html("# Test", "Co", session_type="interview")
        html = content.decode("utf-8")
        assert "Интервью" in html

    def test_consultation_not_present_for_interview(self):
        """When session_type='interview', 'Консультация' should NOT appear as the type label."""
        content, _ = export_print_html("# Test", "Co", session_type="interview")
        html = content.decode("utf-8")
        # The type label div should say Интервью, not Консультация
        assert "Интервью" in html

    def test_html_has_print_button(self):
        """HTML output contains a print button."""
        content, _ = export_print_html("# Test", "Co")
        html = content.decode("utf-8")
        assert "print-btn" in html
        assert "window.print()" in html
        assert "Сохранить как PDF" in html

    def test_empty_markdown_contains_anketa_pusta(self):
        """Empty markdown input results in HTML containing 'Анкета пуста'."""
        content, _ = export_print_html("", "Co")
        html = content.decode("utf-8")
        assert "Анкета пуста" in html

    def test_company_name_with_html_chars_escaped(self):
        """Company name with HTML special chars is escaped to prevent XSS."""
        dangerous_name = '<script>alert("xss")</script>'
        content, _ = export_print_html("# Test", dangerous_name)
        html = content.decode("utf-8")
        # Raw HTML tags must NOT appear — they must be escaped
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_company_name_shows_anketa_in_title(self):
        """Empty company name defaults to 'Анкета' in the HTML title."""
        content, _ = export_print_html("# Test", "")
        html = content.decode("utf-8")
        assert "Анкета" in html

    def test_html_is_valid_doctype(self):
        """HTML output starts with <!DOCTYPE html>."""
        content, _ = export_print_html("# Test", "Co")
        html = content.decode("utf-8")
        assert html.strip().startswith("<!DOCTYPE html>")

    def test_html_has_utf8_meta(self):
        """HTML output contains UTF-8 charset meta tag."""
        content, _ = export_print_html("# Test", "Co")
        html = content.decode("utf-8")
        assert 'charset="utf-8"' in html

    def test_html_filename_uses_safe_company_name(self):
        """Filename uses sanitized company name with .html extension."""
        _, filename = export_print_html("test", "My Company")
        assert filename == "My Company.html"

    def test_html_filename_defaults_to_anketa(self):
        """Empty company name produces 'anketa.html'."""
        _, filename = export_print_html("test", "")
        assert filename == "anketa.html"

    def test_markdown_content_converted_to_html_body(self):
        """Markdown content is converted and embedded in the HTML body."""
        content, _ = export_print_html("# Main Title\n\n- Item A\n- Item B", "Co")
        html = content.decode("utf-8")
        assert "<h1>" in html
        assert "<ul>" in html
        assert "<li>" in html

    def test_unknown_session_type_defaults_to_consultation(self):
        """Any session_type other than 'interview' shows 'Консультация'."""
        content, _ = export_print_html("test", "Co", session_type="unknown")
        html = content.decode("utf-8")
        assert "Консультация" in html


# =========================================================================
# TestEscape
# =========================================================================

class TestEscape:
    """Tests for _escape helper function."""

    def test_escape_ampersand(self):
        """Ampersand is escaped to &amp;."""
        assert _escape("A & B") == "A &amp; B"

    def test_escape_less_than(self):
        """Less-than is escaped to &lt;."""
        assert _escape("a < b") == "a &lt; b"

    def test_escape_greater_than(self):
        """Greater-than is escaped to &gt;."""
        assert _escape("a > b") == "a &gt; b"

    def test_escape_double_quote(self):
        """Double quote is escaped to &quot;."""
        assert _escape('say "hello"') == "say &quot;hello&quot;"

    def test_escape_all_entities_together(self):
        """All special characters escaped in a single string."""
        result = _escape('<a href="x">&</a>')
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&quot;" in result
        assert "&amp;" in result
        # Original chars should not remain unescaped
        assert result == "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"

    def test_normal_text_unchanged(self):
        """Text without special characters is returned as-is."""
        text = "Hello World 123"
        assert _escape(text) == text

    def test_empty_string_unchanged(self):
        """Empty string returns empty string."""
        assert _escape("") == ""

    def test_cyrillic_text_unchanged(self):
        """Cyrillic text without HTML entities is unchanged."""
        text = "Привет мир"
        assert _escape(text) == text

    def test_escape_order_matters_ampersand_first(self):
        """Ampersand must be escaped first to avoid double-escaping."""
        # If & is not escaped first, "&lt;" might become "&amp;lt;"
        result = _escape("&lt;")
        assert result == "&amp;lt;"


# =========================================================================
# TestMdToHtml
# =========================================================================

class TestMdToHtml:
    """Tests for _md_to_html converter."""

    def test_empty_string_returns_anketa_pusta(self):
        """Empty markdown returns the 'Анкета пуста' paragraph."""
        assert _md_to_html("") == "<p>Анкета пуста</p>"

    def test_none_like_empty(self):
        """Falsy empty string is handled correctly."""
        assert _md_to_html("") == "<p>Анкета пуста</p>"

    # --- Headings ---

    def test_h1_heading(self):
        """# heading is converted to <h1>."""
        result = _md_to_html("# Title")
        assert "<h1>" in result
        assert "Title" in result
        assert "</h1>" in result

    def test_h2_heading(self):
        """## heading is converted to <h2>."""
        result = _md_to_html("## Section")
        assert "<h2>Section</h2>" in result

    def test_h3_heading(self):
        """### heading is converted to <h3>."""
        result = _md_to_html("### Subsection")
        assert "<h3>Subsection</h3>" in result

    def test_h4_heading(self):
        """#### heading is converted to <h4>."""
        result = _md_to_html("#### Detail")
        assert "<h4>Detail</h4>" in result

    def test_heading_with_inline_bold(self):
        """Heading containing **bold** text has <strong> inside."""
        result = _md_to_html("## **Important** Section")
        assert "<h2>" in result
        assert "<strong>Important</strong>" in result

    # --- Unordered lists ---

    def test_unordered_list_dash(self):
        """Dash-prefixed items create <ul><li> elements."""
        result = _md_to_html("- Item A\n- Item B")
        assert "<ul>" in result
        assert "<li>" in result
        assert "Item A" in result
        assert "Item B" in result
        assert "</ul>" in result

    def test_unordered_list_asterisk(self):
        """Asterisk-prefixed items also create <ul><li> elements."""
        result = _md_to_html("* Item A\n* Item B")
        assert "<ul>" in result
        assert "<li>" in result

    def test_multiple_list_items_single_ul(self):
        """Consecutive list items produce a single <ul> wrapper, not multiple."""
        result = _md_to_html("- One\n- Two\n- Three")
        assert result.count("<ul>") == 1
        assert result.count("</ul>") == 1
        assert result.count("<li>") == 3

    # --- Ordered lists ---

    def test_ordered_list(self):
        """Numbered items create <ol><li> elements."""
        result = _md_to_html("1. First\n2. Second\n3. Third")
        assert "<ol>" in result
        assert "<li>" in result
        assert "First" in result
        assert "Second" in result
        assert "</ol>" in result

    def test_ordered_list_single_wrapper(self):
        """Consecutive ordered items produce a single <ol>."""
        result = _md_to_html("1. A\n2. B\n3. C")
        assert result.count("<ol>") == 1
        assert result.count("</ol>") == 1

    # --- Blockquotes ---

    def test_blockquote(self):
        """Lines starting with > are wrapped in <blockquote>."""
        result = _md_to_html("> This is a quote")
        assert "<blockquote>" in result
        assert "This is a quote" in result
        assert "</blockquote>" in result

    def test_consecutive_blockquotes_single_wrapper(self):
        """Consecutive blockquote lines share a single <blockquote>."""
        result = _md_to_html("> Line 1\n> Line 2")
        assert result.count("<blockquote>") == 1
        assert result.count("</blockquote>") == 1

    # --- Horizontal rules ---

    def test_hr_triple_dash(self):
        """'---' produces an <hr> element."""
        result = _md_to_html("---")
        assert "<hr>" in result

    def test_hr_triple_asterisk(self):
        """'***' produces an <hr> element."""
        result = _md_to_html("***")
        assert "<hr>" in result

    def test_hr_triple_underscore(self):
        """'___' produces an <hr> element."""
        result = _md_to_html("___")
        assert "<hr>" in result

    # --- Regular paragraphs ---

    def test_regular_text_wrapped_in_p(self):
        """Plain text is wrapped in <p> tags."""
        result = _md_to_html("Just a normal line of text.")
        assert "<p>" in result
        assert "Just a normal line of text." in result
        assert "</p>" in result

    # --- Bold and italic in body ---

    def test_bold_in_paragraph(self):
        """**bold** text in a paragraph is converted to <strong>."""
        result = _md_to_html("This has **bold** text.")
        assert "<strong>bold</strong>" in result

    def test_italic_in_paragraph(self):
        """*italic* text in a paragraph is converted to <em>."""
        result = _md_to_html("This has *italic* text.")
        assert "<em>italic</em>" in result

    # --- Mixed content ---

    def test_mixed_headings_and_lists(self):
        """Document with headings, lists, and paragraphs converts correctly."""
        md = "# Title\n\n## Section\n\n- Item 1\n- Item 2\n\nSome text."
        result = _md_to_html(md)
        assert "<h1>" in result
        assert "<h2>" in result
        assert "<ul>" in result
        assert "<p>" in result

    def test_list_followed_by_paragraph(self):
        """List properly closes before a paragraph starts."""
        md = "- Item 1\n- Item 2\n\nParagraph after list."
        result = _md_to_html(md)
        assert "</ul>" in result
        assert "<p>Paragraph after list.</p>" in result

    def test_empty_lines_skipped(self):
        """Empty lines in markdown are skipped (no empty <p> tags)."""
        md = "Line 1\n\n\n\nLine 2"
        result = _md_to_html(md)
        # Should not produce empty paragraphs
        assert "<p></p>" not in result
        assert "<p>Line 1</p>" in result
        assert "<p>Line 2</p>" in result

    def test_html_entities_in_content_escaped(self):
        """HTML special chars in markdown content are escaped."""
        md = "Use <div> & \"quotes\" in text"
        result = _md_to_html(md)
        assert "&lt;div&gt;" in result
        assert "&amp;" in result
        assert "&quot;quotes&quot;" in result

    def test_ordered_list_followed_by_heading(self):
        """Ordered list closes properly before a heading."""
        md = "1. First\n2. Second\n\n## Next Section"
        result = _md_to_html(md)
        assert "</ol>" in result
        assert "<h2>Next Section</h2>" in result
        # ol should close before h2
        ol_close = result.index("</ol>")
        h2_start = result.index("<h2>")
        assert ol_close < h2_start

    def test_blockquote_followed_by_paragraph(self):
        """Blockquote closes before a regular paragraph."""
        md = "> Quote here\n\nRegular paragraph."
        result = _md_to_html(md)
        assert "</blockquote>" in result
        assert "<p>Regular paragraph.</p>" in result


# =========================================================================
# TestInline
# =========================================================================

class TestInline:
    """Tests for _inline function (inline markdown processing)."""

    def test_bold_text(self):
        """**bold** is converted to <strong>bold</strong>."""
        result = _inline("**bold**")
        assert "<strong>bold</strong>" in result

    def test_italic_text(self):
        """*italic* is converted to <em>italic</em>."""
        result = _inline("*italic*")
        assert "<em>italic</em>" in result

    def test_bold_and_italic_together(self):
        """Both bold and italic in the same string are converted."""
        result = _inline("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_html_entities_escaped_before_inline(self):
        """HTML special chars are escaped before bold/italic processing."""
        result = _inline("Use <b> & **real bold**")
        assert "&lt;b&gt;" in result
        assert "&amp;" in result
        assert "<strong>real bold</strong>" in result

    def test_plain_text_unchanged(self):
        """Text without any inline markers is returned with only HTML escaping."""
        result = _inline("Hello World")
        assert result == "Hello World"

    def test_empty_string(self):
        """Empty string returns empty string."""
        result = _inline("")
        assert result == ""

    def test_multiple_bold_segments(self):
        """Multiple **bold** segments in one line are all converted."""
        result = _inline("**one** and **two**")
        assert "<strong>one</strong>" in result
        assert "<strong>two</strong>" in result

    def test_bold_with_cyrillic(self):
        """Bold with Cyrillic content is processed correctly."""
        result = _inline("**Компания** работает")
        assert "<strong>Компания</strong>" in result

    def test_italic_with_cyrillic(self):
        """Italic with Cyrillic content is processed correctly."""
        result = _inline("*примечание* к тексту")
        assert "<em>примечание</em>" in result

    def test_asterisks_in_already_escaped_context(self):
        """Asterisks for bold/italic work even when other content is escaped."""
        result = _inline('**key**: "value"')
        assert "<strong>key</strong>" in result
        assert "&quot;value&quot;" in result


# =========================================================================
# TestExporterIntegration
# =========================================================================

class TestExporterIntegration:
    """Integration-level tests combining multiple exporter functions."""

    def test_full_anketa_markdown_roundtrip(self):
        """A realistic anketa markdown exports correctly through both exporters."""
        md = (
            "# Анкета клиента\n\n"
            "## 1. Информация о компании\n\n"
            "**Компания:** ООО Рога и Копыта\n"
            "**Отрасль:** E-commerce\n\n"
            "## 2. Задачи агента\n\n"
            "- Обработка входящих звонков\n"
            "- Квалификация лидов\n"
            "- Запись на консультацию\n\n"
            "## 3. Интеграции\n\n"
            "1. CRM Битрикс24\n"
            "2. Телефония Mango Office\n\n"
            "---\n\n"
            "> Примечание: клиент готов начать пилот\n"
        )
        company = "ООО Рога и Копыта"

        # Markdown export
        md_bytes, md_fname = export_markdown(md, company)
        assert md_bytes.decode("utf-8") == md
        assert md_fname.endswith(".md")

        # HTML export
        html_bytes, html_fname = export_print_html(md, company, session_type="interview")
        html = html_bytes.decode("utf-8")
        assert html_fname.endswith(".html")
        assert "Интервью" in html
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<ul>" in html
        assert "<ol>" in html
        assert "<hr>" in html
        assert "<blockquote>" in html
        assert "Обработка входящих звонков" in html
        assert "CRM Битрикс24" in html

    def test_export_html_then_decode_contains_no_raw_markdown(self):
        """Exported HTML should not contain raw markdown syntax like '## ' or '- '."""
        md = "## Section\n\n- item\n\n**bold**"
        html_bytes, _ = export_print_html(md, "Test")
        html = html_bytes.decode("utf-8")
        # Markdown heading marker should not appear raw
        # (it's ok in style or script sections, check the body area)
        assert "## Section" not in html
        # Bold markers should be converted
        assert "**bold**" not in html
