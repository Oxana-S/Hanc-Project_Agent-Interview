"""
Tests for v5.0 interview extraction routing in src/anketa/extractor.py

Tests cover:
- extract() routing: consultation_type="consultation" vs "interview"
- _extract_interview() method with mocked LLM
- _build_interview_anketa() method for InterviewAnketa construction
- Graceful degradation on LLM errors
- Edge cases: empty data, invalid qa_pairs, missing fields
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.anketa.extractor import AnketaExtractor
from src.anketa.schema import (
    FinalAnketa, InterviewAnketa, QAPair, AIRecommendation
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_llm():
    """Mock DeepSeekClient."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value='{"company_name": "TestCo"}')
    return llm


@pytest.fixture
def extractor(mock_llm):
    """Create extractor with mocked LLM."""
    return AnketaExtractor(llm=mock_llm)


@pytest.fixture
def sample_interview_dialogue():
    """Sample interview dialogue history."""
    return [
        {"role": "assistant", "content": "Добрый день! Давайте начнём интервью. Расскажите о себе."},
        {"role": "user", "content": "Меня зовут Алексей Смирнов, я CTO в компании DataFlow."},
        {"role": "assistant", "content": "Какие технологии вы используете в работе?"},
        {"role": "user", "content": "Мы активно используем Python и Kubernetes для микросервисов."},
        {"role": "assistant", "content": "Какие основные вызовы вы видите в своей области?"},
        {"role": "user", "content": "Главный вызов — масштабирование при росте нагрузки и управление техдолгом."},
    ]


@pytest.fixture
def full_interview_llm_response():
    """Full LLM JSON response for interview extraction."""
    return json.dumps({
        "contact_name": "Алексей Смирнов",
        "contact_role": "CTO",
        "company_name": "DataFlow",
        "interview_title": "Технологические вызовы в DataFlow",
        "interview_type": "customer_discovery",
        "interviewee_context": "Опытный технический лидер с 10+ лет в разработке",
        "interviewee_industry": "IT / SaaS",
        "qa_pairs": [
            {
                "question": "Расскажите о себе",
                "answer": "Меня зовут Алексей Смирнов, я CTO в компании DataFlow.",
                "topic": "introduction",
                "follow_ups": ["Сколько лет вы в этой роли?"]
            },
            {
                "question": "Какие технологии вы используете?",
                "answer": "Python и Kubernetes для микросервисов.",
                "topic": "technology",
                "follow_ups": []
            },
            {
                "question": "Какие основные вызовы?",
                "answer": "Масштабирование при росте нагрузки и управление техдолгом.",
                "topic": "challenges",
                "follow_ups": ["Как вы решаете проблему техдолга?"]
            }
        ],
        "detected_topics": ["introduction", "technology", "challenges"],
        "key_quotes": [
            "Главный вызов — масштабирование при росте нагрузки",
            "Мы активно используем Python и Kubernetes"
        ],
        "summary": "Интервью с CTO DataFlow о технологическом стеке и вызовах масштабирования.",
        "key_insights": [
            "Компания делает ставку на Python+Kubernetes",
            "Техдолг — серьёзная проблема"
        ],
        "ai_recommendations": [
            {
                "recommendation": "Внедрить автоматизированное тестирование",
                "impact": "Снижение техдолга на 30%",
                "priority": "high",
                "effort": "medium"
            },
            {
                "recommendation": "Использовать Helm charts для стандартизации деплоя",
                "impact": "Ускорение деплоя на 40%",
                "priority": "medium",
                "effort": "low"
            }
        ],
        "unresolved_topics": ["бюджет на инфраструктуру", "планы по найму"]
    })


