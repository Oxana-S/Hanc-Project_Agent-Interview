"""
Simulated Client for testing ConsultantInterviewer.

Plays the role of a client based on a scenario configuration.
Uses LLM to generate realistic responses.
"""

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from src.llm.deepseek import DeepSeekClient


@dataclass
class ClientPersona:
    """Client persona configuration."""
    name: str
    role: str  # e.g., "CEO", "Marketing Director", "Franchise Owner"
    company: str
    industry: str
    website: Optional[str] = None

    # Personality traits
    communication_style: str = "professional"  # professional, casual, brief, detailed
    knowledge_level: str = "medium"  # low, medium, high

    # Business context
    pain_points: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)

    # Agent requirements
    target_functions: List[str] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)

    # Additional context
    background: str = ""
    special_instructions: str = ""


class SimulatedClient:
    """
    AI-powered client simulator.

    Generates realistic responses based on persona and conversation context.
    Can be configured via YAML scenario files.
    """

    def __init__(
        self,
        persona: ClientPersona,
        llm_client: Optional[DeepSeekClient] = None,
    ):
        """
        Initialize simulated client.

        Args:
            persona: Client persona configuration
            llm_client: LLM client for generating responses
        """
        self.persona = persona
        self.llm = llm_client or DeepSeekClient()
        self.conversation_history: List[Dict[str, str]] = []
        self.response_count = 0

    @classmethod
    def from_yaml(cls, scenario_path: str, llm_client: Optional[DeepSeekClient] = None) -> "SimulatedClient":
        """
        Load client from YAML scenario file.

        Args:
            scenario_path: Path to scenario YAML file
            llm_client: Optional LLM client

        Returns:
            Configured SimulatedClient instance
        """
        path = Path(scenario_path)
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_path}")

        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        persona_data = config.get('persona', {})
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
            target_functions=persona_data.get('target_functions', []),
            integrations=persona_data.get('integrations', []),
            background=persona_data.get('background', ''),
            special_instructions=persona_data.get('special_instructions', ''),
        )

        return cls(persona=persona, llm_client=llm_client)

    def _build_system_prompt(self) -> str:
        """Build system prompt for the simulated client."""
        p = self.persona

        return f"""Ты играешь роль клиента в тестовой симуляции.

ТВОЯ ПЕРСОНА:
- Имя: {p.name}
- Должность: {p.role}
- Компания: {p.company}
- Отрасль: {p.industry}
{f'- Сайт: {p.website}' if p.website else ''}

СТИЛЬ ОБЩЕНИЯ: {p.communication_style}
- professional: деловой, вежливый, по делу
- casual: дружелюбный, неформальный
- brief: короткие ответы, только суть
- detailed: развёрнутые ответы с подробностями

УРОВЕНЬ ЗНАНИЙ О ТЕХНОЛОГИЯХ: {p.knowledge_level}
- low: не разбираешься в AI/IT, нужны простые объяснения
- medium: общее понимание, можешь обсуждать бизнес-задачи
- high: хорошо понимаешь технологии, можешь обсуждать детали

КОНТЕКСТ БИЗНЕСА:
Болевые точки:
{chr(10).join(f'- {pain}' for pain in p.pain_points) if p.pain_points else '- Не указаны'}

Цели:
{chr(10).join(f'- {goal}' for goal in p.goals) if p.goals else '- Не указаны'}

Ограничения:
{chr(10).join(f'- {c}' for c in p.constraints) if p.constraints else '- Нет серьёзных ограничений'}

ЧТО ХОЧЕШЬ ОТ ГОЛОСОВОГО АГЕНТА:
Функции:
{chr(10).join(f'- {func}' for func in p.target_functions) if p.target_functions else '- Открыт к предложениям'}

Интеграции:
{chr(10).join(f'- {intg}' for intg in p.integrations) if p.integrations else '- Пока не определился'}

ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:
{p.background}

{f'ОСОБЫЕ ИНСТРУКЦИИ: {p.special_instructions}' if p.special_instructions else ''}

ПРАВИЛА ПОВЕДЕНИЯ:
1. Отвечай естественно, как реальный клиент
2. Не раскрывай сразу всю информацию — отвечай на вопросы консультанта
3. Можешь задавать встречные вопросы, если что-то непонятно
4. При подтверждении анализа — если всё верно, говори "да"
5. При выборе решения — соглашайся если предложение разумное
6. В фазе анкеты — давай конкретные ответы на вопросы

ВАЖНО: Ты тестовый клиент. Твоя задача — помочь проверить работу консультанта.
Отвечай в пределах 1-3 предложений, если не нужен развёрнутый ответ."""

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

        # Add consultant message to history
        # From client's perspective: consultant speaks TO us = "user" role
        self.conversation_history.append({
            "role": "user",
            "content": consultant_message
        })

        # Build messages for LLM
        system_prompt = self._build_system_prompt()

        # Add phase-specific instructions
        phase_hint = self._get_phase_hint(phase)
        if phase_hint:
            system_prompt += f"\n\nТЕКУЩАЯ ФАЗА: {phase}\n{phase_hint}"

        messages = [
            {"role": "system", "content": system_prompt},
            *self.conversation_history
        ]

        # Generate response
        response = await self.llm.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        # Add our response to history
        # We (client) respond = "assistant" role
        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        return response

    def _get_phase_hint(self, phase: str) -> str:
        """Get phase-specific hints for the client."""
        hints = {
            "discovery": """В этой фазе консультант знакомится с твоим бизнесом.
Расскажи о компании, проблемах, целях. Отвечай на вопросы.""",

            "analysis": """Консультант показывает анализ твоего бизнеса.
Если анализ верный — подтверди. Если что-то неточно — скажи что исправить.""",

            "proposal": """Консультант предлагает решение.
Оцени предложение. Если нравится — соглашайся. Если есть вопросы — задавай.""",

            "refinement": """Консультант заполняет анкету, задаёт уточняющие вопросы.
Отвечай конкретно на каждый вопрос.""",
        }
        return hints.get(phase, "")

    def confirm(self, default: str = "да") -> str:
        """
        Generate a confirmation response.

        Used when the system expects yes/no/clarify responses.
        """
        return default

    def reset(self):
        """Reset conversation history."""
        self.conversation_history = []
        self.response_count = 0
