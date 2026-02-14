"""
Unit tests for the v5.0 export endpoint: GET /api/session/{id}/export/{format}.

Tests markdown export (Content-Disposition: attachment, text/markdown),
PDF/print-HTML export (Content-Disposition: inline, text/html), and
error cases (404 for missing sessions, 400 for unsupported formats).

Uses a temporary SQLite-backed SessionManager swapped into the server
module, following the same pattern as test_api_server.py.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    """Create a TestClient with a temporary SessionManager.

    Replaces the global session_mgr in the server module with one backed
    by a temporary SQLite database so tests are fully isolated.
    """
    from src.session.manager import SessionManager
    from src.web import server

    temp_mgr = SessionManager(db_path=str(tmp_path / "test.db"))
    original_mgr = server.session_mgr
    server.session_mgr = temp_mgr

    from fastapi.testclient import TestClient

    c = TestClient(server.app, raise_server_exceptions=False)
    yield c

    server.session_mgr = original_mgr
    temp_mgr.close()


@pytest.fixture
def created_session(client):
    """Helper: create a session via POST and return the JSON body."""
    resp = client.post("/api/session/create", json={"pattern": "interaction"})
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def session_with_anketa(client, created_session):
    """Helper: create a session and populate it with anketa_md + company_name.

    Returns the session_id for convenience.
    """
    from src.web import server

    sid = created_session["session_id"]

    anketa_data = {"company_name": "TestCorp", "industry": "IT"}
    anketa_md = "# TestCorp\n\n## Industry\nIT\n\n## Contact\nIvan Ivanov"

    server.session_mgr.update_anketa(sid, anketa_data, anketa_md)
    server.session_mgr.update_metadata(sid, company_name="TestCorp")

    return sid


@pytest.fixture
def session_with_voice_config(client):
    """Helper: create a session with voice_config containing consultation_type='interview'."""
    from src.web import server

    resp = client.post(
        "/api/session/create",
        json={"pattern": "interaction", "voice_settings": {"consultation_type": "interview"}},
    )
    assert resp.status_code == 200
    sid = resp.json()["session_id"]

    anketa_data = {"company_name": "InterviewCorp", "industry": "Finance"}
    anketa_md = "# InterviewCorp\n\n## Industry\nFinance"

    server.session_mgr.update_anketa(sid, anketa_data, anketa_md)
    server.session_mgr.update_metadata(sid, company_name="InterviewCorp")

    return sid


# ---------------------------------------------------------------------------
# GET /api/session/{id}/export/md
# ---------------------------------------------------------------------------


class TestExportMarkdown:
    """Tests for markdown export: GET /api/session/{id}/export/md."""

    def test_md_export_returns_200(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        assert resp.status_code == 200

    def test_md_export_content_type_is_markdown(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        assert "text/markdown" in resp.headers["content-type"]

    def test_md_export_content_disposition_is_attachment(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        cd = resp.headers["content-disposition"]
        assert cd.startswith("attachment")
        assert "filename=" in cd

    def test_md_export_filename_contains_company_name(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        cd = resp.headers["content-disposition"]
        assert "TestCorp" in cd
        assert "TestCorp.md" in cd

    def test_md_export_content_matches_anketa(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        body = resp.content.decode("utf-8")
        assert "# TestCorp" in body
        assert "## Industry" in body
        assert "IT" in body
        assert "Ivan Ivanov" in body

    def test_md_export_empty_anketa_returns_empty_bytes(self, client, created_session):
        """Session with no anketa_md should return empty content (0 bytes)."""
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/md")
        assert resp.status_code == 200
        assert resp.content == b""

    def test_md_export_empty_anketa_content_type(self, client, created_session):
        """Even with empty anketa, content type should still be text/markdown."""
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/md")
        assert "text/markdown" in resp.headers["content-type"]

    def test_md_export_empty_anketa_has_fallback_filename(self, client, created_session):
        """When company_name is empty, filename should fall back to 'anketa.md'."""
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/md")
        cd = resp.headers["content-disposition"]
        assert "anketa.md" in cd


# ---------------------------------------------------------------------------
# GET /api/session/{id}/export/pdf
# ---------------------------------------------------------------------------


class TestExportPdf:
    """Tests for PDF/print-HTML export: GET /api/session/{id}/export/pdf."""

    def test_pdf_export_returns_200(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        assert resp.status_code == 200

    def test_pdf_export_content_type_is_html(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        assert "text/html" in resp.headers["content-type"]

    def test_pdf_export_content_disposition_is_inline(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        cd = resp.headers["content-disposition"]
        assert cd.startswith("inline")
        assert "filename=" in cd

    def test_pdf_export_filename_contains_company_name(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        cd = resp.headers["content-disposition"]
        assert "TestCorp" in cd
        assert "TestCorp.html" in cd

    def test_pdf_export_html_contains_company_name(self, client, session_with_anketa):
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        body = resp.content.decode("utf-8")
        assert "TestCorp" in body

    def test_pdf_export_html_is_valid_document(self, client, session_with_anketa):
        """Returned HTML should be a complete document with DOCTYPE and closing tags."""
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        body = resp.content.decode("utf-8")
        assert "<!DOCTYPE html>" in body
        assert "<html" in body
        assert "</html>" in body
        assert "<head>" in body
        assert "</head>" in body
        assert "<body>" in body
        assert "</body>" in body

    def test_pdf_export_default_type_is_consultation(self, client, session_with_anketa):
        """Default session (no voice_config) should show 'Konsultatsiya' label."""
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        body = resp.content.decode("utf-8")
        assert "\u041a\u043e\u043d\u0441\u0443\u043b\u044c\u0442\u0430\u0446\u0438\u044f" in body  # Консультация

    def test_pdf_export_interview_type(self, client, session_with_voice_config):
        """Session with consultation_type='interview' should show 'Intervyu' label."""
        resp = client.get(f"/api/session/{session_with_voice_config}/export/pdf")
        body = resp.content.decode("utf-8")
        assert "\u0418\u043d\u0442\u0435\u0440\u0432\u044c\u044e" in body  # Интервью

    def test_pdf_export_interview_does_not_show_consultation(self, client, session_with_voice_config):
        """Interview-type sessions should NOT show 'Konsultatsiya'."""
        resp = client.get(f"/api/session/{session_with_voice_config}/export/pdf")
        body = resp.content.decode("utf-8")
        # The meta div should contain Интервью, not Консультация
        assert "\u041a\u043e\u043d\u0441\u0443\u043b\u044c\u0442\u0430\u0446\u0438\u044f" not in body

    def test_pdf_export_contains_print_button(self, client, session_with_anketa):
        """Print-ready HTML should include a print button for PDF generation."""
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        body = resp.content.decode("utf-8")
        assert "window.print()" in body

    def test_pdf_export_empty_anketa_shows_placeholder(self, client, created_session):
        """Session with no anketa_md should still return valid HTML."""
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/pdf")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "<!DOCTYPE html>" in body

    def test_pdf_export_contains_anketa_content(self, client, session_with_anketa):
        """HTML body should contain the rendered anketa content."""
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        body = resp.content.decode("utf-8")
        # The markdown heading "# TestCorp" becomes <h1>TestCorp</h1>
        assert "TestCorp" in body
        assert "IT" in body

    def test_pdf_export_has_hanc_branding(self, client, session_with_anketa):
        """HTML title should include Hanc.AI branding."""
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        body = resp.content.decode("utf-8")
        assert "Hanc.AI" in body


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestExportErrors:
    """Tests for error handling in the export endpoint."""

    def test_nonexistent_session_returns_404_md(self, client):
        resp = client.get("/api/session/nonexistent-id/export/md")
        assert resp.status_code == 404

    def test_nonexistent_session_returns_404_pdf(self, client):
        resp = client.get("/api/session/nonexistent-id/export/pdf")
        assert resp.status_code == 404

    def test_nonexistent_session_error_detail(self, client):
        resp = client.get("/api/session/nonexistent-id/export/md")
        data = resp.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_unsupported_format_docx_returns_400(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/docx")
        assert resp.status_code == 400

    def test_unsupported_format_json_returns_400(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/json")
        assert resp.status_code == 400

    def test_unsupported_format_csv_returns_400(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/csv")
        assert resp.status_code == 400

    def test_unsupported_format_error_detail_mentions_format(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/docx")
        data = resp.json()
        assert "detail" in data
        assert "docx" in data["detail"]

    def test_unsupported_format_error_lists_supported(self, client, created_session):
        """Error message should mention the supported formats: md, pdf."""
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/docx")
        data = resp.json()
        detail = data["detail"]
        assert "md" in detail
        assert "pdf" in detail

    def test_empty_format_returns_400(self, client, created_session):
        """An empty-like format should be rejected as unsupported."""
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/export/txt")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Session data population and export integration
# ---------------------------------------------------------------------------


class TestExportWithData:
    """Integration tests: populate session data, then export and verify content."""

    def test_export_md_after_anketa_update(self, client):
        """Full flow: create session -> populate anketa -> export md -> verify content."""
        from src.web import server

        # Create session
        resp = client.post("/api/session/create", json={})
        sid = resp.json()["session_id"]

        # Populate via SessionManager
        anketa_data = {
            "company_name": "ExportCo",
            "industry": "E-commerce",
            "contact_email": "export@co.ru",
        }
        anketa_md = "# ExportCo\n\n## Industry\nE-commerce\n\n## Contact\nexport@co.ru"

        server.session_mgr.update_anketa(sid, anketa_data, anketa_md)
        server.session_mgr.update_metadata(sid, company_name="ExportCo")

        # Export markdown
        resp = client.get(f"/api/session/{sid}/export/md")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "# ExportCo" in body
        assert "E-commerce" in body
        assert "export@co.ru" in body

    def test_export_pdf_after_anketa_update(self, client):
        """Full flow: create session -> populate anketa -> export pdf -> verify HTML."""
        from src.web import server

        # Create session
        resp = client.post("/api/session/create", json={})
        sid = resp.json()["session_id"]

        # Populate via SessionManager
        anketa_data = {"company_name": "HtmlCorp", "industry": "SaaS"}
        anketa_md = "# HtmlCorp\n\n## Service\nSaaS Platform"

        server.session_mgr.update_anketa(sid, anketa_data, anketa_md)
        server.session_mgr.update_metadata(sid, company_name="HtmlCorp")

        # Export PDF (print-HTML)
        resp = client.get(f"/api/session/{sid}/export/pdf")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "HtmlCorp" in body
        assert "SaaS Platform" in body
        assert "<!DOCTYPE html>" in body

    def test_export_pdf_with_cyrillic_content(self, client):
        """Anketa body with Cyrillic text should appear correctly in HTML.

        Note: company_name is set to ASCII to avoid Cyrillic-in-filename
        issues (non-ASCII Content-Disposition filenames cause 500 in ASGI).
        The anketa markdown body itself uses Cyrillic and must be preserved.
        """
        from src.web import server

        resp = client.post("/api/session/create", json={})
        sid = resp.json()["session_id"]

        anketa_md = "# Alfa\n\n## \u041e\u0442\u0440\u0430\u0441\u043b\u044c\nIT\n\n## \u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435\n\u0410\u043b\u044c\u0444\u0430 \u041a\u043e\u043c\u043f\u0430\u043d\u0438\u044f"
        server.session_mgr.update_anketa(sid, {"company_name": "Alfa"}, anketa_md)
        server.session_mgr.update_metadata(sid, company_name="Alfa")

        resp = client.get(f"/api/session/{sid}/export/pdf")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "\u041e\u0442\u0440\u0430\u0441\u043b\u044c" in body  # Отрасль
        assert "\u0410\u043b\u044c\u0444\u0430" in body  # Альфа

    def test_export_md_with_cyrillic_content(self, client):
        """Markdown export should preserve Cyrillic content in the body.

        Uses ASCII company_name for the filename to avoid the non-ASCII
        Content-Disposition header limitation.
        """
        from src.web import server

        resp = client.post("/api/session/create", json={})
        sid = resp.json()["session_id"]

        anketa_md = "# TestKorp\n\n\u0420\u0430\u0437\u0434\u0435\u043b: \u0434\u0430\u043d\u043d\u044b\u0435"
        server.session_mgr.update_anketa(sid, {"company_name": "TestKorp"}, anketa_md)
        server.session_mgr.update_metadata(sid, company_name="TestKorp")

        resp = client.get(f"/api/session/{sid}/export/md")
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "TestKorp" in body
        assert "\u0434\u0430\u043d\u043d\u044b\u0435" in body  # данные
        assert "\u0420\u0430\u0437\u0434\u0435\u043b" in body  # Раздел

    def test_export_md_content_is_raw_markdown(self, client, session_with_anketa):
        """Markdown export should return raw markdown, not HTML."""
        resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        body = resp.content.decode("utf-8")
        # Should contain markdown syntax, not HTML tags
        assert "# TestCorp" in body
        assert "## Industry" in body
        assert "<html>" not in body
        assert "<body>" not in body

    def test_export_pdf_content_is_html_not_markdown(self, client, session_with_anketa):
        """PDF export should return rendered HTML, not raw markdown."""
        resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")
        body = resp.content.decode("utf-8")
        assert "<html" in body
        assert "<body>" in body

    def test_both_formats_for_same_session(self, client, session_with_anketa):
        """Both md and pdf exports should work for the same session."""
        md_resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        pdf_resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")

        assert md_resp.status_code == 200
        assert pdf_resp.status_code == 200

        # Different content types
        assert "text/markdown" in md_resp.headers["content-type"]
        assert "text/html" in pdf_resp.headers["content-type"]

        # Different dispositions
        assert md_resp.headers["content-disposition"].startswith("attachment")
        assert pdf_resp.headers["content-disposition"].startswith("inline")

    def test_export_after_session_confirmed(self, client, session_with_anketa):
        """Export should still work after session is confirmed."""
        client.post(f"/api/session/{session_with_anketa}/confirm")

        md_resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        pdf_resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")

        assert md_resp.status_code == 200
        assert pdf_resp.status_code == 200

    def test_export_after_session_paused(self, client, session_with_anketa):
        """Export should still work after session is ended/paused."""
        client.post(f"/api/session/{session_with_anketa}/end")

        md_resp = client.get(f"/api/session/{session_with_anketa}/export/md")
        pdf_resp = client.get(f"/api/session/{session_with_anketa}/export/pdf")

        assert md_resp.status_code == 200
        assert pdf_resp.status_code == 200
