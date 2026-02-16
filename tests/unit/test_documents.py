"""
Unit tests for documents module.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
import json

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.documents.models import DocumentChunk, ParsedDocument, DocumentContext
from src.documents.analyzer import DocumentAnalyzer
from src.documents.parser import DocumentParser, DocumentLoader


# ============ MODEL TESTS ============

class TestDocumentChunk:
    """Test DocumentChunk model."""

    def test_chunk_minimal(self):
        """Test chunk with minimal fields."""
        chunk = DocumentChunk(content="Some text", doc_type="pdf")

        assert chunk.content == "Some text"
        assert chunk.doc_type == "pdf"
        assert chunk.section is None
        assert chunk.page is None
        assert chunk.row_range is None

    def test_chunk_with_page(self):
        """Test chunk with page number."""
        chunk = DocumentChunk(
            content="Page content",
            doc_type="pdf",
            page=5
        )

        assert chunk.page == 5

    def test_chunk_with_section(self):
        """Test chunk with section."""
        chunk = DocumentChunk(
            content="Section content",
            doc_type="docx",
            section="Introduction"
        )

        assert chunk.section == "Introduction"

    def test_chunk_with_row_range(self):
        """Test chunk with row range (for xlsx)."""
        chunk = DocumentChunk(
            content="Table data",
            doc_type="xlsx",
            row_range="1-50"
        )

        assert chunk.row_range == "1-50"


class TestParsedDocument:
    """Test ParsedDocument model."""

    @pytest.fixture
    def sample_document(self):
        """Create a sample parsed document."""
        chunks = [
            DocumentChunk(content="First paragraph with some text.", doc_type="pdf", page=1),
            DocumentChunk(content="Second paragraph with more text.", doc_type="pdf", page=2),
            DocumentChunk(content="Third paragraph.", doc_type="pdf", page=3)
        ]
        return ParsedDocument(
            filename="test.pdf",
            doc_type="pdf",
            file_path="/path/to/test.pdf",
            chunks=chunks,
            metadata={"pages": 3, "title": "Test Document"}
        )

    def test_document_creation(self, sample_document):
        """Test document creation."""
        assert sample_document.filename == "test.pdf"
        assert sample_document.doc_type == "pdf"
        assert len(sample_document.chunks) == 3

    def test_full_text_property(self, sample_document):
        """Test full_text property concatenates all chunks."""
        full_text = sample_document.full_text

        assert "First paragraph" in full_text
        assert "Second paragraph" in full_text
        assert "Third paragraph" in full_text
        # Chunks are joined with double newlines
        assert "\n\n" in full_text

    def test_word_count_property(self, sample_document):
        """Test word_count property."""
        word_count = sample_document.word_count

        assert word_count > 0
        # Roughly count the words in the chunks
        assert word_count >= 10

    def test_empty_document(self):
        """Test empty document properties."""
        doc = ParsedDocument(
            filename="empty.pdf",
            doc_type="pdf",
            file_path="/path/to/empty.pdf"
        )

        assert doc.full_text == ""
        assert doc.word_count == 0
        assert doc.chunks == []

    def test_extracted_fields_defaults(self):
        """Test extracted fields have empty defaults."""
        doc = ParsedDocument(
            filename="test.pdf",
            doc_type="pdf",
            file_path="/path/test.pdf"
        )

        assert doc.extracted_services == []
        assert doc.extracted_faq == []
        assert doc.extracted_prices == []
        assert doc.extracted_contacts == {}

    def test_document_with_extracted_data(self):
        """Test document with extracted data."""
        doc = ParsedDocument(
            filename="test.pdf",
            doc_type="pdf",
            file_path="/path/test.pdf",
            chunks=[DocumentChunk(content="Test", doc_type="pdf")],
            extracted_services=["Service A", "Service B"],
            extracted_faq=[{"question": "Q?", "answer": "A"}],
            extracted_prices=[{"service": "A", "price": "1000"}],
            extracted_contacts={"email": "test@test.com"}
        )

        assert len(doc.extracted_services) == 2
        assert len(doc.extracted_faq) == 1
        assert len(doc.extracted_prices) == 1
        assert "email" in doc.extracted_contacts


class TestDocumentContext:
    """Test DocumentContext model."""

    @pytest.fixture
    def sample_context(self):
        """Create a sample document context."""
        doc1 = ParsedDocument(
            filename="doc1.pdf",
            doc_type="pdf",
            file_path="/path/doc1.pdf",
            chunks=[DocumentChunk(content="Content one two three", doc_type="pdf")]
        )
        doc2 = ParsedDocument(
            filename="doc2.docx",
            doc_type="docx",
            file_path="/path/doc2.docx",
            chunks=[DocumentChunk(content="Content four five", doc_type="docx")]
        )

        return DocumentContext(
            documents=[doc1, doc2],
            summary="Two business documents",
            key_facts=["Fact 1", "Fact 2", "Fact 3"],
            services_mentioned=["Service A", "Service B"],
            questions_to_clarify=["Question 1?"],
            all_contacts={"email": "test@test.com", "phone": "+7999123456"},
            all_prices=[{"service": "A", "price": "1000"}]
        )

    def test_total_documents_property(self, sample_context):
        """Test total_documents property."""
        assert sample_context.total_documents == 2

    def test_total_words_property(self, sample_context):
        """Test total_words property."""
        total_words = sample_context.total_words

        assert total_words > 0
        # Should be sum of words in both documents
        assert total_words >= 5

    def test_get_documents_by_type(self, sample_context):
        """Test filtering documents by type."""
        pdf_docs = sample_context.get_documents_by_type("pdf")
        docx_docs = sample_context.get_documents_by_type("docx")

        assert len(pdf_docs) == 1
        assert len(docx_docs) == 1
        assert pdf_docs[0].filename == "doc1.pdf"

    def test_to_prompt_context(self, sample_context):
        """Test conversion to prompt context string."""
        prompt_context = sample_context.to_prompt_context()

        assert "Контекст из документов клиента" in prompt_context
        assert "Two business documents" in prompt_context
        assert "Fact 1" in prompt_context
        assert "Service A" in prompt_context
        assert "test@test.com" in prompt_context
        assert "Question 1?" in prompt_context

    def test_to_prompt_context_empty(self):
        """Test prompt context for empty context."""
        context = DocumentContext()

        assert context.to_prompt_context() == ""

    def test_to_prompt_context_no_summary(self):
        """Test prompt context without summary."""
        doc = ParsedDocument(
            filename="test.pdf",
            doc_type="pdf",
            file_path="/path/test.pdf",
            chunks=[DocumentChunk(content="Test", doc_type="pdf")]
        )
        context = DocumentContext(
            documents=[doc],
            key_facts=["Fact 1"]
        )

        prompt = context.to_prompt_context()
        assert "Ключевые факты" in prompt
        assert "Fact 1" in prompt

    def test_context_defaults(self):
        """Test context default values."""
        context = DocumentContext()

        assert context.documents == []
        assert context.summary == ""
        assert context.key_facts == []
        assert context.services_mentioned == []
        assert context.questions_to_clarify == []
        assert context.all_contacts == {}
        assert context.all_prices == []


# ============ PARSER TESTS ============

class TestDocumentParser:
    """Test DocumentParser class."""

    def test_parser_initialization(self):
        """Test parser initializes correctly."""
        parser = DocumentParser()

        assert hasattr(parser, "_has_pymupdf")
        assert hasattr(parser, "_has_docx")
        assert hasattr(parser, "_has_openpyxl")

    def test_supported_extensions(self):
        """Test supported file extensions."""
        expected = {".pdf", ".docx", ".md", ".xlsx", ".xls", ".txt"}
        assert DocumentParser.SUPPORTED_EXTENSIONS == expected

    def test_parse_file_not_found(self, tmp_path):
        """Test parsing non-existent file."""
        parser = DocumentParser()
        result = parser.parse(tmp_path / "nonexistent.pdf")

        assert result is None

    def test_parse_unsupported_format(self, tmp_path):
        """Test parsing unsupported file format."""
        # Create a file with unsupported extension
        test_file = tmp_path / "test.xyz"
        test_file.write_text("test content")

        parser = DocumentParser()
        result = parser.parse(test_file)

        assert result is None

    def test_parse_markdown_simple(self, tmp_path):
        """Test parsing simple markdown file."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Title\n\nSome content here.\n\n## Section\n\nMore content.")

        parser = DocumentParser()
        result = parser.parse(md_file)

        assert result is not None
        assert result.filename == "test.md"
        assert result.doc_type == "md"
        assert len(result.chunks) > 0

    def test_parse_markdown_no_headers(self, tmp_path):
        """Test parsing markdown without headers."""
        md_file = tmp_path / "plain.md"
        md_file.write_text("Just plain text\nwithout any headers\nor structure.")

        parser = DocumentParser()
        result = parser.parse(md_file)

        assert result is not None
        assert len(result.chunks) == 1
        assert "plain text" in result.chunks[0].content

    def test_parse_txt_file(self, tmp_path):
        """Test parsing TXT file (same as markdown)."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Plain text content\nLine 2\nLine 3")

        parser = DocumentParser()
        result = parser.parse(txt_file)

        assert result is not None
        assert result.doc_type == "md"  # TXT parsed as markdown
        assert result.metadata.get("lines") == 3

    def test_parse_markdown_with_sections(self, tmp_path):
        """Test parsing markdown with multiple sections."""
        content = """# Main Title

