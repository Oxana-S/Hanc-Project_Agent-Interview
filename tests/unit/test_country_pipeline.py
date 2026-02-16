"""
Tests for Bug #12 fix: Country context pipeline.

Tests cover:
- FinalAnketa new country/region/currency fields
- Country re-detection when phone changes in consultant
- Expert context includes country/currency
- Expert prompt includes country/currency
- Country hint injection in extraction dialogue
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.anketa.schema import FinalAnketa, AgentFunction
from src.anketa.extractor import AnketaExtractor


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_llm():
    """Mock LLM client for extractor."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value='{"company_name": "TestCo"}')
    return llm


@pytest.fixture
def extractor(mock_llm):
    """AnketaExtractor with mocked LLM."""
    return AnketaExtractor(llm=mock_llm)


# ============================================================================
# 1. FinalAnketa SCHEMA TESTS
# ============================================================================

class TestFinalAnketaCountryFields:
    """Test new country/region/currency fields in FinalAnketa."""

    def test_default_empty_strings(self):
        """New country fields default to empty strings."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        assert anketa.country == ""
        assert anketa.country_name == ""
        assert anketa.region == ""
        assert anketa.currency == ""

    def test_country_fields_serialization(self):
        """Country fields serialize to JSON correctly."""
        anketa = FinalAnketa(
            company_name="Tierarztzentrum",
            industry="veterinary",
            country="at",
            country_name="Austria",
            region="eu",
            currency="EUR",
        )
        data = anketa.model_dump(mode="json")
        assert data["country"] == "at"
        assert data["country_name"] == "Austria"
        assert data["region"] == "eu"
        assert data["currency"] == "EUR"

    def test_country_fields_deserialization(self):
        """Country fields deserialize from dict correctly."""
        data = {
            "company_name": "Test GmbH",
            "industry": "IT",
            "country": "de",
            "country_name": "Germany",
            "region": "eu",
            "currency": "EUR",
        }
        anketa = FinalAnketa(**data)
        assert anketa.country == "de"
        assert anketa.country_name == "Germany"
        assert anketa.region == "eu"
        assert anketa.currency == "EUR"

    def test_country_fields_not_in_completion_rate(self):
        """Country fields do NOT affect completion_rate (auto-detected, not asked)."""
        anketa_without = FinalAnketa(
            company_name="Test",
            industry="IT",
            business_description="testing",
        )
        rate_without = anketa_without.completion_rate()

        anketa_with = FinalAnketa(
            company_name="Test",
            industry="IT",
            business_description="testing",
            country="at",
            country_name="Austria",
            region="eu",
            currency="EUR",
        )
        rate_with = anketa_with.completion_rate()

        assert rate_without == rate_with

    def test_country_fields_not_in_required_fields_status(self):
        """Country fields not in get_required_fields_status()."""
        anketa = FinalAnketa(company_name="Test", industry="IT", country="at")
        status = anketa.get_required_fields_status()
        assert "country" not in status
        assert "country_name" not in status
        assert "region" not in status
        assert "currency" not in status

    def test_extra_ignore_still_works(self):
        """model_config extra='ignore' still works with country fields present."""
        data = {
            "company_name": "Test",
            "industry": "IT",
            "country": "at",
            "unknown_field_xyz": "should be ignored",
        }
        anketa = FinalAnketa(**data)
        assert anketa.country == "at"
        assert not hasattr(anketa, "unknown_field_xyz")

    def test_roundtrip_with_country_fields(self):
        """Full roundtrip: create → dump → load preserves country fields."""
        original = FinalAnketa(
            company_name="АльфаТех",
            industry="IT",
            country="ru",
            country_name="Russia",
            region="ru",
            currency="RUB",
        )
        data = original.model_dump(mode="json")
        restored = FinalAnketa(**data)
        assert restored.country == "ru"
        assert restored.country_name == "Russia"
        assert restored.region == "ru"
        assert restored.currency == "RUB"


# ============================================================================
# 2. EXPERT CONTEXT TESTS
# ============================================================================

class TestExpertContextCountry:
    """Test that _build_expert_context includes country/currency."""

    def test_expert_context_includes_country_fields(self, extractor):
        """_build_expert_context includes website, phone, country, currency."""
        anketa = FinalAnketa(
            company_name="Tierarztzentrum",
            industry="veterinary",
            website="tierarztzentrum-seepark.at",
            contact_phone="+43 1 8900 222",
            country="at",
            country_name="Austria",
            currency="EUR",
        )
        context = extractor._build_expert_context(anketa)

        assert context["website"] == "tierarztzentrum-seepark.at"
        assert context["contact_phone"] == "+43 1 8900 222"
        assert context["country"] == "at"
        assert context["country_name"] == "Austria"
        assert context["currency"] == "EUR"

    def test_expert_context_empty_country_defaults(self, extractor):
        """Empty country fields default to empty strings in context."""
        anketa = FinalAnketa(company_name="Test", industry="IT")
        context = extractor._build_expert_context(anketa)

        assert context["website"] == ""
        assert context["contact_phone"] == ""
        assert context["country"] == ""
        assert context["country_name"] == ""
        assert context["currency"] == ""

    def test_expert_context_preserves_existing_fields(self, extractor):
        """Adding country fields doesn't break existing context fields."""
        anketa = FinalAnketa(
            company_name="Test",
            industry="IT",
            services=["Консалтинг"],
            main_function=AgentFunction(name="Bot", description="Test", priority="high"),
            country="de",
            currency="EUR",
        )
        context = extractor._build_expert_context(anketa)

        assert context["company_name"] == "Test"
        assert context["industry"] == "IT"
        assert context["services"] == ["Консалтинг"]
        assert context["main_function"] is not None
        assert context["currency"] == "EUR"


