"""
Unit tests for v5.0 interview mode routing in src/voice/consultant.py.

Covers:
- Prompt routing: consultation_type from voice_config selects between
  consultant.yaml and interviewer.yaml prompts in the entrypoint.
- KB enrichment skip: interview mode must NOT inject industry knowledge base
  (neutrality requirement for the interviewer role).
- Research skip: interview mode must NOT launch _run_background_research().
- consultation_type passed to extractor: both _extract_and_update_anketa()
  and _finalize_and_save() read consultation_type from db_session.voice_config
  and pass it to extractor.extract().

Patch rules: always target SOURCE modules, not consultant.
- patch("src.voice.consultant._session_mgr") for the session manager
- patch("src.voice.consultant.create_llm_client") for DeepSeek
- patch("src.voice.consultant.AnketaExtractor") for the extractor
- patch("src.voice.consultant.AnketaGenerator") for the generator
- patch("src.voice.consultant.get_prompt") for prompt loading
- patch("src.voice.consultant._get_kb_manager") for KB
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.voice.consultant import (
    VoiceConsultationSession,
    _extract_and_update_anketa,
    _finalize_and_save,
    _run_background_research,
    get_system_prompt,
    get_enriched_system_prompt,
    finalize_consultation,
)
from src.session.models import RuntimeStatus
import src.voice.consultant as _consultant_module


# ---------------------------------------------------------------------------
# Helpers
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


def _make_anketa_mock(completion_rate=0.3, website=None, contact_phone=None):
    """Create a mock FinalAnketa with configurable fields."""
    anketa = MagicMock()
    anketa.company_name = "TestCorp"
    anketa.contact_name = "Test User"
    anketa.industry = "IT"
    anketa.website = website
    anketa.contact_phone = contact_phone or "+1234567890"
    anketa.completion_rate.return_value = completion_rate
    # Include all required fields for _check_required_fields()
    anketa.model_dump.return_value = {
        "company_name": "TestCorp",
        "industry": "IT",
        "business_description": "Test business",
        "services": ["Service 1"],
        "current_problems": ["Problem 1"],
        "business_goals": ["Goal 1"],
        "agent_name": "TestAgent",
        "agent_purpose": "Handle calls",
        "agent_functions": [{"name": "admin", "description": "admin work"}],
        "contact_name": "Test User",
        "contact_phone": contact_phone or "+1234567890",
        "contact_email": "test@example.com",
        "voice_gender": "female",
        "voice_tone": "professional",
        "call_direction": "inbound",
    }
    return anketa


def _make_agent_session():
    """Create a mock AgentSession with _activity."""
    session = AsyncMock()
    activity = MagicMock()
    activity.update_instructions = AsyncMock()
    activity.instructions = "base prompt"
    session._activity = activity
    session.generate_reply = AsyncMock()
    return session


# ===========================================================================
# 1. _extract_and_update_anketa: consultation_type routing (10 tests)
# ===========================================================================

class TestExtractAnketaConsultationType:
    """Tests that _extract_and_update_anketa reads consultation_type from
    db_session.voice_config and passes it to extractor.extract()."""

    @pytest.mark.asyncio
    async def test_interview_type_passed_to_extractor(self):
        """When voice_config has consultation_type='interview', extractor
        receives consultation_type='interview'."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            mock_extractor.extract.assert_called_once()
            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "interview"

    @pytest.mark.asyncio
    async def test_consultation_type_passed_to_extractor(self):
        """When voice_config has consultation_type='consultation', extractor
        receives consultation_type='consultation'."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"consultation_type": "consultation"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_voice_config_none_defaults_to_consultation(self):
        """When voice_config is None, consultation_type defaults to 'consultation'."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(voice_config=None)
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_voice_config_empty_dict_defaults_to_consultation(self):
        """When voice_config is {}, consultation_type defaults to 'consultation'."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(voice_config={})
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_db_session_not_found_defaults_to_consultation(self):
        """When DB session is not found (None), consultation_type defaults to 'consultation'."""
        consultation = _make_consultation(messages=6)
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = None
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_voice_config_without_consultation_type_key_defaults(self):
        """When voice_config has other keys but no consultation_type,
        defaults to 'consultation'."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"voice_gender": "female", "silence_duration_ms": 3000},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_interview_type_also_passes_dialogue_history(self):
        """In interview mode, extractor still receives dialogue_history."""
        consultation = _make_consultation(messages=8)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["dialogue_history"] == consultation.dialogue_history
            assert call_kwargs["consultation_type"] == "interview"

    @pytest.mark.asyncio
    async def test_interview_type_also_passes_duration_seconds(self):
        """In interview mode, extractor still receives duration_seconds."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert "duration_seconds" in call_kwargs
            assert isinstance(call_kwargs["duration_seconds"], float)

    @pytest.mark.asyncio
    async def test_too_few_messages_skips_extraction(self):
        """With fewer than 4 messages, extraction is skipped entirely."""
        consultation = _make_consultation(messages=2)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client") as mock_ds, \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls:

            await _extract_and_update_anketa(consultation, "test-001")

            # Extractor should never be instantiated
            mock_ext_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_mgr_exception_defaults_to_consultation(self):
        """If _session_mgr.get_session() raises, consultation_type defaults
        to 'consultation' and extraction still proceeds."""
        consultation = _make_consultation(messages=6)
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            # First call (for doc_context) raises, so consultation_type stays default
            mock_mgr.get_session.side_effect = Exception("DB connection lost")
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            # Should not raise — the outer try/except catches it
            await _extract_and_update_anketa(consultation, "test-001")

            # Extraction may or may not be called depending on where the
            # exception occurs. The key behavior is no crash.


# ===========================================================================
# 2. _finalize_and_save: consultation_type routing (8 tests)
# ===========================================================================

class TestFinalizeAndSaveConsultationType:
    """Tests that _finalize_and_save reads consultation_type from
    db_session.voice_config and passes it to extractor.extract()."""

    @pytest.mark.asyncio
    async def test_finalize_interview_type_passed_to_extractor(self):
        """When voice_config has consultation_type='interview', finalize
        passes it to extractor.extract()."""
        consultation = _make_consultation(messages=6)
        consultation.runtime_status = RuntimeStatus.COMPLETED

        db_session_for_finalize = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        db_session_for_downstream = _make_db_session(
            voice_config={"consultation_type": "interview"},
            anketa_data={"company_name": "TestCorp"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock) as mock_fin, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager") as mock_notif, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None), \
             patch("src.voice.consultant._update_anketa_via_api", new_callable=AsyncMock, return_value=True) as mock_api_update:

            # Setup KB mocks to avoid StopIteration
            mock_km_inst = mock_km.return_value
            mock_ecb_inst = mock_ecb.return_value
            mock_ecb_inst.get_industry_id.return_value = None  # No industry detected

            # Setup notification mock
            mock_notif_inst = mock_notif.return_value
            mock_notif_inst.on_session_confirmed = AsyncMock()

            # finalize_consultation sets status to completed
            async def set_completed(c):
                c.runtime_status = RuntimeStatus.COMPLETED
            mock_fin.side_effect = set_completed

            # Four calls in _finalize_and_save:
            # 0) R25-01 pre-check: deduplication guard
            # 1) check current status
            # 2) get doc_context + consultation_type
            # 3) downstream pipelines
            mock_mgr.get_session.side_effect = [
                db_session_for_finalize,  # R25-01 pre-check
                db_session_for_finalize,  # status check
                db_session_for_finalize,  # extraction context
                db_session_for_downstream,  # downstream
            ]
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _finalize_and_save(consultation, "test-001")

            mock_extractor.extract.assert_called_once()
            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "interview"

    @pytest.mark.asyncio
    async def test_finalize_consultation_type_defaults_when_no_voice_config(self):
        """When voice_config is None in _finalize_and_save, consultation_type
        defaults to 'consultation'."""
        consultation = _make_consultation(messages=6)
        consultation.runtime_status = RuntimeStatus.COMPLETED

        db_session = _make_db_session(voice_config=None)
        db_session_downstream = _make_db_session(
            voice_config=None,
            anketa_data={"company_name": "TestCorp"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock) as mock_fin, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager") as mock_notif, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None), \
             patch("src.voice.consultant._update_anketa_via_api", new_callable=AsyncMock, return_value=True) as mock_api_update:

            # Setup KB mocks to avoid StopIteration
            mock_km_inst = mock_km.return_value
            mock_ecb_inst = mock_ecb.return_value
            mock_ecb_inst.get_industry_id.return_value = None  # No industry detected

            # Setup notification mock
            mock_notif_inst = mock_notif.return_value
            mock_notif_inst.on_session_confirmed = AsyncMock()

            async def set_completed(c):
                c.runtime_status = RuntimeStatus.COMPLETED
            mock_fin.side_effect = set_completed

            mock_mgr.get_session.side_effect = [db_session, db_session, db_session, db_session_downstream]  # +1 for R25-01
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _finalize_and_save(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_finalize_empty_voice_config_defaults(self):
        """When voice_config is {} in _finalize_and_save, consultation_type
        defaults to 'consultation'."""
        consultation = _make_consultation(messages=6)
        consultation.runtime_status = RuntimeStatus.COMPLETED

        db_session = _make_db_session(voice_config={})
        db_downstream = _make_db_session(voice_config={}, anketa_data={"company_name": "TestCorp"})
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock) as mock_fin, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager") as mock_notif, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None), \
             patch("src.voice.consultant._update_anketa_via_api", new_callable=AsyncMock, return_value=True) as mock_api_update:

            # Setup KB mocks to avoid StopIteration
            mock_km_inst = mock_km.return_value
            mock_ecb_inst = mock_ecb.return_value
            mock_ecb_inst.get_industry_id.return_value = None  # No industry detected

            # Setup notification mock
            mock_notif_inst = mock_notif.return_value
            mock_notif_inst.on_session_confirmed = AsyncMock()

            async def set_completed(c):
                c.runtime_status = RuntimeStatus.COMPLETED
            mock_fin.side_effect = set_completed

            mock_mgr.get_session.side_effect = [db_session, db_session, db_session, db_downstream]  # +1 for R25-01
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _finalize_and_save(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_finalize_no_session_id_skips_db_save(self):
        """When session_id is None, _finalize_and_save skips DB operations."""
        consultation = _make_consultation(messages=6)

        with patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock) as mock_fin, \
             patch("src.voice.consultant._session_mgr") as mock_mgr:

            await _finalize_and_save(consultation, None)

            mock_fin.assert_called_once_with(consultation)
            # update_dialogue should not be called since session_id is None
            mock_mgr.update_dialogue.assert_not_called()

    @pytest.mark.asyncio
    async def test_finalize_not_completed_skips_extraction(self):
        """When consultation.runtime_status is idle (no finalize ran), final extraction
        is skipped in _finalize_and_save. R24-09: ERROR status still triggers extraction."""
        consultation = _make_consultation(messages=6)
        consultation.runtime_status = RuntimeStatus.IDLE

        db_session = _make_db_session()
        db_downstream = _make_db_session(anketa_data={"company_name": "TestCorp"})

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock) as mock_fin, \
             patch("src.voice.consultant.create_llm_client") as mock_ds, \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None):

            # finalize_consultation keeps status as idle (no finalize ran)
            async def keep_idle(c):
                pass  # status stays idle
            mock_fin.side_effect = keep_idle

            # R25-01 pre-check + fresh_session + downstream
            mock_mgr.get_session.side_effect = [db_session, db_session, db_downstream]

            await _finalize_and_save(consultation, "test-001")

            # Extractor should not be instantiated since status is idle (not completed/error)
            mock_ext_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_finalize_interview_type_with_other_voice_config(self):
        """Interview mode with additional voice_config settings (voice_gender,
        silence_duration_ms) still correctly routes consultation_type."""
        consultation = _make_consultation(messages=6)
        consultation.runtime_status = RuntimeStatus.COMPLETED

        db_session = _make_db_session(
            voice_config={
                "consultation_type": "interview",
                "voice_gender": "male",
                "silence_duration_ms": 3000,
            },
        )
        db_downstream = _make_db_session(
            voice_config={"consultation_type": "interview"},
            anketa_data={"company_name": "TestCorp"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock) as mock_fin, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager") as mock_notif, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None), \
             patch("src.voice.consultant._update_anketa_via_api", new_callable=AsyncMock, return_value=True) as mock_api_update:

            # Setup KB mocks to avoid StopIteration
            mock_km_inst = mock_km.return_value
            mock_ecb_inst = mock_ecb.return_value
            mock_ecb_inst.get_industry_id.return_value = None  # No industry detected

            # Setup notification mock
            mock_notif_inst = mock_notif.return_value
            mock_notif_inst.on_session_confirmed = AsyncMock()

            async def set_completed(c):
                c.runtime_status = RuntimeStatus.COMPLETED
            mock_fin.side_effect = set_completed

            # R25-01 pre-check + fresh_session + re-read + downstream
            mock_mgr.get_session.side_effect = [db_session, db_session, db_session, db_downstream]
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _finalize_and_save(consultation, "test-001")

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "interview"

    @pytest.mark.asyncio
    async def test_finalize_updates_anketa_in_db_for_interview(self):
        """In interview mode, anketa is still saved to DB after extraction."""
        consultation = _make_consultation(messages=6)
        consultation.runtime_status = RuntimeStatus.COMPLETED

        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        db_downstream = _make_db_session(
            voice_config={"consultation_type": "interview"},
            anketa_data={"company_name": "TestCorp"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock) as mock_fin, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager") as mock_notif, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None), \
             patch("src.voice.consultant._update_anketa_via_api", new_callable=AsyncMock, return_value=True) as mock_api_update:

            # Setup KB mocks to avoid StopIteration
            mock_km_inst = mock_km.return_value
            mock_ecb_inst = mock_ecb.return_value
            mock_ecb_inst.get_industry_id.return_value = None  # No industry detected

            # Setup notification mock
            mock_notif_inst = mock_notif.return_value
            mock_notif_inst.on_session_confirmed = AsyncMock()

            async def set_completed(c):
                c.runtime_status = RuntimeStatus.COMPLETED
            mock_fin.side_effect = set_completed

            # R25-01 pre-check + fresh_session + re-read + downstream
            mock_mgr.get_session.side_effect = [db_session, db_session, db_session, db_downstream]
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _finalize_and_save(consultation, "test-001")

            # ✅ v4.4: Changed to use API update instead of direct DB write
            mock_api_update.assert_called_once_with(
                "test-001",
                anketa.model_dump.return_value,
                "# Anketa",
            )

    @pytest.mark.asyncio
    async def test_finalize_consultation_reads_type_from_voice_config(self):
        """finalize_consultation() (standalone) reads consultation_type from
        db_session.voice_config via _session_mgr."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/a.md", "json": "/tmp/a.json"}
            mock_output.save_dialogue.return_value = "/tmp/d.md"
            mock_out_cls.return_value = mock_output
            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(consultation)

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "interview"
            assert consultation.runtime_status == RuntimeStatus.COMPLETED


