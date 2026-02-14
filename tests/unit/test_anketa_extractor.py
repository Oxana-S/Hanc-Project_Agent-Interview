"""
Comprehensive tests for src/anketa/extractor.py

Tests cover:
- AnketaExtractor initialization
- extract() method with various inputs
- _build_extraction_prompt() method
- JSON parsing and repair methods
- _build_anketa() method
- Helper extraction methods
- Fallback anketa building
- Expert content generation
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.anketa.extractor import AnketaExtractor
from src.anketa.schema import (
    FinalAnketa, AgentFunction, Integration,
    FAQItem, ObjectionHandler, DialogueExample, FinancialMetric,
    Competitor, MarketInsight, EscalationRule, KPIMetric,
    ChecklistItem, AIRecommendation, TargetAudienceSegment
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
def extractor_no_smart():
    """Create extractor without smart extraction."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value='{}')
    return AnketaExtractor(llm=llm, use_smart_extraction=False)


@pytest.fixture
def sample_dialogue():
    """Sample dialogue history."""
    return [
        {"role": "assistant", "content": "Добрый день! Как могу помочь?"},
        {"role": "user", "content": "Здравствуйте! Меня зовут Иван, я директор компании АльфаТех."},
        {"role": "assistant", "content": "Приятно познакомиться, Иван! Расскажите о вашем бизнесе."},
        {"role": "user", "content": "Мы занимаемся IT-консалтингом, работаем с корпоративными клиентами."},
    ]


@pytest.fixture
def sample_analysis():
    """Sample business analysis."""
    return {
        "company_name": "АльфаТех",
        "industry": "IT",
        "specialization": "IT-консалтинг",
        "pain_points": [
            {"description": "Много рутинных звонков"},
            "Долгое время ожидания"
        ],
        "opportunities": [
            {"description": "Автоматизация обработки заявок"},
            "Увеличение конверсии"
        ],
        "constraints": ["Работа только с юрлицами", "дружелюбный голос"],
        "client_type": "B2B",
        "services": [{"name": "Консалтинг"}, {"name": "Аудит"}],
        "industry_insights": ["Рост рынка IT", "Тренд на автоматизацию"]
    }


@pytest.fixture
def sample_solution():
    """Sample proposed solution."""
    return {
        "agent_name": "АльфаБот",
        "agent_purpose": "Квалификация лидов и консультирование",
        "main_function": {
            "name": "Квалификация лидов",
            "description": "Определение потребностей клиента",
            "priority": "high"
        },
        "additional_functions": [
            {"name": "Консультирование", "description": "Ответы на типовые вопросы", "priority": "medium"}
        ],
        "integrations": [
            {"name": "CRM", "purpose": "Запись данных", "required": True},
            {"name": "Календарь", "reason": "Бронирование", "needed": False}
        ],
        "typical_questions": ["Какие услуги?", "Сколько стоит?"],
        "expected_results": "Увеличение конверсии на 30%"
    }


@pytest.fixture
def full_llm_response():
    """Full LLM JSON response."""
    return json.dumps({
        "company_name": "АльфаТех",
        "industry": "IT",
        "specialization": "IT-консалтинг",
        "website": "https://alphatech.ru",
        "contact_name": "Иван Петров",
        "contact_role": "Директор",
        "business_description": "IT-консалтинг для корпоративных клиентов",
        "services": ["Консалтинг", "Аудит"],
        "client_types": ["B2B", "Корпорации"],
        "current_problems": ["Много рутинных звонков"],
        "business_goals": ["Автоматизация"],
        "constraints": ["Только юрлица"],
        "agent_name": "АльфаБот",
        "agent_purpose": "Квалификация лидов",
        "agent_functions": [
            {"name": "Квалификация", "description": "Определение потребностей", "priority": "high"}
        ],
        "typical_questions": ["Какие услуги?"],
        "voice_gender": "female",
        "voice_tone": "professional",
        "language": "ru",
        "call_direction": "inbound",
        "integrations": [
            {"name": "CRM", "purpose": "Запись данных", "required": True}
        ],
        "main_function": {"name": "Квалификация", "description": "Лиды", "priority": "high"},
        "additional_functions": []
    })