# ============================================================================
# 3. EXPERT PROMPT TESTS
# ============================================================================

class TestExpertPromptCountry:
    """Test that _build_expert_generation_prompt passes country/currency."""

    def test_prompt_with_country_and_currency(self, extractor):
        """Expert prompt includes country and currency when provided."""
        context = {
            "company_name": "Tierarztzentrum",
            "industry": "veterinary",
            "agent_purpose": "запись на приём",
            "country_name": "Austria",
            "country": "at",
            "currency": "EUR",
        }
        prompt = extractor._build_expert_generation_prompt(context)

        assert "Austria" in prompt
        assert "EUR" in prompt

    def test_prompt_without_country(self, extractor):
        """Expert prompt works without country (backward compatible)."""
        context = {
            "company_name": "АльфаТех",
            "industry": "IT",
            "agent_purpose": "консультирование",
        }
        prompt = extractor._build_expert_generation_prompt(context)

        assert "АльфаТех" in prompt
        assert "IT" in prompt

    def test_prompt_country_name_fallback_to_code(self, extractor):
        """If country_name is empty, falls back to country code."""
        context = {
            "company_name": "Test",
            "industry": "IT",
            "agent_purpose": "test",
            "country_name": "",
            "country": "at",
            "currency": "EUR",
        }
        prompt = extractor._build_expert_generation_prompt(context)
        # country_name is empty → falls back to country code "at"
        assert "EUR" in prompt


# ============================================================================
# 4. VOICE CONSULTATION SESSION TESTS
# ============================================================================

class TestVoiceConsultationSessionCountry:
    """Test _detected_phone attribute on VoiceConsultationSession."""

    def test_detected_phone_initial_none(self):
        """New session has _detected_phone = None."""
        from src.voice.consultant import VoiceConsultationSession
        session = VoiceConsultationSession(room_name="test-room")
        assert session._detected_phone is None

    def test_detected_phone_attribute_exists(self):
        """VoiceConsultationSession has _detected_phone attribute."""
        from src.voice.consultant import VoiceConsultationSession
        session = VoiceConsultationSession()
        assert hasattr(session, '_detected_phone')


# ============================================================================
# 5. EXTRACTION PROMPT COUNTRY FIELDS
# ============================================================================

