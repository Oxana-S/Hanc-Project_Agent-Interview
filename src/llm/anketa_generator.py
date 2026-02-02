"""
LLM-powered генератор структурированной анкеты.

Использует DeepSeek для:
1. Анализа сырых ответов интервью
2. Извлечения структурированной информации
3. Генерации недостающих полей из контекста
4. Создания 100% заполненной анкеты
"""

import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field, asdict

from src.models import CompletedAnketa, InterviewPattern
from src.llm.deepseek import DeepSeekClient

# Папка для экспорта (в корне проекта)
OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"


def ensure_output_dir():
    """Создать папку output если не существует."""
    OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class FullAnketa:
    """Полностью заполненная анкета (все поля обязательны)."""

    # Метаданные
    anketa_id: str
    interview_id: str
    pattern: str
    created_at: str
    interview_duration_minutes: float
    quality_score: float

    # 1. Базовая информация
    company_name: str
    industry: str
    specialization: str
    language: str
    agent_purpose: str

    # 2. Клиенты и услуги
    business_type: str
    call_direction: str
    services: list = field(default_factory=list)
    price_policy: str = ""
    client_types: list = field(default_factory=list)
    client_age_group: str = ""
    client_sources: list = field(default_factory=list)
    typical_questions: list = field(default_factory=list)

    # 3. Конфигурация агента
    agent_name: str = "Агент"
    tone: str = ""
    working_hours: dict = field(default_factory=dict)
    transfer_conditions: list = field(default_factory=list)

    # 4. Интеграции
    integrations: dict = field(default_factory=dict)

    # 5. Дополнительная информация
    example_dialogues: list = field(default_factory=list)
    restrictions: list = field(default_factory=list)
    compliance_requirements: list = field(default_factory=list)

    # 6. Контактная информация
    contact_person: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    company_website: str = ""