Introduction text here.

## First Section

Content of first section.

## Second Section

Content of second section.

### Subsection

Subsection content.
"""
        md_file = tmp_path / "sections.md"
        md_file.write_text(content)

        parser = DocumentParser()
        result = parser.parse(md_file)

        assert result is not None
        assert len(result.chunks) >= 3  # At least intro + 2 sections

    def test_parse_pdf_without_dependency(self, tmp_path):
        """Test PDF parsing when PyMuPDF is not available."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf")

        parser = DocumentParser()
        parser._has_pymupdf = False  # Simulate missing dependency

        result = parser._parse_pdf(pdf_file)

        assert result is None

    def test_parse_docx_without_dependency(self, tmp_path):
        """Test DOCX parsing when python-docx is not available."""
        docx_file = tmp_path / "test.docx"
        docx_file.write_bytes(b"fake docx content")

        parser = DocumentParser()
        parser._has_docx = False  # Simulate missing dependency

        result = parser._parse_docx(docx_file)

        assert result is None

    def test_parse_xlsx_without_dependency(self, tmp_path):
        """Test XLSX parsing when openpyxl is not available."""
        xlsx_file = tmp_path / "test.xlsx"
        xlsx_file.write_bytes(b"fake xlsx content")

        parser = DocumentParser()
        parser._has_openpyxl = False  # Simulate missing dependency

        result = parser._parse_xlsx(xlsx_file)

        assert result is None


