"""
Pydantic schemas for the final anketa (questionnaire).

FinalAnketa v2.0 - Expert consultation deliverable.
Contains all data needed to build a voice agent PLUS AI-generated insights.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4
from pydantic import BaseModel, Field


# === BASIC MODELS ===

class AgentFunction(BaseModel):
    """A function that the voice agent should perform."""

    name: str = Field(..., description="Short name of the function")
    description: str = Field(..., description="Detailed description of what this function does")
    priority: str = Field(default="medium", description="Priority: high, medium, low")


class Integration(BaseModel):
    """An integration with an external system."""

    name: str = Field(..., description="Name of the system (e.g., 'Google Sheets', 'Telegram')")
    purpose: str = Field(..., description="What this integration is used for")
    required: bool = Field(default=True, description="Whether this integration is required")


# === NEW V2.0 MODELS ===

class FAQItem(BaseModel):
    """FAQ item with question and suggested answer."""

    question: str = Field(..., description="The question")
    answer: str = Field(..., description="Suggested answer")
    category: str = Field(default="general", description="Category: pricing, process, support, etc.")


class ObjectionHandler(BaseModel):
    """Objection handling script."""

    objection: str = Field(..., description="The objection (e.g., 'Too expensive')")
    response: str = Field(..., description="Suggested response")
    follow_up: Optional[str] = Field(default=None, description="Follow-up action")


class DialogueExample(BaseModel):
    """Example dialogue turn."""

    role: str = Field(..., description="bot or client")
    message: str = Field(..., description="The message")
    intent: Optional[str] = Field(default=None, description="Intent behind the message")


class FinancialMetric(BaseModel):
    """Financial model metric."""

    name: str = Field(..., description="Metric name")
    value: str = Field(..., description="Value (with units)")
    source: str = Field(default="client", description="Source: client, ai_benchmark, calculated")
    note: Optional[str] = Field(default=None, description="Additional note")


class Competitor(BaseModel):
    """Competitor analysis entry."""

    name: str = Field(..., description="Competitor name")
    strengths: List[str] = Field(default_factory=list, description="Their strengths")
    weaknesses: List[str] = Field(default_factory=list, description="Their weaknesses")
    price_range: Optional[str] = Field(default=None, description="Price range if known")


class EscalationRule(BaseModel):
    """Escalation scenario rule."""

    trigger: str = Field(..., description="What triggers escalation")
    urgency: str = Field(default="medium", description="Urgency: immediate, hour, day")
    action: str = Field(..., description="Action to take")


class KPIMetric(BaseModel):
    """KPI metric with target."""

    name: str = Field(..., description="Metric name")
    target: str = Field(..., description="Target value")
    benchmark: Optional[str] = Field(default=None, description="Industry benchmark")
    measurement: Optional[str] = Field(default=None, description="How to measure")


class ChecklistItem(BaseModel):
    """Onboarding checklist item."""

    item: str = Field(..., description="What needs to be done/provided")
    required: bool = Field(default=True, description="Is it required?")
    responsible: str = Field(default="client", description="Who is responsible: client, team, both")


class AIRecommendation(BaseModel):
    """AI-generated recommendation."""

    recommendation: str = Field(..., description="The recommendation")
    impact: str = Field(..., description="Expected impact")
    priority: str = Field(default="medium", description="Priority: high, medium, low")
    effort: str = Field(default="medium", description="Effort: low, medium, high")


class TargetAudienceSegment(BaseModel):
    """Detailed target audience segment."""

    name: str = Field(..., description="Segment name")
    description: str = Field(..., description="Description of this segment")
    pain_points: List[str] = Field(default_factory=list, description="Their specific pain points")
    triggers: List[str] = Field(default_factory=list, description="What triggers them to act")


class MarketInsight(BaseModel):
    """Market analysis insight."""

    insight: str = Field(..., description="The insight")
    source: str = Field(default="ai_analysis", description="Source of insight")
    relevance: str = Field(default="high", description="Relevance: high, medium, low")


class QAPair(BaseModel):
    """Question-answer pair from an interview."""

    question: str = Field(..., description="The question asked")
    answer: str = Field(default="", description="Respondent's answer")
    topic: str = Field(default="general", description="Topic tag")
    follow_ups: List[str] = Field(default_factory=list, description="Follow-up questions")


# === MAIN ANKETA MODEL ===

class FinalAnketa(BaseModel):
    """
    Complete questionnaire for creating a voice agent.

    v2.0 - Expert consultation deliverable.
    Contains client data PLUS AI-generated expert insights.
    """

    # ============================================================
    # IDENTITY (for storage and tracking)
    # ============================================================

    anketa_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique anketa ID")
    interview_id: str = Field(default="", description="Associated interview session ID")
    pattern: str = Field(default="interaction", description="Interview pattern: interaction or management")

    # ============================================================
    # BLOCK 1: BASIC INFORMATION (from client)
    # ============================================================

    # Company
    company_name: str = Field(..., description="Name of the company")
    industry: str = Field(..., description="Industry/sector")
    specialization: str = Field(default="", description="Company specialization")
    website: Optional[str] = Field(default=None, description="Company website URL")
    contact_name: str = Field(default="", description="Name of the contact person")
    contact_role: str = Field(default="", description="Role/position of the contact person")
    contact_email: str = Field(default="", description="Contact email address")
    contact_phone: str = Field(default="", description="Contact phone number")

    # Business Context
    business_description: str = Field(default="", description="Description of the business")
    services: List[str] = Field(default_factory=list, description="Services/products offered")
    client_types: List[str] = Field(default_factory=list, description="Types of clients")
    current_problems: List[str] = Field(default_factory=list, description="Current pain points")
    business_goals: List[str] = Field(default_factory=list, description="Goals for automation")
    business_type: Optional[str] = Field(default=None, description="Type of business (B2B, B2C, etc.)")
    constraints: List[str] = Field(default_factory=list, description="Constraints")
    compliance_requirements: List[str] = Field(default_factory=list, description="Compliance and regulatory requirements")

    # UI Compatibility & Additional Fields
    call_volume: str = Field(default="", description="Call volume per day/month")
    budget: str = Field(default="", description="Project budget with currency")
    timeline: str = Field(default="", description="Implementation timeline")
    additional_notes: str = Field(default="", description="Additional notes or special requirements")

    # Voice Agent Basic
    agent_name: str = Field(default="", description="Name of the voice agent")
    agent_purpose: str = Field(default="", description="Brief description of agent's purpose")
    agent_functions: List[AgentFunction] = Field(default_factory=list, description="List of agent functions")

    # Parameters
    voice_gender: str = Field(default="female", description="Voice gender: female/male")
    voice_tone: str = Field(default="professional", description="Voice tone")
    language: str = Field(default="ru", description="Language code")
    call_direction: str = Field(default="inbound", description="Call direction: inbound/outbound/both")
    working_hours: Dict[str, str] = Field(default_factory=dict, description="Working hours schedule")
    transfer_conditions: List[str] = Field(default_factory=list, description="Conditions for transferring to human")

    # Integrations
    integrations: List[Integration] = Field(default_factory=list, description="Required integrations")

    # Proposed Solution
    main_function: Optional[AgentFunction] = Field(default=None, description="Main function")
    additional_functions: List[AgentFunction] = Field(default_factory=list, description="Additional functions")

    # ============================================================
    # BLOCK 2: FAQ WITH ANSWERS (AI-generated)
    # ============================================================

    faq_items: List[FAQItem] = Field(
        default_factory=list,
        description="FAQ with suggested answers (AI-generated based on industry)"
    )

    # Legacy field for compatibility
    typical_questions: List[str] = Field(default_factory=list, description="Legacy FAQ questions only")

    # ============================================================
    # BLOCK 3: OBJECTION HANDLING (AI-generated)
    # ============================================================

    objection_handlers: List[ObjectionHandler] = Field(
        default_factory=list,
        description="Common objections and how to handle them"
    )

    # ============================================================
    # BLOCK 4: SAMPLE DIALOGUE (AI-generated)
    # ============================================================

    sample_dialogue: List[DialogueExample] = Field(
        default_factory=list,
        description="Example conversation flow"
    )

    # ============================================================
    # BLOCK 5: FINANCIAL MODEL (AI + Client)
    # ============================================================

    financial_metrics: List[FinancialMetric] = Field(
        default_factory=list,
        description="Financial model parameters"
    )

    # ============================================================
    # BLOCK 6: MARKET ANALYSIS (AI-generated)
    # ============================================================

    competitors: List[Competitor] = Field(
        default_factory=list,
        description="Competitor analysis"
    )

    market_insights: List[MarketInsight] = Field(
        default_factory=list,
        description="Market trends and insights"
    )

    competitive_advantages: List[str] = Field(
        default_factory=list,
        description="Client's competitive advantages"
    )

    # ============================================================
    # BLOCK 7: ESCALATION SCENARIOS (AI-generated)
    # ============================================================

    escalation_rules: List[EscalationRule] = Field(
        default_factory=list,
        description="When and how to escalate to human"
    )

    # ============================================================
    # BLOCK 8: KPI & SUCCESS METRICS (AI-generated)
    # ============================================================

    success_kpis: List[KPIMetric] = Field(
        default_factory=list,
        description="KPIs to track success"
    )

    # ============================================================
    # BLOCK 9: LAUNCH CHECKLIST (AI-generated)
    # ============================================================

    launch_checklist: List[ChecklistItem] = Field(
        default_factory=list,
        description="What client needs to prepare"
    )

    # ============================================================
    # BLOCK 10: AI RECOMMENDATIONS
    # ============================================================

    ai_recommendations: List[AIRecommendation] = Field(
        default_factory=list,
        description="AI expert recommendations"
    )

    # ============================================================
    # ADDITIONAL V2.0 FIELDS
    # ============================================================

    target_segments: List[TargetAudienceSegment] = Field(
        default_factory=list,
        description="Detailed target audience segments"
    )

    tone_of_voice: Dict[str, str] = Field(
        default_factory=dict,
        description="Brand voice guidelines: do's and don'ts"
    )

    error_handling_scripts: Dict[str, str] = Field(
        default_factory=dict,
        description="What to say in error scenarios"
    )

    follow_up_sequence: List[str] = Field(
        default_factory=list,
        description="Post-conversation follow-up steps"
    )

    # ============================================================
    # METADATA
    # ============================================================

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    consultation_duration_seconds: float = Field(default=0.0, description="Duration of consultation")
    anketa_version: str = Field(default="2.0", description="Anketa schema version")

    # Storage and tracking
    full_responses: Dict[str, Any] = Field(default_factory=dict, description="Raw responses from interview")
    quality_metrics: Dict[str, float] = Field(default_factory=dict, description="Quality metrics for this anketa")

    # Default values that should NOT count as "filled" for completion_rate
    _SCHEMA_DEFAULTS = {
        'voice_gender': 'female',
        'voice_tone': 'professional',
        'call_direction': 'inbound',
    }

    def completion_rate(self) -> float:
        """
        v5.0: Equal weight completion - все 15 полей обязательны.

        Fields with unchanged schema defaults (voice_gender="female",
        voice_tone="professional", call_direction="inbound") are NOT counted
        as filled — only explicitly extracted values count.

        Returns: float 0.0-1.0 (filled_count / 15)
        """
        required_fields = {
            # Блок 1: Компания (3)
            'company_name': self.company_name,
            'industry': self.industry,
            'business_description': self.business_description,

            # Блок 2: Услуги (3)
            'services': self.services,
            'current_problems': self.current_problems,
            'business_goals': self.business_goals,

            # Блок 3: Агент (3)
            'agent_name': self.agent_name,
            'agent_purpose': self.agent_purpose,
            'agent_functions': self.agent_functions,

            # Блок 4: Контакты (3) - теперь обязательны
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'contact_email': self.contact_email,

            # Блок 5: Дополнительно (3)
            'voice_gender': self.voice_gender,
            'voice_tone': self.voice_tone,
            'call_direction': self.call_direction,
        }

        filled_count = 0
        defaulted_count = 0
        for field_name, v in required_fields.items():
            # Skip fields that still have their schema default
            if field_name in self._SCHEMA_DEFAULTS and v == self._SCHEMA_DEFAULTS[field_name]:
                defaulted_count += 1
                continue
            # R23-02: Explicit type checks prevent whitespace-only strings from counting
            if isinstance(v, list):
                if len(v) > 0:
                    filled_count += 1
            elif isinstance(v, str):
                if v.strip():
                    filled_count += 1
            elif v is not None:
                filled_count += 1

        # R21-05: Denominator excludes fields with unchanged defaults
        # so max achievable is 1.0 (not capped at 0.8 when 3 defaults unchanged)
        effective_total = len(required_fields) - defaulted_count
        return filled_count / max(effective_total, 1)  # 0.0-1.0

    def get_required_fields_status(self) -> dict:
        """R21-03: Check status of required fields (aligned with completion_rate)."""
        required = {
            'company_name': self.company_name,
            'industry': self.industry,
            'business_description': self.business_description,
            'services': self.services,
            'current_problems': self.current_problems,
            'business_goals': self.business_goals,
            'agent_name': self.agent_name,
            'agent_purpose': self.agent_purpose,
            'agent_functions': self.agent_functions,
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'contact_email': self.contact_email,
        }

        return {
            field: bool(value) if not isinstance(value, (str, list)) else bool(value)
            for field, value in required.items()
        }

    def get_ai_generated_sections_status(self) -> dict:
        """Check which AI-generated sections are filled."""
        return {
            'faq_items': len(self.faq_items),
            'objection_handlers': len(self.objection_handlers),
            'sample_dialogue': len(self.sample_dialogue),
            'financial_metrics': len(self.financial_metrics),
            'competitors': len(self.competitors),
            'market_insights': len(self.market_insights),
            'escalation_rules': len(self.escalation_rules),
            'success_kpis': len(self.success_kpis),
            'launch_checklist': len(self.launch_checklist),
            'ai_recommendations': len(self.ai_recommendations),
        }


# === INTERVIEW ANKETA MODEL ===

class InterviewAnketa(BaseModel):
    """
    Anketa for interview mode — structured Q&A collection.

    Used when consultation_type == "interview".
    Focuses on collecting respondent answers rather than business analysis.
    """

    # Identity
    anketa_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique anketa ID")
    interview_id: str = Field(default="", description="Associated session ID")
    anketa_type: str = Field(default="interview", description="Always 'interview'")

    # Contacts
    company_name: str = Field(default="", description="Company or respondent organization")
    contact_name: str = Field(default="", description="Respondent name")
    contact_role: str = Field(default="", description="Respondent role")
    contact_email: str = Field(default="", description="Email")
    contact_phone: str = Field(default="", description="Phone")

    # Interview settings
    interview_type: str = Field(default="general", description="Type: market_research, customer_discovery, hr, survey, requirements")
    interview_title: str = Field(default="", description="Title or topic of the interview")
    target_topics: List[str] = Field(default_factory=list, description="Topics to cover")

    # Q&A data (core)
    qa_pairs: List[QAPair] = Field(default_factory=list, description="Question-answer pairs")
    detected_topics: List[str] = Field(default_factory=list, description="Topics detected in conversation")
    key_quotes: List[str] = Field(default_factory=list, description="Notable quotes from respondent")

    # Respondent profile
    interviewee_context: str = Field(default="", description="Context about respondent")
    interviewee_industry: str = Field(default="", description="Respondent's industry")

    # AI analysis (generated after interview)
    summary: str = Field(default="", description="AI-generated interview summary")
    key_insights: List[str] = Field(default_factory=list, description="Key insights from interview")
    ai_recommendations: List[AIRecommendation] = Field(default_factory=list, description="AI recommendations")
    unresolved_topics: List[str] = Field(default_factory=list, description="Topics not fully covered")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    consultation_duration_seconds: float = Field(default=0.0, description="Duration")
    anketa_version: str = Field(default="2.0", description="Schema version")

    def completion_rate(self) -> float:
        """Calculate completion based on Q&A coverage and contact info."""
        score = 0.0
        total = 0.0

        # Contact info (weight: 20%)
        contact_fields = [self.company_name, self.contact_name, self.interview_title]
        contact_filled = sum(1 for f in contact_fields if f and f.strip())
        score += 0.2 * (contact_filled / max(len(contact_fields), 1))
        total += 0.2

        # Q&A pairs (weight: 70%)
        if self.qa_pairs:
            answered = sum(1 for qa in self.qa_pairs if qa.answer.strip())
            score += 0.7 * (answered / len(self.qa_pairs))
        total += 0.7

        # Topics detected (weight: 10%)
        if self.detected_topics:
            score += 0.1
        total += 0.1

        return score / total if total > 0 else 0.0


# Backward-compatible alias
ConsultationAnketa = FinalAnketa
