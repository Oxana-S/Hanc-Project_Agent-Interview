"""
AnketaExtractor - extracts structured data from consultation dialogue using LLM.

Takes the full dialogue history, business analysis, and proposed solution,
then extracts clean structured data into FinalAnketa format.

v3.1 Improvements:
- JSONRepair for robust JSON parsing with multiple repair strategies
- DialogueCleaner for removing dialogue markers from field values
- SmartExtractor for role-based data extraction from dialogue
- AnketaPostProcessor for comprehensive post-processing pipeline
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from src.llm.factory import create_llm_client
from src.anketa.schema import (
    FinalAnketa, AgentFunction, Integration,
    # v2.0 models
    FAQItem, ObjectionHandler, DialogueExample, FinancialMetric,
    Competitor, MarketInsight, EscalationRule, KPIMetric,
    ChecklistItem, AIRecommendation, TargetAudienceSegment,
    # v5.0 interview models
    InterviewAnketa, QAPair
)
from src.anketa.data_cleaner import (
    JSONRepair, DialogueCleaner, SmartExtractor, AnketaPostProcessor
)
from src.config.prompt_loader import get_prompt, render_prompt

logger = structlog.get_logger("anketa")


class AnketaExtractor:
    """Extracts structured questionnaire data from consultation dialogue."""

    def __init__(
        self,
        llm=None,
        strict_cleaning: bool = True,
        use_smart_extraction: bool = True,
        max_json_retries: int = 3
    ):
        """
        Initialize extractor with v3.1 improvements.

        Args:
            llm: DeepSeek client instance. Creates new one if not provided.
            strict_cleaning: If True, aggressively remove dialogue contamination
            use_smart_extraction: If True, use SmartExtractor for dialogue parsing
            max_json_retries: Number of JSON repair attempts
        """
        # FAILSAFE: НИКОГДА не использовать deepseek-reasoner для extraction!
        # deepseek-reasoner слишком медленный (180-220 sec) для real-time extraction
        # Всегда использовать fast models: deepseek-chat (2-5 sec) или azure (3-4 sec)
        if llm is None:
            llm = create_llm_client()  # ← DEFAULT: uses LLM_PROVIDER from .env

        # Проверить что это не deepseek-reasoner
        if hasattr(llm, 'model') and 'reasoner' in llm.model.lower():
            logger.warning(
                "CRITICAL: deepseek-reasoner detected! Forcing deepseek-chat",
                original_model=llm.model
            )
            # Force override to deepseek-chat (fast model)
            from src.llm.deepseek import DeepSeekClient
            llm = DeepSeekClient(model="deepseek-chat")

        self.llm = llm
        self.strict_cleaning = strict_cleaning
        self.use_smart_extraction = use_smart_extraction
        self.max_json_retries = max_json_retries

        # Initialize v3.1 components
        self.cleaner = DialogueCleaner(strict_mode=strict_cleaning)
        self.smart_extractor = SmartExtractor() if use_smart_extraction else None
        self.post_processor = AnketaPostProcessor(
            strict_cleaning=strict_cleaning,
            normalize_values=True,
            inject_defaults=True
        )

    async def extract(
        self,
        dialogue_history: List[Dict[str, str]],
        business_analysis: Optional[Dict[str, Any]] = None,
        proposed_solution: Optional[Dict[str, Any]] = None,
        duration_seconds: float = 0.0,
        document_context: Optional[Any] = None,
        consultation_type: str = "consultation",
    ) -> Any:
        """
        Extract structured data from all sources into FinalAnketa.

        Args:
            dialogue_history: List of dialogue messages [{role, content}]
            business_analysis: Business analysis results (dict or model)
            proposed_solution: Proposed solution (dict or model)
            duration_seconds: Duration of consultation
            document_context: DocumentContext from analyzed client documents (v3.2)

        Returns:
            Populated FinalAnketa instance
        """
        # Convert models to dicts if needed
        if business_analysis and hasattr(business_analysis, 'model_dump'):
            business_analysis = business_analysis.model_dump()
        if proposed_solution and hasattr(proposed_solution, 'model_dump'):
            proposed_solution = proposed_solution.model_dump()

        # v5.0: Route to interview extraction if interview mode
        if consultation_type == "interview":
            return await self._extract_interview(dialogue_history, duration_seconds)

        prompt = self._build_extraction_prompt(
            dialogue_history,
            business_analysis or {},
            proposed_solution or {},
            document_context
        )

        # Load system prompt from YAML
        system_prompt = get_prompt("anketa/extract", "system_prompt")

        try:
            logger.info("Starting anketa extraction v3.1", dialogue_turns=len(dialogue_history))

            # Step 1: Smart extraction from dialogue (if enabled)
            dialogue_extracted = {}
            if self.smart_extractor and dialogue_history:
                dialogue_extracted = self.smart_extractor.extract_from_dialogue(dialogue_history)
                logger.debug("Smart extraction completed", fields=list(dialogue_extracted.keys()))

            # Для deepseek-reasoner нужно больше токенов:
            # ~4000 на reasoning + ~2000 на JSON ответ
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=8192
            )

            logger.debug("LLM response received", response_length=len(response))

            # Step 2: Parse JSON with robust repair
            anketa_data, was_repaired = self._parse_json_with_repair(response)
            if was_repaired:
                logger.info("JSON was repaired during parsing")

            # Step 3: Merge with smart-extracted data
            if dialogue_extracted:
                anketa_data = self.smart_extractor.merge_with_llm_data(
                    dialogue_extracted, anketa_data
                )

            # Step 3.5: SPRINT 2 - Contextual post-processing for "да/нет" answers
            anketa_data = self._post_process_contextual_lists(anketa_data, dialogue_history)

            # Step 4: Post-process to clean dialogue contamination
            anketa_data, processing_report = self.post_processor.process(anketa_data)
            if processing_report['cleaning_changes']:
                logger.info(
                    "Dialogue contamination cleaned",
                    changes=len(processing_report['cleaning_changes'])
                )

            # Step 4.5: SPRINT 2 - Fallback regex extraction for phone/email
            if not anketa_data.get('contact_phone') or not anketa_data.get('contact_email'):
                fallback_contacts = self._fallback_contact_extraction(dialogue_history)
                if fallback_contacts.get('contact_phone') and not anketa_data.get('contact_phone'):
                    anketa_data['contact_phone'] = fallback_contacts['contact_phone']
                if fallback_contacts.get('contact_email') and not anketa_data.get('contact_email'):
                    anketa_data['contact_email'] = fallback_contacts['contact_email']

            # Build FinalAnketa from cleaned data
            anketa = self._build_anketa(anketa_data, duration_seconds)

            # Generate AI expert content for v2.0 blocks
            anketa = await self._generate_expert_content(anketa)

            # SPRINT 5: Enhanced logging with field counts
            # Count filled fields (non-empty values)
            filled_count = sum(1 for field_name in [
                'company_name', 'industry', 'specialization', 'contact_name', 'contact_role',
                'contact_phone', 'contact_email', 'business_description', 'agent_name', 'agent_purpose'
            ] if getattr(anketa, field_name, None))

            # Count filled lists
            filled_count += sum(1 for field_name in [
                'services', 'client_types', 'current_problems', 'business_goals',
                'agent_functions', 'integrations'
            ] if getattr(anketa, field_name, None) and len(getattr(anketa, field_name, [])) > 0)

            logger.info(
                "Anketa extracted successfully",
                company=anketa.company_name,
                completion_rate=f"{anketa.completion_rate():.0%}",
                fields_filled=filled_count,
                total_fields=16,  # 10 strings + 6 lists
                dialogue_turns=len(dialogue_history),
                extraction_method='smart' if dialogue_extracted else 'llm_only',
                has_phone=bool(anketa.contact_phone),
                has_email=bool(anketa.contact_email)
            )

            return anketa

        except json.JSONDecodeError as e:
            logger.error("JSON parsing failed after repair attempts", error=str(e), response_preview=response[:500] if response else "empty")
            anketa = self._build_fallback_anketa(
                dialogue_history,
                business_analysis,
                proposed_solution,
                duration_seconds
            )
            # Still try to generate expert content for fallback anketa
            anketa = await self._generate_expert_content(anketa)
            return anketa
        except Exception as e:
            import traceback
            logger.error(
                "Anketa extraction failed",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc()
            )
            # Return minimal anketa with what we have
            anketa = self._build_fallback_anketa(
                dialogue_history,
                business_analysis,
                proposed_solution,
                duration_seconds
            )
            # Still try to generate expert content for fallback anketa
            anketa = await self._generate_expert_content(anketa)
            return anketa

    def _build_extraction_prompt(
        self,
        dialogue: List[Dict[str, str]],
        analysis: Dict[str, Any],
        solution: Dict[str, Any],
        document_context: Optional[Any] = None
    ) -> str:
        """Build the extraction prompt for LLM."""

        # Format dialogue
        dialogue_text = "\n".join([
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}"
            for msg in dialogue[-100:]  # Last 100 messages to fit context
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

        # Format document context (v3.2)
        document_text = ""
        if document_context:
            try:
                if hasattr(document_context, 'to_prompt_context'):
                    document_text = f"""
