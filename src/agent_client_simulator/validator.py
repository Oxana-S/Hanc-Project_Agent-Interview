"""
TestValidator - validates consultation test results.

Performs 6 types of checks:
1. Field completeness - required fields are filled
2. Data quality - values are meaningful, not garbage
3. Scenario match - data matches YAML scenario
4. Phase completion - all 4 phases completed
5. No loops - no repetitive dialogue patterns
6. Metrics - turn count and duration within limits

v3.1 Improvements:
- Synonym support for flexible matching
- Extended validation checks
- Fuzzy matching for company/industry names

v3.2 Improvements:
- Synonyms loaded from config/synonyms.yaml
- Expanded synonym dictionaries
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

from src.anketa.schema import FinalAnketa
from src.config.synonym_loader import get_synonym_loader
from .runner import TestResult

logger = structlog.get_logger()


# ============================================================================
# SYNONYM MATCHER (v3.2: loads from YAML)
# ============================================================================

class SynonymMatcher:
    """
    Handles synonym-based matching for validation.

    v3.2: Loads synonyms from config/synonyms.yaml with fallback to defaults.
    """

    # Class-level cache for loaded synonyms
    _industry_synonyms: Optional[Dict[str, List[str]]] = None
    _function_synonyms: Optional[Dict[str, List[str]]] = None
    _integration_synonyms: Optional[Dict[str, List[str]]] = None

    @classmethod
    def _load_synonyms(cls):
        """Load synonyms from YAML config."""
        if cls._industry_synonyms is None:
            loader = get_synonym_loader()
            cls._industry_synonyms = loader.get_industries()
            cls._function_synonyms = loader.get_functions()
            cls._integration_synonyms = loader.get_integrations()
            logger.debug(
                "Synonyms loaded",
                industries=len(cls._industry_synonyms),
                functions=len(cls._function_synonyms),
                integrations=len(cls._integration_synonyms)
            )

    @classmethod
    def get_industry_synonyms(cls) -> Dict[str, List[str]]:
        """Get industry synonyms (loads from YAML if needed)."""
        cls._load_synonyms()
        return cls._industry_synonyms

    @classmethod
    def get_function_synonyms(cls) -> Dict[str, List[str]]:
        """Get function synonyms (loads from YAML if needed)."""
        cls._load_synonyms()
        return cls._function_synonyms

    @classmethod
    def get_integration_synonyms(cls) -> Dict[str, List[str]]:
        """Get integration synonyms (loads from YAML if needed)."""
        cls._load_synonyms()
        return cls._integration_synonyms

    # Legacy class attributes for backward compatibility
    INDUSTRY_SYNONYMS = property(lambda self: self.get_industry_synonyms())
    FUNCTION_SYNONYMS = property(lambda self: self.get_function_synonyms())
    INTEGRATION_SYNONYMS = property(lambda self: self.get_integration_synonyms())

    @classmethod
    def normalize(cls, text: str) -> str:
        """Normalize text for comparison."""
        if not text:
            return ''
        # Lowercase, remove extra spaces, remove punctuation
        normalized = text.lower().strip()
        # v3.2: Convert underscores to spaces for key matching
        normalized = normalized.replace('_', ' ')
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = ' '.join(normalized.split())
        return normalized

    @classmethod
    def find_synonyms(cls, text: str, synonym_dict: Dict[str, List[str]]) -> Set[str]:
        """Find all synonym groups that match the text."""
        normalized = cls.normalize(text)
        matching_groups = set()

        for group_key, synonyms in synonym_dict.items():
            for synonym in synonyms:
                if synonym in normalized or normalized in synonym:
                    matching_groups.add(group_key)
                    break

        return matching_groups

    @classmethod
    def match_with_synonyms(
        cls,
        actual: str,
        expected: str,
        synonym_dict: Dict[str, List[str]]
    ) -> bool:
        """
        Check if actual matches expected, considering synonyms.

        Returns True if:
        - Direct substring match
        - Both belong to the same synonym group
        """
        actual_norm = cls.normalize(actual)
        expected_norm = cls.normalize(expected)

        # Direct match
        if expected_norm in actual_norm or actual_norm in expected_norm:
            return True

        # Synonym match
        actual_groups = cls.find_synonyms(actual, synonym_dict)
        expected_groups = cls.find_synonyms(expected, synonym_dict)

        return bool(actual_groups & expected_groups)

    @classmethod
    def match_industry(cls, actual: str, expected: str) -> bool:
        """Match industry names with synonym support."""
        return cls.match_with_synonyms(actual, expected, cls.get_industry_synonyms())

    @classmethod
    def match_function(cls, actual: str, expected: str) -> bool:
        """Match function names with synonym support."""
        return cls.match_with_synonyms(actual, expected, cls.get_function_synonyms())

    @classmethod
    def match_integration(cls, actual: str, expected: str) -> bool:
        """Match integration names with synonym support."""
        return cls.match_with_synonyms(actual, expected, cls.get_integration_synonyms())


@dataclass
class ValidationCheck:
    """Result of a single validation check."""
    name: str
    status: str  # "ok", "warning", "error"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Complete validation result."""
    passed: bool
    checks: List[ValidationCheck]
    errors: List[str]
    warnings: List[str]
    score: float  # 0-100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "score": self.score,
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "details": c.details
                }
                for c in self.checks
            ]
        }


