"""
AnketaGenerator - generates documents from FinalAnketa.

Supports:
- Markdown format (human-readable)
- JSON format (machine-readable)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import structlog

from src.anketa.schema import (
    FinalAnketa, AgentFunction, Integration,
    FAQItem, ObjectionHandler, DialogueExample, FinancialMetric,
    Competitor, MarketInsight, EscalationRule, KPIMetric,
    ChecklistItem, AIRecommendation, TargetAudienceSegment
)

logger = structlog.get_logger("anketa")


class AnketaGenerator:
    """Generates documents from FinalAnketa."""

    def __init__(self, output_dir: str = "output/anketas"):
        """
        Initialize generator.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_markdown(self, anketa: FinalAnketa, filename: Optional[str] = None) -> Path:
        """
        Generate Markdown document from anketa.

        Args:
            anketa: Populated FinalAnketa instance
            filename: Optional custom filename

        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._safe_filename(anketa.company_name)
            filename = f"{safe_name}_{timestamp}.md"

        content = self._render_markdown(anketa)
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info("Markdown anketa saved", path=str(filepath))
        return filepath

    def to_json(self, anketa: FinalAnketa, filename: Optional[str] = None) -> Path:
        """
        Save anketa as JSON file.

        Args:
            anketa: Populated FinalAnketa instance
            filename: Optional custom filename

        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._safe_filename(anketa.company_name)
            filename = f"{safe_name}_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(anketa.model_dump_json(indent=2, ensure_ascii=False))

        logger.info("JSON anketa saved", path=str(filepath))
        return filepath

    def _safe_filename(self, name: str) -> str:
        """Convert name to safe filename."""
        if not name:
            return "unnamed"
        # Replace spaces and special chars
        safe = name.lower().replace(" ", "_")
        # Keep only alphanumeric and underscore
        safe = "".join(c for c in safe if c.isalnum() or c == "_")
        return safe[:50] if safe else "unnamed"

    @staticmethod
    def render_markdown(anketa: FinalAnketa) -> str:
        """
        Generate Markdown content from anketa (static version).

        Use this when you don't need to save files, just generate content.

        Args:
            anketa: Populated FinalAnketa instance

        Returns:
            Markdown content as string
        """
        generator = AnketaGenerator.__new__(AnketaGenerator)
        return generator._render_markdown(anketa)

    def _render_markdown(self, anketa: FinalAnketa) -> str:
        """Render Markdown content from anketa v2.0."""

        completion_rate = anketa.completion_rate()
        duration_min = anketa.consultation_duration_seconds / 60

        sections = [
            # Header
            f"""# Анкета: {anketa.company_name}

**Дата создания:** {anketa.created_at.strftime('%Y-%m-%d %H:%M')}
**Версия:** {anketa.anketa_version}
**Длительность консультации:** {duration_min:.1f} мин
**Заполненность:** {completion_rate:.0f}%

---

## 1. Информация о компании

| Поле | Значение |
|------|----------|
| Компания | {anketa.company_name} |
| Отрасль | {anketa.industry} |
| Специализация | {anketa.specialization or '—'} |
| Сайт | {anketa.website or '—'} |
| Контактное лицо | {anketa.contact_name or '—'} |
| Должность | {anketa.contact_role or '—'} |

### Описание бизнеса

{anketa.business_description or '*Не указано*'}

### Услуги / Продукты

{self._render_list(anketa.services)}

### Типы клиентов

{self._render_list(anketa.client_types)}""",

            # Business Context
            f"""---

## 2. Бизнес-контекст

### Текущие проблемы

{self._render_list(anketa.current_problems)}

### Цели автоматизации

{self._render_list(anketa.business_goals)}

### Ограничения

{self._render_list(anketa.constraints)}""",

            # Voice Agent
            f"""---

## 3. Голосовой агент

| Параметр | Значение |
|----------|----------|
| Имя агента | {anketa.agent_name or '—'} |
| Назначение | {anketa.agent_purpose or '—'} |
| Голос | {anketa.voice_gender}, {anketa.voice_tone} |
| Язык | {anketa.language} |
| Тип звонков | {self._format_call_direction(anketa.call_direction)} |

### Основная функция

{self._render_main_function(anketa.main_function)}

### Дополнительные функции

{self._render_functions(anketa.additional_functions)}""",

            # All Functions
            f"""---

## 4. Все функции агента

{self._render_functions(anketa.agent_functions)}""",

            # Integrations
            f"""---

## 5. Интеграции

{self._render_integrations(anketa.integrations)}""",

            # FAQ with answers (v2.0)
            f"""---

## 6. FAQ с ответами

{self._render_faq_items(anketa.faq_items)}""",

            # Objection Handling (v2.0)
            f"""---

## 7. Работа с возражениями

{self._render_objection_handlers(anketa.objection_handlers)}""",

            # Sample Dialogue (v2.0)
            f"""---

## 8. Пример диалога

{self._render_sample_dialogue(anketa.sample_dialogue)}""",

            # Financial Model (v2.0)
            f"""---

## 9. Финансовая модель

{self._render_financial_metrics(anketa.financial_metrics)}""",

            # Market Analysis (v2.0)
            f"""---

## 10. Анализ рынка

### Конкуренты

{self._render_competitors(anketa.competitors)}

### Рыночные инсайты

{self._render_market_insights(anketa.market_insights)}

### Конкурентные преимущества клиента

{self._render_list(anketa.competitive_advantages)}""",

            # Target Segments (v2.0)
            f"""---

## 11. Целевые сегменты

{self._render_target_segments(anketa.target_segments)}""",

            # Escalation Rules (v2.0)
            f"""---

## 12. Правила эскалации

{self._render_escalation_rules(anketa.escalation_rules)}""",

            # Success KPIs (v2.0)
            f"""---

## 13. KPI и метрики успеха

{self._render_success_kpis(anketa.success_kpis)}""",

            # Launch Checklist (v2.0)
            f"""---

## 14. Чеклист запуска

{self._render_launch_checklist(anketa.launch_checklist)}""",

            # AI Recommendations (v2.0)
            f"""---

## 15. Рекомендации AI-эксперта

{self._render_ai_recommendations(anketa.ai_recommendations)}""",

            # Tone of Voice (v2.0)
            f"""---

## 16. Тон коммуникации

{self._render_tone_of_voice(anketa.tone_of_voice)}""",

            # Error Handling Scripts (v2.0)
            f"""---

## 17. Скрипты обработки ошибок

{self._render_error_handling_scripts(anketa.error_handling_scripts)}""",

            # Follow-up Sequence (v2.0)
            f"""---

## 18. Последовательность follow-up

{self._render_list(anketa.follow_up_sequence)}""",

            # Metadata
            f"""---

## Метаданные

- **Создано:** {anketa.created_at.strftime('%Y-%m-%d %H:%M:%S')}
- **Версия анкеты:** {anketa.anketa_version}
- **Длительность консультации:** {anketa.consultation_duration_seconds:.0f} сек
- **Заполненность анкеты:** {completion_rate:.0f}%

---

*Сгенерировано автоматически системой ConsultantInterviewer v2.0*
"""
        ]

        return "\n".join(sections)

    def _render_list(self, items: List[str]) -> str:
        """Render list as markdown bullets."""
        if not items:
            return "*Не указано*"
        return "\n".join(f"- {item}" for item in items if item)

    def _render_main_function(self, func: Optional[AgentFunction]) -> str:
        """Render main function block."""
        if not func:
            return "*Не определена*"

        return f"""**{func.name}**

{func.description}

*Приоритет: {func.priority}*"""

    def _render_functions(self, functions: List[AgentFunction]) -> str:
        """Render list of functions."""
        if not functions:
            return "*Не указано*"

        lines = []
        for i, func in enumerate(functions, 1):
            lines.append(f"### {i}. {func.name}")
            lines.append("")
            lines.append(func.description)
            lines.append("")
            lines.append(f"*Приоритет: {func.priority}*")
            lines.append("")

        return "\n".join(lines)

    def _render_integrations(self, integrations: List[Integration]) -> str:
        """Render integrations as table."""
        if not integrations:
            return "*Интеграции не требуются*"

        lines = [
            "| Система | Назначение | Обязательно |",
            "|---------|------------|-------------|"
        ]

        for intg in integrations:
            required = "Да" if intg.required else "Нет"
            lines.append(f"| {intg.name} | {intg.purpose} | {required} |")

        return "\n".join(lines)

    def _format_call_direction(self, direction: str) -> str:
        """Format call direction for display."""
        mapping = {
            "inbound": "Входящие",
            "outbound": "Исходящие",
            "both": "Входящие и исходящие"
        }
        return mapping.get(direction, direction)

    # =========================================================================
    # V2.0 RENDERING METHODS
    # =========================================================================

    def _render_faq_items(self, items: List[FAQItem]) -> str:
        """Render FAQ items with answers."""
        if not items:
            return "*FAQ не сгенерирован*"

        lines = []
        for i, item in enumerate(items, 1):
            category_badge = f"[{item.category}]" if item.category else ""
            lines.append(f"### {i}. {item.question} {category_badge}")
            lines.append("")
            lines.append(f"> {item.answer}")
            lines.append("")

        return "\n".join(lines)

    def _render_objection_handlers(self, handlers: List[ObjectionHandler]) -> str:
        """Render objection handling scripts."""
        if not handlers:
            return "*Возражения не проработаны*"

        lines = []
        for i, handler in enumerate(handlers, 1):
            lines.append(f"### {i}. «{handler.objection}»")
            lines.append("")
            lines.append(f"**Ответ:** {handler.response}")
            if handler.follow_up:
                lines.append(f"")
                lines.append(f"**Далее:** {handler.follow_up}")
            lines.append("")

        return "\n".join(lines)

    def _render_sample_dialogue(self, dialogue: List[DialogueExample]) -> str:
        """Render sample dialogue."""
        if not dialogue:
            return "*Пример диалога не сгенерирован*"

        lines = []
        for turn in dialogue:
            role_label = "🤖 Агент" if turn.role == "bot" else "👤 Клиент"
            intent_badge = f" *({turn.intent})*" if turn.intent else ""
            lines.append(f"**{role_label}:** {turn.message}{intent_badge}")
            lines.append("")

        return "\n".join(lines)

    def _render_financial_metrics(self, metrics: List[FinancialMetric]) -> str:
        """Render financial metrics as table."""
        if not metrics:
            return "*Финансовые метрики не указаны*"

        lines = [
            "| Метрика | Значение | Источник | Примечание |",
            "|---------|----------|----------|------------|"
        ]

        for metric in metrics:
            note = metric.note or "—"
            source_label = {
                "client": "Клиент",
                "ai_benchmark": "AI-бенчмарк",
                "calculated": "Расчёт"
            }.get(metric.source, metric.source)
            lines.append(f"| {metric.name} | {metric.value} | {source_label} | {note} |")

        return "\n".join(lines)

    def _render_competitors(self, competitors: List[Competitor]) -> str:
        """Render competitors analysis."""
        if not competitors:
            return "*Конкуренты не определены*"

        lines = []
        for comp in competitors:
            lines.append(f"#### {comp.name}")
            if comp.price_range:
                lines.append(f"*Цены: {comp.price_range}*")
            lines.append("")

            if comp.strengths:
                lines.append("**Сильные стороны:**")
                for s in comp.strengths:
                    lines.append(f"- ✅ {s}")
                lines.append("")

            if comp.weaknesses:
                lines.append("**Слабые стороны:**")
                for w in comp.weaknesses:
                    lines.append(f"- ❌ {w}")
                lines.append("")

        return "\n".join(lines)

    def _render_market_insights(self, insights: List[MarketInsight]) -> str:
        """Render market insights."""
        if not insights:
            return "*Инсайты не сгенерированы*"

        lines = []
        for insight in insights:
            relevance_icon = {"high": "🔥", "medium": "📊", "low": "📝"}.get(insight.relevance, "📊")
            lines.append(f"- {relevance_icon} {insight.insight}")

        return "\n".join(lines)

    def _render_target_segments(self, segments: List[TargetAudienceSegment]) -> str:
        """Render target audience segments."""
        if not segments:
            return "*Сегменты не определены*"

        lines = []
        for i, seg in enumerate(segments, 1):
            lines.append(f"### {i}. {seg.name}")
            lines.append("")
            lines.append(seg.description)
            lines.append("")

            if seg.pain_points:
                lines.append("**Болевые точки:**")
                for p in seg.pain_points:
                    lines.append(f"- 😓 {p}")
                lines.append("")

            if seg.triggers:
                lines.append("**Триггеры к действию:**")
                for t in seg.triggers:
                    lines.append(f"- ⚡ {t}")
                lines.append("")

        return "\n".join(lines)

    def _render_escalation_rules(self, rules: List[EscalationRule]) -> str:
        """Render escalation rules as table."""
        if not rules:
            return "*Правила эскалации не определены*"

        lines = [
            "| Триггер | Срочность | Действие |",
            "|---------|-----------|----------|"
        ]

        urgency_labels = {
            "immediate": "🚨 Немедленно",
            "hour": "⏰ В течение часа",
            "day": "📅 В течение дня"
        }

        for rule in rules:
            urgency = urgency_labels.get(rule.urgency, rule.urgency)
            lines.append(f"| {rule.trigger} | {urgency} | {rule.action} |")

        return "\n".join(lines)

    def _render_success_kpis(self, kpis: List[KPIMetric]) -> str:
        """Render success KPIs as table."""
        if not kpis:
            return "*KPI не определены*"

        lines = [
            "| KPI | Цель | Бенчмарк | Измерение |",
            "|-----|------|----------|-----------|"
        ]

        for kpi in kpis:
            benchmark = kpi.benchmark or "—"
            measurement = kpi.measurement or "—"
            lines.append(f"| {kpi.name} | {kpi.target} | {benchmark} | {measurement} |")

        return "\n".join(lines)

    def _render_launch_checklist(self, checklist: List[ChecklistItem]) -> str:
        """Render launch checklist."""
        if not checklist:
            return "*Чеклист не определён*"

        lines = []
        responsible_labels = {
            "client": "👤 Клиент",
            "team": "👥 Команда",
            "both": "🤝 Совместно"
        }

        for item in checklist:
            checkbox = "☐" if item.required else "○"
            responsible = responsible_labels.get(item.responsible, item.responsible)
            required_mark = " **(обязательно)**" if item.required else ""
            lines.append(f"- {checkbox} {item.item} — {responsible}{required_mark}")

        return "\n".join(lines)

    def _render_ai_recommendations(self, recommendations: List[AIRecommendation]) -> str:
        """Render AI recommendations."""
        if not recommendations:
            return "*Рекомендации не сгенерированы*"

        lines = []
        priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        effort_labels = {"low": "Низкие", "medium": "Средние", "high": "Высокие"}

        for i, rec in enumerate(recommendations, 1):
            priority_icon = priority_icons.get(rec.priority, "🟡")
            effort = effort_labels.get(rec.effort, rec.effort)

            lines.append(f"### {i}. {priority_icon} {rec.recommendation}")
            lines.append("")
            lines.append(f"**Ожидаемый эффект:** {rec.impact}")
            lines.append(f"")
            lines.append(f"*Приоритет: {rec.priority} | Затраты: {effort}*")
            lines.append("")

        return "\n".join(lines)

    def _render_tone_of_voice(self, tone: dict) -> str:
        """Render tone of voice guidelines."""
        if not tone:
            return "*Тон коммуникации не определён*"

        lines = []
        if tone.get("do"):
            lines.append("### ✅ Делать")
            lines.append("")
            lines.append(tone["do"])
            lines.append("")

        if tone.get("dont"):
            lines.append("### ❌ Не делать")
            lines.append("")
            lines.append(tone["dont"])
            lines.append("")

        return "\n".join(lines) if lines else "*Тон коммуникации не определён*"

    def _render_error_handling_scripts(self, scripts: dict) -> str:
        """Render error handling scripts."""
        if not scripts:
            return "*Скрипты не определены*"

        labels = {
            "not_understood": "🤔 Не понял запрос",
            "technical_issue": "⚠️ Техническая проблема",
            "out_of_scope": "🚫 Вне компетенции"
        }

        lines = []
        for key, script in scripts.items():
            label = labels.get(key, key)
            lines.append(f"**{label}:**")
            lines.append(f"> «{script}»")
            lines.append("")

        return "\n".join(lines)


def generate_anketa_files(anketa: FinalAnketa, output_dir: str = "output/anketas") -> dict:
    """
    Convenience function to generate both Markdown and JSON files.

    Args:
        anketa: Populated FinalAnketa instance
        output_dir: Output directory

    Returns:
        Dict with paths: {'markdown': Path, 'json': Path}
    """
    generator = AnketaGenerator(output_dir=output_dir)

    return {
        'markdown': generator.to_markdown(anketa),
        'json': generator.to_json(anketa)
    }
