"""
Unit tests for core (non-pipeline-wiring) parts of src/voice/consultant.py.

Covers:
- VoiceConsultationSession class (init, add_message, get_duration, get_company_name)
- get_system_prompt()
- get_enriched_system_prompt()
- get_review_system_prompt()
- format_anketa_for_voice()
- _build_resume_context()
- _lookup_db_session()
- _init_consultation()
- _handle_conversation_item()
- _try_get_redis() / _try_get_postgres()
- finalize_consultation()
- _register_event_handlers()

The 39 pipeline-wiring tests live in test_voice_pipeline_wiring.py; this file
tests everything else.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.voice.consultant import (
    VoiceConsultationSession,
    _extract_and_update_anketa,
    _finalize_and_save,
    _try_get_redis,
    _try_get_postgres,
    _run_background_research,
    get_review_system_prompt,
    format_anketa_for_voice,
    get_system_prompt,
    get_enriched_system_prompt,
    _build_resume_context,
    _lookup_db_session,
    _init_consultation,
    _handle_conversation_item,
    _register_event_handlers,
    finalize_consultation,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_voice_pipeline_wiring.py)
# ---------------------------------------------------------------------------

def _make_consultation(messages=20, kb_enriched=False, review_started=False, research_done=False):
    """Create a VoiceConsultationSession with dialogue history."""
    c = VoiceConsultationSession(room_name="consultation-test-001")
    c.session_id = "test-001"
    c.kb_enriched = kb_enriched
    c.review_started = review_started
    c.research_done = research_done
    for i in range(messages):
        role = "user" if i % 2 == 0 else "assistant"
        c.add_message(role, f"Test message {i}")
    return c


def _make_db_session(**overrides):
    """Create a SimpleNamespace mimicking a DB session."""
    defaults = {
        "session_id": "test-001",
        "company_name": "TestCorp",
        "contact_name": "Test User",
        "status": "active",
        "dialogue_history": [],
        "duration_seconds": 600,
        "document_context": None,
        "anketa_data": {"company_name": "TestCorp", "industry": "IT"},
        "anketa_md": "# Anketa",
        "unique_link": "abc-123",
        "voice_config": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_agent_session():
    """Create a mock AgentSession with _activity."""
    session = AsyncMock()
    activity = MagicMock()
    activity.update_instructions = AsyncMock()
    activity.instructions = "base prompt"
    session._activity = activity
    session.generate_reply = AsyncMock()
    return session


def _make_event(role="assistant", content="Hello!"):
    """Create a mock conversation event."""
    event = MagicMock()
    event.item = MagicMock()
    event.item.role = role
    event.item.content = content
    return event


# ===========================================================================
# 1. TestVoiceConsultationSession (12 tests)
# ===========================================================================

class TestVoiceConsultationSession:
    """Tests for VoiceConsultationSession class basic functionality."""

    def test_init_defaults(self):
        """Default constructor creates a session with expected defaults."""
        s = VoiceConsultationSession()
        assert s.room_name == ""
        assert s.status == "active"
        assert isinstance(s.dialogue_history, list)
        assert len(s.dialogue_history) == 0
        assert s.document_context is None
        assert isinstance(s.start_time, datetime)

    def test_init_with_room_name(self):
        """Constructor stores the room_name argument."""
        s = VoiceConsultationSession(room_name="consultation-abc123")
        assert s.room_name == "consultation-abc123"

    def test_session_id_is_short_uuid(self):
        """session_id should be an 8-character hex-like string (uuid[:8])."""
        s = VoiceConsultationSession()
        assert isinstance(s.session_id, str)
        assert len(s.session_id) == 8

    def test_add_message_appends_to_history(self):
        """add_message appends one entry per call."""
        s = VoiceConsultationSession()
        s.add_message("user", "Hi there")
        assert len(s.dialogue_history) == 1
        s.add_message("assistant", "Hello!")
        assert len(s.dialogue_history) == 2

    def test_add_message_includes_role_content_timestamp(self):
        """Each message dict has role, content, and timestamp keys."""
        s = VoiceConsultationSession()
        s.add_message("user", "Question?")
        msg = s.dialogue_history[0]
        assert msg["role"] == "user"
        assert msg["content"] == "Question?"
        assert "timestamp" in msg
        # timestamp should be ISO format parseable
        datetime.fromisoformat(msg["timestamp"])

    def test_add_message_includes_phase(self):
        """Each message should have phase matching current_phase (default: discovery)."""
        s = VoiceConsultationSession()
        s.add_message("assistant", "Welcome!")
        assert s.dialogue_history[0]["phase"] == "discovery"

    def test_add_message_phase_changes_with_session(self):
        """Phase in messages should reflect session's current_phase."""
        s = VoiceConsultationSession()
        s.current_phase = "proposal"
        s.add_message("assistant", "Here is my proposal.")
        assert s.dialogue_history[0]["phase"] == "proposal"

    def test_get_duration_seconds_positive(self):
        """get_duration_seconds returns a positive float."""
        s = VoiceConsultationSession()
        # Even immediately, duration should be >= 0
        duration = s.get_duration_seconds()
        assert isinstance(duration, float)
        assert duration >= 0.0

    def test_get_company_name_from_dialogue_kompaniya(self):
        """get_company_name extracts from user message containing 'компания'."""
        s = VoiceConsultationSession()
        s.add_message("user", "Наша компания называется АльфаТрейд")
        result = s.get_company_name()
        assert "компания" in result.lower() or "АльфаТрейд" in result

    def test_get_company_name_from_dialogue_nazyvaetsya(self):
        """get_company_name extracts from user message containing 'называется'."""
        s = VoiceConsultationSession()
        s.add_message("assistant", "Как называется ваша компания?")
        s.add_message("user", "Она называется ТехноПлюс")
        result = s.get_company_name()
        assert "называется" in result.lower()

    def test_get_company_name_fallback_to_session_id(self):
        """get_company_name returns 'session_{id}' when nothing found."""
        s = VoiceConsultationSession()
        s.session_id = "abc12345"
        s.add_message("user", "Привет")
        result = s.get_company_name()
        assert result == "session_abc12345"

    def test_status_default_active(self):
        """Default status is 'active'."""
        s = VoiceConsultationSession()
        assert s.status == "active"

    def test_flags_default_false(self):
        """kb_enriched, review_started, research_done all default to False."""
        s = VoiceConsultationSession()
        assert s.kb_enriched is False
        assert s.review_started is False
        assert s.research_done is False