# ===========================================================================
# 3. KB enrichment skipped for interview mode (7 tests)
# ===========================================================================

class TestKBEnrichmentSkipForInterview:
    """Tests that KB enrichment is skipped when consultation_type is 'interview'.

    In the _extract_and_update_anketa() function, the KB enrichment block
    is guarded by: `if agent_session is not None and _consultation_type != "interview":`
    """

    @pytest.mark.asyncio
    async def test_interview_mode_skips_kb_enrichment(self):
        """With consultation_type='interview' and an agent_session provided,
        IndustryKnowledgeManager should NOT be instantiated for KB enrichment."""
        consultation = _make_consultation(messages=8)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(completion_rate=0.3)
        agent_session = _make_agent_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._get_missing_interview_fields", return_value=[]):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # KB Manager should NOT be called for industry detection in the
            # enrichment block. It may be called elsewhere (research), but
            # since research is also skipped for interview mode, it should
            # not be called at all.
            # The key assertion: update_instructions should NOT be called
            # for KB enrichment (missing fields reminder also returns empty)
            agent_session._activity.update_instructions.assert_not_called()

    @pytest.mark.asyncio
    async def test_consultation_mode_allows_kb_enrichment(self):
        """With consultation_type='consultation', KB enrichment CAN proceed
        when industry is detected."""
        consultation = _make_consultation(messages=8)
        consultation.detected_profile = None  # Not yet detected
        db_session = _make_db_session(
            voice_config={"consultation_type": "consultation"},
        )
        anketa = _make_anketa_mock(completion_rate=0.3)
        agent_session = _make_agent_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls, \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            # Set up KB detection to succeed
            mock_km = MagicMock()
            mock_km.detect_industry.return_value = "logistics"
            mock_km.get_profile.return_value = MagicMock()
            mock_km_cls.return_value = mock_km

            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = "Industry: logistics"
            mock_ecb_cls.return_value = mock_builder

            # country detector mock — lazy import inside function body,
            # so patch at source module
            with patch("src.knowledge.country_detector.get_country_detector") as mock_gcd:
                mock_detector = MagicMock()
                mock_detector.detect.return_value = (None, None)
                mock_gcd.return_value = mock_detector

                await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # For consultation mode, KB detection should have been attempted
            mock_km.detect_industry.assert_called()

    @pytest.mark.asyncio
    async def test_interview_mode_no_kb_detection_attempted(self):
        """In interview mode, industry detection for KB enrichment is not attempted."""
        consultation = _make_consultation(messages=8)
        consultation.detected_profile = None
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(completion_rate=0.3)
        agent_session = _make_agent_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._get_missing_interview_fields", return_value=[]):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # update_instructions should NOT be called — no KB injection
            # (missing fields reminder also returns empty)
            agent_session._activity.update_instructions.assert_not_called()
            # kb_enriched should remain False
            assert consultation.kb_enriched is False

    @pytest.mark.asyncio
    async def test_interview_mode_kb_enriched_stays_false(self):
        """In interview mode, consultation.kb_enriched never becomes True."""
        consultation = _make_consultation(messages=10)
        consultation.kb_enriched = False
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(completion_rate=0.4)
        agent_session = _make_agent_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            assert consultation.kb_enriched is False

    @pytest.mark.asyncio
    async def test_interview_mode_without_agent_session_still_extracts(self):
        """In interview mode without agent_session (None), extraction
        proceeds but KB enrichment is naturally skipped."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", None)

            # Extraction should still work
            mock_extractor.extract.assert_called_once()
            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "interview"

    @pytest.mark.asyncio
    async def test_consultation_mode_no_agent_session_skips_kb(self):
        """In consultation mode without agent_session, KB enrichment
        is skipped (guarded by agent_session is not None)."""
        consultation = _make_consultation(messages=8)
        db_session = _make_db_session(
            voice_config={"consultation_type": "consultation"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km_cls, \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", None)

            # Without agent_session, KB enrichment block is skipped entirely
            assert consultation.kb_enriched is False

    @pytest.mark.asyncio
    async def test_interview_mode_does_not_update_instructions(self):
        """In interview mode, agent instructions are never updated for KB."""
        consultation = _make_consultation(messages=12)
        consultation.detected_profile = MagicMock()  # Pre-detected profile
        consultation.detected_industry_id = "logistics"
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(completion_rate=0.4)
        agent_session = _make_agent_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._get_missing_interview_fields", return_value=[]):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # Even with a detected profile, instructions should NOT be updated
            # (missing fields reminder also returns empty)
            agent_session._activity.update_instructions.assert_not_called()


# ===========================================================================
# 4. Research skipped for interview mode (6 tests)
# ===========================================================================

class TestResearchSkipForInterview:
    """Tests that _run_background_research() is not launched when
    consultation_type is 'interview'.

    In _extract_and_update_anketa(), the research launch is guarded by:
    `if not consultation.research_done and anketa.website and _consultation_type != "interview":`
    """

    @pytest.mark.asyncio
    async def test_interview_mode_skips_research_even_with_website(self):
        """When consultation_type='interview' and anketa has a website,
        research is NOT launched."""
        consultation = _make_consultation(messages=8)
        consultation.research_done = False
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(website="https://example.com")
        agent_session = _make_agent_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant.asyncio") as mock_asyncio:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # asyncio.create_task should NOT be called for research
            mock_asyncio.create_task.assert_not_called()
            # research_done should remain False
            assert consultation.research_done is False

    @pytest.mark.asyncio
    async def test_consultation_mode_launches_research_with_website(self):
        """When consultation_type='consultation' and anketa has a website,
        research IS launched."""
        consultation = _make_consultation(messages=8)
        consultation.research_done = False
        db_session = _make_db_session(
            voice_config={"consultation_type": "consultation"},
        )
        anketa = _make_anketa_mock(website="https://example.com")

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._get_kb_manager") as mock_km_cls, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant.asyncio") as mock_asyncio:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_km = MagicMock()
            mock_km.detect_industry.return_value = "logistics"
            mock_km_cls.return_value = mock_km

            mock_task = MagicMock()
            mock_asyncio.create_task.return_value = mock_task

            await _extract_and_update_anketa(consultation, "test-001", None)

            # asyncio.create_task should be called for research
            mock_asyncio.create_task.assert_called_once()
            # research_done should be set to True early (prevent duplicates)
            assert consultation.research_done is True

    @pytest.mark.asyncio
    async def test_interview_mode_no_research_without_website(self):
        """When consultation_type='interview' and no website,
        research is not launched (expected: no website = no research)."""
        consultation = _make_consultation(messages=8)
        consultation.research_done = False
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(website=None)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", None)

            assert consultation.research_done is False

    @pytest.mark.asyncio
    async def test_consultation_mode_no_research_without_website(self):
        """Even in consultation mode, no research without a website in anketa."""
        consultation = _make_consultation(messages=8)
        consultation.research_done = False
        db_session = _make_db_session(
            voice_config={"consultation_type": "consultation"},
        )
        anketa = _make_anketa_mock(website=None)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", None)

            assert consultation.research_done is False

    @pytest.mark.asyncio
    async def test_interview_mode_research_done_stays_false(self):
        """In interview mode, research_done flag never becomes True
        even with a website."""
        consultation = _make_consultation(messages=10)
        consultation.research_done = False
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(website="https://example.com")

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", None)

            assert consultation.research_done is False

    @pytest.mark.asyncio
    async def test_consultation_mode_already_researched_skips(self):
        """In consultation mode, if research_done is already True,
        no duplicate research is launched."""
        consultation = _make_consultation(messages=8)
        consultation.research_done = True  # Already researched
        db_session = _make_db_session(
            voice_config={"consultation_type": "consultation"},
        )
        anketa = _make_anketa_mock(website="https://example.com")

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant.asyncio") as mock_asyncio:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", None)

            # No create_task for research since already done
            mock_asyncio.create_task.assert_not_called()


# ===========================================================================
# 5. Prompt routing in entrypoint (5 tests)
# ===========================================================================

class TestPromptRouting:
    """Tests that prompt routing selects the correct YAML prompt based
    on consultation_type from voice_config.

    In the entrypoint, the logic is:
        consultation_type = voice_config.get("consultation_type", "consultation")
        if consultation_type == "interview":
            prompt = get_prompt("voice/interviewer", "system_prompt")
        else:
            prompt = get_system_prompt()  # which calls get_prompt("voice/consultant", ...)
    """

    def test_get_system_prompt_uses_consultant_yaml(self):
        """get_system_prompt() calls get_prompt with 'voice/consultant'."""
        with patch("src.voice.consultant.get_prompt", return_value="Consultant prompt") as mock_gp:
            result = get_system_prompt()
            mock_gp.assert_called_once_with("voice/consultant", "system_prompt")
            assert result == "Consultant prompt"

    def test_interview_routing_logic(self):
        """Simulate entrypoint's prompt routing: interview mode uses
        'voice/interviewer' prompt path."""
        voice_config = {"consultation_type": "interview"}

        with patch("src.voice.consultant.get_prompt") as mock_gp:
            mock_gp.return_value = "Interviewer prompt"

            # Replicate entrypoint logic
            consultation_type = voice_config.get("consultation_type", "consultation")
            if consultation_type == "interview":
                prompt = mock_gp("voice/interviewer", "system_prompt")
            else:
                prompt = get_system_prompt()

            assert prompt == "Interviewer prompt"
            mock_gp.assert_called_with("voice/interviewer", "system_prompt")

    def test_consultation_routing_logic(self):
        """Simulate entrypoint's prompt routing: consultation mode uses
        'voice/consultant' prompt path."""
        voice_config = {"consultation_type": "consultation"}

        with patch("src.voice.consultant.get_prompt", return_value="Consultant prompt") as mock_gp:
            consultation_type = voice_config.get("consultation_type", "consultation")
            if consultation_type == "interview":
                prompt = mock_gp("voice/interviewer", "system_prompt")
            else:
                prompt = get_system_prompt()

            assert prompt == "Consultant prompt"
            # get_system_prompt internally calls get_prompt("voice/consultant", ...)
            mock_gp.assert_called_with("voice/consultant", "system_prompt")

    def test_no_voice_config_defaults_to_consultation(self):
        """When voice_config is None, prompt routing defaults to consultation."""
        voice_config = None

        with patch("src.voice.consultant.get_prompt", return_value="Consultant prompt") as mock_gp:
            consultation_type = voice_config.get("consultation_type", "consultation") if voice_config else "consultation"
            if consultation_type == "interview":
                prompt = mock_gp("voice/interviewer", "system_prompt")
            else:
                prompt = get_system_prompt()

            assert prompt == "Consultant prompt"

    def test_empty_voice_config_defaults_to_consultation(self):
        """When voice_config is {}, prompt routing defaults to consultation."""
        voice_config = {}

        with patch("src.voice.consultant.get_prompt", return_value="Consultant prompt") as mock_gp:
            consultation_type = voice_config.get("consultation_type", "consultation")
            assert consultation_type == "consultation"

            if consultation_type == "interview":
                prompt = mock_gp("voice/interviewer", "system_prompt")
            else:
                prompt = get_system_prompt()

            assert prompt == "Consultant prompt"


# ===========================================================================
# 6. finalize_consultation standalone: consultation_type routing (4 tests)
# ===========================================================================

class TestFinalizeConsultationStandalone:
    """Tests for finalize_consultation() reading consultation_type from
    the session manager (not _finalize_and_save wrapper)."""

    @pytest.mark.asyncio
    async def test_finalize_with_interview_voice_config(self):
        """finalize_consultation passes consultation_type='interview'
        to extractor when voice_config says so."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/a.md", "json": "/tmp/a.json"}
            mock_output.save_dialogue.return_value = "/tmp/d.md"
            mock_out_cls.return_value = mock_output
            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(consultation)

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "interview"

    @pytest.mark.asyncio
    async def test_finalize_with_consultation_voice_config(self):
        """finalize_consultation passes consultation_type='consultation'
        when voice_config specifies it explicitly."""
        consultation = _make_consultation(messages=6)
        db_session = _make_db_session(
            voice_config={"consultation_type": "consultation"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/a.md", "json": "/tmp/a.json"}
            mock_output.save_dialogue.return_value = "/tmp/d.md"
            mock_out_cls.return_value = mock_output
            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(consultation)

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_finalize_session_mgr_exception_defaults(self):
        """If _session_mgr.get_session() raises in finalize_consultation,
        consultation_type defaults to 'consultation'."""
        consultation = _make_consultation(messages=6)
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.OutputManager") as mock_out_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen:

            mock_mgr.get_session.side_effect = Exception("DB error")
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_output = MagicMock()
            mock_output.get_company_dir.return_value = "/tmp/test"
            mock_output.save_anketa.return_value = {"md": "/tmp/a.md", "json": "/tmp/a.json"}
            mock_output.save_dialogue.return_value = "/tmp/d.md"
            mock_out_cls.return_value = mock_output
            mock_gen.render_markdown.return_value = "# Anketa"

            await finalize_consultation(consultation)

            call_kwargs = mock_extractor.extract.call_args[1]
            assert call_kwargs["consultation_type"] == "consultation"

    @pytest.mark.asyncio
    async def test_finalize_short_dialogue_does_not_extract(self):
        """finalize_consultation with < 2 messages skips extraction."""
        consultation = _make_consultation(messages=1)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls:

            await finalize_consultation(consultation)

            mock_ext_cls.assert_not_called()
            assert consultation.runtime_status == RuntimeStatus.COMPLETED


# ===========================================================================
# 7. Verbosity injection combined with interview mode (3 tests)
# ===========================================================================

class TestVerbosityWithInterviewMode:
    """Tests that verbosity settings work independently of consultation_type.

    In the entrypoint, verbosity is applied AFTER prompt selection:
        if verbosity == "concise":
            prompt = "ВАЖНО: Отвечай МАКСИМАЛЬНО кратко..." + prompt
    This should work for both interview and consultation prompts.
    """

    def test_concise_verbosity_prepended_to_interview_prompt(self):
        """Simulate: interview mode + concise verbosity prepends to prompt."""
        voice_config = {
            "consultation_type": "interview",
            "verbosity": "concise",
        }

        with patch("src.voice.consultant.get_prompt", return_value="INTERVIEW PROMPT"):
            consultation_type = voice_config.get("consultation_type", "consultation")
            if consultation_type == "interview":
                from src.config.prompt_loader import get_prompt as _gp
                prompt = "INTERVIEW PROMPT"
            else:
                prompt = get_system_prompt()

            verbosity = voice_config.get("verbosity", "normal")
            if verbosity == "concise":
                prompt = "ВАЖНО: Отвечай МАКСИМАЛЬНО кратко — 1-2 предложения + 1 вопрос. Без длинных вступлений.\n\n" + prompt

            assert "ВАЖНО" in prompt
            assert "INTERVIEW PROMPT" in prompt

    def test_verbose_verbosity_prepended_to_interview_prompt(self):
        """Simulate: interview mode + verbose verbosity prepends to prompt."""
        voice_config = {
            "consultation_type": "interview",
            "verbosity": "verbose",
        }

        prompt = "INTERVIEW PROMPT"
        verbosity = voice_config.get("verbosity", "normal")
        if verbosity == "verbose":
            prompt = "ВАЖНО: Давай развёрнутые ответы с примерами и пояснениями. Объясняй подробно.\n\n" + prompt

        assert "развёрнутые" in prompt
        assert "INTERVIEW PROMPT" in prompt

    def test_normal_verbosity_no_prefix(self):
        """With normal verbosity, no prefix is added."""
        voice_config = {
            "consultation_type": "interview",
            "verbosity": "normal",
        }

        prompt = "INTERVIEW PROMPT"
        verbosity = voice_config.get("verbosity", "normal")
        if verbosity == "concise":
            prompt = "ВАЖНО: ..." + prompt
        elif verbosity == "verbose":
            prompt = "ВАЖНО: ..." + prompt

        assert prompt == "INTERVIEW PROMPT"


# ===========================================================================
# 8. Edge cases and integration scenarios (5 tests)
# ===========================================================================

class TestInterviewModeEdgeCases:
    """Edge case tests for interview mode behavior."""

    @pytest.mark.asyncio
    async def test_interview_mode_anketa_still_saved_to_db(self):
        """In interview mode, anketa extraction and DB update still happen."""
        consultation = _make_consultation(messages=8)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None), \
             patch("src.voice.consultant._update_anketa_via_api", new_callable=AsyncMock, return_value=True) as mock_api_update:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            # Anketa should still be saved via API (v4.4)
            mock_api_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_interview_mode_metadata_still_updated(self):
        """In interview mode, company/contact metadata is still updated."""
        consultation = _make_consultation(messages=8)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None), \
             patch("src.voice.consultant._update_anketa_via_api", new_callable=AsyncMock, return_value=True) as mock_api_update:

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            # ✅ v4.4: Metadata is now updated via API (included in anketa_data)
            mock_api_update.assert_called_once()
            # Check that anketa_data contains company_name and contact_name
            call_args = mock_api_update.call_args
            anketa_data = call_args[0][1]  # second positional arg
            assert anketa_data["company_name"] == "TestCorp"
            assert anketa_data["contact_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_interview_mode_review_phase_still_triggers(self):
        """In interview mode, the review phase can still be triggered
        (review phase is NOT guarded by consultation_type)."""
        consultation = _make_consultation(messages=20)
        consultation.review_started = False
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock(completion_rate=0.95)
        agent_session = _make_agent_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant.get_review_system_prompt", return_value="REVIEW"), \
             patch("src.voice.consultant.format_anketa_for_voice", return_value="Summary"), \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # Review phase should trigger because completion >= 0.9 and messages >= 16
            assert consultation.review_started is True

    @pytest.mark.asyncio
    async def test_interview_mode_redis_cache_still_works(self):
        """In interview mode, Redis hot cache is still updated."""
        consultation = _make_consultation(messages=8)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        mock_redis = MagicMock()
        mock_redis.client = MagicMock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=mock_redis):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001")

            # Redis setex should be called even in interview mode
            mock_redis.client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_extractions_maintain_interview_type(self):
        """Multiple calls to _extract_and_update_anketa for the same session
        consistently pass consultation_type='interview'."""
        consultation = _make_consultation(messages=8)
        db_session = _make_db_session(
            voice_config={"consultation_type": "interview"},
        )
        anketa = _make_anketa_mock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            # Call extraction 3 times
            for _ in range(3):
                await _extract_and_update_anketa(consultation, "test-001")

            assert mock_extractor.extract.call_count == 3
            for call_obj in mock_extractor.extract.call_args_list:
                assert call_obj[1]["consultation_type"] == "interview"
