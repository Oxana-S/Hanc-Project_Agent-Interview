"""
Research Engine.

Объединяет все источники данных и синтезирует результаты.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.research.website_parser import WebsiteParser
from src.research.web_search import WebSearchClient
from src.llm.factory import create_llm_client


class ResearchResult(BaseModel):
    """Результат исследования."""

    # Данные с сайта клиента
    website_data: Optional[Dict[str, Any]] = None

    # Инсайты об отрасли
    industry_insights: List[str] = Field(default_factory=list)

    # Информация о конкурентах
    competitor_info: List[Dict[str, str]] = Field(default_factory=list)

    # Best practices
    best_practices: List[str] = Field(default_factory=list)

    # Compliance и ограничения отрасли
    compliance_notes: List[str] = Field(default_factory=list)

    # Похожие кейсы из RAG
    similar_cases: List[Dict[str, Any]] = Field(default_factory=list)

    # Метаданные
    sources_used: List[str] = Field(default_factory=list)
    research_timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence_score: float = 0.0

    def has_data(self) -> bool:
        """Есть ли какие-то данные."""
        return bool(
            self.website_data or
            self.industry_insights or
            self.competitor_info or
            self.best_practices
        )


class ResearchEngine:
    """
    Research Engine — сбор и анализ внешних данных.

    Источники:
    - Website Parser: анализ сайта клиента
    - Web Search: поиск информации об отрасли
    - RAG: похожие кейсы из базы знаний (TODO)
    """

    def __init__(
        self,
        deepseek_client=None,
        web_search_client: Optional[WebSearchClient] = None,
        enable_web_search: bool = True,
        enable_website_parser: bool = True,
        enable_rag: bool = False  # TODO: реализовать
    ):
        """
        Инициализация Research Engine.

        Args:
            deepseek_client: Клиент для синтеза результатов
            web_search_client: Клиент для веб-поиска
            enable_web_search: Включить веб-поиск
            enable_website_parser: Включить парсинг сайтов
            enable_rag: Включить RAG (Azure Cognitive Search)
        """
        self.deepseek = deepseek_client or create_llm_client()
        self.web_search = web_search_client or WebSearchClient()
        self.website_parser = WebsiteParser()

        self.enable_web_search = enable_web_search
        self.enable_website_parser = enable_website_parser
        self.enable_rag = enable_rag

    async def research(
        self,
        website: Optional[str] = None,
        industry: Optional[str] = None,
        company_name: Optional[str] = None,
        additional_context: Optional[str] = None
    ) -> ResearchResult:
        """
        Провести исследование.

        Args:
            website: URL сайта клиента
            industry: Отрасль
            company_name: Название компании
            additional_context: Дополнительный контекст

        Returns:
            Результаты исследования
        """
        result = ResearchResult()
        tasks = []

        # Парсинг сайта
        if website and self.enable_website_parser:
            tasks.append(self._parse_website(website))

        # Веб-поиск по отрасли
        if industry and self.enable_web_search:
            tasks.append(self._search_industry(industry))

        # RAG поиск похожих кейсов
        if self.enable_rag and industry:
            tasks.append(self._search_similar_cases(industry, company_name))

        # Выполняем параллельно
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    continue
                if isinstance(res, dict):
                    self._merge_result(result, res)

        # Синтезируем инсайты
        if result.has_data():
            result = await self._synthesize_insights(result, industry, additional_context)

        result.research_timestamp = datetime.utcnow()
        return result

    async def _parse_website(self, url: str) -> Dict[str, Any]:
        """Парсить сайт клиента."""
        try:
            data = await self.website_parser.parse(url)
            return {"type": "website", "data": data}
        except Exception as e:
            return {"type": "website", "error": str(e)}

    async def _search_industry(self, industry: str) -> Dict[str, Any]:
        """Поиск информации об отрасли."""
        try:
            queries = [
                f"{industry} голосовой агент автоматизация",
                f"{industry} тренды автоматизации 2026",
                f"{industry} чат-бот кейсы"
            ]

            all_results = []
            for query in queries[:2]:  # Лимитируем запросы
                results = await self.web_search.search(query, max_results=3)
                all_results.extend(results)

            return {"type": "web_search", "data": all_results}
        except Exception as e:
            return {"type": "web_search", "error": str(e)}

    async def _search_similar_cases(self, industry: str, company_name: Optional[str]) -> Dict[str, Any]:
        """Поиск похожих кейсов в RAG."""
        # TODO: Реализовать интеграцию с Azure Cognitive Search
        return {"type": "rag", "data": []}

    def _merge_result(self, result: ResearchResult, data: Dict[str, Any]):
        """Объединить результаты в общий ResearchResult."""
        data_type = data.get("type")
        content = data.get("data")

        if not content:
            return

        if data_type == "website":
            result.website_data = content
            result.sources_used.append("website_parser")

        elif data_type == "web_search":
            result.sources_used.append("web_search")
            # Данные будут обработаны в synthesize

        elif data_type == "rag":
            result.similar_cases = content
            result.sources_used.append("rag")

    async def _synthesize_insights(
        self,
        result: ResearchResult,
        industry: Optional[str],
        context: Optional[str]
    ) -> ResearchResult:
        """Синтезировать инсайты из собранных данных."""
        prompt = f"""Проанализируй собранные данные об отрасли и бизнесе.

ОТРАСЛЬ: {industry or 'не указана'}

ДАННЫЕ С САЙТА:
{result.website_data if result.website_data else 'нет данных'}

ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:
{context or 'нет'}

Сформируй:
1. 3-5 ключевых инсайтов об отрасли (тренды, проблемы, возможности)
2. Best practices для голосовых агентов в этой отрасли
3. Compliance-требования (если есть)

Верни JSON:
{{
    "industry_insights": ["инсайт 1", "инсайт 2"],
    "best_practices": ["практика 1", "практика 2"],
    "compliance_notes": ["требование 1"]
}}"""

        try:
            response = await self.deepseek.chat([
                {"role": "user", "content": prompt}
            ], temperature=0.3)

            import json
            json_text = response.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]

            start = json_text.find('{')
            end = json_text.rfind('}')
            if start != -1 and end != -1:
                json_text = json_text[start:end+1]

            data = json.loads(json_text)

            result.industry_insights = data.get("industry_insights", [])
            result.best_practices = data.get("best_practices", [])
            result.compliance_notes = data.get("compliance_notes", [])
            result.confidence_score = 0.8

        except Exception:
            pass

        return result