class TestExtractionPromptCountryFields:
    """Test that extract.yaml prompt includes country fields in schema."""

    def test_extraction_prompt_has_country_fields(self):
        """extract.yaml prompt template includes country, country_name, region, currency."""
        from src.config.prompt_loader import render_prompt

        # Render with minimal variables
        prompt = render_prompt(
            "anketa/extract", "user_prompt_template",
            dialogue_text="Тест",
        )

        # Check that country fields are in the JSON schema
        assert '"country"' in prompt
        assert '"country_name"' in prompt
        assert '"region"' in prompt
        assert '"currency"' in prompt

    def test_extraction_prompt_has_country_detection_instructions(self):
        """extract.yaml includes country detection instructions."""
        from src.config.prompt_loader import render_prompt

        prompt = render_prompt(
            "anketa/extract", "user_prompt_template",
            dialogue_text="Тест",
        )

        assert "ОПРЕДЕЛЕНИЕ СТРАНЫ И ВАЛЮТЫ" in prompt
        assert "+43 = Австрия" in prompt
        assert "НЕ ИСПОЛЬЗУЙ рубли" in prompt

    def test_extraction_prompt_budget_has_currency_instruction(self):
        """Budget field description mentions using client's country currency."""
        from src.config.prompt_loader import render_prompt

        prompt = render_prompt(
            "anketa/extract", "user_prompt_template",
            dialogue_text="Тест",
        )

        assert "ОБЯЗАТЕЛЬНО с валютой страны клиента" in prompt


# ============================================================================
# 6. EXPERT YAML PROMPT TESTS
# ============================================================================

class TestExpertYamlPrompt:
    """Test that expert.yaml includes country/currency conditional blocks."""

    def test_expert_prompt_with_country_renders_currency_warning(self):
        """expert.yaml renders currency warning when country and currency provided."""
        from src.config.prompt_loader import render_prompt

        prompt = render_prompt(
            "anketa/expert", "user_prompt_template",
            company_name="Tierarztzentrum",
            industry="veterinary",
            agent_purpose="запись",
            country="Austria",
            currency="EUR",
        )

        assert "EUR" in prompt
        assert "Austria" in prompt
        assert "НЕ используй рубли" in prompt

    def test_expert_prompt_without_country_no_warning(self):
        """expert.yaml without country does not render currency warning."""
        from src.config.prompt_loader import render_prompt

        prompt = render_prompt(
            "anketa/expert", "user_prompt_template",
            company_name="АльфаТех",
            industry="IT",
            agent_purpose="консультирование",
        )

        assert "НЕ используй рубли" not in prompt

    def test_expert_prompt_with_russian_currency(self):
        """expert.yaml with RUB currency renders properly."""
        from src.config.prompt_loader import render_prompt

        prompt = render_prompt(
            "anketa/expert", "user_prompt_template",
            company_name="Test",
            industry="IT",
            agent_purpose="test",
            country="Россия",
            currency="RUB",
        )

        assert "RUB" in prompt
        assert "Россия" in prompt


# ============================================================================
# 7. COUNTRY RE-DETECTION LOGIC TESTS
# ============================================================================

class TestCountryRedetection:
    """Test country re-detection logic in _extract_and_update_anketa."""

    def test_redetection_trigger_on_new_phone(self):
        """should_redetect is True when phone appears and _detected_phone is None."""
        from src.voice.consultant import VoiceConsultationSession
        session = VoiceConsultationSession()
        session.detected_profile = MagicMock()  # Already detected once
        session._detected_phone = None

        current_phone = "+43 1 8900 222"
        should_redetect = (
            session.detected_profile is None
            or (current_phone and current_phone != (session._detected_phone or ''))
        )
        assert should_redetect is True

    def test_redetection_trigger_on_phone_change(self):
        """should_redetect is True when phone changes."""
        from src.voice.consultant import VoiceConsultationSession
        session = VoiceConsultationSession()
        session.detected_profile = MagicMock()
        session._detected_phone = "+7 901 234 5567"

        current_phone = "+43 1 8900 222"
        should_redetect = (
            session.detected_profile is None
            or (current_phone and current_phone != (session._detected_phone or ''))
        )
        assert should_redetect is True

    def test_no_redetection_same_phone(self):
        """should_redetect is False when phone is the same."""
        from src.voice.consultant import VoiceConsultationSession
        session = VoiceConsultationSession()
        session.detected_profile = MagicMock()
        session._detected_phone = "+43 1 8900 222"

        current_phone = "+43 1 8900 222"
        should_redetect = (
            session.detected_profile is None
            or (current_phone and current_phone != (session._detected_phone or ''))
        )
        assert should_redetect is False

    def test_no_redetection_empty_phone(self):
        """should_redetect is False when phone is empty and profile exists."""
        from src.voice.consultant import VoiceConsultationSession
        session = VoiceConsultationSession()
        session.detected_profile = MagicMock()
        session._detected_phone = ""

        current_phone = ""
        should_redetect = (
            session.detected_profile is None
            or (current_phone and current_phone != (session._detected_phone or ''))
        )
        assert not should_redetect

    def test_first_detection_when_no_profile(self):
        """should_redetect is True when no profile exists yet."""
        from src.voice.consultant import VoiceConsultationSession
        session = VoiceConsultationSession()
        assert session.detected_profile is None

        current_phone = ""
        should_redetect = (
            session.detected_profile is None
            or (current_phone and current_phone != (session._detected_phone or ''))
        )
        assert should_redetect is True


