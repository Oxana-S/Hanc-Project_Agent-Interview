"""
LLM Client Factory — единая точка создания LLM клиентов.

Поддерживаемые провайдеры:
  - deepseek: DeepSeek API (deepseek-reasoner, deepseek-chat)
  - azure: Azure OpenAI Chat (gpt-4.1-mini и аналоги)

Использование:
    from src.llm.factory import create_llm_client

    # Из переменной окружения LLM_PROVIDER (по умолчанию "azure")
    client = create_llm_client()

    # Явный выбор провайдера
    client = create_llm_client("deepseek")
    client = create_llm_client("azure")

    # Все клиенты имеют одинаковый интерфейс:
    response = await client.chat(messages=[...], temperature=0.7, max_tokens=8192)
"""

import os
from typing import Optional


def create_llm_client(provider: Optional[str] = None):
    """
    Создать LLM клиент по имени провайдера.

    Args:
        provider: Имя провайдера ("deepseek", "azure").
                  Если не указан — берётся из LLM_PROVIDER env var,
                  по умолчанию "azure".

    Returns:
        Клиент с методом chat(messages, temperature, max_tokens) -> str
    """
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", "azure")

    provider = provider.lower().strip()

    if provider == "deepseek":
        from src.llm.deepseek import DeepSeekClient
        return DeepSeekClient()

    elif provider in ("azure", "azure_openai", "openai"):
        from src.llm.azure_chat import AzureChatClient
        return AzureChatClient()

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported: deepseek, azure"
        )