# ===========================================================================
# 2. TestGetSystemPrompt (2 tests)
# ===========================================================================

class TestGetSystemPrompt:
    """Tests for get_system_prompt()."""

    def test_get_system_prompt_returns_string(self):
        """get_system_prompt returns a string."""
        with patch("src.voice.consultant.get_prompt", return_value="Test prompt text"):
            result = get_system_prompt()
            assert isinstance(result, str)

    def test_get_system_prompt_not_empty(self):
        """get_system_prompt returns a non-empty string."""
        with patch("src.voice.consultant.get_prompt", return_value="Test prompt text"):
            result = get_system_prompt()
            assert len(result) > 0


# ===========================================================================
# 3. TestGetEnrichedSystemPrompt (4 tests)
# ===========================================================================

class TestGetEnrichedSystemPrompt:
    """Tests for get_enriched_system_prompt()."""

    def test_enriched_with_few_messages_returns_base(self):
        """With fewer than 2 messages, returns base prompt unchanged."""
        with patch("src.voice.consultant.get_prompt", return_value="BASE PROMPT"):
            result = get_enriched_system_prompt([{"role": "user", "content": "Hi"}])
            assert result == "BASE PROMPT"

    def test_enriched_with_enough_messages_includes_context(self):
        """With >= 2 messages and detected industry, enriches prompt."""
        dialogue = [
            {"role": "user", "content": "Мы логистическая компания"},
            {"role": "assistant", "content": "Расскажите подробнее"},
        ]
        with patch("src.voice.consultant.get_prompt", return_value="BASE PROMPT"), \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb:
            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = "Industry: logistics"
            mock_ecb.return_value = mock_builder

            result = get_enriched_system_prompt(dialogue)
            assert "BASE PROMPT" in result
            assert "Контекст отрасли" in result
            assert "Industry: logistics" in result

    def test_enriched_exception_returns_base(self):
        """When enrichment raises, returns base prompt."""
        dialogue = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        with patch("src.voice.consultant.get_prompt", return_value="BASE PROMPT"), \
             patch("src.voice.consultant.IndustryKnowledgeManager", side_effect=Exception("KB error")):
            result = get_enriched_system_prompt(dialogue)
            assert result == "BASE PROMPT"

    def test_enriched_base_prompt_always_present(self):
        """Base prompt is always present in enriched result."""
        dialogue = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        with patch("src.voice.consultant.get_prompt", return_value="BASE PROMPT"), \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb:
            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = None  # No context available
            mock_ecb.return_value = mock_builder

            result = get_enriched_system_prompt(dialogue)
            assert result == "BASE PROMPT"


