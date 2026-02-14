"""
Anthropic Claude LLM клиент.

Использует Anthropic Messages API (https://api.anthropic.com/v1/messages).
API формат отличается от OpenAI:
  - Авторизация: x-api-key + anthropic-version
  - System prompt — отдельное поле, НЕ сообщение с role="system"
  - Ответ: {"content": [{"type": "text", "text": "..."}]}

Клиент конвертирует OpenAI-стиль сообщений в формат Anthropic внутри,
чтобы вызывающий код не менялся.
"""

import os
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("anthropic")

MAX_RETRIES = 3
RETRY_DELAY = 2.0

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicClient:
    """Клиент для Anthropic Messages API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self._http_client: Optional[httpx.AsyncClient] = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create a reusable httpx client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
            )
        return self._http_client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        top_p: Optional[float] = None,
        timeout: float = 180.0,
    ) -> str:
        """
        Отправить запрос к Anthropic Messages API.

        Интерфейс совместим с DeepSeekClient.chat() и AzureChatClient.chat().
        Внутри конвертирует сообщения из OpenAI-формата в Anthropic-формат.
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        # Конвертация: извлечь system message из списка
        system_text, anthropic_messages = self._convert_messages(messages)

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
        }

        if system_text:
            payload["system"] = system_text

        if temperature is not None:
            payload["temperature"] = temperature

        if top_p is not None:
            payload["top_p"] = top_p

        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._make_request(headers, payload, timeout)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Rate limit hit, retrying (attempt {attempt + 1}, wait {wait_time}s)"
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                elif e.response.status_code == 529:  # Anthropic overloaded
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Anthropic overloaded, retrying (attempt {attempt + 1}, wait {wait_time}s)"
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.warning(
                    f"Request failed ({e}), retrying (attempt {attempt + 1}, wait {wait_time}s)"
                )
                await asyncio.sleep(wait_time)
                last_error = e

        raise last_error or Exception("All retry attempts failed")

    @staticmethod
    def _convert_messages(
        messages: List[Dict[str, str]],
    ) -> tuple:
        """
        Конвертация OpenAI-формата сообщений в Anthropic-формат.

        OpenAI: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        Anthropic: system="...", messages=[{"role": "user", "content": "..."}]

        Returns: (system_text, anthropic_messages)
        """
        system_parts = []
        anthropic_msgs = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(content)
            elif role in ("user", "assistant"):
                anthropic_msgs.append({"role": role, "content": content})

        system_text = "\n\n".join(system_parts) if system_parts else ""
        return system_text, anthropic_msgs

    async def _make_request(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> str:
        """Выполнить HTTP запрос к Anthropic Messages API."""
        client = self._get_http_client()
        try:
            response = await client.post(
                ANTHROPIC_API_URL, headers=headers, json=payload, timeout=timeout
            )
            response.raise_for_status()

            data = response.json()

            # Anthropic ответ: {"content": [{"type": "text", "text": "..."}], "stop_reason": "..."}
            content_blocks = data.get("content", [])
            text_parts = [
                block["text"]
                for block in content_blocks
                if block.get("type") == "text"
            ]
            content = "\n".join(text_parts)

            stop_reason = data.get("stop_reason", "unknown")

            if not content:
                logger.warning(
                    f"Anthropic returned empty content (stop_reason={stop_reason})"
                )
            elif stop_reason == "max_tokens":
                logger.warning(
                    f"Anthropic response truncated (content_length={len(content)})"
                )

            return content

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Anthropic API error: status={e.response.status_code}, detail={e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"Anthropic request failed: {e}")
            raise
