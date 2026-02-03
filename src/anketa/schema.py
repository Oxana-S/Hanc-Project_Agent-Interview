"""
Pydantic schemas for the final anketa (questionnaire).

FinalAnketa contains all data needed to build a voice agent.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


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


class FinalAnketa(BaseModel):
    """
    Complete questionnaire for creating a voice agent.

    This is the final output of a consultation session, containing
    all structured data extracted from the dialogue.
    """

    # === COMPANY ===
    company_name: str = Field(..., description="Name of the company")
    industry: str = Field(..., description="Industry/sector")
    specialization: str = Field(default="", description="Company specialization")
    website: Optional[str] = Field(default=None, description="Company website URL")
    contact_name: str = Field(default="", description="Name of the contact person")
    contact_role: str = Field(default="", description="Role/position of the contact person")

    # === BUSINESS CONTEXT ===
    business_description: str = Field(default="", description="Description of the business")
    services: List[str] = Field(default_factory=list, description="Services/products offered")
    client_types: List[str] = Field(default_factory=list, description="Types of clients (B2B, B2C, partners)")
    current_problems: List[str] = Field(default_factory=list, description="Current pain points")
    business_goals: List[str] = Field(default_factory=list, description="Goals for automation")
    constraints: List[str] = Field(default_factory=list, description="Constraints (budget, timeline, technical)")

    # === VOICE AGENT ===
    agent_name: str = Field(default="", description="Name of the voice agent")
    agent_purpose: str = Field(default="", description="Brief description of agent's purpose")
    agent_functions: List[AgentFunction] = Field(default_factory=list, description="List of agent functions")
    typical_questions: List[str] = Field(default_factory=list, description="FAQ that the agent should handle")

    # === PARAMETERS ===
    voice_gender: str = Field(default="female", description="Voice gender: female/male")
    voice_tone: str = Field(default="professional", description="Voice tone: professional, friendly, calm")
    language: str = Field(default="ru", description="Language code")
    call_direction: str = Field(default="inbound", description="Call direction: inbound/outbound/both")

    # === INTEGRATIONS ===
    integrations: List[Integration] = Field(default_factory=list, description="Required integrations")

    # === PROPOSED SOLUTION ===
    main_function: Optional[AgentFunction] = Field(default=None, description="Main function from proposed solution")
    additional_functions: List[AgentFunction] = Field(default_factory=list, description="Additional functions")

    # === METADATA ===
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    consultation_duration_seconds: float = Field(default=0.0, description="Duration of consultation in seconds")

    def completion_rate(self) -> float:
        """Calculate the percentage of filled fields."""
        fields = self.model_dump(exclude={'created_at', 'consultation_duration_seconds'})
        total = 0
        filled = 0

        for key, value in fields.items():
            total += 1
            if value:
                if isinstance(value, list):
                    if len(value) > 0:
                        filled += 1
                elif isinstance(value, str):
                    if value.strip():
                        filled += 1
                elif isinstance(value, dict):
                    if value:
                        filled += 1
                else:
                    filled += 1

        return (filled / total * 100) if total > 0 else 0.0

    def get_required_fields_status(self) -> dict:
        """Check status of required fields."""
        required = {
            'company_name': self.company_name,
            'industry': self.industry,
            'agent_name': self.agent_name,
            'agent_purpose': self.agent_purpose,
            'main_function': self.main_function,
        }

        return {
            field: bool(value) if not isinstance(value, str) else bool(value.strip())
            for field, value in required.items()
        }