class TestDocumentLoader:
    """Test DocumentLoader class."""

    def test_loader_initialization(self):
        """Test loader initializes correctly."""
        loader = DocumentLoader()

        assert loader.parser is not None
        assert loader._loaded_files == set()

    def test_load_all_empty_directory(self, tmp_path):
        """Test loading from empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        loader = DocumentLoader()
        result = loader.load_all(empty_dir)

        assert result == []

    def test_load_all_nonexistent_directory(self, tmp_path):
        """Test loading from non-existent directory."""
        loader = DocumentLoader()
        result = loader.load_all(tmp_path / "nonexistent")

        assert result == []

    def test_load_all_with_markdown(self, tmp_path):
        """Test loading markdown files from directory."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create test files
        (docs_dir / "doc1.md").write_text("# Document 1\n\nContent here.")
        (docs_dir / "doc2.txt").write_text("Plain text document.")
        (docs_dir / "ignored.xyz").write_text("Ignored file.")

        loader = DocumentLoader()
        result = loader.load_all(docs_dir)

        # Should load md and txt, ignore xyz
        assert len(result) == 2
        filenames = [doc.filename for doc in result]
        assert "doc1.md" in filenames
        assert "doc2.txt" in filenames

    def test_load_all_with_subdirectories(self, tmp_path):
        """Test loading from subdirectories."""
        docs_dir = tmp_path / "docs"
        sub_dir = docs_dir / "sub"
        sub_dir.mkdir(parents=True)

        (docs_dir / "root.md").write_text("Root document")
        (sub_dir / "nested.md").write_text("Nested document")

        loader = DocumentLoader()
        result = loader.load_all(docs_dir)

        assert len(result) == 2

    def test_get_loaded_files(self, tmp_path):
        """Test getting list of loaded files."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.md").write_text("Test content")

        loader = DocumentLoader()
        loader.load_all(docs_dir)

        loaded = loader.get_loaded_files()

        assert len(loaded) == 1
        assert "test.md" in loaded[0]

    def test_check_for_new_documents(self, tmp_path):
        """Test checking for new documents."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Initial file
        (docs_dir / "initial.md").write_text("Initial document")

        loader = DocumentLoader()
        initial = loader.load_all(docs_dir)
        assert len(initial) == 1

        # Add new file
        (docs_dir / "new.md").write_text("New document")

        new_docs = loader.check_for_new(docs_dir)
        assert len(new_docs) == 1
        assert new_docs[0].filename == "new.md"

        # Check again - should find nothing new
        new_docs_again = loader.check_for_new(docs_dir)
        assert len(new_docs_again) == 0

    def test_check_for_new_nonexistent_directory(self, tmp_path):
        """Test checking for new in non-existent directory."""
        loader = DocumentLoader()
        result = loader.check_for_new(tmp_path / "nonexistent")

        assert result == []