@pytest.fixture
def expert_llm_response():
    """Expert content LLM response."""
    return json.dumps({
        "faq_items": [
            {"question": "Какие услуги?", "answer": "IT-консалтинг", "category": "general"}
        ],
        "objection_handlers": [
            {"objection": "Дорого", "response": "Понимаю", "follow_up": "Предложить скидку"}
        ],
        "sample_dialogue": [
            {"role": "bot", "message": "Здравствуйте!", "intent": "greeting"}
        ],
        "financial_metrics": [
            {"name": "ROI", "value": "150%", "source": "benchmark", "note": "За год"}
        ],
        "competitors": [
            {"name": "КонкурентCo", "strengths": ["Дешевле"], "weaknesses": ["Меньше опыта"], "price_range": "10-50k"}
        ],
        "market_insights": [
            {"insight": "Рост рынка", "source": "IDC", "relevance": "high"}
        ],
        "escalation_rules": [
            {"trigger": "Жалоба", "urgency": "immediate", "action": "Перевод на менеджера"}
        ],
        "success_kpis": [
            {"name": "Конверсия", "target": ">20%", "benchmark": "15%", "measurement": "Лиды/Звонки"}
        ],
        "launch_checklist": [
            {"item": "Настроить CRM", "required": True, "responsible": "team"}
        ],
        "ai_recommendations": [
            {"recommendation": "Добавить FAQ", "impact": "Высокий", "priority": "high", "effort": "low"}
        ],
        "target_segments": [
            {"name": "Малый бизнес", "description": "До 50 человек", "pain_points": ["Бюджет"], "triggers": ["Рост"]}
        ],
        "tone_of_voice": {"do": "Быть вежливым", "dont": "Не торопить"},
        "error_handling_scripts": {"not_understood": "Уточните, пожалуйста"},
        "follow_up_sequence": ["Письмо", "Звонок"],
        "competitive_advantages": ["Опыт", "Качество"]
    })


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestAnketaExtractorInit:
    """Tests for AnketaExtractor initialization."""

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        with patch('src.anketa.extractor.create_llm_client'):
            extractor = AnketaExtractor()
            assert extractor.strict_cleaning is True
            assert extractor.use_smart_extraction is True
            assert extractor.max_json_retries == 3
            assert extractor.cleaner is not None
            assert extractor.smart_extractor is not None
            assert extractor.post_processor is not None

    def test_init_with_custom_llm(self, mock_llm):
        """Test initialization with custom LLM."""
        extractor = AnketaExtractor(llm=mock_llm)
        assert extractor.llm is mock_llm

    def test_init_strict_cleaning_false(self, mock_llm):
        """Test initialization with strict_cleaning=False."""
        extractor = AnketaExtractor(llm=mock_llm, strict_cleaning=False)
        assert extractor.strict_cleaning is False

    def test_init_no_smart_extraction(self, mock_llm):
        """Test initialization with use_smart_extraction=False."""
        extractor = AnketaExtractor(llm=mock_llm, use_smart_extraction=False)
        assert extractor.smart_extractor is None

    def test_init_custom_max_retries(self, mock_llm):
        """Test initialization with custom max_json_retries."""
        extractor = AnketaExtractor(llm=mock_llm, max_json_retries=5)
        assert extractor.max_json_retries == 5


# ============================================================================
# PROMPT BUILDING TESTS
# ============================================================================

class TestBuildExtractionPrompt:
    """Tests for _build_extraction_prompt method."""

    def test_build_prompt_with_dialogue(self, extractor, sample_dialogue):
        """Test prompt building with dialogue."""
        prompt = extractor._build_extraction_prompt(sample_dialogue, {}, {}, None)

        assert "ДИАЛОГ КОНСУЛЬТАЦИИ:" in prompt
        assert "АльфаТех" in prompt
        assert "IT-консалтинг" in prompt

    def test_build_prompt_with_analysis(self, extractor, sample_dialogue, sample_analysis):
        """Test prompt building with business analysis."""
        prompt = extractor._build_extraction_prompt(sample_dialogue, sample_analysis, {}, None)

        assert "АНАЛИЗ БИЗНЕСА:" in prompt
        assert "АльфаТех" in prompt
        assert "IT" in prompt

    def test_build_prompt_with_solution(self, extractor, sample_dialogue, sample_solution):
        """Test prompt building with proposed solution."""
        prompt = extractor._build_extraction_prompt(sample_dialogue, {}, sample_solution, None)

        assert "ПРЕДЛОЖЕННОЕ РЕШЕНИЕ:" in prompt
        assert "Квалификация лидов" in prompt

    def test_build_prompt_with_document_context(self, extractor, sample_dialogue):
        """Test prompt building with document context."""
        doc_context = MagicMock()
        doc_context.to_prompt_context.return_value = "Документ: Прайс-лист"

        prompt = extractor._build_extraction_prompt(sample_dialogue, {}, {}, doc_context)

        assert "ДОКУМЕНТЫ КЛИЕНТА:" in prompt
        assert "Прайс-лист" in prompt

    def test_build_prompt_with_document_summary(self, extractor, sample_dialogue):
        """Test prompt building with document summary fallback."""
        doc_context = MagicMock()
        doc_context.summary = "Краткое резюме документов"
        del doc_context.to_prompt_context

        prompt = extractor._build_extraction_prompt(sample_dialogue, {}, {}, doc_context)

        assert "Краткое резюме документов" in prompt

    def test_build_prompt_truncates_dialogue(self, extractor):
        """Test that dialogue is truncated to last 100 messages."""
        long_dialogue = [{"role": "user", "content": f"Сообщение {i}"} for i in range(200)]

        prompt = extractor._build_extraction_prompt(long_dialogue, {}, {}, None)

        # Should only include last 100
        assert "Сообщение 199" in prompt
        assert "Сообщение 100" in prompt
        assert "Сообщение 99" not in prompt


