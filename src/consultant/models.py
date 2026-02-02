"""
Consultant Models.

Модели данных для фаз ANALYSIS и PROPOSAL.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PainPoint(BaseModel):
    """Выявленная боль/проблема клиента."""

    description: str
    severity: str = "medium"  # low, medium, high, critical
    source: str = "dialogue"  # dialogue, research, website
    evidence: Optional[str] = None  # Цитата или факт


class Opportunity(BaseModel):
    """Возможность для автоматизации."""

    description: str
    addresses_pain: Optional[str] = None  # ID боли, которую решает
    expected_impact: Optional[str] = None
    confidence: float = 0.7


class BusinessAnalysis(BaseModel):
    """Результат анализа бизнеса (фаза ANALYSIS)."""

    # Профиль бизнеса
    company_name: Optional[str] = None
    industry: Optional[str] = None
    specialization: Optional[str] = None
    business_scale: str = "unknown"  # small, medium, large
    client_type: str = "unknown"  # B2B, B2C, mixed

    # Боли и возможности
    pain_points: List[PainPoint] = Field(default_factory=list)
    opportunities: List[Opportunity] = Field(default_factory=list)

    # Ограничения
    constraints: List[str] = Field(default_factory=list)

    # Из исследования
    industry_insights: List[str] = Field(default_factory=list)
    similar_cases: List[Dict[str, Any]] = Field(default_factory=list)

    # Метаданные
    confidence_score: float = 0.0
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_confirmed: bool = False

    def get_top_pains(self, n: int = 3) -> List[PainPoint]:
        """Получить топ-N болей по severity."""
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_pains = sorted(
            self.pain_points,
            key=lambda p: severity_order.get(p.severity, 99)
        )
        return sorted_pains[:n]

    def to_summary_text(self) -> str:
        """Конвертировать в текст для промпта."""
        lines = []

        if self.company_name:
            lines.append(f"Компания: {self.company_name}")
        if self.industry:
            lines.append(f"Отрасль: {self.industry}")
        if self.specialization:
            lines.append(f"Специализация: {self.specialization}")

        if self.pain_points:
            lines.append("\nГлавные боли:")
            for i, pain in enumerate(self.get_top_pains(5), 1):
                lines.append(f"  {i}. {pain.description}")

        if self.opportunities:
            lines.append("\nВозможности:")
            for opp in self.opportunities[:3]:
                lines.append(f"  - {opp.description}")

        return "\n".join(lines)


class ProposedFunction(BaseModel):
    """Предлагаемая функция агента."""

    name: str
    description: str
    reason: str  # Почему предлагаем (связь с болью)
    is_main: bool = False
    addresses_pain: Optional[str] = None


class ProposedIntegration(BaseModel):
    """Предлагаемая интеграция."""

    name: str  # email, calendar, whatsapp, etc.
    needed: bool
    reason: str
    details: Optional[str] = None


class ProposedSolution(BaseModel):
    """Предложенное решение (фаза PROPOSAL)."""

    # Основная функция
    main_function: ProposedFunction

    # Дополнительные функции
    additional_functions: List[ProposedFunction] = Field(default_factory=list)

    # Интеграции
    integrations: List[ProposedIntegration] = Field(default_factory=list)

    # Ожидаемый результат
    expected_results: Optional[str] = None

    # Метаданные
    based_on_analysis: bool = True
    user_confirmed: bool = False
    modifications: List[str] = Field(default_factory=list)

    def to_proposal_text(self) -> str:
        """Конвертировать в текст предложения."""
        lines = [
            "На основе анализа, вот что рекомендую:",
            "",
            f"**1. ОСНОВНАЯ ФУНКЦИЯ: {self.main_function.name}**",
            f"Почему: {self.main_function.reason}",
            f"Описание: {self.main_function.description}",
        ]

        if self.additional_functions:
            lines.append("")
            lines.append("**2. ДОПОЛНИТЕЛЬНО:**")
            for func in self.additional_functions:
                lines.append(f"- {func.name} — {func.reason}")

        if self.integrations:
            lines.append("")
            lines.append("**3. ИНТЕГРАЦИИ:**")
            for intg in self.integrations:
                icon = "✓" if intg.needed else "✗"
                lines.append(f"{icon} {intg.name} — {intg.reason}")

        if self.expected_results:
            lines.append("")
            lines.append("**4. ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:**")
            lines.append(self.expected_results)

        lines.append("")
        lines.append("Что думаете? Хотите что-то изменить или добавить?")

        return "\n".join(lines)

    def get_needed_integrations(self) -> List[ProposedIntegration]:
        """Получить список нужных интеграций."""
        return [i for i in self.integrations if i.needed]
