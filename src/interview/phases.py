"""
Модели и Enum'ы для Maximum Interview Mode.

Три фазы интервью:
1. DISCOVERY - свободный диалог, изучение бизнеса
2. STRUCTURED - целенаправленный сбор недостающих данных
3. SYNTHESIS - генерация полной анкеты
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class InterviewPhase(str, Enum):
    """Фаза интервью в Maximum режиме."""
    DISCOVERY = "discovery"      # Свободный диалог, изучение бизнеса
    STRUCTURED = "structured"    # Целенаправленный сбор данных
    SYNTHESIS = "synthesis"      # Финальная генерация анкеты


class FieldStatus(str, Enum):
    """Статус заполнения поля анкеты."""
    EMPTY = "empty"              # Не заполнено
    PARTIAL = "partial"          # Частично заполнено
    COMPLETE = "complete"        # Полностью заполнено
    AI_SUGGESTED = "ai_suggested"  # AI предложил значение (требует подтверждения)


class FieldPriority(str, Enum):
    """Приоритет поля."""
    REQUIRED = "required"        # Обязательное
    IMPORTANT = "important"      # Важное, но не критичное
    OPTIONAL = "optional"        # Опциональное


class AnketaField(BaseModel):
    """Поле анкеты с метаданными."""
    field_id: str
    name: str                      # Название поля (company_name, industry, etc.)
    display_name: str              # Отображаемое название
    description: str               # Описание для AI
    priority: FieldPriority
    status: FieldStatus = FieldStatus.EMPTY
    value: Any = None
    ai_suggested_value: Any = None  # Значение, предложенное AI
    source: Optional[str] = None    # Откуда получено (discovery/structured/ai)
    confidence: float = 0.0         # Уверенность в значении (0-1)
    examples: List[str] = []        # Примеры значений


# Определение всех полей анкеты
ANKETA_FIELDS = {
    # Базовая информация
    "company_name": AnketaField(
        field_id="company_name",
        name="company_name",
        display_name="Название компании",
        description="Официальное или используемое название компании",
        priority=FieldPriority.REQUIRED,
        examples=["ООО Рога и Копыта", "TechSolutions", "Клиника Здоровье"]
    ),
    "industry": AnketaField(
        field_id="industry",
        name="industry",
        display_name="Отрасль",
        description="Сфера деятельности компании",
        priority=FieldPriority.REQUIRED,
        examples=["IT / Разработка", "Медицина", "Недвижимость", "Образование"]
    ),
    "specialization": AnketaField(
        field_id="specialization",
        name="specialization",
        display_name="Специализация",
        description="Конкретная специализация в отрасли",
        priority=FieldPriority.IMPORTANT,
        examples=["Веб-разработка", "Стоматология", "Коммерческая недвижимость"]
    ),
    "business_description": AnketaField(
        field_id="business_description",
        name="business_description",
        display_name="Описание бизнеса",
        description="Краткое описание чем занимается компания",
        priority=FieldPriority.REQUIRED,
        examples=["Разрабатываем мобильные приложения для бизнеса"]
    ),
    "language": AnketaField(
        field_id="language",
        name="language",
        display_name="Язык общения",
        description="На каком языке агент должен общаться",
        priority=FieldPriority.REQUIRED,
        examples=["Русский", "English", "Русский и English"]
    ),

    # Назначение агента
    "agent_purpose": AnketaField(
        field_id="agent_purpose",
        name="agent_purpose",
        display_name="Назначение агента",
        description="Основные задачи голосового агента",
        priority=FieldPriority.REQUIRED,
        examples=["Приём входящих звонков, консультации по услугам, запись на приём"]
    ),
    "agent_goals": AnketaField(
        field_id="agent_goals",
        name="agent_goals",
        display_name="Цели агента",
        description="Конкретные цели, которые должен достигать агент",
        priority=FieldPriority.IMPORTANT,
        examples=["Снизить нагрузку на операторов", "Увеличить конверсию", "Ускорить обработку заявок"]
    ),
    "call_direction": AnketaField(
        field_id="call_direction",
        name="call_direction",
        display_name="Направление звонков",
        description="Входящие, исходящие или оба направления",
        priority=FieldPriority.REQUIRED,
        examples=["Входящие", "Исходящие", "Оба направления"]
    ),

    # Услуги и клиенты
    "services": AnketaField(
        field_id="services",
        name="services",
        display_name="Услуги/продукты",
        description="Список услуг или продуктов компании с ценами",
        priority=FieldPriority.REQUIRED,
        examples=["Консультация - 3000 руб", "Разработка сайта - от 100000 руб"]
    ),
    "client_types": AnketaField(
        field_id="client_types",
        name="client_types",
        display_name="Типы клиентов",
        description="B2B, B2C, возрастные группы, профиль клиента",
        priority=FieldPriority.IMPORTANT,
        examples=["B2B - малый бизнес", "B2C - женщины 25-45 лет"]
    ),
    "typical_questions": AnketaField(
        field_id="typical_questions",
        name="typical_questions",
        display_name="Типичные вопросы",
        description="Частые вопросы, которые задают клиенты",
        priority=FieldPriority.IMPORTANT,
        examples=["Сколько стоит?", "Как записаться?", "Есть ли скидки?"]
    ),
    "current_problems": AnketaField(
        field_id="current_problems",
        name="current_problems",
        display_name="Текущие проблемы",
        description="Проблемы, которые должен решить агент",
        priority=FieldPriority.IMPORTANT,
        examples=["Много пропущенных звонков", "Долгое время ответа"]
    ),

    # Конфигурация агента
    "agent_name": AnketaField(
        field_id="agent_name",
        name="agent_name",
        display_name="Имя агента",
        description="Как агент должен представляться",
        priority=FieldPriority.IMPORTANT,
        examples=["Алекс", "Анна", "Помощник компании"]
    ),
    "tone": AnketaField(
        field_id="tone",
        name="tone",
        display_name="Тон общения",
        description="Стиль общения агента",
        priority=FieldPriority.IMPORTANT,
        examples=["Дружелюбный и профессиональный", "Формальный", "Неформальный"]
    ),
    "working_hours": AnketaField(
        field_id="working_hours",
        name="working_hours",
        display_name="Часы работы",
        description="Когда агент должен работать",
        priority=FieldPriority.OPTIONAL,
        examples=["Пн-Пт 9:00-18:00", "Круглосуточно"]
    ),
    "transfer_conditions": AnketaField(
        field_id="transfer_conditions",
        name="transfer_conditions",
        display_name="Условия переадресации",
        description="Когда агент должен переводить на человека",
        priority=FieldPriority.IMPORTANT,
        examples=["При жалобах", "По запросу клиента", "При сложных вопросах"]
    ),

    # Интеграции
    "integrations": AnketaField(
        field_id="integrations",
        name="integrations",
        display_name="Интеграции",
        description="Какие интеграции нужны (email, календарь, CRM и т.д.)",
        priority=FieldPriority.OPTIONAL,
        examples=["Google Calendar", "Email уведомления", "Интеграция с 1С"]
    ),

    # Ограничения
    "restrictions": AnketaField(
        field_id="restrictions",
        name="restrictions",
        display_name="Ограничения",
        description="Что агент НЕ должен делать",
        priority=FieldPriority.IMPORTANT,
        examples=["Не давать медицинских советов", "Не обещать скидки без согласования"]
    ),

    # Контакты
    "contact_phone": AnketaField(
        field_id="contact_phone",
        name="contact_phone",
        display_name="Телефон для переадресации",
        description="Номер для перевода звонков на человека",
        priority=FieldPriority.OPTIONAL,
        examples=["+7 495 123-45-67"]
    ),
    "contact_email": AnketaField(
        field_id="contact_email",
        name="contact_email",
        display_name="Email",
        description="Email для уведомлений",
        priority=FieldPriority.OPTIONAL,
        examples=["info@company.ru"]
    ),
}


class CollectedInfo(BaseModel):
    """Собранная информация во время интервью."""
    fields: Dict[str, AnketaField] = {}
    dialogue_history: List[Dict[str, str]] = []
    discovery_summary: str = ""
    decisions_made: List[str] = []

    def __init__(self, **data):
        super().__init__(**data)
        # Инициализируем поля из ANKETA_FIELDS
        if not self.fields:
            self.fields = {k: v.model_copy() for k, v in ANKETA_FIELDS.items()}

    def update_field(self, field_id: str, value: Any, source: str = "user", confidence: float = 1.0):
        """Обновить значение поля."""
        if field_id in self.fields:
            field = self.fields[field_id]
            field.value = value
            field.source = source
            field.confidence = confidence

            # Определяем статус
            if value:
                if isinstance(value, list) and len(value) > 0:
                    field.status = FieldStatus.COMPLETE
                elif isinstance(value, str) and len(value) > 10:
                    field.status = FieldStatus.COMPLETE
                else:
                    field.status = FieldStatus.PARTIAL
            else:
                field.status = FieldStatus.EMPTY

    def set_ai_suggestion(self, field_id: str, value: Any, confidence: float = 0.7):
        """Установить предложение AI для поля."""
        if field_id in self.fields:
            field = self.fields[field_id]
            field.ai_suggested_value = value
            field.status = FieldStatus.AI_SUGGESTED
            field.confidence = confidence

    def get_missing_required_fields(self) -> List[AnketaField]:
        """Получить список незаполненных обязательных полей."""
        return [
            f for f in self.fields.values()
            if f.priority == FieldPriority.REQUIRED and f.status in [FieldStatus.EMPTY, FieldStatus.PARTIAL]
        ]

    def get_missing_important_fields(self) -> List[AnketaField]:
        """Получить список незаполненных важных полей."""
        return [
            f for f in self.fields.values()
            if f.priority == FieldPriority.IMPORTANT and f.status in [FieldStatus.EMPTY, FieldStatus.PARTIAL]
        ]

    def get_completion_stats(self) -> Dict[str, Any]:
        """Получить статистику заполнения."""
        total = len(self.fields)
        complete = sum(1 for f in self.fields.values() if f.status == FieldStatus.COMPLETE)
        partial = sum(1 for f in self.fields.values() if f.status == FieldStatus.PARTIAL)
        ai_suggested = sum(1 for f in self.fields.values() if f.status == FieldStatus.AI_SUGGESTED)

        required_total = sum(1 for f in self.fields.values() if f.priority == FieldPriority.REQUIRED)
        required_filled = sum(1 for f in self.fields.values()
                             if f.priority == FieldPriority.REQUIRED
                             and f.status in [FieldStatus.COMPLETE, FieldStatus.AI_SUGGESTED])

        return {
            "total": total,
            "complete": complete,
            "partial": partial,
            "ai_suggested": ai_suggested,
            "empty": total - complete - partial - ai_suggested,
            "completion_percentage": (complete + partial * 0.5 + ai_suggested * 0.8) / total * 100,
            "required_total": required_total,
            "required_filled": required_filled,
            "required_percentage": required_filled / required_total * 100 if required_total > 0 else 0
        }

    def to_anketa_dict(self) -> Dict[str, Any]:
        """Конвертировать в словарь для генерации анкеты."""
        result = {}
        for field_id, field in self.fields.items():
            # Берём value, или ai_suggested_value если value пустое
            value = field.value if field.value else field.ai_suggested_value
            if value:
                result[field_id] = value
        return result


class PhaseTransition(BaseModel):
    """Информация о переходе между фазами."""
    from_phase: InterviewPhase
    to_phase: InterviewPhase
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reason: str
    stats_at_transition: Dict[str, Any] = {}
