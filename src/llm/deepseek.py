"""
DeepSeek API клиент для анализа и генерации.

Оптимизирован для deepseek-reasoner:
- Увеличенные лимиты токенов (reasoning требует ~1000-4000 токенов)
- Увеличенный timeout (reasoning занимает больше времени)
- Retry логика для rate limits
"""

import os
import json
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from src.config.prompt_loader import get_prompt, render_prompt

load_dotenv()
logger = logging.getLogger("deepseek")

# Константы для retry
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # секунды


class DeepSeekClient:
    """Клиент для DeepSeek API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.endpoint = endpoint or os.getenv("DEEPSEEK_API_ENDPOINT", "https://api.deepseek.com/v1")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8192,  # Увеличено для deepseek-reasoner
        top_p: Optional[float] = None,  # Nucleus sampling
        timeout: float = 180.0  # Увеличено для reasoning
    ) -> str:
        """
        Отправить запрос к DeepSeek Chat API.

        Args:
            messages: Список сообщений [{role, content}]
            temperature: Температура генерации (0.0-2.0)
            max_tokens: Максимум токенов в ответе (для reasoner нужно 2048+)
            top_p: Nucleus sampling (0.0-1.0), None = не использовать
            timeout: Таймаут запроса в секундах

        Returns:
            Текст ответа
        """
        url = f"{self.endpoint}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Добавляем top_p если указан
        if top_p is not None:
            payload["top_p"] = top_p

        # Retry логика для rate limits и transient errors
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._make_request(url, headers, payload, timeout)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Rate limit hit, retrying (attempt {attempt + 1}, wait {wait_time}s)"
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.warning(
                    f"Request failed ({e}), retrying (attempt {attempt + 1}, wait {wait_time}s)"
                )
                await asyncio.sleep(wait_time)
                last_error = e

        # Все попытки исчерпаны
        raise last_error or Exception("All retry attempts failed")

    async def _make_request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float
    ) -> str:
        """Выполнить HTTP запрос к API."""
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                data = response.json()

                # Логируем finish_reason для диагностики
                choice = data["choices"][0]
                finish_reason = choice.get("finish_reason", "unknown")
                content = choice["message"]["content"] or ""

                if not content:
                    logger.warning(
                        f"DeepSeek returned empty content (finish_reason={finish_reason}, usage={data.get('usage', {})})"
                    )
                elif finish_reason == "length":
                    logger.warning(
                        f"DeepSeek response truncated (content_length={len(content)}, usage={data.get('usage', {})})"
                    )

                return content

            except httpx.HTTPStatusError as e:
                logger.error(f"DeepSeek API error: status={e.response.status_code}, detail={e.response.text}")
                raise
            except Exception as e:
                logger.error(f"DeepSeek request failed: {e}")
                raise

    async def analyze_answer(
        self,
        question: str,
        answer: str,
        question_context: Dict[str, Any],
        previous_answers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Анализ ответа интервьюируемого в реальном времени.

        Определяет:
        - Полнота ответа
        - Нужны ли уточнения
        - Какие уточняющие вопросы задать

        Args:
            question: Текст вопроса
            answer: Ответ пользователя
            question_context: Контекст вопроса (section, priority, examples)
            previous_answers: Предыдущие ответы для контекста

        Returns:
            {
                "is_complete": bool,
                "completeness_score": float (0-1),
                "needs_clarification": bool,
                "clarification_questions": List[str],
                "extracted_info": Dict,
                "reasoning": str
            }
        """
        # Формируем контекст из предыдущих ответов
        context_text = ""
        if previous_answers:
            context_text = "Предыдущие ответы клиента:\n"
            for qid, ans in list(previous_answers.items())[-5:]:  # Последние 5
                context_text += f"- {ans[:100]}...\n" if len(ans) > 100 else f"- {ans}\n"

        # Load prompts from YAML
        system_prompt = get_prompt("llm/analyze_answer", "system_prompt")

        user_prompt = render_prompt(
            "llm/analyze_answer", "user_prompt_template",
            question=question,
            answer=answer,
            section=question_context.get('section', 'Общие'),
            priority=question_context.get('priority', 'optional'),
            examples=str(question_context.get('examples', [])),
            context=context_text
        )

        try:
            # Используем chat модель для структурированных ответов
            original_model = self.model
            self.model = "deepseek-chat"

            # Для deepseek-reasoner нужно больше токенов на reasoning + JSON
            response = await self.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.2, max_tokens=2048)

            self.model = original_model  # Восстанавливаем

            # Парсим JSON с улучшенной обработкой
            json_text = response.strip()

            # Убираем markdown обёртки
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                parts = json_text.split("```")
                if len(parts) >= 2:
                    json_text = parts[1]

            # Ищем JSON объект в тексте
            json_text = json_text.strip()
            start = json_text.find('{')
            end = json_text.rfind('}')
            if start != -1 and end != -1:
                json_text = json_text[start:end+1]

            # Исправляем частые ошибки
            json_text = json_text.replace('\n', ' ').replace('\r', '')

            result = json.loads(json_text)

            # Валидация результата
            return {
                "is_complete": result.get("is_complete", False),
                "completeness_score": min(1.0, max(0.0, result.get("completeness_score", 0.5))),
                "needs_clarification": result.get("needs_clarification", False),
                "clarification_questions": result.get("clarification_questions", [])[:3],
                "extracted_info": result.get("extracted_info", {}),
                "reasoning": result.get("reasoning", "")
            }

        except Exception as e:
            logger.error(f"Answer analysis failed: {e}")
            # Fallback - простая эвристика
            word_count = len(answer.split())
            is_short = word_count < 10

            return {
                "is_complete": not is_short,
                "completeness_score": min(1.0, word_count / 20),
                "needs_clarification": is_short,
                "clarification_questions": ["Можете рассказать подробнее?"] if is_short else [],
                "extracted_info": {},
                "reasoning": "Fallback анализ по количеству слов"
            }

    async def analyze_and_complete_anketa(
        self,
        raw_responses: Dict[str, str],
        pattern: str,
        company_name: str
    ) -> Dict[str, Any]:
        """
        Анализ сырых ответов и генерация полной анкеты.

        LLM анализирует все ответы пользователя и:
        1. Извлекает структурированную информацию
        2. Генерирует недостающие поля на основе контекста
        3. Обогащает данные логическими выводами

        Args:
            raw_responses: Сырые ответы {question_id: answer}
            pattern: Паттерн интервью (interaction/management)
            company_name: Название компании

        Returns:
            Структурированная анкета с заполненными полями
        """
        # Формируем контекст из всех ответов
        responses_text = "\n".join([
            f"Вопрос {qid}: {answer}"
            for qid, answer in raw_responses.items()
        ])

        # Load prompts from YAML
        system_prompt = get_prompt("llm/complete_anketa", "system_prompt")

        user_prompt = render_prompt(
            "llm/complete_anketa", "user_prompt_template",
            company_name=company_name,
            pattern=pattern,
            responses_text=responses_text
        )

        response = await self.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], temperature=0.3)

        # Парсим JSON из ответа
        try:
            # Убираем markdown обёртку если есть
            json_text = response
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            return json.loads(json_text.strip())

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}, response={response[:500]}")
            # Возвращаем пустую структуру в случае ошибки
            return {}

    async def generate_example_dialogues(
        self,
        company_name: str,
        industry: str,
        services: List[str],
        agent_purpose: str
    ) -> List[Dict[str, Any]]:
        """
        Генерация примеров диалогов для агента.

        Args:
            company_name: Название компании
            industry: Отрасль
            services: Список услуг
            agent_purpose: Назначение агента

        Returns:
            Список примеров диалогов
        """
        services_text = "\n".join([f"- {s}" for s in services])

        # Load prompts from YAML
        system_prompt = get_prompt("llm/generation", "dialogues.system_prompt")
        user_prompt = render_prompt(
            "llm/generation", "dialogues.user_prompt_template",
            company_name=company_name,
            industry=industry,
            services_text=services_text,
            agent_purpose=agent_purpose
        )

        response = await self.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], temperature=0.7)

        try:
            json_text = response
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            return json.loads(json_text.strip())
        except:
            return []

    async def suggest_restrictions(
        self,
        industry: str,
        agent_purpose: str
    ) -> List[str]:
        """
        Генерация рекомендуемых ограничений для агента.

        Args:
            industry: Отрасль
            agent_purpose: Назначение агента

        Returns:
            Список ограничений (что агент НЕ должен делать)
        """
        # Load prompts from YAML
        system_prompt = get_prompt("llm/generation", "restrictions.system_prompt")
        user_prompt = render_prompt(
            "llm/generation", "restrictions.user_prompt_template",
            industry=industry,
            agent_purpose=agent_purpose
        )

        response = await self.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], temperature=0.5)

        try:
            json_text = response
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            return json.loads(json_text.strip())
        except:
            return []