# ============ ANALYZER TESTS ============

class TestDocumentAnalyzer:
    """Test DocumentAnalyzer class."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = MagicMock()
        client.chat = AsyncMock(return_value='{"summary": "Test summary", "key_facts": ["Fact 1"], "services": ["Service A"], "contacts": {"email": "test@test.com"}, "prices": [], "questions": ["Question?"]}')
        return client

    @pytest.fixture
    def sample_documents(self):
        """Create sample parsed documents."""
        doc1 = ParsedDocument(
            filename="doc1.pdf",
            doc_type="pdf",
            file_path="/path/doc1.pdf",
            chunks=[
                DocumentChunk(content="This is a business document about logistics.", doc_type="pdf", page=1)
            ]
        )
        doc2 = ParsedDocument(
            filename="doc2.md",
            doc_type="md",
            file_path="/path/doc2.md",
            chunks=[
                DocumentChunk(content="Services: delivery, warehousing. Phone: +79991234567", doc_type="md")
            ]
        )
        return [doc1, doc2]

    def test_analyzer_initialization(self):
        """Test analyzer initialization."""
        analyzer = DocumentAnalyzer()
        assert analyzer._llm_client is None

    def test_analyzer_with_client(self, mock_llm_client):
        """Test analyzer with provided client."""
        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)
        assert analyzer._llm_client is mock_llm_client

    @pytest.mark.asyncio
    async def test_analyze_empty_documents(self):
        """Test analyzing empty document list."""
        analyzer = DocumentAnalyzer()
        result = await analyzer.analyze([])

        assert isinstance(result, DocumentContext)
        assert result.documents == []

    @pytest.mark.asyncio
    async def test_analyze_documents(self, mock_llm_client, sample_documents):
        """Test analyzing documents."""
        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)
        result = await analyzer.analyze(sample_documents)

        assert isinstance(result, DocumentContext)
        assert result.summary == "Test summary"
        assert "Fact 1" in result.key_facts
        assert "Service A" in result.services_mentioned

    def test_combine_documents(self, sample_documents):
        """Test combining document text."""
        analyzer = DocumentAnalyzer()
        combined = analyzer._combine_documents(sample_documents)

        assert "doc1.pdf" in combined
        assert "doc2.md" in combined
        assert "logistics" in combined
        assert "delivery" in combined

    def test_parse_json_response_valid(self):
        """Test parsing valid JSON response."""
        analyzer = DocumentAnalyzer()
        response = '{"summary": "Test", "key_facts": ["Fact 1"]}'
        result = analyzer._parse_json_response(response)

        assert result["summary"] == "Test"
        assert "Fact 1" in result["key_facts"]

    def test_parse_json_response_markdown_block(self):
        """Test parsing JSON in markdown code block."""
        analyzer = DocumentAnalyzer()
        response = 'Here is the analysis:\n```json\n{"summary": "Test"}\n```'
        result = analyzer._parse_json_response(response)

        assert result["summary"] == "Test"

    def test_parse_json_response_embedded(self):
        """Test parsing embedded JSON in text."""
        analyzer = DocumentAnalyzer()
        response = 'The result is: {"summary": "Embedded"} and more text.'
        result = analyzer._parse_json_response(response)

        assert result["summary"] == "Embedded"

    def test_parse_json_response_invalid(self):
        """Test parsing invalid JSON response."""
        analyzer = DocumentAnalyzer()
        response = "This is not JSON at all"
        result = analyzer._parse_json_response(response)

        assert result == {}

    def test_parse_json_array_valid(self):
        """Test parsing valid JSON array."""
        analyzer = DocumentAnalyzer()
        response = '["Item 1", "Item 2", "Item 3"]'
        result = analyzer._parse_json_array(response)

        assert len(result) == 3
        assert "Item 1" in result

    def test_parse_json_array_embedded(self):
        """Test parsing embedded JSON array."""
        analyzer = DocumentAnalyzer()
        response = 'The services are: ["Service A", "Service B"]'
        result = analyzer._parse_json_array(response)

        assert len(result) == 2

    def test_parse_json_array_invalid(self):
        """Test parsing invalid array response."""
        analyzer = DocumentAnalyzer()
        response = "No array here"
        result = analyzer._parse_json_array(response)

        assert result == []

    def test_analyze_sync_empty(self):
        """Test synchronous analysis of empty documents."""
        analyzer = DocumentAnalyzer()
        result = analyzer.analyze_sync([])

        assert isinstance(result, DocumentContext)
        assert result.documents == []

    def test_analyze_sync_with_documents(self, sample_documents):
        """Test synchronous analysis."""
        analyzer = DocumentAnalyzer()
        result = analyzer.analyze_sync(sample_documents)

        assert len(result.documents) == 2
        assert "Загружено 2 документ" in result.summary

    def test_extract_contacts_regex_phone(self):
        """Test phone extraction via regex."""
        analyzer = DocumentAnalyzer()

        text = "Наш телефон: +7 (999) 123-45-67, звоните!"
        contacts = analyzer._extract_contacts_regex(text)

        assert "телефон" in contacts

    def test_extract_contacts_regex_email(self):
        """Test email extraction via regex."""
        analyzer = DocumentAnalyzer()

        text = "Email: info@company.ru для связи"
        contacts = analyzer._extract_contacts_regex(text)

        assert "email" in contacts
        assert contacts["email"] == "info@company.ru"

    def test_extract_contacts_regex_website(self):
        """Test website extraction via regex."""
        analyzer = DocumentAnalyzer()

        text = "Наш сайт: www.company.ru"
        contacts = analyzer._extract_contacts_regex(text)

        assert "сайт" in contacts

    def test_extract_contacts_regex_all(self):
        """Test extracting all contact types."""
        analyzer = DocumentAnalyzer()

        text = """
        Контакты:
        Телефон: 8 (495) 123-45-67
        Email: contact@business.com
        Сайт: https://business.com
        """
        contacts = analyzer._extract_contacts_regex(text)

        assert len(contacts) >= 2  # At least email and phone

    def test_extract_key_sentences(self, sample_documents):
        """Test extracting key sentences."""
        analyzer = DocumentAnalyzer()
        facts = analyzer._extract_key_sentences(sample_documents)

        assert len(facts) > 0
        # Should extract first sentences from chunks

    def test_extract_key_sentences_filters_short(self):
        """Test that short sentences are filtered."""
        analyzer = DocumentAnalyzer()

        doc = ParsedDocument(
            filename="test.pdf",
            doc_type="pdf",
            file_path="/path/test.pdf",
            chunks=[
                DocumentChunk(content="OK.", doc_type="pdf"),  # Too short
                DocumentChunk(content="This is a longer sentence that should be included.", doc_type="pdf")
            ]
        )

        facts = analyzer._extract_key_sentences([doc])

        # Only the longer sentence should be included
        assert all(len(f) > 20 for f in facts)

    @pytest.mark.asyncio
    async def test_extract_services(self, mock_llm_client):
        """Test service extraction."""
        mock_llm_client.chat = AsyncMock(return_value='["Доставка", "Хранение", "Упаковка"]')

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)
        doc = ParsedDocument(
            filename="services.pdf",
            doc_type="pdf",
            file_path="/path/services.pdf",
            chunks=[DocumentChunk(content="Our services include...", doc_type="pdf")]
        )

        services = await analyzer.extract_services(doc)

        assert len(services) == 3
        assert "Доставка" in services

    @pytest.mark.asyncio
    async def test_extract_services_error(self, mock_llm_client):
        """Test service extraction error handling."""
        mock_llm_client.chat = AsyncMock(side_effect=Exception("API Error"))

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)
        doc = ParsedDocument(
            filename="test.pdf",
            doc_type="pdf",
            file_path="/path/test.pdf",
            chunks=[DocumentChunk(content="Test", doc_type="pdf")]
        )

        services = await analyzer.extract_services(doc)

        assert services == []

    @pytest.mark.asyncio
    async def test_extract_faq(self, mock_llm_client):
        """Test FAQ extraction."""
        mock_llm_client.chat = AsyncMock(return_value='[{"question": "How much?", "answer": "From $100"}]')

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)
        doc = ParsedDocument(
            filename="faq.pdf",
            doc_type="pdf",
            file_path="/path/faq.pdf",
            chunks=[DocumentChunk(content="FAQ section...", doc_type="pdf")]
        )

        faq = await analyzer.extract_faq(doc)

        assert len(faq) == 1
        assert faq[0]["question"] == "How much?"

    @pytest.mark.asyncio
    async def test_extract_faq_error(self, mock_llm_client):
        """Test FAQ extraction error handling."""
        mock_llm_client.chat = AsyncMock(side_effect=Exception("API Error"))

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)
        doc = ParsedDocument(
            filename="test.pdf",
            doc_type="pdf",
            file_path="/path/test.pdf",
            chunks=[DocumentChunk(content="Test", doc_type="pdf")]
        )

        faq = await analyzer.extract_faq(doc)

        assert faq == []

    @pytest.mark.asyncio
    async def test_llm_analyze_error(self, mock_llm_client):
        """Test LLM analysis error handling."""
        mock_llm_client.chat = AsyncMock(side_effect=Exception("API Error"))

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)
        result = await analyzer._llm_analyze("test text")

        assert result == {}


# ============ INTEGRATION TESTS ============

class TestDocumentsIntegration:
    """Integration tests for documents module."""

    def test_full_pipeline_markdown(self, tmp_path):
        """Test full pipeline with markdown files."""
        # Create test files
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "about.md").write_text("""
# О компании