# ============================================================================
# FORMAT HELPER TESTS
# ============================================================================

class TestFormatHelpers:
    """Tests for format helper methods."""

    def test_format_pain_points_empty(self, extractor):
        """Test formatting empty pain points."""
        result = extractor._format_pain_points([])
        assert result == "[]"

    def test_format_pain_points_dict_list(self, extractor):
        """Test formatting pain points with dicts."""
        pain_points = [
            {"description": "Проблема 1"},
            {"description": "Проблема 2"}
        ]
        result = extractor._format_pain_points(pain_points)
        assert "Проблема 1" in result
        assert "Проблема 2" in result

    def test_format_pain_points_string_list(self, extractor):
        """Test formatting pain points with strings."""
        pain_points = ["Проблема А", "Проблема Б"]
        result = extractor._format_pain_points(pain_points)
        assert "Проблема А" in result
        assert "Проблема Б" in result

    def test_format_opportunities_empty(self, extractor):
        """Test formatting empty opportunities."""
        result = extractor._format_opportunities([])
        assert result == "[]"

    def test_format_opportunities_mixed(self, extractor):
        """Test formatting mixed opportunities."""
        opportunities = [
            {"description": "Возможность 1"},
            "Возможность 2"
        ]
        result = extractor._format_opportunities(opportunities)
        assert "Возможность 1" in result
        assert "Возможность 2" in result


# ============================================================================
# JSON PARSING TESTS
# ============================================================================

class TestJsonParsing:
    """Tests for JSON parsing methods."""

    def test_extract_json_from_markdown_json_block(self, extractor):
        """Test extracting JSON from ```json block."""
        text = '```json\n{"key": "value"}\n```'
        result = extractor._extract_json_from_markdown(text)
        assert '{"key": "value"}' in result

    def test_extract_json_from_markdown_plain_block(self, extractor):
        """Test extracting JSON from plain ``` block."""
        text = '```\n{"key": "value"}\n```'
        result = extractor._extract_json_from_markdown(text)
        assert '{"key": "value"}' in result

    def test_extract_json_from_markdown_no_block(self, extractor):
        """Test extracting JSON without markdown blocks."""
        text = '{"key": "value"}'
        result = extractor._extract_json_from_markdown(text)
        assert text == result

    def test_fix_common_json_errors_trailing_comma(self, extractor):
        """Test fixing trailing commas."""
        json_with_trailing = '{"key": "value",}'
        result = extractor._fix_common_json_errors(json_with_trailing)
        assert result == '{"key": "value"}'

    def test_fix_common_json_errors_trailing_comma_array(self, extractor):
        """Test fixing trailing commas in arrays."""
        json_with_trailing = '["a", "b",]'
        result = extractor._fix_common_json_errors(json_with_trailing)
        assert result == '["a", "b"]'

    def test_find_balanced_json(self, extractor):
        """Test finding balanced JSON."""
        text = '{"key": "value"} extra text'
        result = extractor._find_balanced_json(text)
        assert result == '{"key": "value"}'

    def test_find_balanced_json_nested(self, extractor):
        """Test finding balanced JSON with nesting."""
        text = '{"outer": {"inner": "value"}} more'
        result = extractor._find_balanced_json(text)
        assert result == '{"outer": {"inner": "value"}}'

    def test_parse_json_response_direct(self, extractor):
        """Test parsing valid JSON directly."""
        response = '{"company_name": "Test"}'
        result = extractor._parse_json_response(response)
        assert result["company_name"] == "Test"

    def test_parse_json_response_with_markdown(self, extractor):
        """Test parsing JSON from markdown."""
        response = '```json\n{"company_name": "Test"}\n```'
        result = extractor._parse_json_response(response)
        assert result["company_name"] == "Test"

    def test_parse_json_response_with_trailing_comma(self, extractor):
        """Test parsing JSON with trailing comma."""
        response = '{"company_name": "Test",}'
        result = extractor._parse_json_response(response)
        assert result["company_name"] == "Test"


# ============================================================================
# BUILD ANKETA TESTS
# ============================================================================

