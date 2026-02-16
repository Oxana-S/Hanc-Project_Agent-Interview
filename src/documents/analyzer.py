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

        # Per-document structured extraction (services, FAQ) for ALL doc types
        all_services = list(analysis.get("services", []))
        all_contacts = dict(analysis.get("contacts", {}))
        all_prices = list(analysis.get("prices", []))

        for doc in documents:
            # Regex-based contact extraction for ALL doc types (fast, no LLM)
            if doc.full_text:
                regex_contacts = self._extract_contacts_regex(doc.full_text)
                for key, value in regex_contacts.items():
                    if key not in all_contacts or not all_contacts[key]:
                        all_contacts[key] = value
                doc.extracted_contacts = regex_contacts

            # LLM-based extraction only for docs with meaningful content (>50 words)
            if doc.word_count < 50:
                continue

            try:
                services = await self.extract_services(doc)
                if services:
                    # Merge unique services
                    existing = set(s.lower() for s in all_services)
                    for s in services:
                        if s.lower() not in existing:
                            all_services.append(s)
                            existing.add(s.lower())
            except Exception as e:
                logger.warning("per_doc_service_extraction_failed", filename=doc.filename, error=str(e))

            try:
                faq = await self.extract_faq(doc)
                # FAQ stored on doc.extracted_faq by extract_faq()
            except Exception as e:
                logger.warning("per_doc_faq_extraction_failed", filename=doc.filename, error=str(e))

        # Формируем контекст
        context = DocumentContext(
            documents=documents,
            summary=analysis.get("summary", ""),
            key_facts=analysis.get("key_facts", []),
            services_mentioned=all_services,
            questions_to_clarify=analysis.get("questions", []),
            all_contacts=all_contacts,
            all_prices=all_prices,
        )

        logger.info(
            "Documents analyzed",
            documents_count=len(documents),
            key_facts=len(context.key_facts),
            services=len(context.services_mentioned),
            contacts=len(context.all_contacts),
        )

        return context

    def _combine_documents(self, documents: List[ParsedDocument]) -> str:
        """Объединить текст документов с метками источников.

        Все документы обрабатываются равноценно — MD и TXT так же важны, как PDF.
        Каждый документ помечен типом для LLM-контекста.
        """
        parts = []

        for doc in documents:
            doc_type_label = {
                "pdf": "PDF",
                "md": "Markdown",
                "docx": "Word",
                "xlsx": "Excel",
                "txt": "Текст",
            }.get(doc.doc_type, doc.doc_type.upper())
            parts.append(f"\n=== Документ [{doc_type_label}]: {doc.filename} ===\n")
            parts.append(doc.full_text[:20000])  # 20K per doc

        return "\n".join(parts)

    async def _llm_analyze(self, text: str) -> Dict[str, Any]:
        """Анализ текста через LLM."""
        prompt = f"""Проанализируй ВСЕ документы клиента и извлеки структурированную информацию.

ДОКУМЕНТЫ:
{text[:30000]}

Верни JSON с полями:
{{
    "summary": "Краткая сводка (3-5 предложений), покрывающая ВСЕ документы — и правовые, и бизнес-анализ, и экономику",
    "key_facts": ["Факт 1 о бизнесе", "Факт 2 (финансовый)", "Факт 3 (правовой)", ...],
    "services": ["Услуга 1", "Услуга 2", ...],
    "contacts": {{"телефон": "...", "email": "...", "адрес": "...", "сайт": "..."}},
    "prices": [{{"service": "...", "price": "..."}}],
    "questions": ["Вопрос 1 для уточнения", "Вопрос 2", ...]
}}

КРИТИЧЕСКИ ВАЖНО:
- Анализируй ВСЕ документы РАВНОЦЕННО — не игнорируй ни один тип (MD, PDF, DOCX, TXT)
- Документы бизнес-анализа (экономика, ROI, агенты) так же важны, как правовые
- Извлекай финансовые данные: средний чек, выручка, ROI, экономия, бюджеты
- Извлекай данные о команде: врачи, специалисты, количество сотрудников
- Извлекай данные о клиентопотоке: пациенты/день, звонки/день
- Извлекай все упомянутые интеграции и системы
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
