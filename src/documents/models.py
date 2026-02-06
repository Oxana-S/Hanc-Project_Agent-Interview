"""
Document Analysis Models - Pydantic models for document parsing and analysis.

v1.0: Initial implementation
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """Часть документа для анализа."""

    content: str
    doc_type: str  # pdf, docx, md, xlsx
    section: Optional[str] = None  # Заголовок секции
    page: Optional[int] = None  # Номер страницы (для PDF)
    row_range: Optional[str] = None  # Диапазон строк (для XLSX)


class ParsedDocument(BaseModel):
    """Распарсенный документ."""

    filename: str
    doc_type: str  # pdf, docx, md, xlsx
    file_path: str
    chunks: List[DocumentChunk] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Извлечённая информация (заполняется анализатором)
    extracted_services: List[str] = Field(default_factory=list)
    extracted_faq: List[Dict[str, str]] = Field(default_factory=list)
    extracted_prices: List[Dict[str, Any]] = Field(default_factory=list)
    extracted_contacts: Dict[str, str] = Field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Объединённый текст всех чанков."""
        return "\n\n".join(chunk.content for chunk in self.chunks if chunk.content)

    @property
    def word_count(self) -> int:
        """Количество слов в документе."""
        return len(self.full_text.split())


class DocumentContext(BaseModel):
    """Контекст из всех документов для интервью."""

    documents: List[ParsedDocument] = Field(default_factory=list)
    summary: str = ""  # LLM-сводка всех документов
    key_facts: List[str] = Field(default_factory=list)
    services_mentioned: List[str] = Field(default_factory=list)
    questions_to_clarify: List[str] = Field(default_factory=list)

    # Агрегированные данные
    all_contacts: Dict[str, str] = Field(default_factory=dict)
    all_prices: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def total_documents(self) -> int:
        """Общее количество документов."""
        return len(self.documents)

    @property
    def total_words(self) -> int:
        """Общее количество слов во всех документах."""
        return sum(doc.word_count for doc in self.documents)

    def get_documents_by_type(self, doc_type: str) -> List[ParsedDocument]:
        """Получить документы определённого типа."""
        return [doc for doc in self.documents if doc.doc_type == doc_type]

    def to_prompt_context(self) -> str:
        """
        Преобразовать в строку для добавления в промпт LLM.

        Returns:
            Форматированная строка с контекстом из документов
        """
        if not self.documents:
            return ""

        parts = ["### Контекст из документов клиента:\n"]

        if self.summary:
            parts.append(f"**Сводка:** {self.summary}\n")

        if self.key_facts:
            parts.append("**Ключевые факты:**")
            for fact in self.key_facts[:10]:  # Ограничиваем до 10
                parts.append(f"- {fact}")
            parts.append("")

        if self.services_mentioned:
            parts.append(f"**Упомянутые услуги:** {', '.join(self.services_mentioned[:15])}\n")

        if self.all_contacts:
            contacts_str = ", ".join(f"{k}: {v}" for k, v in self.all_contacts.items())
            parts.append(f"**Контакты:** {contacts_str}\n")

        if self.questions_to_clarify:
            parts.append("**Вопросы для уточнения:**")
            for q in self.questions_to_clarify[:5]:
                parts.append(f"- {q}")

        return "\n".join(parts)