Мы занимаемся логистикой с 2010 года.

## Услуги

- Доставка грузов
- Складирование
- Упаковка

## Контакты

Телефон: +7 (495) 123-45-67
Email: info@logistics.ru
""")

        (docs_dir / "prices.txt").write_text("""
Прайс-лист

Доставка по Москве: от 500 руб
Доставка по России: от 1500 руб
Хранение: 100 руб/м3/день
""")

        # Load documents
        loader = DocumentLoader()
        documents = loader.load_all(docs_dir)

        assert len(documents) == 2

        # Analyze synchronously (no LLM)
        analyzer = DocumentAnalyzer()
        context = analyzer.analyze_sync(documents)

        assert context.total_documents == 2
        assert context.total_words > 0
        assert "email" in context.all_contacts or "телефон" in context.all_contacts

    def test_document_context_prompt_generation(self, tmp_path):
        """Test generating prompt context from documents."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "services.md").write_text("# Наши услуги\n\nМы предлагаем доставку.")

        loader = DocumentLoader()
        documents = loader.load_all(docs_dir)

        analyzer = DocumentAnalyzer()
        context = analyzer.analyze_sync(documents)

        prompt = context.to_prompt_context()

        assert "Контекст из документов" in prompt
        assert "Загружено" in prompt

    def test_parser_handles_encoding(self, tmp_path):
        """Test parser handles various text encodings."""
        md_file = tmp_path / "russian.md"
        md_file.write_text("# Заголовок\n\nРусский текст с кириллицей.", encoding="utf-8")

        parser = DocumentParser()
        result = parser.parse(md_file)

        assert result is not None
        assert "Русский текст" in result.full_text

    def test_check_new_documents_workflow(self, tmp_path):
        """Test the check-for-new workflow."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        loader = DocumentLoader()

        # Empty initially
        initial = loader.load_all(docs_dir)
        assert len(initial) == 0

        # Add first document
        (docs_dir / "first.md").write_text("First document")
        new1 = loader.check_for_new(docs_dir)
        assert len(new1) == 1

        # Add second document
        (docs_dir / "second.md").write_text("Second document")
        new2 = loader.check_for_new(docs_dir)
        assert len(new2) == 1
        assert new2[0].filename == "second.md"

        # Verify total loaded
        loaded = loader.get_loaded_files()
        assert len(loaded) == 2


# ============ ANALYZER V2 TESTS (equal weight, per-doc extraction) ============

class TestDocumentAnalyzerV2:
    """Tests for improved document analysis — equal weight for all doc types."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = MagicMock()
        client.chat = AsyncMock(return_value='{"summary": "Business analysis and legal docs", "key_facts": ["Fact 1"], "services": ["Service A"], "contacts": {"email": "test@test.com"}, "prices": [{"service": "CT scan", "price": "300 EUR"}], "questions": ["Question?"]}')
        return client

    def test_combine_documents_includes_type_label(self):
        """Test that _combine_documents adds document type labels."""
        analyzer = DocumentAnalyzer()

        pdf_doc = ParsedDocument(
            filename="legal.pdf", doc_type="pdf", file_path="/p/legal.pdf",
            chunks=[DocumentChunk(content="Legal text about TAeG", doc_type="pdf")]
        )
        md_doc = ParsedDocument(
            filename="analysis.md", doc_type="md", file_path="/p/analysis.md",
            chunks=[DocumentChunk(content="Business analysis with ROI 460%", doc_type="md")]
        )

        combined = analyzer._combine_documents([pdf_doc, md_doc])

        assert "[PDF]" in combined
        assert "[Markdown]" in combined
        assert "legal.pdf" in combined
        assert "analysis.md" in combined
        assert "TAeG" in combined
        assert "ROI 460%" in combined

    def test_combine_documents_20k_limit_per_doc(self):
        """Test that each document gets up to 20K chars."""
        analyzer = DocumentAnalyzer()

        # Create a doc with >20K chars
        long_text = "x" * 25000
        doc = ParsedDocument(
            filename="big.md", doc_type="md", file_path="/p/big.md",
            chunks=[DocumentChunk(content=long_text, doc_type="md")]
        )

        combined = analyzer._combine_documents([doc])

        # Should be truncated: header + 20000 chars
        assert len(combined) < 25000

    @pytest.mark.asyncio
    async def test_analyze_calls_per_doc_extraction(self, mock_llm_client):
        """Test that analyze() calls extract_services for each document."""
        # Mock: first call = analyze, second = extract_services for doc1, third = extract_faq for doc1,
        # fourth = extract_services for doc2, fifth = extract_faq for doc2
        responses = [
            '{"summary": "Test", "key_facts": [], "services": [], "contacts": {}, "prices": [], "questions": []}',
            '["Service from PDF"]',  # extract_services doc1
            '[]',  # extract_faq doc1
            '["Service from MD", "Another MD service"]',  # extract_services doc2
            '[{"question": "Q?", "answer": "A"}]',  # extract_faq doc2
        ]
        mock_llm_client.chat = AsyncMock(side_effect=responses)

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)

        # Docs need >50 words to trigger per-doc LLM extraction
        long_pdf_text = " ".join(["Legal document text about veterinary regulations and compliance requirements"] * 8)
        long_md_text = " ".join(["Business analysis document with ROI calculations and revenue projections"] * 8)

        docs = [
            ParsedDocument(
                filename="legal.pdf", doc_type="pdf", file_path="/p",
                chunks=[DocumentChunk(content=long_pdf_text, doc_type="pdf")]
            ),
            ParsedDocument(
                filename="analysis.md", doc_type="md", file_path="/p",
                chunks=[DocumentChunk(content=long_md_text, doc_type="md")]
            ),
        ]

        context = await analyzer.analyze(docs)

        # Services should include per-document extracted ones
        assert "Service from PDF" in context.services_mentioned
        assert "Service from MD" in context.services_mentioned
        assert "Another MD service" in context.services_mentioned

    @pytest.mark.asyncio
    async def test_analyze_extracts_contacts_regex_all_docs(self, mock_llm_client):
        """Test that regex contact extraction runs on all document types."""
        mock_llm_client.chat = AsyncMock(return_value='{"summary": "Test", "key_facts": [], "services": [], "contacts": {}, "prices": [], "questions": []}')

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)

        md_doc = ParsedDocument(
            filename="contacts.md", doc_type="md", file_path="/p",
            chunks=[DocumentChunk(
                content="Contact us at info@company.at or call +43 1 890 222. Visit www.company.at",
                doc_type="md"
            )]
        )

        context = await analyzer.analyze([md_doc])

        # Regex should extract email from MD
        assert "email" in context.all_contacts
        assert "info@company.at" in context.all_contacts["email"]

    @pytest.mark.asyncio
    async def test_analyze_per_doc_extraction_error_handled(self, mock_llm_client):
        """Test that per-document extraction errors don't break the pipeline."""
        # First call succeeds (LLM analyze), then extraction calls fail
        mock_llm_client.chat = AsyncMock(side_effect=[
            '{"summary": "Test", "key_facts": ["Fact"], "services": ["S1"], "contacts": {}, "prices": [], "questions": []}',
            Exception("LLM extraction error"),  # extract_services fails
            Exception("LLM extraction error"),  # extract_faq fails
        ])

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)

        doc = ParsedDocument(
            filename="test.md", doc_type="md", file_path="/p",
            chunks=[DocumentChunk(content="Content with enough words for extraction " * 5, doc_type="md")]
        )

        # Should not raise, should return context from main analysis
        context = await analyzer.analyze([doc])

        assert context.summary == "Test"
        assert "Fact" in context.key_facts
        assert "S1" in context.services_mentioned

    @pytest.mark.asyncio
    async def test_analyze_skips_short_docs(self, mock_llm_client):
        """Test that very short documents skip per-doc extraction."""
        mock_llm_client.chat = AsyncMock(return_value='{"summary": "Test", "key_facts": [], "services": [], "contacts": {}, "prices": [], "questions": []}')

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)

        short_doc = ParsedDocument(
            filename="tiny.md", doc_type="md", file_path="/p",
            chunks=[DocumentChunk(content="Too short", doc_type="md")]
        )

        context = await analyzer.analyze([short_doc])

        # Only 1 LLM call (main analyze), not 3 (analyze + services + faq)
        assert mock_llm_client.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_analyze_deduplicates_services(self, mock_llm_client):
        """Test that services are deduplicated (case-insensitive)."""
        responses = [
            '{"summary": "Test", "key_facts": [], "services": ["Delivery", "Storage"], "contacts": {}, "prices": [], "questions": []}',
            '["delivery", "Packing"]',  # "delivery" is duplicate (different case)
            '[]',  # faq
        ]
        mock_llm_client.chat = AsyncMock(side_effect=responses)

        analyzer = DocumentAnalyzer(llm_client=mock_llm_client)

        # Need >50 words for per-doc LLM extraction to trigger
        long_text = " ".join(["Document about delivery storage packing and logistics services for business customers"] * 8)

        doc = ParsedDocument(
            filename="services.md", doc_type="md", file_path="/p",
            chunks=[DocumentChunk(content=long_text, doc_type="md")]
        )

        context = await analyzer.analyze([doc])

        # Should have Delivery, Storage, Packing — but NOT duplicate "delivery"
        service_names_lower = [s.lower() for s in context.services_mentioned]
        assert service_names_lower.count("delivery") == 1
        assert "packing" in service_names_lower
