"""
OpenAI-совместимый LLM клиент.

Базовый клиент для всех провайдеров с OpenAI-совместимым API:
  - OpenAI (https://api.openai.com/v1)
  - DeepSeek (https://api.deepseek.com/v1)
  - xAI Grok (https://api.x.ai/v1)

Все используют Bearer-авторизацию и одинаковый формат запросов/ответов.
"""

import asyncio
import logging
import httpx
from typing import Optional, Dict, Any, List

MAX_RETRIES = 3
RETRY_DELAY = 2.0


class OpenAICompatibleClient:
    """Универсальный клиент для OpenAI-совместимых API."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model: str,
        logger_name: str = "openai_compat",
        env_key: str = "API_KEY",
    ):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._log = logging.getLogger(logger_name)
        self._http_client: Optional[httpx.AsyncClient] = None

        if not self.api_key:
            raise ValueError(f"{logger_name}: API key not set (set {env_key})")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        top_p: Optional[float] = None,
        timeout: float = 180.0,
    ) -> str:
        """
        Отправить запрос к Chat Completions API.

        Интерфейс совместим с DeepSeekClient.chat() и AzureChatClient.chat().
        """
        url = f"{self.endpoint}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if top_p is not None:
            payload["top_p"] = top_p

        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._make_request(url, headers, payload, timeout)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    self._log.warning(
                        f"Rate limit hit, retrying (attempt {attempt + 1}, wait {wait_time}s)"
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                wait_time = RETRY_DELAY * (2 ** attempt)
                self._log.warning(
                    f"Request failed ({e}), retrying (attempt {attempt + 1}, wait {wait_time}s)"
                )
                await asyncio.sleep(wait_time)
                last_error = e

        raise last_error or Exception("All retry attempts failed")

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create a reusable httpx client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
            )
        return self._http_client

    async def _make_request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> str:
        """Выполнить HTTP запрос к API."""
        client = self._get_http_client()
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason", "unknown")
            content = choice["message"]["content"] or ""

            if not content:
                self._log.warning(
                    f"Empty content (finish_reason={finish_reason}, usage={data.get('usage', {})})"
                )
            elif finish_reason == "length":
                self._log.warning(
                    f"Response truncated (content_length={len(content)}, usage={data.get('usage', {})})"
                )

            return content

        except httpx.HTTPStatusError as e:
            detail = (e.response.text or "")[:200]
            self._log.error(f"API error: status={e.response.status_code}, detail={detail}")
            raise
        except Exception as e:
            self._log.error(f"Request failed: {e}")
            raise
