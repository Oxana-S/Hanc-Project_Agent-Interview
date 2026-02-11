"""
Simulated Client for testing ConsultantInterviewer.

v2.0 - With BehaviorEngine integration for realistic behavior.
Plays the role of a client based on a scenario configuration.
Uses LLM to generate realistic responses.
"""

import random
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from src.llm.factory import create_llm_client

from .personas import (
    BehaviorConfig,
    BehaviorEngine,
    BehaviorAction,
    TriggerRule,
)


@dataclass
class ClientPersona:
    """Client persona configuration."""
    name: str
    role: str
    company: str
    industry: str
    website: Optional[str] = None

    # Personality traits (legacy - for backward compatibility)
    communication_style: str = "professional"
    knowledge_level: str = "medium"

    # Business context
    pain_points: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)

    # Agent requirements
    target_functions: List[str] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)

    # Additional context
    background: str = ""
    current_situation: str = ""
    special_instructions: str = ""

    # Objections by topic (for behavior engine)
    objections: Dict[str, List[str]] = field(default_factory=dict)


class PromptBuilder:
    """
    Builds prompts from YAML templates.

    Loads templates from config/personas/prompts.yaml
    """

    _instance: Optional["PromptBuilder"] = None
    _templates: Dict[str, Any] = {}
    _loaded: bool = False

    def __new__(cls) -> "PromptBuilder":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self._load_templates()
            PromptBuilder._loaded = True

    def _load_templates(self) -> None:
        """Load prompt templates from YAML."""
        config_path = Path("config/personas/prompts.yaml")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                PromptBuilder._templates = yaml.safe_load(f) or {}

    def build_persona_section(self, persona: ClientPersona) -> str:
        """Build persona section of prompt."""
        pain_points_text = "\n".join(f"- {p}" for p in persona.pain_points) if persona.pain_points else "- Не указаны"

        situation = persona.current_situation or persona.background or "Не указана"

        template = self._templates.get('persona_template', '')
        if template:
            return template.format(
                name=persona.name,
                role=persona.role,
                company=persona.company,
                industry=persona.industry,
                situation=situation,
                pain_points=pain_points_text,
            )

        # Fallback
        return f"""РОЛЬ: {persona.name}, {persona.role}
КОМПАНИЯ: {persona.company} ({persona.industry})
СИТУАЦИЯ: {situation}
ПРОБЛЕМЫ:
{pain_points_text}"""

    def build_style_section(self, style_keys: Dict[str, str]) -> str:
        """Build style instructions from keys."""
        instructions = self._templates.get('style_instructions', {})
        parts = []

        for category, key in style_keys.items():
            category_instructions = instructions.get(category, {})
            instruction = category_instructions.get(key, '')
            if instruction:
                parts.append(instruction)

        return "\n".join(parts) if parts else ""

    def get_phase_context(self, phase: str) -> str:
        """Get phase-specific context."""
        contexts = self._templates.get('phase_context', {})
        return contexts.get(phase, '')

    def get_action_instruction(self, action: BehaviorAction, modifier: Optional[str] = None) -> str:
        """Get instruction for specific action."""
        instructions = self._templates.get('action_instructions', {})

        if action == BehaviorAction.RESPOND:
            return instructions.get('respond', '')

        action_key = action.value
        action_instructions = instructions.get(action_key, {})

        if isinstance(action_instructions, dict) and modifier:
            return action_instructions.get(modifier, action_instructions.get('general', ''))
        elif isinstance(action_instructions, str):
            return action_instructions

        return ''

    def get_base_rules(self) -> str:
        """Get base rules."""
        return self._templates.get('base_rules', '')

    def get_objection_template(self, topic: str, severity: float) -> Optional[str]:
        """Get objection template by topic and severity."""
        templates = self._templates.get('objection_templates', {})
        topic_templates = templates.get(topic, templates.get('general', {}))

        if severity > 0.6:
            options = topic_templates.get('strong', [])
        else:
            options = topic_templates.get('mild', [])

        if options:
            return random.choice(options)
        return None


