"""
Knowledge Base Module - Industry profiles and accumulated learnings.

Provides:
- IndustryProfile: Pydantic model for industry data
- IndustryKnowledgeManager: Main interface for knowledge base
- IndustryMatcher: Detects industry from text
- IndustryProfileLoader: Loads YAML profiles

Usage:
    from src.knowledge import IndustryKnowledgeManager

    manager = IndustryKnowledgeManager()

    # Get profile by ID
    profile = manager.get_profile("logistics")

    # Detect industry from text
    industry = manager.detect_industry("Мы занимаемся доставкой грузов")

    # Get context for interview
    context = manager.get_context_for_interview("logistics")

    # Record learning
    manager.record_learning("logistics", "Клиенты называют ТТН по-разному", "test_001")
"""

from .models import (
    # Original models
    IndustryProfile,
    IndustryMeta,
    PainPoint,
    RecommendedFunction,
    TypicalIntegration,
    IndustryFAQ,
    TypicalObjection,
    Learning,
    SuccessBenchmarks,
    IndustrySpecifics,
    IndustryIndex,
    IndustryIndexEntry,
    # v2.0 models
    SalesScript,
    Competitor,
    ROIExample,
    PricingContext,
    Seasonality,
    MarketContext,
)

from .loader import IndustryProfileLoader

from .matcher import IndustryMatcher

from .manager import (
    IndustryKnowledgeManager,
    get_knowledge_manager,
)

from .context_builder import (
    KBContextBuilder,
    get_kb_context_builder,
)

from .validator import (
    ProfileValidator,
    ValidationResult,
)

from .enriched_builder import (
    EnrichedContextBuilder,
    get_enriched_context_builder,
)

from .country_detector import (
    CountryDetector,
    get_country_detector,
)


__all__ = [
    # Models (original)
    "IndustryProfile",
    "IndustryMeta",
    "PainPoint",
    "RecommendedFunction",
    "TypicalIntegration",
    "IndustryFAQ",
    "TypicalObjection",
    "Learning",
    "SuccessBenchmarks",
    "IndustrySpecifics",
    "IndustryIndex",
    "IndustryIndexEntry",
    # Models (v2.0)
    "SalesScript",
    "Competitor",
    "ROIExample",
    "PricingContext",
    "Seasonality",
    "MarketContext",

    # Loader
    "IndustryProfileLoader",

    # Matcher
    "IndustryMatcher",

    # Manager
    "IndustryKnowledgeManager",
    "get_knowledge_manager",

    # Context Builder
    "KBContextBuilder",
    "get_kb_context_builder",

    # Validator
    "ProfileValidator",
    "ValidationResult",

    # Enriched Context Builder
    "EnrichedContextBuilder",
    "get_enriched_context_builder",

    # Country Detector
    "CountryDetector",
    "get_country_detector",
]
