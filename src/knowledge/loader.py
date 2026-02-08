"""
Industry Profile Loader - loads YAML profiles with caching.

v1.0: Initial implementation
v2.0: Regional structure support with inheritance
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    # v2.0 models
    SalesScript,
    Competitor,
    ROIExample,
    PricingContext,
    Seasonality,
    MarketContext,
)

logger = structlog.get_logger("knowledge")


class IndustryProfileLoader:
    """
    Загрузчик профилей отраслей из YAML файлов.

    Использует кэширование для повторных запросов.
    Поддерживает региональную структуру и наследование профилей.

    Directory structure:
        config/industries/
        ├── _index.yaml           # Global index
        ├── _countries.yaml       # Country metadata
        ├── _base/                # Base profiles (templates)
        │   ├── automotive.yaml
        │   └── ...
        ├── eu/                   # Europe region
        │   ├── de/              # Germany
        │   │   ├── _meta.yaml   # Country metadata
        │   │   └── automotive.yaml
        │   └── ...
        └── ...
    """

    # Supported regions with their priority (lower = higher priority)
    REGIONS = {
        "eu": 1,      # Europe
        "na": 2,      # North America
        "latam": 3,   # Latin America
        "mena": 4,    # Middle East & North Africa
        "sea": 5,     # Southeast Asia
        "ru": 6,      # Russia (legacy)
    }

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
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl: float = 300.0  # 5 minutes
        self._index: Optional[IndustryIndex] = None
        self._countries_meta: Optional[Dict[str, Any]] = None

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
        # Проверяем кэш с TTL
        now = time.time()
        if industry_id in self._cache:
            cache_age = now - self._cache_time.get(industry_id, 0)
            if cache_age < self._cache_ttl:
                return self._cache[industry_id]
            else:
                logger.debug("Cache expired", industry_id=industry_id, age=cache_age)

        # Загружаем индекс если нужно
        index = self.load_index()

        # Проверяем наличие в индексе
        if industry_id not in index.industries:
            logger.warning("Industry not found in index", industry_id=industry_id)
            return None

        # Получаем путь к файлу
        entry = index.industries[industry_id]
        profile_path = self.config_dir / entry.file

        # Fallback to _base/ directory if not found at root
        if not profile_path.exists():
            base_path = self.config_dir / "_base" / entry.file
            if base_path.exists():
                profile_path = base_path

        # Загружаем YAML
        data = self._load_yaml(profile_path)
        if not data:
            logger.error("Failed to load industry profile", industry_id=industry_id)
            return None

        # Парсим в модель
        try:
            profile = self._parse_profile(data)
            self._cache[industry_id] = profile
            self._cache_time[industry_id] = time.time()

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

    def load_regional_profile(
        self,
        region: str,
        country: str,
        industry_id: str
    ) -> Optional[IndustryProfile]:
        """
        Загрузить региональный профиль с поддержкой наследования.

        Args:
            region: Код региона (eu, na, latam, mena, sea, ru)
            country: Код страны (de, us, br, etc.)
            industry_id: ID отрасли (automotive, medical, etc.)

        Returns:
            IndustryProfile с наследованием от базового профиля или None
        """
        cache_key = f"{region}/{country}/{industry_id}"

        # Check cache
        now = time.time()
        if cache_key in self._cache:
            cache_age = now - self._cache_time.get(cache_key, 0)
            if cache_age < self._cache_ttl:
                return self._cache[cache_key]

        # Build path to regional profile
        profile_path = self.config_dir / region / country / f"{industry_id}.yaml"

        if not profile_path.exists():
            logger.warning(
                "Regional profile not found",
                region=region,
                country=country,
                industry_id=industry_id,
                path=str(profile_path)
            )
            # Fallback to base profile
            return self.load_profile(industry_id)

        # Load regional data
        regional_data = self._load_yaml(profile_path)
        if not regional_data:
            return self.load_profile(industry_id)

        # Check for inheritance
        extends = regional_data.pop("_extends", None)
        base_data: Dict[str, Any] = {}

        if extends:
            # Load base profile
            base_path = self.config_dir / f"{extends}.yaml"
            if not base_path.exists():
                base_path = self.config_dir / "_base" / f"{extends}.yaml"
            base_data = self._load_yaml(base_path)
            if not base_data:
                logger.warning("Base profile not found for inheritance", extends=extends)

        # Merge base + regional (regional overrides base)
        merged_data = self._merge_profiles(base_data, regional_data)

        # Add region/country metadata
        if "meta" not in merged_data:
            merged_data["meta"] = {}
        merged_data["meta"]["region"] = region
        merged_data["meta"]["country"] = country

        # Load country metadata if available
        country_meta = self._load_country_meta(region, country)
        if country_meta:
            if "language" not in merged_data["meta"]:
                merged_data["meta"]["language"] = country_meta.get("language", "en")
            if "phone_codes" not in merged_data["meta"]:
                merged_data["meta"]["phone_codes"] = country_meta.get("phone_codes", [])
            if "currency" not in merged_data["meta"]:
                merged_data["meta"]["currency"] = country_meta.get("currency", "EUR")
            if "timezone" not in merged_data["meta"]:
                merged_data["meta"]["timezone"] = country_meta.get("timezone")

        try:
            profile = self._parse_profile(merged_data)
            self._cache[cache_key] = profile
            self._cache_time[cache_key] = now

            logger.info(
                "Regional profile loaded",
                region=region,
                country=country,
                industry_id=industry_id,
                inherited_from=extends
            )
            return profile

        except Exception as e:
            logger.error(
                "Failed to parse regional profile",
                region=region,
                country=country,
                industry_id=industry_id,
                error=str(e)
            )
            return None

    def _merge_profiles(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge base profile with regional overrides.

        Strategy:
        - Lists: override replaces base (if non-empty)
        - Dicts: deep merge
        - Scalars: override wins
        """
        if not base:
            return override.copy()

        result = base.copy()

        for key, value in override.items():
            if key not in result:
                result[key] = value
            elif isinstance(value, dict) and isinstance(result[key], dict):
                # Deep merge for dicts (like meta, success_benchmarks)
                result[key] = self._merge_profiles(result[key], value)
            elif isinstance(value, list):
                # Lists: use override if non-empty, otherwise keep base
                if value:
                    result[key] = value
            else:
                # Scalars: override wins
                result[key] = value

        return result

    def _load_country_meta(self, region: str, country: str) -> Optional[Dict[str, Any]]:
        """Load country metadata from _meta.yaml."""
        meta_path = self.config_dir / region / country / "_meta.yaml"
        if meta_path.exists():
            return self._load_yaml(meta_path)

        # Try global countries file
        if self._countries_meta is None:
            countries_path = self.config_dir / "_countries.yaml"
            if countries_path.exists():
                self._countries_meta = self._load_yaml(countries_path)
            else:
                self._countries_meta = {}

        # Look up in global countries
        return self._countries_meta.get("countries", {}).get(country)

    def get_available_regions(self) -> List[str]:
        """Get list of available regions."""
        regions = []
        for region in self.REGIONS:
            region_path = self.config_dir / region
            if region_path.exists() and region_path.is_dir():
                regions.append(region)
        return regions

    def get_available_countries(self, region: str) -> List[str]:
        """Get list of available countries in a region."""
        region_path = self.config_dir / region
        if not region_path.exists():
            return []

        countries = []
        for item in region_path.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                countries.append(item.name)
        return sorted(countries)

    def get_regional_industries(self, region: str, country: str) -> List[str]:
        """Get list of available industries for a country."""
        country_path = self.config_dir / region / country
        if not country_path.exists():
            return []

        industries = []
        for item in country_path.glob("*.yaml"):
            if not item.name.startswith("_"):
                industries.append(item.stem)
        return sorted(industries)

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

        # ====== v2.0 fields ======

        # Парсим sales_scripts
        sales_scripts = [
            SalesScript(**s)
            for s in data.get("sales_scripts", [])
            if isinstance(s, dict)
        ]

        # Парсим competitors
        competitors = [
            Competitor(**c)
            for c in data.get("competitors", [])
            if isinstance(c, dict)
        ]

        # Парсим pricing_context
        pricing_data = data.get("pricing_context")
        pricing_context = None
        if pricing_data:
            # Parse nested ROIExample objects
            if "roi_examples" in pricing_data:
                pricing_data["roi_examples"] = [
                    ROIExample(**r) if isinstance(r, dict) else r
                    for r in pricing_data["roi_examples"]
                ]
            pricing_context = PricingContext(**pricing_data)

        # Парсим market_context
        market_data = data.get("market_context")
        market_context = None
        if market_data:
            # Parse nested Seasonality
            if "seasonality" in market_data and isinstance(market_data["seasonality"], dict):
                market_data["seasonality"] = Seasonality(**market_data["seasonality"])
            market_context = MarketContext(**market_data)

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
            # v2.0 fields
            sales_scripts=sales_scripts,
            competitors=competitors,
            pricing_context=pricing_context,
            market_context=market_context,
        )

    def get_all_industry_ids(self) -> list[str]:
        """Получить список всех ID отраслей."""
        index = self.load_index()
        return list(index.industries.keys())

    def reload(self):
        """Перезагрузить все данные (очистить кэш)."""
        self.invalidate_cache()
        logger.info("Industry cache cleared")

    def invalidate_cache(self, industry_id: Optional[str] = None):
        """
        Инвалидировать кэш профиля или всех профилей.

        Args:
            industry_id: ID отрасли или None для всех
        """
        if industry_id is None:
            self._cache.clear()
            self._cache_time.clear()
            self._index = None
            logger.debug("All industry cache invalidated")
        elif industry_id in self._cache:
            del self._cache[industry_id]
            self._cache_time.pop(industry_id, None)
            logger.debug("Industry cache invalidated", industry_id=industry_id)

    def save_profile(
        self,
        profile: IndustryProfile,
        region: Optional[str] = None,
        country: Optional[str] = None
    ):
        """
        Сохранить профиль обратно в YAML файл.

        Используется для обновления learnings и метрик.

        Args:
            profile: Профиль для сохранения
            region: Код региона (для региональных профилей)
            country: Код страны (для региональных профилей)
        """
        # Determine path based on region/country
        if region and country:
            profile_dir = self.config_dir / region / country
            profile_dir.mkdir(parents=True, exist_ok=True)
            profile_path = profile_dir / f"{profile.id}.yaml"
            cache_key = f"{region}/{country}/{profile.id}"
        else:
            profile_path = self.config_dir / f"{profile.id}.yaml"
            cache_key = profile.id

        # Конвертируем в словарь
        data = {
            "meta": profile.meta.model_dump(exclude_none=True),
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

        # v2.0 fields
        if profile.sales_scripts:
            data["sales_scripts"] = [s.model_dump() for s in profile.sales_scripts]

        if profile.competitors:
            data["competitors"] = [c.model_dump() for c in profile.competitors]

        if profile.pricing_context:
            data["pricing_context"] = profile.pricing_context.model_dump()

        if profile.market_context:
            data["market_context"] = profile.market_context.model_dump()

        self._save_yaml(profile_path, data)

        # Обновляем кэш
        self._cache[cache_key] = profile
        self._cache_time[cache_key] = time.time()

        logger.info(
            "Industry profile saved",
            industry_id=profile.id,
            region=region,
            country=country
        )

    def increment_usage_stats(self, industry_id: str):
        """
        Update usage stats in _index.yaml.

        Args:
            industry_id: Industry ID to increment
        """
        index_path = self.config_dir / "_index.yaml"
        data = self._load_yaml(index_path)

        if not data:
            logger.warning("Cannot update usage stats: index not found")
            return

        # Ensure usage_stats section exists
        if "usage_stats" not in data:
            data["usage_stats"] = {
                "total_tests": 0,
                "last_test_date": None,
                "most_used_industry": None,
                "industry_usage": {}
            }

        stats = data["usage_stats"]

        # Ensure industry_usage exists
        if "industry_usage" not in stats:
            stats["industry_usage"] = {}

        # Increment counters
        stats["total_tests"] = stats.get("total_tests", 0) + 1
        stats["last_test_date"] = datetime.now().strftime("%Y-%m-%d")

        # Increment industry-specific counter
        industry_usage = stats["industry_usage"]
        industry_usage[industry_id] = industry_usage.get(industry_id, 0) + 1

        # Update most_used_industry
        if industry_usage:
            most_used = max(industry_usage.items(), key=lambda x: x[1])
            stats["most_used_industry"] = most_used[0]

        # Save
        self._save_yaml(index_path, data)

        logger.debug(
            "Usage stats updated",
            industry_id=industry_id,
            total_tests=stats["total_tests"]
        )