# ===========================================================================
# 4. TestFormatAnketaForVoice (6 tests)
# ===========================================================================

class TestFormatAnketaForVoice:
    """Tests for format_anketa_for_voice()."""

    def test_format_full_data(self):
        """Formats all non-None fields into numbered lines."""
        data = {
            "company_name": "TestCorp",
            "contact_name": "Ivan",
            "industry": "IT",
            "services": "Web development",
            "current_problems": "Too many calls",
            "proposed_tasks": "Automate",
            "integrations": ["CRM", "1C"],
            "notes": "Extra info",
        }
        result = format_anketa_for_voice(data)
        assert "1." in result
        assert "TestCorp" in result
        assert "Ivan" in result
        assert "IT" in result
        assert "CRM, 1C" in result

    def test_format_empty_dict_returns_empty_message(self):
        """Empty dict returns the 'empty anketa' placeholder."""
        result = format_anketa_for_voice({})
        assert "пуста" in result.lower()

    def test_format_with_list_values(self):
        """List values are joined with commas."""
        data = {"integrations": ["Slack", "Teams", "Email"]}
        result = format_anketa_for_voice(data)
        assert "Slack, Teams, Email" in result

    def test_format_skips_none_values(self):
        """None values are skipped entirely."""
        data = {
            "company_name": "TestCorp",
            "contact_name": None,
            "industry": None,
            "services": "Consulting",
        }
        result = format_anketa_for_voice(data)
        assert "TestCorp" in result
        assert "Consulting" in result
        # Should have exactly 2 numbered items
        assert "1." in result
        assert "2." in result
        assert "3." not in result

    def test_format_numbered_correctly(self):
        """Numbers are sequential starting from 1."""
        data = {
            "company_name": "A",
            "contact_name": "B",
            "industry": "C",
        }
        result = format_anketa_for_voice(data)
        lines = result.strip().split("\n")
        assert lines[0].startswith("1.")
        assert lines[1].startswith("2.")
        assert lines[2].startswith("3.")

    def test_format_partial_data(self):
        """Only present keys from the known sections appear."""
        data = {"industry": "Medicine"}
        result = format_anketa_for_voice(data)
        assert "1." in result
        assert "Medicine" in result
        assert "2." not in result


# ===========================================================================
# 5. TestBuildResumeContext (6 tests)
# ===========================================================================

class TestBuildResumeContext:
    """Tests for _build_resume_context()."""

    def test_resume_with_anketa_and_history(self):
        """Resume context includes both anketa and history sections."""
        db = _make_db_session(
            anketa_data={"company_name": "TestCorp", "industry": "IT"},
            dialogue_history=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello there"},
            ],
        )
        result = _build_resume_context(db)
        assert "ПРОДОЛЖЕНИЕ СЕССИИ" in result
        assert "TestCorp" in result
        assert "Клиент: Hi" in result
        assert "Консультант: Hello there" in result

    def test_resume_with_anketa_only(self):
        """Resume context with anketa but empty history."""
        db = _make_db_session(
            anketa_data={"company_name": "OnlyCorp"},
            dialogue_history=[],
        )
        result = _build_resume_context(db)
        assert "ПРОДОЛЖЕНИЕ СЕССИИ" in result
        assert "OnlyCorp" in result

    def test_resume_with_history_only(self):
        """Resume context with history but no anketa data."""
        db = _make_db_session(
            anketa_data=None,
            dialogue_history=[
                {"role": "user", "content": "Hi there"},
            ],
        )
        result = _build_resume_context(db)
        assert "ПРОДОЛЖЕНИЕ СЕССИИ" in result
        assert "Клиент: Hi there" in result

    def test_resume_empty_session_returns_empty(self):
        """Resume context with no anketa and no history returns empty string."""
        db = _make_db_session(anketa_data=None, dialogue_history=[])
        result = _build_resume_context(db)
        assert result == ""

    def test_resume_truncates_long_messages(self):
        """Messages longer than 300 characters are truncated with '...'."""
        long_msg = "A" * 400
        db = _make_db_session(
            anketa_data=None,
            dialogue_history=[
                {"role": "user", "content": long_msg},
            ],
        )
        result = _build_resume_context(db)
        assert "..." in result
        # The truncated content should be 300 chars from original
        assert "A" * 300 in result
        assert "A" * 301 not in result

    def test_resume_limits_to_20_messages(self):
        """Only the last 20 messages are included."""
        history = [
            {"role": "user", "content": f"Message {i}"} for i in range(30)
        ]
        db = _make_db_session(anketa_data=None, dialogue_history=history)
        result = _build_resume_context(db)
        # Messages 0-9 should not appear, messages 10-29 should
        assert "Message 0" not in result
        assert "Message 10" in result
        assert "Message 29" in result


