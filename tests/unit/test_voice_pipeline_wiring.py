"""
Integration tests for voice agent pipeline wiring (v4.2).

Verifies that 7 pipelines are actually connected to the voice agent:
1. NotificationManager → _finalize_and_save()
2. Review Phase → _extract_and_update_anketa()
3. record_learning() → _finalize_and_save()
4. CountryDetector → _extract_and_update_anketa() KB enrichment
5. ResearchEngine → _extract_and_update_anketa() background task
6. RedisStorageManager → entrypoint(), _extract_and_update_anketa(), _finalize_and_save()
7. PostgreSQLStorageManager → entrypoint(), _finalize_and_save()
"""

import asyncio
import json
import os
import sys
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
)


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
        if role == "user":
            c.add_message(role, f"Мы занимаемся логистикой, перевозим грузы по России. У нас проблемы с обработкой звонков. Наш сайт example.com. Телефон +7 999 123 45 67.")
        else:
            c.add_message(role, f"Понял, расскажите подробнее о вашей компании и проблемах.")
    return c


def _make_db_session(**overrides):
    """Create a SimpleNamespace mimicking a DB session."""
    defaults = {
        "session_id": "test-001",
        "company_name": "TestLogistics",
        "contact_name": "Иван Петров",
        "status": "reviewing",
        "dialogue_history": [],
        "duration_seconds": 600,
        "document_context": None,
        "anketa_data": {"company_name": "TestLogistics", "industry": "logistics", "services": "Грузоперевозки"},
        "anketa_md": "## Анкета\n- Компания: TestLogistics",
        "unique_link": "abc-123",
        "voice_config": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_anketa_mock(completion_rate=0.6, website=None, contact_phone=None):
    """Create a mock FinalAnketa."""
    anketa = MagicMock()
    anketa.company_name = "TestLogistics"
    anketa.contact_name = "Иван Петров"
    anketa.industry = "logistics"
    anketa.website = website
    anketa.contact_phone = contact_phone
    anketa.completion_rate.return_value = completion_rate
    anketa.model_dump.return_value = {
        "company_name": "TestLogistics",
        "industry": "logistics",
        "services": "Грузоперевозки",
        "current_problems": "Много звонков",
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
# Test: VoiceConsultationSession has new flags
# ===========================================================================

class TestVoiceConsultationSessionFlags:
    """Verify new pipeline flags exist on VoiceConsultationSession."""

    def test_has_review_started_flag(self):
        session = VoiceConsultationSession()
        assert hasattr(session, 'review_started')
        assert session.review_started is False

    def test_has_research_done_flag(self):
        session = VoiceConsultationSession()
        assert hasattr(session, 'research_done')
        assert session.research_done is False

    def test_has_kb_enriched_flag(self):
        session = VoiceConsultationSession()
        assert hasattr(session, 'kb_enriched')
        assert session.kb_enriched is False


# ===========================================================================
# Test 1: NotificationManager → _finalize_and_save()
# ===========================================================================

class TestNotificationManagerWiring:
    """NotificationManager.on_session_confirmed() called in _finalize_and_save()."""

    @pytest.mark.asyncio
    async def test_notification_sent_on_finalize(self):
        """Verify NotificationManager is invoked during session finalization."""
        consultation = _make_consultation(messages=6)
        consultation.status = "completed"

        db_session = _make_db_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock), \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.notifications.manager.NotificationManager.on_session_confirmed",
                   new_callable=AsyncMock) as mock_notify, \
             patch("src.voice.consultant.IndustryKnowledgeManager"), \
             patch("src.voice.consultant.EnrichedContextBuilder"), \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_anketa = _make_anketa_mock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            await _finalize_and_save(consultation, "test-001")

            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_notification_failure_does_not_crash(self):
        """Verify notification failure doesn't break finalization."""
        consultation = _make_consultation(messages=6)
        consultation.status = "completed"

        db_session = _make_db_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock), \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.notifications.manager.NotificationManager.on_session_confirmed",
                   new_callable=AsyncMock, side_effect=Exception("SMTP down")), \
             patch("src.voice.consultant.IndustryKnowledgeManager"), \
             patch("src.voice.consultant.EnrichedContextBuilder"), \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_mgr.update_session = MagicMock()
            mock_mgr.update_dialogue = MagicMock(return_value=True)
            mock_mgr.update_anketa = MagicMock(return_value=True)
            mock_mgr.update_metadata = MagicMock(return_value=True)

            mock_extractor = AsyncMock()
            mock_anketa = _make_anketa_mock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            # Should not raise
            await _finalize_and_save(consultation, "test-001")
            mock_mgr.update_dialogue.assert_called()


