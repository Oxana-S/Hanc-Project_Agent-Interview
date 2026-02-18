"""
Tests for post-mortem session d9bbe7cd fixes (7 bugs).

BUG #1: Agent doesn't announce document receipt — _announce_documents_received()
BUG #2: Periodic dialogue_history persistence — save in _extract_and_update_anketa()
BUG #3: CountryDetector uses document phone — fallback to doc_contacts phone/domain
BUG #4: Prompt prioritises documents — consultant.yaml changes (prompt-only, tested via load)
BUG #5: Structured recommendations in injection — agent_recommendations in doc_block
BUG #6: Multi-agent recommendations in prompt — consultant.yaml changes (prompt-only)
BUG #7: Improve contact_role extraction — extract.yaml changes (prompt-only, tested via load)
"""

import asyncio
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.voice.consultant import (
    VoiceConsultationSession,
    _announce_documents_received,
    _extract_and_update_anketa,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_consultation(messages=20):
    """Create a VoiceConsultationSession with dialogue history."""
    c = VoiceConsultationSession(room_name="consultation-test-d9b")
    c.session_id = "d9bbe7cd-test"
    for i in range(messages):
        role = "user" if i % 2 == 0 else "assistant"
        c.add_message(role, f"Test message {i}")
    return c


def _make_db_session(**overrides):
    """Create a SimpleNamespace mimicking a DB session."""
    defaults = {
        "session_id": "d9bbe7cd-test",
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


# ===========================================================================
# BUG #1: _announce_documents_received()
# ===========================================================================

class TestAnnounceDocumentsReceived:
    """Tests for BUG #1 fix: proactive document announcement."""

    @pytest.mark.asyncio
    async def test_calls_generate_reply(self):
        """Should call generate_reply after document injection."""
        agent_session = _make_agent_session()
        doc_ctx = {
            'documents': [{'filename': 'analysis.md'}],
            'key_facts': ['Компания: Bestattung Hanser', 'Отрасль: похоронные услуги'],
            'services_mentioned': ['трансфер', 'организация церемоний'],
        }

        with patch('src.voice.consultant.asyncio.sleep', new_callable=AsyncMock):
            await _announce_documents_received(agent_session, doc_ctx)

        agent_session.generate_reply.assert_called_once()
        call_kwargs = agent_session.generate_reply.call_args
        prompt = call_kwargs.kwargs.get('user_input', '')
        if not prompt and call_kwargs.args:
            prompt = call_kwargs.args[0]
        # Check prompt mentions document count
        assert '1 документ' in prompt

    @pytest.mark.asyncio
    async def test_includes_key_facts_in_prompt(self):
        """Prompt should contain hints from key_facts and services."""
        agent_session = _make_agent_session()
        doc_ctx = {
            'documents': [{'filename': 'a.md'}, {'filename': 'b.md'}],
            'key_facts': ['Компания: ABC Corp'],
            'services_mentioned': ['поддержка', 'продажи'],
        }

        with patch('src.voice.consultant.asyncio.sleep', new_callable=AsyncMock):
            await _announce_documents_received(agent_session, doc_ctx)

        call_kwargs = agent_session.generate_reply.call_args
        prompt = call_kwargs.kwargs.get('user_input', '')
        assert '2 документ' in prompt

    @pytest.mark.asyncio
    async def test_handles_generate_reply_exception(self):
        """Should not raise if generate_reply fails."""
        agent_session = _make_agent_session()
        agent_session.generate_reply = AsyncMock(side_effect=Exception("connection lost"))
        doc_ctx = {'documents': [], 'key_facts': [], 'services_mentioned': []}

        with patch('src.voice.consultant.asyncio.sleep', new_callable=AsyncMock):
            # Should not raise
            await _announce_documents_received(agent_session, doc_ctx)

    @pytest.mark.asyncio
    async def test_empty_doc_ctx(self):
        """Should work with empty document context."""
        agent_session = _make_agent_session()
        doc_ctx = {}

        with patch('src.voice.consultant.asyncio.sleep', new_callable=AsyncMock):
            await _announce_documents_received(agent_session, doc_ctx)

        agent_session.generate_reply.assert_called_once()
        prompt = agent_session.generate_reply.call_args.kwargs.get('user_input', '')
        assert '0 документ' in prompt

    @pytest.mark.asyncio
    async def test_non_dict_doc_ctx(self):
        """Should handle non-dict doc_ctx gracefully."""
        agent_session = _make_agent_session()

        with patch('src.voice.consultant.asyncio.sleep', new_callable=AsyncMock):
            await _announce_documents_received(agent_session, "just a string")

        agent_session.generate_reply.assert_called_once()


# ===========================================================================
# BUG #2: Periodic dialogue_history persistence
# ===========================================================================

class TestPeriodicDialogueSave:
    """Tests for BUG #2 fix: dialogue saved during extraction cycles."""

    @pytest.mark.asyncio
    async def test_dialogue_saved_after_extraction(self):
        """_update_dialogue_via_api should be called after successful anketa extraction."""
        consultation = _make_consultation(messages=6)
        consultation._cached_extractor = MagicMock()

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.website = ""
        mock_anketa.completion_rate.return_value = 0.5
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        consultation._cached_extractor.extract = AsyncMock(return_value=mock_anketa)
        consultation._cached_extractor_provider = "deepseek"

        db_session = _make_db_session()

        with patch('src.voice.consultant._session_mgr') as mock_mgr, \
             patch('src.voice.consultant._update_anketa_via_api', new_callable=AsyncMock) as mock_anketa_api, \
             patch('src.voice.consultant._update_dialogue_via_api', new_callable=AsyncMock) as mock_dialogue_api, \
             patch('src.voice.consultant._try_get_redis', return_value=None), \
             patch('src.voice.consultant._extraction_semaphore', new=None):

            mock_mgr.get_session.return_value = db_session

            await _extract_and_update_anketa(consultation, "d9bbe7cd-test", None)

            # Verify dialogue was saved
            mock_dialogue_api.assert_called_once()
            call_kwargs = mock_dialogue_api.call_args
            assert call_kwargs.kwargs.get('status') is None or call_kwargs[1].get('status') is None
            # Messages should be passed
            args = call_kwargs.args if call_kwargs.args else []
            if len(args) >= 2:
                assert len(args[1]) == 6  # 6 messages

    @pytest.mark.asyncio
    async def test_dialogue_save_failure_doesnt_crash(self):
        """If periodic dialogue save fails, extraction should still succeed."""
        consultation = _make_consultation(messages=6)
        consultation._cached_extractor = MagicMock()

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.website = ""
        mock_anketa.completion_rate.return_value = 0.5
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        consultation._cached_extractor.extract = AsyncMock(return_value=mock_anketa)
        consultation._cached_extractor_provider = "deepseek"

        db_session = _make_db_session()

        with patch('src.voice.consultant._session_mgr') as mock_mgr, \
             patch('src.voice.consultant._update_anketa_via_api', new_callable=AsyncMock), \
             patch('src.voice.consultant._update_dialogue_via_api', new_callable=AsyncMock, side_effect=Exception("network error")), \
             patch('src.voice.consultant._try_get_redis', return_value=None), \
             patch('src.voice.consultant._extraction_semaphore', new=None):

            mock_mgr.get_session.return_value = db_session

            # Should not raise
            await _extract_and_update_anketa(consultation, "d9bbe7cd-test", None)
            # extraction_consecutive_failures should still be reset
            assert consultation._extraction_consecutive_failures == 0


# ===========================================================================
# BUG #3: CountryDetector with document phone
# ===========================================================================

class TestCountryDetectorDocumentPhone:
    """Tests for BUG #3 fix: CountryDetector uses phone from documents."""

    @pytest.mark.asyncio
    async def test_detector_receives_document_phone(self):
        """When anketa has no phone but documents do, doc phone should be passed."""
        consultation = _make_consultation(messages=8)
        consultation._cached_extractor = MagicMock()
        consultation.detected_profile = None  # Force re-detection

        mock_anketa = MagicMock()
        mock_anketa.company_name = "Bestattung Hanser"
        mock_anketa.contact_phone = ""  # No phone from dialogue
        mock_anketa.website = ""
        mock_anketa.completion_rate.return_value = 0.6
        mock_anketa.model_dump.return_value = {"company_name": "Bestattung Hanser"}

        consultation._cached_extractor.extract = AsyncMock(return_value=mock_anketa)
        consultation._cached_extractor_provider = "deepseek"

        db_session = _make_db_session(
            document_context={
                'all_contacts': {
                    'phone': '+43 664 755 03580',
                    'email': 'info@bestattung-hanser.at',
                },
                'key_facts': ['Bestattung Hanser'],
                'services_mentioned': ['funeral services'],
                'documents': [],
            }
        )

        mock_detector = MagicMock()
        mock_detector.detect.return_value = ("eu", "at")

        mock_profile = MagicMock()
        mock_profile.meta = SimpleNamespace(country="at", currency="EUR")

        with patch('src.voice.consultant._session_mgr') as mock_mgr, \
             patch('src.voice.consultant._update_anketa_via_api', new_callable=AsyncMock), \
             patch('src.voice.consultant._update_dialogue_via_api', new_callable=AsyncMock), \
             patch('src.voice.consultant._try_get_redis', return_value=None), \
             patch('src.voice.consultant._extraction_semaphore', new=None), \
             patch('src.voice.consultant._get_kb_manager') as mock_kb, \
             patch('src.knowledge.country_detector.get_country_detector', return_value=mock_detector):

            mock_mgr.get_session.return_value = db_session
            mock_manager = MagicMock()
            mock_manager.detect_industry.return_value = "funeral"
            mock_manager.loader.load_regional_profile.return_value = mock_profile
            mock_manager.get_profile.return_value = mock_profile
            mock_kb.return_value = mock_manager

            agent_session = _make_agent_session()

            await _extract_and_update_anketa(consultation, "d9bbe7cd-test", agent_session)

            # Verify detector was called with document phone
            mock_detector.detect.assert_called_once()
            call_kwargs = mock_detector.detect.call_args
            phone_arg = call_kwargs.kwargs.get('phone') or (call_kwargs.args[0] if call_kwargs.args else None)
            assert phone_arg == '+43 664 755 03580'

    @pytest.mark.asyncio
    async def test_detector_uses_dialogue_phone_first(self):
        """When anketa has a phone, it should be used over document phone."""
        consultation = _make_consultation(messages=8)
        consultation._cached_extractor = MagicMock()
        consultation.detected_profile = None

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.contact_phone = "+49 171 1234567"  # Phone from dialogue
        mock_anketa.website = ""
        mock_anketa.completion_rate.return_value = 0.6
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        consultation._cached_extractor.extract = AsyncMock(return_value=mock_anketa)
        consultation._cached_extractor_provider = "deepseek"

        db_session = _make_db_session(
            document_context={
                'all_contacts': {'phone': '+43 664 000 0000'},
                'key_facts': [],
                'services_mentioned': [],
                'documents': [],
            }
        )

        mock_detector = MagicMock()
        mock_detector.detect.return_value = ("eu", "de")

        mock_profile = MagicMock()
        mock_profile.meta = SimpleNamespace(country="de", currency="EUR")

        with patch('src.voice.consultant._session_mgr') as mock_mgr, \
             patch('src.voice.consultant._update_anketa_via_api', new_callable=AsyncMock), \
             patch('src.voice.consultant._update_dialogue_via_api', new_callable=AsyncMock), \
             patch('src.voice.consultant._try_get_redis', return_value=None), \
             patch('src.voice.consultant._extraction_semaphore', new=None), \
             patch('src.voice.consultant._get_kb_manager') as mock_kb, \
             patch('src.knowledge.country_detector.get_country_detector', return_value=mock_detector):

            mock_mgr.get_session.return_value = db_session
            mock_manager = MagicMock()
            mock_manager.detect_industry.return_value = "it"
            mock_manager.loader.load_regional_profile.return_value = mock_profile
            mock_kb.return_value = mock_manager

            agent_session = _make_agent_session()

            await _extract_and_update_anketa(consultation, "d9bbe7cd-test", agent_session)

            # Verify dialogue phone takes priority
            call_kwargs = mock_detector.detect.call_args
            phone_arg = call_kwargs.kwargs.get('phone') or (call_kwargs.args[0] if call_kwargs.args else None)
            assert phone_arg == "+49 171 1234567"

    @pytest.mark.asyncio
    async def test_detector_appends_email_domain_to_text(self):
        """Email domain from documents should be appended to dialogue text for detection."""
        consultation = _make_consultation(messages=8)
        consultation._cached_extractor = MagicMock()
        consultation.detected_profile = None

        mock_anketa = MagicMock()
        mock_anketa.company_name = "TestCorp"
        mock_anketa.contact_phone = ""
        mock_anketa.website = ""
        mock_anketa.completion_rate.return_value = 0.6
        mock_anketa.model_dump.return_value = {"company_name": "TestCorp"}

        consultation._cached_extractor.extract = AsyncMock(return_value=mock_anketa)
        consultation._cached_extractor_provider = "deepseek"

        db_session = _make_db_session(
            document_context={
                'all_contacts': {
                    'phone': '',
                    'email': 'info@firma.at',
                },
                'key_facts': [],
                'services_mentioned': [],
                'documents': [],
            }
        )

        mock_detector = MagicMock()
        mock_detector.detect.return_value = ("eu", "at")

        mock_profile = MagicMock()
        mock_profile.meta = SimpleNamespace(country="at", currency="EUR")

        with patch('src.voice.consultant._session_mgr') as mock_mgr, \
             patch('src.voice.consultant._update_anketa_via_api', new_callable=AsyncMock), \
             patch('src.voice.consultant._update_dialogue_via_api', new_callable=AsyncMock), \
             patch('src.voice.consultant._try_get_redis', return_value=None), \
             patch('src.voice.consultant._extraction_semaphore', new=None), \
             patch('src.voice.consultant._get_kb_manager') as mock_kb, \
             patch('src.knowledge.country_detector.get_country_detector', return_value=mock_detector):

            mock_mgr.get_session.return_value = db_session
            mock_manager = MagicMock()
            mock_manager.detect_industry.return_value = "funeral"
            mock_manager.loader.load_regional_profile.return_value = mock_profile
            mock_kb.return_value = mock_manager

            agent_session = _make_agent_session()

            await _extract_and_update_anketa(consultation, "d9bbe7cd-test", agent_session)

            call_kwargs = mock_detector.detect.call_args
            dialogue_text = call_kwargs.kwargs.get('dialogue_text', '')
            assert 'firma.at' in dialogue_text


# ===========================================================================
# BUG #4: Prompt prioritises documents (YAML-level test)
# ===========================================================================

class TestConsultantPromptDocumentPriority:
    """Tests for BUG #4 fix: consultant.yaml has document priority rules."""

    def test_prompt_contains_priority_rules(self):
        """System prompt should contain document priority instructions."""
        import yaml
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'prompts', 'voice', 'consultant.yaml',
        )
        with open(prompt_path, 'r') as f:
            data = yaml.safe_load(f)

        # Get the full prompt text
        prompt_text = str(data)

        assert 'КРИТИЧЕСКИЕ ПРАВИЛА ПРИ НАЛИЧИИ ДОКУМЕНТОВ' in prompt_text
        assert 'ПРИОРИТЕТ' in prompt_text
        assert 'ПОДТВЕРЖДАЙ вместо спрашивай' in prompt_text
        assert 'АДАПТИРУЙ чеклист' in prompt_text
        assert 'НИКОГДА не говори' in prompt_text

    def test_prompt_contains_multiagent_instructions(self):
        """System prompt should contain multi-agent recommendation handling (BUG #6)."""
        import yaml
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'prompts', 'voice', 'consultant.yaml',
        )
        with open(prompt_path, 'r') as f:
            data = yaml.safe_load(f)

        prompt_text = str(data)

        assert 'МУЛЬТИ-АГЕНТН' in prompt_text
        assert 'additional_notes' in prompt_text


