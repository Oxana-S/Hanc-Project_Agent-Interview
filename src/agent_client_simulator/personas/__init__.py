"""
Personas module for simulated client behavior.

Provides:
- PersonaTrait: Personality trait definition
- BehaviorConfig: Behavior configuration from YAML
- BehaviorEngine: Decision engine for client behavior
- TraitsLibrary: Traits loaded from config
"""

from .models import (
    BehaviorAction,
    BehaviorConfig,
    BehaviorDecision,
    ObjectionContext,
    PersonaTrait,
    PhaseContext,
    ResponseStyle,
    TraitCategory,
    TriggerRule,
)
from .traits import TraitsLibrary, get_traits_library
from .behavior import BehaviorEngine

__all__ = [
    # Models
    'BehaviorAction',
    'BehaviorConfig',
    'BehaviorDecision',
    'ObjectionContext',
    'PersonaTrait',
    'PhaseContext',
    'ResponseStyle',
    'TraitCategory',
    'TriggerRule',
    # Traits
    'TraitsLibrary',
    'get_traits_library',
    # Behavior
    'BehaviorEngine',
]
