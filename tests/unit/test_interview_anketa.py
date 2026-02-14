"""
Unit tests for InterviewAnketa and QAPair models (v5.0) from src/anketa/schema.py.

Tests cover:
- QAPair model: creation, defaults, validation
- InterviewAnketa model: creation, defaults, UUID uniqueness, full population
- InterviewAnketa.completion_rate(): weighted scoring across contact, Q&A, and topics
- ConsultationAnketa backward-compatible alias
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError

from src.anketa.schema import (
    QAPair,
    InterviewAnketa,
    AIRecommendation,
    FinalAnketa,
    ConsultationAnketa,
)


# ============================================================
# QAPair Model Tests
# ============================================================

class TestQAPairCreation:
    """Test QAPair model creation and defaults."""

    def test_create_with_required_question(self):
        """QAPair can be created with only the required 'question' field."""
        qa = QAPair(question="What is your role?")
        assert qa.question == "What is your role?"

    def test_default_answer_is_empty_string(self):
        """Default answer should be an empty string."""
        qa = QAPair(question="Test?")
        assert qa.answer == ""

    def test_default_topic_is_general(self):
        """Default topic should be 'general'."""
        qa = QAPair(question="Test?")
        assert qa.topic == "general"

    def test_default_follow_ups_is_empty_list(self):
        """Default follow_ups should be an empty list."""
        qa = QAPair(question="Test?")
        assert qa.follow_ups == []
        assert isinstance(qa.follow_ups, list)

    def test_custom_values_for_all_fields(self):
        """QAPair accepts custom values for every field."""
        qa = QAPair(
            question="How many employees?",
            answer="About 50",
            topic="company_size",
            follow_ups=["In which departments?", "Remote or on-site?"],
        )
        assert qa.question == "How many employees?"
        assert qa.answer == "About 50"
        assert qa.topic == "company_size"
        assert qa.follow_ups == ["In which departments?", "Remote or on-site?"]
        assert len(qa.follow_ups) == 2

    def test_question_is_required(self):
        """Creating QAPair without 'question' must raise ValidationError."""
        with pytest.raises(ValidationError):
            QAPair()

    def test_question_is_required_explicit_none(self):
        """Passing question=None must raise ValidationError."""
        with pytest.raises(ValidationError):
            QAPair(question=None)

    def test_follow_ups_list_independence(self):
        """Each QAPair instance should have its own follow_ups list (no shared mutable default)."""
        qa1 = QAPair(question="Q1")
        qa2 = QAPair(question="Q2")
        qa1.follow_ups.append("Follow-up for Q1")
        assert qa2.follow_ups == []

    def test_json_serialization(self):
        """QAPair can be serialized to JSON and back."""
        qa = QAPair(
            question="What tools do you use?",
            answer="Slack, Jira",
            topic="tools",
            follow_ups=["Any custom integrations?"],
        )
        json_str = qa.model_dump_json()
        assert "What tools do you use?" in json_str
        assert "Slack, Jira" in json_str

        restored = QAPair.model_validate_json(json_str)
        assert restored.question == qa.question
        assert restored.answer == qa.answer
        assert restored.topic == qa.topic
        assert restored.follow_ups == qa.follow_ups

    def test_dict_serialization(self):
        """QAPair can be converted to dict."""
        qa = QAPair(question="Test?", answer="Yes", topic="misc")
        d = qa.model_dump()
        assert d["question"] == "Test?"
        assert d["answer"] == "Yes"
        assert d["topic"] == "misc"
        assert d["follow_ups"] == []


# ============================================================
# InterviewAnketa Creation Tests
# ============================================================

class TestInterviewAnketaCreation:
    """Test InterviewAnketa model creation and defaults."""

    def test_default_creation(self):
        """InterviewAnketa can be created with no arguments (all fields have defaults)."""
        anketa = InterviewAnketa()
        assert anketa is not None
        assert isinstance(anketa, InterviewAnketa)

    def test_anketa_type_default_is_interview(self):
        """anketa_type should always default to 'interview'."""
        anketa = InterviewAnketa()
        assert anketa.anketa_type == "interview"

    def test_anketa_type_can_be_overridden(self):
        """anketa_type can technically be set to another value (no enum constraint)."""
        anketa = InterviewAnketa(anketa_type="custom")
        assert anketa.anketa_type == "custom"

    def test_anketa_id_is_uuid_format(self):
        """anketa_id should be a valid UUID string."""
        anketa = InterviewAnketa()
        parsed = uuid.UUID(anketa.anketa_id)
        assert str(parsed) == anketa.anketa_id

    def test_anketa_id_unique_across_instances(self):
        """Each InterviewAnketa instance should get a unique anketa_id."""
        ids = {InterviewAnketa().anketa_id for _ in range(50)}
        assert len(ids) == 50

    def test_default_string_fields_are_empty(self):
        """All default string fields should be empty strings."""
        anketa = InterviewAnketa()
        assert anketa.interview_id == ""
        assert anketa.company_name == ""
        assert anketa.contact_name == ""
        assert anketa.contact_role == ""
        assert anketa.contact_email == ""
        assert anketa.contact_phone == ""
        assert anketa.interview_type == "general"
        assert anketa.interview_title == ""
        assert anketa.interviewee_context == ""
        assert anketa.interviewee_industry == ""
        assert anketa.summary == ""

    def test_default_list_fields_are_empty(self):
        """All default list fields should be empty lists."""
        anketa = InterviewAnketa()
        assert anketa.target_topics == []
        assert anketa.qa_pairs == []
        assert anketa.detected_topics == []
        assert anketa.key_quotes == []
        assert anketa.key_insights == []
        assert anketa.ai_recommendations == []
        assert anketa.unresolved_topics == []

    def test_default_metadata_fields(self):
        """Metadata fields should have sensible defaults."""
        anketa = InterviewAnketa()
        assert isinstance(anketa.created_at, datetime)
        assert anketa.consultation_duration_seconds == 0.0
        assert anketa.anketa_version == "2.0"

    def test_created_at_is_approximately_now(self):
        """created_at should be close to the current time."""
        before = datetime.now(timezone.utc)
        anketa = InterviewAnketa()
        after = datetime.now(timezone.utc)
        assert before <= anketa.created_at <= after

    def test_full_creation_with_all_fields(self):
        """InterviewAnketa can be created with all fields populated."""
        rec = AIRecommendation(
            recommendation="Use structured interviews",
            impact="Higher data quality",
            priority="high",
            effort="low",
        )
        qa = QAPair(
            question="What is your main challenge?",
            answer="Scaling the team",
            topic="challenges",
            follow_ups=["How are you addressing it?"],
        )
        anketa = InterviewAnketa(
            anketa_id="custom-id-123",
            interview_id="session-456",
            anketa_type="interview",
            company_name="Acme Corp",
            contact_name="Jane Doe",
            contact_role="CTO",
            contact_email="jane@acme.com",
            contact_phone="+1-555-0100",
            interview_type="customer_discovery",
            interview_title="Product Feedback Session",
            target_topics=["usability", "pricing", "features"],
            qa_pairs=[qa],
            detected_topics=["challenges", "scaling"],
            key_quotes=["Scaling the team is our #1 priority"],
            interviewee_context="Series B startup, 50 employees",
            interviewee_industry="SaaS",
            summary="Respondent focused on scaling challenges.",
            key_insights=["Team scaling is critical"],
            ai_recommendations=[rec],
            unresolved_topics=["budget"],
            consultation_duration_seconds=1800.0,
            anketa_version="2.0",
        )
        assert anketa.anketa_id == "custom-id-123"
        assert anketa.interview_id == "session-456"
        assert anketa.company_name == "Acme Corp"
        assert anketa.contact_name == "Jane Doe"
        assert anketa.contact_role == "CTO"
        assert anketa.contact_email == "jane@acme.com"
        assert anketa.contact_phone == "+1-555-0100"
        assert anketa.interview_type == "customer_discovery"
        assert anketa.interview_title == "Product Feedback Session"
        assert len(anketa.target_topics) == 3
        assert len(anketa.qa_pairs) == 1
        assert anketa.qa_pairs[0].answer == "Scaling the team"
        assert len(anketa.detected_topics) == 2
        assert len(anketa.key_quotes) == 1
        assert anketa.interviewee_context == "Series B startup, 50 employees"
        assert anketa.interviewee_industry == "SaaS"
        assert anketa.summary == "Respondent focused on scaling challenges."
        assert len(anketa.key_insights) == 1
        assert len(anketa.ai_recommendations) == 1
        assert anketa.ai_recommendations[0].priority == "high"
        assert len(anketa.unresolved_topics) == 1
        assert anketa.consultation_duration_seconds == 1800.0

    def test_json_round_trip(self):
        """InterviewAnketa can be serialized to JSON and deserialized back."""
        original = InterviewAnketa(
            company_name="RoundTrip LLC",
            contact_name="Bob",
            interview_title="Market Research",
            qa_pairs=[QAPair(question="Q1", answer="A1")],
            detected_topics=["market"],
        )
        json_str = original.model_dump_json()
        restored = InterviewAnketa.model_validate_json(json_str)
        assert restored.company_name == "RoundTrip LLC"
        assert restored.contact_name == "Bob"
        assert len(restored.qa_pairs) == 1
        assert restored.qa_pairs[0].question == "Q1"

    def test_list_fields_are_independent(self):
        """Mutable list defaults should not be shared between instances."""
        a1 = InterviewAnketa()
        a2 = InterviewAnketa()
        a1.detected_topics.append("topic_a")
        a1.qa_pairs.append(QAPair(question="Q?"))
        assert a2.detected_topics == []
        assert a2.qa_pairs == []


# ============================================================
# InterviewAnketa.completion_rate() Tests
# ============================================================

class TestInterviewAnketaCompletionRate:
    """Test the weighted completion_rate() method.

    Weight breakdown:
    - Contact info (company_name, contact_name, interview_title): 20%
    - Q&A pairs answered: 70%
    - Detected topics present: 10%
    Total possible: 1.0
    """

    def test_empty_anketa_returns_zero(self):
        """Empty anketa with no data filled should return 0.0."""
        anketa = InterviewAnketa()
        assert anketa.completion_rate() == 0.0

    def test_only_all_contacts_filled(self):
        """Filling all three contact fields yields ~0.2."""
        anketa = InterviewAnketa(
            company_name="Acme",
            contact_name="Alice",
            interview_title="Discovery Call",
        )
        rate = anketa.completion_rate()
        assert abs(rate - 0.2) < 0.001

    def test_only_one_contact_filled(self):
        """Filling one of three contact fields yields ~0.2 * (1/3)."""
        anketa = InterviewAnketa(company_name="Acme")
        rate = anketa.completion_rate()
        expected = 0.2 * (1 / 3)
        assert abs(rate - expected) < 0.001

    def test_only_two_contacts_filled(self):
        """Filling two of three contact fields yields ~0.2 * (2/3)."""
        anketa = InterviewAnketa(
            company_name="Acme",
            contact_name="Alice",
        )
        rate = anketa.completion_rate()
        expected = 0.2 * (2 / 3)
        assert abs(rate - expected) < 0.001

    def test_only_qa_pairs_all_answered(self):
        """All Q&A pairs answered yields ~0.7."""
        anketa = InterviewAnketa(
            qa_pairs=[
                QAPair(question="Q1", answer="A1"),
                QAPair(question="Q2", answer="A2"),
                QAPair(question="Q3", answer="A3"),
            ]
        )
        rate = anketa.completion_rate()
        assert abs(rate - 0.7) < 0.001

    def test_only_qa_pairs_some_answered(self):
        """Some Q&A pairs answered yields proportional score."""
        anketa = InterviewAnketa(
            qa_pairs=[
                QAPair(question="Q1", answer="A1"),
                QAPair(question="Q2", answer=""),
                QAPair(question="Q3", answer="A3"),
                QAPair(question="Q4", answer=""),
            ]
        )
        rate = anketa.completion_rate()
        # 2 out of 4 answered: 0.7 * (2/4) = 0.35
        expected = 0.7 * (2 / 4)
        assert abs(rate - expected) < 0.001

    def test_only_qa_pairs_none_answered(self):
        """Q&A pairs present but none answered yields 0 for Q&A component."""
        anketa = InterviewAnketa(
            qa_pairs=[
                QAPair(question="Q1"),
                QAPair(question="Q2"),
            ]
        )
        rate = anketa.completion_rate()
        # All answers are empty: 0.7 * 0/2 = 0.0
        assert rate == 0.0

    def test_only_detected_topics_filled(self):
        """Having detected_topics yields ~0.1."""
        anketa = InterviewAnketa(
            detected_topics=["pricing", "features"],
        )
        rate = anketa.completion_rate()
        assert abs(rate - 0.1) < 0.001

    def test_full_completion_rate(self):
        """All components filled should yield 1.0."""
        anketa = InterviewAnketa(
            company_name="Acme Corp",
            contact_name="Alice",
            interview_title="Discovery Session",
            qa_pairs=[
                QAPair(question="Q1", answer="A1"),
                QAPair(question="Q2", answer="A2"),
            ],
            detected_topics=["topic1"],
        )
        rate = anketa.completion_rate()
        # 0.2 (contacts 3/3) + 0.7 (qa 2/2) + 0.1 (topics present) = 1.0
        assert abs(rate - 1.0) < 0.001

    def test_whitespace_only_answers_do_not_count(self):
        """Answers containing only whitespace should not count as answered."""
        anketa = InterviewAnketa(
            qa_pairs=[
                QAPair(question="Q1", answer="   "),
                QAPair(question="Q2", answer="\t"),
                QAPair(question="Q3", answer="\n"),
            ]
        )
        rate = anketa.completion_rate()
        # None of the answers count: Q&A contribution = 0
        assert rate == 0.0

    def test_whitespace_only_contacts_do_not_count(self):
        """Contact fields with only whitespace should not count as filled."""
        anketa = InterviewAnketa(
            company_name="   ",
            contact_name="\t",
            interview_title="  \n  ",
        )
        rate = anketa.completion_rate()
        assert rate == 0.0

    def test_mixed_whitespace_and_real_answers(self):
        """Mix of real answers and whitespace-only answers."""
        anketa = InterviewAnketa(
            qa_pairs=[
                QAPair(question="Q1", answer="Real answer"),
                QAPair(question="Q2", answer="   "),
                QAPair(question="Q3", answer="Another real one"),
                QAPair(question="Q4", answer="\t\n"),
            ]
        )
        rate = anketa.completion_rate()
        # 2 out of 4 real answers: 0.7 * (2/4) = 0.35
        expected = 0.7 * (2 / 4)
        assert abs(rate - expected) < 0.001

    def test_single_qa_pair_answered(self):
        """Single Q&A pair fully answered."""
        anketa = InterviewAnketa(
            qa_pairs=[QAPair(question="Q1", answer="A1")]
        )
        rate = anketa.completion_rate()
        assert abs(rate - 0.7) < 0.001

    def test_contacts_and_topics_without_qa(self):
        """Contacts and topics filled but no Q&A pairs at all."""
        anketa = InterviewAnketa(
            company_name="Acme",
            contact_name="Alice",
            interview_title="Session",
            detected_topics=["pricing"],
        )
        rate = anketa.completion_rate()
        # 0.2 (contacts 3/3) + 0.0 (no qa_pairs) + 0.1 (topics) = 0.3
        expected = 0.2 + 0.0 + 0.1
        assert abs(rate - expected) < 0.001

    def test_partial_contacts_plus_full_qa_plus_topics(self):
        """Partial contacts + all Q&A answered + topics."""
        anketa = InterviewAnketa(
            company_name="Acme",
            # contact_name and interview_title left empty
            qa_pairs=[
                QAPair(question="Q1", answer="A1"),
                QAPair(question="Q2", answer="A2"),
            ],
            detected_topics=["scaling"],
        )
        rate = anketa.completion_rate()
        # contacts: 0.2 * (1/3) + qa: 0.7 * (2/2) + topics: 0.1
        expected = 0.2 * (1 / 3) + 0.7 + 0.1
        assert abs(rate - expected) < 0.001

    def test_completion_rate_returns_float(self):
        """completion_rate() should always return a float."""
        anketa = InterviewAnketa()
        rate = anketa.completion_rate()
        assert isinstance(rate, float)

    def test_completion_rate_is_between_zero_and_one(self):
        """completion_rate() should always be in [0.0, 1.0]."""
        # Test various configurations
        cases = [
            InterviewAnketa(),
            InterviewAnketa(company_name="X"),
            InterviewAnketa(qa_pairs=[QAPair(question="Q", answer="A")]),
            InterviewAnketa(detected_topics=["t"]),
            InterviewAnketa(
                company_name="X",
                contact_name="Y",
                interview_title="Z",
                qa_pairs=[QAPair(question="Q", answer="A")],
                detected_topics=["t"],
            ),
        ]
        for anketa in cases:
            rate = anketa.completion_rate()
            assert 0.0 <= rate <= 1.0, f"Rate {rate} out of bounds for {anketa}"

    def test_empty_qa_pairs_list_contributes_zero(self):
        """An empty qa_pairs list should contribute 0 to the Q&A component."""
        anketa = InterviewAnketa(
            company_name="Acme",
            contact_name="Alice",
            interview_title="Title",
            qa_pairs=[],
            detected_topics=["topic"],
        )
        rate = anketa.completion_rate()
        # 0.2 (contacts) + 0.0 (empty qa) + 0.1 (topics) = 0.3
        expected = 0.3
        assert abs(rate - expected) < 0.001

    def test_many_qa_pairs_one_answered(self):
        """Many Q&A pairs with only one answered."""
        pairs = [QAPair(question=f"Q{i}") for i in range(10)]
        pairs[0] = QAPair(question="Q0", answer="Real answer")
        anketa = InterviewAnketa(qa_pairs=pairs)
        rate = anketa.completion_rate()
        expected = 0.7 * (1 / 10)
        assert abs(rate - expected) < 0.001


# ============================================================
# ConsultationAnketa Backward-Compatible Alias Test
# ============================================================

class TestConsultationAnketaAlias:
    """Test that ConsultationAnketa is a backward-compatible alias for FinalAnketa."""

    def test_alias_identity(self):
        """ConsultationAnketa should be the exact same class as FinalAnketa."""
        assert ConsultationAnketa is FinalAnketa

    def test_isinstance_check_with_alias(self):
        """An instance of ConsultationAnketa should be an instance of FinalAnketa."""
        obj = ConsultationAnketa(company_name="Test", industry="IT")
        assert isinstance(obj, FinalAnketa)
        assert isinstance(obj, ConsultationAnketa)

    def test_isinstance_check_reverse(self):
        """An instance of FinalAnketa should also be an instance of ConsultationAnketa."""
        obj = FinalAnketa(company_name="Test", industry="IT")
        assert isinstance(obj, ConsultationAnketa)

    def test_alias_creates_functional_instance(self):
        """ConsultationAnketa can be used to create fully functional FinalAnketa instances."""
        obj = ConsultationAnketa(
            company_name="Alias Corp",
            industry="Finance",
            business_description="Financial services",
        )
        assert obj.company_name == "Alias Corp"
        assert obj.industry == "Finance"
        assert obj.business_description == "Financial services"
        assert hasattr(obj, "completion_rate")
        assert callable(obj.completion_rate)

    def test_alias_type_name(self):
        """The type name of an instance created via the alias should be FinalAnketa."""
        obj = ConsultationAnketa(company_name="Test", industry="IT")
        assert type(obj).__name__ == "FinalAnketa"