class TestBuildAnketa:
    """Tests for _build_anketa method."""

    def test_build_anketa_minimal(self, extractor):
        """Test building anketa with minimal data."""
        data = {"company_name": "TestCo"}
        anketa = extractor._build_anketa(data, 100.0)

        assert anketa.company_name == "TestCo"
        assert anketa.consultation_duration_seconds == pytest.approx(100.0)
        assert isinstance(anketa, FinalAnketa)

    def test_build_anketa_full_data(self, extractor, full_llm_response):
        """Test building anketa with full data."""
        data = json.loads(full_llm_response)
        anketa = extractor._build_anketa(data, 300.0)

        assert anketa.company_name == "АльфаТех"
        assert anketa.industry == "IT"
        assert anketa.specialization == "IT-консалтинг"
        assert anketa.website == "https://alphatech.ru"
        assert anketa.contact_name == "Иван Петров"
        assert anketa.contact_role == "Директор"
        assert anketa.agent_name == "АльфаБот"
        assert anketa.voice_gender == "female"
        assert anketa.voice_tone == "professional"
        assert anketa.language == "ru"
        assert anketa.call_direction == "inbound"
        assert len(anketa.services) == 2
        assert len(anketa.agent_functions) == 1
        assert len(anketa.integrations) == 1

    def test_build_anketa_with_main_function(self, extractor):
        """Test building anketa with main function."""
        data = {
            "company_name": "Test",
            "main_function": {
                "name": "Квалификация",
                "description": "Определение потребностей",
                "priority": "high"
            }
        }
        anketa = extractor._build_anketa(data, 0)

        assert anketa.main_function is not None
        assert anketa.main_function.name == "Квалификация"
        assert anketa.main_function.priority == "high"

    def test_build_anketa_with_additional_functions(self, extractor):
        """Test building anketa with additional functions."""
        data = {
            "company_name": "Test",
            "additional_functions": [
                {"name": "Функция 1", "description": "Описание 1"},
                {"name": "Функция 2", "description": "Описание 2", "priority": "low"}
            ]
        }
        anketa = extractor._build_anketa(data, 0)

        assert len(anketa.additional_functions) == 2
        assert anketa.additional_functions[0].name == "Функция 1"
        assert anketa.additional_functions[1].priority == "low"

    def test_build_anketa_with_integrations(self, extractor):
        """Test building anketa with integrations."""
        data = {
            "company_name": "Test",
            "integrations": [
                {"name": "CRM", "purpose": "Запись", "required": True},
                {"name": "Calendar", "purpose": "Бронирование", "required": False}
            ]
        }
        anketa = extractor._build_anketa(data, 0)

        assert len(anketa.integrations) == 2
        assert anketa.integrations[0].required is True
        assert anketa.integrations[1].required is False


# ============================================================================
# EXTRACTION HELPER TESTS
# ============================================================================

class TestExtractionHelpers:
    """Tests for extraction helper methods."""

    def test_extract_string_list_strings(self, extractor):
        """Test extracting from string list."""
        items = ["Услуга 1", "Услуга 2", ""]
        result = extractor._extract_string_list(items)
        assert result == ["Услуга 1", "Услуга 2"]

    def test_extract_string_list_dicts(self, extractor):
        """Test extracting from dict list."""
        items = [
            {"description": "Услуга 1"},
            {"name": "Услуга 2"},
            {"type": "Услуга 3"}
        ]
        result = extractor._extract_string_list(items)
        assert "Услуга 1" in result
        assert "Услуга 2" in result
        assert "Услуга 3" in result

    def test_extract_functions_list(self, extractor):
        """Test extracting functions list."""
        items = [
            {"name": "Функция 1", "description": "Описание 1"},
            {"name": "Функция 2", "description": "Описание 2", "priority": "low"}
        ]
        result = extractor._extract_functions_list(items)

        assert len(result) == 2
        assert all(isinstance(f, AgentFunction) for f in result)
        assert result[0].priority == "medium"  # default
        assert result[1].priority == "low"

    def test_extract_integrations_list(self, extractor):
        """Test extracting integrations list."""
        items = [
            {"name": "CRM", "purpose": "Запись", "required": True},
            {"name": "Calendar", "reason": "Бронирование", "needed": False}
        ]
        result = extractor._extract_integrations_list(items)

        assert len(result) == 2
        assert all(isinstance(i, Integration) for i in result)
        assert result[0].purpose == "Запись"
        assert result[1].purpose == "Бронирование"
        assert result[0].required is True
        assert result[1].required is False


# ============================================================================
# EXTRACT FROM ANALYSIS TESTS
# ============================================================================

class TestExtractFromAnalysis:
    """Tests for _extract_from_analysis method."""

    def test_extract_from_analysis_full(self, extractor, sample_analysis):
        """Test extracting from full analysis."""
        result = extractor._extract_from_analysis(sample_analysis)

        assert result["company_name"] == "АльфаТех"
        assert result["industry"] == "IT"
        assert result["specialization"] == "IT-консалтинг"
        assert len(result["current_problems"]) == 2
        assert len(result["business_goals"]) == 2
        assert "B2B" in result["client_types"]

    def test_extract_from_analysis_empty(self, extractor):
        """Test extracting from empty analysis."""
        result = extractor._extract_from_analysis({})

        assert result["company_name"] == ""
        assert result["industry"] == ""
        assert result["current_problems"] == []

    def test_extract_from_analysis_industry_insights(self, extractor):
        """Test industry insights used as constraints fallback."""
        analysis = {
            "industry_insights": ["Insight 1", "Insight 2", "Insight 3", "Insight 4"]
        }
        result = extractor._extract_from_analysis(analysis)

        assert len(result["constraints"]) == 3  # Only first 3


