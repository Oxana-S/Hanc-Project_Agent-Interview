"""
Document Analyzer - LLM-based document analysis.

v1.0: Initial implementation
"""

import json
import re
from typing import Any, Dict, List, Optional

import structlog

from .models import DocumentContext, ParsedDocument

logger = structlog.get_logger("documents")


class DocumentAnalyzer:
    """
    Анализатор документов с помощью LLM.

    Извлекает ключевые факты, услуги, контакты из документов.
    """

    def __init__(self, llm_client: Optional[Any] = None):
        """
        Инициализация анализатора.

        Args:
            llm_client: Клиент LLM (DeepSeekClient). Если None - используется lazy loading.
        """
        self._llm_client = llm_client

    @property
    def llm(self):
        """Lazy loading LLM клиента."""
        if self._llm_client is None:
            from src.llm.factory import create_llm_client

            self._llm_client = create_llm_client()
        return self._llm_client

    async def analyze(self, documents: List[ParsedDocument]) -> DocumentContext:
        """
        Проанализировать все документы и создать контекст.

        Args:
            documents: Список распарсенных документов

        Returns:
            DocumentContext с извлечённой информацией
        """
        if not documents:
            return DocumentContext()

        # Объединяем текст всех документов
        combined_text = self._combine_documents(documents)

        # Анализируем через LLM
        analysis = await self._llm_analyze(combined_text)

        # Формируем контекст
        context = DocumentContext(
            documents=documents,
            summary=analysis.get("summary", ""),
            key_facts=analysis.get("key_facts", []),
            services_mentioned=analysis.get("services", []),
            questions_to_clarify=analysis.get("questions", []),
            all_contacts=analysis.get("contacts", {}),
            all_prices=analysis.get("prices", []),
        )

        logger.info(
            "Documents analyzed",
            documents_count=len(documents),
            key_facts=len(context.key_facts),
            services=len(context.services_mentioned),
        )

        return context

    def _combine_documents(self, documents: List[ParsedDocument]) -> str:
        """Объединить текст документов с метками источников."""
        parts = []

        for doc in documents:
            parts.append(f"\n=== Документ: {doc.filename} ===\n")
            parts.append(doc.full_text[:15000])  # Ограничиваем размер

        return "\n".join(parts)

    async def _llm_analyze(self, text: str) -> Dict[str, Any]:
        """Анализ текста через LLM."""
        prompt = f"""Проанализируй документы клиента и извлеки структурированную информацию.

ДОКУМЕНТЫ:
{text[:20000]}

Верни JSON с полями:
{{
    "summary": "Краткая сводка (2-3 предложения) о чём эти документы",
    "key_facts": ["Факт 1 о бизнесе", "Факт 2", ...],
    "services": ["Услуга 1", "Услуга 2", ...],
    "contacts": {{"телефон": "...", "email": "...", "адрес": "..."}},
    "prices": [{{"service": "...", "price": "..."}}],
    "questions": ["Вопрос 1 для уточнения", "Вопрос 2", ...]
}}

ВАЖНО:
- Извлекай только явно указанную информацию
- Если чего-то нет — оставь пустым
- Вопросы — это то, что неясно из документов и стоит уточнить у клиента
- Верни ТОЛЬКО валидный JSON без markdown"""

        try:
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            # Парсим JSON из ответа
            return self._parse_json_response(response)

        except Exception as e:
            logger.error("LLM analysis failed", error=str(e))
            return {}

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Извлечь JSON из ответа LLM."""
        # Пробуем напрямую
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Ищем JSON в markdown блоке
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Ищем фигурные скобки
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON from LLM response")
        return {}

    async def extract_services(self, doc: ParsedDocument) -> List[str]:
        """
        Извлечь услуги из документа.

        Args:
            doc: Распарсенный документ

        Returns:
            Список услуг
        """
        prompt = f"""Извлеки список услуг/продуктов из документа.

ДОКУМЕНТ: {doc.filename}
{doc.full_text[:10000]}

Верни JSON массив услуг: ["Услуга 1", "Услуга 2", ...]
Только валидный JSON."""

        try:
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )

            # Парсим массив
            services = self._parse_json_array(response)
            doc.extracted_services = services
            return services

        except Exception as e:
            logger.error("Service extraction failed", error=str(e))
            return []

    async def extract_faq(self, doc: ParsedDocument) -> List[Dict[str, str]]:
        """
        Извлечь FAQ из документа (если есть).

        Args:
            doc: Распарсенный документ

        Returns:
            Список FAQ
        """
        prompt = f"""Найди вопросы и ответы (FAQ) в документе.

ДОКУМЕНТ: {doc.filename}
{doc.full_text[:10000]}

Верни JSON массив: [{{"question": "Вопрос?", "answer": "Ответ"}}]
Если FAQ нет — верни пустой массив []"""

        try:
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )

            faq = self._parse_json_array(response)
            doc.extracted_faq = faq
            return faq

        except Exception as e:
            logger.error("FAQ extraction failed", error=str(e))
            return []

    def _parse_json_array(self, response: str) -> List[Any]:
        """Извлечь JSON массив из ответа."""
        # Пробуем напрямую
        try:
            result = json.loads(response)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # Ищем массив
        array_match = re.search(r"\[[\s\S]*\]", response)
        if array_match:
            try:
                result = json.loads(array_match.group(0))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        return []

    def analyze_sync(self, documents: List[ParsedDocument]) -> DocumentContext:
        """
        Синхронный анализ документов (без LLM).

        Извлекает базовую информацию с помощью регулярных выражений.
        Используется когда LLM недоступен или не нужен.

        Args:
            documents: Список документов

        Returns:
            DocumentContext с базовой информацией
        """
        if not documents:
            return DocumentContext()

        all_text = " ".join(doc.full_text for doc in documents)

        # Извлекаем контакты регулярками
        contacts = self._extract_contacts_regex(all_text)

        # Извлекаем ключевые факты (первые предложения секций)
        key_facts = self._extract_key_sentences(documents)

        # Создаём простую сводку
        summary = f"Загружено {len(documents)} документов: {', '.join(d.filename for d in documents)}"

        return DocumentContext(
            documents=documents,
            summary=summary,
            key_facts=key_facts[:10],
            all_contacts=contacts,
        )

    def _extract_contacts_regex(self, text: str) -> Dict[str, str]:
        """Извлечь контакты с помощью регулярных выражений."""
        contacts = {}

        # Телефон
        phone_match = re.search(
            r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
            text
        )
        if phone_match:
            contacts["телефон"] = phone_match.group(0)

        # Email
        email_match = re.search(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            text
        )
        if email_match:
            contacts["email"] = email_match.group(0)

        # Сайт
        site_match = re.search(
            r"(?:https?://)?(?:www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z]{2,}(?:/\S*)?",
            text
        )
        if site_match:
            contacts["сайт"] = site_match.group(0)

        return contacts

    def _extract_key_sentences(self, documents: List[ParsedDocument]) -> List[str]:
        """Извлечь ключевые предложения из документов."""
        facts = []

        for doc in documents:
            for chunk in doc.chunks[:5]:  # Первые 5 чанков
                # Берём первое предложение каждого чанка
                sentences = re.split(r"[.!?]\s+", chunk.content)
                if sentences and sentences[0]:
                    fact = sentences[0].strip()[:200]
                    if len(fact) > 20:  # Фильтруем слишком короткие
                        facts.append(fact)

        return facts
