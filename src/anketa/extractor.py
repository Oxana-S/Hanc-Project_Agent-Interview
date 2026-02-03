"""
AnketaExtractor - extracts structured data from consultation dialogue using LLM.

Takes the full dialogue history, business analysis, and proposed solution,
then extracts clean structured data into FinalAnketa format.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from src.llm.deepseek import DeepSeekClient
from src.anketa.schema import FinalAnketa, AgentFunction, Integration

logger = structlog.get_logger()


class AnketaExtractor:
    """Extracts structured questionnaire data from consultation dialogue."""

    def __init__(self, llm: Optional[DeepSeekClient] = None):
        """
        Initialize extractor.

        Args:
            llm: DeepSeek client instance. Creates new one if not provided.
        """
        self.llm = llm or DeepSeekClient()

    async def extract(
        self,
        dialogue_history: List[Dict[str, str]],
        business_analysis: Optional[Dict[str, Any]] = None,
        proposed_solution: Optional[Dict[str, Any]] = None,
        duration_seconds: float = 0.0
    ) -> FinalAnketa:
        """
        Extract structured data from all sources into FinalAnketa.

        Args:
            dialogue_history: List of dialogue messages [{role, content}]
            business_analysis: Business analysis results (dict or model)
            proposed_solution: Proposed solution (dict or model)
            duration_seconds: Duration of consultation

        Returns:
            Populated FinalAnketa instance
        """
        # Convert models to dicts if needed
        if business_analysis and hasattr(business_analysis, 'model_dump'):
            business_analysis = business_analysis.model_dump()
        if proposed_solution and hasattr(proposed_solution, 'model_dump'):
            proposed_solution = proposed_solution.model_dump()

        prompt = self._build_extraction_prompt(
            dialogue_history,
            business_analysis or {},
            proposed_solution or {}
        )

        try:
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Low temperature for accuracy
                max_tokens=4096
            )

            # Parse JSON from response
            anketa_data = self._parse_json_response(response)

            # Build FinalAnketa from extracted data
            anketa = self._build_anketa(anketa_data, duration_seconds)

            logger.info(
                "Anketa extracted successfully",
                company=anketa.company_name,
                completion_rate=f"{anketa.completion_rate():.0f}%"
            )

            return anketa

        except Exception as e:
            logger.error("Anketa extraction failed", error=str(e))
            # Return minimal anketa with what we have
            return self._build_fallback_anketa(
                dialogue_history,
                business_analysis,
                proposed_solution,
                duration_seconds
            )

    def _build_extraction_prompt(
        self,
        dialogue: List[Dict[str, str]],
        analysis: Dict[str, Any],
        solution: Dict[str, Any]
    ) -> str:
        """Build the extraction prompt for LLM."""

        # Format dialogue
        dialogue_text = "\n".join([
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}"
            for msg in dialogue[-50:]  # Last 50 messages to fit context
        ])

        # Format analysis
        analysis_text = ""
        if analysis:
            analysis_text = f"""
АНАЛИЗ БИЗНЕСА:
- Компания: {analysis.get('company_name', 'N/A')}
- Отрасль: {analysis.get('industry', 'N/A')}
- Специализация: {analysis.get('specialization', 'N/A')}
- Болевые точки: {self._format_pain_points(analysis.get('pain_points', []))}
- Возможности: {self._format_opportunities(analysis.get('opportunities', []))}
- Ограничения: {analysis.get('constraints', [])}
"""

        # Format solution
        solution_text = ""
        if solution:
            main_func = solution.get('main_function', {})
            add_funcs = solution.get('additional_functions', [])
            solution_text = f"""
ПРЕДЛОЖЕННОЕ РЕШЕНИЕ:
- Основная функция: {main_func.get('name', 'N/A')} - {main_func.get('description', '')}
- Дополнительные функции: {[f.get('name', '') for f in add_funcs]}
"""

        return f"""Ты — эксперт по извлечению структурированных данных из консультаций.

ЗАДАЧА: Извлеки все данные из диалога консультации в структурированный JSON.

ВАЖНЫЕ ПРАВИЛА:
1. Извлекай КОНКРЕТНЫЕ значения, НЕ копируй фразы из диалога целиком
2. Для списков используй краткие, чёткие пункты
3. Если данные не упомянуты явно — оставь пустую строку или пустой список
4. Имена полей должны ТОЧНО соответствовать схеме ниже
5. Верни ТОЛЬКО валидный JSON без комментариев и пояснений

---

ДИАЛОГ КОНСУЛЬТАЦИИ:
{dialogue_text}

---
{analysis_text}
{solution_text}
---

СХЕМА JSON (заполни все поля):

{{
  "company_name": "название компании",
  "industry": "отрасль",
  "specialization": "специализация",
  "website": "URL сайта или null",
  "contact_name": "имя контактного лица",
  "contact_role": "должность",

  "business_description": "краткое описание бизнеса (1-2 предложения)",
  "services": ["услуга 1", "услуга 2"],
  "client_types": ["тип клиентов 1", "тип 2"],
  "current_problems": ["проблема 1", "проблема 2"],
  "business_goals": ["цель 1", "цель 2"],
  "constraints": ["ограничение 1", "ограничение 2"],

  "agent_name": "имя агента",
  "agent_purpose": "назначение агента (1-2 предложения)",
  "agent_functions": [
    {{"name": "название функции", "description": "описание", "priority": "high/medium/low"}}
  ],
  "typical_questions": ["вопрос 1", "вопрос 2"],

  "voice_gender": "female или male",
  "voice_tone": "professional, friendly, calm и т.д.",
  "language": "ru",
  "call_direction": "inbound, outbound или both",

  "integrations": [
    {{"name": "название системы", "purpose": "для чего", "required": true/false}}
  ],

  "main_function": {{"name": "...", "description": "...", "priority": "high"}},
  "additional_functions": [
    {{"name": "...", "description": "...", "priority": "medium"}}
  ]
}}

