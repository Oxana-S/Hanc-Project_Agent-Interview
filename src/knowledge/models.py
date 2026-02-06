"""
Knowledge Base Models - Pydantic models for industry profiles.

v1.0: Initial implementation
v2.0: Multi-region support, sales scripts, competitors, pricing context
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============ NEW v2.0 MODELS ============

class SalesScript(BaseModel):
    """Sales script for specific situations."""
    trigger: str  # Machine-readable trigger (e.g., "price_question")
    situation: str  # Human description of when to use
    script: str  # The actual script text
    goal: str  # What we're trying to achieve
    effectiveness: float = 0.0  # Success rate from learnings (0.0-1.0)


class Competitor(BaseModel):
    """Competitor analysis."""
    name: str
    website: Optional[str] = None
    positioning: str  # How they position themselves
    market_share: Optional[str] = None  # e.g., "~15% DACH"
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    our_differentiation: Optional[str] = None  # How we're better


class ROIExample(BaseModel):
    """ROI calculation example."""
    scenario: str  # e.g., "1 FTE savings"
    monthly_cost: float
    monthly_savings: float
    payback_months: int


class PricingContext(BaseModel):
    """Pricing hints and context."""
    currency: str = "EUR"
    typical_budget_range: List[float] = Field(default_factory=lambda: [0, 0])  # [min, max]
    entry_point: float = 0.0
    enterprise_threshold: float = 0.0
    roi_examples: List[ROIExample] = Field(default_factory=list)
    value_anchors: List[str] = Field(default_factory=list)  # Comparison points


class Seasonality(BaseModel):
    """Seasonal patterns."""
    high: List[str] = Field(default_factory=list)  # High seasons
    low: List[str] = Field(default_factory=list)  # Low seasons


class MarketContext(BaseModel):
    """Market information."""
    market_size: Optional[str] = None  # e.g., "€2.3B DACH automotive"
    growth_rate: Optional[str] = None  # e.g., "8% YoY"
    key_trends: List[str] = Field(default_factory=list)
    seasonality: Optional[Seasonality] = None


# ============ ORIGINAL MODELS ============


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
    # v2.0: Regional support
    region: Optional[str] = None  # e.g., "eu", "na", "latam", "mena", "sea", "ru"
    country: Optional[str] = None  # e.g., "de", "us", "br"
    language: str = "ru"  # Primary language
    languages: List[str] = Field(default_factory=list)  # Supported languages
    phone_codes: List[str] = Field(default_factory=list)  # e.g., ["+49"]
    currency: str = "RUB"
    timezone: Optional[str] = None  # e.g., "Europe/Berlin"


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

    # v2.0: Sales and market context
    sales_scripts: List[SalesScript] = Field(default_factory=list)
    competitors: List[Competitor] = Field(default_factory=list)
    pricing_context: Optional[PricingContext] = None
    market_context: Optional[MarketContext] = None

    # v2.0: Inheritance support
    _extends: Optional[str] = None  # Base profile path for inheritance

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

    def get_script_for_trigger(self, trigger: str) -> Optional[SalesScript]:
        """Get sales script by trigger."""
        for script in self.sales_scripts:
            if script.trigger == trigger:
                return script
        return None

    def get_competitor_by_name(self, name: str) -> Optional[Competitor]:
        """Get competitor by name."""
        for comp in self.competitors:
            if comp.name.lower() == name.lower():
                return comp
        return None

    @property
    def region(self) -> Optional[str]:
        """Region code."""
        return self.meta.region

    @property
    def country(self) -> Optional[str]:
        """Country code."""
        return self.meta.country

    @property
    def language(self) -> str:
        """Primary language."""
        return self.meta.language

    @property
    def currency(self) -> str:
        """Currency code."""
        return self.meta.currency

    def to_context_dict(self) -> Dict[str, Any]:
        """
        Преобразовать в словарь для использования в промптах.

        Returns:
            Словарь с ключевыми данными для LLM контекста
        """
        result = {
            "industry_id": self.id,
            "region": self.region,
            "country": self.country,
            "language": self.language,
            "currency": self.currency,
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

        # v2.0 fields
        if self.sales_scripts:
            result["sales_scripts"] = [
                {"trigger": s.trigger, "script": s.script, "goal": s.goal}
                for s in self.sales_scripts
            ]

        if self.competitors:
            result["competitors"] = [
                {
                    "name": c.name,
                    "positioning": c.positioning,
                    "weaknesses": c.weaknesses,
                    "our_differentiation": c.our_differentiation,
                }
                for c in self.competitors
            ]

        if self.pricing_context:
            result["pricing_context"] = {
                "currency": self.pricing_context.currency,
                "typical_budget_range": self.pricing_context.typical_budget_range,
                "entry_point": self.pricing_context.entry_point,
                "value_anchors": self.pricing_context.value_anchors,
            }

        if self.market_context:
            result["market_context"] = {
                "market_size": self.market_context.market_size,
                "key_trends": self.market_context.key_trends,
            }

        return result


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