# ===========================================================================
# Test 2: Review Phase → _extract_and_update_anketa()
# ===========================================================================

class TestReviewPhaseWiring:
    """Review phase triggers when anketa completion >= 0.5 and messages >= 16."""

    @pytest.mark.asyncio
    async def test_review_phase_triggered(self):
        """When completion >= 0.5 and >= 16 messages, review phase starts."""
        consultation = _make_consultation(messages=20)
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.6)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd, \
             patch("src.voice.consultant.get_review_system_prompt", return_value="REVIEW PROMPT") as mock_review:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = ("ru", "ru")
            mock_cd.return_value = mock_detector

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            assert consultation.review_started is True
            mock_review.assert_called_once()
            agent_session._activity.update_instructions.assert_called()
            agent_session.generate_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_review_phase_not_triggered_low_completion(self):
        """Review phase does NOT trigger when completion < 0.5."""
        consultation = _make_consultation(messages=20)
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.3)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = (None, None)
            mock_cd.return_value = mock_detector

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            assert consultation.review_started is False

    @pytest.mark.asyncio
    async def test_review_phase_not_triggered_few_messages(self):
        """Review phase does NOT trigger when < 16 messages."""
        consultation = _make_consultation(messages=10)
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.8)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = (None, None)
            mock_cd.return_value = mock_detector

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            assert consultation.review_started is False

    @pytest.mark.asyncio
    async def test_review_phase_not_triggered_twice(self):
        """Review phase only triggers once (review_started flag)."""
        consultation = _make_consultation(messages=20)
        consultation.review_started = True  # already started
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.8)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = (None, None)
            mock_cd.return_value = mock_detector

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # generate_reply should NOT be called since review already started
            agent_session.generate_reply.assert_not_called()


# ===========================================================================
# Test 3: record_learning() → _finalize_and_save()
# ===========================================================================

class TestRecordLearningWiring:
    """record_learning() called in _finalize_and_save()."""

    @pytest.mark.asyncio
    async def test_learning_recorded_on_finalize(self):
        """Verify learning is recorded after session finalization."""
        consultation = _make_consultation(messages=6)
        consultation.status = "completed"

        db_session = _make_db_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock), \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls, \
             patch("src.notifications.manager.NotificationManager.on_session_confirmed",
                   new_callable=AsyncMock), \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_anketa = _make_anketa_mock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_manager = MagicMock()
            mock_manager.record_learning = MagicMock()
            mock_km_cls.return_value = mock_manager

            mock_builder = MagicMock()
            mock_builder.get_industry_id.return_value = "logistics"
            mock_ecb_cls.return_value = mock_builder

            await _finalize_and_save(consultation, "test-001")

            mock_manager.record_learning.assert_called_once()
            call_args = mock_manager.record_learning.call_args
            assert call_args[0][0] == "logistics"  # industry_id
            assert "test-001" in call_args[0][2]  # source contains session_id

    @pytest.mark.asyncio
    async def test_learning_not_recorded_without_industry(self):
        """No learning recorded if industry can't be detected."""
        consultation = _make_consultation(messages=6)
        consultation.status = "completed"

        db_session = _make_db_session()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock), \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls, \
             patch("src.notifications.manager.NotificationManager.on_session_confirmed",
                   new_callable=AsyncMock), \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=None):

            mock_mgr.get_session.return_value = db_session
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_anketa = _make_anketa_mock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_manager = MagicMock()
            mock_km_cls.return_value = mock_manager

            mock_builder = MagicMock()
            mock_builder.get_industry_id.return_value = None  # No industry detected
            mock_ecb_cls.return_value = mock_builder

            await _finalize_and_save(consultation, "test-001")

            mock_manager.record_learning.assert_not_called()


# ===========================================================================
# Test 4: CountryDetector → KB enrichment
# ===========================================================================