# ============================================================================
# EXTRACT FROM SOLUTION TESTS
# ============================================================================

class TestExtractFromSolution:
    """Tests for _extract_from_solution method."""

    def test_extract_from_solution_full(self, extractor, sample_solution):
        """Test extracting from full solution."""
        result = extractor._extract_from_solution(sample_solution)

        assert result["agent_name"] == "АльфаБот"
        assert result["agent_purpose"] == "Квалификация лидов и консультирование"
        assert result["main_function"] is not None
        assert len(result["additional_functions"]) == 1
        assert len(result["integrations"]) == 2

    def test_extract_from_solution_empty(self, extractor):
        """Test extracting from empty solution."""
        result = extractor._extract_from_solution({})

        assert result["agent_name"] == ""
        assert result["main_function"] is None
        assert result["additional_functions"] == []

    def test_extract_from_solution_generated_agent_name(self, extractor):
        """Test agent name generation when not provided."""
        solution = {
            "main_function": {"name": "Test", "description": "Test"}
        }
        result = extractor._extract_from_solution(solution)

        assert result["agent_name"] == "Виртуальный ассистент"


# ============================================================================
# VOICE SETTINGS TESTS
# ============================================================================

class TestVoiceSettings:
    """Tests for voice settings extraction."""

    def test_extract_voice_settings_default(self, extractor):
        """Test default voice settings."""
        result = extractor._extract_voice_settings_from_constraints([])

        assert result["voice_gender"] == "female"
        assert result["voice_tone"] == "professional"

    def test_extract_voice_settings_male(self, extractor):
        """Test male voice detection."""
        result = extractor._extract_voice_settings_from_constraints(["Нужен мужской голос"])

        assert result["voice_gender"] == "male"

    def test_extract_voice_settings_friendly(self, extractor):
        """Test friendly tone detection."""
        result = extractor._extract_voice_settings_from_constraints(["Дружелюбный тон"])

        assert result["voice_tone"] == "friendly"

    def test_extract_voice_settings_calm(self, extractor):
        """Test calm tone detection."""
        result = extractor._extract_voice_settings_from_constraints(["Спокойный голос"])

        assert result["voice_tone"] == "calm"

    def test_extract_voice_settings_confident(self, extractor):
        """Test confident tone detection."""
        result = extractor._extract_voice_settings_from_constraints(["Уверенный профессионал"])

        assert result["voice_tone"] == "confident, professional"


# ============================================================================
# CALL DIRECTION TESTS
# ============================================================================

class TestCallDirection:
    """Tests for call direction determination."""

    def test_determine_call_direction_default(self, extractor):
        """Test default call direction."""
        result = extractor._determine_call_direction([], [])
        assert result == "inbound"

    def test_determine_call_direction_outbound(self, extractor):
        """Test outbound detection."""
        result = extractor._determine_call_direction(["Исходящие звонки"], [])
        assert result == "outbound"

    def test_determine_call_direction_inbound_explicit(self, extractor):
        """Test explicit inbound detection."""
        result = extractor._determine_call_direction([], ["Обработка входящих"])
        assert result == "inbound"


# ============================================================================
# GENERATE TYPICAL QUESTIONS TESTS
# ============================================================================

class TestGenerateTypicalQuestions:
    """Tests for typical questions generation."""

    def test_generate_questions_qualification(self, extractor):
        """Test questions for qualification function."""
        main_func = AgentFunction(name="Квалификация лидов", description="", priority="high")
        result = extractor._generate_typical_questions("", "", main_func, [])

        assert any("условия" in q.lower() for q in result)

    def test_generate_questions_booking(self, extractor):
        """Test questions for booking function."""
        main_func = AgentFunction(name="Запись на приём", description="", priority="high")
        result = extractor._generate_typical_questions("", "", main_func, [])

        assert any("записаться" in q.lower() for q in result)

    def test_generate_questions_wellness(self, extractor):
        """Test questions for wellness industry."""
        result = extractor._generate_typical_questions("wellness", "массаж", None, [])

        assert any("сеанс" in q.lower() for q in result)

    def test_generate_questions_franchise(self, extractor):
        """Test questions for franchise business."""
        result = extractor._generate_typical_questions("", "франчайзинг", None, [])

        assert any("паушальн" in q.lower() for q in result)

    def test_generate_questions_b2b(self, extractor):
        """Test questions for B2B clients."""
        result = extractor._generate_typical_questions("", "", None, ["B2B"])

        assert any("юрлиц" in q.lower() for q in result)

    def test_generate_questions_max_5(self, extractor):
        """Test that max 5 questions are generated."""
        main_func = AgentFunction(name="Квалификация лидов", description="", priority="high")
        result = extractor._generate_typical_questions("wellness", "франчайзинг", main_func, ["B2B"])

        assert len(result) <= 5