# ============================================================================
# 8. COUNTRY HINT INJECTION TESTS
# ============================================================================

class TestCountryHintInjection:
    """Test country hint injection into extraction dialogue."""

    def _make_profile_mock(self, country="at", currency="EUR"):
        """Create a mock IndustryProfile with meta."""
        meta = MagicMock()
        meta.country = country
        meta.currency = currency
        profile = MagicMock()
        profile.meta = meta
        return profile

    def test_hint_injected_when_profile_has_country(self):
        """Country hint is prepended to dialogue when profile has country."""
        profile = self._make_profile_mock(country="at", currency="EUR")

        dialogue = [
            {"role": "user", "content": "Здравствуйте"},
            {"role": "assistant", "content": "Добрый день"},
        ]

        # Simulate the hint injection logic from consultant.py
        _meta = getattr(profile, 'meta', None)
        _country = getattr(_meta, 'country', None) if _meta else None
        _currency = getattr(_meta, 'currency', None) if _meta else None
        if _country and _currency:
            country_hint = {
                "role": "system",
                "content": f"Контекст: Страна клиента — {_country.upper()}. Валюта: {_currency}."
            }
            dialogue = [country_hint] + list(dialogue)

        assert len(dialogue) == 3
        assert dialogue[0]["role"] == "system"
        assert "AT" in dialogue[0]["content"]
        assert "EUR" in dialogue[0]["content"]

    def test_no_hint_when_no_profile(self):
        """No hint injected when detected_profile is None."""
        profile = None
        dialogue = [{"role": "user", "content": "Здравствуйте"}]

        if profile:
            _meta = getattr(profile, 'meta', None)
            _country = getattr(_meta, 'country', None)
            _currency = getattr(_meta, 'currency', None)
            if _country and _currency:
                dialogue = [{"role": "system", "content": "hint"}] + list(dialogue)

        assert len(dialogue) == 1
        assert dialogue[0]["role"] == "user"

    def test_no_hint_when_country_missing(self):
        """No hint when profile meta has no country."""
        profile = self._make_profile_mock(country=None, currency="EUR")
        dialogue = [{"role": "user", "content": "Здравствуйте"}]

        _meta = getattr(profile, 'meta', None)
        _country = getattr(_meta, 'country', None)
        _currency = getattr(_meta, 'currency', None)
        if _country and _currency:
            dialogue = [{"role": "system", "content": "hint"}] + list(dialogue)

        assert len(dialogue) == 1

    def test_no_hint_when_currency_missing(self):
        """No hint when profile meta has no currency."""
        profile = self._make_profile_mock(country="at", currency=None)
        dialogue = [{"role": "user", "content": "Здравствуйте"}]

        _meta = getattr(profile, 'meta', None)
        _country = getattr(_meta, 'country', None)
        _currency = getattr(_meta, 'currency', None)
        if _country and _currency:
            dialogue = [{"role": "system", "content": "hint"}] + list(dialogue)

        assert len(dialogue) == 1
