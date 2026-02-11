"""
KB Context Builder - Formats industry knowledge for consultant prompts.

Loads templates from config/consultant/kb_context.yaml and formats
IndustryProfile data into prompt-ready text.
"""

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import IndustryProfile

SUCCESS_TAG = "[SUCCESS]"


class KBContextBuilder:
    """
    Builds prompt context from industry knowledge base.

    Formats IndustryProfile data according to templates in kb_context.yaml.
    """

    _instance: Optional["KBContextBuilder"] = None
    _config: Dict[str, Any] = {}
    _loaded: bool = False

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize context builder.

        Args:
            config_path: Path to kb_context.yaml
        """
        if not KBContextBuilder._loaded:
            self._config_path = config_path or Path("config/consultant/kb_context.yaml")
            self._load_config()

    def _load_config(self) -> None:
        """Load context templates from YAML."""
        if self._config_path.exists():
            with open(self._config_path, 'r', encoding='utf-8') as f:
                KBContextBuilder._config = yaml.safe_load(f) or {}
        KBContextBuilder._loaded = True

    def build_context(
        self,
        profile: IndustryProfile,
        phase: str
    ) -> str:
        """
        Build prompt context for a specific phase.

        Args:
            profile: Industry profile with data
            phase: Consultation phase (discovery, analysis, proposal, refinement)

        Returns:
            Formatted context string for prompt injection
        """
        sections = self._config.get('sections', {})
        section_config = sections.get(phase)

        if not section_config or not section_config.get('enabled', True):
            return ""

        parts = []
        header = section_config.get('header', '')

        if header:
            parts.append(f"---\n{header}: {profile.meta.id}\n")

        for block in section_config.get('blocks', []):
            block_text = self._format_block(profile, block)
            if block_text:
                parts.append(block_text)

        if len(parts) > 1:  # Has header + at least one block
            parts.append("---")
            return "\n".join(parts)

        return ""

    def _format_block(self, profile: IndustryProfile, block: Dict) -> str:
        """Format a single data block."""
        key = block.get('key', '')
        label = block.get('label', '')
        format_name = block.get('format', 'bullet_list')
        instruction = block.get('instruction', '')

        # Get data from profile
        data = self._get_profile_data(profile, key)
        if not data:
            return ""

        # Format data
        formatted = self._format_data(data, format_name)
        if not formatted:
            return ""

        parts = []
        if label:
            parts.append(f"\n{label}:")
        parts.append(formatted)

        if instruction:
            parts.append(f"[{instruction}]")

        return "\n".join(parts)

    def _get_profile_data(self, profile: IndustryProfile, key: str) -> Any:
        """Extract data from profile by key."""
        key_mapping = {
            'pain_points': profile.pain_points,
            'typical_services': profile.typical_services,
            'recommended_functions': profile.recommended_functions,
            'typical_integrations': profile.typical_integrations,
            'industry_faq': profile.industry_faq,
            'typical_objections': profile.typical_objections,
            'success_benchmarks': profile.success_benchmarks,
            'industry_specifics': profile.industry_specifics,
            'learnings': profile.learnings,
            'sales_scripts': profile.sales_scripts,
            'competitors': profile.competitors,
            'pricing_context': profile.pricing_context,
            'market_context': profile.market_context,
        }
        return key_mapping.get(key)

    def _format_data(self, data: Any, format_name: str) -> str:
        """Format data according to format template."""
        formats = self._config.get('formats', {})
        format_config = formats.get(format_name, {})

        if not data:
            return ""

        # Handle different data types
        if format_name == 'bullet_list':
            return self._format_bullet_list(data, format_config)
        elif format_name == 'severity_list':
            return self._format_severity_list(data, format_config)
        elif format_name == 'priority_list':
            return self._format_priority_list(data, format_config)
        elif format_name == 'integration_list':
            return self._format_integration_list(data, format_config)
        elif format_name == 'qa_list':
            return self._format_qa_list(data, format_config)
        elif format_name == 'objection_list':
            return self._format_objection_list(data, format_config)
        elif format_name == 'kpi_list':
            return self._format_kpi_list(data, format_config)
        elif format_name == 'specifics_list':
            return self._format_specifics_list(data, format_config)
        elif format_name == 'learnings_list':
            return self._format_learnings_list(data, format_config)
        elif format_name == 'sales_script_list':
            return self._format_sales_scripts(data, format_config)
        elif format_name == 'competitor_list':
            return self._format_competitors(data, format_config)
        elif format_name == 'pricing_format':
            return self._format_pricing(data, format_config)
        elif format_name == 'market_format':
            return self._format_market(data, format_config)

        # Fallback: simple bullet list
        return self._format_bullet_list(data, format_config)

    def _format_bullet_list(self, data: List, config: Dict) -> str:
        """Format as simple bullet list."""
        if isinstance(data, list):
            items = [f"- {item}" for item in data if item]
            return "\n".join(items)
        return ""

    def _format_severity_list(self, data: List, config: Dict) -> str:
        """Format pain points with severity."""
        labels = config.get('severity_labels', {
            'high': '!!!',
            'medium': '!!',
            'low': '!'
        })

        items = []
        for item in data:
            if hasattr(item, 'description') and hasattr(item, 'severity'):
                severity = labels.get(item.severity, '!')
                items.append(f"- [{severity}] {item.description}")
            elif isinstance(item, dict):
                severity = labels.get(item.get('severity', 'medium'), '!')
                items.append(f"- [{severity}] {item.get('description', str(item))}")
            else:
                items.append(f"- {item}")

        return "\n".join(items)

    def _format_priority_list(self, data: List, config: Dict) -> str:
        """Format recommended functions with priority."""
        labels = config.get('priority_labels', {
            'high': 'ВАЖНО',
            'medium': 'ЖЕЛАТЕЛЬНО',
            'low': 'ОПЦИОНАЛЬНО'
        })

        items = []
        for item in data:
            if hasattr(item, 'name') and hasattr(item, 'priority'):
                priority = labels.get(item.priority, 'ЖЕЛАТЕЛЬНО')
                reason = getattr(item, 'reason', '')
                items.append(f"- [{priority}] {item.name}: {reason}")
            elif isinstance(item, dict):
                priority = labels.get(item.get('priority', 'medium'), 'ЖЕЛАТЕЛЬНО')
                items.append(f"- [{priority}] {item.get('name', '')}: {item.get('reason', '')}")

        return "\n".join(items)

    def _format_integration_list(self, data: List, config: Dict) -> str:
        """Format integrations with examples."""
        items = []
        for item in data:
            if hasattr(item, 'name') and hasattr(item, 'examples'):
                examples = ", ".join(item.examples[:3]) if item.examples else ""
                items.append(f"- {item.name} ({examples})")
            elif isinstance(item, dict):
                examples = ", ".join(item.get('examples', [])[:3])
                items.append(f"- {item.get('name', '')} ({examples})")

        return "\n".join(items)

    def _format_qa_list(self, data: List, config: Dict) -> str:
        """Format FAQ as Q&A."""
        items = []
        for item in data:
            if hasattr(item, 'question') and hasattr(item, 'answer_template'):
                items.append(f"В: {item.question}\nО: {item.answer_template}")
            elif isinstance(item, dict):
                items.append(f"В: {item.get('question', '')}\nО: {item.get('answer_template', '')}")

        return "\n\n".join(items)

    def _format_objection_list(self, data: List, config: Dict) -> str:
        """Format objections with responses."""
        items = []
        for item in data:
            if hasattr(item, 'objection') and hasattr(item, 'response'):
                items.append(f'Возражение: "{item.objection}"\nОтвет: {item.response}')
            elif isinstance(item, dict):
                items.append(f'Возражение: "{item.get("objection", "")}"\nОтвет: {item.get("response", "")}')

        return "\n\n".join(items)

    def _format_kpi_list(self, data: Any, config: Dict) -> str:
        """Format success benchmarks."""
        if hasattr(data, 'typical_kpis') and data.typical_kpis:
            items = [f"- {kpi}" for kpi in data.typical_kpis]
            return "\n".join(items)
        elif isinstance(data, dict) and 'typical_kpis' in data:
            items = [f"- {kpi}" for kpi in data.get('typical_kpis', [])]
            return "\n".join(items)
        return ""

    def _format_specifics_list(self, data: Any, config: Dict) -> str:
        """Format industry specifics (compliance, tone, peak_times)."""
        if not data:
            return ""

        parts = []

        # Handle IndustrySpecifics model
        if hasattr(data, 'compliance') and data.compliance:
            parts.append(f"Комплаенс: {', '.join(data.compliance)}")

        if hasattr(data, 'tone') and data.tone:
            parts.append(f"Тон общения: {', '.join(data.tone)}")

        if hasattr(data, 'peak_times') and data.peak_times:
            parts.append(f"Пиковые часы: {', '.join(data.peak_times)}")

        # Handle dict
        if isinstance(data, dict):
            if data.get('compliance'):
                parts.append(f"Комплаенс: {', '.join(data['compliance'])}")
            if data.get('tone'):
                parts.append(f"Тон общения: {', '.join(data['tone'])}")
            if data.get('peak_times'):
                parts.append(f"Пиковые часы: {', '.join(data['peak_times'])}")

        return "\n".join(parts)

    def _format_learnings_list(self, data: List, config: Dict) -> str:
        """Format learnings list."""
        if not data:
            return ""

        items = []
        for item in data[-5:]:  # Last 5 learnings
            insight = item.insight if hasattr(item, 'insight') else item.get('insight', '')
            if not insight:
                continue
            is_success = SUCCESS_TAG in insight
            clean_insight = insight.replace(f"{SUCCESS_TAG} ", "")
            prefix = "+" if is_success else "•"
            items.append(f"{prefix} {clean_insight}")

        return "\n".join(items)

    def _format_sales_scripts(self, data: List, config: Dict) -> str:
        """Format sales scripts with triggers and goals."""
        if not data:
            return ""
        items = []
        for item in data:
            if hasattr(item, 'trigger'):
                trigger = item.trigger
                script = item.script if hasattr(item, 'script') else ''
                goal = item.goal if hasattr(item, 'goal') else ''
                items.append(f"Триггер: {trigger}\nСкрипт: {script}\nЦель: {goal}")
            elif isinstance(item, dict):
                items.append(
                    f"Триггер: {item.get('trigger', '')}\n"
                    f"Скрипт: {item.get('script', '')}\n"
                    f"Цель: {item.get('goal', '')}"
                )
        return "\n\n".join(items)

    def _format_competitors(self, data: List, config: Dict) -> str:
        """Format competitor analysis."""
        if not data:
            return ""
        items = []
        for item in data:
            if hasattr(item, 'name') and hasattr(item, 'positioning'):
                diff = getattr(item, 'our_differentiation', '') or ''
                weaknesses = getattr(item, 'weaknesses', [])
                weak_str = f" | Слабости: {', '.join(weaknesses)}" if weaknesses else ""
                diff_str = f" | Наше отличие: {diff}" if diff else ""
                items.append(f"- {item.name}: {item.positioning}{weak_str}{diff_str}")
            elif isinstance(item, dict):
                diff = item.get('our_differentiation', '') or ''
                weaknesses = item.get('weaknesses', [])
                weak_str = f" | Слабости: {', '.join(weaknesses)}" if weaknesses else ""
                diff_str = f" | Наше отличие: {diff}" if diff else ""
                items.append(f"- {item.get('name', '')}: {item.get('positioning', '')}{weak_str}{diff_str}")
        return "\n".join(items)

    def _format_pricing(self, data: Any, config: Dict) -> str:
        """Format pricing context with budget ranges and ROI."""
        if not data:
            return ""
        parts = []
        if hasattr(data, 'typical_budget_range'):
            budget = data.typical_budget_range
            currency = getattr(data, 'currency', 'EUR')
            if budget and len(budget) == 2 and (budget[0] > 0 or budget[1] > 0):
                parts.append(f"Бюджет: {budget[0]:.0f}-{budget[1]:.0f} {currency}")
            entry = getattr(data, 'entry_point', 0)
            if entry > 0:
                parts.append(f"Входная цена: {entry:.0f} {currency}")
            roi_examples = getattr(data, 'roi_examples', [])
            for roi in roi_examples[:2]:
                scenario = roi.scenario if hasattr(roi, 'scenario') else roi.get('scenario', '')
                months = roi.payback_months if hasattr(roi, 'payback_months') else roi.get('payback_months', 0)
                parts.append(f"ROI: {scenario} → окупаемость {months} мес")
            anchors = getattr(data, 'value_anchors', [])
            if anchors:
                parts.append(f"Ценностные якоря: {', '.join(anchors[:3])}")
        elif isinstance(data, dict):
            budget = data.get('typical_budget_range', [0, 0])
            currency = data.get('currency', 'EUR')
            if budget and len(budget) == 2 and (budget[0] > 0 or budget[1] > 0):
                parts.append(f"Бюджет: {budget[0]:.0f}-{budget[1]:.0f} {currency}")
            for roi in data.get('roi_examples', [])[:2]:
                parts.append(f"ROI: {roi.get('scenario', '')} → окупаемость {roi.get('payback_months', 0)} мес")
        return "\n".join(parts)

    def _format_market(self, data: Any, config: Dict) -> str:
        """Format market context with size, growth and trends."""
        if not data:
            return ""
        parts = []
        if hasattr(data, 'market_size'):
            if data.market_size:
                parts.append(f"Объём рынка: {data.market_size}")
            growth = getattr(data, 'growth_rate', None)
            if growth:
                parts.append(f"Рост: {growth}")
            trends = getattr(data, 'key_trends', [])
            if trends:
                parts.append(f"Тренды: {', '.join(trends[:4])}")
            seasonality = getattr(data, 'seasonality', None)
            if seasonality:
                high = getattr(seasonality, 'high', [])
                if high:
                    parts.append(f"Высокий сезон: {', '.join(high)}")
        elif isinstance(data, dict):
            if data.get('market_size'):
                parts.append(f"Объём рынка: {data['market_size']}")
            if data.get('growth_rate'):
                parts.append(f"Рост: {data['growth_rate']}")
            if data.get('key_trends'):
                parts.append(f"Тренды: {', '.join(data['key_trends'][:4])}")
        return "\n".join(parts)


# Singleton accessor
_builder: Optional[KBContextBuilder] = None


def get_kb_context_builder(config_path: Optional[Path] = None) -> KBContextBuilder:
    """Get or create KB context builder singleton."""
    global _builder
    if _builder is None or config_path is not None:
        _builder = KBContextBuilder(config_path)
    return _builder
