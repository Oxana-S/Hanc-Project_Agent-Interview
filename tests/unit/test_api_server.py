"""
Unit tests for FastAPI web server (src/web/server.py).

Tests all REST API endpoints for session lifecycle, anketa CRUD,
confirmation, and session termination using FastAPI TestClient
with a temporary SQLite-backed SessionManager.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    """Create a TestClient with a temporary SessionManager.

    Replaces the global session_mgr in the server module with one backed
    by a temporary SQLite database so tests are fully isolated and leave
    no artefacts on disk.
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
    """Helper fixture: create a session via POST and return the JSON body."""
    resp = client.post("/api/session/create", json={"pattern": "interaction"})
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/session/create
# ---------------------------------------------------------------------------


class TestCreateSession:
    """Tests for the POST /api/session/create endpoint."""

    def test_create_session_returns_200(self, client):
        resp = client.post("/api/session/create", json={"pattern": "interaction"})
        assert resp.status_code == 200

    def test_create_session_has_required_fields(self, client):
        resp = client.post("/api/session/create", json={"pattern": "interaction"})
        data = resp.json()
        assert "session_id" in data
        assert "unique_link" in data
        assert "room_name" in data
        assert "livekit_url" in data
        assert "user_token" in data

    def test_create_session_ids_are_non_empty(self, client):
        data = client.post("/api/session/create", json={}).json()
        assert len(data["session_id"]) > 0
        assert len(data["unique_link"]) > 0
        assert len(data["room_name"]) > 0

    def test_room_name_contains_session_id(self, client):
        data = client.post("/api/session/create", json={}).json()
        assert data["session_id"] in data["room_name"]

    def test_create_session_default_pattern(self, client):
        """POST without explicit pattern should still succeed (default is 'interaction')."""
        resp = client.post("/api/session/create", json={})
        assert resp.status_code == 200

    def test_create_multiple_sessions_unique_ids(self, client):
        ids = set()
        for _ in range(5):
            data = client.post("/api/session/create", json={}).json()
            ids.add(data["session_id"])
        assert len(ids) == 5, "All session IDs should be unique"


# ---------------------------------------------------------------------------
# GET /api/session/{session_id}
# ---------------------------------------------------------------------------


