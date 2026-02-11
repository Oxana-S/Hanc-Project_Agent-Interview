"""
Comprehensive tests for src/llm/anketa_generator.py (LLMAnketaGenerator).

Tests cover:
- Initialization with custom and default DeepSeek clients
- Basic info population (specialization, business_description)
- Services and client types (string lists, dict lists)
- Agent config (name, tone, working hours, transfer conditions)
- Contact info (person, email, phone, website)
- Edge cases (empty/null LLM result, constraints, compliance, preservation)
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.anketa.schema import FinalAnketa
from src.llm.anketa_generator import LLMAnketaGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anketa(**overrides) -> FinalAnketa:
    """Create a FinalAnketa with sensible defaults for testing."""
    defaults = {
        "interview_id": "test-123",
        "pattern": "interaction",
        "company_name": "TestCorp",
        "industry": "Technology",
    }
    defaults.update(overrides)
    return FinalAnketa(**defaults)


def _make_llm_result(**section_overrides) -> dict:
    """Create a skeleton LLM result dict with empty sections."""
    result = {
        "basic_info": {},
        "clients_and_services": {},
        "agent_config": {},
        "additional_info": {},
        "contact_info": {},
    }
    result.update(section_overrides)
    return result


def _mock_client(llm_result) -> AsyncMock:
    """Return an AsyncMock DeepSeekClient whose analyze_and_complete_anketa returns llm_result."""
    client = AsyncMock()
    client.analyze_and_complete_anketa = AsyncMock(return_value=llm_result)
    return client


# ===========================================================================
# 1. Initialization
# ===========================================================================

class TestLLMAnketaGeneratorInit:

    def test_init_with_custom_client(self):
        """Passing an explicit DeepSeekClient should be stored on .client."""
        mock_client = AsyncMock()
        generator = LLMAnketaGenerator(deepseek_client=mock_client)
        assert generator.client is mock_client

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key-12345"})
    @patch("src.llm.anketa_generator.create_llm_client")
    def test_init_creates_default_client(self, MockDeepSeekClass):
        """When no client is provided, a default DeepSeekClient is created."""
        mock_instance = MagicMock()
        MockDeepSeekClass.return_value = mock_instance

        generator = LLMAnketaGenerator()

        MockDeepSeekClass.assert_called_once()
        assert generator.client is mock_instance


# ===========================================================================
# 2. Basic Info
# ===========================================================================

class TestGenerateBasicInfo:

    @pytest.mark.asyncio
    async def test_generate_fills_specialization(self):
        """LLM-provided specialization should be written when field is empty."""
        client = _mock_client(_make_llm_result(
            basic_info={"specialization": "Web Development"}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.specialization == "Web Development"

    @pytest.mark.asyncio
    async def test_generate_fills_business_description(self):
        """LLM-provided business_description should be written when field is empty."""
        client = _mock_client(_make_llm_result(
            basic_info={"business_description": "We build software solutions"}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.business_description == "We build software solutions"

    @pytest.mark.asyncio
    async def test_generate_does_not_overwrite_existing_specialization(self):
        """Pre-existing specialization must NOT be overwritten by LLM."""
        client = _mock_client(_make_llm_result(
            basic_info={"specialization": "LLM Suggestion"}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa(specialization="Already Set")

        result = await generator.generate(anketa)

        assert result.specialization == "Already Set"


# ===========================================================================
# 3. Services & Client Types
# ===========================================================================

class TestGenerateServices:

    @pytest.mark.asyncio
    async def test_generate_fills_services_from_strings(self):
        """Services provided as a simple list of strings should be stored directly."""
        client = _mock_client(_make_llm_result(
            clients_and_services={"services": ["Consulting", "Development", "Support"]}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.services == ["Consulting", "Development", "Support"]

    @pytest.mark.asyncio
    async def test_generate_fills_services_from_dicts(self):
        """Services provided as list of dicts should be mapped via .get('name')."""
        client = _mock_client(_make_llm_result(
            clients_and_services={
                "services": [
                    {"name": "Consulting", "price": "100"},
                    {"name": "Development", "price": "200"},
                ]
            }
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.services == ["Consulting", "Development"]

    @pytest.mark.asyncio
    async def test_generate_fills_client_types(self):
        """Client types from LLM should be stored when anketa field is empty."""
        client = _mock_client(_make_llm_result(
            clients_and_services={"client_types": ["SMB", "Enterprise", "Startup"]}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.client_types == ["SMB", "Enterprise", "Startup"]


# ===========================================================================
# 4. Agent Config
# ===========================================================================

class TestGenerateAgentConfig:

    @pytest.mark.asyncio
    async def test_generate_fills_agent_name(self):
        """LLM-suggested agent name should be written when field is empty."""
        client = _mock_client(_make_llm_result(
            agent_config={"name": "Ava"}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.agent_name == "Ava"

    @pytest.mark.asyncio
    async def test_generate_fills_voice_tone(self):
        """voice_tone should be filled when it is currently empty string."""
        client = _mock_client(_make_llm_result(
            agent_config={"tone": "friendly and warm"}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        # voice_tone defaults to "professional" which is truthy, so explicitly set empty
        anketa = _make_anketa(voice_tone="")

        result = await generator.generate(anketa)

        assert result.voice_tone == "friendly and warm"

    @pytest.mark.asyncio
    async def test_generate_fills_working_hours_and_transfer_conditions(self):
        """working_hours and transfer_conditions should both be populated from agent_config."""
        client = _mock_client(_make_llm_result(
            agent_config={
                "working_hours": {"mon-fri": "09:00-18:00"},
                "transfer_conditions": ["angry customer", "billing issues"],
            }
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.working_hours == {"mon-fri": "09:00-18:00"}
        assert result.transfer_conditions == ["angry customer", "billing issues"]


# ===========================================================================
# 5. Contact Info
# ===========================================================================

class TestGenerateContactInfo:

    @pytest.mark.asyncio
    async def test_generate_fills_contact_info(self):
        """All four contact fields (person, email, phone, website) should be filled."""
        client = _mock_client(_make_llm_result(
            contact_info={
                "person": "John Doe",
                "email": "john@example.com",
                "phone": "+1-555-0100",
                "website": "https://example.com",
            }
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.contact_name == "John Doe"
        assert result.contact_email == "john@example.com"
        assert result.contact_phone == "+1-555-0100"
        assert result.website == "https://example.com"

    @pytest.mark.asyncio
    async def test_generate_does_not_overwrite_existing_contact(self):
        """Pre-existing contact info must NOT be overwritten by LLM."""
        client = _mock_client(_make_llm_result(
            contact_info={
                "person": "LLM Person",
                "email": "llm@example.com",
                "phone": "+0-000-0000",
            }
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa(
            contact_name="Original Person",
            contact_email="original@example.com",
            contact_phone="+1-111-1111",
        )

        result = await generator.generate(anketa)

        assert result.contact_name == "Original Person"
        assert result.contact_email == "original@example.com"
        assert result.contact_phone == "+1-111-1111"

    @pytest.mark.asyncio
    async def test_generate_fills_website(self):
        """Website should be filled from LLM when anketa.website is None."""
        client = _mock_client(_make_llm_result(
            contact_info={"website": "https://testcorp.io"}
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()
        assert anketa.website is None  # precondition

        result = await generator.generate(anketa)

        assert result.website == "https://testcorp.io"


# ===========================================================================
# 6. Edge Cases
# ===========================================================================

class TestGenerateEdgeCases:

    @pytest.mark.asyncio
    async def test_generate_empty_llm_result_returns_unchanged(self):
        """An empty dict from LLM should leave the anketa completely unchanged."""
        client = _mock_client({})
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa(specialization="Existing")

        result = await generator.generate(anketa)

        # All original values preserved
        assert result.specialization == "Existing"
        assert result.company_name == "TestCorp"

    @pytest.mark.asyncio
    async def test_generate_null_llm_result_returns_unchanged(self):
        """None from LLM should return the anketa unchanged (early return path)."""
        client = _mock_client(None)
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa(specialization="Keep Me")

        result = await generator.generate(anketa)

        assert result.specialization == "Keep Me"
        assert result.company_name == "TestCorp"

    @pytest.mark.asyncio
    async def test_generate_fills_constraints_and_compliance(self):
        """constraints and compliance_requirements should be filled from additional_info."""
        client = _mock_client(_make_llm_result(
            additional_info={
                "restrictions": ["No medical advice", "No financial advice"],
                "compliance_requirements": ["GDPR", "HIPAA"],
            }
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa()

        result = await generator.generate(anketa)

        assert result.constraints == ["No medical advice", "No financial advice"]
        assert result.compliance_requirements == ["GDPR", "HIPAA"]

    @pytest.mark.asyncio
    async def test_generate_preserves_all_existing_fields(self):
        """When all fields are already filled, nothing should change."""
        client = _mock_client(_make_llm_result(
            basic_info={
                "specialization": "LLM Spec",
                "business_description": "LLM Desc",
            },
            clients_and_services={
                "services": ["LLM Service"],
                "client_types": ["LLM Client"],
                "typical_questions": ["LLM Question?"],
            },
            agent_config={
                "name": "LLM Agent",
                "tone": "LLM Tone",
                "working_hours": {"sat": "10-14"},
                "transfer_conditions": ["LLM Transfer"],
            },
            contact_info={
                "person": "LLM Person",
                "email": "llm@test.com",
                "phone": "+0-000",
                "website": "https://llm.test",
            },
            additional_info={
                "restrictions": ["LLM Restriction"],
                "compliance_requirements": ["LLM Compliance"],
            },
        ))
        generator = LLMAnketaGenerator(deepseek_client=client)
        anketa = _make_anketa(
            specialization="Original Spec",
            business_description="Original Desc",
            services=["Original Service"],
            client_types=["Original Client"],
            typical_questions=["Original Question?"],
            agent_name="Original Agent",
            voice_tone="Original Tone",
            working_hours={"mon": "9-17"},
            transfer_conditions=["Original Transfer"],
            contact_name="Original Person",
            contact_email="original@test.com",
            contact_phone="+1-111",
            website="https://original.test",
            constraints=["Original Restriction"],
            compliance_requirements=["Original Compliance"],
        )

        result = await generator.generate(anketa)

        # Every field should retain its original value
        assert result.specialization == "Original Spec"
        assert result.business_description == "Original Desc"
        assert result.services == ["Original Service"]
        assert result.client_types == ["Original Client"]
        assert result.typical_questions == ["Original Question?"]
        assert result.agent_name == "Original Agent"
        assert result.voice_tone == "Original Tone"
        assert result.working_hours == {"mon": "9-17"}
        assert result.transfer_conditions == ["Original Transfer"]
        assert result.contact_name == "Original Person"
        assert result.contact_email == "original@test.com"
        assert result.contact_phone == "+1-111"
        assert result.website == "https://original.test"
        assert result.constraints == ["Original Restriction"]
        assert result.compliance_requirements == ["Original Compliance"]