Верни ТОЛЬКО JSON:"""

    def _format_pain_points(self, pain_points: List) -> str:
        """Format pain points list."""
        if not pain_points:
            return "[]"
        results = []
        for p in pain_points:
            if isinstance(p, dict):
                results.append(p.get('description', str(p)))
            else:
                results.append(str(p))
        return str(results)

    def _format_opportunities(self, opportunities: List) -> str:
        """Format opportunities list."""
        if not opportunities:
            return "[]"
        results = []
        for o in opportunities:
            if isinstance(o, dict):
                results.append(o.get('description', str(o)))
            else:
                results.append(str(o))
        return str(results)

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        json_text = response.strip()

        # Remove markdown code blocks
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0]
        elif "```" in json_text:
            parts = json_text.split("```")
            if len(parts) >= 2:
                json_text = parts[1]

        # Find JSON object
        json_text = json_text.strip()
        start = json_text.find('{')
        end = json_text.rfind('}')
        if start != -1 and end != -1:
            json_text = json_text[start:end + 1]

        return json.loads(json_text)

    def _build_anketa(self, data: Dict[str, Any], duration_seconds: float) -> FinalAnketa:
        """Build FinalAnketa from extracted data."""

        # Parse agent functions
        agent_functions = []
        for func in data.get('agent_functions', []):
            if isinstance(func, dict):
                agent_functions.append(AgentFunction(
                    name=func.get('name', ''),
                    description=func.get('description', ''),
                    priority=func.get('priority', 'medium')
                ))

        # Parse integrations
        integrations = []
        for intg in data.get('integrations', []):
            if isinstance(intg, dict):
                integrations.append(Integration(
                    name=intg.get('name', ''),
                    purpose=intg.get('purpose', ''),
                    required=intg.get('required', True)
                ))

        # Parse main function
        main_func_data = data.get('main_function', {})
        main_function = None
        if main_func_data and isinstance(main_func_data, dict):
            main_function = AgentFunction(
                name=main_func_data.get('name', ''),
                description=main_func_data.get('description', ''),
                priority=main_func_data.get('priority', 'high')
            )

        # Parse additional functions
        additional_functions = []
        for func in data.get('additional_functions', []):
            if isinstance(func, dict):
                additional_functions.append(AgentFunction(
                    name=func.get('name', ''),
                    description=func.get('description', ''),
                    priority=func.get('priority', 'medium')
                ))

        return FinalAnketa(
            # Company
            company_name=data.get('company_name', ''),
            industry=data.get('industry', ''),
            specialization=data.get('specialization', ''),
            website=data.get('website'),
            contact_name=data.get('contact_name', ''),
            contact_role=data.get('contact_role', ''),

            # Business context
            business_description=data.get('business_description', ''),
            services=data.get('services', []),
            client_types=data.get('client_types', []),
            current_problems=data.get('current_problems', []),
            business_goals=data.get('business_goals', []),
            constraints=data.get('constraints', []),

            # Voice agent
            agent_name=data.get('agent_name', ''),
            agent_purpose=data.get('agent_purpose', ''),
            agent_functions=agent_functions,
            typical_questions=data.get('typical_questions', []),

            # Parameters
            voice_gender=data.get('voice_gender', 'female'),
            voice_tone=data.get('voice_tone', 'professional'),
            language=data.get('language', 'ru'),
            call_direction=data.get('call_direction', 'inbound'),

            # Integrations
            integrations=integrations,

            # Proposed solution
            main_function=main_function,
            additional_functions=additional_functions,

            # Metadata
            created_at=datetime.now(),
            consultation_duration_seconds=duration_seconds
        )

    def _build_fallback_anketa(
        self,
        dialogue: List[Dict[str, str]],
        analysis: Optional[Dict[str, Any]],
        solution: Optional[Dict[str, Any]],
        duration_seconds: float
    ) -> FinalAnketa:
        """Build minimal anketa from available data when LLM extraction fails."""

        company_name = ""
        industry = ""

        if analysis:
            company_name = analysis.get('company_name', '')
            industry = analysis.get('industry', '')

        main_function = None
        additional_functions = []

        if solution:
            main_func_data = solution.get('main_function', {})
            if main_func_data:
                main_function = AgentFunction(
                    name=main_func_data.get('name', ''),
                    description=main_func_data.get('description', ''),
                    priority='high'
                )

            for func in solution.get('additional_functions', []):
                if isinstance(func, dict):
                    additional_functions.append(AgentFunction(
                        name=func.get('name', ''),
                        description=func.get('description', ''),
                        priority='medium'
                    ))

        return FinalAnketa(
            company_name=company_name,
            industry=industry,
            main_function=main_function,
            additional_functions=additional_functions,
            created_at=datetime.now(),
            consultation_duration_seconds=duration_seconds
        )
