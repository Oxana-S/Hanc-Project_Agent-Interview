"""
Unit tests for ConsultationSession model in src/session/models.py
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.session.models import ConsultationSession, VALID_STATUSES


class TestValidStatuses:
    """Test the VALID_STATUSES constant."""

    def test_valid_statuses_contains_exactly_expected(self):
        expected = {"active", "paused", "reviewing", "confirmed", "declined"}
        assert VALID_STATUSES == expected

    def test_valid_statuses_has_five_entries(self):
        assert len(VALID_STATUSES) == 5

    def test_valid_statuses_is_a_set(self):
        assert isinstance(VALID_STATUSES, set)


class TestRequiredFields:
    """Test that session_id and unique_link are required."""

    def test_missing_session_id_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            ConsultationSession(unique_link="abc-def-123")
        assert "session_id" in str(exc_info.value)

    def test_missing_unique_link_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            ConsultationSession(session_id="abcd1234")
        assert "unique_link" in str(exc_info.value)

    def test_missing_both_required_fields_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            ConsultationSession()
        errors = str(exc_info.value)
        assert "session_id" in errors
        assert "unique_link" in errors


class TestDefaultValues:
    """Test that default values are set correctly."""

    def test_room_name_defaults_to_empty_string(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.room_name == ""

    def test_status_defaults_to_active(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.status == "active"

    def test_dialogue_history_defaults_to_empty_list(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.dialogue_history == []
        assert isinstance(session.dialogue_history, list)

    def test_anketa_data_defaults_to_none(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.anketa_data is None

    def test_anketa_md_defaults_to_none(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.anketa_md is None

    def test_company_name_defaults_to_none(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.company_name is None

    def test_contact_name_defaults_to_none(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.contact_name is None

    def test_duration_seconds_defaults_to_zero(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.duration_seconds == 0.0

    def test_output_dir_defaults_to_none(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.output_dir is None


class TestDatetimeFields:
    """Test that datetime fields are set by default."""

    def test_created_at_is_set_by_default(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.created_at is not None
        assert isinstance(session.created_at, datetime)

    def test_updated_at_is_set_by_default(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        assert session.updated_at is not None
        assert isinstance(session.updated_at, datetime)

    def test_created_at_is_recent(self):
        before = datetime.now()
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        after = datetime.now()
        assert before <= session.created_at <= after

    def test_updated_at_is_recent(self):
        before = datetime.now()
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        after = datetime.now()
        assert before <= session.updated_at <= after


class TestFullCreation:
    """Test model creation with all fields provided."""

    def test_create_with_all_fields(self):
        now = datetime.now()
        session = ConsultationSession(
            session_id="abcd1234",
            room_name="room-test-123",
            unique_link="550e8400-e29b-41d4-a716-446655440000",
            status="reviewing",
            created_at=now,
            updated_at=now,
            dialogue_history=[
                {"role": "agent", "content": "Hello", "timestamp": "2026-01-01T00:00:00"},
                {"role": "user", "content": "Hi there", "timestamp": "2026-01-01T00:00:05"},
            ],
            anketa_data={"company": "TestCorp", "industry": "IT"},
            anketa_md="# Anketa\n\nCompany: TestCorp",
            company_name="TestCorp",
            contact_name="Ivan Ivanov",
            duration_seconds=345.7,
            output_dir="/tmp/output/abcd1234",
        )
        assert session.session_id == "abcd1234"
        assert session.room_name == "room-test-123"
        assert session.unique_link == "550e8400-e29b-41d4-a716-446655440000"
        assert session.status == "reviewing"
        assert session.created_at == now
        assert session.updated_at == now
        assert len(session.dialogue_history) == 2
        assert session.anketa_data == {"company": "TestCorp", "industry": "IT"}
        assert session.anketa_md == "# Anketa\n\nCompany: TestCorp"
        assert session.company_name == "TestCorp"
        assert session.contact_name == "Ivan Ivanov"
        assert session.duration_seconds == 345.7
        assert session.output_dir == "/tmp/output/abcd1234"


class TestModelDump:
    """Test model_dump() returns correct dict."""

    def test_model_dump_returns_dict(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        data = session.model_dump()
        assert isinstance(data, dict)

    def test_model_dump_contains_all_fields(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        data = session.model_dump()
        expected_keys = {
            "session_id", "room_name", "unique_link", "status",
            "created_at", "updated_at", "dialogue_history",
            "anketa_data", "anketa_md", "company_name", "contact_name",
            "duration_seconds", "output_dir", "document_context",
            "voice_config",
        }
        assert set(data.keys()) == expected_keys

    def test_model_dump_preserves_values(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link-uuid",
            company_name="TestCorp",
            duration_seconds=120.5,
        )
        data = session.model_dump()
        assert data["session_id"] == "abcd1234"
        assert data["unique_link"] == "link-uuid"
        assert data["company_name"] == "TestCorp"
        assert data["duration_seconds"] == 120.5
        assert data["status"] == "active"
        assert data["room_name"] == ""


class TestJsonRoundTrip:
    """Test JSON round-trip: model_dump() -> ConsultationSession(**data) preserves data."""

    def test_roundtrip_minimal(self):
        original = ConsultationSession(session_id="abcd1234", unique_link="full-uuid-link")
        data = original.model_dump()
        restored = ConsultationSession(**data)
        assert restored.session_id == original.session_id
        assert restored.unique_link == original.unique_link
        assert restored.status == original.status
        assert restored.room_name == original.room_name
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at
        assert restored.dialogue_history == original.dialogue_history
        assert restored.anketa_data == original.anketa_data
        assert restored.duration_seconds == original.duration_seconds

    def test_roundtrip_full(self):
        now = datetime.now()
        original = ConsultationSession(
            session_id="xyz98765",
            room_name="room-abc",
            unique_link="550e8400-e29b-41d4-a716-446655440000",
            status="confirmed",
            created_at=now,
            updated_at=now,
            dialogue_history=[
                {"role": "agent", "content": "Welcome"},
                {"role": "user", "content": "Thanks"},
            ],
            anketa_data={"key": "value", "nested": {"a": 1}},
            anketa_md="# Test",
            company_name="RoundTripCo",
            contact_name="Test User",
            duration_seconds=999.9,
            output_dir="/tmp/test",
        )
        data = original.model_dump()
        restored = ConsultationSession(**data)
        assert restored.session_id == original.session_id
        assert restored.room_name == original.room_name
        assert restored.unique_link == original.unique_link
        assert restored.status == original.status
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at
        assert restored.dialogue_history == original.dialogue_history
        assert restored.anketa_data == original.anketa_data
        assert restored.anketa_md == original.anketa_md
        assert restored.company_name == original.company_name
        assert restored.contact_name == original.contact_name
        assert restored.duration_seconds == original.duration_seconds
        assert restored.output_dir == original.output_dir

    def test_roundtrip_produces_equal_dumps(self):
        original = ConsultationSession(
            session_id="abcd1234",
            unique_link="link-1234",
            company_name="Corp",
        )
        data = original.model_dump()
        restored = ConsultationSession(**data)
        assert original.model_dump() == restored.model_dump()


class TestDialogueHistory:
    """Test dialogue_history accepts list of dicts."""

    def test_empty_dialogue_history(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            dialogue_history=[],
        )
        assert session.dialogue_history == []

    def test_dialogue_history_with_entries(self):
        history = [
            {"role": "agent", "content": "Hello, how can I help?", "timestamp": "2026-01-01T10:00:00"},
            {"role": "user", "content": "I need consulting", "timestamp": "2026-01-01T10:00:05"},
            {"role": "agent", "content": "Sure, let me ask some questions", "timestamp": "2026-01-01T10:00:10"},
        ]
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            dialogue_history=history,
        )
        assert len(session.dialogue_history) == 3
        assert session.dialogue_history[0]["role"] == "agent"
        assert session.dialogue_history[1]["content"] == "I need consulting"

    def test_dialogue_history_with_extra_keys(self):
        history = [
            {"role": "agent", "content": "Hi", "phase": "greeting", "extra_field": 42},
        ]
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            dialogue_history=history,
        )
        assert session.dialogue_history[0]["extra_field"] == 42
        assert session.dialogue_history[0]["phase"] == "greeting"


class TestAnketaData:
    """Test anketa_data accepts nested dict."""

    def test_anketa_data_none(self):
        session = ConsultationSession(session_id="abcd1234", unique_link="link")
        assert session.anketa_data is None

    def test_anketa_data_simple_dict(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            anketa_data={"company": "TestCorp", "industry": "IT"},
        )
        assert session.anketa_data["company"] == "TestCorp"
        assert session.anketa_data["industry"] == "IT"

    def test_anketa_data_nested_dict(self):
        nested = {
            "company": "TestCorp",
            "details": {
                "address": {"city": "Moscow", "street": "Tverskaya 1"},
                "contacts": [
                    {"name": "Ivan", "phone": "+71234567890"},
                    {"name": "Maria", "phone": "+70987654321"},
                ],
            },
            "scores": [0.8, 0.9, 0.95],
        }
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            anketa_data=nested,
        )
        assert session.anketa_data["details"]["address"]["city"] == "Moscow"
        assert len(session.anketa_data["details"]["contacts"]) == 2
        assert session.anketa_data["scores"][2] == 0.95


class TestOptionalFieldsCanBeNone:
    """Test that all Optional fields can be explicitly set to None."""

    def test_anketa_data_explicit_none(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            anketa_data=None,
        )
        assert session.anketa_data is None

    def test_anketa_md_explicit_none(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            anketa_md=None,
        )
        assert session.anketa_md is None

    def test_company_name_explicit_none(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            company_name=None,
        )
        assert session.company_name is None

    def test_contact_name_explicit_none(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            contact_name=None,
        )
        assert session.contact_name is None

    def test_output_dir_explicit_none(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            output_dir=None,
        )
        assert session.output_dir is None

    def test_all_optional_fields_none_simultaneously(self):
        session = ConsultationSession(
            session_id="abcd1234",
            unique_link="link",
            anketa_data=None,
            anketa_md=None,
            company_name=None,
            contact_name=None,
            output_dir=None,
        )
        assert session.anketa_data is None
        assert session.anketa_md is None
        assert session.company_name is None
        assert session.contact_name is None
        assert session.output_dir is None
