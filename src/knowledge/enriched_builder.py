"""
Enriched Context Builder - Unified context combining KB, Documents, and Learnings.

v1.0: Initial implementation
"""

import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import structlog

from .context_builder import KBContextBuilder, SUCCESS_TAG
from .models import IndustryProfile, Learning

if TYPE_CHECKING:
    from .manager import IndustryKnowledgeManager
    from src.documents.models import DocumentContext

logger = structlog.get_logger("knowledge")


class EnrichedContextBuilder:
    """
    Unified context builder combining KB, Documents, and Learnings.

    Builds enriched context for consultation phases and voice agent.
    """

    def __init__(
        self,
        knowledge_manager: "IndustryKnowledgeManager",
        document_context: Optional["DocumentContext"] = None
    ):
        """
        Initialize enriched context builder.

        Args:
            knowledge_manager: Industry knowledge manager
            document_context: Optional document context from parsed documents
        """
        self.kb_manager = knowledge_manager
        self.doc_context = document_context
        self._kb_builder = KBContextBuilder()

    def build_for_phase(
        self,
        phase: str,
        dialogue_history: List[Dict[str, Any]],
        industry_profile: Optional[IndustryProfile] = None
    ) -> str:
        """
        Build enriched context for a consultation phase.

        Args:
            phase: Consultation phase (discovery, analysis, proposal, refinement)
            dialogue_history: Current dialogue history
            industry_profile: Pre-detected industry profile

        Returns:
            Formatted context string for prompt injection
        """
        parts: List[str] = []

        # Get or detect profile
        profile = industry_profile
        if profile is None:
            profile = self._detect_profile(dialogue_history)

        # Add KB context for phase
        if profile:
            kb_context = self._kb_builder.build_context(profile, phase)
            if kb_context:
                parts.append(kb_context)

            # Add learnings
            learnings_context = self._include_learnings(profile)
            if learnings_context:
                parts.append(learnings_context)

        # Add document context
        doc_context = self._include_documents()
        if doc_context:
            parts.append(doc_context)

        # Combine and prioritize
        if parts:
            combined = "\n\n".join(parts)
            return self._prioritize_by_dialogue(combined, dialogue_history)

        return ""

    def build_for_voice(
        self,
        dialogue_history: List[Dict[str, Any]]
    ) -> str:
        """
        Build compact context for voice agent.

        Returns shorter context optimized for voice interactions.

        Args:
            dialogue_history: Current dialogue history

        Returns:
            Compact formatted context string
        """
        profile = self._detect_profile(dialogue_history)
        if not profile:
            return ""

        parts: List[str] = []
        parts.append(f"[Отрасль: {profile.id}]")

        # High priority pain points only
        high_pains = profile.get_high_severity_pain_points()
        if high_pains:
            pains_list = ", ".join(p.description[:30] for p in high_pains[:3])
            parts.append(f"Боли: {pains_list}")

        # High priority functions only
        high_funcs = profile.get_high_priority_functions()
        if high_funcs:
            funcs_list = ", ".join(f.name for f in high_funcs[:3])
            parts.append(f"Функции: {funcs_list}")

        # Recent learnings (1-2 max)
        if profile.learnings:
            recent = profile.learnings[-1]
            parts.append(f"Опыт: {recent.insight[:50]}")

        return " | ".join(parts)

    def build_for_voice_full(
        self,
        dialogue_history: List[Dict[str, Any]],
        profile: Optional[IndustryProfile] = None,
        phase: str = "discovery",
    ) -> str:
        """
        Build full KB context for voice agent with phase awareness.

        Combines phase-specific KB context + v2.0 data (sales scripts,
        competitors, pricing, market) + learnings + documents.

        Args:
            dialogue_history: Current dialogue history
            profile: Pre-detected industry profile (avoids re-detection)
            phase: Current consultation phase

        Returns:
            Full formatted context string for prompt injection
        """
        MAX_CONTEXT_CHARS = 4000

        if profile is None:
            profile = self._detect_profile(dialogue_history)
        if not profile:
            return ""

        parts: List[str] = []

        # 1. Phase-specific KB context (uses kb_context.yaml blocks)
        kb_context = self._kb_builder.build_context(profile, phase)
        if kb_context:
            parts.append(kb_context)

        # 2. v2.0 data not covered by phase blocks
        v2_parts = self._build_v2_context(profile, phase)
        if v2_parts:
            parts.append(v2_parts)

        # 3. Learnings
        learnings_context = self._include_learnings(profile)
        if learnings_context:
            parts.append(learnings_context)

        # 4. Document context
        doc_context = self._include_documents()
        if doc_context:
            parts.append(doc_context)

        if not parts:
            return ""

        # Combine and enforce token budget
        combined = "\n\n".join(parts)
        if len(combined) > MAX_CONTEXT_CHARS:
            combined = combined[:MAX_CONTEXT_CHARS] + "\n[...контекст сокращён]"

        return self._prioritize_by_dialogue(combined, dialogue_history)

    def _build_v2_context(self, profile: IndustryProfile, phase: str) -> str:
        """
        Build context from v2.0 KB fields not covered by phase blocks.

        Only includes data relevant to the current phase to avoid duplication
        with what KBContextBuilder already provides.
        """
        parts: List[str] = []

        # Sales scripts — relevant in proposal and refinement
        if phase in ("proposal", "refinement") and profile.sales_scripts:
            # Already included via kb_context.yaml blocks, skip to avoid duplication
            pass

        # Competitors — relevant in analysis and proposal
        if phase in ("analysis", "discovery") and profile.competitors:
            comp_text = self._kb_builder._format_competitors(profile.competitors, {})
            if comp_text:
                parts.append(f"\nКонкурентный анализ:\n{comp_text}")

        # Pricing — relevant in proposal
        if phase == "discovery" and profile.pricing_context:
            price_text = self._kb_builder._format_pricing(profile.pricing_context, {})
            if price_text:
                parts.append(f"\nЦенообразование:\n{price_text}")

        # Market — relevant in discovery
        if phase in ("discovery", "proposal") and profile.market_context:
            # Already in analysis via kb_context.yaml, add to other phases
            market_text = self._kb_builder._format_market(profile.market_context, {})
            if market_text:
                parts.append(f"\nРыночный контекст:\n{market_text}")

        return "\n".join(parts) if parts else ""

    def _detect_profile(
        self,
        dialogue_history: List[Dict[str, Any]]
    ) -> Optional[IndustryProfile]:
        """
        Detect industry profile from dialogue history.

        Args:
            dialogue_history: Dialogue history

        Returns:
            IndustryProfile or None
        """
        if not dialogue_history:
            return None

        # Combine user messages for detection
        user_text = " ".join(
            msg.get("content", "")
            for msg in dialogue_history
            if msg.get("role") == "user"
        )

        if not user_text:
            return None

        industry_id = self.kb_manager.detect_industry(user_text)
        if industry_id:
            return self.kb_manager.get_profile(industry_id)

        return None

    def _include_learnings(
        self,
        profile: IndustryProfile,
        max_learnings: int = 5
    ) -> str:
        """
        Include recent learnings in context.

        Args:
            profile: Industry profile
            max_learnings: Maximum learnings to include

        Returns:
            Formatted learnings string
        """
        if not profile.learnings:
            return ""

        # Get recent learnings (newest first)
        recent = list(reversed(profile.learnings))[:max_learnings]

        parts = ["\n--- НАКОПЛЕННЫЙ ОПЫТ ---"]
        for learning in recent:
            is_success = SUCCESS_TAG in learning.insight
            insight = learning.insight.replace(f"{SUCCESS_TAG} ", "")
            prefix = "+" if is_success else "•"
            parts.append(f"{prefix} {insight}")

        parts.append("---")
        return "\n".join(parts)

    def _include_documents(self) -> str:
        """
        Include document context if available.

        Returns:
            Formatted document context string
        """
        if not self.doc_context:
            return ""

        # Use DocumentContext.to_prompt_context()
        return self.doc_context.to_prompt_context()

    def _prioritize_by_dialogue(
        self,
        context: str,
        dialogue_history: List[Dict[str, Any]]
    ) -> str:
        """
        Filter context by relevance to dialogue.

        Removes sections that are not relevant to current dialogue topics.

        Args:
            context: Full context string
            dialogue_history: Dialogue history

        Returns:
            Filtered context string
        """
        if not dialogue_history or not context:
            return context

        # Extract keywords from recent dialogue
        recent_messages = dialogue_history[-5:]
        dialogue_text = " ".join(
            msg.get("content", "").lower()
            for msg in recent_messages
        )

        # Define topic keywords
        topic_keywords = {
            "интеграци": ["интеграц", "crm", "erp", "api", "1с"],
            "функци": ["функци", "модуль", "возможност", "бот"],
            "боли": ["проблем", "боли", "сложност", "труд"],
            "цен": ["цен", "стоимост", "бюджет", "тариф"],
        }

        # Find active topics
        active_topics: List[str] = []
        for topic, keywords in topic_keywords.items():
            if any(kw in dialogue_text for kw in keywords):
                active_topics.append(topic)

        # If no specific topics, return full context
        if not active_topics:
            return context

        # For now, return full context (future: filter by topics)
        # This is a placeholder for more sophisticated filtering
        return context

    def set_document_context(self, doc_context: "DocumentContext"):
        """
        Set or update document context.

        Args:
            doc_context: Document context from parsed documents
        """
        self.doc_context = doc_context
        logger.debug("Document context updated")

    def get_industry_id(
        self,
        dialogue_history: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Get detected industry ID from dialogue.

        Args:
            dialogue_history: Dialogue history

        Returns:
            Industry ID or None
        """
        profile = self._detect_profile(dialogue_history)
        return profile.id if profile else None


# Singleton accessor
_builder: Optional[EnrichedContextBuilder] = None


def get_enriched_context_builder(
    knowledge_manager: Optional["IndustryKnowledgeManager"] = None,
    document_context: Optional["DocumentContext"] = None
) -> EnrichedContextBuilder:
    """
    Get or create enriched context builder singleton.

    Args:
        knowledge_manager: Knowledge manager (required on first call)
        document_context: Optional document context

    Returns:
        EnrichedContextBuilder instance
    """
    global _builder
    if _builder is None:
        if knowledge_manager is None:
            from .manager import get_knowledge_manager
            knowledge_manager = get_knowledge_manager()
        _builder = EnrichedContextBuilder(knowledge_manager, document_context)
    elif document_context is not None:
        _builder.set_document_context(document_context)
    return _builder