# ===========================================================================
# 6. TestLookupDbSession (4 tests)
# ===========================================================================

class TestLookupDbSession:
    """Tests for _lookup_db_session()."""

    def test_lookup_valid_room_name(self):
        """Valid room name returns session_id and db_session."""
        db_session = _make_db_session()
        with patch("src.voice.consultant._session_mgr") as mock_mgr:
            mock_mgr.get_session.return_value = db_session
            sid, session = _lookup_db_session("consultation-test-001")
            assert sid == "test-001"
            assert session is db_session

    def test_lookup_invalid_room_name_returns_none(self):
        """Room name without 'consultation-' prefix returns (None, None)."""
        sid, session = _lookup_db_session("random-room-name")
        assert sid is None
        assert session is None

    def test_lookup_session_not_found_returns_none(self):
        """Valid prefix but DB session not found returns (session_id, None)."""
        with patch("src.voice.consultant._session_mgr") as mock_mgr:
            mock_mgr.get_session.return_value = None
            sid, session = _lookup_db_session("consultation-missing-123")
            assert sid == "missing-123"
            assert session is None

    def test_lookup_extracts_correct_session_id(self):
        """Extracts the full suffix after 'consultation-' as session_id."""
        with patch("src.voice.consultant._session_mgr") as mock_mgr:
            mock_mgr.get_session.return_value = None
            sid, _ = _lookup_db_session("consultation-abc-def-ghi")
            assert sid == "abc-def-ghi"


# ===========================================================================
# 7. TestInitConsultation (4 tests)
# ===========================================================================

class TestInitConsultation:
    """Tests for _init_consultation()."""

    def test_init_consultation_without_db(self):
        """Without DB session, creates fresh consultation."""
        c = _init_consultation("consultation-new-001", None)
        assert isinstance(c, VoiceConsultationSession)
        assert c.room_name == "consultation-new-001"
        assert len(c.dialogue_history) == 0

    def test_init_consultation_with_db_session(self):
        """With DB session, consultation is seeded with DB data."""
        db = _make_db_session(
            session_id="db-session-id",
            dialogue_history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ],
        )
        c = _init_consultation("consultation-db-session-id", db)
        assert c.session_id == "db-session-id"
        assert len(c.dialogue_history) == 2

    def test_init_consultation_copies_dialogue_history(self):
        """Dialogue history is copied, not referenced."""
        original = [{"role": "user", "content": "Hello"}]
        db = _make_db_session(dialogue_history=original)
        c = _init_consultation("consultation-test-001", db)
        # Modifying consultation history should not affect original
        c.dialogue_history.append({"role": "assistant", "content": "Hi"})
        assert len(original) == 1
        assert len(c.dialogue_history) == 2

    def test_init_consultation_uses_db_session_id(self):
        """Consultation uses session_id from DB session, not a new UUID."""
        db = _make_db_session(session_id="specific-id-123")
        c = _init_consultation("consultation-specific-id-123", db)
        assert c.session_id == "specific-id-123"


# ===========================================================================
# 8. TestHandleConversationItem (12 tests)
# ===========================================================================