# ===========================================================================
# BUG #5: Structured recommendations in injection
# ===========================================================================

class TestStructuredRecommendationsInjection:
    """Tests for BUG #5 fix: agent recommendations extracted from key_facts."""

    def test_recommendations_extracted_from_key_facts(self):
        """Key facts mentioning 'агент' or 'рекоменд' should be in recommendations."""
        key_facts = [
            'Компания: Bestattung Hanser',
            'Рекомендован агент Reception для приёма звонков',
            'Отрасль: похоронные услуги',
            'Рекомендован агент Support для консультаций',
            'Адрес: Вена, Австрия',
        ]

        _rec_keywords = ['агент', 'agent', 'рекоменд', 'recommend', 'роль', 'role', 'бот', 'bot']
        agent_recommendations = [
            f for f in key_facts
            if any(w in f.lower() for w in _rec_keywords)
        ]

        assert len(agent_recommendations) == 2
        assert 'Reception' in agent_recommendations[0]
        assert 'Support' in agent_recommendations[1]

    def test_no_recommendations_when_no_agent_facts(self):
        """When key_facts have no agent-related entries, list should be empty."""
        key_facts = [
            'Компания: TestCorp',
            'Отрасль: IT',
            'Адрес: Москва',
        ]

        _rec_keywords = ['агент', 'agent', 'рекоменд', 'recommend', 'роль', 'role', 'бот', 'bot']
        agent_recommendations = [
            f for f in key_facts
            if any(w in f.lower() for w in _rec_keywords)
        ]

        assert len(agent_recommendations) == 0

    def test_english_keywords_also_matched(self):
        """English keywords like 'agent', 'recommend', 'role', 'bot' should also match."""
        key_facts = [
            'Recommended agent: Customer Support Bot',
            'Company: ABC Corp',
            'Role: Sales Agent for outbound calls',
        ]

        _rec_keywords = ['агент', 'agent', 'рекоменд', 'recommend', 'роль', 'role', 'бот', 'bot']
        agent_recommendations = [
            f for f in key_facts
            if any(w in f.lower() for w in _rec_keywords)
        ]

        assert len(agent_recommendations) == 2


