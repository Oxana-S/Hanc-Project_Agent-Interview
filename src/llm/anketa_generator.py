"""
LLM-powered генератор структурированной анкеты.

Использует DeepSeek для обогащения частично заполненной FinalAnketa:
1. Анализа сырых ответов интервью
2. Генерации недостающих полей из контекста
3. Создания полностью заполненной анкеты
"""

from typing import Optional

from src.anketa.schema import FinalAnketa
from src.llm.factory import create_llm_client


class LLMAnketaGenerator:
    """
    LLM-powered генератор анкеты.

    Обогащает частично заполненную FinalAnketa через DeepSeek.
    """

    def __init__(self, deepseek_client=None):
        self.client = deepseek_client or create_llm_client()

    async def generate(self, anketa: FinalAnketa) -> FinalAnketa:
        """
        Обогащение FinalAnketa через LLM.

        LLM анализирует все ответы из full_responses и:
        1. Извлекает структурированную информацию
        2. Заполняет недостающие поля из контекста
        3. Генерирует примеры диалогов, ограничения и т.д.

        Args:
            anketa: Частично заполненная FinalAnketa

        Returns:
            FinalAnketa: Обогащённая анкета
        """
        raw_responses = anketa.full_responses or {}

        # Запрашиваем LLM для анализа и заполнения
        llm_result = await self.client.analyze_and_complete_anketa(
            raw_responses=raw_responses,
            pattern=anketa.pattern,
            company_name=anketa.company_name
        )

        # Если LLM вернул пустой результат, возвращаем как есть
        if not llm_result:
            return anketa

        # Мержим результаты LLM в поля anketa
        basic = llm_result.get("basic_info", {})
        clients = llm_result.get("clients_and_services", {})
        agent = llm_result.get("agent_config", {})
        additional = llm_result.get("additional_info", {})
        contact = llm_result.get("contact_info", {})

        # Обновляем базовые поля если пустые
        if not anketa.specialization and basic.get("specialization"):
            anketa.specialization = basic["specialization"]

        if not anketa.business_description and basic.get("business_description"):
            anketa.business_description = basic["business_description"]

        # Обновляем клиентские поля
        if not anketa.services and clients.get("services"):
            services = clients["services"]
            # Преобразуем в List[str] если это List[dict]
            if services and isinstance(services[0], dict):
                anketa.services = [s.get("name", str(s)) for s in services]
            else:
                anketa.services = services

        if not anketa.client_types and clients.get("client_types"):
            client_types = clients["client_types"]
            if client_types and isinstance(client_types[0], dict):
                anketa.client_types = [c.get("type", str(c)) for c in client_types]
            else:
                anketa.client_types = client_types

        if not anketa.typical_questions and clients.get("typical_questions"):
            anketa.typical_questions = clients["typical_questions"]

        # Обновляем конфигурацию агента
        if not anketa.agent_name and agent.get("name"):
            anketa.agent_name = agent["name"]

        if not anketa.voice_tone and agent.get("tone"):
            anketa.voice_tone = agent["tone"]

        if not anketa.working_hours and agent.get("working_hours"):
            anketa.working_hours = agent["working_hours"]

        if not anketa.transfer_conditions and agent.get("transfer_conditions"):
            anketa.transfer_conditions = agent["transfer_conditions"]

        # Обновляем контактную информацию
        if not anketa.contact_name and contact.get("person"):
            anketa.contact_name = contact["person"]

        if not anketa.contact_email and contact.get("email"):
            anketa.contact_email = contact["email"]

        if not anketa.contact_phone and contact.get("phone"):
            anketa.contact_phone = contact["phone"]

        if not anketa.website and contact.get("website"):
            anketa.website = contact["website"]

        # Генерируем constraints если пустые
        if not anketa.constraints and additional.get("restrictions"):
            anketa.constraints = additional["restrictions"]

        if not anketa.compliance_requirements and additional.get("compliance_requirements"):
            anketa.compliance_requirements = additional["compliance_requirements"]

        return anketa
