"""
Research Engine Module.

Сбор и анализ внешних данных:
- Web Search (Bing/Tavily)
- Website Parser
- RAG (Azure Cognitive Search)
"""

from src.research.engine import ResearchEngine, ResearchResult
from src.research.website_parser import WebsiteParser
from src.research.web_search import WebSearchClient

__all__ = [
    "ResearchEngine",
    "ResearchResult",
    "WebsiteParser",
    "WebSearchClient",
]