# ============================================================================
# GENERATE SERVICES TESTS
# ============================================================================

class TestGenerateServices:
    """Tests for services generation."""

    def test_generate_services_massage(self, extractor):
        """Test services for massage business."""
        result = extractor._generate_services_from_context("массаж", "", "")

        assert any("массаж" in s.lower() for s in result)

    def test_generate_services_franchise(self, extractor):
        """Test services for franchise business."""
        result = extractor._generate_services_from_context("франчайзинг", "", "")

        assert any("франшиз" in s.lower() for s in result)

    def test_generate_services_generic(self, extractor):
        """Test generic services generation."""
        result = extractor._generate_services_from_context("", "IT", "")

        assert len(result) > 0
        assert any("IT" in s for s in result)


# ============================================================================
# FALLBACK ANKETA TESTS
# ============================================================================

class TestBuildFallbackAnketa:
    """Tests for _build_fallback_anketa method."""

    def test_fallback_anketa_with_analysis_and_solution(self, extractor, sample_dialogue, sample_analysis, sample_solution):
        """Test fallback anketa building."""
        anketa = extractor._build_fallback_anketa(
            sample_dialogue, sample_analysis, sample_solution, 300.0
        )

        assert anketa.company_name == "АльфаТех"
        assert anketa.industry == "IT"
        assert anketa.agent_name == "АльфаБот"
        assert anketa.consultation_duration_seconds == pytest.approx(300.0)
        assert isinstance(anketa, FinalAnketa)

    def test_fallback_anketa_empty_inputs(self, extractor):
        """Test fallback anketa with empty inputs."""
        anketa = extractor._build_fallback_anketa([], None, None, 0)

        assert anketa.company_name == ""
        assert anketa.agent_name == "Виртуальный ассистент"

    def test_fallback_anketa_generated_agent_name(self, extractor, sample_analysis):
        """Test agent name generation in fallback."""
        anketa = extractor._build_fallback_anketa([], sample_analysis, {}, 0)

        assert "АльфаТех" in anketa.agent_name or "Ассистент" in anketa.agent_name

    def test_fallback_anketa_voice_settings(self, extractor):
        """Test voice settings in fallback."""
        analysis = {"constraints": ["дружелюбный голос", "мужской"]}
        anketa = extractor._build_fallback_anketa([], analysis, {}, 0)

        assert anketa.voice_tone == "friendly"
        assert anketa.voice_gender == "male"


# ============================================================================
# EXPERT CONTENT TESTS
# ============================================================================

class TestExpertContent:
    """Tests for expert content generation."""

    def test_build_expert_context(self, extractor):
        """Test building expert context."""
        anketa = FinalAnketa(
            company_name="Test",
            industry="IT",
            services=["Консалтинг"],
            main_function=AgentFunction(name="Test", description="Test", priority="high")
        )

        context = extractor._build_expert_context(anketa)

        assert context["company_name"] == "Test"
        assert context["industry"] == "IT"
        assert context["main_function"] is not None

    @pytest.mark.asyncio
    async def test_generate_expert_content_success(self, extractor, expert_llm_response):
        """Test successful expert content generation."""
        extractor.llm.chat = AsyncMock(return_value=expert_llm_response)

        anketa = FinalAnketa(company_name="Test", industry="IT")
        result = await extractor._generate_expert_content(anketa)

        assert len(result.faq_items) > 0
        assert len(result.objection_handlers) > 0
        assert result.anketa_version == "2.0"

    @pytest.mark.asyncio
    async def test_generate_expert_content_fallback(self, extractor):
        """Test expert content fallback on LLM failure."""
        extractor.llm.chat = AsyncMock(side_effect=Exception("LLM error"))

        anketa = FinalAnketa(company_name="Test", industry="IT", services=["Услуга"])
        result = await extractor._generate_expert_content(anketa)

        # Should have fallback content
        assert len(result.faq_items) > 0
        assert len(result.objection_handlers) > 0
        assert len(result.escalation_rules) > 0
        assert result.anketa_version == "2.0"


# ============================================================================
# MERGE EXPERT CONTENT TESTS
# ============================================================================