class SimulatedClient:
    """
    AI-powered client simulator v2.

    Generates realistic responses based on persona, behavior config,
    and conversation context.
    """

    def __init__(
        self,
        persona: ClientPersona,
        llm_client=None,
        behavior_config: Optional[BehaviorConfig] = None,
    ):
        """
        Initialize simulated client.

        Args:
            persona: Client persona configuration
            llm_client: LLM client for generating responses
            behavior_config: Behavior configuration (optional)
        """
        self.persona = persona
        self.llm = llm_client or create_llm_client()
        self.conversation_history: List[Dict[str, str]] = []
        self.response_count = 0

        # Initialize behavior engine
        self.behavior_config = behavior_config or BehaviorConfig()
        self.behavior = BehaviorEngine(self.behavior_config)

        # Prompt builder
        self.prompt_builder = PromptBuilder()

        # Current phase
        self._current_phase = "discovery"

    @classmethod
    def from_yaml(cls, scenario_path: str, llm_client=None) -> "SimulatedClient":
        """
        Load client from YAML scenario file.

        Supports both v1 (legacy) and v2 (with behavior) formats.
        """
        path = Path(scenario_path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_path}")

        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        persona_data = config.get('persona', {})

        # Build persona
        persona = ClientPersona(
            name=persona_data.get('name', 'Test Client'),
            role=persona_data.get('role', 'Business Owner'),
            company=persona_data.get('company', 'Test Company'),
            industry=persona_data.get('industry', 'General'),
            website=persona_data.get('website'),
            communication_style=persona_data.get('communication_style', 'professional'),
            knowledge_level=persona_data.get('knowledge_level', 'medium'),
            pain_points=persona_data.get('pain_points', []),
            goals=persona_data.get('goals', []),
            constraints=persona_data.get('constraints', []),
            services=persona_data.get('services', []),
            target_functions=persona_data.get('target_functions', []),
            integrations=persona_data.get('integrations', []),
            background=persona_data.get('background', ''),
            current_situation=persona_data.get('current_situation', ''),
            special_instructions=persona_data.get('special_instructions', ''),
        )

        # Load objections if present
        objections_data = config.get('objections', {})
        if objections_data:
            persona.objections = objections_data

        # Build behavior config (v2 format)
        behavior_config = None
        behavior_data = persona_data.get('behavior', {})

        if behavior_data:
            # Parse triggers
            triggers = []
            for trigger_data in behavior_data.get('triggers', []):
                triggers.append(TriggerRule(
                    keyword=trigger_data.get('keyword', ''),
                    action=BehaviorAction(trigger_data.get('action', 'respond')),
                    probability=trigger_data.get('probability', 0.5),
                    response_hint=trigger_data.get('response_hint'),
                ))

            behavior_config = BehaviorConfig(
                patience=behavior_data.get('patience', 0.5),
                skepticism=behavior_data.get('skepticism', 0.3),
                technical_level=behavior_data.get('technical_level', 0.5),
                decisiveness=behavior_data.get('decisiveness', 0.5),
                price_sensitivity=behavior_data.get('price_sensitivity', 0.3),
                traits=behavior_data.get('traits', []),
                triggers=triggers,
                phase_modifiers=behavior_data.get('phase_modifiers', {}),
                randomness=behavior_data.get('randomness', 0.3),
                seed=behavior_data.get('seed'),
            )
        else:
            # Legacy format - map communication_style to traits
            traits = cls._map_legacy_style_to_traits(
                persona_data.get('communication_style', 'professional'),
                persona_data.get('knowledge_level', 'medium'),
            )
            behavior_config = BehaviorConfig(traits=traits)

        return cls(persona=persona, llm_client=llm_client, behavior_config=behavior_config)

    @staticmethod
    def _map_legacy_style_to_traits(communication_style: str, knowledge_level: str) -> List[str]:
        """Map legacy style/level to trait IDs."""
        traits = []

        style_mapping = {
            'professional': ['formal'],
            'casual': ['casual'],
            'brief': ['brief'],
            'detailed': ['verbose'],
        }
        traits.extend(style_mapping.get(communication_style, []))

        level_mapping = {
            'low': ['novice'],
            'medium': [],
            'high': ['expert'],
        }
        traits.extend(level_mapping.get(knowledge_level, []))

        return traits

    def set_phase(self, phase: str) -> None:
        """Set current consultation phase."""
        self._current_phase = phase
        self.behavior.set_phase(phase, self.response_count)

    async def respond(self, consultant_message: str, phase: str = "discovery") -> str:
        """
        Generate response to consultant's message.

        Args:
            consultant_message: Message from the consultant
            phase: Current consultation phase

        Returns:
            Client's response
        """
        self.response_count += 1

        # Update phase if changed
        if phase != self._current_phase:
            self.set_phase(phase)

        # Add consultant message to history
        self.conversation_history.append({
            "role": "user",
            "content": consultant_message
        })

        # Get behavior decision
        decision = self.behavior.decide(consultant_message)

        # Build prompt
        system_prompt = self._build_system_prompt(phase, decision)

        messages = [
            {"role": "system", "content": system_prompt},
            *self.conversation_history
        ]

        # Generate response
        response = await self.llm.chat(
            messages=messages,
            temperature=0.7 + self.behavior_config.randomness * 0.2,
            max_tokens=2048
        )

        # Add response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        return response

    def _build_system_prompt(self, phase: str, decision) -> str:
        """Build system prompt using templates and behavior decision."""
        parts = []

        # Persona section
        parts.append(self.prompt_builder.build_persona_section(self.persona))

        # Style section based on behavior
        style = self.behavior.get_response_style()
        style_keys = {
            'length': style.length_instruction_key,
            'formality': style.formality_instruction_key,
            'detail': style.detail_instruction_key,
        }
        style_text = self.prompt_builder.build_style_section(style_keys)
        if style_text:
            parts.append(style_text)

        # Phase context
        phase_context = self.prompt_builder.get_phase_context(phase)
        if phase_context:
            parts.append(phase_context)

        # Action instruction
        action_instruction = self.prompt_builder.get_action_instruction(
            decision.action,
            decision.modifier
        )
        if action_instruction:
            parts.append(f"ДЕЙСТВИЕ: {action_instruction}")

        # If objection with hint from trigger
        if decision.action == BehaviorAction.OBJECT and decision.modifier:
            topic = decision.modifier
            objections = self.persona.objections.get(topic, [])
            if objections:
                hint = random.choice(objections)
                parts.append(f"Пример: {hint}")

        # Base rules
        parts.append(self.prompt_builder.get_base_rules())

        return "\n\n".join(filter(None, parts))

    def confirm(self, default: str = "да") -> str:
        """Generate a confirmation response."""
        return default

    def reset(self):
        """Reset conversation history."""
        self.conversation_history = []
        self.response_count = 0
        self._current_phase = "discovery"
