"""
TestValidator - validates consultation test results.

Performs 6 types of checks:
1. Field completeness - required fields are filled
2. Data quality - values are meaningful, not garbage
3. Scenario match - data matches YAML scenario
4. Phase completion - all 4 phases completed
5. No loops - no repetitive dialogue patterns
6. Metrics - turn count and duration within limits
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from src.anketa.schema import FinalAnketa
from tests.simulation.runner import TestResult

logger = structlog.get_logger()


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
    MAX_DURATION_SECONDS = 600  # 10 minutes
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
        """Check that data values are meaningful."""
        issues = []

        # Check company_name length (not too long = dialog chunk)
        if anketa.company_name and len(anketa.company_name) > 100:
            issues.append("company_name слишком длинное (возможно, кусок диалога)")

        # Check agent_purpose length
        if anketa.agent_purpose and len(anketa.agent_purpose) > 500:
            issues.append("agent_purpose слишком длинное")

        # Check for dialog markers in values
        dialog_markers = ["Консультант:", "Клиент:", "ASSISTANT:", "USER:"]
        fields_to_check = [
            ('company_name', anketa.company_name),
            ('industry', anketa.industry),
            ('agent_name', anketa.agent_name),
            ('agent_purpose', anketa.agent_purpose),
        ]

        for field_name, value in fields_to_check:
            if value:
                for marker in dialog_markers:
                    if marker in value:
                        issues.append(f"{field_name} содержит маркер диалога '{marker}'")
                        break

        # Check that lists don't contain very long items
        list_fields = [
            ('services', anketa.services),
            ('current_problems', anketa.current_problems),
            ('typical_questions', anketa.typical_questions),
        ]

        for field_name, items in list_fields:
            for item in items:
                if len(item) > 300:
                    issues.append(f"{field_name} содержит слишком длинный элемент")
                    break

        if issues:
            return ValidationCheck(
                name="data_quality",
                status="warning" if len(issues) <= 2 else "error",
                message=f"Проблемы с качеством данных: {'; '.join(issues[:3])}",
                details={"issues": issues}
            )

        return ValidationCheck(
            name="data_quality",
            status="ok",
            message="Качество данных в норме"
        )

    def _check_scenario_match(
        self,
        anketa: FinalAnketa,
        scenario: Dict[str, Any]
    ) -> ValidationCheck:
        """Check that extracted data matches YAML scenario."""
        issues = []
        persona = scenario.get('persona', {})

        # Check company name
        expected_company = persona.get('company', '').lower()
        if expected_company:
            actual_company = anketa.company_name.lower()
            if expected_company not in actual_company and actual_company not in expected_company:
                issues.append(f"Компания не совпадает: ожидали '{persona.get('company')}'")

        # Check industry
        expected_industry = persona.get('industry', '').lower()
        if expected_industry:
            actual_industry = anketa.industry.lower()
            if expected_industry not in actual_industry and actual_industry not in expected_industry:
                issues.append(f"Отрасль не совпадает: ожидали '{persona.get('industry')}'")

        # Check that target functions are covered
        expected_functions = [f.lower() for f in persona.get('target_functions', [])]
        if expected_functions:
            actual_functions = [f.name.lower() for f in anketa.agent_functions]
            actual_functions.extend([f.name.lower() for f in anketa.additional_functions])
            if anketa.main_function:
                actual_functions.append(anketa.main_function.name.lower())

            # Check if any expected function is mentioned
            matched = 0
            for expected in expected_functions:
                for actual in actual_functions:
                    if expected in actual or actual in expected:
                        matched += 1
                        break

            if matched < len(expected_functions) / 2:
                issues.append(f"Мало совпадений по функциям: {matched}/{len(expected_functions)}")

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
