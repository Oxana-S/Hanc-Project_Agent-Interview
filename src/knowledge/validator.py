"""
Profile Validator - Validates industry profile completeness.

v1.0: Initial implementation
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import IndustryProfile
    from .manager import IndustryKnowledgeManager


@dataclass
class ValidationResult:
    """Result of profile validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    completeness_score: float = 0.0


class ProfileValidator:
    """
    Validates industry profile completeness.

    Checks that profiles have all required fields with minimum items.
    """

    REQUIRED_FIELDS = ['pain_points', 'typical_services', 'recommended_functions']

    MIN_ITEMS = {
        'pain_points': 3,
        'typical_services': 5,
        'recommended_functions': 3,
        'typical_integrations': 2,
        'industry_faq': 3,
        'typical_objections': 2,
        'aliases': 2,
    }

    FIELD_WEIGHTS = {
        'pain_points': 0.2,
        'typical_services': 0.15,
        'recommended_functions': 0.2,
        'typical_integrations': 0.1,
        'industry_faq': 0.1,
        'typical_objections': 0.1,
        'aliases': 0.05,
        'industry_specifics': 0.05,
        'success_benchmarks': 0.05,
    }

    def validate(self, profile: "IndustryProfile") -> ValidationResult:
        """
        Validate profile completeness.

        Args:
            profile: Industry profile to validate

        Returns:
            ValidationResult with errors, warnings, and completeness score
        """
        errors: List[str] = []
        warnings: List[str] = []
        field_scores: Dict[str, float] = {}

        for req_field in self.REQUIRED_FIELDS:
            field_value = getattr(profile, req_field, [])
            if not field_value:
                errors.append(f"Обязательное поле '{req_field}' пустое")
                field_scores[req_field] = 0.0
            else:
                min_count = self.MIN_ITEMS.get(req_field, 1)
                actual_count = len(field_value)
                if actual_count < min_count:
                    warnings.append(
                        f"Поле '{req_field}' содержит {actual_count} элементов "
                        f"(рекомендуется минимум {min_count})"
                    )
                    field_scores[req_field] = actual_count / min_count
                else:
                    field_scores[req_field] = 1.0

        for opt_field in ['typical_integrations', 'industry_faq', 'typical_objections', 'aliases']:
            field_value = getattr(profile, opt_field, [])
            min_count = self.MIN_ITEMS.get(opt_field, 1)
            if not field_value:
                warnings.append(f"Рекомендуемое поле '{opt_field}' пустое")
                field_scores[opt_field] = 0.0
            else:
                actual_count = len(field_value)
                if actual_count < min_count:
                    warnings.append(
                        f"Поле '{opt_field}' содержит {actual_count} элементов "
                        f"(рекомендуется минимум {min_count})"
                    )
                    field_scores[opt_field] = min(1.0, actual_count / min_count)
                else:
                    field_scores[opt_field] = 1.0

        if profile.industry_specifics is None:
            warnings.append("Поле 'industry_specifics' не заполнено")
            field_scores['industry_specifics'] = 0.0
        else:
            spec = profile.industry_specifics
            spec_filled = 0
            if spec.compliance:
                spec_filled += 1
            if spec.tone:
                spec_filled += 1
            if spec.peak_times:
                spec_filled += 1
            field_scores['industry_specifics'] = spec_filled / 3.0

        benchmarks = profile.success_benchmarks
        if benchmarks and benchmarks.typical_kpis:
            field_scores['success_benchmarks'] = 1.0
        else:
            warnings.append("Поле 'success_benchmarks.typical_kpis' пустое")
            field_scores['success_benchmarks'] = 0.5

        completeness_score = 0.0
        for field_name, weight in self.FIELD_WEIGHTS.items():
            score = field_scores.get(field_name, 0.0)
            completeness_score += score * weight

        completeness_score = min(1.0, completeness_score)

        is_valid = len(errors) == 0 and completeness_score >= 0.5

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            completeness_score=completeness_score
        )

    def validate_all(
        self,
        manager: "IndustryKnowledgeManager"
    ) -> Dict[str, ValidationResult]:
        """
        Validate all profiles in the knowledge base.

        Args:
            manager: Knowledge manager instance

        Returns:
            Dict mapping industry_id to ValidationResult
        """
        results: Dict[str, ValidationResult] = {}

        for industry_id in manager.get_all_industries():
            profile = manager.get_profile(industry_id)
            if profile:
                results[industry_id] = self.validate(profile)
            else:
                results[industry_id] = ValidationResult(
                    is_valid=False,
                    errors=[f"Профиль '{industry_id}' не найден"],
                    completeness_score=0.0
                )

        return results

    def get_summary(
        self,
        results: Dict[str, ValidationResult]
    ) -> str:
        """
        Get human-readable summary of validation results.

        Args:
            results: Dict of validation results

        Returns:
            Formatted summary string
        """
        lines = ["Результаты валидации профилей:", ""]

        valid_count = sum(1 for r in results.values() if r.is_valid)
        total_count = len(results)
        avg_score = sum(r.completeness_score for r in results.values()) / total_count if total_count else 0

        lines.append(f"Всего профилей: {total_count}")
        lines.append(f"Валидных: {valid_count} ({valid_count/total_count*100:.0f}%)")
        lines.append(f"Средний completeness: {avg_score:.0%}")
        lines.append("")

        for industry_id, result in sorted(results.items()):
            status = "✅" if result.is_valid else "⚠️"
            lines.append(f"{status} {industry_id}: {result.completeness_score:.0%}")

            for error in result.errors:
                lines.append(f"   ❌ {error}")

            for warning in result.warnings[:3]:
                lines.append(f"   └─ {warning}")

            if len(result.warnings) > 3:
                lines.append(f"   └─ ... и ещё {len(result.warnings) - 3} предупреждений")

        return "\n".join(lines)