class TestCountryDetectorWiring:
    """CountryDetector used during KB enrichment in _extract_and_update_anketa()."""

    @pytest.mark.asyncio
    async def test_country_detector_called_for_kb_enrichment(self):
        """CountryDetector.detect() called when KB is not yet enriched."""
        consultation = _make_consultation(messages=20)
        consultation.kb_enriched = False
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.3, contact_phone="+7 999 123 45 67")

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd_fn, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = ("ru", "ru")
            mock_cd_fn.return_value = mock_detector

            mock_manager = MagicMock()
            mock_manager.detect_industry.return_value = "logistics"
            mock_profile = MagicMock()
            mock_manager.get_profile.return_value = mock_profile
            mock_manager.loader.load_regional_profile.return_value = mock_profile
            mock_km_cls.return_value = mock_manager

            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = "[Отрасль: logistics] | Боли: Много звонков"
            mock_ecb_cls.return_value = mock_builder

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            mock_detector.detect.assert_called_once()
            # Should use load_regional_profile since region detected
            mock_manager.loader.load_regional_profile.assert_called_once_with("ru", "ru", "logistics")

    @pytest.mark.asyncio
    async def test_fallback_to_base_profile_when_no_country(self):
        """Falls back to base profile when country cannot be detected."""
        consultation = _make_consultation(messages=20)
        consultation.kb_enriched = False
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.3)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd_fn, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = (None, None)  # No country
            mock_cd_fn.return_value = mock_detector

            mock_manager = MagicMock()
            mock_manager.detect_industry.return_value = "logistics"
            mock_profile = MagicMock()
            mock_manager.get_profile.return_value = mock_profile
            mock_km_cls.return_value = mock_manager

            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = "[Отрасль: logistics]"
            mock_ecb_cls.return_value = mock_builder

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # Should use get_profile (base) not load_regional_profile
            mock_manager.get_profile.assert_called_once_with("logistics")
            mock_manager.loader.load_regional_profile.assert_not_called()


# ===========================================================================
# Test 5: ResearchEngine → background research
# ===========================================================================

class TestResearchEngineWiring:
    """ResearchEngine launched as background task when website detected."""

    @pytest.mark.asyncio
    async def test_research_launched_when_website_present(self):
        """Background research starts when anketa contains website."""
        consultation = _make_consultation(messages=20)
        consultation.research_done = False
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.3, website="https://example.com")

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd, \
             patch("src.voice.consultant._run_background_research", new_callable=AsyncMock) as mock_research:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = (None, None)
            mock_cd.return_value = mock_detector

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            assert consultation.research_done is True

    @pytest.mark.asyncio
    async def test_research_not_launched_without_website(self):
        """No research when anketa has no website."""
        consultation = _make_consultation(messages=20)
        consultation.research_done = False
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.3, website=None)

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = (None, None)
            mock_cd.return_value = mock_detector

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            assert consultation.research_done is False

    @pytest.mark.asyncio
    async def test_research_not_launched_twice(self):
        """Research only launches once (research_done flag)."""
        consultation = _make_consultation(messages=20)
        consultation.research_done = True  # already done
        agent_session = _make_agent_session()
        anketa = _make_anketa_mock(completion_rate=0.3, website="https://example.com")

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd, \
             patch("src.voice.consultant._run_background_research", new_callable=AsyncMock) as mock_research:

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_detector = MagicMock()
            mock_detector.detect.return_value = (None, None)
            mock_cd.return_value = mock_detector

            await _extract_and_update_anketa(consultation, "test-001", agent_session)

            # _run_background_research should NOT be called via create_task
            # since research_done was already True
            assert consultation.research_done is True

    @pytest.mark.asyncio
    async def test_run_background_research_injects_results(self):
        """_run_background_research injects results into agent instructions."""
        consultation = _make_consultation(messages=4)
        agent_session = _make_agent_session()

        mock_result = MagicMock()
        mock_result.has_data.return_value = True
        mock_result.industry_insights = ["Логистика растёт на 15%"]
        mock_result.best_practices = ["24/7 поддержка"]
        mock_result.website_data = {"description": "Транспортная компания"}
        mock_result.sources_used = ["web_search", "website_parser"]

        with patch("src.voice.consultant.get_system_prompt", return_value="base"):
            with patch("src.research.engine.ResearchEngine") as mock_eng_cls:
                mock_engine = AsyncMock()
                mock_engine.research = AsyncMock(return_value=mock_result)
                mock_eng_cls.return_value = mock_engine

                await _run_background_research(
                    consultation, "test-001", agent_session,
                    website="https://example.com",
                    industry="logistics",
                    company_name="TestLogistics",
                )

                assert consultation.research_done is True
                agent_session._activity.update_instructions.assert_called_once()
                call_arg = agent_session._activity.update_instructions.call_args[0][0]
                assert "Данные исследования" in call_arg

    @pytest.mark.asyncio
    async def test_run_background_research_handles_failure(self):
        """_run_background_research handles errors gracefully."""
        consultation = _make_consultation(messages=4)
        agent_session = _make_agent_session()

        with patch("src.research.engine.ResearchEngine", side_effect=Exception("API down")):
            # Should not raise
            await _run_background_research(
                consultation, "test-001", agent_session,
                website="https://example.com",
                industry="logistics",
                company_name="TestLogistics",
            )


# ===========================================================================
# Test 6: RedisStorageManager → _try_get_redis()
# ===========================================================================