@pytest.fixture
def consultation_llm_response():
    """LLM JSON response for regular consultation extraction."""
    return json.dumps({
        "company_name": "TestCo",
        "industry": "IT",
        "specialization": "Консалтинг",
        "website": None,
        "contact_name": "Тест",
        "contact_role": "",
        "business_description": "IT-компания",
        "services": ["Консалтинг"],
        "client_types": [],
        "current_problems": [],
        "business_goals": [],
        "constraints": [],
        "agent_name": "Бот",
        "agent_purpose": "Помощь",
        "agent_functions": [],
        "typical_questions": [],
        "voice_gender": "female",
        "voice_tone": "professional",
        "language": "ru",
        "call_direction": "inbound",
        "integrations": [],
        "main_function": None,
        "additional_functions": []
    })


@pytest.fixture
def expert_llm_response():
    """Expert content LLM response for consultation path."""
    return json.dumps({
        "faq_items": [{"question": "Q?", "answer": "A", "category": "general"}],
        "objection_handlers": [],
        "sample_dialogue": [],
        "financial_metrics": [],
        "competitors": [],
        "market_insights": [],
        "escalation_rules": [],
        "success_kpis": [],
        "launch_checklist": [],
        "ai_recommendations": [],
        "target_segments": [],
        "tone_of_voice": {},
        "error_handling_scripts": {},
        "follow_up_sequence": [],
        "competitive_advantages": []
    })


# ============================================================================
# EXTRACT() ROUTING TESTS
# ============================================================================

class TestExtractRouting:
    """Tests for extract() method routing based on consultation_type."""

    @pytest.mark.asyncio
    async def test_extract_default_returns_final_anketa(
        self, extractor, sample_interview_dialogue,
        consultation_llm_response, expert_llm_response
    ):
        """Default consultation_type (no argument) routes to consultation path and returns FinalAnketa."""
        extractor.llm.chat = AsyncMock(
            side_effect=[consultation_llm_response, expert_llm_response]
        )

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(consultation_llm_response), False)
        ):
            with patch.object(
                extractor.post_processor, 'process',
                return_value=(json.loads(consultation_llm_response), {'cleaning_changes': []})
            ):
                result = await extractor.extract(
                    sample_interview_dialogue,
                    duration_seconds=100.0,
                )

        assert isinstance(result, FinalAnketa)
        assert not isinstance(result, InterviewAnketa)

    @pytest.mark.asyncio
    async def test_extract_consultation_type_consultation_returns_final_anketa(
        self, extractor, sample_interview_dialogue,
        consultation_llm_response, expert_llm_response
    ):
        """consultation_type='consultation' explicitly routes to consultation path."""
        extractor.llm.chat = AsyncMock(
            side_effect=[consultation_llm_response, expert_llm_response]
        )

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(consultation_llm_response), False)
        ):
            with patch.object(
                extractor.post_processor, 'process',
                return_value=(json.loads(consultation_llm_response), {'cleaning_changes': []})
            ):
                result = await extractor.extract(
                    sample_interview_dialogue,
                    duration_seconds=100.0,
                    consultation_type="consultation",
                )

        assert isinstance(result, FinalAnketa)
        assert not isinstance(result, InterviewAnketa)

    @pytest.mark.asyncio
    async def test_extract_consultation_type_interview_returns_interview_anketa(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """consultation_type='interview' routes to interview path and returns InterviewAnketa."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor.extract(
                sample_interview_dialogue,
                duration_seconds=200.0,
                consultation_type="interview",
            )

        assert isinstance(result, InterviewAnketa)

    @pytest.mark.asyncio
    async def test_extract_interview_calls_extract_interview_method(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """consultation_type='interview' invokes _extract_interview() internally."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_extract_interview',
            new_callable=AsyncMock,
            return_value=InterviewAnketa()
        ) as mock_extract_interview:
            await extractor.extract(
                sample_interview_dialogue,
                duration_seconds=150.0,
                consultation_type="interview",
            )

        mock_extract_interview.assert_called_once_with(
            sample_interview_dialogue, 150.0
        )

    @pytest.mark.asyncio
    async def test_extract_consultation_does_not_call_extract_interview(
        self, extractor, sample_interview_dialogue,
        consultation_llm_response, expert_llm_response
    ):
        """consultation_type='consultation' does NOT call _extract_interview()."""
        extractor.llm.chat = AsyncMock(
            side_effect=[consultation_llm_response, expert_llm_response]
        )

        with patch.object(
            extractor, '_extract_interview',
            new_callable=AsyncMock
        ) as mock_extract_interview:
            with patch.object(
                extractor, '_parse_json_with_repair',
                return_value=(json.loads(consultation_llm_response), False)
            ):
                with patch.object(
                    extractor.post_processor, 'process',
                    return_value=(json.loads(consultation_llm_response), {'cleaning_changes': []})
                ):
                    await extractor.extract(
                        sample_interview_dialogue,
                        duration_seconds=100.0,
                        consultation_type="consultation",
                    )

        mock_extract_interview.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_interview_ignores_business_analysis_and_solution(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Interview path ignores business_analysis and proposed_solution args."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_extract_interview',
            new_callable=AsyncMock,
            return_value=InterviewAnketa()
        ) as mock_extract_interview:
            await extractor.extract(
                sample_interview_dialogue,
                business_analysis={"company_name": "Ignored"},
                proposed_solution={"agent_name": "Ignored"},
                duration_seconds=200.0,
                consultation_type="interview",
            )

        # _extract_interview receives only dialogue and duration
        mock_extract_interview.assert_called_once_with(
            sample_interview_dialogue, 200.0
        )