class TestHandleConversationItem:
    """Tests for _handle_conversation_item()."""

    def test_handle_assistant_message_adds_to_history(self):
        """Assistant messages are added to dialogue_history."""
        c = _make_consultation(messages=0)
        event = _make_event(role="assistant", content="Hello there!")
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 1
        assert c.dialogue_history[0]["role"] == "assistant"
        assert c.dialogue_history[0]["content"] == "Hello there!"

    def test_handle_user_message_skipped(self):
        """User messages are skipped (prevents double-counting with on_user_input_transcribed)."""
        c = _make_consultation(messages=0)
        event = _make_event(role="user", content="My question")
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 0

    def test_handle_no_role_skips(self):
        """Items without a role are skipped."""
        c = _make_consultation(messages=0)
        event = MagicMock()
        event.item = MagicMock()
        event.item.role = None
        event.item.content = "Something"
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 0

    def test_handle_empty_content_skips(self):
        """Items with empty content are skipped."""
        c = _make_consultation(messages=0)
        event = _make_event(role="assistant", content="")
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 0

    def test_handle_list_content_extracts_text(self):
        """List content is joined into a single string."""
        c = _make_consultation(messages=0)
        event = _make_event(role="assistant", content=["Hello", " ", "World"])
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 1
        assert "Hello" in c.dialogue_history[0]["content"]
        assert "World" in c.dialogue_history[0]["content"]

    def test_handle_non_string_content_converts(self):
        """Non-string, non-list content is converted to string."""
        c = _make_consultation(messages=0)
        event = _make_event(role="assistant", content=12345)
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 1
        assert c.dialogue_history[0]["content"] == "12345"

    def test_handle_increments_message_counter(self):
        """Message counter increments for assistant messages."""
        c = _make_consultation(messages=0)
        event = _make_event(role="assistant", content="Response")
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert counter[0] == 1

    def test_handle_triggers_extraction_at_6(self):
        """Extraction is triggered when counter reaches 6."""
        c = _make_consultation(messages=0)
        counter = [5]  # one more will trigger

        with patch("src.voice.consultant.asyncio") as mock_asyncio:
            event = _make_event(role="assistant", content="Response six")
            _handle_conversation_item(event, c, "test-001", True, counter, None)
            mock_asyncio.create_task.assert_called_once()

    def test_handle_resets_counter_after_extraction(self):
        """Counter resets to 0 after extraction is triggered."""
        c = _make_consultation(messages=0)
        counter = [5]

        with patch("src.voice.consultant.asyncio") as mock_asyncio:
            event = _make_event(role="assistant", content="Response six")
            _handle_conversation_item(event, c, "test-001", True, counter, None)
            assert counter[0] == 0

    def test_handle_no_extraction_without_db(self):
        """No extraction when db_backed is False."""
        c = _make_consultation(messages=0)
        counter = [5]

        with patch("src.voice.consultant.asyncio") as mock_asyncio:
            event = _make_event(role="assistant", content="Response")
            _handle_conversation_item(event, c, None, False, counter, None)
            mock_asyncio.create_task.assert_not_called()

    def test_handle_exception_does_not_crash(self):
        """Exception inside handler is caught gracefully."""
        c = _make_consultation(messages=0)
        # Create an event that will cause an AttributeError
        event = MagicMock()
        event.item = None  # This will cause getattr to fail differently
        # Actually, getattr(None, 'role', None) returns None, so let's
        # force an exception via the item property
        event_broken = MagicMock()
        type(event_broken).item = PropertyMock(side_effect=Exception("Broken event"))
        counter = [0]

        # Should not raise
        _handle_conversation_item(event_broken, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 0

    def test_handle_none_content_skips(self):
        """Items with None content are skipped."""
        c = _make_consultation(messages=0)
        event = _make_event(role="assistant", content=None)
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 0


# ===========================================================================
# 9. TestTryGetRedis (4 tests)
# ===========================================================================

class TestTryGetRedis:
    """Tests for _try_get_redis() connection helper."""

    def test_redis_returns_none_when_unavailable(self):
        """Returns None when health check fails."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        mod._redis_mgr = None

        try:
            with patch("src.storage.redis.RedisStorageManager") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.health_check.return_value = False
                mock_cls.return_value = mock_instance
                result = _try_get_redis()
                assert result is None
        finally:
            mod._redis_mgr = original

    def test_redis_returns_manager_when_available(self):
        """Returns manager instance when health check passes."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        mod._redis_mgr = None

        try:
            with patch("src.storage.redis.RedisStorageManager") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.health_check.return_value = True
                mock_cls.return_value = mock_instance
                result = _try_get_redis()
                assert result is mock_instance
        finally:
            mod._redis_mgr = original

    def test_redis_caches_after_first_success(self):
        """After first success, returns cached singleton without re-checking."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        cached_mgr = MagicMock()
        mod._redis_mgr = cached_mgr

        try:
            result = _try_get_redis()
            assert result is cached_mgr
        finally:
            mod._redis_mgr = original

    def test_redis_import_failure_returns_none(self):
        """Returns None when Redis module cannot be imported."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        mod._redis_mgr = None

        try:
            with patch("src.storage.redis.RedisStorageManager", side_effect=ImportError("No redis")):
                result = _try_get_redis()
                assert result is None
        finally:
            mod._redis_mgr = original


# ===========================================================================
# 10. TestTryGetPostgres (4 tests)
# ===========================================================================

class TestTryGetPostgres:
    """Tests for _try_get_postgres() connection helper."""

    def test_postgres_returns_none_when_no_url(self):
        """Returns None when DATABASE_URL is not set."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        mod._postgres_mgr = None

        try:
            with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
                result = _try_get_postgres()
                assert result is None
        finally:
            mod._postgres_mgr = original

    def test_postgres_returns_manager_when_available(self):
        """Returns manager when DATABASE_URL is set and health check passes."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        mod._postgres_mgr = None

        try:
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test@localhost/db"}), \
                 patch("src.storage.postgres.PostgreSQLStorageManager") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.health_check.return_value = True
                mock_cls.return_value = mock_instance
                result = _try_get_postgres()
                assert result is mock_instance
        finally:
            mod._postgres_mgr = original

    def test_postgres_caches_after_first_success(self):
        """After first success, returns cached singleton."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        cached_mgr = MagicMock()
        mod._postgres_mgr = cached_mgr

        try:
            result = _try_get_postgres()
            assert result is cached_mgr
        finally:
            mod._postgres_mgr = original

    def test_postgres_import_failure_returns_none(self):
        """Returns None when psycopg2 module cannot be imported."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        mod._postgres_mgr = None

        try:
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test@localhost/db"}), \
                 patch("src.storage.postgres.PostgreSQLStorageManager",
                       side_effect=ImportError("No psycopg2")):
                result = _try_get_postgres()
                assert result is None
        finally:
            mod._postgres_mgr = original