class TestMergeExpertContent:
    """Tests for _merge_expert_content method."""

    def test_merge_faq_items(self, extractor):
        """Test merging FAQ items."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        data = {
            "faq_items": [
                {"question": "Q1", "answer": "A1", "category": "general"},
                {"question": "Q2", "answer": "A2"}
            ]
        }

        result = extractor._merge_expert_content(anketa, data)

        assert len(result.faq_items) == 2
        assert result.faq_items[0].question == "Q1"
        assert result.faq_items[1].category == "general"  # default

    def test_merge_objection_handlers(self, extractor):
        """Test merging objection handlers."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        data = {
            "objection_handlers": [
                {"objection": "Дорого", "response": "Понимаю", "follow_up": "Скидка"}
            ]
        }

        result = extractor._merge_expert_content(anketa, data)

        assert len(result.objection_handlers) == 1
        assert result.objection_handlers[0].objection == "Дорого"
        assert result.objection_handlers[0].follow_up == "Скидка"

    def test_merge_sample_dialogue(self, extractor):
        """Test merging sample dialogue."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        data = {
            "sample_dialogue": [
                {"role": "bot", "message": "Привет!", "intent": "greeting"},
                {"role": "user", "message": "Здравствуйте"}
            ]
        }

        result = extractor._merge_expert_content(anketa, data)

        assert len(result.sample_dialogue) == 2
        assert result.sample_dialogue[0].role == "bot"

    def test_merge_financial_metrics(self, extractor):
        """Test merging financial metrics."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        data = {
            "financial_metrics": [
                {"name": "ROI", "value": "150%", "source": "benchmark", "note": "За год"}
            ]
        }

        result = extractor._merge_expert_content(anketa, data)

        assert len(result.financial_metrics) == 1
        assert result.financial_metrics[0].name == "ROI"

    def test_merge_competitors(self, extractor):
        """Test merging competitors."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        data = {
            "competitors": [
                {"name": "Конкурент", "strengths": ["Цена"], "weaknesses": ["Качество"]}
            ]
        }

        result = extractor._merge_expert_content(anketa, data)

        assert len(result.competitors) == 1
        assert result.competitors[0].strengths == ["Цена"]

    def test_merge_all_expert_blocks(self, extractor, expert_llm_response):
        """Test merging all expert content blocks."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        data = json.loads(expert_llm_response)

        result = extractor._merge_expert_content(anketa, data)

        assert len(result.faq_items) > 0
        assert len(result.objection_handlers) > 0
        assert len(result.sample_dialogue) > 0
        assert len(result.financial_metrics) > 0
        assert len(result.competitors) > 0
        assert len(result.market_insights) > 0
        assert len(result.escalation_rules) > 0
        assert len(result.success_kpis) > 0
        assert len(result.launch_checklist) > 0
        assert len(result.ai_recommendations) > 0
        assert len(result.target_segments) > 0
        assert result.tone_of_voice is not None
        assert result.error_handling_scripts is not None


# ============================================================================
# FALLBACK EXPERT CONTENT TESTS
# ============================================================================

class TestFallbackExpertContent:
    """Tests for _generate_fallback_expert_content method."""

    def test_fallback_expert_content_faq(self, extractor):
        """Test fallback FAQ generation."""
        anketa = FinalAnketa(company_name="Test", industry="IT", services=["Услуга 1", "Услуга 2"])

        result = extractor._generate_fallback_expert_content(anketa)

        assert len(result.faq_items) == 3
        assert any("услуги" in faq.question.lower() for faq in result.faq_items)

    def test_fallback_expert_content_objections(self, extractor):
        """Test fallback objection handlers."""
        anketa = FinalAnketa(company_name="Test", industry="IT")

        result = extractor._generate_fallback_expert_content(anketa)

        assert len(result.objection_handlers) == 2
        assert any("дорого" in obj.objection.lower() for obj in result.objection_handlers)

    def test_fallback_expert_content_escalation(self, extractor):
        """Test fallback escalation rules."""
        anketa = FinalAnketa(company_name="Test", industry="IT")

        result = extractor._generate_fallback_expert_content(anketa)

        assert len(result.escalation_rules) == 2
        assert any(rule.urgency == "immediate" for rule in result.escalation_rules)

    def test_fallback_expert_content_kpis(self, extractor):
        """Test fallback KPIs."""
        anketa = FinalAnketa(company_name="Test", industry="IT")

        result = extractor._generate_fallback_expert_content(anketa)

        assert len(result.success_kpis) == 3
        assert any("конверсия" in kpi.name.lower() for kpi in result.success_kpis)

    def test_fallback_expert_content_checklist(self, extractor):
        """Test fallback launch checklist."""
        anketa = FinalAnketa(company_name="Test", industry="IT")

        result = extractor._generate_fallback_expert_content(anketa)

        assert len(result.launch_checklist) == 4
        assert any(item.required for item in result.launch_checklist)

    def test_fallback_expert_content_recommendations(self, extractor):
        """Test fallback AI recommendations."""
        anketa = FinalAnketa(company_name="Test", industry="IT")

        result = extractor._generate_fallback_expert_content(anketa)

        assert len(result.ai_recommendations) == 2
        assert any(rec.priority == "high" for rec in result.ai_recommendations)

    def test_fallback_expert_content_tone(self, extractor):
        """Test fallback tone of voice."""
        anketa = FinalAnketa(company_name="Test", industry="IT")

        result = extractor._generate_fallback_expert_content(anketa)

        assert "do" in result.tone_of_voice
        assert "dont" in result.tone_of_voice

    def test_fallback_expert_content_error_handling(self, extractor):
        """Test fallback error handling scripts."""
        anketa = FinalAnketa(company_name="Test", industry="IT")

        result = extractor._generate_fallback_expert_content(anketa)

        assert "not_understood" in result.error_handling_scripts
        assert "technical_issue" in result.error_handling_scripts
        assert "out_of_scope" in result.error_handling_scripts


