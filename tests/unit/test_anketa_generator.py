"""
Tests for src/anketa/generator.py

Comprehensive tests for AnketaGenerator class.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone

from src.anketa.generator import AnketaGenerator, generate_anketa_files
from src.anketa.schema import (
    FinalAnketa, AgentFunction, Integration,
    FAQItem, ObjectionHandler, DialogueExample, FinancialMetric,
    Competitor, MarketInsight, EscalationRule, KPIMetric,
    ChecklistItem, AIRecommendation, TargetAudienceSegment
)


class TestAnketaGeneratorInit:
    """Tests for AnketaGenerator initialization."""

    def test_init_creates_output_dir(self, tmp_path):
        """Test initialization creates output directory."""
        output_dir = tmp_path / "new_dir" / "anketas"
        generator = AnketaGenerator(output_dir=str(output_dir))

        assert output_dir.exists()
        assert generator.output_dir == output_dir

    def test_init_default_dir(self):
        """Test default output directory."""
        generator = AnketaGenerator()
        assert generator.output_dir == Path("output/anketas")


class TestAnketaGeneratorSafeFilename:
    """Tests for _safe_filename method."""

    def test_safe_filename_basic(self):
        """Test basic filename conversion."""
        generator = AnketaGenerator()
        result = generator._safe_filename("Test Company")
        assert result == "test_company"

    def test_safe_filename_special_chars(self):
        """Test filename with special characters."""
        generator = AnketaGenerator()
        result = generator._safe_filename("Компания №1 (Москва)")
        assert result == "компания_1_москва"

    def test_safe_filename_empty(self):
        """Test empty filename."""
        generator = AnketaGenerator()
        result = generator._safe_filename("")
        assert result == "unnamed"

    def test_safe_filename_only_special_chars(self):
        """Test filename with only special characters."""
        generator = AnketaGenerator()
        result = generator._safe_filename("!@#$%")
        assert result == "unnamed"

    def test_safe_filename_truncation(self):
        """Test filename truncation to 50 chars."""
        generator = AnketaGenerator()
        long_name = "A" * 100
        result = generator._safe_filename(long_name)
        assert len(result) == 50


class TestAnketaGeneratorToMarkdown:
    """Tests for to_markdown method."""

    @pytest.fixture
    def sample_anketa(self):
        """Create a sample anketa for testing."""
        return FinalAnketa(
            company_name="Test Company",
            industry="IT",
            services=["Consulting", "Development"],
            client_types=["B2B", "Enterprise"],
            agent_purpose="Customer support",
            agent_name="TestBot",
            voice_tone="friendly",
            language="ru"
        )

    def test_to_markdown_creates_file(self, tmp_path, sample_anketa):
        """Test that to_markdown creates a file."""
        generator = AnketaGenerator(output_dir=str(tmp_path))
        filepath = generator.to_markdown(sample_anketa)

        assert filepath.exists()
        assert filepath.suffix == ".md"

    def test_to_markdown_with_custom_filename(self, tmp_path, sample_anketa):
        """Test to_markdown with custom filename."""
        generator = AnketaGenerator(output_dir=str(tmp_path))
        filepath = generator.to_markdown(sample_anketa, filename="custom.md")

        assert filepath.name == "custom.md"

    def test_to_markdown_content_has_company_name(self, tmp_path, sample_anketa):
        """Test that markdown contains company name."""
        generator = AnketaGenerator(output_dir=str(tmp_path))
        filepath = generator.to_markdown(sample_anketa)

        content = filepath.read_text()
        assert "Test Company" in content

    def test_to_markdown_content_has_industry(self, tmp_path, sample_anketa):
        """Test that markdown contains industry."""
        generator = AnketaGenerator(output_dir=str(tmp_path))
        filepath = generator.to_markdown(sample_anketa)

        content = filepath.read_text()
        assert "IT" in content


class TestAnketaGeneratorToJson:
    """Tests for to_json method."""

    @pytest.fixture
    def sample_anketa(self):
        """Create a sample anketa for testing."""
        return FinalAnketa(
            company_name="Test Company",
            industry="IT"
        )

    def test_to_json_creates_file(self, tmp_path, sample_anketa):
        """Test that to_json creates a file."""
        generator = AnketaGenerator(output_dir=str(tmp_path))
        filepath = generator.to_json(sample_anketa)

        assert filepath.exists()
        assert filepath.suffix == ".json"

    def test_to_json_with_custom_filename(self, tmp_path, sample_anketa):
        """Test to_json with custom filename."""
        generator = AnketaGenerator(output_dir=str(tmp_path))
        filepath = generator.to_json(sample_anketa, filename="custom.json")

        assert filepath.name == "custom.json"

    def test_to_json_valid_json(self, tmp_path, sample_anketa):
        """Test that output is valid JSON."""
        generator = AnketaGenerator(output_dir=str(tmp_path))
        filepath = generator.to_json(sample_anketa)

        with open(filepath) as f:
            data = json.load(f)

        assert data["company_name"] == "Test Company"
        assert data["industry"] == "IT"


class TestAnketaGeneratorRenderList:
    """Tests for _render_list method."""

    def test_render_list_with_items(self):
        """Test rendering list with items."""
        generator = AnketaGenerator()
        result = generator._render_list(["Item 1", "Item 2", "Item 3"])

        assert "- Item 1" in result
        assert "- Item 2" in result
        assert "- Item 3" in result

    def test_render_list_empty(self):
        """Test rendering empty list."""
        generator = AnketaGenerator()
        result = generator._render_list([])

        assert result == "*Не указано*"

    def test_render_list_filters_empty_strings(self):
        """Test that empty strings are filtered."""
        generator = AnketaGenerator()
        result = generator._render_list(["Item 1", "", "Item 2"])

        assert "- Item 1" in result
        assert "- Item 2" in result
        assert result.count("-") == 2


class TestAnketaGeneratorRenderMainFunction:
    """Tests for _render_main_function method."""

    def test_render_main_function_with_data(self):
        """Test rendering main function."""
        generator = AnketaGenerator()
        func = AgentFunction(
            name="Answer Questions",
            description="Answers customer questions",
            priority="high"
        )

        result = generator._render_main_function(func)

        assert "Answer Questions" in result
        assert "Answers customer questions" in result
        assert "high" in result

    def test_render_main_function_none(self):
        """Test rendering None function."""
        generator = AnketaGenerator()
        result = generator._render_main_function(None)

        assert result == "*Не определена*"


class TestAnketaGeneratorRenderFunctions:
    """Tests for _render_functions method."""

    def test_render_functions_with_data(self):
        """Test rendering list of functions."""
        generator = AnketaGenerator()
        functions = [
            AgentFunction(name="Func 1", description="Desc 1", priority="high"),
            AgentFunction(name="Func 2", description="Desc 2", priority="medium")
        ]

        result = generator._render_functions(functions)

        assert "1. Func 1" in result
        assert "2. Func 2" in result
        assert "Desc 1" in result
        assert "high" in result

    def test_render_functions_empty(self):
        """Test rendering empty functions list."""
        generator = AnketaGenerator()
        result = generator._render_functions([])

        assert result == "*Не указано*"


class TestAnketaGeneratorRenderIntegrations:
    """Tests for _render_integrations method."""

    def test_render_integrations_with_data(self):
        """Test rendering integrations table."""
        generator = AnketaGenerator()
        integrations = [
            Integration(name="CRM", purpose="Customer data", required=True),
            Integration(name="Calendar", purpose="Scheduling", required=False)
        ]

        result = generator._render_integrations(integrations)

        assert "| CRM |" in result
        assert "| Calendar |" in result
        assert "| Да |" in result
        assert "| Нет |" in result

    def test_render_integrations_empty(self):
        """Test rendering empty integrations."""
        generator = AnketaGenerator()
        result = generator._render_integrations([])

        assert result == "*Интеграции не требуются*"


class TestAnketaGeneratorFormatCallDirection:
    """Tests for _format_call_direction method."""

    def test_format_call_direction_inbound(self):
        """Test formatting inbound calls."""
        generator = AnketaGenerator()
        assert generator._format_call_direction("inbound") == "Входящие"

    def test_format_call_direction_outbound(self):
        """Test formatting outbound calls."""
        generator = AnketaGenerator()
        assert generator._format_call_direction("outbound") == "Исходящие"

    def test_format_call_direction_both(self):
        """Test formatting both direction."""
        generator = AnketaGenerator()
        assert generator._format_call_direction("both") == "Входящие и исходящие"

    def test_format_call_direction_unknown(self):
        """Test formatting unknown direction."""
        generator = AnketaGenerator()
        assert generator._format_call_direction("unknown") == "unknown"


class TestAnketaGeneratorRenderFAQItems:
    """Tests for _render_faq_items method."""

    def test_render_faq_items_with_data(self):
        """Test rendering FAQ items."""
        generator = AnketaGenerator()
        items = [
            FAQItem(question="What is price?", answer="Starting from $100", category="pricing"),
            FAQItem(question="Working hours?", answer="9-18", category="general")
        ]

        result = generator._render_faq_items(items)

        assert "What is price?" in result
        assert "Starting from $100" in result
        assert "[pricing]" in result

    def test_render_faq_items_empty(self):
        """Test rendering empty FAQ."""
        generator = AnketaGenerator()
        result = generator._render_faq_items([])

        assert result == "*FAQ не сгенерирован*"


class TestAnketaGeneratorRenderObjectionHandlers:
    """Tests for _render_objection_handlers method."""

    def test_render_objection_handlers_with_data(self):
        """Test rendering objection handlers."""
        generator = AnketaGenerator()
        handlers = [
            ObjectionHandler(
                objection="Too expensive",
                response="We offer payment plans",
                follow_up="Would you like details?"
            )
        ]

        result = generator._render_objection_handlers(handlers)

        assert "Too expensive" in result
        assert "We offer payment plans" in result
        assert "Would you like details?" in result

    def test_render_objection_handlers_without_followup(self):
        """Test rendering objection handler without follow-up."""
        generator = AnketaGenerator()
        handlers = [
            ObjectionHandler(
                objection="Test",
                response="Response",
                follow_up=None
            )
        ]

        result = generator._render_objection_handlers(handlers)

        assert "Test" in result
        assert "Response" in result

    def test_render_objection_handlers_empty(self):
        """Test rendering empty handlers."""
        generator = AnketaGenerator()
        result = generator._render_objection_handlers([])

        assert result == "*Возражения не проработаны*"


class TestAnketaGeneratorRenderSampleDialogue:
    """Tests for _render_sample_dialogue method."""

    def test_render_sample_dialogue_with_data(self):
        """Test rendering sample dialogue."""
        generator = AnketaGenerator()
        dialogue = [
            DialogueExample(role="bot", message="Hello!", intent="greeting"),
            DialogueExample(role="client", message="Hi there", intent="response")
        ]

        result = generator._render_sample_dialogue(dialogue)

        assert "🤖 Агент" in result
        assert "👤 Клиент" in result
        assert "Hello!" in result
        assert "(greeting)" in result

    def test_render_sample_dialogue_empty(self):
        """Test rendering empty dialogue."""
        generator = AnketaGenerator()
        result = generator._render_sample_dialogue([])

        assert result == "*Пример диалога не сгенерирован*"


class TestAnketaGeneratorRenderFinancialMetrics:
    """Tests for _render_financial_metrics method."""

    def test_render_financial_metrics_with_data(self):
        """Test rendering financial metrics."""
        generator = AnketaGenerator()
        metrics = [
            FinancialMetric(
                name="ROI",
                value="300%",
                source="ai_benchmark",
                note="Based on similar projects"
            )
        ]

        result = generator._render_financial_metrics(metrics)

        assert "ROI" in result
        assert "300%" in result
        assert "AI-бенчмарк" in result
        assert "Based on similar projects" in result

    def test_render_financial_metrics_empty(self):
        """Test rendering empty metrics."""
        generator = AnketaGenerator()
        result = generator._render_financial_metrics([])

        assert result == "*Финансовые метрики не указаны*"


class TestAnketaGeneratorRenderCompetitors:
    """Tests for _render_competitors method."""

    def test_render_competitors_with_data(self):
        """Test rendering competitors."""
        generator = AnketaGenerator()
        competitors = [
            Competitor(
                name="Competitor A",
                strengths=["Good price", "Fast delivery"],
                weaknesses=["Poor support"],
                price_range="$100-500"
            )
        ]

        result = generator._render_competitors(competitors)

        assert "Competitor A" in result
        assert "Good price" in result
        assert "Poor support" in result
        assert "$100-500" in result

    def test_render_competitors_empty(self):
        """Test rendering empty competitors."""
        generator = AnketaGenerator()
        result = generator._render_competitors([])

        assert result == "*Конкуренты не определены*"


class TestAnketaGeneratorRenderMarketInsights:
    """Tests for _render_market_insights method."""

    def test_render_market_insights_with_data(self):
        """Test rendering market insights."""
        generator = AnketaGenerator()
        insights = [
            MarketInsight(insight="Market growing 20%", source="research", relevance="high"),
            MarketInsight(insight="New regulation", source="news", relevance="medium")
        ]

        result = generator._render_market_insights(insights)

        assert "Market growing 20%" in result
        assert "New regulation" in result
        assert "🔥" in result  # high relevance icon
        assert "📊" in result  # medium relevance icon

    def test_render_market_insights_empty(self):
        """Test rendering empty insights."""
        generator = AnketaGenerator()
        result = generator._render_market_insights([])

        assert result == "*Инсайты не сгенерированы*"


class TestAnketaGeneratorRenderTargetSegments:
    """Tests for _render_target_segments method."""

    def test_render_target_segments_with_data(self):
        """Test rendering target segments."""
        generator = AnketaGenerator()
        segments = [
            TargetAudienceSegment(
                name="Small Business",
                description="Companies with 10-50 employees",
                pain_points=["Limited budget", "Need automation"],
                triggers=["Growth phase", "New funding"]
            )
        ]

        result = generator._render_target_segments(segments)

        assert "Small Business" in result
        assert "Companies with 10-50 employees" in result
        assert "Limited budget" in result
        assert "Growth phase" in result

    def test_render_target_segments_empty(self):
        """Test rendering empty segments."""
        generator = AnketaGenerator()
        result = generator._render_target_segments([])

        assert result == "*Сегменты не определены*"


class TestAnketaGeneratorRenderEscalationRules:
    """Tests for _render_escalation_rules method."""

    def test_render_escalation_rules_with_data(self):
        """Test rendering escalation rules."""
        generator = AnketaGenerator()
        rules = [
            EscalationRule(
                trigger="Customer angry",
                urgency="immediate",
                action="Transfer to manager"
            )
        ]

        result = generator._render_escalation_rules(rules)

        assert "Customer angry" in result
        assert "🚨 Немедленно" in result
        assert "Transfer to manager" in result

    def test_render_escalation_rules_empty(self):
        """Test rendering empty rules."""
        generator = AnketaGenerator()
        result = generator._render_escalation_rules([])

        assert result == "*Правила эскалации не определены*"


class TestAnketaGeneratorRenderSuccessKPIs:
    """Tests for _render_success_kpis method."""

    def test_render_success_kpis_with_data(self):
        """Test rendering KPIs."""
        generator = AnketaGenerator()
        kpis = [
            KPIMetric(
                name="Conversion Rate",
                target="15%",
                benchmark="10%",
                measurement="Monthly tracking"
            )
        ]

        result = generator._render_success_kpis(kpis)

        assert "Conversion Rate" in result
        assert "15%" in result
        assert "10%" in result
        assert "Monthly tracking" in result

    def test_render_success_kpis_empty(self):
        """Test rendering empty KPIs."""
        generator = AnketaGenerator()
        result = generator._render_success_kpis([])

        assert result == "*KPI не определены*"


class TestAnketaGeneratorRenderLaunchChecklist:
    """Tests for _render_launch_checklist method."""

    def test_render_launch_checklist_with_data(self):
        """Test rendering launch checklist."""
        generator = AnketaGenerator()
        checklist = [
            ChecklistItem(item="Configure CRM", required=True, responsible="team"),
            ChecklistItem(item="Test calls", required=False, responsible="client")
        ]

        result = generator._render_launch_checklist(checklist)

        assert "Configure CRM" in result
        assert "Test calls" in result
        assert "👥 Команда" in result
        assert "👤 Клиент" in result
        assert "(обязательно)" in result

    def test_render_launch_checklist_empty(self):
        """Test rendering empty checklist."""
        generator = AnketaGenerator()
        result = generator._render_launch_checklist([])

        assert result == "*Чеклист не определён*"


class TestAnketaGeneratorRenderAIRecommendations:
    """Tests for _render_ai_recommendations method."""

    def test_render_ai_recommendations_with_data(self):
        """Test rendering AI recommendations."""
        generator = AnketaGenerator()
        recommendations = [
            AIRecommendation(
                recommendation="Add FAQ section",
                impact="Reduce calls by 30%",
                priority="high",
                effort="low"
            )
        ]

        result = generator._render_ai_recommendations(recommendations)

        assert "Add FAQ section" in result
        assert "Reduce calls by 30%" in result
        assert "🔴" in result  # high priority
        assert "Низкие" in result  # low effort

    def test_render_ai_recommendations_empty(self):
        """Test rendering empty recommendations."""
        generator = AnketaGenerator()
        result = generator._render_ai_recommendations([])

        assert result == "*Рекомендации не сгенерированы*"


class TestAnketaGeneratorRenderToneOfVoice:
    """Tests for _render_tone_of_voice method."""

    def test_render_tone_of_voice_with_data(self):
        """Test rendering tone of voice."""
        generator = AnketaGenerator()
        tone = {
            "do": "Be friendly and helpful",
            "dont": "Never be rude"
        }

        result = generator._render_tone_of_voice(tone)

        assert "✅ Делать" in result
        assert "Be friendly and helpful" in result
        assert "❌ Не делать" in result
        assert "Never be rude" in result

    def test_render_tone_of_voice_empty(self):
        """Test rendering empty tone."""
        generator = AnketaGenerator()
        result = generator._render_tone_of_voice({})

        assert result == "*Тон коммуникации не определён*"


class TestAnketaGeneratorRenderErrorHandlingScripts:
    """Tests for _render_error_handling_scripts method."""

    def test_render_error_handling_scripts_with_data(self):
        """Test rendering error handling scripts."""
        generator = AnketaGenerator()
        scripts = {
            "not_understood": "Sorry, I didn't understand",
            "technical_issue": "We have a technical problem"
        }

        result = generator._render_error_handling_scripts(scripts)

        assert "🤔 Не понял запрос" in result
        assert "Sorry, I didn't understand" in result
        assert "⚠️ Техническая проблема" in result

    def test_render_error_handling_scripts_empty(self):
        """Test rendering empty scripts."""
        generator = AnketaGenerator()
        result = generator._render_error_handling_scripts({})

        assert result == "*Скрипты не определены*"


class TestAnketaGeneratorStaticRenderMarkdown:
    """Tests for static render_markdown method."""

    def test_static_render_markdown(self):
        """Test static render_markdown method."""
        anketa = FinalAnketa(
            company_name="Static Test",
            industry="Tech"
        )

        result = AnketaGenerator.render_markdown(anketa)

        assert "Static Test" in result
        assert "Tech" in result


class TestGenerateAnketaFiles:
    """Tests for generate_anketa_files function."""

    def test_generate_anketa_files_creates_both(self, tmp_path):
        """Test that both MD and JSON files are created."""
        anketa = FinalAnketa(
            company_name="Test",
            industry="IT"
        )

        result = generate_anketa_files(anketa, output_dir=str(tmp_path))

        assert result["markdown"].exists()
        assert result["json"].exists()
        assert result["markdown"].suffix == ".md"
        assert result["json"].suffix == ".json"


class TestAnketaGeneratorFullRender:
    """Integration tests for full markdown rendering."""

    @pytest.fixture
    def full_anketa(self):
        """Create a fully populated anketa."""
        return FinalAnketa(
            company_name="Full Test Company",
            industry="Healthcare",
            specialization="Dentistry",
            website="https://test.com",
            contact_name="John Doe",
            contact_role="CEO",
            business_description="We provide dental services",
            services=["Cleaning", "Whitening", "Implants"],
            client_types=["Individual", "Corporate"],
            current_problems=["Too many calls", "Long wait times"],
            business_goals=["Automate booking", "Reduce wait times"],
            constraints=["HIPAA compliance"],
            agent_name="DentalBot",
            agent_purpose="Appointment booking",
            voice_gender="female",
            voice_tone="professional",
            language="en",
            call_direction="inbound",
            main_function=AgentFunction(
                name="Book Appointments",
                description="Schedule dental appointments",
                priority="high"
            ),
            additional_functions=[
                AgentFunction(name="Answer FAQ", description="Answer common questions", priority="medium")
            ],
            agent_functions=[
                AgentFunction(name="Book Appointments", description="Schedule", priority="high"),
                AgentFunction(name="Answer FAQ", description="FAQ", priority="medium")
            ],
            integrations=[
                Integration(name="Calendar", purpose="Scheduling", required=True)
            ],
            faq_items=[
                FAQItem(question="Hours?", answer="9-5", category="general")
            ],
            objection_handlers=[
                ObjectionHandler(objection="Too expensive", response="We offer plans", follow_up="Details?")
            ],
            sample_dialogue=[
                DialogueExample(role="bot", message="Hello!", intent="greeting")
            ],
            financial_metrics=[
                FinancialMetric(name="ROI", value="200%", source="calculated", note=None)
            ],
            competitors=[
                Competitor(name="Rival", strengths=["Cheap"], weaknesses=["Slow"], price_range="$50-100")
            ],
            market_insights=[
                MarketInsight(insight="Growing market", source="research", relevance="high")
            ],
            competitive_advantages=["Best service"],
            target_segments=[
                TargetAudienceSegment(
                    name="Families",
                    description="Family dental care",
                    pain_points=["Cost"],
                    triggers=["Insurance"]
                )
            ],
            escalation_rules=[
                EscalationRule(trigger="Emergency", urgency="immediate", action="Call doctor")
            ],
            success_kpis=[
                KPIMetric(name="Bookings", target="100/month", benchmark="50", measurement="Monthly")
            ],
            launch_checklist=[
                ChecklistItem(item="Test", required=True, responsible="team")
            ],
            ai_recommendations=[
                AIRecommendation(recommendation="Add SMS", impact="More reach", priority="high", effort="low")
            ],
            tone_of_voice={"do": "Be professional", "dont": "Be casual"},
            error_handling_scripts={"not_understood": "Please repeat"},
            follow_up_sequence=["Thank you call", "Survey"]
        )

    def test_full_render_contains_all_sections(self, full_anketa):
        """Test that full render contains all sections."""
        result = AnketaGenerator.render_markdown(full_anketa)

        # Check all 18 sections
        assert "## 1. Информация о компании" in result
        assert "## 2. Бизнес-контекст" in result
        assert "## 3. Голосовой агент" in result
        assert "## 4. Все функции агента" in result
        assert "## 5. Интеграции" in result
        assert "## 6. FAQ с ответами" in result
        assert "## 7. Работа с возражениями" in result
        assert "## 8. Пример диалога" in result
        assert "## 9. Финансовая модель" in result
        assert "## 10. Анализ рынка" in result
        assert "## 11. Целевые сегменты" in result
        assert "## 12. Правила эскалации" in result
        assert "## 13. KPI и метрики успеха" in result
        assert "## 14. Чеклист запуска" in result
        assert "## 15. Рекомендации AI-эксперта" in result
        assert "## 16. Тон коммуникации" in result
        assert "## 17. Скрипты обработки ошибок" in result
        assert "## 18. Последовательность follow-up" in result

    def test_full_render_contains_company_data(self, full_anketa):
        """Test that full render contains company data."""
        result = AnketaGenerator.render_markdown(full_anketa)

        assert "Full Test Company" in result
        assert "Healthcare" in result
        assert "Dentistry" in result
        assert "John Doe" in result