# ===========================================================================
# 11. TestFinalizeConsultation (6 tests)
# ===========================================================================

class TestFinalizeConsultation:
    """Tests for finalize_consultation()."""

    @pytest.mark.asyncio
    async def test_finalize_with_enough_messages(self):
        """Finalization runs extraction when there are enough messages."""
        c = _make_consultation(messages=6)

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.contact_name = "Ivan"
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        with patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/test/anketa.md", "json": "/tmp/test/anketa.json"}
            mock_output.save_dialogue.return_value = "/tmp/test/dialogue.md"
            mock_out_cls.return_value = mock_output

            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(c)

            assert c.status == "completed"
            mock_extractor.extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_skips_short_dialogue(self):
        """Finalization skips when dialogue has < 2 messages."""
        c = _make_consultation(messages=1)

        await finalize_consultation(c)

        assert c.status == "completed"

    @pytest.mark.asyncio
    async def test_finalize_sets_status_completed(self):
        """On successful finalization, status is set to 'completed'."""
        c = _make_consultation(messages=4)

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.contact_name = "Ivan"
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        with patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/a.md", "json": "/tmp/a.json"}
            mock_output.save_dialogue.return_value = "/tmp/d.md"
            mock_out_cls.return_value = mock_output

            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(c)

            assert c.status == "completed"

    @pytest.mark.asyncio
    async def test_finalize_error_sets_status_error(self):
        """On extraction error, status is set to 'error'."""
        c = _make_consultation(messages=4)

        with patch("src.voice.consultant.DeepSeekClient", side_effect=Exception("API down")):
            await finalize_consultation(c)
            assert c.status == "error"

    @pytest.mark.asyncio
    async def test_finalize_calls_extractor(self):
        """Finalization calls AnketaExtractor.extract() with dialogue_history."""
        c = _make_consultation(messages=4)

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.contact_name = "Ivan"
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        with patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/a.md", "json": "/tmp/a.json"}
            mock_output.save_dialogue.return_value = "/tmp/d.md"
            mock_out_cls.return_value = mock_output

            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(c)

            mock_extractor.extract.assert_called_once()
            call_kwargs = mock_extractor.extract.call_args
            assert call_kwargs[1]["dialogue_history"] == c.dialogue_history

    @pytest.mark.asyncio
    async def test_finalize_saves_output(self):
        """Finalization saves anketa and dialogue via OutputManager."""
        c = _make_consultation(messages=4)

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.contact_name = "Ivan"
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        with patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/a.md", "json": "/tmp/a.json"}
            mock_output.save_dialogue.return_value = "/tmp/d.md"
            mock_out_cls.return_value = mock_output

            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(c)

            mock_output.save_anketa.assert_called_once()
            mock_output.save_dialogue.assert_called_once()


# ===========================================================================
# 12. TestRegisterEventHandlers (5 tests)
# ===========================================================================

