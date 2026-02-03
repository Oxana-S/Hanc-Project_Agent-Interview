"""
Synonym Loader - загружает словари синонимов из YAML.

v3.2: Вынесение словарей из кода в конфигурационные файлы.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

import structlog

logger = structlog.get_logger()


class SynonymLoader:
    """Загрузчик словарей синонимов из YAML файлов."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Инициализация загрузчика.

        Args:
            config_path: Путь к файлу synonyms.yaml.
                        Если None - ищет в config/synonyms.yaml
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "synonyms.yaml"

        self.config_path = Path(config_path)
        self._cache: Optional[Dict[str, Any]] = None
        self._loaded = False

    def _load(self) -> Dict[str, Any]:
        """Загрузить конфигурацию с кэшированием."""
        if self._cache is not None:
            return self._cache

        if not self.config_path.exists():
            logger.warning(
                "Synonyms config not found, using defaults",
                path=str(self.config_path)
            )
            return self._get_defaults()

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._cache = yaml.safe_load(f)
                self._loaded = True
                logger.info(
                    "Synonyms loaded from YAML",
                    path=str(self.config_path),
                    version=self._cache.get("meta", {}).get("version", "unknown")
                )
                return self._cache
        except Exception as e:
            logger.error("Failed to load synonyms", error=str(e))
            return self._get_defaults()

    def _get_defaults(self) -> Dict[str, Any]:
        """Возвращает минимальные дефолтные словари."""
        return {
            "industries": {
                "медицина": ["медицина", "healthcare", "medical"],
                "wellness": ["wellness", "массаж", "спа"],
                "it": ["it", "software", "tech"],
            },
            "functions": {
                "запись": ["запись", "booking", "бронирование"],
                "поддержка": ["поддержка", "support", "помощь"],
                "faq": ["faq", "частые вопросы", "справка"],
            },
            "integrations": {
                "crm": ["crm", "битрикс", "amocrm"],
                "телефония": ["телефония", "атс", "pbx"],
            }
        }

    def get_industries(self) -> Dict[str, List[str]]:
        """Получить словарь отраслей."""
        data = self._load()
        return data.get("industries", {})

    def get_functions(self) -> Dict[str, List[str]]:
        """Получить словарь функций."""
        data = self._load()
        return data.get("functions", {})

    def get_integrations(self) -> Dict[str, List[str]]:
        """Получить словарь интеграций."""
        data = self._load()
        return data.get("integrations", {})

    def get_all(self) -> Dict[str, Dict[str, List[str]]]:
        """Получить все словари."""
        data = self._load()
        return {
            "industries": data.get("industries", {}),
            "functions": data.get("functions", {}),
            "integrations": data.get("integrations", {}),
        }

    def reload(self):
        """Перезагрузить конфигурацию."""
        self._cache = None
        self._loaded = False
        self._load()

    @property
    def is_loaded(self) -> bool:
        """Проверить, загружена ли конфигурация из файла."""
        return self._loaded


# Глобальный экземпляр
_default_loader: Optional[SynonymLoader] = None


def get_synonym_loader() -> SynonymLoader:
    """Получить глобальный загрузчик синонимов."""
    global _default_loader
    if _default_loader is None:
        _default_loader = SynonymLoader()
    return _default_loader


def get_industry_synonyms() -> Dict[str, List[str]]:
    """Shortcut для получения словаря отраслей."""
    return get_synonym_loader().get_industries()


def get_function_synonyms() -> Dict[str, List[str]]:
    """Shortcut для получения словаря функций."""
    return get_synonym_loader().get_functions()


def get_integration_synonyms() -> Dict[str, List[str]]:
    """Shortcut для получения словаря интеграций."""
    return get_synonym_loader().get_integrations()