# ============================================================================
# FULL EXTRACTION TESTS
# ============================================================================

class TestFullExtraction:
    """Integration tests for full extraction flow."""

    @pytest.mark.asyncio
    async def test_extract_success(self, extractor, sample_dialogue, sample_analysis, sample_solution, full_llm_response, expert_llm_response):
        """Test successful full extraction."""
        # First call for extraction, second for expert content
        extractor.llm.chat = AsyncMock(side_effect=[full_llm_response, expert_llm_response])

        with patch.object(extractor, '_parse_json_with_repair', return_value=(json.loads(full_llm_response), False)):
            with patch.object(extractor.post_processor, 'process', return_value=(json.loads(full_llm_response), {'cleaning_changes': []})):
                result = await extractor.extract(
                    sample_dialogue, sample_analysis, sample_solution, 300.0
                )

        assert isinstance(result, FinalAnketa)
        assert result.company_name == "АльфаТех"

    @pytest.mark.asyncio
    async def test_extract_with_model_dump(self, extractor, sample_dialogue):
        """Test extraction with Pydantic models that have model_dump."""
        analysis = MagicMock()
        analysis.model_dump.return_value = {"company_name": "Test"}

        solution = MagicMock()
        solution.model_dump.return_value = {"agent_name": "Bot"}

        extractor.llm.chat = AsyncMock(return_value='{"company_name": "Test"}')

        with patch.object(extractor, '_parse_json_with_repair', return_value=({'company_name': 'Test'}, False)):
            with patch.object(extractor.post_processor, 'process', return_value=({'company_name': 'Test'}, {'cleaning_changes': []})):
                result = await extractor.extract(sample_dialogue, analysis, solution, 0)

        assert isinstance(result, FinalAnketa)
        analysis.model_dump.assert_called_once()
        solution.model_dump.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_json_error_fallback(self, extractor, sample_dialogue, sample_analysis, sample_solution):
        """Test fallback on JSON decode error."""
        extractor.llm.chat = AsyncMock(return_value="invalid json")

        with patch.object(extractor, '_parse_json_with_repair', side_effect=json.JSONDecodeError("", "", 0)):
            result = await extractor.extract(
                sample_dialogue, sample_analysis, sample_solution, 300.0
            )

        # Should return fallback anketa
        assert isinstance(result, FinalAnketa)
        assert result.company_name == "АльфаТех"  # From analysis

    @pytest.mark.asyncio
    async def test_extract_general_error_fallback(self, extractor, sample_dialogue, sample_analysis, sample_solution):
        """Test fallback on general error."""
        extractor.llm.chat = AsyncMock(side_effect=Exception("LLM failed"))

        result = await extractor.extract(
            sample_dialogue, sample_analysis, sample_solution, 300.0
        )

        # Should return fallback anketa
        assert isinstance(result, FinalAnketa)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_dialogue(self, extractor):
        """Test with empty dialogue."""
        prompt = extractor._build_extraction_prompt([], {}, {}, None)
        assert "ДИАЛОГ КОНСУЛЬТАЦИИ:" in prompt

    def test_missing_values_in_data(self, extractor):
        """Test anketa building with missing/empty values."""
        data = {
            "company_name": "",
            "industry": "",
            "services": [],
            "agent_functions": []
        }
        anketa = extractor._build_anketa(data, 0)

        # Should handle empty values gracefully
        assert anketa.services == []
        assert anketa.agent_functions == []
        assert anketa.company_name == ""

    def test_invalid_function_format(self, extractor):
        """Test with invalid function format."""
        data = {
            "company_name": "Test",
            "agent_functions": ["not a dict", 123, None]
        }
        anketa = extractor._build_anketa(data, 0)

        # Should skip invalid entries
        assert anketa.agent_functions == []

    def test_invalid_integration_format(self, extractor):
        """Test with invalid integration format."""
        data = {
            "company_name": "Test",
            "integrations": ["not a dict", 123]
        }
        anketa = extractor._build_anketa(data, 0)

        assert anketa.integrations == []

    def test_partial_main_function(self, extractor):
        """Test with partial main function data."""
        data = {
            "company_name": "Test",
            "main_function": {"name": "Test"}  # Missing description
        }
        anketa = extractor._build_anketa(data, 0)

        assert anketa.main_function is not None
        assert anketa.main_function.name == "Test"
        assert anketa.main_function.description == ""