class TestRegisterEventHandlers:
    """Tests for _register_event_handlers()."""

    def _capture_handlers(self):
        """Create a mock session and capture registered handlers."""
        session = MagicMock()
        handlers = {}

        def mock_on(event_name):
            def decorator(fn):
                handlers[event_name] = fn
                return fn
            return decorator

        session.on = mock_on
        return session, handlers

    def test_register_event_handlers_registers_all_events(self):
        """All expected event names are registered."""
        session, handlers = self._capture_handlers()
        c = _make_consultation(messages=0)

        _register_event_handlers(session, c, "test-001", db_backed=True)

        expected_events = {
            "user_input_transcribed",
            "user_state_changed",
            "agent_state_changed",
            "speech_created",
            "conversation_item_added",
            "error",
            "metrics_collected",
            "close",
        }
        assert expected_events == set(handlers.keys())

    def test_user_input_transcribed_adds_message(self):
        """user_input_transcribed handler adds final transcripts to history."""
        session, handlers = self._capture_handlers()
        c = _make_consultation(messages=0)

        _register_event_handlers(session, c, "test-001", db_backed=True)

        # Simulate a final transcript event
        event = MagicMock()
        event.transcript = "Hello from user"
        event.is_final = True

        handlers["user_input_transcribed"](event)

        assert len(c.dialogue_history) == 1
        assert c.dialogue_history[0]["role"] == "user"
        assert c.dialogue_history[0]["content"] == "Hello from user"

    def test_user_input_transcribed_triggers_extraction(self):
        """user_input_transcribed triggers extraction at message count 6."""
        session, handlers = self._capture_handlers()
        c = _make_consultation(messages=0)

        _register_event_handlers(session, c, "test-001", db_backed=True)

        with patch("src.voice.consultant.asyncio") as mock_asyncio:
            # Send 6 final transcripts
            for i in range(6):
                event = MagicMock()
                event.transcript = f"Message {i}"
                event.is_final = True
                handlers["user_input_transcribed"](event)

            mock_asyncio.create_task.assert_called_once()

    def test_conversation_item_added_calls_handler(self):
        """conversation_item_added handler processes assistant messages."""
        session, handlers = self._capture_handlers()
        c = _make_consultation(messages=0)

        _register_event_handlers(session, c, "test-001", db_backed=True)

        # Simulate an assistant conversation item
        event = MagicMock()
        event.item = MagicMock()
        event.item.role = "assistant"
        event.item.content = "Agent response"

        handlers["conversation_item_added"](event)

        assert len(c.dialogue_history) == 1
        assert c.dialogue_history[0]["role"] == "assistant"

    def test_session_close_triggers_finalize(self):
        """close handler creates a finalization task."""
        session, handlers = self._capture_handlers()
        c = _make_consultation(messages=2)

        _register_event_handlers(session, c, "test-001", db_backed=True)

        with patch("src.voice.consultant.asyncio") as mock_asyncio:
            event = MagicMock()
            event.reason = "disconnect"
            handlers["close"](event)

            mock_asyncio.create_task.assert_called_once()


# ===========================================================================
# 13. TestGetReviewSystemPrompt (2 tests)
# ===========================================================================

class TestGetReviewSystemPrompt:
    """Tests for get_review_system_prompt()."""

    def test_review_prompt_returns_string(self):
        """get_review_system_prompt returns a string."""
        with patch("src.config.prompt_loader.render_prompt", return_value="REVIEW prompt text"):
            result = get_review_system_prompt("summary")
            assert isinstance(result, str)

    def test_review_prompt_contains_summary(self):
        """get_review_system_prompt passes anketa_summary to render_prompt."""
        with patch("src.config.prompt_loader.render_prompt") as mock_render:
            mock_render.return_value = "REVIEW with TestCorp"
            result = get_review_system_prompt("1. Компания: TestCorp")
            mock_render.assert_called_once_with(
                "voice/review", "system_prompt", anketa_summary="1. Компания: TestCorp"
            )
            assert "TestCorp" in result


# ===========================================================================
# 14. Additional edge case tests
# ===========================================================================

