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

    def test_get_session_invalid_format_returns_400(self, client):
        resp = client.get("/api/session/nonexistent-id")
        assert resp.status_code == 400

    def test_get_session_nonexistent_returns_404(self, client):
        resp = client.get("/api/session/deadbeef")
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

    def test_get_session_by_link_invalid_format_returns_400(self, client):
        """R9-01: Invalid UUID format → 400."""
        resp = client.get("/api/session/by-link/no-such-link-uuid")
        assert resp.status_code == 400

    def test_get_session_by_link_nonexistent_returns_404(self, client):
        """Valid UUID format but nonexistent → 404."""
        resp = client.get("/api/session/by-link/deadbeef-dead-beef-dead-beefdeadbeef")
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

    def test_get_anketa_invalid_format_returns_400(self, client):
        resp = client.get("/api/session/does-not-exist/anketa")
        assert resp.status_code == 400

    def test_get_anketa_nonexistent_returns_404(self, client):
        resp = client.get("/api/session/deadbeef/anketa")
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

    def test_update_anketa_invalid_format_returns_400(self, client):
        resp = client.put(
            "/api/session/no-such-id/anketa",
            json={"anketa_data": {"key": "val"}},
        )
        assert resp.status_code == 400

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

    def test_confirm_invalid_format_returns_400(self, client):
        resp = client.post("/api/session/invalid-id/confirm")
        assert resp.status_code == 400

    def test_confirm_nonexistent_session_returns_404(self, client):
        resp = client.post("/api/session/deadbeef/confirm")
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

    def test_end_invalid_format_returns_400(self, client):
        resp = client.post("/api/session/no-session/end")
        assert resp.status_code == 400

    def test_end_nonexistent_session_returns_404(self, client):
        resp = client.post("/api/session/deadbeef/end")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/sessions (Dashboard)
# ---------------------------------------------------------------------------


