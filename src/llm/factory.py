"""
LLM Client Factory — единая точка создания LLM клиентов.

Поддерживаемые провайдеры:
  - deepseek: DeepSeek API (deepseek-reasoner, deepseek-chat)
  - azure: Azure OpenAI Chat (gpt-4.1-mini и аналоги)
  - openai: OpenAI API напрямую (gpt-4.1-mini и аналоги)
  - anthropic: Anthropic Claude (claude-sonnet-4-5 и аналоги)
  - xai: xAI Grok (grok-3-mini и аналоги)

Использование:
    from src.llm.factory import create_llm_client

    # Из переменной окружения LLM_PROVIDER (по умолчанию "deepseek")
    client = create_llm_client()

    # Явный выбор провайдера
    client = create_llm_client("anthropic")

    # Все клиенты имеют одинаковый интерфейс:
    response = await client.chat(messages=[...], temperature=0.7, max_tokens=8192)
"""

import os
from typing import Optional, List, Dict, Any


# Реестр провайдеров: id → (display_name, env_key_var)
_PROVIDER_REGISTRY: List[Dict[str, str]] = [
    {"id": "deepseek", "name": "DeepSeek", "env_key": "DEEPSEEK_API_KEY"},
    {"id": "azure", "name": "Azure GPT", "env_key": "AZURE_CHAT_OPENAI_API_KEY"},
    {"id": "openai", "name": "OpenAI", "env_key": "OPENAI_API_KEY"},
    {"id": "anthropic", "name": "Claude", "env_key": "ANTHROPIC_API_KEY"},
    {"id": "xai", "name": "Grok", "env_key": "XAI_API_KEY"},
]


def create_llm_client(provider: Optional[str] = None):
    """
    Создать LLM клиент по имени провайдера.

    Args:
        provider: Имя провайдера ("deepseek", "azure", "openai", "anthropic", "xai").
                  Если не указан — берётся из LLM_PROVIDER env var,
                  по умолчанию "deepseek".

    Returns:
        Клиент с методом chat(messages, temperature, max_tokens) -> str
    """
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", "deepseek")

    provider = provider.lower().strip()

    if provider == "deepseek":
        from src.llm.deepseek import DeepSeekClient
        return DeepSeekClient()

    elif provider in ("azure", "azure_openai"):
        from src.llm.azure_chat import AzureChatClient
        return AzureChatClient()

    elif provider == "openai":
        from src.llm.openai_client import OpenAICompatibleClient
        return OpenAICompatibleClient(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            endpoint=os.getenv("OPENAI_API_ENDPOINT", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            logger_name="openai",
            env_key="OPENAI_API_KEY",
        )

    elif provider == "anthropic":
        from src.llm.anthropic_client import AnthropicClient
        return AnthropicClient()

    elif provider in ("xai", "grok"):
        from src.llm.openai_client import OpenAICompatibleClient
        return OpenAICompatibleClient(
            api_key=os.getenv("XAI_API_KEY", ""),
            endpoint=os.getenv("XAI_API_ENDPOINT", "https://api.x.ai/v1"),
            model=os.getenv("XAI_MODEL", "grok-3-mini"),
            logger_name="xai",
            env_key="XAI_API_KEY",
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported: deepseek, azure, openai, anthropic, xai"
        )


def get_available_providers() -> Dict[str, Any]:
    """
    Вернуть список провайдеров с информацией о доступности.

    Провайдер считается доступным, если его API ключ задан в .env.

    Returns:
        {"providers": [{"id": "deepseek", "name": "DeepSeek", "available": true}, ...],
         "default": "deepseek"}
    """
    providers = []
    for entry in _PROVIDER_REGISTRY:
        key_value = os.getenv(entry["env_key"], "").strip()
        providers.append({
            "id": entry["id"],
            "name": entry["name"],
            "available": bool(key_value),
        })

    return {
        "providers": providers,
        "default": os.getenv("LLM_PROVIDER", "deepseek"),
    }
