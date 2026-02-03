"""
Configuration loaders for prompts, locales, and synonyms.

v3.2: Added SynonymLoader for loading synonym dictionaries from YAML.
"""

from src.config.prompt_loader import PromptLoader, get_prompt, render_prompt
from src.config.locale_loader import LocaleLoader, t, set_locale
from src.config.synonym_loader import (
    SynonymLoader,
    get_synonym_loader,
    get_industry_synonyms,
    get_function_synonyms,
    get_integration_synonyms,
)

__all__ = [
    # Prompt loader
    "PromptLoader",
    "get_prompt",
    "render_prompt",
    # Locale loader
    "LocaleLoader",
    "t",
    "set_locale",
    # Synonym loader (v3.2)
    "SynonymLoader",
    "get_synonym_loader",
    "get_industry_synonyms",
    "get_function_synonyms",
    "get_integration_synonyms",
]
