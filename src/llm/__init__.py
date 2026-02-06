"""LLM module — клиенты для работы с LLM."""

from src.llm.deepseek import DeepSeekClient
from src.llm.anketa_generator import LLMAnketaGenerator

__all__ = [
    "DeepSeekClient",
    "LLMAnketaGenerator",
]
