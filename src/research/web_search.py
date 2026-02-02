"""
Web Search Client.

Поиск информации в интернете через API.
"""

import os
from typing import Any, Dict, List, Optional

import httpx


class WebSearchClient:
    """
    Клиент для веб-поиска.

    Поддерживает:
    - Tavily API (рекомендуется)
    - Bing Search API
    - DuckDuckGo (fallback, без API)
    """

    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        bing_api_key: Optional[str] = None,
    ):
        """
        Инициализация клиента.

        Args:
            tavily_api_key: API ключ Tavily
            bing_api_key: API ключ Bing Search
        """
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        self.bing_api_key = bing_api_key or os.getenv("BING_API_KEY")

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic"
    ) -> List[Dict[str, Any]]:
        """
        Выполнить поиск.

        Args:
            query: Поисковый запрос
            max_results: Максимум результатов
            search_depth: Глубина поиска (basic/advanced)

        Returns:
            Список результатов [{title, url, snippet}]
        """
        # Пробуем Tavily
        if self.tavily_api_key:
            try:
                return await self._search_tavily(query, max_results, search_depth)
            except Exception:
                pass

        # Пробуем Bing
        if self.bing_api_key:
            try:
                return await self._search_bing(query, max_results)
            except Exception:
                pass

        # Fallback — пустой результат
        return []

    async def _search_tavily(
        self,
        query: str,
        max_results: int,
        search_depth: str
    ) -> List[Dict[str, Any]]:
        """Поиск через Tavily API."""
        url = "https://api.tavily.com/search"

        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:500],
                "source": "tavily"
            })

        return results

    async def _search_bing(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Поиск через Bing Search API."""
        url = "https://api.bing.microsoft.com/v7.0/search"

        headers = {
            "Ocp-Apim-Subscription-Key": self.bing_api_key
        }

        params = {
            "q": query,
            "count": max_results,
            "mkt": "ru-RU"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("webPages", {}).get("value", []):
            results.append({
                "title": item.get("name", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", "")[:500],
                "source": "bing"
            })

        return results

    async def search_industry_insights(
        self,
        industry: str,
        topics: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Поиск инсайтов об отрасли.

        Args:
            industry: Отрасль
            topics: Темы для поиска

        Returns:
            Результаты по темам
        """
        if topics is None:
            topics = [
                "тренды автоматизации",
                "голосовые боты кейсы",
                "проблемы и решения"
            ]

        results = {}
        for topic in topics:
            query = f"{industry} {topic}"
            search_results = await self.search(query, max_results=3)
            results[topic] = search_results

        return results
