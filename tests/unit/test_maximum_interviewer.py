"""
Comprehensive tests for src/interview/maximum.py

Tests cover:
- MaximumInterviewer initialization
- Phase transition logic
- Question generation
- Answer analysis
- Information extraction
- FinalAnketa creation
- Session statistics
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.interview.maximum import MaximumInterviewer
from src.interview.phases import (
    InterviewPhase, FieldStatus, FieldPriority,
    CollectedInfo, PhaseTransition, ANKETA_FIELDS
)
from src.models import InterviewPattern
from src.anketa.schema import FinalAnketa


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_deepseek():
    """Mock DeepSeekClient."""
    client = MagicMock()
    client.chat = AsyncMock(return_value="Ответ AI")
    client.analyze_answer = AsyncMock(return_value={
        "completeness_score": 0.8,
        "is_complete": True,
        "reasoning": "Полный ответ",
        "needs_clarification": False
    })
    return client


@pytest.fixture
def interviewer(mock_deepseek):
    """Create MaximumInterviewer with mocked DeepSeek."""
    return MaximumInterviewer(
        pattern=InterviewPattern.INTERACTION,
        deepseek_client=mock_deepseek
    )


@pytest.fixture
def interviewer_management(mock_deepseek):
    """Create MaximumInterviewer with MANAGEMENT pattern."""
    return MaximumInterviewer(
        pattern=InterviewPattern.MANAGEMENT,
        deepseek_client=mock_deepseek
    )


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestMaximumInterviewerInit:
    """Tests for MaximumInterviewer initialization."""

    def test_init_default_pattern(self, mock_deepseek):
        """Test initialization with default pattern."""
        interviewer = MaximumInterviewer(deepseek_client=mock_deepseek)

        assert interviewer.pattern == InterviewPattern.INTERACTION
        assert interviewer.phase == InterviewPhase.DISCOVERY
        assert interviewer.session_id is not None
        assert isinstance(interviewer.collected, CollectedInfo)
        assert interviewer.dialogue_history == []
        assert interviewer.phase_transitions == []

    def test_init_management_pattern(self, mock_deepseek):
        """Test initialization with MANAGEMENT pattern."""
        interviewer = MaximumInterviewer(
            pattern=InterviewPattern.MANAGEMENT,
            deepseek_client=mock_deepseek
        )

        assert interviewer.pattern == InterviewPattern.MANAGEMENT

    def test_init_settings(self, interviewer):
        """Test default settings."""
        assert interviewer.discovery_min_turns == 5
        assert interviewer.discovery_max_turns == 15
        assert interviewer.max_clarifications == 3

    def test_init_creates_deepseek_if_not_provided(self):
        """Test that DeepSeek is created if not provided."""
        with patch('src.interview.maximum.DeepSeekClient') as mock_class:
            mock_class.return_value = MagicMock()
            result = MaximumInterviewer()
            mock_class.assert_called_once()
            assert result.deepseek is not None

    def test_init_start_time_is_set(self, interviewer):
        """Test that start_time is set."""
        assert interviewer.start_time is not None
        assert isinstance(interviewer.start_time, datetime)


# ============================================================================
# READY FOR STRUCTURED TESTS
# ============================================================================

class TestReadyForStructured:
    """Tests for _ready_for_structured method."""

    def test_not_ready_below_min_turns(self, interviewer):
        """Test not ready when below minimum turns."""
        result = interviewer._ready_for_structured(3)
        assert result is False

    def test_ready_with_required_percentage(self, interviewer):
        """Test ready when required percentage met."""
        # Set up some fields as complete
        interviewer.collected.update_field("company_name", "TestCo", source="test", confidence=1.0)
        interviewer.collected.update_field("industry", "IT", source="test", confidence=1.0)
        interviewer.collected.update_field("agent_purpose", "Консультирование", source="test", confidence=1.0)
        interviewer.collected.update_field("business_description", "IT компания", source="test", confidence=1.0)

        result = interviewer._ready_for_structured(6)
        assert result is True

    def test_ready_with_company_and_purpose(self, interviewer):
        """Test ready when company name and agent purpose are filled."""
        interviewer.collected.update_field("company_name", "TestCo", source="test", confidence=1.0)
        interviewer.collected.update_field("agent_purpose", "Консультирование", source="test", confidence=1.0)

        result = interviewer._ready_for_structured(6)
        assert result is True

    def test_not_ready_without_company(self, interviewer):
        """Test not ready without company name."""
        interviewer.collected.update_field("agent_purpose", "Консультирование", source="test", confidence=1.0)

        result = interviewer._ready_for_structured(6)
        assert result is False

    def test_not_ready_without_purpose(self, interviewer):
        """Test not ready without agent purpose."""
        interviewer.collected.update_field("company_name", "TestCo", source="test", confidence=1.0)

        result = interviewer._ready_for_structured(6)
        assert result is False


# ============================================================================
# QUESTION GENERATION TESTS
# ============================================================================

class TestGenerateContextualQuestion:
    """Tests for _generate_contextual_question method."""

    @pytest.mark.asyncio
    async def test_generate_question(self, interviewer):
        """Test question generation."""
        interviewer.deepseek.chat = AsyncMock(return_value="Как называется ваша компания?")

        # Get a field from ANKETA_FIELDS (it's a dict)
        field = ANKETA_FIELDS["company_name"]

        result = await interviewer._generate_contextual_question(field)

        assert result == "Как называется ваша компания?"
        interviewer.deepseek.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_question_uses_context(self, interviewer):
        """Test that question generation uses collected context."""
        interviewer.collected.update_field("company_name", "TestCo", source="test", confidence=1.0)
        interviewer.deepseek.chat = AsyncMock(return_value="Вопрос с контекстом")

        field = ANKETA_FIELDS["industry"]
        await interviewer._generate_contextual_question(field)

        # Check that the prompt includes context
        call_args = interviewer.deepseek.chat.call_args
        prompt = call_args[0][0][0]["content"]
        assert "TestCo" in prompt or "СОБРАННАЯ ИНФОРМАЦИЯ" in prompt


# ============================================================================
# ANSWER ANALYSIS TESTS
# ============================================================================

class TestAnalyzeAnswer:
    """Tests for _analyze_answer method."""

    @pytest.mark.asyncio
    async def test_analyze_answer(self, interviewer):
        """Test answer analysis."""
        field = ANKETA_FIELDS["company_name"]

        result = await interviewer._analyze_answer(field, "ООО Тест")

        assert "completeness_score" in result
        assert result["is_complete"] is True
        interviewer.deepseek.analyze_answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_answer_passes_context(self, interviewer):
        """Test that analysis includes context."""
        interviewer.collected.update_field("industry", "IT", source="test", confidence=1.0)
        field = ANKETA_FIELDS["company_name"]

        await interviewer._analyze_answer(field, "ООО Тест")

        call_args = interviewer.deepseek.analyze_answer.call_args
        assert "previous_answers" in call_args.kwargs
        assert call_args.kwargs["previous_answers"]["industry"] == "IT"


# ============================================================================
# INFORMATION EXTRACTION TESTS
# ============================================================================

class TestExtractInfoFromDialogue:
    """Tests for _extract_info_from_dialogue method."""

    @pytest.mark.asyncio
    async def test_extract_company_name(self, interviewer):
        """Test extracting company name from dialogue."""
        interviewer.deepseek.chat = AsyncMock(return_value='{"company_name": "АльфаТех", "industry": null}')

        await interviewer._extract_info_from_dialogue(
            "Я из компании АльфаТех",
            "Отлично, расскажите подробнее"
        )

        assert interviewer.collected.fields["company_name"].value == "АльфаТех"

    @pytest.mark.asyncio
    async def test_extract_multiple_fields(self, interviewer):
        """Test extracting multiple fields."""
        response = json.dumps({
            "company_name": "TestCo",
            "industry": "IT",
            "business_description": "IT компания",
            "services": ["Консалтинг", "Разработка"]
        })
        interviewer.deepseek.chat = AsyncMock(return_value=response)

        await interviewer._extract_info_from_dialogue(
            "Мы TestCo, IT компания",
            "Понятно"
        )

        assert interviewer.collected.fields["company_name"].value == "TestCo"
        assert interviewer.collected.fields["industry"].value == "IT"
        assert interviewer.collected.fields["business_description"].value == "IT компания"
        assert "Консалтинг" in interviewer.collected.fields["services"].value

    @pytest.mark.asyncio
    async def test_extract_handles_json_in_text(self, interviewer):
        """Test extraction handles JSON embedded in text."""
        response = 'Вот результат:\n```json\n{"company_name": "Test"}\n```'
        interviewer.deepseek.chat = AsyncMock(return_value=response)

        await interviewer._extract_info_from_dialogue("Test", "OK")

        assert interviewer.collected.fields["company_name"].value == "Test"

    @pytest.mark.asyncio
    async def test_extract_handles_invalid_json(self, interviewer):
        """Test extraction handles invalid JSON gracefully."""
        interviewer.deepseek.chat = AsyncMock(return_value="not valid json")

        # Should not raise exception
        await interviewer._extract_info_from_dialogue("Test", "OK")

        # Field should not be updated
        assert interviewer.collected.fields["company_name"].status == FieldStatus.EMPTY

    @pytest.mark.asyncio
    async def test_extract_appends_to_list_fields(self, interviewer):
        """Test that list fields are appended, not replaced."""
        # First extraction
        interviewer.deepseek.chat = AsyncMock(return_value='{"services": ["Услуга 1"]}')
        await interviewer._extract_info_from_dialogue("Услуга 1", "OK")

        # Second extraction
        interviewer.deepseek.chat = AsyncMock(return_value='{"services": ["Услуга 2"]}')
        await interviewer._extract_info_from_dialogue("Услуга 2", "OK")

        services = interviewer.collected.fields["services"].value
        assert "Услуга 1" in services
        assert "Услуга 2" in services


# ============================================================================
# FINAL ANKETA CREATION TESTS
# ============================================================================

class TestCreateFinalAnketa:
    """Tests for _create_final_anketa method."""

    def test_create_anketa_basic(self, interviewer):
        """Test basic anketa creation."""
        interviewer.collected.update_field("company_name", "TestCo", source="test", confidence=1.0)
        interviewer.collected.update_field("industry", "IT", source="test", confidence=1.0)

        anketa = interviewer._create_final_anketa()

        assert isinstance(anketa, FinalAnketa)
        assert anketa.company_name == "TestCo"
        assert anketa.industry == "IT"
        assert anketa.interview_id == interviewer.session_id
        assert anketa.pattern == "interaction"

    def test_create_anketa_with_defaults(self, interviewer):
        """Test anketa creation with default values."""
        anketa = interviewer._create_final_anketa()

        assert anketa.company_name == "Не указано"
        assert anketa.industry == "Не указано"
        assert anketa.language == "ru"
        assert anketa.agent_name == "Агент"

    def test_create_anketa_with_full_data(self, interviewer):
        """Test anketa creation with full collected data."""
        interviewer.collected.update_field("company_name", "АльфаТех", source="test", confidence=1.0)
        interviewer.collected.update_field("industry", "IT", source="test", confidence=1.0)
        interviewer.collected.update_field("agent_purpose", "Консультирование", source="test", confidence=1.0)
        interviewer.collected.update_field("agent_name", "АльфаБот", source="test", confidence=1.0)
        interviewer.collected.update_field("services", ["Консалтинг", "Разработка"], source="test", confidence=1.0)
        interviewer.collected.update_field("business_description", "IT компания", source="test", confidence=1.0)

        anketa = interviewer._create_final_anketa()

        assert anketa.company_name == "АльфаТех"
        assert anketa.industry == "IT"
        assert anketa.agent_purpose == "Консультирование"
        assert anketa.agent_name == "АльфаБот"
        assert anketa.services == ["Консалтинг", "Разработка"]
        assert anketa.business_description == "IT компания"

    def test_create_anketa_includes_quality_metrics(self, interviewer):
        """Test anketa includes quality metrics."""
        interviewer.collected.update_field("company_name", "Test", source="test", confidence=1.0)
        interviewer.collected.update_field("industry", "IT", source="test", confidence=1.0)

        anketa = interviewer._create_final_anketa()

        assert anketa.quality_metrics is not None
        assert "complete" in anketa.quality_metrics

    def test_create_anketa_includes_full_responses(self, interviewer):
        """Test anketa includes full responses."""
        interviewer.collected.update_field("company_name", "Test", source="test", confidence=1.0)
        interviewer.collected.update_field("industry", "IT", source="test", confidence=1.0)

        anketa = interviewer._create_final_anketa()

        assert anketa.full_responses is not None
        assert "company_name" in anketa.full_responses

    def test_create_anketa_management_pattern(self, interviewer_management):
        """Test anketa creation with management pattern."""
        interviewer_management.collected.update_field("company_name", "Test", source="test", confidence=1.0)
        interviewer_management.collected.update_field("industry", "IT", source="test", confidence=1.0)

        anketa = interviewer_management._create_final_anketa()

        assert anketa.pattern == "management"


# ============================================================================
# SESSION STATS TESTS
# ============================================================================

class TestGetSessionStats:
    """Tests for _get_session_stats method."""

    def test_get_session_stats_basic(self, interviewer):
        """Test getting basic session stats."""
        stats = interviewer._get_session_stats()

        assert "session_id" in stats
        assert stats["session_id"] == interviewer.session_id
        assert "duration_seconds" in stats
        assert "dialogue_turns" in stats
        assert "phase_transitions" in stats
        assert "completion_stats" in stats

    def test_get_session_stats_with_dialogue(self, interviewer):
        """Test stats with dialogue history."""
        interviewer.dialogue_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]

        stats = interviewer._get_session_stats()

        assert stats["dialogue_turns"] == 2

    def test_get_session_stats_with_transitions(self, interviewer):
        """Test stats with phase transitions."""
        interviewer._transition_phase(
            InterviewPhase.DISCOVERY,
            InterviewPhase.STRUCTURED,
            "Test transition"
        )

        stats = interviewer._get_session_stats()

        assert stats["phase_transitions"] == 1


# ============================================================================
# PHASE TRANSITION TESTS
# ============================================================================

class TestTransitionPhase:
    """Tests for _transition_phase method."""

    def test_transition_phase(self, interviewer):
        """Test phase transition."""
        with patch('src.interview.maximum.console'):
            interviewer._transition_phase(
                InterviewPhase.DISCOVERY,
                InterviewPhase.STRUCTURED,
                "Test reason"
            )

        assert interviewer.phase == InterviewPhase.STRUCTURED
        assert len(interviewer.phase_transitions) == 1
        assert interviewer.phase_transitions[0].from_phase == InterviewPhase.DISCOVERY
        assert interviewer.phase_transitions[0].to_phase == InterviewPhase.STRUCTURED
        assert interviewer.phase_transitions[0].reason == "Test reason"

    def test_transition_records_stats(self, interviewer):
        """Test that transition records completion stats."""
        interviewer.collected.update_field("company_name", "Test", source="test", confidence=1.0)

        with patch('src.interview.maximum.console'):
            interviewer._transition_phase(
                InterviewPhase.DISCOVERY,
                InterviewPhase.STRUCTURED,
                "Test"
            )

        assert interviewer.phase_transitions[0].stats_at_transition is not None


# ============================================================================
# AI RESPONSE TESTS
# ============================================================================

class TestGetAIResponse:
    """Tests for _get_ai_response method."""

    @pytest.mark.asyncio
    async def test_get_ai_response(self, interviewer):
        """Test getting AI response."""
        interviewer.deepseek.chat = AsyncMock(return_value="Ответ AI")

        response = await interviewer._get_ai_response("System prompt", "User message")

        assert response == "Ответ AI"

    @pytest.mark.asyncio
    async def test_get_ai_response_adds_to_history(self, interviewer):
        """Test that response adds messages to history."""
        interviewer.deepseek.chat = AsyncMock(return_value="Ответ AI")

        await interviewer._get_ai_response("System", "User message")

        assert len(interviewer.dialogue_history) == 2
        assert interviewer.dialogue_history[0]["role"] == "user"
        assert interviewer.dialogue_history[0]["content"] == "User message"
        assert interviewer.dialogue_history[1]["role"] == "assistant"
        assert interviewer.dialogue_history[1]["content"] == "Ответ AI"

    @pytest.mark.asyncio
    async def test_get_ai_response_includes_context(self, interviewer):
        """Test that AI response includes collected context."""
        interviewer.collected.update_field("company_name", "TestCo", source="test", confidence=1.0)
        interviewer.deepseek.chat = AsyncMock(return_value="OK")

        await interviewer._get_ai_response("System", "Message")

        call_args = interviewer.deepseek.chat.call_args
        system_content = call_args[0][0][0]["content"]
        assert "TestCo" in system_content or "ТЕКУЩАЯ СОБРАННАЯ ИНФОРМАЦИЯ" in system_content

    @pytest.mark.asyncio
    async def test_get_ai_response_limits_history(self, interviewer):
        """Test that AI response limits dialogue history in context."""
        # Add 15 messages to history
        for i in range(15):
            interviewer.dialogue_history.append({"role": "user", "content": f"Message {i}"})

        interviewer.deepseek.chat = AsyncMock(return_value="OK")
        await interviewer._get_ai_response("System", "New message")

        call_args = interviewer.deepseek.chat.call_args
        messages = call_args[0][0]
        # Should have system + last 10 messages + new user message
        # But history was extended with user message first, so it's system + last 10
        assert len(messages) <= 12  # system + up to 10 history + new


# ============================================================================
# DISCOVERY PROMPT TESTS
# ============================================================================

class TestGetDiscoverySystemPrompt:
    """Tests for _get_discovery_system_prompt method."""

    def test_get_discovery_prompt(self, interviewer):
        """Test getting discovery system prompt."""
        prompt = interviewer._get_discovery_system_prompt()

        assert prompt is not None
        assert len(prompt) > 0
        assert isinstance(prompt, str)


# ============================================================================
# CLARIFICATIONS TESTS
# ============================================================================

class TestHandleClarifications:
    """Tests for _handle_clarifications method."""

    @pytest.mark.asyncio
    async def test_handle_clarifications_skip(self, interviewer):
        """Test handling clarifications with skip."""
        field = ANKETA_FIELDS["company_name"]
        analysis = {
            "clarification_questions": ["Уточните, пожалуйста?"],
            "completeness_score": 0.5
        }

        with patch('src.interview.maximum.Prompt') as mock_prompt:
            with patch('src.interview.maximum.console'):
                mock_prompt.ask.return_value = "skip"

                await interviewer._handle_clarifications(field, analysis, "Original answer")

    @pytest.mark.asyncio
    async def test_handle_clarifications_provides_answer(self, interviewer):
        """Test handling clarifications with actual answer."""
        field = ANKETA_FIELDS["company_name"]
        analysis = {
            "clarification_questions": ["Уточните?"],
            "completeness_score": 0.5
        }

        interviewer.deepseek.analyze_answer = AsyncMock(return_value={
            "completeness_score": 1.0,
            "is_complete": True
        })

        with patch('src.interview.maximum.Prompt') as mock_prompt:
            with patch('src.interview.maximum.console'):
                mock_prompt.ask.return_value = "Дополнительная информация"

                await interviewer._handle_clarifications(field, analysis, "Original")

        # Check that field was updated
        interviewer.deepseek.analyze_answer.assert_called()


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_collected_info(self, interviewer):
        """Test with empty collected info."""
        anketa = interviewer._create_final_anketa()

        assert anketa.company_name == "Не указано"
        assert anketa.services == []

    @pytest.mark.asyncio
    async def test_extract_with_null_values(self, interviewer):
        """Test extraction with null values."""
        response = '{"company_name": null, "industry": "IT"}'
        interviewer.deepseek.chat = AsyncMock(return_value=response)

        await interviewer._extract_info_from_dialogue("Test", "OK")

        # company_name should not be updated (null)
        # industry should be updated
        assert interviewer.collected.fields["industry"].value == "IT"

    def test_ready_for_structured_exact_min_turns(self, interviewer):
        """Test ready_for_structured at exact minimum turns."""
        interviewer.collected.update_field("company_name", "Test", source="test", confidence=1.0)
        interviewer.collected.update_field("agent_purpose", "Консультирование", source="test", confidence=1.0)

        # At exactly min turns, should be ready if fields are filled
        result = interviewer._ready_for_structured(5)
        assert result is True

    def test_multiple_phase_transitions(self, interviewer):
        """Test multiple phase transitions."""
        with patch('src.interview.maximum.console'):
            interviewer._transition_phase(
                InterviewPhase.DISCOVERY,
                InterviewPhase.STRUCTURED,
                "First transition"
            )
            interviewer._transition_phase(
                InterviewPhase.STRUCTURED,
                InterviewPhase.SYNTHESIS,
                "Second transition"
            )

        assert len(interviewer.phase_transitions) == 2
        assert interviewer.phase == InterviewPhase.SYNTHESIS


# ============================================================================
# DISPLAY METHOD TESTS
# ============================================================================

class TestDisplayMethods:
    """Tests for display methods."""

    def test_show_welcome(self, interviewer):
        """Test show_welcome doesn't crash."""
        with patch('src.interview.maximum.console'):
            interviewer._show_welcome()

    def test_show_phase_banner(self, interviewer):
        """Test show_phase_banner doesn't crash."""
        with patch('src.interview.maximum.console'):
            interviewer._show_phase_banner("TEST", "cyan", "Test message")

    def test_show_ai_message(self, interviewer):
        """Test show_ai_message doesn't crash."""
        with patch('src.interview.maximum.console'):
            interviewer._show_ai_message("Test AI message")

    def test_show_status(self, interviewer):
        """Test show_status doesn't crash."""
        with patch('src.interview.maximum.console'):
            interviewer._show_status()

    def test_show_mini_progress(self, interviewer):
        """Test show_mini_progress doesn't crash."""
        with patch('src.interview.maximum.console'):
            interviewer._show_mini_progress()

    def test_show_field_question(self, interviewer):
        """Test show_field_question doesn't crash."""
        field = ANKETA_FIELDS["company_name"]
        with patch('src.interview.maximum.console'):
            interviewer._show_field_question(field, 1, 5)

    def test_show_results(self, interviewer):
        """Test show_results doesn't crash."""
        result = {
            "anketa": FinalAnketa(
                company_name="Test",
                industry="IT",
                faq_items=[],
                objection_handlers=[],
                success_kpis=[],
                ai_recommendations=[]
            ),
            "json": "/path/to/file.json",
            "markdown": "/path/to/file.md"
        }
        with patch('src.interview.maximum.console'):
            interviewer._show_results(result)


