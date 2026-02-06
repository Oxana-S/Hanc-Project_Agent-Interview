"""
Behavior Engine for simulated client.

Decides how the client should react based on traits and context.
All text/prompt content is loaded from external configuration.
"""

import re
import random
from typing import Dict, List, Optional, Tuple

from .models import (
    BehaviorAction,
    BehaviorConfig,
    BehaviorDecision,
    ObjectionContext,
    PersonaTrait,
    PhaseContext,
    ResponseStyle,
    TriggerRule,
)
from .traits import get_traits_library


class BehaviorEngine:
    """
    Engine that determines client behavior based on traits and context.

    Uses probabilistic decisions influenced by:
    - Loaded personality traits
    - Numerical behavior parameters
    - Custom trigger rules
    - Phase-specific modifiers
    """

    def __init__(
        self,
        config: BehaviorConfig,
        traits: Optional[List[PersonaTrait]] = None,
    ):
        """
        Initialize behavior engine.

        Args:
            config: BehaviorConfig with parameters and trait references
            traits: Optional pre-loaded traits (loads from library if not provided)
        """
        self.config = config

        # Load traits from library if not provided
        if traits is not None:
            self.traits = traits
        else:
            library = get_traits_library()
            self.traits = library.get_many(config.traits)

        # Set random seed for reproducibility
        if config.seed is not None:
            random.seed(config.seed)

        # Compute aggregated parameters
        self._params = self._compute_params()

        # Current phase context
        self._phase_context: Optional[PhaseContext] = None

    def _compute_params(self) -> Dict[str, float]:
        """Compute aggregated behavioral parameters from config and traits."""
        # Start with config values
        params = {
            'patience': self.config.patience,
            'skepticism': self.config.skepticism,
            'technical_level': self.config.technical_level,
            'decisiveness': self.config.decisiveness,
            'price_sensitivity': self.config.price_sensitivity,
            # From traits
            'response_length': 1.0,
            'detail_level': 1.0,
            'formality': 1.0,
            'objection_prob': 0.2,
            'question_prob': 0.3,
            'interrupt_prob': 0.1,
            'hesitation_prob': 0.1,
        }

        # Aggregate traits
        if self.traits:
            # Multiplicative modifiers
            for modifier in ['response_length', 'detail_level', 'formality']:
                values = [getattr(t, modifier, 1.0) for t in self.traits]
                params[modifier] = sum(values) / len(values)

            # Probabilities - take maximum (dominant trait wins)
            for prob in ['objection_prob', 'question_prob', 'interrupt_prob', 'hesitation_prob']:
                values = [getattr(t, prob, 0.0) for t in self.traits]
                params[prob] = max(params[prob], max(values) if values else 0.0)

        # Map config values to probabilities
        # Higher skepticism -> higher objection probability
        params['objection_prob'] = max(
            params['objection_prob'],
            self.config.skepticism * 0.7
        )
        # Lower patience -> higher interrupt probability
        params['interrupt_prob'] = max(
            params['interrupt_prob'],
            (1.0 - self.config.patience) * 0.3
        )
        # Lower decisiveness -> higher hesitation
        params['hesitation_prob'] = max(
            params['hesitation_prob'],
            (1.0 - self.config.decisiveness) * 0.5
        )

        return params

    def set_phase(self, phase: str, turn: int = 0) -> None:
        """
        Set current consultation phase.

        Applies phase-specific modifiers.

        Args:
            phase: Phase name (discovery, analysis, proposal, refinement)
            turn: Current turn number
        """
        modifiers = self.config.phase_modifiers.get(phase, {})

        self._phase_context = PhaseContext(
            phase=phase,
            turn_number=turn,
            applied_modifiers=modifiers,
        )

        # Apply phase modifiers
        for key, value in modifiers.items():
            if key in self._params:
                self._params[key] = value

    def decide(
        self,
        message: str,
        context: Optional[Dict] = None
    ) -> BehaviorDecision:
        """
        Decide how to react to consultant's message.

        Args:
            message: Consultant's message
            context: Additional context

        Returns:
            BehaviorDecision with action and modifiers
        """
        context = context or {}
        message_lower = message.lower()

        # Check custom triggers first
        trigger_result = self._check_triggers(message_lower)
        if trigger_result:
            return trigger_result

        # Check focus topics
        focus_triggered = self._check_focuses(message_lower)

        # Probabilistic decision with randomness
        noise = (random.random() - 0.5) * self.config.randomness
        roll = random.random()

        # Decision order by priority:
        # 1. Interrupt (if impatient)
        if roll < self._params['interrupt_prob'] + noise:
            return BehaviorDecision(
                action=BehaviorAction.INTERRUPT,
                modifier='impatience',
            )

        # 2. Objection (if skeptic or triggered)
        obj_prob = self._params['objection_prob']
        if focus_triggered:
            obj_prob *= 1.5  # Boost if topic is important

        if roll < obj_prob + noise:
            objection_topic = self._detect_objection_topic(message_lower)
            return BehaviorDecision(
                action=BehaviorAction.OBJECT,
                modifier=objection_topic,
            )

        # 3. Question (technical or clarifying)
        if roll < self._params['question_prob'] + noise:
            question_type = 'technical' if self._has_trait('expert') else 'clarification'
            return BehaviorDecision(
                action=BehaviorAction.QUESTION,
                modifier=question_type,
            )

        # 4. Hesitation (if indecisive)
        if roll < self._params['hesitation_prob'] + noise:
            return BehaviorDecision(
                action=BehaviorAction.HESITATE,
            )

        # 5. Normal response
        return BehaviorDecision(action=BehaviorAction.RESPOND)

    def _check_triggers(self, message: str) -> Optional[BehaviorDecision]:
        """Check custom trigger rules."""
        for trigger in self.config.triggers:
            if re.search(trigger.keyword, message, re.IGNORECASE):
                # Apply probability
                if random.random() < trigger.probability:
                    return BehaviorDecision(
                        action=trigger.action,
                        modifier=trigger.response_hint,
                        triggered_by=trigger.keyword,
                    )
        return None

    def _check_focuses(self, message: str) -> bool:
        """Check if message contains focus topics."""
        all_focuses = []
        for trait in self.traits:
            all_focuses.extend(trait.focuses_on)

        return any(focus in message for focus in all_focuses)

    def _detect_objection_topic(self, message: str) -> str:
        """Detect the topic for objection."""
        topic_keywords = {
            'price': ['цен', 'стоим', 'рубл', 'бюджет', 'дорог', 'деньг'],
            'time': ['срок', 'времени', 'быстро', 'долго', 'когда', 'дней'],
            'guarantee': ['гаранти', 'точно', 'уверен', 'если не'],
            'technical': ['интеграц', 'api', 'crm', 'систем', 'техн'],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in message for kw in keywords):
                return topic

        return 'general'

    def _has_trait(self, trait_id: str) -> bool:
        """Check if behavior has specific trait."""
        return any(t.id == trait_id for t in self.traits)

    def get_response_style(self) -> ResponseStyle:
        """
        Get style parameters for response generation.

        Returns:
            ResponseStyle with instruction keys for prompt building
        """
        length = self._params['response_length']
        formality = self._params['formality']
        detail = self._params['detail_level']

        # Map to instruction keys
        length_key = (
            'very_short' if length < 0.7 else
            'short' if length < 0.9 else
            'long' if length > 1.3 else
            'normal'
        )

        formality_key = (
            'informal' if formality < 0.7 else
            'formal' if formality > 1.3 else
            'normal'
        )

        detail_key = (
            'minimal' if detail < 0.5 else
            'detailed' if detail > 1.3 else
            'normal'
        )

        return ResponseStyle(
            length_modifier=length,
            detail_modifier=detail,
            formality_modifier=formality,
            length_instruction_key=length_key,
            formality_instruction_key=formality_key,
            detail_instruction_key=detail_key,
        )

    def get_objection_context(self, topic: str, message: str) -> ObjectionContext:
        """
        Get context for generating an objection.

        Args:
            topic: Objection topic
            message: Message that triggered objection

        Returns:
            ObjectionContext with severity and details
        """
        # Severity based on skepticism and price sensitivity
        severity = self.config.skepticism

        if topic == 'price':
            severity = max(severity, self.config.price_sensitivity)

        return ObjectionContext(
            topic=topic,
            triggered_by=message[:50],
            severity=severity,
        )

    @property
    def current_phase(self) -> Optional[str]:
        """Get current phase name."""
        return self._phase_context.phase if self._phase_context else None

    @property
    def params(self) -> Dict[str, float]:
        """Get current behavioral parameters."""
        return self._params.copy()
