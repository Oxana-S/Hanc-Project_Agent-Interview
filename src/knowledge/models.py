"""
Knowledge Base Models - Pydantic models for industry profiles.

v1.0: Initial implementation
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PainPoint(BaseModel):
    """Типичная боль клиента в отрасли."""
    description: str
    severity: str = "medium"  # high, medium, low
    solution_hint: Optional[str] = None


class RecommendedFunction(BaseModel):
    """Рекомендуемая функция агента для отрасли."""
    name: str
    priority: str = "medium"  # high, medium, low
    reason: Optional[str] = None


class TypicalIntegration(BaseModel):
    """Типичная интеграция для отрасли."""
    name: str
    examples: List[str] = Field(default_factory=list)
    priority: str = "medium"
    reason: Optional[str] = None


class IndustryFAQ(BaseModel):
    """FAQ специфичный для отрасли."""
    question: str
    answer_template: str


class TypicalObjection(BaseModel):
    """Типичное возражение клиента."""
    objection: str
    response: str


class Learning(BaseModel):
    """Урок, извлечённый из предыдущих тестов."""
    date: str
    insight: str
    source: Optional[str] = None


class IndustryMeta(BaseModel):
    """Метаданные профиля отрасли."""
    id: str
    version: str = "1.0"
    created_at: str = ""
    last_updated: str = ""
    tests_run: int = 0
    avg_validation_score: float = 0.0


class SuccessBenchmarks(BaseModel):
    """Метрики успеха для отрасли."""
    avg_call_duration_seconds: int = 180
    target_automation_rate: float = 0.6
    typical_kpis: List[str] = Field(default_factory=list)


class IndustrySpecifics(BaseModel):
    """Специфика отрасли."""
    compliance: List[str] = Field(default_factory=list)
    tone: List[str] = Field(default_factory=list)
    peak_times: List[str] = Field(default_factory=list)


class IndustryProfile(BaseModel):
    """
    Полный профиль отрасли.

    Загружается из YAML файла в config/industries/{id}.yaml
    """
    # Метаданные
    meta: IndustryMeta

    # Синонимы для определения отрасли
    aliases: List[str] = Field(default_factory=list)

    # Типичные услуги
    typical_services: List[str] = Field(default_factory=list)

    # Боли клиентов
    pain_points: List[PainPoint] = Field(default_factory=list)

    # Рекомендуемые функции агента
    recommended_functions: List[RecommendedFunction] = Field(default_factory=list)

    # Типичные интеграции
    typical_integrations: List[TypicalIntegration] = Field(default_factory=list)

    # FAQ
    industry_faq: List[IndustryFAQ] = Field(default_factory=list)

    # Типичные возражения
    typical_objections: List[TypicalObjection] = Field(default_factory=list)

    # Уроки из тестов
    learnings: List[Learning] = Field(default_factory=list)

    # Метрики успеха
    success_benchmarks: SuccessBenchmarks = Field(default_factory=SuccessBenchmarks)

    # Специфика отрасли
    industry_specifics: Optional[IndustrySpecifics] = None

    @property
    def id(self) -> str:
        """ID отрасли."""
        return self.meta.id

    @property
    def version(self) -> str:
        """Версия профиля."""
        return self.meta.version

    def get_high_priority_functions(self) -> List[RecommendedFunction]:
        """Получить функции с высоким приоритетом."""
        return [f for f in self.recommended_functions if f.priority == "high"]

    def get_high_priority_integrations(self) -> List[TypicalIntegration]:
        """Получить интеграции с высоким приоритетом."""
        return [i for i in self.typical_integrations if i.priority == "high"]

    def get_high_severity_pain_points(self) -> List[PainPoint]:
        """Получить боли с высокой серьёзностью."""
        return [p for p in self.pain_points if p.severity == "high"]

    def to_context_dict(self) -> Dict[str, Any]:
        """
        Преобразовать в словарь для использования в промптах.

        Returns:
            Словарь с ключевыми данными для LLM контекста
        """
        return {
            "industry_id": self.id,
            "typical_services": self.typical_services,
            "pain_points": [
                {"description": p.description, "severity": p.severity}
                for p in self.pain_points
            ],
            "recommended_functions": [
                {"name": f.name, "priority": f.priority, "reason": f.reason}
                for f in self.recommended_functions
            ],
            "typical_integrations": [
                {"name": i.name, "examples": i.examples}
                for i in self.typical_integrations
            ],
            "faq": [
                {"question": f.question, "answer_template": f.answer_template}
                for f in self.industry_faq
            ],
            "success_benchmarks": self.success_benchmarks.model_dump(),
        }


class IndustryIndexEntry(BaseModel):
    """Запись в индексе отраслей."""
    file: str
    name: str
    description: str
    aliases: List[str] = Field(default_factory=list)


class IndustryIndex(BaseModel):
    """Индекс всех отраслей из _index.yaml."""
    meta: Dict[str, Any] = Field(default_factory=dict)
    industries: Dict[str, IndustryIndexEntry] = Field(default_factory=dict)
    usage_stats: Dict[str, Any] = Field(default_factory=dict)
