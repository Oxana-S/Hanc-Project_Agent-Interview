"""
Industry Profile Loader - loads YAML profiles with caching.

v1.0: Initial implementation
"""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
import structlog

from .models import (
    IndustryProfile,
    IndustryIndex,
    IndustryMeta,
    PainPoint,
    RecommendedFunction,
    TypicalIntegration,
    IndustryFAQ,
    TypicalObjection,
    Learning,
    SuccessBenchmarks,
    IndustrySpecifics,
)

logger = structlog.get_logger("knowledge")


class IndustryProfileLoader:
    """
    Загрузчик профилей отраслей из YAML файлов.

    Использует кэширование для повторных запросов.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Инициализация загрузчика.

        Args:
            config_dir: Путь к директории config/industries/
                       Если None — ищет в config/industries/
        """
        if config_dir is None:
            project_root = Path(__file__).parent.parent.parent
            config_dir = project_root / "config" / "industries"

        self.config_dir = Path(config_dir)
        self._cache: Dict[str, IndustryProfile] = {}
        self._index: Optional[IndustryIndex] = None

        logger.debug("IndustryProfileLoader initialized", config_dir=str(self.config_dir))

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Загрузить YAML файл."""
        if not path.exists():
            logger.warning("YAML file not found", path=str(path))
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to load YAML", path=str(path), error=str(e))
            return {}

    def _save_yaml(self, path: Path, data: Dict[str, Any]):
        """Сохранить YAML файл."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            logger.debug("YAML saved", path=str(path))
        except Exception as e:
            logger.error("Failed to save YAML", path=str(path), error=str(e))

    def load_index(self) -> IndustryIndex:
        """
        Загрузить индекс отраслей.

        Returns:
            IndustryIndex с информацией о всех отраслях
        """
        if self._index is not None:
            return self._index

        index_path = self.config_dir / "_index.yaml"
        data = self._load_yaml(index_path)

        if not data:
            logger.warning("Industry index is empty or not found")
            return IndustryIndex()

        self._index = IndustryIndex(**data)
        logger.info("Industry index loaded", industries_count=len(self._index.industries))

        return self._index

    def load_profile(self, industry_id: str) -> Optional[IndustryProfile]:
        """
        Загрузить профиль отрасли по ID.

        Args:
            industry_id: ID отрасли (например: "logistics", "medical")

        Returns:
            IndustryProfile или None если не найден
        """
        # Проверяем кэш
        if industry_id in self._cache:
            return self._cache[industry_id]

        # Загружаем индекс если нужно
        index = self.load_index()

        # Проверяем наличие в индексе
        if industry_id not in index.industries:
            logger.warning("Industry not found in index", industry_id=industry_id)
            return None

        # Получаем путь к файлу
        entry = index.industries[industry_id]
        profile_path = self.config_dir / entry.file

        # Загружаем YAML
        data = self._load_yaml(profile_path)
        if not data:
            logger.error("Failed to load industry profile", industry_id=industry_id)
            return None

        # Парсим в модель
        try:
            profile = self._parse_profile(data)
            self._cache[industry_id] = profile

            logger.info(
                "Industry profile loaded",
                industry_id=industry_id,
                pain_points=len(profile.pain_points),
                functions=len(profile.recommended_functions)
            )

            return profile

        except Exception as e:
            logger.error(
                "Failed to parse industry profile",
                industry_id=industry_id,
                error=str(e)
            )
            return None

    def _parse_profile(self, data: Dict[str, Any]) -> IndustryProfile:
        """Распарсить данные YAML в IndustryProfile."""
        # Парсим meta
        meta_data = data.get("meta", {})
        meta = IndustryMeta(**meta_data)

        # Парсим pain_points
        pain_points = [
            PainPoint(**p) if isinstance(p, dict) else PainPoint(description=str(p))
            for p in data.get("pain_points", [])
        ]

        # Парсим recommended_functions
        functions = [
            RecommendedFunction(**f) if isinstance(f, dict) else RecommendedFunction(name=str(f))
            for f in data.get("recommended_functions", [])
        ]

        # Парсим typical_integrations
        integrations = [
            TypicalIntegration(**i) if isinstance(i, dict) else TypicalIntegration(name=str(i))
            for i in data.get("typical_integrations", [])
        ]

        # Парсим industry_faq
        faq = [
            IndustryFAQ(**f)
            for f in data.get("industry_faq", [])
            if isinstance(f, dict)
        ]

        # Парсим typical_objections
        objections = [
            TypicalObjection(**o)
            for o in data.get("typical_objections", [])
            if isinstance(o, dict)
        ]

        # Парсим learnings
        learnings = [
            Learning(**l)
            for l in data.get("learnings", [])
            if isinstance(l, dict)
        ]

        # Парсим success_benchmarks
        benchmarks_data = data.get("success_benchmarks", {})
        benchmarks = SuccessBenchmarks(**benchmarks_data) if benchmarks_data else SuccessBenchmarks()

        # Парсим industry_specifics
        specifics_data = data.get("industry_specifics")
        specifics = IndustrySpecifics(**specifics_data) if specifics_data else None

        return IndustryProfile(
            meta=meta,
            aliases=data.get("aliases", []),
            typical_services=data.get("typical_services", []),
            pain_points=pain_points,
            recommended_functions=functions,
            typical_integrations=integrations,
            industry_faq=faq,
            typical_objections=objections,
            learnings=learnings,
            success_benchmarks=benchmarks,
            industry_specifics=specifics,
        )

    def get_all_industry_ids(self) -> list[str]:
        """Получить список всех ID отраслей."""
        index = self.load_index()
        return list(index.industries.keys())

    def reload(self):
        """Перезагрузить все данные (очистить кэш)."""
        self._cache.clear()
        self._index = None
        logger.info("Industry cache cleared")

    def save_profile(self, profile: IndustryProfile):
        """
        Сохранить профиль обратно в YAML файл.

        Используется для обновления learnings и метрик.

        Args:
            profile: Профиль для сохранения
        """
        profile_path = self.config_dir / f"{profile.id}.yaml"

        # Конвертируем в словарь
        data = {
            "meta": profile.meta.model_dump(),
            "aliases": profile.aliases,
            "typical_services": profile.typical_services,
            "pain_points": [p.model_dump() for p in profile.pain_points],
            "recommended_functions": [f.model_dump() for f in profile.recommended_functions],
            "typical_integrations": [i.model_dump() for i in profile.typical_integrations],
            "industry_faq": [f.model_dump() for f in profile.industry_faq],
            "typical_objections": [o.model_dump() for o in profile.typical_objections],
            "learnings": [l.model_dump() for l in profile.learnings],
            "success_benchmarks": profile.success_benchmarks.model_dump(),
        }

        if profile.industry_specifics:
            data["industry_specifics"] = profile.industry_specifics.model_dump()

        self._save_yaml(profile_path, data)

        # Обновляем кэш
        self._cache[profile.id] = profile

        logger.info("Industry profile saved", industry_id=profile.id)
