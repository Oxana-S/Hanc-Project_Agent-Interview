"""
DeepSeek API клиент для анализа и генерации.

Наследует OpenAICompatibleClient (общий chat() интерфейс).
Добавляет DeepSeek-специфичные методы для текстовых скриптов:
  - analyze_answer() — анализ ответа интервьюируемого
  - analyze_and_complete_anketa() — генерация полной анкеты из сырых ответов
  - generate_example_dialogues() — генерация примеров диалогов
  - suggest_restrictions() — генерация ограничений для агента
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from src.llm.openai_client import OpenAICompatibleClient, MAX_RETRIES, RETRY_DELAY  # noqa: F401
from src.config.prompt_loader import get_prompt, render_prompt

load_dotenv()
logger = logging.getLogger("deepseek")


class DeepSeekClient(OpenAICompatibleClient):
    """Клиент для DeepSeek API с дополнительными методами анализа."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ):
        super().__init__(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            endpoint=endpoint or os.getenv("DEEPSEEK_API_ENDPOINT", "https://api.deepseek.com/v1"),
            model=model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            logger_name="deepseek",
            env_key="DEEPSEEK_API_KEY",
        )

    async def analyze_answer(
        self,
        question: str,
        answer: str,
        question_context: Dict[str, Any],
        previous_answers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Анализ ответа интервьюируемого в реальном времени.

        Определяет:
        - Полнота ответа
        - Нужны ли уточнения
        - Какие уточняющие вопросы задать
        """
        context_text = ""
        if previous_answers:
            context_text = "Предыдущие ответы клиента:\n"
            for qid, ans in list(previous_answers.items())[-5:]:
                context_text += f"- {ans[:100]}...\n" if len(ans) > 100 else f"- {ans}\n"

        system_prompt = get_prompt("llm/analyze_answer", "system_prompt")
        user_prompt = render_prompt(
            "llm/analyze_answer",
            "user_prompt_template",
            question=question,
            answer=answer,
            section=question_context.get("section", "Общие"),
            priority=question_context.get("priority", "optional"),
            examples=str(question_context.get("examples", [])),
            context=context_text,
        )

        try:
            # R12-04: Use local model override instead of mutating shared self.model
            original_model = self.model
            self.model = "deepseek-chat"
            try:
                response = await self.chat(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=2048,
                )
            finally:
                self.model = original_model

            json_text = response.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                parts = json_text.split("```")
                if len(parts) >= 2:
                    json_text = parts[1]

            json_text = json_text.strip()
            start = json_text.find("{")
            end = json_text.rfind("}")
            if start != -1 and end != -1:
                json_text = json_text[start : end + 1]

            json_text = json_text.replace("\n", " ").replace("\r", "")
            result = json.loads(json_text)

            return {
                "is_complete": result.get("is_complete", False),
                "completeness_score": min(1.0, max(0.0, result.get("completeness_score", 0.5))),
                "needs_clarification": result.get("needs_clarification", False),
                "clarification_questions": result.get("clarification_questions", [])[:3],
                "extracted_info": result.get("extracted_info", {}),
                "reasoning": result.get("reasoning", ""),
            }

        except Exception as e:
            logger.error(f"Answer analysis failed: {e}")
            word_count = len(answer.split())
            is_short = word_count < 10

            return {
                "is_complete": not is_short,
                "completeness_score": min(1.0, word_count / 20),
                "needs_clarification": is_short,
                "clarification_questions": ["Можете рассказать подробнее?"] if is_short else [],
                "extracted_info": {},
                "reasoning": "Fallback анализ по количеству слов",
            }

    async def analyze_and_complete_anketa(
        self,
        raw_responses: Dict[str, str],
        pattern: str,
        company_name: str,
    ) -> Dict[str, Any]:
        """Анализ сырых ответов и генерация полной анкеты."""
        responses_text = "\n".join(
            [f"Вопрос {qid}: {answer}" for qid, answer in raw_responses.items()]
        )

        system_prompt = get_prompt("llm/complete_anketa", "system_prompt")
        user_prompt = render_prompt(
            "llm/complete_anketa",
            "user_prompt_template",
            company_name=company_name,
            pattern=pattern,
            responses_text=responses_text,
        )

        response = await self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        try:
            json_text = response
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            return json.loads(json_text.strip())

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}, response={response[:500]}")
            return {}

    async def generate_example_dialogues(
        self,
        company_name: str,
        industry: str,
        services: List[str],
        agent_purpose: str,
    ) -> List[Dict[str, Any]]:
        """Генерация примеров диалогов для агента."""
        services_text = "\n".join([f"- {s}" for s in services])

        system_prompt = get_prompt("llm/generation", "dialogues.system_prompt")
        user_prompt = render_prompt(
            "llm/generation",
            "dialogues.user_prompt_template",
            company_name=company_name,
            industry=industry,
            services_text=services_text,
            agent_purpose=agent_purpose,
        )

        response = await self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )

        try:
            json_text = response
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            return json.loads(json_text.strip())
        except Exception:
            return []

    async def suggest_restrictions(
        self,
        industry: str,
        agent_purpose: str,
    ) -> List[str]:
        """Генерация рекомендуемых ограничений для агента."""
        system_prompt = get_prompt("llm/generation", "restrictions.system_prompt")
        user_prompt = render_prompt(
            "llm/generation",
            "restrictions.user_prompt_template",
            industry=industry,
            agent_purpose=agent_purpose,
        )

        response = await self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
        )

        try:
            json_text = response
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            return json.loads(json_text.strip())
        except Exception:
            return []