class LLMAnketaGenerator:
    """LLM-powered генератор анкеты."""

    def __init__(self, deepseek_client: Optional[DeepSeekClient] = None):
        self.client = deepseek_client or DeepSeekClient()

    async def generate(self, interview_data: CompletedAnketa) -> FullAnketa:
        """
        Генерация полной анкеты из данных интервью.

        LLM анализирует все ответы и:
        1. Извлекает структурированную информацию
        2. Заполняет недостающие поля из контекста
        3. Генерирует примеры диалогов, ограничения и т.д.

        Args:
            interview_data: Сырые данные интервью

        Returns:
            FullAnketa: Полностью заполненная анкета
        """
        raw_responses = interview_data.full_responses or {}

        # Запрашиваем LLM для анализа и заполнения
        llm_result = await self.client.analyze_and_complete_anketa(
            raw_responses=raw_responses,
            pattern=interview_data.pattern.value,
            company_name=interview_data.company_name
        )

        # Если LLM вернул пустой результат, используем fallback
        if not llm_result:
            return self._fallback_generation(interview_data)

        # Собираем анкету из результата LLM
        basic = llm_result.get("basic_info", {})
        clients = llm_result.get("clients_and_services", {})
        agent = llm_result.get("agent_config", {})
        integrations = llm_result.get("integrations", {})
        additional = llm_result.get("additional_info", {})
        contact = llm_result.get("contact_info", {})

        # Если примеры диалогов пустые - генерируем
        example_dialogues = additional.get("example_dialogues", [])
        if not example_dialogues:
            services_names = [s.get("name", "") for s in clients.get("services", [])]
            example_dialogues = await self.client.generate_example_dialogues(
                company_name=basic.get("company_name", interview_data.company_name),
                industry=basic.get("industry", interview_data.industry),
                services=services_names,
                agent_purpose=basic.get("agent_purpose", interview_data.agent_purpose)
            )

        # Если ограничения пустые - генерируем
        restrictions = additional.get("restrictions", [])
        if not restrictions:
            restrictions = await self.client.suggest_restrictions(
                industry=basic.get("industry", interview_data.industry),
                agent_purpose=basic.get("agent_purpose", interview_data.agent_purpose)
            )

        return FullAnketa(
            # Метаданные
            anketa_id=interview_data.anketa_id,
            interview_id=interview_data.interview_id,
            pattern=interview_data.pattern.value,
            created_at=interview_data.created_at.isoformat() if interview_data.created_at else datetime.now().isoformat(),
            interview_duration_minutes=interview_data.interview_duration_seconds / 60 if interview_data.interview_duration_seconds else 0,
            quality_score=interview_data.quality_metrics.get("completeness_score", 0.0) if interview_data.quality_metrics else 0.0,

            # 1. Базовая информация
            company_name=basic.get("company_name", interview_data.company_name),
            industry=basic.get("industry", interview_data.industry),
            specialization=basic.get("specialization", ""),
            language=basic.get("language", interview_data.language),
            agent_purpose=basic.get("agent_purpose", interview_data.agent_purpose),

            # 2. Клиенты и услуги
            business_type=clients.get("business_type", ""),
            call_direction=clients.get("call_direction", ""),
            services=clients.get("services", []),
            price_policy=clients.get("price_policy", ""),
            client_types=clients.get("client_types", []),
            client_age_group=clients.get("client_age_group", ""),
            client_sources=clients.get("client_sources", []),
            typical_questions=clients.get("typical_questions", []),

            # 3. Конфигурация агента
            agent_name=agent.get("name", interview_data.agent_name),
            tone=agent.get("tone", interview_data.tone),
            working_hours=agent.get("working_hours", {}),
            transfer_conditions=agent.get("transfer_conditions", []),

            # 4. Интеграции
            integrations=integrations,

            # 5. Дополнительная информация
            example_dialogues=example_dialogues,
            restrictions=restrictions,
            compliance_requirements=additional.get("compliance_requirements", []),

            # 6. Контактная информация
            contact_person=contact.get("person", interview_data.contact_person),
            contact_email=contact.get("email", interview_data.contact_email),
            contact_phone=contact.get("phone", interview_data.contact_phone),
            company_website=contact.get("website", interview_data.company_website or "")
        )

    def _fallback_generation(self, interview_data: CompletedAnketa) -> FullAnketa:
        """Fallback генерация без LLM."""
        return FullAnketa(
            anketa_id=interview_data.anketa_id,
            interview_id=interview_data.interview_id,
            pattern=interview_data.pattern.value,
            created_at=interview_data.created_at.isoformat() if interview_data.created_at else datetime.now().isoformat(),
            interview_duration_minutes=interview_data.interview_duration_seconds / 60 if interview_data.interview_duration_seconds else 0,
            quality_score=0.5,
            company_name=interview_data.company_name,
            industry=interview_data.industry,
            specialization="",
            language=interview_data.language,
            agent_purpose=interview_data.agent_purpose,
            business_type="Не указано",
            call_direction="Не указано",
            agent_name=interview_data.agent_name,
            tone=interview_data.tone,
            contact_person=interview_data.contact_person,
            contact_email=interview_data.contact_email,
            contact_phone=interview_data.contact_phone,
            company_website=interview_data.company_website or ""
        )