ДОКУМЕНТЫ КЛИЕНТА:
{document_context.to_prompt_context()}
"""
                    # v4.3: Debug logging to verify document context is used
                    logger.info(
                        "document_context_added_to_extraction_prompt",
                        has_to_prompt_context=True,
                        key_facts_count=len(document_context.key_facts) if hasattr(document_context, 'key_facts') else 0,
                        has_summary=bool(getattr(document_context, 'summary', None)),
                    )
                elif hasattr(document_context, 'summary') and document_context.summary:
                    document_text = f"""
ДОКУМЕНТЫ КЛИЕНТА:
{document_context.summary}
"""
                    logger.info(
                        "document_context_added_to_extraction_prompt",
                        has_to_prompt_context=False,
                        has_summary=True,
                        summary_length=len(document_context.summary),
                    )
            except Exception as e:
                logger.warning("failed_to_add_document_context_to_prompt", error=str(e))
                pass  # Ignore document context errors

        return f"""Ты — эксперт по извлечению структурированных данных из консультаций.

ЗАДАЧА: Извлеки все данные из диалога консультации в структурированный JSON.

ВАЖНЫЕ ПРАВИЛА:
1. Извлекай КОНКРЕТНЫЕ значения, НЕ копируй фразы из диалога целиком
2. Для списков используй краткие, чёткие пункты
3. Если данные не упомянуты явно — оставь пустую строку или пустой список
4. Имена полей должны ТОЧНО соответствовать схеме ниже
5. Верни ТОЛЬКО валидный JSON без комментариев и пояснений
6. КРИТИЧНО: company_name — это БРЕНД/НАЗВАНИЕ компании (например: "АльфаСервис", "ГрузовикОнлайн"), а НЕ описание деятельности!
7. business_description — это ЧЕМ занимается компания (например: "логистика и грузоперевозки"), а НЕ название!
8. КРИТИЧНО: agent_name — извлеки ТОЧНОЕ имя, которое КЛИЕНТ назвал для агента (например: "Мальвина", "Анна"). Ищи фразы типа "назовём...", "пусть будет...", "имя агента...". НЕ подставляй "Hanc.AI" или название компании!
9. КРИТИЧНО: voice_tone — извлеки тон голоса ТОЧНО как описал КЛИЕНТ (например: "дружелюбный", "тёплый", "участливый"). Ищи фразы типа "тон...", "голос должен быть...", "дружелюбный". НЕ ставь "professional" по умолчанию!
10. client_types — опиши типы клиентов КОНКРЕТНО (например: "владельцы кошек и собак", "малый бизнес"), НЕ обобщай до одного слова

---

ДИАЛОГ КОНСУЛЬТАЦИИ:
{dialogue_text}

---
{analysis_text}
{solution_text}
{document_text}
---

СХЕМА JSON (заполни все поля):

