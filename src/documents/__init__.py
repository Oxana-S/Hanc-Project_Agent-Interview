"""
Document Analysis Module - parsing and analyzing client documents.

Provides:
- DocumentLoader: Loads documents from a folder
- DocumentParser: Parses PDF, DOCX, MD, XLSX files
- DocumentAnalyzer: LLM-based document analysis
- DocumentContext: Context from all documents for interview

Usage:
    from src.documents import DocumentLoader, DocumentAnalyzer, DocumentContext

    # Load documents
    loader = DocumentLoader()
    documents = loader.load_all(Path("input/"))

    # Analyze with LLM
    analyzer = DocumentAnalyzer()
    context = await analyzer.analyze(documents)

    # Or analyze without LLM (sync)
    context = analyzer.analyze_sync(documents)

    # Use context in interview
    prompt_addition = context.to_prompt_context()
"""

from .models import (
    DocumentChunk,
    ParsedDocument,
    DocumentContext,
)

from .parser import (
    DocumentParser,
    DocumentLoader,
)

from .analyzer import (
    DocumentAnalyzer,
)


__all__ = [
    # Models
    "DocumentChunk",
    "ParsedDocument",
    "DocumentContext",

    # Parser
    "DocumentParser",
    "DocumentLoader",

    # Analyzer
    "DocumentAnalyzer",
]