# ============================================================================
# INTEGRATION-LIKE TESTS
# ============================================================================

class TestIntegration:
    """Integration-like tests for the interviewer."""

    def test_full_workflow_data_collection(self, interviewer):
        """Test a full workflow of data collection."""
        # Simulate discovery phase data collection
        interviewer.collected.update_field("company_name", "АльфаТех", source="discovery", confidence=0.8)
        interviewer.collected.update_field("industry", "IT", source="discovery", confidence=0.8)
        interviewer.collected.update_field("business_description", "IT консалтинг", source="discovery", confidence=0.7)
        interviewer.collected.update_field("agent_purpose", "Консультирование", source="discovery", confidence=0.8)

        # Check ready for structured (needs company_name AND agent_purpose)
        assert interviewer._ready_for_structured(6)

        # Transition to structured
        with patch('src.interview.maximum.console'):
            interviewer._transition_phase(
                InterviewPhase.DISCOVERY,
                InterviewPhase.STRUCTURED,
                "Ready for structured"
            )

        # Simulate structured phase
        interviewer.collected.update_field("agent_purpose", "Консультирование клиентов", source="structured", confidence=0.9)
        interviewer.collected.update_field("agent_name", "АльфаБот", source="structured", confidence=1.0)

        # Transition to synthesis
        with patch('src.interview.maximum.console'):
            interviewer._transition_phase(
                InterviewPhase.STRUCTURED,
                InterviewPhase.SYNTHESIS,
                "Ready for synthesis"
            )

        # Create final anketa
        anketa = interviewer._create_final_anketa()

        assert anketa.company_name == "АльфаТех"
        assert anketa.industry == "IT"
        assert anketa.agent_name == "АльфаБот"
        assert len(interviewer.phase_transitions) == 2

    @pytest.mark.asyncio
    async def test_dialogue_extraction_workflow(self, interviewer):
        """Test dialogue extraction workflow."""
        # Simulate a dialogue
        responses = [
            '{"company_name": "TestCo", "industry": null}',
            '{"industry": "IT", "business_description": "IT компания"}',
            '{"services": ["Консалтинг"], "client_types": ["B2B"]}'
        ]

        for response in responses:
            interviewer.deepseek.chat = AsyncMock(return_value=response)
            await interviewer._extract_info_from_dialogue("User", "AI")

        assert interviewer.collected.fields["company_name"].value == "TestCo"
        assert interviewer.collected.fields["industry"].value == "IT"
        assert interviewer.collected.fields["business_description"].value == "IT компания"
        assert "Консалтинг" in interviewer.collected.fields["services"].value
        assert "B2B" in interviewer.collected.fields["client_types"].value