{{
  "company_name": "ТОЧНОЕ название/бренд компании (НЕ описание деятельности!)",
  "industry": "отрасль",
  "specialization": "специализация",
  "website": "URL сайта или null",
  "contact_name": "имя контактного лица",
  "contact_role": "должность",
  "contact_phone": "телефон контактного лица (в формате +XXX...)",
  "contact_email": "email контактного лица",

  "business_description": "чем занимается компания (1-2 предложения, НЕ название!)",
  "business_type": "тип бизнеса: B2B, B2C, B2B2C или другое",
  "services": ["услуга 1", "услуга 2"],
  "client_types": ["конкретный тип клиентов 1 (НЕ обобщай до одного слова!)", "тип 2"],
  "current_problems": ["проблема 1", "проблема 2"],
  "business_goals": ["цель 1", "цель 2"],
  "constraints": ["ограничение 1", "ограничение 2"],
  "compliance_requirements": ["регуляторное требование 1", "требование 2"],

  "agent_name": "ТОЧНОЕ имя агента, которое КЛИЕНТ назвал в диалоге (НЕ Hanc.AI!)",
  "agent_purpose": "конкретное назначение агента для ЭТОГО бизнеса (1-2 предложения)",
  "agent_functions": [
    {{"name": "название функции", "description": "описание", "priority": "high/medium/low"}}
  ],
  "typical_questions": ["вопрос 1", "вопрос 2"],

  "voice_gender": "female или male",
  "voice_tone": "тон голоса ТОЧНО как описал КЛИЕНТ (например: дружелюбный, тёплый, участливый)",
  "language": "ru",
  "call_direction": "inbound, outbound или both",
  "working_hours": {{"пн-пт": "9:00-18:00", "сб": "10:00-15:00"}},
  "transfer_conditions": ["условие перевода на оператора 1", "условие 2"],

  "integrations": [
    {{"name": "название системы", "purpose": "для чего", "required": true/false}}
  ],

  "call_volume": "объём звонков в день или месяц",
  "budget": "бюджет проекта с валютой",
  "timeline": "желаемые сроки внедрения",
  "additional_notes": "дополнительные замечания или пожелания клиента",

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

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON content from markdown code blocks."""
        if "```json" in text:
            return text.split("```json")[1].split("```")[0]
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                return parts[1]
        return text

    def _fix_common_json_errors(self, text: str) -> str:
        """Fix common JSON syntax errors."""
        import re
        # Fix trailing commas before ] or }
        fixed = re.sub(r',\s*([}\]])', r'\1', text)
        return fixed

    def _find_balanced_json(self, text: str) -> str:
        """Find the first balanced JSON object in text (string-aware).

        R16-04: Track start position of first '{' to exclude any preamble text.
        """
        brace_count = 0
        start_pos = -1
        in_string = False
        escape_next = False
        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if in_string:
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == '{':
                if brace_count == 0:
                    start_pos = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_pos >= 0:
                    return text[start_pos:i + 1]
        return text

    def _parse_json_with_repair(self, response: str) -> Tuple[Dict[str, Any], bool]:
        """
        Parse JSON with v3.1 robust repair mechanism.

        Uses JSONRepair class for multiple repair strategies.

        Returns:
            Tuple of (parsed_data, was_repaired)
        """
        return JSONRepair.parse(response, max_retries=self.max_json_retries)

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response with robust error handling (legacy method)."""
        json_text = self._extract_json_from_markdown(response.strip())

        # Find JSON object boundaries
        start = json_text.find('{')
        end = json_text.rfind('}')
        if start != -1 and end != -1:
            json_text = json_text[start:end + 1]

        # Try direct parse
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # Try with fixes
        fixed_json = self._fix_common_json_errors(json_text)
        try:
            return json.loads(fixed_json)
        except json.JSONDecodeError:
            pass

        # Try partial extraction
        partial = self._find_balanced_json(json_text)
        partial = self._fix_common_json_errors(partial)
        try:
            return json.loads(partial)
        except json.JSONDecodeError:
            pass

        # Last resort: raise original error
        return json.loads(json_text)

    def _fallback_contact_extraction(self, dialogue: List[Dict[str, str]]) -> Dict[str, str]:
        """
        Fallback: search entire dialogue for phone/email using regex.

        SPRINT 2: If LLM failed to extract phone/email, try regex on full text.
        """
        full_text = ' '.join([
            msg.get('content', '')
            for msg in dialogue
            if msg.get('role', '').lower() in ('user', 'client', 'клиент')
        ])

        result = {}

        import re

        # Phone patterns (речевой ввод)
        phone_patterns = [
            r'(\+\d{1,3}\s?\d{3}\s?\d{3}\s?\d{2,4}\s?\d{2,4})',  # +43 664 755 03580
            r'плюс\s+(\d{2,3})\s+(\d{3})\s+(\d{3})\s+(\d{2,4})\s+(\d{2,4})',  # "плюс сорок три..."
            r'(?:телефон|номер|позвонить)\s*[:—]?\s*([+\d\s\-()]{10,20})',
        ]

        for pattern in phone_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                if match.lastindex and match.lastindex > 1:
                    # Reconstruct from groups: "плюс 43 664..." → +43664...
                    groups = [g for g in match.groups() if g]
                    phone = '+' + ''.join(groups).replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                    # Validate length
                    if 10 <= len(phone) <= 20:
                        result['contact_phone'] = phone
                        logger.debug("Fallback phone extraction", phone=phone)
                        break
                else:
                    phone = match.group(1).strip()
                    # Clean and validate
                    digits = re.sub(r'\D', '', phone)
                    if 7 <= len(digits) <= 15:
                        result['contact_phone'] = phone
                        logger.debug("Fallback phone extraction", phone=phone)
                        break

        # Email patterns (речевой ввод)
        email_patterns = [
            r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)',  # standard email
            r'([a-zA-Z0-9_.+-]+)\s+(?:эт|at)\s+([a-zA-Z0-9-]+)\s+(?:точка|dot)\s+([a-zA-Z0-9-]+)',  # "channel эт gmail точка com"
            r'(?:email|емейл|мейл|почта)\s*[:—]?\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)',
        ]

        for pattern in email_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                if match.lastindex and match.lastindex >= 3:
                    # Reconstruct: "channel эт gmail точка com" → channel@gmail.com
                    groups = [g for g in match.groups() if g]
                    if len(groups) >= 3:
                        email = f"{groups[0]}@{groups[1]}.{groups[2]}"
                        # Validate
                        if '@' in email and '.' in email.split('@')[-1]:
                            result['contact_email'] = email
                            logger.debug("Fallback email extraction", email=email)
                            break
                else:
                    email = match.group(1).strip()
                    # Validate
                    if '@' in email and '.' in email.split('@')[-1] and len(email) < 100:
                        result['contact_email'] = email
                        logger.debug("Fallback email extraction", email=email)
                        break

        return result

    def _post_process_contextual_lists(
        self,
        data: Dict[str, Any],
        dialogue: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Post-process list fields to handle contextual "да/нет" answers.

        SPRINT 2: If agent mentions options and user says "да все" / "да, интересно",
        fill all mentioned options.
        """
        # Define affirmative patterns
        affirmative_patterns = [
            r'да\s+все',
            r'все\s+интересн',
            r'все\s+подходит',
            r'всё\s+устра',
            r'да,?\s+однозначно',
            r'конечно',
            r'именно\s+так',
            r'подходит',
        ]

        import re
        affirmative_re = re.compile('|'.join(affirmative_patterns), re.IGNORECASE)

        # Process agent_functions
        if not data.get('agent_functions') or len(data.get('agent_functions', [])) == 0:
            for i, msg in enumerate(dialogue):
                if msg.get('role', '').lower() in ('assistant', 'agent'):
                    content = msg['content'].lower()

                    # Check if agent mentioned roles
                    roles_mentioned = []
                    if 'администратор' in content:
                        roles_mentioned.append({
                            "name": "администратор",
                            "description": "приём звонков и запись на приём 24/7",
                            "priority": "high"
                        })
                    if 'напоминатель' in content or 'напоминани' in content:
                        roles_mentioned.append({
                            "name": "напоминатель",
                            "description": "напоминания клиентам о записи",
                            "priority": "medium"
                        })
                    if 'консультант' in content:
                        roles_mentioned.append({
                            "name": "консультант",
                            "description": "консультации по услугам и ценам",
                            "priority": "medium"
                        })
                    if 'маршрутизатор' in content or 'направл' in content or 'переключ' in content:
                        roles_mentioned.append({
                            "name": "маршрутизатор",
                            "description": "направление звонков нужным специалистам",
                            "priority": "medium"
                        })

                    # Check next user message for affirmative
                    if roles_mentioned and i + 1 < len(dialogue):
                        next_msg = dialogue[i + 1]
                        if next_msg.get('role', '').lower() in ('user', 'client', 'клиент'):
                            user_response = next_msg['content'].lower()
                            if affirmative_re.search(user_response):
                                data['agent_functions'] = roles_mentioned
                                logger.debug(
                                    "Contextual post-processing filled agent_functions",
                                    count=len(roles_mentioned)
                                )
                                break

        # Process integrations
        if not data.get('integrations') or len(data.get('integrations', [])) == 0:
            for i, msg in enumerate(dialogue):
                if msg.get('role', '').lower() in ('assistant', 'agent'):
                    content = msg['content'].lower()

                    # Check if agent mentioned integrations
                    integrations_mentioned = []
                    if 'crm' in content or ('систем' in content and 'учёт' in content):
                        integrations_mentioned.append({
                            "name": "CRM",
                            "purpose": "интеграция с системой учёта клиентов",
                            "required": True
                        })
                    if ('календар' in content and 'интеграц' in content) or ('запис' in content and 'интеграц' in content):
                        integrations_mentioned.append({
                            "name": "Календарь",
                            "purpose": "синхронизация записей",
                            "required": True
                        })
                    if 'телефон' in content and 'интеграц' in content:
                        integrations_mentioned.append({
                            "name": "Телефония",
                            "purpose": "интеграция с телефонной системой",
                            "required": True
                        })

                    # Check next user message for affirmative
                    if integrations_mentioned and i + 1 < len(dialogue):
                        next_msg = dialogue[i + 1]
                        if next_msg.get('role', '').lower() in ('user', 'client', 'клиент'):
                            user_response = next_msg['content'].lower()
                            if affirmative_re.search(user_response):
                                data['integrations'] = integrations_mentioned
                                logger.debug(
                                    "Contextual post-processing filled integrations",
                                    count=len(integrations_mentioned)
                                )
                                break

        return data

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
            contact_phone=data.get('contact_phone', ''),
            contact_email=data.get('contact_email', ''),

            # Business context
            business_description=data.get('business_description', ''),
            business_type=data.get('business_type'),
            services=data.get('services', []),
            client_types=data.get('client_types', []),
            current_problems=data.get('current_problems', []),
            business_goals=data.get('business_goals', []),
            constraints=data.get('constraints', []),
            compliance_requirements=data.get('compliance_requirements', []),
            call_volume=data.get('call_volume', ''),
            budget=data.get('budget', ''),
            timeline=data.get('timeline', ''),
            additional_notes=data.get('additional_notes', ''),

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
            working_hours=data.get('working_hours', {}),
            transfer_conditions=data.get('transfer_conditions', []),

            # Integrations
            integrations=integrations,

            # Proposed solution
            main_function=main_function,
            additional_functions=additional_functions,

            # Metadata
            created_at=datetime.now(timezone.utc),
            consultation_duration_seconds=duration_seconds
        )

    def _extract_string_list(self, items: List, key: str = 'description') -> List[str]:
        """Extract string list from mixed list of dicts/strings."""
        result = []
        for item in items:
            if isinstance(item, str) and item:
                result.append(item)
            elif isinstance(item, dict):
                value = item.get(key, item.get('name', item.get('type', '')))
                if value:
                    result.append(str(value))
        return result

    def _extract_functions_list(self, items: List, default_priority: str = 'medium') -> List[AgentFunction]:
        """Extract AgentFunction list from dict list."""
        result = []
        for func in items:
            if isinstance(func, dict):
                result.append(AgentFunction(
                    name=func.get('name', ''),
                    description=func.get('description', ''),
                    priority=func.get('priority', default_priority)
                ))
        return result

    def _extract_integrations_list(self, items: List) -> List[Integration]:
        """Extract Integration list from dict list."""
        result = []
        for intg in items:
            if isinstance(intg, dict):
                # ProposedIntegration uses 'reason', Integration uses 'purpose'
                purpose = intg.get('purpose', '') or intg.get('reason', '') or intg.get('details', '')
                # Also check 'needed' (ProposedIntegration) vs 'required' (Integration)
                required = intg.get('required', intg.get('needed', True))
                result.append(Integration(
                    name=intg.get('name', ''),
                    purpose=purpose,
                    required=required if isinstance(required, bool) else True
                ))
        return result

    def _extract_from_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Extract all relevant fields from business_analysis."""
        # Basic company info
        company_name = analysis.get('company_name', '')
        industry = analysis.get('industry', '')
        specialization = analysis.get('specialization', '')

        # Extract pain points and opportunities
        current_problems = self._extract_string_list(analysis.get('pain_points', []))
        business_goals = self._extract_string_list(analysis.get('opportunities', []))
        constraints = self._extract_string_list(analysis.get('constraints', []))

        # Extract client type (may be single string or list)
        client_type = analysis.get('client_type', '')
        client_types = self._extract_string_list(analysis.get('client_types', []), key='name')
        if client_type and client_type not in ['unknown', '']:
            client_types = [client_type] if not client_types else client_types

        # Services
        services = self._extract_string_list(analysis.get('services', []), key='name')

        # Generate business_description from available data
        business_description = ""
        if specialization:
            business_description = specialization
        elif industry:
            business_description = f"Компания в сфере {industry}"

        # Add industry insights to constraints if valuable
        industry_insights = analysis.get('industry_insights', [])
        if industry_insights and not constraints:
            constraints = industry_insights[:3]

        return {
            'company_name': company_name,
            'industry': industry,
            'specialization': specialization,
            'business_description': business_description,
            'current_problems': current_problems,
            'business_goals': business_goals,
            'constraints': constraints,
            'client_types': client_types,
            'services': services,
        }

    def _extract_from_solution(self, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Extract all relevant fields from proposed_solution."""
        main_func_data = solution.get('main_function', {})
        main_function = None
        agent_purpose = ""

        if main_func_data and isinstance(main_func_data, dict):
            main_function = AgentFunction(
                name=main_func_data.get('name', ''),
                description=main_func_data.get('description', ''),
                priority='high'
            )
            agent_purpose = main_func_data.get('description', '')

        # Get agent name - generate if not provided
        agent_name = solution.get('agent_name', '')
        if not agent_name and main_function:
            # Generate a generic name based on function
            agent_name = "Виртуальный ассистент"

        # Extract integrations with proper purpose
        integrations = self._extract_integrations_list(solution.get('integrations', []))

        # Extract additional functions
        additional_functions = self._extract_functions_list(solution.get('additional_functions', []))

        # Build unified agent_functions list (main + additional)
        agent_functions = []
        if main_function:
            agent_functions.append(main_function)
        agent_functions.extend(additional_functions)

        # Extract expected_results for additional context
        expected_results = solution.get('expected_results', '')

        # Typical questions from FAQ or generate from context
        typical_questions = solution.get('typical_questions', [])

        return {
            'main_function': main_function,
            'additional_functions': additional_functions,
            'agent_functions': agent_functions,
            'agent_name': agent_name,
            'agent_purpose': solution.get('agent_purpose', agent_purpose),
            'integrations': integrations,
            'typical_questions': typical_questions,
            'expected_results': expected_results,
        }

    def _generate_typical_questions(
        self,
        industry: str,
        specialization: str,
        main_function: Optional[AgentFunction],
        client_types: List[str]
    ) -> List[str]:
        """Generate typical FAQ questions based on business context."""
        questions = []

        # Industry-specific questions
        industry_lower = industry.lower() if industry else ""
        spec_lower = specialization.lower() if specialization else ""

        # Common questions for all businesses
        if main_function:
            func_name = main_function.name.lower()
            if "квалификац" in func_name or "лид" in func_name:
                questions.extend([
                    "Какие условия сотрудничества?",
                    "Какой бюджет нужен для начала?",
                    "Какие документы потребуются?"
                ])
            elif "запис" in func_name or "бронирован" in func_name:
                questions.extend([
                    "Как записаться на приём?",
                    "Какие есть свободные окна?",
                    "Можно ли перенести запись?"
                ])
            elif "поддержк" in func_name or "консультац" in func_name:
                questions.extend([
                    "Как связаться с менеджером?",
                    "Какой график работы?",
                    "Где находится ваш офис?"
                ])

        # Industry-specific questions
        if "wellness" in industry_lower or "массаж" in spec_lower or "здоров" in industry_lower:
            questions.extend([
                "Сколько длится сеанс?",
                "Какие виды массажа вы предлагаете?",
                "Есть ли противопоказания?"
            ])
        elif "франчайз" in spec_lower or "франшиз" in spec_lower:
            questions.extend([
                "Какой размер паушального взноса?",
                "Какие требования к локации?",
                "Какая окупаемость проекта?"
            ])
        elif "b2b" in " ".join(client_types).lower():
            questions.extend([
                "Работаете ли вы с юрлицами?",
                "Предоставляете ли закрывающие документы?",
                "Какие условия для оптовых заказов?"
            ])

        # Deduplicate and limit
        seen = set()
        unique_questions = []
        for q in questions:
            if q not in seen:
                seen.add(q)
                unique_questions.append(q)

        return unique_questions[:5]  # Max 5 questions

    def _generate_services_from_context(
        self,
        specialization: str,
        industry: str,
        business_description: str
    ) -> List[str]:
        """Generate services list from business context when not explicitly provided."""
        services = []

        spec_lower = specialization.lower() if specialization else ""
        industry_lower = industry.lower() if industry else ""
        desc_lower = business_description.lower() if business_description else ""

        combined = f"{spec_lower} {industry_lower} {desc_lower}"

        # Extract services based on keywords
        if "массаж" in combined:
            services.append("Экспресс-массаж (15 минут)")
        if "франчайз" in combined or "франшиз" in combined:
            services.append("Продажа франшизы")
            services.append("Обучение и поддержка франчайзи")
        if "консультац" in combined:
            services.append("Консультационные услуги")
        if "wellness" in combined or "здоров" in combined:
            services.append("Wellness-услуги")
        if "бронирован" in combined or "запис" in combined:
            services.append("Онлайн-бронирование")

        # If we found something specific, return it; otherwise generate generic
        if not services:
            if industry:
                services.append(f"Основные услуги в сфере {industry}")
            if specialization and specialization not in str(services):
                services.append(specialization)

        return services

    def _extract_voice_settings_from_constraints(self, constraints: List[str]) -> Dict[str, str]:
        """Extract voice settings from constraints text."""
        voice_gender = "female"  # default
        voice_tone = "professional"  # default

        constraints_text = " ".join(constraints).lower()

        # Check for gender preferences
        if "мужск" in constraints_text or "male" in constraints_text:
            voice_gender = "male"
        elif "женск" in constraints_text or "female" in constraints_text:
            voice_gender = "female"

        # Check for tone preferences
        if "дружелюбн" in constraints_text or "friendly" in constraints_text:
            voice_tone = "friendly"
        elif "спокойн" in constraints_text or "calm" in constraints_text:
            voice_tone = "calm"
        elif "уверенн" in constraints_text or "confident" in constraints_text:
            voice_tone = "confident, professional"
        elif "делов" in constraints_text or "professional" in constraints_text:
            voice_tone = "professional"

        return {"voice_gender": voice_gender, "voice_tone": voice_tone}

    def _build_fallback_anketa(
        self,
        _dialogue: List[Dict[str, str]],  # Reserved for future dialogue-based extraction
        analysis: Optional[Dict[str, Any]],
        solution: Optional[Dict[str, Any]],
        duration_seconds: float
    ) -> FinalAnketa:
        """Build comprehensive anketa from available data when LLM extraction fails."""
        logger.info("Building fallback anketa from available data")

        # Extract from business_analysis
        analysis_data = self._extract_from_analysis(analysis) if analysis else {}

        # Extract from proposed_solution
        solution_data = self._extract_from_solution(solution) if solution else {}

        # Extract voice settings from constraints
        voice_settings = self._extract_voice_settings_from_constraints(
            analysis_data.get('constraints', [])
        )

        # Determine call_direction from context
        call_direction = self._determine_call_direction(
            analysis_data.get('constraints', []),
            analysis_data.get('business_goals', [])
        )

        # Generate agent name if empty
        agent_name = solution_data.get('agent_name', '')
        if not agent_name:
            company = analysis_data.get('company_name', '')
            agent_name = f"Ассистент {company}" if company else "Виртуальный ассистент"

        # Generate business description if empty
        business_description = analysis_data.get('business_description', '')
        if not business_description:
            spec = analysis_data.get('specialization', '')
            industry = analysis_data.get('industry', '')
            if spec:
                business_description = spec
            elif industry:
                business_description = f"Компания в сфере {industry}"

        # Generate services if empty
        services = analysis_data.get('services', [])
        if not services:
            services = self._generate_services_from_context(
                analysis_data.get('specialization', ''),
                analysis_data.get('industry', ''),
                business_description
            )

        # Generate typical questions if empty
        typical_questions = solution_data.get('typical_questions', [])
        if not typical_questions:
            typical_questions = self._generate_typical_questions(
                analysis_data.get('industry', ''),
                analysis_data.get('specialization', ''),
                solution_data.get('main_function'),
                analysis_data.get('client_types', [])
            )

        logger.info(
            "Fallback anketa built",
            company=analysis_data.get('company_name', ''),
            problems_count=len(analysis_data.get('current_problems', [])),
            goals_count=len(analysis_data.get('business_goals', [])),
            functions_count=len(solution_data.get('agent_functions', []))
        )

        anketa = FinalAnketa(
            # Company info
            company_name=analysis_data.get('company_name', ''),
            industry=analysis_data.get('industry', ''),
            specialization=analysis_data.get('specialization', ''),

            # Business context
            business_description=business_description,
            services=services,
            client_types=analysis_data.get('client_types', []),
            current_problems=analysis_data.get('current_problems', []),
            business_goals=analysis_data.get('business_goals', []),
            constraints=analysis_data.get('constraints', []),

            # Agent config
            agent_name=agent_name,
            agent_purpose=solution_data.get('agent_purpose', ''),
            agent_functions=solution_data.get('agent_functions', []),
            typical_questions=typical_questions,

            # Voice parameters
            voice_gender=voice_settings['voice_gender'],
            voice_tone=voice_settings['voice_tone'],
            language="ru",
            call_direction=call_direction,

            # Proposed solution
            main_function=solution_data.get('main_function'),
            additional_functions=solution_data.get('additional_functions', []),

            # Integrations
            integrations=solution_data.get('integrations', []),

            # Metadata
            created_at=datetime.now(timezone.utc),
            consultation_duration_seconds=duration_seconds
        )
        # R22-07: Mark as fallback so accumulative merge can skip auto-generated values
        anketa._is_fallback = True
        return anketa

    def _determine_call_direction(self, constraints: List[str], business_goals: List[str]) -> str:
        """Determine call direction from context."""
        constraints_text = " ".join(constraints).lower()
        goals_text = " ".join(business_goals).lower()

        if "исходящ" in constraints_text or "outbound" in constraints_text:
            return "outbound"
        if "входящ" in goals_text or "inbound" in goals_text:
            return "inbound"
        return "inbound"  # default

    # =========================================================================
    # V2.0: AI EXPERT CONTENT GENERATION
    # =========================================================================

    async def _generate_expert_content(self, anketa: FinalAnketa) -> FinalAnketa:
        """
        Generate AI expert content for v2.0 blocks.

        This transforms a basic anketa into a comprehensive expert consultation
        deliverable with FAQ answers, objection handling, financial model, etc.
        """
        logger.info("Generating expert content for anketa v2.0",
                   company=anketa.company_name, industry=anketa.industry)

        # Build context for AI generation
        context = self._build_expert_context(anketa)

        # Generate all expert blocks in a single LLM call for efficiency
        prompt = self._build_expert_generation_prompt(context)

        # Load system prompt from YAML
        system_prompt = get_prompt("anketa/expert", "system_prompt")

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=8000
            )

            expert_data = self._parse_json_response(response)
            anketa = self._merge_expert_content(anketa, expert_data)

            logger.info("Expert content generated successfully",
                       faq_count=len(anketa.faq_items),
                       objections_count=len(anketa.objection_handlers),
                       kpis_count=len(anketa.success_kpis))

        except Exception as e:
            logger.warning("Expert content generation failed, using fallback",
                          error=str(e))
            anketa = self._generate_fallback_expert_content(anketa)

        return anketa

    def _build_expert_context(self, anketa: FinalAnketa) -> Dict[str, Any]:
        """Build context dict for expert content generation."""
        return {
            "company_name": anketa.company_name,
            "industry": anketa.industry,
            "specialization": anketa.specialization,
            "business_description": anketa.business_description,
            "services": anketa.services,
            "client_types": anketa.client_types,
            "current_problems": anketa.current_problems,
            "business_goals": anketa.business_goals,
            "agent_name": anketa.agent_name,
            "agent_purpose": anketa.agent_purpose,
            "main_function": anketa.main_function.model_dump() if anketa.main_function else None,
            "additional_functions": [f.model_dump() for f in anketa.additional_functions],
            "integrations": [i.model_dump() for i in anketa.integrations],
            "call_direction": anketa.call_direction,
        }

    def _build_expert_generation_prompt(self, context: Dict[str, Any]) -> str:
        """Build comprehensive prompt for expert content generation from YAML."""
        company = context.get('company_name', 'компания')
        industry = context.get('industry', 'бизнес')
        purpose = context.get('agent_purpose', 'консультирование клиентов')

        return render_prompt(
            "anketa/expert", "user_prompt_template",
            company_name=company,
            industry=industry,
            agent_purpose=purpose
        )

    def _merge_expert_content(self, anketa: FinalAnketa, data: Dict[str, Any]) -> FinalAnketa:
        """Merge AI-generated expert content into anketa."""

        # FAQ Items
        faq_items = []
        for item in data.get('faq_items', []):
            if isinstance(item, dict):
                faq_items.append(FAQItem(
                    question=item.get('question', ''),
                    answer=item.get('answer', ''),
                    category=item.get('category', 'general')
                ))
        anketa.faq_items = faq_items

        # Objection Handlers
        objection_handlers = []
        for item in data.get('objection_handlers', []):
            if isinstance(item, dict):
                objection_handlers.append(ObjectionHandler(
                    objection=item.get('objection', ''),
                    response=item.get('response', ''),
                    follow_up=item.get('follow_up')
                ))
        anketa.objection_handlers = objection_handlers

        # Sample Dialogue
        sample_dialogue = []
        for item in data.get('sample_dialogue', []):
            if isinstance(item, dict):
                sample_dialogue.append(DialogueExample(
                    role=item.get('role', 'bot'),
                    message=item.get('message', ''),
                    intent=item.get('intent')
                ))
        anketa.sample_dialogue = sample_dialogue

        # Financial Metrics
        financial_metrics = []
        for item in data.get('financial_metrics', []):
            if isinstance(item, dict):
                financial_metrics.append(FinancialMetric(
                    name=item.get('name', ''),
                    value=item.get('value', ''),
                    source=item.get('source', 'ai_benchmark'),
                    note=item.get('note')
                ))
        anketa.financial_metrics = financial_metrics

        # Competitors
        competitors = []
        for item in data.get('competitors', []):
            if isinstance(item, dict):
                competitors.append(Competitor(
                    name=item.get('name', ''),
                    strengths=item.get('strengths', []),
                    weaknesses=item.get('weaknesses', []),
                    price_range=item.get('price_range')
                ))
        anketa.competitors = competitors

        # Market Insights
        market_insights = []
        for item in data.get('market_insights', []):
            if isinstance(item, dict):
                market_insights.append(MarketInsight(
                    insight=item.get('insight', ''),
                    source=item.get('source', 'ai_analysis'),
                    relevance=item.get('relevance', 'medium')
                ))
        anketa.market_insights = market_insights

        # Escalation Rules
        escalation_rules = []
        for item in data.get('escalation_rules', []):
            if isinstance(item, dict):
                escalation_rules.append(EscalationRule(
                    trigger=item.get('trigger', ''),
                    urgency=item.get('urgency', 'medium'),
                    action=item.get('action', '')
                ))
        anketa.escalation_rules = escalation_rules

        # Success KPIs
        success_kpis = []
        for item in data.get('success_kpis', []):
            if isinstance(item, dict):
                success_kpis.append(KPIMetric(
                    name=item.get('name', ''),
                    target=item.get('target', ''),
                    benchmark=item.get('benchmark'),
                    measurement=item.get('measurement')
                ))
        anketa.success_kpis = success_kpis

        # Launch Checklist
        launch_checklist = []
        for item in data.get('launch_checklist', []):
            if isinstance(item, dict):
                launch_checklist.append(ChecklistItem(
                    item=item.get('item', ''),
                    required=item.get('required', True),
                    responsible=item.get('responsible', 'client')
                ))
        anketa.launch_checklist = launch_checklist

        # AI Recommendations
        ai_recommendations = []
        for item in data.get('ai_recommendations', []):
            if isinstance(item, dict):
                ai_recommendations.append(AIRecommendation(
                    recommendation=item.get('recommendation', ''),
                    impact=item.get('impact', ''),
                    priority=item.get('priority', 'medium'),
                    effort=item.get('effort', 'medium')
                ))
        anketa.ai_recommendations = ai_recommendations

        # Target Segments
        target_segments = []
        for item in data.get('target_segments', []):
            if isinstance(item, dict):
                target_segments.append(TargetAudienceSegment(
                    name=item.get('name', ''),
                    description=item.get('description', ''),
                    pain_points=item.get('pain_points', []),
                    triggers=item.get('triggers', [])
                ))
        anketa.target_segments = target_segments

        # Simple dicts
        anketa.tone_of_voice = data.get('tone_of_voice', {})
        anketa.error_handling_scripts = data.get('error_handling_scripts', {})
        anketa.follow_up_sequence = data.get('follow_up_sequence', [])
        anketa.competitive_advantages = data.get('competitive_advantages', [])

        # Update version
        anketa.anketa_version = "2.0"

        return anketa

    def _generate_fallback_expert_content(self, anketa: FinalAnketa) -> FinalAnketa:
        """Generate basic expert content when LLM fails."""
        logger.info("Generating fallback expert content")

        # Basic FAQ based on agent purpose
        faq_items = [
            FAQItem(
                question="Какие услуги вы предоставляете?",
                answer=f"Мы предлагаем {', '.join(anketa.services[:3]) if anketa.services else 'широкий спектр услуг'}.",
                category="general"
            ),
            FAQItem(
                question="Как с вами связаться?",
                answer="Вы можете позвонить нам или оставить заявку на сайте. Мы свяжемся с вами в ближайшее время.",
                category="support"
            ),
            FAQItem(
                question="Какова стоимость услуг?",
                answer="Стоимость зависит от ваших потребностей. Могу рассчитать предварительную стоимость или соединить с менеджером.",
                category="pricing"
            ),
        ]
        anketa.faq_items = faq_items

        # Basic objection handlers
        anketa.objection_handlers = [
            ObjectionHandler(
                objection="Слишком дорого",
                response="Понимаю вашу озабоченность. Давайте обсудим, какой вариант будет оптимален для вашего бюджета.",
                follow_up="Предложить альтернативные варианты"
            ),
            ObjectionHandler(
                objection="Нужно подумать",
                response="Конечно, это важное решение. Могу отправить вам детальную информацию на email?",
                follow_up="Запросить email и отправить материалы"
            ),
        ]

        # Basic escalation rules
        anketa.escalation_rules = [
            EscalationRule(
                trigger="Клиент просит соединить с руководством",
                urgency="immediate",
                action="Перевести на менеджера"
            ),
            EscalationRule(
                trigger="Клиент выражает сильное недовольство",
                urgency="immediate",
                action="Извиниться и перевести на специалиста"
            ),
        ]

        # Basic KPIs
        anketa.success_kpis = [
            KPIMetric(name="Конверсия в целевое действие", target=">15%", measurement="Отношение целевых действий к звонкам"),
            KPIMetric(name="Удовлетворённость клиентов", target=">4.0/5", measurement="Средняя оценка после разговора"),
            KPIMetric(name="Среднее время разговора", target="<5 мин", measurement="Время от начала до конца диалога"),
        ]

        # Basic launch checklist
        anketa.launch_checklist = [
            ChecklistItem(item="Утвердить скрипты и сценарии", required=True, responsible="both"),
            ChecklistItem(item="Настроить интеграции с CRM", required=True, responsible="team"),
            ChecklistItem(item="Предоставить актуальный прайс", required=True, responsible="client"),
            ChecklistItem(item="Провести тестовые звонки", required=True, responsible="both"),
        ]

        # Basic recommendations
        anketa.ai_recommendations = [
            AIRecommendation(
                recommendation="Регулярно обновлять базу знаний агента",
                impact="Повышение точности ответов на 20-30%",
                priority="high",
                effort="low"
            ),
            AIRecommendation(
                recommendation="Настроить автоматическую отправку резюме разговора",
                impact="Улучшение конверсии и прозрачности",
                priority="medium",
                effort="low"
            ),
        ]

        # Basic tone of voice
        anketa.tone_of_voice = {
            "do": "Быть вежливым, профессиональным, готовым помочь",
            "dont": "Не давить на клиента, не торопить, не использовать сленг"
        }

        # Basic error handling
        anketa.error_handling_scripts = {
            "not_understood": "Извините, я не совсем понял. Могли бы вы уточнить?",
            "technical_issue": "Произошла техническая проблема. Сейчас соединю с оператором.",
            "out_of_scope": "Этот вопрос лучше обсудить с нашим специалистом."
        }

        anketa.anketa_version = "2.0"
        return anketa

    # =========================================================================
    # V5.0: INTERVIEW EXTRACTION
    # =========================================================================

    async def _extract_interview(
        self,
        dialogue_history: List[Dict[str, str]],
        duration_seconds: float = 0.0,
    ) -> InterviewAnketa:
        """Extract structured interview data into InterviewAnketa."""
        dialogue_text = "\n".join([
            f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}"
            for msg in dialogue_history[-100:]  # Last 100 messages to fit context
        ])

        prompt = f"""Ты — эксперт по извлечению данных из интервью.

ЗАДАЧА: Извлеки структурированные данные из интервью в JSON.

ПРАВИЛА:
1. Извлекай ВСЕ пары вопрос-ответ из диалога
2. Определи темы, которые обсуждались
3. Выдели ключевые цитаты респондента
4. Заполни профиль респондента если данные есть
5. Верни ТОЛЬКО валидный JSON
6. КРИТИЧНО: contact_name — извлеки ТОЧНОЕ имя, которое респондент назвал. Ищи фразы типа "Меня зовут...", "Я — ..."
7. КРИТИЧНО: contact_role — извлеки должность/роль. Ищи: "Я работаю...", "Моя должность...", "Я — директор/менеджер/..."
8. interview_title — определи ГЛАВНУЮ тему интервью из контекста разговора
9. interviewee_industry — определи отрасль из описания работы респондента

ДИАЛОГ ИНТЕРВЬЮ:
{dialogue_text}

СХЕМА JSON:
{{
  "contact_name": "ТОЧНОЕ имя респондента из диалога",
  "contact_role": "должность/роль респондента из диалога",
  "contact_phone": "телефон (если респондент назвал)",
  "contact_email": "email (если респондент назвал)",
  "company_name": "организация/компания респондента",
  "interview_type": "тип интервью: market_research, customer_discovery, hr, survey, requirements или general",
  "interview_title": "конкретная тема интервью (НЕ 'general'!)",
  "target_topics": ["целевая тема 1", "целевая тема 2"],
  "interviewee_context": "контекст о респонденте (опыт, бэкграунд, сколько лет в области)",
  "interviewee_industry": "отрасль респондента",
  "qa_pairs": [
    {{"question": "заданный вопрос", "answer": "ответ респондента", "topic": "тег темы"}}
  ],
  "detected_topics": ["тема 1", "тема 2"],
  "key_quotes": ["важная цитата 1 (дословно из ответов респондента)", "цитата 2"],
  "summary": "краткое резюме интервью (2-3 предложения)",
  "key_insights": ["конкретный инсайт 1", "инсайт 2"],
  "unresolved_topics": ["тема которую не удалось полностью раскрыть"],
  "ai_recommendations": [
    {{"recommendation": "рекомендация", "impact": "ожидаемый эффект", "priority": "high/medium/low", "effort": "low/medium/high"}}
  ]
}}

Верни ТОЛЬКО JSON:"""

        system_prompt = "Ты — эксперт по анализу интервью. Извлекай данные точно и структурированно."

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=8192
            )

            data, _ = self._parse_json_with_repair(response)
            return self._build_interview_anketa(data, duration_seconds)

        except Exception as e:
            logger.error("Interview extraction failed", error=str(e))
            return self._build_interview_anketa({}, duration_seconds)

    def _build_interview_anketa(self, data: dict, duration_seconds: float) -> InterviewAnketa:
        """Build InterviewAnketa from extracted data."""
        qa_pairs = []
        for qa in data.get('qa_pairs', []):
            if isinstance(qa, dict):
                qa_pairs.append(QAPair(
                    question=qa.get('question', ''),
                    answer=qa.get('answer', ''),
                    topic=qa.get('topic', 'general'),
                    follow_ups=qa.get('follow_ups', []),
                ))

        ai_recs = []
        for rec in data.get('ai_recommendations', []):
            if isinstance(rec, dict):
                ai_recs.append(AIRecommendation(
                    recommendation=rec.get('recommendation', ''),
                    impact=rec.get('impact', ''),
                    priority=rec.get('priority', 'medium'),
                    effort=rec.get('effort', 'medium'),
                ))

        return InterviewAnketa(
            company_name=data.get('company_name', ''),
            contact_name=data.get('contact_name', ''),
            contact_role=data.get('contact_role', ''),
            contact_email=data.get('contact_email', ''),
            contact_phone=data.get('contact_phone', ''),
            interview_title=data.get('interview_title', ''),
            interview_type=data.get('interview_type', 'general'),
            target_topics=data.get('target_topics', []),
            interviewee_context=data.get('interviewee_context', ''),
            interviewee_industry=data.get('interviewee_industry', ''),
            qa_pairs=qa_pairs,
            detected_topics=data.get('detected_topics', []),
            key_quotes=data.get('key_quotes', []),
            summary=data.get('summary', ''),
            key_insights=data.get('key_insights', []),
            ai_recommendations=ai_recs,
            unresolved_topics=data.get('unresolved_topics', []),
            consultation_duration_seconds=duration_seconds,
        )