class TestEdgeCases:
    """Extra edge case tests for thoroughness."""

    def test_handle_conversation_item_list_with_non_strings(self):
        """List content with non-string items extracts only strings."""
        c = _make_consultation(messages=0)
        event = MagicMock()
        event.item = MagicMock()
        event.item.role = "assistant"
        # Mix strings and non-strings
        event.item.content = ["Hello", 42, "World", None]
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 1
        # Only string items should be extracted
        assert "Hello" in c.dialogue_history[0]["content"]
        assert "World" in c.dialogue_history[0]["content"]

    def test_handle_conversation_item_whitespace_only_skips(self):
        """Content that is only whitespace is skipped."""
        c = _make_consultation(messages=0)
        event = _make_event(role="assistant", content="   \n  \t  ")
        counter = [0]

        _handle_conversation_item(event, c, "test-001", True, counter, None)
        assert len(c.dialogue_history) == 0

    def test_voice_session_multiple_messages_ordering(self):
        """Messages maintain insertion order."""
        s = VoiceConsultationSession()
        s.add_message("user", "First")
        s.add_message("assistant", "Second")
        s.add_message("user", "Third")
        assert s.dialogue_history[0]["content"] == "First"
        assert s.dialogue_history[1]["content"] == "Second"
        assert s.dialogue_history[2]["content"] == "Third"

    def test_format_anketa_unknown_keys_ignored(self):
        """Keys not in the known sections list are ignored."""
        data = {
            "company_name": "TestCorp",
            "unknown_field": "should be ignored",
            "another_random": 42,
        }
        result = format_anketa_for_voice(data)
        assert "TestCorp" in result
        assert "should be ignored" not in result
        assert "42" not in result

    def test_build_resume_context_empty_content_messages_skipped(self):
        """Messages with empty content in history are skipped."""
        db = _make_db_session(
            anketa_data=None,
            dialogue_history=[
                {"role": "user", "content": ""},
                {"role": "assistant", "content": "Valid message"},
                {"role": "user", "content": ""},
            ],
        )
        result = _build_resume_context(db)
        assert "Valid message" in result
        # Empty messages should not produce "Клиент: " lines
        lines = [l for l in result.split("\n") if l.startswith("- Клиент:")]
        assert len(lines) == 0

    def test_lookup_db_session_consultation_prefix_only(self):
        """Room name 'consultation-' with empty suffix extracts empty session_id."""
        with patch("src.voice.consultant._session_mgr") as mock_mgr:
            mock_mgr.get_session.return_value = None
            sid, session = _lookup_db_session("consultation-")
            assert sid == ""
            assert session is None

    def test_init_consultation_without_db_generates_uuid(self):
        """Without DB, session_id is a new 8-char UUID."""
        c = _init_consultation("consultation-test", None)
        assert len(c.session_id) == 8

    @pytest.mark.asyncio
    async def test_finalize_consultation_zero_messages(self):
        """Finalization with 0 messages sets status to completed."""
        c = _make_consultation(messages=0)
        await finalize_consultation(c)
        assert c.status == "completed"

    def test_handle_conversation_item_no_session_id_no_extraction(self):
        """No extraction when session_id is None even with db_backed=True."""
        c = _make_consultation(messages=0)
        counter = [5]

        with patch("src.voice.consultant.asyncio") as mock_asyncio:
            event = _make_event(role="assistant", content="Response")
            _handle_conversation_item(event, c, None, True, counter, None)
            mock_asyncio.create_task.assert_not_called()

    def test_user_input_transcribed_skips_non_final(self):
        """Non-final transcripts are not added to history."""
        session, handlers = TestRegisterEventHandlers()._capture_handlers()
        c = _make_consultation(messages=0)

        _register_event_handlers(session, c, "test-001", db_backed=True)

        event = MagicMock()
        event.transcript = "partial text"
        event.is_final = False

        handlers["user_input_transcribed"](event)
        assert len(c.dialogue_history) == 0

    def test_user_input_transcribed_skips_empty_transcript(self):
        """Empty final transcripts are not added."""
        session, handlers = TestRegisterEventHandlers()._capture_handlers()
        c = _make_consultation(messages=0)

        _register_event_handlers(session, c, "test-001", db_backed=True)

        event = MagicMock()
        event.transcript = "   "
        event.is_final = True

        handlers["user_input_transcribed"](event)
        assert len(c.dialogue_history) == 0

    def test_register_handlers_without_db_no_extraction(self):
        """When db_backed=False, user input does not trigger extraction."""
        session, handlers = TestRegisterEventHandlers()._capture_handlers()
        c = _make_consultation(messages=0)

        _register_event_handlers(session, c, None, db_backed=False)

        with patch("src.voice.consultant.asyncio") as mock_asyncio:
            for i in range(10):
                event = MagicMock()
                event.transcript = f"Message {i}"
                event.is_final = True
                handlers["user_input_transcribed"](event)

            mock_asyncio.create_task.assert_not_called()

    def test_get_company_name_returns_first_match(self):
        """get_company_name returns the first message with the keyword."""
        s = VoiceConsultationSession()
        s.add_message("user", "First message without keyword")
        s.add_message("user", "Наша компания Альфа")
        s.add_message("user", "Наша компания Бета")
        result = s.get_company_name()
        assert "Альфа" in result

    def test_resume_context_anketa_empty_is_excluded(self):
        """Anketa that formats to 'empty' placeholder is excluded from resume."""
        db = _make_db_session(
            anketa_data={},  # formats to "(Анкета пока пуста)"
            dialogue_history=[{"role": "user", "content": "Hi"}],
        )
        result = _build_resume_context(db)
        # Should not contain "Собранная информация" since anketa is empty
        assert "Собранная информация" not in result
        # But should contain the history
        assert "Клиент: Hi" in result