class TestValidator:
    """Validates consultation test results."""

    # Limits for metrics check
    MAX_TURNS = 50
    MAX_DURATION_SECONDS = 900  # 15 minutes (v3.2: increased for expert content generation)
    MAX_DUPLICATE_MESSAGES = 5

    def validate(
        self,
        result: TestResult,
        scenario: Dict[str, Any],
        anketa: FinalAnketa
    ) -> ValidationResult:
        """
        Run all validation checks.

        Args:
            result: Test result from ConsultationTester
            scenario: Original YAML scenario config
            anketa: Extracted FinalAnketa

        Returns:
            ValidationResult with all checks
        """
        checks = []
        errors = []
        warnings = []

        # 1. Completeness check
        check = self._check_completeness(anketa)
        checks.append(check)
        self._collect_issues(check, errors, warnings)

        # 2. Data quality check
        check = self._check_data_quality(anketa)
        checks.append(check)
        self._collect_issues(check, errors, warnings)

        # 3. Scenario match check
        check = self._check_scenario_match(anketa, scenario)
        checks.append(check)
        self._collect_issues(check, errors, warnings)

        # 4. Phase completion check
        check = self._check_phases(result)
        checks.append(check)
        self._collect_issues(check, errors, warnings)

        # 5. No loops check
        check = self._check_no_loops(result)
        checks.append(check)
        self._collect_issues(check, errors, warnings)

        # 6. Metrics check
        check = self._check_metrics(result)
        checks.append(check)
        self._collect_issues(check, errors, warnings)

        # Calculate score
        ok_count = sum(1 for c in checks if c.status == "ok")
        warning_count = sum(1 for c in checks if c.status == "warning")
        # OK = 1.0, Warning = 0.5, Error = 0
        score = (ok_count + warning_count * 0.5) / len(checks) * 100

        passed = len(errors) == 0

        validation = ValidationResult(
            passed=passed,
            checks=checks,
            errors=errors,
            warnings=warnings,
            score=score
        )

        logger.info(
            "Validation completed",
            passed=passed,
            score=f"{score:.0f}%",
            errors=len(errors),
            warnings=len(warnings)
        )

        return validation

    def _collect_issues(
        self,
        check: ValidationCheck,
        errors: List[str],
        warnings: List[str]
    ):
        """Collect errors and warnings from check."""
        if check.status == "error":
            errors.append(f"[{check.name}] {check.message}")
        elif check.status == "warning":
            warnings.append(f"[{check.name}] {check.message}")

    def _check_completeness(self, anketa: FinalAnketa) -> ValidationCheck:
        """Check that required fields are filled."""
        required_fields = {
            'company_name': anketa.company_name,
            'industry': anketa.industry,
            'agent_name': anketa.agent_name,
            'agent_purpose': anketa.agent_purpose,
            'main_function': anketa.main_function,
        }

        missing = []
        for field_name, value in required_fields.items():
            if not value:
                missing.append(field_name)
            elif isinstance(value, str) and not value.strip():
                missing.append(field_name)

        if missing:
            return ValidationCheck(
                name="completeness",
                status="error",
                message=f"Не заполнены обязательные поля: {', '.join(missing)}",
                details={"missing_fields": missing}
            )

        # Check optional fields for completeness percentage
        completion = anketa.completion_rate()
        if completion < 70:
            return ValidationCheck(
                name="completeness",
                status="warning",
                message=f"Низкий уровень заполненности: {completion:.0f}%",
                details={"completion_rate": completion}
            )

        return ValidationCheck(
            name="completeness",
            status="ok",
            message=f"Все обязательные поля заполнены ({completion:.0f}%)",
            details={"completion_rate": completion}
        )

    def _check_data_quality(self, anketa: FinalAnketa) -> ValidationCheck:
        """Check that data values are meaningful with extended checks."""
        issues = []

        # Extended dialogue markers detection
        dialog_markers = [
            "Консультант:", "Клиент:", "ASSISTANT:", "USER:",
            "AI:", "Bot:", "Здравствуйте,", "Добрый день,",
            "Расскажите", "Подскажите", "Давайте"
        ]

        # Fields with strict requirements
        strict_fields = {
            'company_name': {'max_len': 100, 'check_markers': True},
            'industry': {'max_len': 80, 'check_markers': True},
            'agent_name': {'max_len': 100, 'check_markers': True},
            'language': {'max_len': 10, 'check_markers': False},
            'voice_gender': {'max_len': 20, 'check_markers': False},
        }

        # Check strict fields
        for field_name, rules in strict_fields.items():
            value = getattr(anketa, field_name, '')
            if not value:
                continue

            if len(value) > rules['max_len']:
                issues.append(f"{field_name} слишком длинное ({len(value)} > {rules['max_len']})")

            if rules['check_markers']:
                for marker in dialog_markers:
                    if marker.lower() in value.lower():
                        issues.append(f"{field_name} содержит диалоговый маркер")
                        break

        # Check agent_purpose (description field, more lenient)
        if anketa.agent_purpose and len(anketa.agent_purpose) > 500:
            issues.append("agent_purpose слишком длинное")

        # Check for dialogue contamination patterns
        contamination_patterns = [
            r'^(Да|Нет|Конечно|Хорошо),\s',  # Starting with confirmation
            r'\?$',  # Ending with question mark (shouldn't be in data fields)
            r'[!]{2,}',  # Multiple exclamation marks
        ]

        fields_to_check = ['company_name', 'industry', 'agent_name']
        for field_name in fields_to_check:
            value = getattr(anketa, field_name, '')
            if value:
                for pattern in contamination_patterns:
                    if re.search(pattern, value):
                        issues.append(f"{field_name} имеет признаки диалога")
                        break

        # Check lists for quality
        issues.extend(self._check_list_quality(anketa))

        if issues:
            severity = "error" if len(issues) > 3 else "warning"
            return ValidationCheck(
                name="data_quality",
                status=severity,
                message=f"Проблемы с качеством данных: {'; '.join(issues[:3])}",
                details={"issues": issues, "total_issues": len(issues)}
            )

        return ValidationCheck(
            name="data_quality",
            status="ok",
            message="Качество данных в норме"
        )

    def _check_list_quality(self, anketa: FinalAnketa) -> List[str]:
        """Check quality of list fields."""
        issues = []

        list_fields = [
            ('services', anketa.services, 300),
            ('current_problems', anketa.current_problems, 300),
            ('typical_questions', anketa.typical_questions, 200),
            ('business_goals', anketa.business_goals, 300),
        ]

        for field_name, items, max_item_len in list_fields:
            if not items:
                continue

            # Check for overly long items
            long_items = [i for i in items if len(i) > max_item_len]
            if long_items:
                issues.append(f"{field_name} содержит слишком длинные элементы")

            # Check for duplicate items
            unique_items = {i.lower().strip() for i in items}
            if len(unique_items) < len(items) * 0.7:
                issues.append(f"{field_name} содержит дубликаты")

        return issues

    def _check_scenario_match(
        self,
        anketa: FinalAnketa,
        scenario: Dict[str, Any]
    ) -> ValidationCheck:
        """Check that extracted data matches YAML scenario with synonym support."""
        issues = []
        persona = scenario.get('persona', {})
        expected_results = scenario.get('expected_results', {})

        # Check company name
        expected_company = persona.get('company', '')
        if expected_company and anketa.company_name:
            if not self._fuzzy_company_match(anketa.company_name, expected_company):
                issues.append(f"Компания не совпадает: ожидали '{expected_company}'")

        # Check industry with synonym support
        expected_industry = persona.get('industry', '')
        if expected_industry and anketa.industry:
            if not SynonymMatcher.match_industry(anketa.industry, expected_industry):
                issues.append(f"Отрасль не совпадает: ожидали '{expected_industry}'")

        # Check target functions with synonym support
        expected_functions = persona.get('target_functions', [])
        expected_functions.extend(expected_results.get('expected_functions', []))

        if expected_functions:
            matched = self._count_function_matches(anketa, expected_functions)
            total = len(expected_functions)
            if matched < total / 2:
                issues.append(f"Мало совпадений по функциям: {matched}/{total}")

        # Check integrations with synonym support
        expected_integrations = persona.get('integrations', [])
        expected_integrations.extend(expected_results.get('expected_integrations', []))

        if expected_integrations:
            matched = self._count_integration_matches(anketa, expected_integrations)
            total = len(expected_integrations)
            if matched < total / 2:
                issues.append(f"Мало совпадений по интеграциям: {matched}/{total}")

        if issues:
            return ValidationCheck(
                name="scenario_match",
                status="error" if len(issues) > 1 else "warning",
                message="; ".join(issues),
                details={"issues": issues}
            )

        return ValidationCheck(
            name="scenario_match",
            status="ok",
            message="Данные соответствуют сценарию"
        )

    def _fuzzy_company_match(self, actual: str, expected: str) -> bool:
        """Fuzzy match company names."""
        actual_norm = SynonymMatcher.normalize(actual)
        expected_norm = SynonymMatcher.normalize(expected)
        return expected_norm in actual_norm or actual_norm in expected_norm

    def _count_function_matches(self, anketa: FinalAnketa, expected: List[str]) -> int:
        """Count how many expected functions are matched (v3.2: includes agent_purpose)."""
        actual_functions = [f.name for f in anketa.agent_functions]
        actual_functions.extend([f.name for f in anketa.additional_functions])
        if anketa.main_function:
            actual_functions.append(anketa.main_function.name)
        # v3.2: Also search in agent_purpose description
        if anketa.agent_purpose:
            actual_functions.append(anketa.agent_purpose)

        matched = 0
        for exp in expected:
            for act in actual_functions:
                if SynonymMatcher.match_function(act, exp):
                    matched += 1
                    break
        return matched

    def _count_integration_matches(self, anketa: FinalAnketa, expected: List[str]) -> int:
        """Count how many expected integrations are matched."""
        actual_integrations = [i.name for i in anketa.integrations]

        matched = 0
        for exp in expected:
            for act in actual_integrations:
                if SynonymMatcher.match_integration(act, exp):
                    matched += 1
                    break
        return matched

    def _check_phases(self, result: TestResult) -> ValidationCheck:
        """Check that all consultation phases completed."""
        required_phases = ['discovery', 'analysis', 'proposal', 'refinement']

        if not result.phases_completed:
            return ValidationCheck(
                name="phases",
                status="error",
                message="Нет информации о пройденных фазах",
                details={"required": required_phases, "completed": []}
            )

        missing = [p for p in required_phases if p not in result.phases_completed]

        if missing:
            return ValidationCheck(
                name="phases",
                status="error",
                message=f"Не пройдены фазы: {', '.join(missing)}",
                details={"missing": missing, "completed": result.phases_completed}
            )

        return ValidationCheck(
            name="phases",
            status="ok",
            message=f"Все {len(required_phases)} фазы пройдены",
            details={"completed": result.phases_completed}
        )

    def _check_no_loops(self, result: TestResult) -> ValidationCheck:
        """Check for repetitive patterns in dialogue."""
        if not result.dialogue_history:
            return ValidationCheck(
                name="no_loops",
                status="ok",
                message="Диалог пуст или недоступен"
            )

        # Extract message contents (first 100 chars to compare)
        messages = []
        for msg in result.dialogue_history:
            content = msg.get('content', '')
            if content:
                messages.append(content[:100])

        # Count duplicates
        unique_messages = set(messages)
        duplicate_count = len(messages) - len(unique_messages)

        # Check for specific loop patterns
        loop_indicators = [
            "технический сбой",
            "повторяется",
            "уже ответил",
            "цикл",
            "ещё раз",
        ]

        loop_detected = False
        for msg in result.dialogue_history:
            content = msg.get('content', '').lower()
            if any(indicator in content for indicator in loop_indicators):
                loop_detected = True
                break

        if loop_detected or duplicate_count > self.MAX_DUPLICATE_MESSAGES:
            return ValidationCheck(
                name="no_loops",
                status="warning",
                message=f"Обнаружено зацикливание: {duplicate_count} повторов",
                details={
                    "duplicate_count": duplicate_count,
                    "loop_detected": loop_detected
                }
            )

        return ValidationCheck(
            name="no_loops",
            status="ok",
            message="Зацикливание не обнаружено",
            details={"duplicate_count": duplicate_count}
        )

    def _check_metrics(self, result: TestResult) -> ValidationCheck:
        """Check that metrics are within acceptable limits."""
        issues = []
        details = {
            "turn_count": result.turn_count,
            "duration_seconds": result.duration_seconds
        }

        if result.turn_count > self.MAX_TURNS:
            issues.append(f"Слишком много ходов: {result.turn_count} (макс {self.MAX_TURNS})")

        if result.duration_seconds > self.MAX_DURATION_SECONDS:
            issues.append(
                f"Слишком долго: {result.duration_seconds:.0f} сек "
                f"(макс {self.MAX_DURATION_SECONDS})"
            )

        # Check for very short consultation (suspicious)
        if result.turn_count < 5:
            issues.append(f"Очень короткая консультация: {result.turn_count} ходов")

        if issues:
            return ValidationCheck(
                name="metrics",
                status="warning",
                message="; ".join(issues),
                details=details
            )

        return ValidationCheck(
            name="metrics",
            status="ok",
            message=f"Метрики в норме: {result.turn_count} ходов, {result.duration_seconds:.0f} сек",
            details=details
        )
