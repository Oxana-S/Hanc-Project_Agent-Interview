"""
Unit tests for SessionManager - SQLite-based session storage.

Tests CRUD operations, JSON round-trip for complex fields,
status validation, and session lifecycle.
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from src.session.manager import SessionManager
from src.session.models import ConsultationSession, VALID_STATUSES


@pytest.fixture
def manager(tmp_path):
    """Create a SessionManager backed by a temporary SQLite database."""
    db_path = str(tmp_path / "test_sessions.db")
    mgr = SessionManager(db_path=db_path)
    yield mgr
    mgr.close()


class TestCreateSession:
    """Test session creation."""

    def test_create_session_defaults(self, manager):
        """create_session returns a ConsultationSession with correct default fields."""
        session = manager.create_session()

        assert isinstance(session, ConsultationSession)
        assert len(session.session_id) == 8
        # unique_link must be a valid UUID (36 chars with hyphens)
        parsed = uuid.UUID(session.unique_link)
        assert str(parsed) == session.unique_link
        assert session.status == "active"
        assert session.dialogue_history == []
        assert session.room_name == ""
        assert session.anketa_data is None
        assert session.anketa_md is None
        assert session.company_name is None
        assert session.contact_name is None
        assert session.duration_seconds == 0.0
        assert session.output_dir is None
        assert session.created_at is not None
        assert session.updated_at is not None

    def test_create_session_with_room_name(self, manager):
        """create_session accepts a room_name and persists it."""
        session = manager.create_session(room_name="livekit-room-42")

        assert session.room_name == "livekit-room-42"

        # Verify persistence
        loaded = manager.get_session(session.session_id)
        assert loaded is not None
        assert loaded.room_name == "livekit-room-42"


class TestGetSession:
    """Test retrieving sessions by session_id."""

    def test_get_existing_session(self, manager):
        """get_session returns the correct session for a valid session_id."""
        created = manager.create_session(room_name="room-get")
        loaded = manager.get_session(created.session_id)

        assert loaded is not None
        assert loaded.session_id == created.session_id
        assert loaded.unique_link == created.unique_link
        assert loaded.room_name == "room-get"
        assert loaded.status == "active"

    def test_get_non_existing_session(self, manager):
        """get_session returns None for a session_id that does not exist."""
        result = manager.get_session("nonexist")
        assert result is None


class TestGetSessionByLink:
    """Test retrieving sessions by unique_link."""

    def test_get_existing_session_by_link(self, manager):
        """get_session_by_link returns the correct session for a valid unique_link."""
        created = manager.create_session()
        loaded = manager.get_session_by_link(created.unique_link)

        assert loaded is not None
        assert loaded.session_id == created.session_id
        assert loaded.unique_link == created.unique_link

    def test_get_non_existing_session_by_link(self, manager):
        """get_session_by_link returns None for a link that does not exist."""
        result = manager.get_session_by_link("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestUpdateSession:
    """Test full session update."""

    def test_update_session_persists_changes(self, manager):
        """update_session modifies fields and persists them to the database."""
        session = manager.create_session(room_name="original-room")

        # Mutate fields
        session.room_name = "updated-room"
        session.company_name = "TestCorp"
        session.contact_name = "Ivan Petrov"
        session.duration_seconds = 123.45
        session.output_dir = "/tmp/output"
        session.dialogue_history = [{"role": "agent", "content": "Hello"}]

        result = manager.update_session(session)
        assert result is True

        # Reload and verify
        loaded = manager.get_session(session.session_id)
        assert loaded.room_name == "updated-room"
        assert loaded.company_name == "TestCorp"
        assert loaded.contact_name == "Ivan Petrov"
        assert loaded.duration_seconds == 123.45
        assert loaded.output_dir == "/tmp/output"
        assert loaded.dialogue_history == [{"role": "agent", "content": "Hello"}]

    def test_update_session_returns_false_for_nonexistent(self, manager):
        """update_session returns False when session_id does not exist in the database."""
        fake_session = ConsultationSession(
            session_id="fakeid00",
            unique_link=str(uuid.uuid4()),
            status="active",
        )
        result = manager.update_session(fake_session)
        assert result is False


class TestUpdateAnketa:
    """Test anketa-specific update."""

    def test_update_anketa_data_and_md(self, manager):
        """update_anketa sets anketa_data and anketa_md, persisted correctly."""
        session = manager.create_session()

        anketa = {
            "company_name": "TestCorp",
            "industry": "IT",
            "services": ["consulting", "development"],
        }
        anketa_md = "# TestCorp\n\n- Industry: IT"

        result = manager.update_anketa(session.session_id, anketa, anketa_md=anketa_md)
        assert result is True

        loaded = manager.get_session(session.session_id)
        assert loaded.anketa_data == anketa
        assert loaded.anketa_md == anketa_md

    def test_update_anketa_without_md(self, manager):
        """update_anketa works when anketa_md is not provided."""
        session = manager.create_session()
        anketa = {"key": "value"}

        result = manager.update_anketa(session.session_id, anketa)
        assert result is True

        loaded = manager.get_session(session.session_id)
        assert loaded.anketa_data == anketa
        assert loaded.anketa_md is None

    def test_update_anketa_nonexistent_session(self, manager):
        """update_anketa returns False for a non-existent session_id."""
        result = manager.update_anketa("noexist1", {"key": "value"})
        assert result is False


class TestUpdateStatus:
    """Test status update and validation."""

    def test_valid_status_transitions(self, manager):
        """update_status allows transitions through valid statuses."""
        session = manager.create_session()
        sid = session.session_id

        # active -> reviewing
        assert manager.update_status(sid, "reviewing") is True
        assert manager.get_session(sid).status == "reviewing"

        # reviewing -> confirmed
        assert manager.update_status(sid, "confirmed") is True
        assert manager.get_session(sid).status == "confirmed"

    def test_valid_status_transitions_via_pause(self, manager):
        """Paused session can be confirmed directly."""
        session = manager.create_session()
        sid = session.session_id

        # active -> paused
        assert manager.update_status(sid, "paused") is True
        assert manager.get_session(sid).status == "paused"

        # paused -> confirmed
        assert manager.update_status(sid, "confirmed") is True
        assert manager.get_session(sid).status == "confirmed"

    def test_all_valid_statuses_accepted(self, manager):
        """Each status in VALID_STATUSES can be reached via valid transitions."""
        # R12: Test each status via valid transition path
        transition_paths = {
            "active": [],  # already active
            "paused": ["paused"],
            "reviewing": ["reviewing"],
            "confirmed": ["reviewing", "confirmed"],
            "declined": ["declined"],
        }
        for status, path in transition_paths.items():
            session = manager.create_session()
            for step in path:
                result = manager.update_status(session.session_id, step)
                assert result is True
            loaded = manager.get_session(session.session_id)
            assert loaded.status == status

    def test_invalid_status_raises_value_error(self, manager):
        """update_status raises ValueError for an invalid status string."""
        session = manager.create_session()

        with pytest.raises(ValueError, match="Invalid status"):
            manager.update_status(session.session_id, "invalid_status")

    def test_invalid_status_empty_string(self, manager):
        """update_status raises ValueError for an empty string."""
        session = manager.create_session()

        with pytest.raises(ValueError):
            manager.update_status(session.session_id, "")

    def test_update_status_nonexistent_session(self, manager):
        """update_status returns False for a non-existent session_id."""
        result = manager.update_status("noexist1", "paused")
        assert result is False


class TestListSessions:
    """Test listing sessions with and without filters."""

    def test_list_sessions_no_filter(self, manager):
        """list_sessions returns all sessions when no status filter is provided."""
        manager.create_session(room_name="room-a")
        manager.create_session(room_name="room-b")
        manager.create_session(room_name="room-c")

        sessions = manager.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_empty(self, manager):
        """list_sessions returns an empty list when no sessions exist."""
        sessions = manager.list_sessions()
        assert sessions == []

    def test_list_sessions_with_status_filter(self, manager):
        """list_sessions filters correctly by status."""
        s1 = manager.create_session()
        s2 = manager.create_session()
        s3 = manager.create_session()

        manager.update_status(s1.session_id, "paused")
        manager.update_status(s2.session_id, "paused")
        # s3 remains active

        paused = manager.list_sessions(status="paused")
        assert len(paused) == 2
        assert all(s.status == "paused" for s in paused)

        active = manager.list_sessions(status="active")
        assert len(active) == 1
        assert active[0].session_id == s3.session_id

    def test_list_sessions_filter_no_matches(self, manager):
        """list_sessions returns empty list when no sessions match the filter."""
        manager.create_session()

        result = manager.list_sessions(status="declined")
        assert result == []


class TestJsonRoundTrip:
    """Test JSON serialization/deserialization round-trips for complex fields."""

    def test_dialogue_history_round_trip(self, manager):
        """dialogue_history list of dicts survives SQLite JSON round-trip."""
        session = manager.create_session()

        history = [
            {"role": "agent", "content": "Welcome!", "timestamp": "2026-01-01T10:00:00"},
            {"role": "user", "content": "Hello, I need help.", "timestamp": "2026-01-01T10:00:05"},
            {"role": "agent", "content": "Sure, what is your company name?", "timestamp": "2026-01-01T10:00:10"},
        ]
        session.dialogue_history = history
        manager.update_session(session)

        loaded = manager.get_session(session.session_id)
        assert loaded.dialogue_history == history
        assert len(loaded.dialogue_history) == 3
        assert loaded.dialogue_history[0]["role"] == "agent"
        assert loaded.dialogue_history[1]["content"] == "Hello, I need help."

    def test_anketa_data_nested_dict_round_trip(self, manager):
        """anketa_data with nested dicts and lists survives SQLite JSON round-trip."""
        session = manager.create_session()

        nested_anketa = {
            "company_name": "DeepTech LLC",
            "industry": "AI/ML",
            "contacts": {
                "primary": {"name": "Alice", "email": "alice@deeptech.com"},
                "secondary": {"name": "Bob", "phone": "+71234567890"},
            },
            "services": ["consulting", "development", "support"],
            "integrations": {
                "crm": {"enabled": True, "provider": "Bitrix24"},
                "email": {"enabled": False},
            },
            "numeric_value": 42,
            "float_value": 3.14,
            "flag": True,
            "nothing": None,
        }

        manager.update_anketa(session.session_id, nested_anketa)

        loaded = manager.get_session(session.session_id)
        assert loaded.anketa_data == nested_anketa
        assert loaded.anketa_data["contacts"]["primary"]["name"] == "Alice"
        assert loaded.anketa_data["integrations"]["crm"]["enabled"] is True
        assert loaded.anketa_data["nothing"] is None
        assert loaded.anketa_data["services"] == ["consulting", "development", "support"]

    def test_dialogue_history_with_cyrillic(self, manager):
        """dialogue_history preserves Cyrillic text through JSON round-trip."""
        session = manager.create_session()

        history = [
            {"role": "agent", "content": "Здравствуйте! Как называется ваша компания?"},
            {"role": "user", "content": "Компания 'ТехноСервис'"},
        ]
        session.dialogue_history = history
        manager.update_session(session)

        loaded = manager.get_session(session.session_id)
        assert loaded.dialogue_history == history
        assert "ТехноСервис" in loaded.dialogue_history[1]["content"]

    def test_empty_dialogue_history_round_trip(self, manager):
        """Empty dialogue_history is stored and loaded as an empty list."""
        session = manager.create_session()

        loaded = manager.get_session(session.session_id)
        assert loaded.dialogue_history == []
        assert isinstance(loaded.dialogue_history, list)


class TestListSessionsSummary:
    """Test list_sessions_summary — lightweight query for dashboard."""

    def test_returns_empty_list_when_no_sessions(self, manager):
        """list_sessions_summary returns [] when DB is empty."""
        result, total = manager.list_sessions_summary()
        assert result == []
        assert total == 0

    def test_returns_correct_fields(self, manager):
        """Each summary dict has exactly the expected lightweight fields."""
        session = manager.create_session(room_name="room-summary")
        session.company_name = "SummaryCorp"
        session.contact_name = "Иван"
        manager.update_session(session)

        summaries, total = manager.list_sessions_summary()
        assert len(summaries) == 1
        assert total == 1

        s = summaries[0]
        expected_keys = {
            "session_id", "unique_link", "status", "created_at",
            "updated_at", "company_name", "contact_name", "duration_seconds",
            "room_name", "has_documents",
        }
        assert set(s.keys()) == expected_keys
        assert s["company_name"] == "SummaryCorp"
        assert s["contact_name"] == "Иван"
        assert s["room_name"] == "room-summary"

    def test_excludes_heavy_fields(self, manager):
        """Summary must NOT include dialogue_history, anketa_data, etc."""
        session = manager.create_session()
        session.dialogue_history = [{"role": "agent", "content": "Hello"}]
        manager.update_anketa(session.session_id, {"company_name": "Heavy"})
        manager.update_session(session)

        summaries, _ = manager.list_sessions_summary()
        s = summaries[0]
        assert "dialogue_history" not in s
        assert "anketa_data" not in s
        assert "anketa_md" not in s
        assert "document_context" not in s

    def test_filter_by_status(self, manager):
        """list_sessions_summary filters by status."""
        s1 = manager.create_session()
        s2 = manager.create_session()
        s3 = manager.create_session()
        manager.update_status(s1.session_id, "paused")
        manager.update_status(s2.session_id, "confirmed")
        # s3 stays active

        paused, paused_total = manager.list_sessions_summary(status="paused")
        assert len(paused) == 1
        assert paused_total == 1
        assert paused[0]["session_id"] == s1.session_id

        active, active_total = manager.list_sessions_summary(status="active")
        assert len(active) == 1
        assert active_total == 1
        assert active[0]["session_id"] == s3.session_id

        confirmed, confirmed_total = manager.list_sessions_summary(status="confirmed")
        assert len(confirmed) == 1
        assert confirmed_total == 1

    def test_filter_no_matches(self, manager):
        """Returns empty list when status filter has no matches."""
        manager.create_session()
        result, total = manager.list_sessions_summary(status="declined")
        assert result == []
        assert total == 0

    def test_limit_and_offset(self, manager):
        """Limit and offset work correctly."""
        for _ in range(5):
            manager.create_session()

        all_sessions, all_total = manager.list_sessions_summary()
        assert len(all_sessions) == 5
        assert all_total == 5

        limited, limited_total = manager.list_sessions_summary(limit=2)
        assert len(limited) == 2
        assert limited_total == 5  # total is always full count

        offset_result, offset_total = manager.list_sessions_summary(limit=2, offset=3)
        assert len(offset_result) == 2
        assert offset_total == 5

        too_much_offset, too_much_total = manager.list_sessions_summary(offset=10)
        assert len(too_much_offset) == 0
        assert too_much_total == 5  # total count unchanged even with large offset

    def test_ordered_by_created_at_desc(self, manager):
        """Sessions are returned newest first."""
        s1 = manager.create_session()
        manager.create_session()
        s3 = manager.create_session()

        summaries, _ = manager.list_sessions_summary()
        # Newest first: s3, _, s1
        assert summaries[0]["session_id"] == s3.session_id
        assert summaries[2]["session_id"] == s1.session_id

    def test_no_filter_returns_all_statuses(self, manager):
        """Without status filter, all sessions are returned regardless of status."""
        s1 = manager.create_session()
        s2 = manager.create_session()
        manager.create_session()
        manager.update_status(s1.session_id, "paused")
        manager.update_status(s2.session_id, "confirmed")

        all_sessions, total = manager.list_sessions_summary()
        assert len(all_sessions) == 3
        assert total == 3
        statuses = {s["status"] for s in all_sessions}
        assert statuses == {"active", "paused", "confirmed"}


class TestDeleteSessions:
    """Test delete_sessions — bulk deletion."""

    def test_delete_single_session(self, manager):
        """Deleting a single session removes it from the database."""
        s = manager.create_session()
        deleted = manager.delete_sessions([s.session_id])
        assert deleted == 1
        assert manager.get_session(s.session_id) is None

    def test_delete_multiple_sessions(self, manager):
        """Deleting multiple sessions removes all of them."""
        s1 = manager.create_session()
        s2 = manager.create_session()
        s3 = manager.create_session()
        deleted = manager.delete_sessions([s1.session_id, s3.session_id])
        assert deleted == 2
        assert manager.get_session(s1.session_id) is None
        assert manager.get_session(s2.session_id) is not None
        assert manager.get_session(s3.session_id) is None

    def test_delete_nonexistent_returns_zero(self, manager):
        """Deleting non-existent IDs returns 0."""
        deleted = manager.delete_sessions(["nonexistent-id"])
        assert deleted == 0

    def test_delete_empty_list(self, manager):
        """Deleting empty list returns 0 without error."""
        manager.create_session()
        deleted = manager.delete_sessions([])
        assert deleted == 0

    def test_deleted_sessions_not_in_summary(self, manager):
        """Deleted sessions do not appear in list_sessions_summary."""
        s1 = manager.create_session()
        s2 = manager.create_session()
        manager.delete_sessions([s1.session_id])
        summaries, total = manager.list_sessions_summary()
        assert len(summaries) == 1
        assert total == 1
        assert summaries[0]["session_id"] == s2.session_id


class TestClose:
    """Test manager close behavior."""

    def test_close_works_without_error(self, tmp_path):
        """close() completes without raising any exception."""
        db_path = str(tmp_path / "close_test.db")
        mgr = SessionManager(db_path=db_path)

        # Use the manager first to ensure it is fully initialized
        mgr.create_session()

        # close() should not raise
        mgr.close()

    def test_close_idempotent_concept(self, tmp_path):
        """Closing a manager that was used normally does not corrupt data."""
        db_path = str(tmp_path / "idempotent_test.db")
        mgr = SessionManager(db_path=db_path)
        session = mgr.create_session(room_name="persist-check")
        sid = session.session_id
        mgr.close()

        # Reopen and verify data survived
        mgr2 = SessionManager(db_path=db_path)
        loaded = mgr2.get_session(sid)
        assert loaded is not None
        assert loaded.room_name == "persist-check"
        mgr2.close()