def generate_full_anketa_markdown(anketa: FullAnketa) -> str:
    """Генерация Markdown для полной анкеты."""
    md = f"""# Заполненная анкета голосового агента

> **Паттерн:** {anketa.pattern}
> **Дата создания:** {anketa.created_at[:10] if anketa.created_at else 'N/A'}
> **Длительность интервью:** {anketa.interview_duration_minutes:.0f} минут
> **Качество заполнения:** {anketa.quality_score * 100:.0f}%

---

## 1. БАЗОВАЯ ИНФОРМАЦИЯ

### 1.1 Компания
**{anketa.company_name}**

### 1.2 Отрасль
**{anketa.industry}**

{f"Специализация: {anketa.specialization}" if anketa.specialization else ""}

### 1.3 Язык агента
**{anketa.language}**

### 1.4 Основная задача агента
{anketa.agent_purpose}

---

## 2. КЛИЕНТЫ И УСЛУГИ

### 2.1 Тип бизнеса
**{anketa.business_type}**

### 2.2 Направление звонков
**{anketa.call_direction}**

### 2.3 Услуги / продукты
"""

    if anketa.services:
        md += "\n| Услуга | Длительность | Цена |\n"
        md += "|--------|--------------|------|\n"
        for svc in anketa.services:
            if isinstance(svc, dict):
                md += f"| {svc.get('name', '')} | {svc.get('duration', '-')} | {svc.get('price', '-')} |\n"
            else:
                md += f"| {svc} | - | - |\n"
    else:
        md += "*Не указаны*\n"

    md += f"""
### 2.4 Политика цен
{anketa.price_policy or "*Не указана*"}

### 2.5 Клиенты

**Тип клиентов:**
"""
    if anketa.client_types:
        for ct in anketa.client_types:
            if isinstance(ct, dict):
                desc = f" - {ct.get('description', '')}" if ct.get('description') else ""
                pct = f" ({ct.get('percentage', '')})" if ct.get('percentage') else ""
                md += f"- ☑ {ct.get('type', '')}{pct}{desc}\n"
            else:
                md += f"- ☑ {ct}\n"
    else:
        md += "*Не указано*\n"

    if anketa.client_age_group:
        md += f"\n**Возрастная группа:** {anketa.client_age_group}\n"

    if anketa.client_sources:
        md += "\n**Откуда приходят клиенты:**\n"
        for src in anketa.client_sources:
            md += f"- {src}\n"

    if anketa.typical_questions:
        md += "\n**Типичные вопросы клиентов:**\n"
        for i, q in enumerate(anketa.typical_questions, 1):
            md += f"{i}. {q}\n"

    md += f"""
### 2.6 Имя агента
**{anketa.agent_name}**

### 2.7 Тон общения
{anketa.tone}

### 2.8 Рабочие часы
"""
    if anketa.working_hours:
        for key, value in anketa.working_hours.items():
            md += f"- **{key}:** {value}\n"
    else:
        md += "*Не указано*\n"

    md += "\n### 2.9 Переадресация на человека\n\n**Когда переводить:**\n"
    if anketa.transfer_conditions:
        for cond in anketa.transfer_conditions:
            md += f"- {cond}\n"
    else:
        md += "*Не указано*\n"

    md += """
---

## 3. ИНТЕГРАЦИИ
"""
    integrations = anketa.integrations or {}

    # Email
    email = integrations.get("email", {})
    md += "\n### 3.1 EMAIL\n"
    if email.get("enabled"):
        md += "**Включено:** ✅ Да\n\n"
        if email.get("address"):
            md += f"**Email:** {email['address']}\n\n"
        if email.get("purposes"):
            md += "**Назначение:**\n"
            for p in email["purposes"]:
                md += f"- {p}\n"
    else:
        md += "**Включено:** ❌ Нет\n"

    # Calendar
    calendar = integrations.get("calendar", {})
    md += "\n### 3.2 КАЛЕНДАРЬ\n"
    if calendar.get("enabled"):
        md += "**Включено:** ✅ Да\n\n"
        if calendar.get("link"):
            md += f"**Ссылка:** {calendar['link']}\n\n"
        if calendar.get("duration"):
            md += f"**Длительность встречи:** {calendar['duration']}\n\n"
        if calendar.get("purposes"):
            md += "**Что бронируем:**\n"
            for p in calendar["purposes"]:
                md += f"- {p}\n"
    else:
        md += "**Включено:** ❌ Нет\n"

    # Call transfer
    call = integrations.get("call_transfer", {})
    md += "\n### 3.3 ПЕРЕАДРЕСАЦИЯ ЗВОНКА\n"
    if call.get("enabled"):
        md += "**Включено:** ✅ Да\n\n"
        if call.get("phone"):
            md += f"**Номер для переадресации:** {call['phone']}\n\n"
        if call.get("backup_phone"):
            md += f"**Резервный номер:** {call['backup_phone']}\n\n"
        if call.get("conditions"):
            md += "**Когда переадресовывать:**\n"
            for c in call["conditions"]:
                md += f"- {c}\n"
    else:
        md += "**Включено:** ❌ Нет\n"

    # SMS
    sms = integrations.get("sms", {})
    md += "\n### 3.4 SMS\n"
    if sms.get("enabled"):
        md += "**Включено:** ✅ Да\n\n"
        if sms.get("sender_id"):
            md += f"**Sender ID:** {sms['sender_id']}\n\n"
        if sms.get("purposes"):
            md += "**Назначение:**\n"
            for p in sms["purposes"]:
                md += f"- {p}\n"
        if sms.get("reminder_times"):
            md += f"\n**Время напоминаний:** {sms['reminder_times']}\n"
    else:
        md += "**Включено:** ❌ Нет\n"

    # WhatsApp
    wa = integrations.get("whatsapp", {})
    md += "\n### 3.5 WHATSAPP\n"
    if wa.get("enabled"):
        md += "**Включено:** ✅ Да\n\n"
        if wa.get("number"):
            md += f"**Номер:** {wa['number']}\n\n"
        if wa.get("purposes"):
            md += "**Назначение:**\n"
            for p in wa["purposes"]:
                md += f"- {p}\n"
    else:
        md += "**Включено:** ❌ Нет\n"

    md += """
---

## 4. ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ

### 4.1 Примеры диалогов
"""
    if anketa.example_dialogues:
        for i, dialog in enumerate(anketa.example_dialogues, 1):
            if isinstance(dialog, dict):
                md += f"\n**Диалог {i}: {dialog.get('scenario', '')}**\n\n"
                if dialog.get("client_says"):
                    md += f"**Клиент:** {dialog['client_says']}\n\n"
                if dialog.get("agent_should"):
                    md += "**Агент должен:**\n"
                    for step in dialog["agent_should"]:
                        md += f"- {step}\n"
            else:
                md += f"\n**Диалог {i}:**\n{dialog}\n"
    else:
        md += "*Примеры не предоставлены*\n"

    md += "\n### 4.2 Что агент НЕ должен делать\n"
    if anketa.restrictions:
        for r in anketa.restrictions:
            md += f"- ❌ {r}\n"
    else:
        md += "*Не указано*\n"

    md += "\n### 4.3 Требования compliance\n"
    if anketa.compliance_requirements:
        for req in anketa.compliance_requirements:
            md += f"- ☑ {req}\n"
    else:
        md += "*Не указано*\n"

    md += f"""
### 4.4 Контактная информация

| Поле | Значение |
|------|----------|
| **Контактное лицо** | {anketa.contact_person} |
| **Email** | {anketa.contact_email or "Не указан"} |
| **Телефон** | {anketa.contact_phone or "Не указан"} |
| **Сайт компании** | {anketa.company_website or "Не указан"} |

---

## МЕТРИКИ КАЧЕСТВА ЗАПОЛНЕНИЯ

| Метрика | Значение |
|---------|----------|
| Completeness Score | {anketa.quality_score * 100:.0f}% |
| Длительность интервью | {anketa.interview_duration_minutes:.0f} минут |
| Услуг описано | {len(anketa.services)} |
| Примеров диалогов | {len(anketa.example_dialogues)} |
| Ограничений | {len(anketa.restrictions)} |

---

**✅ Анкета полностью заполнена и готова для создания голосового агента**
"""

    return md


async def export_full_anketa(
    interview_data: CompletedAnketa,
    filename: Optional[str] = None
) -> dict:
    """
    Генерация и экспорт полной анкеты с использованием LLM.

    Args:
        interview_data: Данные интервью
        filename: Базовое имя файла (без расширения)

    Returns:
        Словарь с путями к файлам и объектом анкеты
    """
    ensure_output_dir()

    # Генерируем полную анкету через LLM
    generator = LLMAnketaGenerator()
    anketa = await generator.generate(interview_data)

    # Имя файла
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"full_anketa_{anketa.pattern}_{timestamp}"

    # Экспорт в JSON
    json_path = OUTPUT_DIR / f"{filename}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(anketa), f, ensure_ascii=False, indent=2)

    # Экспорт в Markdown
    md_path = OUTPUT_DIR / f"{filename}.md"
    md_content = generate_full_anketa_markdown(anketa)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "anketa": anketa
    }