class TestGetSession:
    """Tests for the GET /api/session/{session_id} endpoint."""

    def test_get_session_valid_id(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}")
        assert resp.status_code == 200

        data = resp.json()
        assert data["session_id"] == sid
        assert data["unique_link"] == created_session["unique_link"]
        assert data["status"] == "active"

    def test_get_session_has_expected_model_fields(self, client, created_session):
        data = client.get(f"/api/session/{created_session['session_id']}").json()
        for field in ("session_id", "room_name", "unique_link", "status",
                      "created_at", "updated_at", "dialogue_history",
                      "anketa_data", "anketa_md", "company_name",
                      "contact_name", "duration_seconds"):
            assert field in data, f"Missing expected field: {field}"

    def test_get_session_invalid_id_returns_404(self, client):
        resp = client.get("/api/session/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/session/by-link/{link}
# ---------------------------------------------------------------------------


class TestGetSessionByLink:
    """Tests for the GET /api/session/by-link/{link} endpoint."""

    def test_get_session_by_link_valid(self, client, created_session):
        link = created_session["unique_link"]
        resp = client.get(f"/api/session/by-link/{link}")
        assert resp.status_code == 200

        data = resp.json()
        assert data["session_id"] == created_session["session_id"]
        assert data["unique_link"] == link

    def test_get_session_by_link_invalid_returns_404(self, client):
        resp = client.get("/api/session/by-link/no-such-link-uuid")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/session/{session_id}/anketa
# ---------------------------------------------------------------------------


class TestGetAnketa:
    """Tests for the GET /api/session/{session_id}/anketa endpoint."""

    def test_get_anketa_returns_200(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.get(f"/api/session/{sid}/anketa")
        assert resp.status_code == 200

    def test_get_anketa_has_required_fields(self, client, created_session):
        sid = created_session["session_id"]
        data = client.get(f"/api/session/{sid}/anketa").json()
        assert "anketa_data" in data
        assert "anketa_md" in data
        assert "status" in data
        assert "company_name" in data
        assert "updated_at" in data

    def test_get_anketa_initial_values(self, client, created_session):
        sid = created_session["session_id"]
        data = client.get(f"/api/session/{sid}/anketa").json()
        assert data["anketa_data"] is None
        assert data["anketa_md"] is None
        assert data["status"] == "active"

    def test_get_anketa_invalid_session_returns_404(self, client):
        resp = client.get("/api/session/does-not-exist/anketa")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/session/{session_id}/anketa
# ---------------------------------------------------------------------------


class TestUpdateAnketa:
    """Tests for the PUT /api/session/{session_id}/anketa endpoint."""

    def test_update_anketa_returns_ok(self, client, created_session):
        sid = created_session["session_id"]
        payload = {
            "anketa_data": {"company_name": "TestCorp", "industry": "IT"},
            "anketa_md": "# TestCorp\nIndustry: IT",
        }
        resp = client.put(f"/api/session/{sid}/anketa", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_update_anketa_persists_data(self, client, created_session):
        sid = created_session["session_id"]
        payload = {
            "anketa_data": {"company_name": "PersistCo", "industry": "Finance"},
            "anketa_md": "# PersistCo\nIndustry: Finance",
        }
        client.put(f"/api/session/{sid}/anketa", json=payload)

        data = client.get(f"/api/session/{sid}/anketa").json()
        assert data["anketa_data"]["company_name"] == "PersistCo"
        assert data["anketa_data"]["industry"] == "Finance"
        assert data["anketa_md"] == "# PersistCo\nIndustry: Finance"

    def test_update_anketa_invalid_session_returns_404(self, client):
        resp = client.put(
            "/api/session/no-such-id/anketa",
            json={"anketa_data": {"key": "val"}},
        )
        assert resp.status_code == 404

    def test_update_anketa_empty_body_still_200(self, client, created_session):
        """PUT with empty body (no anketa_data) should succeed without error."""
        sid = created_session["session_id"]
        resp = client.put(f"/api/session/{sid}/anketa", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/session/{session_id}/confirm
# ---------------------------------------------------------------------------


class TestConfirmSession:
    """Tests for the POST /api/session/{session_id}/confirm endpoint."""

    def test_confirm_session_returns_confirmed(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.post(f"/api/session/{sid}/confirm")
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_confirm_session_updates_status_in_db(self, client, created_session):
        sid = created_session["session_id"]
        client.post(f"/api/session/{sid}/confirm")

        session_data = client.get(f"/api/session/{sid}").json()
        assert session_data["status"] == "confirmed"

    def test_confirm_invalid_session_returns_404(self, client):
        resp = client.post("/api/session/invalid-id/confirm")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/session/{session_id}/end
# ---------------------------------------------------------------------------


class TestEndSession:
    """Tests for the POST /api/session/{session_id}/end endpoint."""

    def test_end_session_returns_paused(self, client, created_session):
        sid = created_session["session_id"]
        resp = client.post(f"/api/session/{sid}/end")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    def test_end_session_has_summary_fields(self, client, created_session):
        sid = created_session["session_id"]
        data = client.post(f"/api/session/{sid}/end").json()
        assert "duration" in data
        assert "message_count" in data
        assert "unique_link" in data

    def test_end_session_unique_link_matches(self, client, created_session):
        sid = created_session["session_id"]
        data = client.post(f"/api/session/{sid}/end").json()
        assert data["unique_link"] == created_session["unique_link"]

    def test_end_session_initial_counts(self, client, created_session):
        """A freshly created session should have 0 duration and 0 messages."""
        sid = created_session["session_id"]
        data = client.post(f"/api/session/{sid}/end").json()
        assert data["duration"] == 0.0
        assert data["message_count"] == 0

    def test_end_session_updates_status_in_db(self, client, created_session):
        sid = created_session["session_id"]
        client.post(f"/api/session/{sid}/end")

        session_data = client.get(f"/api/session/{sid}").json()
        assert session_data["status"] == "paused"

    def test_end_invalid_session_returns_404(self, client):
        resp = client.post("/api/session/no-session/end")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Page routes (GET /, GET /session/{link})
# ---------------------------------------------------------------------------


class TestPageRoutes:
    """Tests for page-serving routes.

    These routes attempt to serve public/index.html via FileResponse.
    Since the public directory may not exist in a test environment,
    we verify the server does not return a 500 (internal server error).
    If public/index.html exists we expect 200; otherwise 404 is acceptable.
    """

    def test_index_does_not_500(self, client):
        resp = client.get("/")
        assert resp.status_code != 500

    def test_session_page_invalid_link_returns_404(self, client):
        resp = client.get("/session/nonexistent-link")
        assert resp.status_code == 404

    def test_session_page_valid_link_does_not_500(self, client, created_session):
        link = created_session["unique_link"]
        resp = client.get(f"/session/{link}")
        # Either 200 (public/index.html exists) or non-500 error
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# Full lifecycle flow
# ---------------------------------------------------------------------------


class TestFullLifecycleFlow:
    """End-to-end test covering: create -> update anketa -> confirm -> verify."""

    def test_full_flow(self, client):
        # 1. Create session
        create_resp = client.post("/api/session/create", json={"pattern": "interaction"})
        assert create_resp.status_code == 200
        session = create_resp.json()
        sid = session["session_id"]
        link = session["unique_link"]

        # 2. Verify session exists via ID and link
        assert client.get(f"/api/session/{sid}").status_code == 200
        assert client.get(f"/api/session/by-link/{link}").status_code == 200

        # 3. Anketa is initially empty
        anketa = client.get(f"/api/session/{sid}/anketa").json()
        assert anketa["anketa_data"] is None
        assert anketa["status"] == "active"

        # 4. Update anketa with data
        anketa_payload = {
            "anketa_data": {
                "company_name": "FlowCorp",
                "industry": "Logistics",
                "contact_person": "Ivan Ivanov",
                "contact_email": "ivan@flowcorp.ru",
            },
            "anketa_md": "# FlowCorp\n\nIndustry: Logistics\nContact: Ivan Ivanov",
        }
        put_resp = client.put(f"/api/session/{sid}/anketa", json=anketa_payload)
        assert put_resp.status_code == 200
        assert put_resp.json()["status"] == "ok"

        # 5. Verify anketa data was persisted
        anketa_after = client.get(f"/api/session/{sid}/anketa").json()
        assert anketa_after["anketa_data"]["company_name"] == "FlowCorp"
        assert anketa_after["anketa_data"]["industry"] == "Logistics"
        assert anketa_after["anketa_md"] is not None
        assert "FlowCorp" in anketa_after["anketa_md"]

        # 6. Confirm the session
        confirm_resp = client.post(f"/api/session/{sid}/confirm")
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["status"] == "confirmed"

        # 7. Verify final state: status is confirmed, anketa data is intact
        final_session = client.get(f"/api/session/{sid}").json()
        assert final_session["status"] == "confirmed"
        assert final_session["anketa_data"]["company_name"] == "FlowCorp"

        final_anketa = client.get(f"/api/session/{sid}/anketa").json()
        assert final_anketa["status"] == "confirmed"
        assert final_anketa["anketa_data"]["contact_email"] == "ivan@flowcorp.ru"

    def test_create_update_end_flow(self, client):
        """Variant flow: create -> update anketa -> end (pause) session."""
        # Create
        session = client.post("/api/session/create", json={}).json()
        sid = session["session_id"]

        # Update anketa
        client.put(
            f"/api/session/{sid}/anketa",
            json={"anketa_data": {"company_name": "EndCo"}, "anketa_md": "# EndCo"},
        )

        # End session
        end_resp = client.post(f"/api/session/{sid}/end")
        assert end_resp.status_code == 200
        data = end_resp.json()
        assert data["status"] == "paused"
        assert data["unique_link"] == session["unique_link"]

        # Session should now be paused but still retrievable
        final = client.get(f"/api/session/{sid}").json()
        assert final["status"] == "paused"
        assert final["anketa_data"]["company_name"] == "EndCo"

        # Session should also be retrievable by link
        by_link = client.get(f"/api/session/by-link/{session['unique_link']}").json()
        assert by_link["status"] == "paused"
