"""
Synonym Loader - загружает словари синонимов из YAML.

v3.3: Multi-language support
- base.yaml: universal technical terms
- {lang}.yaml: language-specific synonyms
- Deep merge: language extends/overrides base
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

import structlog

logger = structlog.get_logger("config")


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    For lists: concatenate and deduplicate.
    For dicts: recursively merge.
    For other types: override wins.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            elif isinstance(result[key], list) and isinstance(value, list):
                # Concatenate lists and remove duplicates while preserving order
                seen = set()
                merged = []
                for item in result[key] + value:
                    item_lower = item.lower() if isinstance(item, str) else item
                    if item_lower not in seen:
                        seen.add(item_lower)
                        merged.append(item)
                result[key] = merged
            else:
                result[key] = value
        else:
            result[key] = value

    return result


class SynonymLoader:
    """
    Загрузчик словарей синонимов из YAML файлов.

    v3.3: Multi-language architecture
    - Loads base.yaml (universal terms)
    - Loads {language}.yaml (language-specific)
    - Merges them with language taking priority
    """

    # Supported languages
    SUPPORTED_LANGUAGES = ["ru", "en"]
    DEFAULT_LANGUAGE = "ru"

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        language: str = DEFAULT_LANGUAGE
    ):
        """
        Инициализация загрузчика.

        Args:
            config_dir: Путь к директории с файлами synonyms/.
                        Если None - ищет в config/synonyms/
            language: Код языка (ru, en). По умолчанию - ru.
        """
        if config_dir is None:
            project_root = Path(__file__).parent.parent.parent
            config_dir = project_root / "config" / "synonyms"

        self.config_dir = Path(config_dir)
        self.language = language if language in self.SUPPORTED_LANGUAGES else self.DEFAULT_LANGUAGE

        self._cache: Optional[Dict[str, Any]] = None
        self._loaded = False
        self._loaded_language: Optional[str] = None

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load a single YAML file."""
        if not path.exists():
            logger.debug("YAML file not found", path=str(path))
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to load YAML", path=str(path), error=str(e))
            return {}

    def _load(self) -> Dict[str, Any]:
        """
        Загрузить конфигурацию с кэшированием.

        Порядок загрузки:
        1. base.yaml (универсальные термины)
        2. {language}.yaml (языковые синонимы)
        3. Deep merge
        """
        # Return cached if same language
        if self._cache is not None and self._loaded_language == self.language:
            return self._cache

        # Check if new directory structure exists
        base_path = self.config_dir / "base.yaml"
        lang_path = self.config_dir / f"{self.language}.yaml"

        if base_path.exists() or lang_path.exists():
            # New v3.3 structure
            base_data = self._load_yaml(base_path)
            lang_data = self._load_yaml(lang_path)

            # Merge: base + language (language overrides)
            self._cache = deep_merge(base_data, lang_data)
            self._loaded = True
            self._loaded_language = self.language

            logger.info(
                "Synonyms loaded (multi-language)",
                language=self.language,
                base_path=str(base_path),
                lang_path=str(lang_path),
                version=self._cache.get("meta", {}).get("version", "unknown")
            )
            return self._cache

        # Fallback: try old single-file structure (config/synonyms.yaml)
        old_path = self.config_dir.parent / "synonyms.yaml"
        if old_path.exists():
            logger.warning(
                "Using legacy synonyms.yaml - consider migrating to multi-language",
                path=str(old_path)
            )
            self._cache = self._load_yaml(old_path)
            self._loaded = True
            self._loaded_language = self.language
            return self._cache

        # No files found - return defaults
        logger.warning(
            "No synonym files found, using defaults",
            config_dir=str(self.config_dir)
        )
        return self._get_defaults()

    def _get_defaults(self) -> Dict[str, Any]:
        """Возвращает минимальные дефолтные словари."""
        return {
            "meta": {"version": "default", "language": self.language},
            "industries": {
                "медицина": ["медицина", "healthcare", "medical"],
                "wellness": ["wellness", "массаж", "спа"],
                "it": ["it", "software", "tech"],
            },
            "functions": {
                "запись": ["запись", "booking", "бронирование"],
                "статус": ["статус", "status", "отслеживание", "tracking"],
                "поддержка": ["поддержка", "support", "помощь"],
                "faq": ["faq", "частые вопросы", "справка"],
            },
            "integrations": {
                "crm": ["crm", "битрикс", "amocrm"],
                "телефония": ["телефония", "атс", "pbx"],
                "sms": ["sms", "смс"],
            }
        }

    def set_language(self, language: str):
        """
        Change the language and reload synonyms.

        Args:
            language: Language code (ru, en)
        """
        if language not in self.SUPPORTED_LANGUAGES:
            logger.warning(
                "Unsupported language, using default",
                requested=language,
                default=self.DEFAULT_LANGUAGE
            )
            language = self.DEFAULT_LANGUAGE

        if language != self.language:
            self.language = language
            self._cache = None  # Force reload
            self._load()

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

    def get_canonical_mapping(self) -> Dict[str, List[str]]:
        """Получить маппинг канонических ключей (для кросс-языкового матчинга)."""
        data = self._load()
        return data.get("canonical_mapping", {})

    def get_all(self) -> Dict[str, Dict[str, List[str]]]:
        """Получить все словари."""
        data = self._load()
        return {
            "industries": data.get("industries", {}),
            "functions": data.get("functions", {}),
            "integrations": data.get("integrations", {}),
        }

    def get_meta(self) -> Dict[str, Any]:
        """Получить метаданные словаря."""
        data = self._load()
        return data.get("meta", {})

    def reload(self):
        """Перезагрузить конфигурацию."""
        self._cache = None
        self._loaded = False
        self._loaded_language = None
        self._load()

    @property
    def is_loaded(self) -> bool:
        """Проверить, загружена ли конфигурация из файла."""
        return self._loaded

    @property
    def current_language(self) -> str:
        """Текущий язык."""
        return self.language


# ============================================================================
# GLOBAL INSTANCE MANAGEMENT
# ============================================================================

# Global instances per language
_loaders: Dict[str, SynonymLoader] = {}


def get_synonym_loader(language: str = "ru") -> SynonymLoader:
    """
    Получить загрузчик синонимов для указанного языка.

    Args:
        language: Код языка (ru, en)

    Returns:
        SynonymLoader instance for the specified language
    """
    global _loaders

    if language not in SynonymLoader.SUPPORTED_LANGUAGES:
        language = SynonymLoader.DEFAULT_LANGUAGE

    if language not in _loaders:
        _loaders[language] = SynonymLoader(language=language)

    return _loaders[language]


def get_industry_synonyms(language: str = "ru") -> Dict[str, List[str]]:
    """Shortcut для получения словаря отраслей."""
    return get_synonym_loader(language).get_industries()


def get_function_synonyms(language: str = "ru") -> Dict[str, List[str]]:
    """Shortcut для получения словаря функций."""
    return get_synonym_loader(language).get_functions()


def get_integration_synonyms(language: str = "ru") -> Dict[str, List[str]]:
    """Shortcut для получения словаря интеграций."""
    return get_synonym_loader(language).get_integrations()


def reload_all_loaders():
    """Перезагрузить все загрузчики."""
    global _loaders
    for loader in _loaders.values():
        loader.reload()
