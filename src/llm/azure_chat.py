"""
Azure OpenAI Chat клиент.

Drop-in replacement для DeepSeekClient с тем же интерфейсом chat().
Использует Azure OpenAI Chat Completions API (gpt-4.1-mini и аналоги).
"""

import os
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("azure_chat")

MAX_RETRIES = 3
RETRY_DELAY = 2.0


class AzureChatClient:
    """Клиент для Azure OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment: Optional[str] = None,
        api_version: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("AZURE_CHAT_OPENAI_API_KEY")
        self.endpoint = (endpoint or os.getenv("AZURE_CHAT_OPENAI_ENDPOINT", "")).rstrip("/")
        self.deployment = deployment or os.getenv("AZURE_CHAT_OPENAI_DEPLOYMENT_NAME")
        self.api_version = api_version or os.getenv("AZURE_CHAT_OPENAI_API_VERSION", "2024-12-01-preview")

        if not self.api_key:
            raise ValueError("AZURE_CHAT_OPENAI_API_KEY not set")
        if not self.endpoint:
            raise ValueError("AZURE_CHAT_OPENAI_ENDPOINT not set")
        if not self.deployment:
            raise ValueError("AZURE_CHAT_OPENAI_DEPLOYMENT_NAME not set")

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
        timeout: float = 180.0
    ) -> str:
        """
        Отправить запрос к Azure OpenAI Chat Completions API.

        Интерфейс совместим с DeepSeekClient.chat().
        """
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if top_p is not None:
            payload["top_p"] = top_p

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._make_request(url, headers, payload, timeout)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Rate limit hit, retrying (attempt {attempt + 1}, wait {wait_time}s)"
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

    async def _make_request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float
    ) -> str:
        """Выполнить HTTP запрос к Azure OpenAI API."""
        client = self._get_http_client()
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason", "unknown")
            content = choice["message"]["content"] or ""

            if not content:
                logger.warning(
                    f"Azure returned empty content (finish_reason={finish_reason})"
                )
            elif finish_reason == "length":
                logger.warning(
                    f"Azure response truncated (content_length={len(content)})"
                )

            return content

        except httpx.HTTPStatusError as e:
            detail = (e.response.text or "")[:200]
            logger.error(f"Azure API error: status={e.response.status_code}, detail={detail}")
            raise
        except Exception as e:
            logger.error(f"Azure request failed: {e}")
            raise