class TestListSessions:
    """Tests for the GET /api/sessions dashboard endpoint."""

    def test_returns_200_empty(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions"] == []
        assert data["total"] == 0

    def test_returns_created_sessions(self, client, created_session):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["sessions"][0]["session_id"] == created_session["session_id"]

    def test_summary_has_expected_fields(self, client, created_session):
        sessions = client.get("/api/sessions").json()["sessions"]
        s = sessions[0]
        for field in ("session_id", "unique_link", "status", "created_at",
                      "updated_at", "company_name", "contact_name",
                      "duration_seconds", "room_name"):
            assert field in s, f"Missing field: {field}"

    def test_summary_excludes_heavy_fields(self, client, created_session):
        """Dashboard summaries must NOT contain dialogue_history or anketa_data."""
        sid = created_session["session_id"]
        client.put(
            f"/api/session/{sid}/anketa",
            json={"anketa_data": {"company_name": "Test"}},
        )
        sessions = client.get("/api/sessions").json()["sessions"]
        s = sessions[0]
        assert "dialogue_history" not in s
        assert "anketa_data" not in s
        assert "anketa_md" not in s

    def test_filter_by_status(self, client):
        s1 = client.post("/api/session/create", json={}).json()
        s2 = client.post("/api/session/create", json={}).json()
        # End s1 -> paused
        client.post(f"/api/session/{s1['session_id']}/end")

        active = client.get("/api/sessions?status=active").json()
        assert active["total"] == 1
        assert active["sessions"][0]["session_id"] == s2["session_id"]

        paused = client.get("/api/sessions?status=paused").json()
        assert paused["total"] == 1
        assert paused["sessions"][0]["session_id"] == s1["session_id"]

    def test_filter_no_matches(self, client, created_session):
        resp = client.get("/api/sessions?status=confirmed")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_limit_parameter(self, client):
        for _ in range(3):
            client.post("/api/session/create", json={})
        resp = client.get("/api/sessions?limit=2")
        data = resp.json()
        assert len(data["sessions"]) == 2  # page size limited
        assert data["total"] == 3  # total count is full (for pagination)

    def test_multiple_sessions_ordered_newest_first(self, client):
        s1 = client.post("/api/session/create", json={}).json()
        client.post("/api/session/create", json={})
        s3 = client.post("/api/session/create", json={}).json()

        sessions = client.get("/api/sessions").json()["sessions"]
        assert len(sessions) == 3
        # Newest first
        assert sessions[0]["session_id"] == s3["session_id"]
        assert sessions[2]["session_id"] == s1["session_id"]


# ---------------------------------------------------------------------------
# Page routes (GET /, GET /session/{link}, GET /session/{link}/review)
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

    def test_session_page_invalid_format_returns_400(self, client):
        """R9-01: Invalid UUID format → 400."""
        resp = client.get("/session/nonexistent-link")
        assert resp.status_code == 400

    def test_session_page_nonexistent_returns_404(self, client):
        """Valid UUID format but nonexistent → 404."""
        resp = client.get("/session/deadbeef-dead-beef-dead-beefdeadbeef")
        assert resp.status_code == 404

    def test_session_page_valid_link_does_not_500(self, client, created_session):
        link = created_session["unique_link"]
        resp = client.get(f"/session/{link}")
        # Either 200 (public/index.html exists) or non-500 error
        assert resp.status_code != 500

    def test_review_page_invalid_format_returns_400(self, client):
        """R9-01: Invalid UUID format → 400."""
        resp = client.get("/session/nonexistent-link/review")
        assert resp.status_code == 400

    def test_review_page_nonexistent_returns_404(self, client):
        """Valid UUID format but nonexistent → 404."""
        resp = client.get("/session/deadbeef-dead-beef-dead-beefdeadbeef/review")
        assert resp.status_code == 404

    def test_review_page_valid_link_does_not_500(self, client, created_session):
        link = created_session["unique_link"]
        resp = client.get(f"/session/{link}/review")
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# POST /api/sessions/delete (Bulk delete)
# ---------------------------------------------------------------------------


class TestDeleteSessions:
    """Tests for the POST /api/sessions/delete endpoint."""

    def test_delete_sessions_returns_count(self, client):
        s1 = client.post("/api/session/create", json={}).json()
        s2 = client.post("/api/session/create", json={}).json()
        resp = client.post(
            "/api/sessions/delete",
            json={"session_ids": [s1["session_id"], s2["session_id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    def test_delete_empty_returns_zero(self, client):
        resp = client.post("/api/sessions/delete", json={"session_ids": []})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0

    def test_deleted_not_in_dashboard(self, client):
        s1 = client.post("/api/session/create", json={}).json()
        s2 = client.post("/api/session/create", json={}).json()

        # Delete s1
        client.post("/api/sessions/delete", json={"session_ids": [s1["session_id"]]})

        # Dashboard should only have s2
        dashboard = client.get("/api/sessions").json()
        assert dashboard["total"] == 1
        assert dashboard["sessions"][0]["session_id"] == s2["session_id"]

    def test_delete_invalid_format_returns_400(self, client):
        """R9-02: Invalid session_id format in body → 400."""
        resp = client.post(
            "/api/sessions/delete",
            json={"session_ids": ["nonexistent-id"]},
        )
        assert resp.status_code == 400

    def test_delete_nonexistent_returns_zero(self, client):
        """Valid format but nonexistent → 200 with deleted=0."""
        resp = client.post(
            "/api/sessions/delete",
            json={"session_ids": ["deadbeef"]},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0


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

    def test_dashboard_lifecycle_flow(self, client):
        """Dashboard flow: empty list -> create sessions -> filter -> review data.

        Simulates the web UI lifecycle:
        1. Dashboard shows empty state
        2. Create two sessions, fill anketa in one
        3. End one session (paused)
        4. Dashboard lists both, filter works
        5. Session data accessible via by-link for review screen
        """
        # 1. Dashboard is empty
        empty = client.get("/api/sessions").json()
        assert empty["total"] == 0

        # 2. Create two sessions
        s1 = client.post("/api/session/create", json={}).json()
        s2 = client.post("/api/session/create", json={}).json()

        # 3. Fill anketa in s1
        client.put(
            f"/api/session/{s1['session_id']}/anketa",
            json={"anketa_data": {"company_name": "Альфа", "industry": "IT"}},
        )

        # 4. Dashboard shows 2 active sessions
        dashboard = client.get("/api/sessions").json()
        assert dashboard["total"] == 2

        active_only = client.get("/api/sessions?status=active").json()
        assert active_only["total"] == 2

        # 5. End s1 -> paused
        client.post(f"/api/session/{s1['session_id']}/end")

        # 6. Filter: 1 active, 1 paused
        active = client.get("/api/sessions?status=active").json()
        assert active["total"] == 1
        assert active["sessions"][0]["session_id"] == s2["session_id"]

        paused = client.get("/api/sessions?status=paused").json()
        assert paused["total"] == 1
        assert paused["sessions"][0]["session_id"] == s1["session_id"]

        # 7. Review: session data accessible via by-link
        review = client.get(f"/api/session/by-link/{s1['unique_link']}").json()
        assert review["status"] == "paused"
        assert review["anketa_data"]["company_name"] == "Альфа"
        assert "dialogue_history" in review  # Full data for review screen

        # 8. Confirm s1 -> confirmed
        client.post(f"/api/session/{s1['session_id']}/confirm")

        confirmed = client.get("/api/sessions?status=confirmed").json()
        assert confirmed["total"] == 1
        assert confirmed["sessions"][0]["session_id"] == s1["session_id"]


# ===================================================================
# LLM Providers endpoint
# ===================================================================

class TestLLMProvidersEndpoint:
    """Tests for GET /api/llm/providers."""

    def test_returns_200(self, client):
        """Endpoint returns 200 OK."""
        resp = client.get("/api/llm/providers")
        assert resp.status_code == 200

    def test_response_structure(self, client):
        """Response has 'providers' list and 'default' string."""
        data = client.get("/api/llm/providers").json()
        assert "providers" in data
        assert "default" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) == 5

    def test_each_provider_has_required_fields(self, client):
        """Each provider entry has id, name, available."""
        data = client.get("/api/llm/providers").json()
        for p in data["providers"]:
            assert "id" in p
            assert "name" in p
            assert "available" in p
