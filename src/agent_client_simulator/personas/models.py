"""
Pydantic models for persona traits and behavior system.

All text content (prompts, patterns, hints) is loaded from config/personas/*.yaml
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TraitCategory(str, Enum):
    """Categories of personality traits."""
    COMMUNICATION = "communication"
    DECISION = "decision"
    KNOWLEDGE = "knowledge"
    EMOTIONAL = "emotional"


class BehaviorAction(str, Enum):
    """Possible behavior actions."""
    RESPOND = "respond"
    OBJECT = "object"
    QUESTION = "question"
    HESITATE = "hesitate"
    INTERRUPT = "interrupt"


class TriggerRule(BaseModel):
    """Rule for triggering specific behavior."""
    keyword: str = Field(..., description="Regex pattern to match")
    action: BehaviorAction
    probability: float = Field(0.5, ge=0.0, le=1.0)
    response_hint: Optional[str] = None


class PersonaTrait(BaseModel):
    """
    Personality trait definition.

    Numerical parameters only - text loaded from config.
    """
    id: str
    category: TraitCategory

    # Modifiers (multipliers, 1.0 = normal)
    response_length: float = Field(1.0, ge=0.1, le=3.0)
    detail_level: float = Field(1.0, ge=0.1, le=3.0)
    formality: float = Field(1.0, ge=0.1, le=3.0)

    # Probabilities (0.0 - 1.0)
    objection_prob: float = Field(0.2, ge=0.0, le=1.0)
    question_prob: float = Field(0.3, ge=0.0, le=1.0)
    interrupt_prob: float = Field(0.1, ge=0.0, le=1.0)
    hesitation_prob: float = Field(0.1, ge=0.0, le=1.0)

    # Focus topics (loaded from config)
    focuses_on: List[str] = Field(default_factory=list)
    avoids_topics: List[str] = Field(default_factory=list)


class BehaviorConfig(BaseModel):
    """
    Behavior configuration from scenario YAML.

    Combines numerical parameters with trait references.
    """
    # Numerical parameters (0.0 - 1.0)
    patience: float = Field(0.5, ge=0.0, le=1.0)
    skepticism: float = Field(0.3, ge=0.0, le=1.0)
    technical_level: float = Field(0.5, ge=0.0, le=1.0)
    decisiveness: float = Field(0.5, ge=0.0, le=1.0)
    price_sensitivity: float = Field(0.3, ge=0.0, le=1.0)

    # Named traits from library
    traits: List[str] = Field(default_factory=list)

    # Custom triggers
    triggers: List[TriggerRule] = Field(default_factory=list)

    # Phase-specific modifiers
    phase_modifiers: Dict[str, Dict[str, float]] = Field(default_factory=dict)

    # Randomness factor (0 = deterministic, 1 = chaotic)
    randomness: float = Field(0.3, ge=0.0, le=1.0)

    # Seed for reproducibility (optional)
    seed: Optional[int] = None


class BehaviorDecision(BaseModel):
    """Decision about how to behave."""
    action: BehaviorAction
    modifier: Optional[str] = None
    triggered_by: Optional[str] = None  # What triggered this decision


class ResponseStyle(BaseModel):
    """Style parameters for response generation."""
    length_modifier: float = 1.0
    detail_modifier: float = 1.0
    formality_modifier: float = 1.0

    # Instructions loaded from config based on modifiers
    length_instruction_key: str = "normal"
    formality_instruction_key: str = "normal"
    detail_instruction_key: str = "normal"


class PhaseContext(BaseModel):
    """Context for current consultation phase."""
    phase: str
    turn_number: int = 0

    # Applied modifiers for this phase
    applied_modifiers: Dict[str, float] = Field(default_factory=dict)


class ObjectionContext(BaseModel):
    """Context for generating objection."""
    topic: str  # price, time, guarantee, technical, general
    triggered_by: str  # What message part triggered
    severity: float = 0.5  # How strong the objection should be
