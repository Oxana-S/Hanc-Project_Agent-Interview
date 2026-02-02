"""
DeepSeek API клиент для анализа и генерации.
"""

import os
import json
import httpx
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import structlog

load_dotenv()
logger = structlog.get_logger()


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
        max_tokens: int = 4096
    ) -> str:
        """
        Отправить запрос к DeepSeek Chat API.

        Args:
            messages: Список сообщений [{role, content}]
            temperature: Температура генерации
            max_tokens: Максимум токенов в ответе

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

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()

                data = response.json()
                return data["choices"][0]["message"]["content"]

            except httpx.HTTPStatusError as e:
                logger.error("DeepSeek API error", status=e.response.status_code, detail=e.response.text)
                raise
            except Exception as e:
                logger.error("DeepSeek request failed", error=str(e))
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

        system_prompt = """Ты - эксперт по проведению интервью для создания голосовых агентов.
Твоя задача - анализировать ответы клиента и определять, достаточно ли информации.

КРИТЕРИИ ПОЛНОГО ОТВЕТА:
1. Конкретика вместо общих фраз
2. Примеры или числовые данные
3. Достаточная детализация для создания агента
4. Отсутствие противоречий с предыдущими ответами

КОГДА НУЖНЫ УТОЧНЕНИЯ:
- Ответ слишком короткий (< 15 слов для важных вопросов)
- Только общие формулировки без конкретики
- Пропущены важные детали (цены, сроки, условия)
- Неясные термины или жаргон
- Противоречия с ранее сказанным

Ответ СТРОГО в формате JSON."""

        user_prompt = f"""ВОПРОС: {question}

ОТВЕТ КЛИЕНТА: {answer}

КОНТЕКСТ ВОПРОСА:
- Секция: {question_context.get('section', 'Общие')}
- Приоритет: {question_context.get('priority', 'optional')}
- Примеры хороших ответов: {question_context.get('examples', [])}

{context_text}

Проанализируй ответ и верни JSON:
{{
    "is_complete": true/false,
    "completeness_score": 0.0-1.0,
    "needs_clarification": true/false,
    "clarification_questions": ["уточняющий вопрос 1", "вопрос 2"],
    "extracted_info": {{"ключ": "извлечённое значение"}},
    "reasoning": "почему нужны/не нужны уточнения"
}}

ВАЖНО: Если нужны уточнения - сформулируй 1-3 конкретных вопроса, которые помогут получить недостающую информацию. Вопросы должны быть дружелюбными и направляющими."""

        try:
            # Используем chat модель для структурированных ответов
            original_model = self.model
            self.model = "deepseek-chat"

            response = await self.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.2, max_tokens=1024)

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
            logger.error("Answer analysis failed", error=str(e))
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

        system_prompt = """Ты - эксперт по созданию голосовых агентов.
Твоя задача - проанализировать ответы клиента из интервью и создать ПОЛНОСТЬЮ заполненную анкету.

ВАЖНО:
1. Если какое-то поле не было явно указано клиентом, но его можно ЛОГИЧЕСКИ ВЫВЕСТИ из контекста - заполни его.
2. Если информации недостаточно - сгенерируй разумное значение по умолчанию для данной отрасли.
3. Все поля должны быть заполнены. Пустых полей быть не должно.
4. Ответ должен быть в формате JSON."""

        user_prompt = f"""Компания: {company_name}
Паттерн агента: {pattern}

ОТВЕТЫ КЛИЕНТА ИЗ ИНТЕРВЬЮ:
{responses_text}

Создай ПОЛНУЮ анкету в следующем JSON формате:

{{
  "basic_info": {{
    "company_name": "...",
    "industry": "...",
    "specialization": "конкретная специализация в отрасли",
    "language": "...",
    "agent_purpose": "подробное описание задач агента"
  }},
  "clients_and_services": {{
    "business_type": "Продажи с длинным/коротким циклом, описание",
    "call_direction": "Входящие/Исходящие/Оба направления",
    "services": [
      {{"name": "...", "duration": "...", "price": "..."}}
    ],
    "price_policy": "как агент должен говорить о ценах",
    "client_types": [
      {{"type": "B2B/B2C/...", "percentage": "...", "description": "..."}}
    ],
    "client_age_group": "возрастная группа если B2C",
    "client_sources": ["откуда приходят клиенты"],
    "typical_questions": ["типичные вопросы клиентов"]
  }},
  "agent_config": {{
    "name": "имя агента",
    "tone": "подробное описание тона общения",
    "working_hours": {{
      "weekdays": "...",
      "saturday": "...",
      "sunday": "..."
    }},
    "transfer_conditions": ["когда переводить на человека"]
  }},
  "integrations": {{
    "email": {{
      "enabled": true/false,
      "address": "...",
      "purposes": ["для чего используется"]
    }},
    "calendar": {{
      "enabled": true/false,
      "link": "...",
      "duration": "длительность встречи",
      "purposes": ["что бронируем"]
    }},
    "call_transfer": {{
      "enabled": true/false,
      "phone": "...",
      "backup_phone": "...",
      "conditions": ["условия переадресации"]
    }},
    "sms": {{
      "enabled": true/false,
      "sender_id": "...",
      "purposes": ["для чего"],
      "reminder_times": "..."
    }},
    "whatsapp": {{
      "enabled": true/false,
      "number": "...",
      "purposes": ["для чего"]
    }}
  }},
  "additional_info": {{
    "example_dialogues": [
      {{
        "scenario": "название сценария",
        "client_says": "что говорит клиент",
        "agent_should": ["что должен сделать агент"]
      }}
    ],
    "restrictions": ["что агент НЕ должен делать"],
    "compliance_requirements": ["требования compliance"]
  }},
  "contact_info": {{
    "person": "...",
    "email": "...",
    "phone": "...",
    "website": "..."
  }}
}}

ВАЖНО: Заполни ВСЕ поля. Если информация не указана явно - выведи логически или предложи разумное значение."""

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
            logger.error("Failed to parse LLM response as JSON", error=str(e), response=response[:500])
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

        prompt = f"""Компания: {company_name}
Отрасль: {industry}
Услуги:
{services_text}

Назначение агента: {agent_purpose}

Сгенерируй 3 примера типичных диалогов с клиентами.
Формат JSON:
[
  {{
    "scenario": "Название сценария",
    "client_says": "Что говорит клиент",
    "agent_should": ["Шаг 1", "Шаг 2", "Шаг 3"]
  }}
]"""

        response = await self.chat([
            {"role": "system", "content": "Ты создаёшь примеры диалогов для голосовых агентов."},
            {"role": "user", "content": prompt}
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
        prompt = f"""Отрасль: {industry}
Назначение агента: {agent_purpose}

Сгенерируй список из 5-7 вещей, которые голосовой агент НЕ должен делать.
Учти специфику отрасли и типичные риски.

Формат: JSON массив строк.
["Не делать X", "Не обещать Y", ...]"""

        response = await self.chat([
            {"role": "system", "content": "Ты эксперт по compliance и рискам в автоматизации."},
            {"role": "user", "content": prompt}
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
