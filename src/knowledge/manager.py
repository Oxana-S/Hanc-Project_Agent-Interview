"""
Industry Knowledge Manager - main interface for industry knowledge base.

v1.0: Initial implementation
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from .models import IndustryProfile, Learning
from .loader import IndustryProfileLoader
from .matcher import IndustryMatcher

logger = structlog.get_logger("knowledge")


class IndustryKnowledgeManager:
    """
    Главный интерфейс для работы с базой знаний по отраслям.

    Объединяет загрузку профилей, определение отрасли и обновление данных.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Инициализация менеджера.

        Args:
            config_dir: Путь к директории config/industries/
        """
        self.loader = IndustryProfileLoader(config_dir)
        self.matcher = IndustryMatcher(self.loader)

        logger.info("IndustryKnowledgeManager initialized")

    def get_profile(self, industry_id: str) -> Optional[IndustryProfile]:
        """
        Получить профиль отрасли по ID.

        Args:
            industry_id: ID отрасли (например: "logistics", "medical")

        Returns:
            IndustryProfile или None
        """
        return self.loader.load_profile(industry_id)

    def detect_industry(self, text: str) -> Optional[str]:
        """
        Определить отрасль из текста.

        Args:
            text: Текст для анализа (диалог, описание бизнеса)

        Returns:
            ID отрасли или None
        """
        return self.matcher.detect(text)

    def detect_industry_with_confidence(self, text: str) -> tuple[Optional[str], float]:
        """
        Определить отрасль с уровнем уверенности.

        Args:
            text: Текст для анализа

        Returns:
            Tuple (industry_id, confidence)
        """
        return self.matcher.detect_with_confidence(text)

    def get_context_for_interview(self, industry_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить контекст для обогащения интервью.

        Возвращает ключевые данные из профиля для использования
        в промптах консультанта.

        Args:
            industry_id: ID отрасли

        Returns:
            Словарь с контекстом или None
        """
        profile = self.get_profile(industry_id)
        if not profile:
            return None

        return profile.to_context_dict()

    def get_recommended_functions(self, industry_id: str) -> List[Dict[str, Any]]:
        """
        Получить рекомендуемые функции для отрасли.

        Args:
            industry_id: ID отрасли

        Returns:
            Список функций с приоритетами
        """
        profile = self.get_profile(industry_id)
        if not profile:
            return []

        return [
            {
                "name": f.name,
                "priority": f.priority,
                "reason": f.reason
            }
            for f in profile.recommended_functions
        ]

    def get_typical_integrations(self, industry_id: str) -> List[Dict[str, Any]]:
        """
        Получить типичные интеграции для отрасли.

        Args:
            industry_id: ID отрасли

        Returns:
            Список интеграций
        """
        profile = self.get_profile(industry_id)
        if not profile:
            return []

        return [
            {
                "name": i.name,
                "examples": i.examples,
                "priority": i.priority,
                "reason": i.reason
            }
            for i in profile.typical_integrations
        ]

    def get_pain_points(self, industry_id: str) -> List[Dict[str, Any]]:
        """
        Получить типичные боли клиентов.

        Args:
            industry_id: ID отрасли

        Returns:
            Список болей с severity
        """
        profile = self.get_profile(industry_id)
        if not profile:
            return []

        return [
            {
                "description": p.description,
                "severity": p.severity,
                "solution_hint": p.solution_hint
            }
            for p in profile.pain_points
        ]

    def get_industry_faq(self, industry_id: str) -> List[Dict[str, str]]:
        """
        Получить FAQ для отрасли.

        Args:
            industry_id: ID отрасли

        Returns:
            Список FAQ
        """
        profile = self.get_profile(industry_id)
        if not profile:
            return []

        return [
            {
                "question": f.question,
                "answer_template": f.answer_template
            }
            for f in profile.industry_faq
        ]

    def record_learning(self, industry_id: str, insight: str, source: str):
        """
        Записать новый урок в профиль отрасли.

        Args:
            industry_id: ID отрасли
            insight: Текст урока/инсайта
            source: Источник (например: "test_logistics_company")
        """
        profile = self.get_profile(industry_id)
        if not profile:
            logger.warning("Cannot record learning: profile not found", industry_id=industry_id)
            return

        learning = Learning(
            date=datetime.now().strftime("%Y-%m-%d"),
            insight=insight,
            source=source
        )

        profile.learnings.append(learning)
        profile.meta.last_updated = datetime.now().strftime("%Y-%m-%d")

        self.loader.save_profile(profile)

        logger.info(
            "Learning recorded",
            industry_id=industry_id,
            insight=insight[:50] + "..." if len(insight) > 50 else insight
        )

    def record_success(
        self,
        industry_id: str,
        pattern: str,
        source: str
    ):
        """
        Record a successful pattern.

        Args:
            industry_id: Industry ID
            pattern: What worked well
            source: Session ID or test name
        """
        self.record_learning(
            industry_id,
            f"[SUCCESS] {pattern}",
            source
        )

        logger.info(
            "Success recorded",
            industry_id=industry_id,
            pattern=pattern[:50] + "..." if len(pattern) > 50 else pattern
        )

    def get_recent_learnings(
        self,
        industry_id: str,
        limit: int = 10,
        include_success: bool = True
    ) -> List[Learning]:
        """
        Get recent learnings for industry.

        Args:
            industry_id: Industry ID
            limit: Max learnings to return
            include_success: Include [SUCCESS] tagged learnings

        Returns:
            List of Learning objects, newest first
        """
        profile = self.get_profile(industry_id)
        if not profile or not profile.learnings:
            return []

        learnings = list(reversed(profile.learnings))

        if not include_success:
            learnings = [
                l for l in learnings
                if "[SUCCESS]" not in l.insight
            ]

        return learnings[:limit]

    def update_metrics(self, industry_id: str, validation_score: float):
        """
        Обновить метрики после теста.

        Args:
            industry_id: ID отрасли
            validation_score: Результат валидации (0.0 - 1.0)
        """
        profile = self.get_profile(industry_id)
        if not profile:
            logger.warning("Cannot update metrics: profile not found", industry_id=industry_id)
            return

        # Обновляем средний скор
        old_tests = profile.meta.tests_run
        old_avg = profile.meta.avg_validation_score

        new_tests = old_tests + 1
        new_avg = ((old_avg * old_tests) + validation_score) / new_tests

        profile.meta.tests_run = new_tests
        profile.meta.avg_validation_score = round(new_avg, 3)
        profile.meta.last_updated = datetime.now().strftime("%Y-%m-%d")

        self.loader.save_profile(profile)

        logger.info(
            "Metrics updated",
            industry_id=industry_id,
            tests_run=new_tests,
            avg_score=new_avg
        )

    def increment_usage(self, industry_id: str):
        """
        Increment usage counter for industry.

        Called when industry is detected during a session.

        Args:
            industry_id: Industry ID
        """
        self.loader.increment_usage_stats(industry_id)

    def get_all_industries(self) -> List[str]:
        """
        Получить список всех доступных отраслей.

        Returns:
            Список ID отраслей
        """
        return self.loader.get_all_industry_ids()

    def get_industry_summary(self, industry_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить краткую сводку по отрасли.

        Args:
            industry_id: ID отрасли

        Returns:
            Словарь со сводкой
        """
        profile = self.get_profile(industry_id)
        if not profile:
            return None

        return {
            "id": profile.id,
            "version": profile.version,
            "tests_run": profile.meta.tests_run,
            "avg_validation_score": profile.meta.avg_validation_score,
            "pain_points_count": len(profile.pain_points),
            "functions_count": len(profile.recommended_functions),
            "integrations_count": len(profile.typical_integrations),
            "faq_count": len(profile.industry_faq),
            "learnings_count": len(profile.learnings),
        }

    def reload(self):
        """Перезагрузить все данные."""
        self.loader.reload()
        self.matcher.reload()
        logger.info("IndustryKnowledgeManager reloaded")


# Global instance for convenience
_manager: Optional[IndustryKnowledgeManager] = None


def get_knowledge_manager() -> IndustryKnowledgeManager:
    """
    Получить глобальный экземпляр менеджера.

    Returns:
        IndustryKnowledgeManager instance
    """
    global _manager
    if _manager is None:
        _manager = IndustryKnowledgeManager()
    return _manager