# ============================================================================
# _EXTRACT_INTERVIEW() TESTS
# ============================================================================

class TestExtractInterview:
    """Tests for _extract_interview() method."""

    @pytest.mark.asyncio
    async def test_extract_interview_returns_interview_anketa(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """_extract_interview returns an InterviewAnketa instance."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert isinstance(result, InterviewAnketa)

    @pytest.mark.asyncio
    async def test_extract_interview_populates_contact_fields(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has correct contact fields."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert result.contact_name == "Алексей Смирнов"
        assert result.contact_role == "CTO"
        assert result.company_name == "DataFlow"

    @pytest.mark.asyncio
    async def test_extract_interview_populates_interview_metadata(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has correct interview metadata."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert result.interview_title == "Технологические вызовы в DataFlow"
        assert result.interview_type == "customer_discovery"
        assert result.interviewee_context == "Опытный технический лидер с 10+ лет в разработке"
        assert result.interviewee_industry == "IT / SaaS"

    @pytest.mark.asyncio
    async def test_extract_interview_populates_qa_pairs(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has correct QA pairs."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert len(result.qa_pairs) == 3
        assert all(isinstance(qa, QAPair) for qa in result.qa_pairs)
        assert result.qa_pairs[0].topic == "introduction"
        assert result.qa_pairs[1].topic == "technology"
        assert result.qa_pairs[2].topic == "challenges"

    @pytest.mark.asyncio
    async def test_extract_interview_populates_detected_topics(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has detected topics."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert result.detected_topics == ["introduction", "technology", "challenges"]

    @pytest.mark.asyncio
    async def test_extract_interview_populates_key_quotes(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has key quotes."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert len(result.key_quotes) == 2
        assert "масштабирование" in result.key_quotes[0].lower()

    @pytest.mark.asyncio
    async def test_extract_interview_populates_summary_and_insights(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has summary and key insights."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert "DataFlow" in result.summary
        assert len(result.key_insights) == 2

    @pytest.mark.asyncio
    async def test_extract_interview_populates_ai_recommendations(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has AI recommendations."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert len(result.ai_recommendations) == 2
        assert all(isinstance(r, AIRecommendation) for r in result.ai_recommendations)
        assert result.ai_recommendations[0].priority == "high"
        assert result.ai_recommendations[1].effort == "low"

    @pytest.mark.asyncio
    async def test_extract_interview_populates_unresolved_topics(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has unresolved topics."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 200.0
            )

        assert len(result.unresolved_topics) == 2
        assert "бюджет на инфраструктуру" in result.unresolved_topics

    @pytest.mark.asyncio
    async def test_extract_interview_sets_duration(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Extracted InterviewAnketa has correct duration."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 456.7
            )

        assert result.consultation_duration_seconds == pytest.approx(456.7)

    @pytest.mark.asyncio
    async def test_extract_interview_calls_llm_with_dialogue(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """_extract_interview sends formatted dialogue to LLM."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            await extractor._extract_interview(sample_interview_dialogue, 100.0)

        extractor.llm.chat.assert_called_once()
        call_args = extractor.llm.chat.call_args
        messages = call_args[1].get("messages") or call_args[0][0] if call_args[0] else call_args[1]["messages"]

        # System message should be the interview expert prompt
        assert len(messages) == 2
        system_msg = messages[0]
        user_msg = messages[1]
        assert system_msg["role"] == "system"
        assert user_msg["role"] == "user"

    @pytest.mark.asyncio
    async def test_extract_interview_dialogue_formatted_as_role_content(
        self, extractor, full_interview_llm_response
    ):
        """Dialogue is formatted as 'ROLE: content' in the prompt sent to LLM."""
        dialogue = [
            {"role": "assistant", "content": "Вопрос один?"},
            {"role": "user", "content": "Ответ один."},
        ]
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            await extractor._extract_interview(dialogue, 100.0)

        call_args = extractor.llm.chat.call_args
        messages = call_args[1].get("messages") or call_args[0][0] if call_args[0] else call_args[1]["messages"]
        user_prompt = messages[1]["content"]

        assert "ASSISTANT: Вопрос один?" in user_prompt
        assert "USER: Ответ один." in user_prompt

    @pytest.mark.asyncio
    async def test_extract_interview_truncates_to_50_messages(
        self, extractor, full_interview_llm_response
    ):
        """Dialogue is truncated to last 50 messages."""
        long_dialogue = [
            {"role": "user", "content": f"Сообщение {i}"}
            for i in range(100)
        ]
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            await extractor._extract_interview(long_dialogue, 100.0)

        call_args = extractor.llm.chat.call_args
        messages = call_args[1].get("messages") or call_args[0][0] if call_args[0] else call_args[1]["messages"]
        user_prompt = messages[1]["content"]

        assert "Сообщение 99" in user_prompt
        assert "Сообщение 50" in user_prompt
        assert "Сообщение 49" not in user_prompt

    @pytest.mark.asyncio
    async def test_extract_interview_llm_error_returns_empty_anketa(
        self, extractor, sample_interview_dialogue
    ):
        """On LLM error, _extract_interview returns empty InterviewAnketa (graceful degradation)."""
        extractor.llm.chat = AsyncMock(side_effect=Exception("LLM connection failed"))

        result = await extractor._extract_interview(
            sample_interview_dialogue, 300.0
        )

        assert isinstance(result, InterviewAnketa)
        assert result.contact_name == ""
        assert result.company_name == ""
        assert result.qa_pairs == []
        assert result.detected_topics == []
        assert result.consultation_duration_seconds == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_extract_interview_json_parse_error_returns_empty_anketa(
        self, extractor, sample_interview_dialogue
    ):
        """On JSON parse error, _extract_interview returns empty InterviewAnketa."""
        extractor.llm.chat = AsyncMock(return_value="not valid json at all")

        with patch.object(
            extractor, '_parse_json_with_repair',
            side_effect=json.JSONDecodeError("Expecting value", "", 0)
        ):
            result = await extractor._extract_interview(
                sample_interview_dialogue, 150.0
            )

        assert isinstance(result, InterviewAnketa)
        assert result.qa_pairs == []
        assert result.consultation_duration_seconds == pytest.approx(150.0)

    @pytest.mark.asyncio
    async def test_extract_interview_empty_dialogue(self, extractor):
        """_extract_interview handles empty dialogue gracefully."""
        extractor.llm.chat = AsyncMock(return_value='{}')

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=({}, False)
        ):
            result = await extractor._extract_interview([], 0.0)

        assert isinstance(result, InterviewAnketa)
        assert result.qa_pairs == []

    @pytest.mark.asyncio
    async def test_extract_interview_uses_parse_json_with_repair(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """_extract_interview uses _parse_json_with_repair for JSON parsing."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), True)
        ) as mock_parse:
            await extractor._extract_interview(sample_interview_dialogue, 100.0)

        mock_parse.assert_called_once_with(full_interview_llm_response)


# ============================================================================
# _BUILD_INTERVIEW_ANKETA() TESTS
# ============================================================================

class TestBuildInterviewAnketa:
    """Tests for _build_interview_anketa() method."""

    def test_build_from_empty_data(self, extractor):
        """Empty data dict produces InterviewAnketa with defaults."""
        result = extractor._build_interview_anketa({}, 0.0)

        assert isinstance(result, InterviewAnketa)
        assert result.company_name == ""
        assert result.contact_name == ""
        assert result.contact_role == ""
        assert result.interview_title == ""
        assert result.interview_type == "general"
        assert result.interviewee_context == ""
        assert result.interviewee_industry == ""
        assert result.qa_pairs == []
        assert result.detected_topics == []
        assert result.key_quotes == []
        assert result.summary == ""
        assert result.key_insights == []
        assert result.ai_recommendations == []
        assert result.unresolved_topics == []
        assert result.consultation_duration_seconds == pytest.approx(0.0)

    def test_build_from_full_data(self, extractor, full_interview_llm_response):
        """Full data dict produces InterviewAnketa with all fields populated."""
        data = json.loads(full_interview_llm_response)
        result = extractor._build_interview_anketa(data, 500.0)

        assert result.company_name == "DataFlow"
        assert result.contact_name == "Алексей Смирнов"
        assert result.contact_role == "CTO"
        assert result.interview_title == "Технологические вызовы в DataFlow"
        assert result.interview_type == "customer_discovery"
        assert result.interviewee_context == "Опытный технический лидер с 10+ лет в разработке"
        assert result.interviewee_industry == "IT / SaaS"
        assert len(result.qa_pairs) == 3
        assert result.detected_topics == ["introduction", "technology", "challenges"]
        assert len(result.key_quotes) == 2
        assert "DataFlow" in result.summary
        assert len(result.key_insights) == 2
        assert len(result.ai_recommendations) == 2
        assert len(result.unresolved_topics) == 2
        assert result.consultation_duration_seconds == pytest.approx(500.0)

    def test_build_qa_pairs_as_qapair_objects(self, extractor):
        """qa_pairs are built as QAPair model instances."""
        data = {
            "qa_pairs": [
                {"question": "Q1?", "answer": "A1", "topic": "intro", "follow_ups": ["FU1"]},
                {"question": "Q2?", "answer": "A2", "topic": "tech"},
            ]
        }
        result = extractor._build_interview_anketa(data, 0.0)

        assert len(result.qa_pairs) == 2
        assert all(isinstance(qa, QAPair) for qa in result.qa_pairs)

        assert result.qa_pairs[0].question == "Q1?"
        assert result.qa_pairs[0].answer == "A1"
        assert result.qa_pairs[0].topic == "intro"
        assert result.qa_pairs[0].follow_ups == ["FU1"]

        assert result.qa_pairs[1].question == "Q2?"
        assert result.qa_pairs[1].answer == "A2"
        assert result.qa_pairs[1].topic == "tech"
        assert result.qa_pairs[1].follow_ups == []  # default

    def test_build_qa_pair_defaults(self, extractor):
        """QAPair defaults are applied for missing keys."""
        data = {
            "qa_pairs": [
                {"question": "Only question"}
            ]
        }
        result = extractor._build_interview_anketa(data, 0.0)

        assert len(result.qa_pairs) == 1
        qa = result.qa_pairs[0]
        assert qa.question == "Only question"
        assert qa.answer == ""
        assert qa.topic == "general"
        assert qa.follow_ups == []

    def test_build_ai_recommendations_as_objects(self, extractor):
        """ai_recommendations are built as AIRecommendation model instances."""
        data = {
            "ai_recommendations": [
                {
                    "recommendation": "Use caching",
                    "impact": "50% faster",
                    "priority": "high",
                    "effort": "low"
                },
                {
                    "recommendation": "Add monitoring",
                    "impact": "Better observability",
                    "priority": "medium",
                    "effort": "medium"
                }
            ]
        }
        result = extractor._build_interview_anketa(data, 0.0)

        assert len(result.ai_recommendations) == 2
        assert all(isinstance(r, AIRecommendation) for r in result.ai_recommendations)

        assert result.ai_recommendations[0].recommendation == "Use caching"
        assert result.ai_recommendations[0].impact == "50% faster"
        assert result.ai_recommendations[0].priority == "high"
        assert result.ai_recommendations[0].effort == "low"

        assert result.ai_recommendations[1].priority == "medium"
        assert result.ai_recommendations[1].effort == "medium"

    def test_build_ai_recommendation_defaults(self, extractor):
        """AIRecommendation defaults are applied for missing keys."""
        data = {
            "ai_recommendations": [
                {"recommendation": "Do something", "impact": "Good"}
            ]
        }
        result = extractor._build_interview_anketa(data, 0.0)

        assert len(result.ai_recommendations) == 1
        rec = result.ai_recommendations[0]
        assert rec.recommendation == "Do something"
        assert rec.impact == "Good"
        assert rec.priority == "medium"  # default
        assert rec.effort == "medium"  # default

    def test_build_invalid_qa_pairs_skipped(self, extractor):
        """Non-dict items in qa_pairs are silently skipped."""
        data = {
            "qa_pairs": [
                {"question": "Valid Q?", "answer": "Valid A"},
                "not a dict",
                123,
                None,
                ["also", "invalid"],
                {"question": "Another valid Q?", "answer": "Another A"},
            ]
        }
        result = extractor._build_interview_anketa(data, 0.0)

        assert len(result.qa_pairs) == 2
        assert result.qa_pairs[0].question == "Valid Q?"
        assert result.qa_pairs[1].question == "Another valid Q?"

    def test_build_invalid_ai_recommendations_skipped(self, extractor):
        """Non-dict items in ai_recommendations are silently skipped."""
        data = {
            "ai_recommendations": [
                {"recommendation": "Valid", "impact": "Good"},
                "not a dict",
                42,
                None,
                {"recommendation": "Also valid", "impact": "Great"},
            ]
        }
        result = extractor._build_interview_anketa(data, 0.0)

        assert len(result.ai_recommendations) == 2
        assert result.ai_recommendations[0].recommendation == "Valid"
        assert result.ai_recommendations[1].recommendation == "Also valid"

    def test_build_duration_seconds_set_correctly(self, extractor):
        """duration_seconds is set correctly on the anketa."""
        result = extractor._build_interview_anketa({}, 999.5)
        assert result.consultation_duration_seconds == pytest.approx(999.5)

    def test_build_duration_seconds_zero(self, extractor):
        """duration_seconds=0 is valid."""
        result = extractor._build_interview_anketa({}, 0.0)
        assert result.consultation_duration_seconds == pytest.approx(0.0)

    def test_build_duration_seconds_large_value(self, extractor):
        """Large duration_seconds values are preserved."""
        result = extractor._build_interview_anketa({}, 36000.0)  # 10 hours
        assert result.consultation_duration_seconds == pytest.approx(36000.0)

    def test_build_anketa_type_always_interview(self, extractor):
        """anketa_type is always 'interview' regardless of input."""
        result = extractor._build_interview_anketa({}, 0.0)
        assert result.anketa_type == "interview"

    def test_build_anketa_type_interview_with_full_data(
        self, extractor, full_interview_llm_response
    ):
        """anketa_type is 'interview' even with full data."""
        data = json.loads(full_interview_llm_response)
        result = extractor._build_interview_anketa(data, 100.0)
        assert result.anketa_type == "interview"

    def test_build_anketa_type_not_overridden_by_data(self, extractor):
        """anketa_type cannot be overridden by data dict (model default takes precedence)."""
        # The _build_interview_anketa method does not pass anketa_type from data,
        # so the model default "interview" is always used
        data = {"anketa_type": "consultation"}  # Attempt to override
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.anketa_type == "interview"

    def test_build_detected_topics_list(self, extractor):
        """detected_topics is set from data."""
        data = {"detected_topics": ["topic_a", "topic_b", "topic_c"]}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.detected_topics == ["topic_a", "topic_b", "topic_c"]

    def test_build_key_quotes_list(self, extractor):
        """key_quotes is set from data."""
        data = {"key_quotes": ["Quote one", "Quote two"]}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.key_quotes == ["Quote one", "Quote two"]

    def test_build_key_insights_list(self, extractor):
        """key_insights is set from data."""
        data = {"key_insights": ["Insight A", "Insight B"]}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.key_insights == ["Insight A", "Insight B"]

    def test_build_unresolved_topics_list(self, extractor):
        """unresolved_topics is set from data."""
        data = {"unresolved_topics": ["Topic X", "Topic Y"]}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.unresolved_topics == ["Topic X", "Topic Y"]

    def test_build_summary_string(self, extractor):
        """summary is set from data."""
        data = {"summary": "A comprehensive interview summary."}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.summary == "A comprehensive interview summary."

    def test_build_interview_type_from_data(self, extractor):
        """interview_type is set from data when provided."""
        data = {"interview_type": "hr"}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.interview_type == "hr"

    def test_build_interview_type_default(self, extractor):
        """interview_type defaults to 'general' when not in data."""
        result = extractor._build_interview_anketa({}, 0.0)
        assert result.interview_type == "general"

    def test_build_with_empty_qa_pairs_list(self, extractor):
        """Empty qa_pairs list in data results in empty list on anketa."""
        data = {"qa_pairs": []}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.qa_pairs == []

    def test_build_with_empty_ai_recommendations_list(self, extractor):
        """Empty ai_recommendations list in data results in empty list on anketa."""
        data = {"ai_recommendations": []}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.ai_recommendations == []

    def test_build_missing_qa_pairs_key(self, extractor):
        """Missing qa_pairs key in data results in empty list."""
        data = {"company_name": "Test"}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.qa_pairs == []

    def test_build_missing_ai_recommendations_key(self, extractor):
        """Missing ai_recommendations key in data results in empty list."""
        data = {"company_name": "Test"}
        result = extractor._build_interview_anketa(data, 0.0)
        assert result.ai_recommendations == []

    def test_build_qa_pair_with_all_fields(self, extractor):
        """QAPair with all fields set correctly."""
        data = {
            "qa_pairs": [
                {
                    "question": "Detailed question?",
                    "answer": "Detailed answer.",
                    "topic": "specific_topic",
                    "follow_ups": ["Follow-up 1", "Follow-up 2"]
                }
            ]
        }
        result = extractor._build_interview_anketa(data, 0.0)

        qa = result.qa_pairs[0]
        assert qa.question == "Detailed question?"
        assert qa.answer == "Detailed answer."
        assert qa.topic == "specific_topic"
        assert qa.follow_ups == ["Follow-up 1", "Follow-up 2"]

    def test_build_preserves_anketa_id(self, extractor):
        """Each built InterviewAnketa gets a unique anketa_id."""
        result1 = extractor._build_interview_anketa({}, 0.0)
        result2 = extractor._build_interview_anketa({}, 0.0)

        assert result1.anketa_id != ""
        assert result2.anketa_id != ""
        assert result1.anketa_id != result2.anketa_id

    def test_build_partial_data_no_crash(self, extractor):
        """Partial data dict does not cause crashes; missing keys get defaults."""
        data = {
            "contact_name": "Partial Person",
            "qa_pairs": [{"question": "One question?"}],
        }
        result = extractor._build_interview_anketa(data, 42.0)

        assert result.contact_name == "Partial Person"
        assert result.company_name == ""
        assert result.contact_role == ""
        assert len(result.qa_pairs) == 1
        assert result.qa_pairs[0].answer == ""
        assert result.consultation_duration_seconds == pytest.approx(42.0)


# ============================================================================
# INTEGRATION: FULL INTERVIEW FLOW VIA extract()
# ============================================================================

class TestInterviewFullFlow:
    """Integration tests for the complete interview extraction flow via extract()."""

    @pytest.mark.asyncio
    async def test_full_interview_flow_success(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Full flow: extract(consultation_type='interview') produces correct InterviewAnketa."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            result = await extractor.extract(
                sample_interview_dialogue,
                duration_seconds=600.0,
                consultation_type="interview",
            )

        assert isinstance(result, InterviewAnketa)
        assert result.company_name == "DataFlow"
        assert result.contact_name == "Алексей Смирнов"
        assert len(result.qa_pairs) == 3
        assert len(result.ai_recommendations) == 2
        assert result.consultation_duration_seconds == pytest.approx(600.0)
        assert result.anketa_type == "interview"

    @pytest.mark.asyncio
    async def test_full_interview_flow_llm_failure(
        self, extractor, sample_interview_dialogue
    ):
        """Full flow: LLM failure returns empty InterviewAnketa, not FinalAnketa."""
        extractor.llm.chat = AsyncMock(side_effect=RuntimeError("Service unavailable"))

        result = await extractor.extract(
            sample_interview_dialogue,
            duration_seconds=100.0,
            consultation_type="interview",
        )

        assert isinstance(result, InterviewAnketa)
        assert result.company_name == ""
        assert result.qa_pairs == []
        assert result.consultation_duration_seconds == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_full_interview_flow_empty_dialogue(self, extractor):
        """Full flow: empty dialogue with interview type returns InterviewAnketa."""
        extractor.llm.chat = AsyncMock(return_value='{}')

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=({}, False)
        ):
            result = await extractor.extract(
                [],
                duration_seconds=0.0,
                consultation_type="interview",
            )

        assert isinstance(result, InterviewAnketa)
        assert result.qa_pairs == []

    @pytest.mark.asyncio
    async def test_interview_and_consultation_produce_different_types(
        self, extractor, sample_interview_dialogue,
        full_interview_llm_response, consultation_llm_response, expert_llm_response
    ):
        """Same extractor produces InterviewAnketa or FinalAnketa based on consultation_type."""
        # Interview path
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)
        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            interview_result = await extractor.extract(
                sample_interview_dialogue,
                duration_seconds=100.0,
                consultation_type="interview",
            )

        # Consultation path
        extractor.llm.chat = AsyncMock(
            side_effect=[consultation_llm_response, expert_llm_response]
        )
        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(consultation_llm_response), False)
        ):
            with patch.object(
                extractor.post_processor, 'process',
                return_value=(json.loads(consultation_llm_response), {'cleaning_changes': []})
            ):
                consultation_result = await extractor.extract(
                    sample_interview_dialogue,
                    duration_seconds=100.0,
                    consultation_type="consultation",
                )

        assert isinstance(interview_result, InterviewAnketa)
        assert isinstance(consultation_result, FinalAnketa)
        assert not isinstance(consultation_result, InterviewAnketa)

    @pytest.mark.asyncio
    async def test_interview_llm_called_once(
        self, extractor, sample_interview_dialogue, full_interview_llm_response
    ):
        """Interview extraction calls LLM exactly once (no expert content generation)."""
        extractor.llm.chat = AsyncMock(return_value=full_interview_llm_response)

        with patch.object(
            extractor, '_parse_json_with_repair',
            return_value=(json.loads(full_interview_llm_response), False)
        ):
            await extractor.extract(
                sample_interview_dialogue,
                duration_seconds=100.0,
                consultation_type="interview",
            )

        assert extractor.llm.chat.call_count == 1
