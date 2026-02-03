"""
Anketa module - generates final questionnaires from consultations.

Components:
- FinalAnketa: Pydantic schema for the questionnaire
- AnketaExtractor: Extracts structured data from dialogue via LLM
- AnketaGenerator: Generates Markdown/JSON documents
- AnketaReviewService: Review workflow with external editor
- AnketaMarkdownParser: Parses Markdown back to FinalAnketa

v3.1 Data Cleaning Components:
- JSONRepair: Robust JSON parsing with multiple repair strategies
- DialogueCleaner: Removes dialogue markers from field values
- SmartExtractor: Role-based data extraction from dialogue
- AnketaPostProcessor: Comprehensive post-processing pipeline
"""

from src.anketa.schema import FinalAnketa, AgentFunction, Integration
from src.anketa.extractor import AnketaExtractor
from src.anketa.generator import AnketaGenerator
from src.anketa.review_service import AnketaReviewService, create_review_service
from src.anketa.markdown_parser import AnketaMarkdownParser, parse_anketa_markdown
from src.anketa.data_cleaner import (
    JSONRepair, DialogueCleaner, SmartExtractor, AnketaPostProcessor
)

__all__ = [
    # Schema
    'FinalAnketa',
    'AgentFunction',
    'Integration',
    # Extractor
    'AnketaExtractor',
    # Generator
    'AnketaGenerator',
    # Review
    'AnketaReviewService',
    'create_review_service',
    # Parser
    'AnketaMarkdownParser',
    'parse_anketa_markdown',
    # v3.1 Data Cleaning
    'JSONRepair',
    'DialogueCleaner',
    'SmartExtractor',
    'AnketaPostProcessor',
]