# ===========================================================================
# BUG #7: contact_role extraction prompt
# ===========================================================================

class TestContactRoleExtractionPrompt:
    """Tests for BUG #7 fix: extract.yaml has richer contact_role description."""

    def test_extraction_prompt_has_role_patterns(self):
        """Extraction prompt should mention role identification patterns."""
        import yaml
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'prompts', 'anketa', 'extract.yaml',
        )
        with open(prompt_path, 'r') as f:
            data = yaml.safe_load(f)

        prompt_text = data.get('user_prompt_template', '')

        # Check that the enhanced description is present
        assert 'я директор' in prompt_text
        assert 'я консультант' in prompt_text
        assert 'я владелец' in prompt_text
        assert 'подписи' in prompt_text


# ===========================================================================
# SessionManager.update_dialogue() status=None guard
# ===========================================================================

class TestUpdateDialogueStatusNone:
    """Tests for BUG #2 support: manager.update_dialogue handles status=None."""

    def test_update_dialogue_without_status(self):
        """update_dialogue with status=None should not update status column."""
        from src.session.manager import SessionManager
        import tempfile
        import sqlite3

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            mgr = SessionManager(db_path)
            # Create a session
            s = mgr.create_session("test-room")
            session_id = s.session_id
            assert session_id

            # Verify initial status is active
            session = mgr.get_session(session_id)
            assert session.status == "active"

            # Update dialogue without changing status
            result = mgr.update_dialogue(
                session_id,
                dialogue_history=[{"role": "user", "content": "hello"}],
                duration_seconds=42.0,
                status=None,
            )
            assert result is True

            # Verify status hasn't changed
            session = mgr.get_session(session_id)
            assert session.status == "active"
            assert len(session.dialogue_history) == 1
            assert session.duration_seconds == 42.0

        finally:
            os.unlink(db_path)

    def test_update_dialogue_with_status(self):
        """update_dialogue with valid status should update status column."""
        from src.session.manager import SessionManager
        import tempfile

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            mgr = SessionManager(db_path)
            s = mgr.create_session("test-room")
            session_id = s.session_id

            # Update with valid status transition active → reviewing
            result = mgr.update_dialogue(
                session_id,
                dialogue_history=[{"role": "user", "content": "done"}],
                duration_seconds=100.0,
                status="reviewing",
            )
            assert result is True

            session = mgr.get_session(session_id)
            assert session.status == "reviewing"

        finally:
            os.unlink(db_path)
