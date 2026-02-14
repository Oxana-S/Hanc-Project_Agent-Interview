"""
YAML Prompt Loader.

Загружает промпты из YAML файлов с поддержкой шаблонизации.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class PromptLoader:
    """Загрузчик промптов из YAML файлов."""

    def __init__(self, base_path: Optional[Path] = None):
        """
        Инициализация загрузчика.

        Args:
            base_path: Базовый путь к директории prompts/
        """
        if base_path is None:
            # Определяем путь относительно корня проекта
            project_root = Path(__file__).parent.parent.parent
            base_path = project_root / "prompts"

        self.base_path = Path(base_path)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, path: str, key: Optional[str] = None) -> Any:
        """
        Получить промпт или его часть.

        Args:
            path: Путь к файлу (без .yaml), например "consultant/discovery"
            key: Ключ внутри файла, например "system_prompt"

        Returns:
            Содержимое промпта или его части
        """
        data = self._load_file(path)

        if key is None:
            return data

        # Поддержка вложенных ключей через точку
        keys = key.split(".")
        result = data
        for k in keys:
            if isinstance(result, dict) and k in result:
                result = result[k]
            else:
                raise KeyError(f"Key '{key}' not found in {path}.yaml")

        return result

    def render(self, path: str, key: str, **variables) -> str:
        """
        Получить промпт с подстановкой переменных.

        Поддерживает простой шаблонный синтаксис:
        - {{variable}} — простая подстановка
        - {{#if condition}}...{{/if}} — условие
        - {{#each items}}...{{/each}} — цикл

        Args:
            path: Путь к файлу
            key: Ключ промпта
            **variables: Переменные для подстановки

        Returns:
            Отрендеренный промпт
        """
        template = self.get(path, key)

        if not isinstance(template, str):
            raise TypeError(f"Expected string template, got {type(template)}")

        return self._render_template(template, variables)

    def _load_file(self, path: str) -> Dict[str, Any]:
        """Загрузить YAML файл с кэшированием."""
        if path in self._cache:
            return self._cache[path]

        file_path = (self.base_path / f"{path}.yaml").resolve()

        # R20-03: Prevent path traversal - resolved path must be under base_path
        if not str(file_path).startswith(str(self.base_path.resolve())):
            raise ValueError(f"Path traversal detected: {path}")

        if not file_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._cache[path] = data
        return data

    def _render_template(self, template: str, variables: Dict[str, Any]) -> str:
        """Простой рендеринг шаблона."""
        result = template

        # Простая подстановка {{variable}}
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value) if value else "")

        # Обработка {{#if condition}}...{{/if}}
        result = self._process_conditionals(result, variables)

        # Обработка {{#each items}}...{{/each}}
        result = self._process_loops(result, variables)

        # Удаляем неподставленные переменные
        result = re.sub(r"\{\{[^}]+\}\}", "", result)

        return result.strip()

    def _process_conditionals(self, template: str, variables: Dict[str, Any]) -> str:
        """Обработка условий {{#if}}...{{/if}}."""
        pattern = r"\{\{#if\s+(\w+)\}\}(.*?)\{\{/if\}\}"

        def replace_if(match):
            condition_var = match.group(1)
            content = match.group(2)

            if variables.get(condition_var):
                return content
            return ""

        return re.sub(pattern, replace_if, template, flags=re.DOTALL)

    def _process_loops(self, template: str, variables: Dict[str, Any]) -> str:
        """Обработка циклов {{#each}}...{{/each}}."""
        pattern = r"\{\{#each\s+(\w+)\}\}(.*?)\{\{/each\}\}"

        def replace_each(match):
            list_var = match.group(1)
            item_template = match.group(2)

            items = variables.get(list_var, [])
            if not isinstance(items, list):
                return ""

            results = []
            for i, item in enumerate(items):
                item_result = item_template
                item_result = item_result.replace("{{@index}}", str(i + 1))

                if isinstance(item, dict):
                    for k, v in item.items():
                        item_result = item_result.replace(f"{{{{this.{k}}}}}", str(v))
                        item_result = item_result.replace(f"{{{{{k}}}}}", str(v))
                else:
                    item_result = item_result.replace("{{this}}", str(item))

                results.append(item_result)

            return "".join(results)

        return re.sub(pattern, replace_each, template, flags=re.DOTALL)

    def clear_cache(self):
        """Очистить кэш загруженных файлов."""
        self._cache.clear()

    def reload(self, path: str) -> Dict[str, Any]:
        """Перезагрузить файл (сбросить кэш)."""
        if path in self._cache:
            del self._cache[path]
        return self._load_file(path)


# Глобальный экземпляр
_default_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """Получить глобальный загрузчик промптов."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


def get_prompt(path: str, key: Optional[str] = None) -> Any:
    """Shortcut для получения промпта."""
    return get_prompt_loader().get(path, key)


def render_prompt(path: str, key: str, **variables) -> str:
    """Shortcut для рендеринга промпта."""
    return get_prompt_loader().render(path, key, **variables)
