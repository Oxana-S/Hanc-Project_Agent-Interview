"""
YAML Locale Loader.

Загружает локализованные тексты из YAML файлов.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class LocaleLoader:
    """Загрузчик локализации из YAML файлов."""

    def __init__(
        self,
        base_path: Optional[Path] = None,
        default_locale: str = "ru"
    ):
        """
        Инициализация загрузчика.

        Args:
            base_path: Базовый путь к директории locales/
            default_locale: Локаль по умолчанию
        """
        if base_path is None:
            project_root = Path(__file__).parent.parent.parent
            base_path = project_root / "locales"

        self.base_path = Path(base_path)
        self.default_locale = default_locale
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(
        self,
        key: str,
        locale: Optional[str] = None,
        file: str = "ui",
        **variables
    ) -> str:
        """
        Получить локализованный текст.

        Args:
            key: Ключ текста (поддерживает точечную нотацию)
            locale: Локаль (ru, en). Если None — используется default_locale
            file: Имя файла без .yaml (ui, errors, etc.)
            **variables: Переменные для подстановки

        Returns:
            Локализованный текст

        Example:
            loader.get("phases.discovery.title")  # -> "Знакомство с бизнесом"
            loader.get("errors.api_error", message="timeout")  # -> "Ошибка API: timeout"
        """
        locale = locale or self.default_locale
        data = self._load_file(locale, file)

        # Навигация по вложенным ключам
        keys = key.split(".")
        result = data
        for k in keys:
            if isinstance(result, dict) and k in result:
                result = result[k]
            else:
                # Fallback на default_locale если не найдено
                if locale != self.default_locale:
                    return self.get(key, self.default_locale, file, **variables)
                raise KeyError(f"Locale key '{key}' not found in {locale}/{file}.yaml")

        if not isinstance(result, str):
            return str(result)

        # Подстановка переменных
        for var_key, var_value in variables.items():
            result = result.replace(f"{{{{{var_key}}}}}", str(var_value))

        return result

    def get_dict(
        self,
        key: str,
        locale: Optional[str] = None,
        file: str = "ui"
    ) -> Dict[str, Any]:
        """
        Получить словарь локализованных текстов.

        Args:
            key: Ключ секции
            locale: Локаль
            file: Имя файла

        Returns:
            Словарь текстов
        """
        locale = locale or self.default_locale
        data = self._load_file(locale, file)

        keys = key.split(".")
        result = data
        for k in keys:
            if isinstance(result, dict) and k in result:
                result = result[k]
            else:
                raise KeyError(f"Locale key '{key}' not found")

        return result if isinstance(result, dict) else {key: result}

    def _load_file(self, locale: str, file: str) -> Dict[str, Any]:
        """Загрузить YAML файл с кэшированием."""
        cache_key = f"{locale}/{file}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = self.base_path / locale / f"{file}.yaml"

        if not file_path.exists():
            raise FileNotFoundError(f"Locale file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._cache[cache_key] = data
        return data

    def set_locale(self, locale: str):
        """Установить локаль по умолчанию."""
        self.default_locale = locale

    def get_available_locales(self) -> list:
        """Получить список доступных локалей."""
        return [d.name for d in self.base_path.iterdir() if d.is_dir()]

    def clear_cache(self):
        """Очистить кэш."""
        self._cache.clear()


# Глобальный экземпляр
_default_loader: Optional[LocaleLoader] = None


def get_locale_loader() -> LocaleLoader:
    """Получить глобальный загрузчик локализации."""
    global _default_loader
    if _default_loader is None:
        _default_loader = LocaleLoader()
    return _default_loader


def t(key: str, **variables) -> str:
    """
    Shortcut для получения локализованного текста.

    Example:
        t("phases.discovery.title")
        t("errors.api_error", message="timeout")
    """
    return get_locale_loader().get(key, **variables)


def set_locale(locale: str):
    """Установить глобальную локаль."""
    get_locale_loader().set_locale(locale)
