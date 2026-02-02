"""LLM module — клиенты для работы с LLM."""

from src.llm.deepseek import DeepSeekClient
from src.llm.anketa_generator import export_full_anketa

__all__ = [
    "DeepSeekClient",
    "export_full_anketa",
]