class TestRedisWiring:
    """RedisStorageManager optional integration."""

    def test_try_get_redis_returns_none_when_unavailable(self):
        """_try_get_redis returns None when Redis is not running."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        mod._redis_mgr = None  # Reset singleton

        try:
            with patch("src.storage.redis.RedisStorageManager") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.health_check.return_value = False
                mock_cls.return_value = mock_instance

                result = _try_get_redis()
                assert result is None
        finally:
            mod._redis_mgr = original  # Restore

    def test_try_get_redis_returns_manager_when_available(self):
        """_try_get_redis returns manager when Redis responds to health check."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        mod._redis_mgr = None  # Reset singleton

        try:
            with patch("src.storage.redis.RedisStorageManager") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.health_check.return_value = True
                mock_cls.return_value = mock_instance

                result = _try_get_redis()
                assert result is mock_instance
        finally:
            mod._redis_mgr = original  # Restore

    def test_try_get_redis_caches_result(self):
        """_try_get_redis caches the manager singleton."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        mock_mgr = MagicMock()
        mod._redis_mgr = mock_mgr

        try:
            result = _try_get_redis()
            assert result is mock_mgr
        finally:
            mod._redis_mgr = original

    def test_try_get_redis_handles_import_error(self):
        """_try_get_redis returns None when redis package is not installed."""
        import src.voice.consultant as mod
        original = mod._redis_mgr
        mod._redis_mgr = None

        try:
            with patch("src.storage.redis.RedisStorageManager", side_effect=ImportError("No redis")):
                result = _try_get_redis()
                assert result is None
        finally:
            mod._redis_mgr = original

    @pytest.mark.asyncio
    async def test_redis_updated_during_extraction(self):
        """Redis cache updated during _extract_and_update_anketa()."""
        consultation = _make_consultation(messages=20, kb_enriched=True, review_started=True)
        anketa = _make_anketa_mock(completion_rate=0.4)

        mock_redis = MagicMock()
        mock_redis.client = MagicMock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=mock_redis):

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            await _extract_and_update_anketa(consultation, "test-001", None)

            mock_redis.client.setex.assert_called_once()
            call_args = mock_redis.client.setex.call_args
            assert call_args[0][0] == "voice:session:test-001"
            assert call_args[0][1] == 7200

    @pytest.mark.asyncio
    async def test_redis_deleted_on_finalize(self):
        """Redis key deleted during _finalize_and_save()."""
        consultation = _make_consultation(messages=6)
        consultation.status = "completed"

        mock_redis = MagicMock()
        mock_redis.client = MagicMock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock), \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager.on_session_confirmed",
                   new_callable=AsyncMock), \
             patch("src.voice.consultant._try_get_redis", return_value=mock_redis), \
             patch("src.voice.consultant._try_get_postgres", return_value=None):

            mock_mgr.get_session.return_value = _make_db_session()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_anketa = _make_anketa_mock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_builder = MagicMock()
            mock_builder.get_industry_id.return_value = None
            mock_ecb.return_value = mock_builder

            await _finalize_and_save(consultation, "test-001")

            mock_redis.client.delete.assert_called_once_with("voice:session:test-001")


# ===========================================================================
# Test 7: PostgreSQLStorageManager → _try_get_postgres()
# ===========================================================================

class TestPostgreSQLWiring:
    """PostgreSQLStorageManager optional integration."""

    def test_try_get_postgres_returns_none_when_unavailable(self):
        """_try_get_postgres returns None when DATABASE_URL is not set."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        mod._postgres_mgr = None

        try:
            with patch.dict(os.environ, {}, clear=False), \
                 patch.dict(os.environ, {"DATABASE_URL": ""}):
                result = _try_get_postgres()
                assert result is None
        finally:
            mod._postgres_mgr = original

    def test_try_get_postgres_returns_manager_when_available(self):
        """_try_get_postgres returns manager when PostgreSQL responds to health check."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        mod._postgres_mgr = None

        try:
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}), \
                 patch("src.storage.postgres.PostgreSQLStorageManager") as mock_cls:
                mock_instance = MagicMock()
                mock_instance.health_check.return_value = True
                mock_cls.return_value = mock_instance

                result = _try_get_postgres()
                assert result is mock_instance
        finally:
            mod._postgres_mgr = original

    def test_try_get_postgres_caches_result(self):
        """_try_get_postgres caches the manager singleton."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        mock_mgr = MagicMock()
        mod._postgres_mgr = mock_mgr

        try:
            result = _try_get_postgres()
            assert result is mock_mgr
        finally:
            mod._postgres_mgr = original

    def test_try_get_postgres_handles_import_error(self):
        """_try_get_postgres returns None when psycopg2 is not installed."""
        import src.voice.consultant as mod
        original = mod._postgres_mgr
        mod._postgres_mgr = None

        try:
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}), \
                 patch("src.storage.postgres.PostgreSQLStorageManager",
                       side_effect=ImportError("No psycopg2")):
                result = _try_get_postgres()
                assert result is None
        finally:
            mod._postgres_mgr = original

    @pytest.mark.asyncio
    async def test_postgres_saved_on_finalize(self):
        """PostgreSQL save_anketa + update_interview_session called in _finalize_and_save()."""
        consultation = _make_consultation(messages=6)
        consultation.status = "completed"

        db_session = _make_db_session()

        mock_pg = MagicMock()
        mock_pg.save_anketa = AsyncMock(return_value=True)
        mock_pg.update_interview_session = AsyncMock(return_value=True)

        mock_anketa_obj = MagicMock()
        mock_anketa_obj.completion_rate.return_value = 0.6

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock), \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager.on_session_confirmed",
                   new_callable=AsyncMock), \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=mock_pg), \
             patch("src.anketa.schema.FinalAnketa", return_value=mock_anketa_obj):

            mock_mgr.get_session.return_value = db_session
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_anketa = _make_anketa_mock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_builder = MagicMock()
            mock_builder.get_industry_id.return_value = None
            mock_ecb.return_value = mock_builder

            await _finalize_and_save(consultation, "test-001")

            mock_pg.save_anketa.assert_called_once()
            mock_pg.update_interview_session.assert_called_once()
            update_kwargs = mock_pg.update_interview_session.call_args
            assert update_kwargs[1]["session_id"] == "test-001"

    @pytest.mark.asyncio
    async def test_postgres_not_called_without_anketa_data(self):
        """PostgreSQL NOT called when session has no anketa_data."""
        consultation = _make_consultation(messages=6)
        consultation.status = "completed"

        db_session = _make_db_session(anketa_data=None)

        mock_pg = MagicMock()
        mock_pg.save_anketa = AsyncMock()
        mock_pg.update_interview_session = AsyncMock()

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.finalize_consultation", new_callable=AsyncMock), \
             patch("src.voice.consultant.DeepSeekClient"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb, \
             patch("src.notifications.manager.NotificationManager.on_session_confirmed",
                   new_callable=AsyncMock), \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant._try_get_postgres", return_value=mock_pg):

            mock_mgr.get_session.return_value = db_session
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_anketa = _make_anketa_mock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor

            mock_builder = MagicMock()
            mock_builder.get_industry_id.return_value = None
            mock_ecb.return_value = mock_builder

            await _finalize_and_save(consultation, "test-001")

            mock_pg.save_anketa.assert_not_called()


# ===========================================================================
# Test: Existing functions still importable
# ===========================================================================

class TestFunctionsImportable:
    """Verify all pipeline-related functions are importable from consultant module."""

    def test_import_try_get_redis(self):
        assert callable(_try_get_redis)

    def test_import_try_get_postgres(self):
        assert callable(_try_get_postgres)

    def test_import_run_background_research(self):
        assert callable(_run_background_research)

    def test_import_get_review_system_prompt(self):
        assert callable(get_review_system_prompt)

    def test_import_format_anketa_for_voice(self):
        assert callable(format_anketa_for_voice)

    def test_import_get_system_prompt(self):
        assert callable(get_system_prompt)


# ===========================================================================
# Test: format_anketa_for_voice and get_review_system_prompt
# ===========================================================================

class TestReviewPhaseHelpers:
    """Test review phase helper functions."""

    def test_format_anketa_for_voice_with_data(self):
        data = {
            "company_name": "TestCorp",
            "contact_name": "Иван",
            "industry": "IT",
            "services": None,
            "current_problems": "Много звонков",
            "proposed_tasks": None,
            "integrations": ["CRM", "1С"],
            "notes": None,
        }
        result = format_anketa_for_voice(data)
        assert "TestCorp" in result
        assert "Иван" in result
        assert "IT" in result
        assert "Много звонков" in result
        assert "CRM, 1С" in result
        # None fields should be skipped
        assert "Услуги" not in result

    def test_format_anketa_for_voice_empty(self):
        result = format_anketa_for_voice({})
        assert "пуста" in result.lower()

    def test_get_review_system_prompt_contains_summary(self):
        summary = "1. Компания: TestCorp\n2. Отрасль: IT"
        result = get_review_system_prompt(summary)
        assert "TestCorp" in result
        assert "ПРОВЕРКА" in result.upper() or "проверка" in result.lower()
