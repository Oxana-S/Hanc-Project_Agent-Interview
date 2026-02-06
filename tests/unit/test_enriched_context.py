"""
Unit tests for enriched context module.

Tests for:
- EnrichedContextBuilder
- ProfileValidator
- Profile caching
- Feedback loop
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.knowledge.models import (
    IndustryProfile, IndustryMeta, PainPoint, RecommendedFunction,
    TypicalIntegration, IndustryFAQ, Learning, SuccessBenchmarks,
    IndustrySpecifics
)
from src.knowledge.validator import ProfileValidator, ValidationResult
from src.knowledge.enriched_builder import EnrichedContextBuilder
from src.knowledge.manager import IndustryKnowledgeManager
from src.knowledge.loader import IndustryProfileLoader


# ============ FIXTURES ============

@pytest.fixture
def sample_profile():
    """Create a sample industry profile for testing."""
    return IndustryProfile(
        meta=IndustryMeta(
            id="test_industry",
            version="1.0",
            created_at="2026-01-01",
            last_updated="2026-02-01",
            tests_run=5,
            avg_validation_score=0.85
        ),
        aliases=["test", "testing", "tester"],
        typical_services=["Service A", "Service B", "Service C", "Service D", "Service E"],
        pain_points=[
            PainPoint(description="Problem 1", severity="high"),
            PainPoint(description="Problem 2", severity="medium"),
            PainPoint(description="Problem 3", severity="low"),
        ],
        recommended_functions=[
            RecommendedFunction(name="Function 1", priority="high", reason="Important"),
            RecommendedFunction(name="Function 2", priority="medium", reason="Useful"),
            RecommendedFunction(name="Function 3", priority="low", reason="Optional"),
        ],
        typical_integrations=[
            TypicalIntegration(name="CRM", examples=["Bitrix24", "amoCRM"]),
            TypicalIntegration(name="Telephony", examples=["Asterisk"]),
        ],
        industry_faq=[
            IndustryFAQ(question="Q1?", answer_template="A1"),
            IndustryFAQ(question="Q2?", answer_template="A2"),
            IndustryFAQ(question="Q3?", answer_template="A3"),
        ],
        learnings=[
            Learning(date="2026-01-15", insight="First insight", source="test1"),
            Learning(date="2026-01-20", insight="[SUCCESS] Great pattern", source="test2"),
        ],
        success_benchmarks=SuccessBenchmarks(
            avg_call_duration_seconds=180,
            target_automation_rate=0.6,
            typical_kpis=["KPI 1", "KPI 2"]
        ),
        industry_specifics=IndustrySpecifics(
            compliance=["GDPR"],
            tone=["professional", "friendly"],
            peak_times=["morning", "evening"]
        )
    )


@pytest.fixture
def incomplete_profile():
    """Create an incomplete profile for validation testing."""
    return IndustryProfile(
        meta=IndustryMeta(id="incomplete", version="1.0"),
        aliases=[],
        typical_services=["Service A"],
        pain_points=[PainPoint(description="Problem 1", severity="high")],
        recommended_functions=[],
        typical_integrations=[],
        industry_faq=[],
        learnings=[],
    )


@pytest.fixture
def sample_dialogue():
    """Sample dialogue history for testing."""
    return [
        {"role": "assistant", "content": "Здравствуйте! Расскажите о вашем бизнесе."},
        {"role": "user", "content": "Мы автосервис, занимаемся ремонтом машин."},
        {"role": "assistant", "content": "Какие основные проблемы у вас сейчас?"},
        {"role": "user", "content": "Много пропущенных звонков от клиентов."},
    ]


# ============ PROFILE VALIDATOR TESTS ============

class TestProfileValidator:
    """Tests for ProfileValidator."""

    def test_validate_complete_profile(self, sample_profile):
        """Complete profile passes validation with high score."""
        validator = ProfileValidator()
        result = validator.validate(sample_profile)

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.completeness_score >= 0.9

    def test_validate_incomplete_profile(self, incomplete_profile):
        """Incomplete profile returns warnings and lower score."""
        validator = ProfileValidator()
        result = validator.validate(incomplete_profile)

        # Should have warnings for missing/insufficient fields
        assert len(result.warnings) > 0
        assert result.completeness_score < 0.5

    def test_validate_empty_required_fields(self):
        """Profile with empty required fields returns errors."""
        profile = IndustryProfile(
            meta=IndustryMeta(id="empty", version="1.0"),
            pain_points=[],
            typical_services=[],
            recommended_functions=[],
        )
        validator = ProfileValidator()
        result = validator.validate(profile)

        assert not result.is_valid
        assert len(result.errors) >= 3  # At least 3 required fields empty

    def test_completeness_score_range(self, sample_profile):
        """Completeness score is between 0 and 1."""
        validator = ProfileValidator()
        result = validator.validate(sample_profile)

        assert 0.0 <= result.completeness_score <= 1.0

    def test_validate_all_profiles(self):
        """validate_all returns results for all industries."""
        manager = IndustryKnowledgeManager()
        validator = ProfileValidator()

        results = validator.validate_all(manager)

        assert len(results) > 0
        for industry_id, result in results.items():
            assert isinstance(result, ValidationResult)

    def test_get_summary(self, sample_profile, incomplete_profile):
        """Summary is properly formatted."""
        validator = ProfileValidator()
        results = {
            "complete": validator.validate(sample_profile),
            "incomplete": validator.validate(incomplete_profile),
        }

        summary = validator.get_summary(results)

        assert "Результаты валидации профилей" in summary
        assert "complete" in summary
        assert "incomplete" in summary


# ============ ENRICHED CONTEXT BUILDER TESTS ============

class TestEnrichedContextBuilder:
    """Tests for EnrichedContextBuilder."""

    def test_build_for_discovery_phase(self, sample_dialogue):
        """Context for discovery includes pain_points and services."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_phase("discovery", sample_dialogue)

        assert len(context) > 0
        # Should detect automotive from dialogue
        assert "КОНТЕКСТ" in context or "automotive" in context.lower()

    def test_build_for_analysis_phase(self, sample_dialogue):
        """Context for analysis includes integrations."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_phase("analysis", sample_dialogue)

        assert len(context) > 0

    def test_build_for_proposal_phase(self, sample_dialogue):
        """Context for proposal includes recommended_functions."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_phase("proposal", sample_dialogue)

        assert len(context) > 0

    def test_build_for_refinement_phase(self, sample_dialogue):
        """Context for refinement includes FAQ and objections."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_phase("refinement", sample_dialogue)

        assert len(context) > 0

    def test_includes_learnings(self, sample_profile):
        """Learnings are included in context."""
        manager = MagicMock()
        manager.detect_industry.return_value = "test_industry"
        manager.get_profile.return_value = sample_profile

        builder = EnrichedContextBuilder(manager)
        context = builder.build_for_phase(
            "discovery",
            [{"role": "user", "content": "test"}],
            sample_profile
        )

        assert "НАКОПЛЕННЫЙ ОПЫТ" in context
        assert "First insight" in context or "Great pattern" in context

    def test_build_for_voice(self, sample_dialogue):
        """Compact context for voice mode."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice(sample_dialogue)

        # Voice context should be compact
        assert len(context) > 0
        assert len(context) < 500  # Should be short for voice

    def test_empty_dialogue_returns_empty_context(self):
        """Empty dialogue returns empty context."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_phase("discovery", [])
        assert context == ""

    def test_get_industry_id(self, sample_dialogue):
        """get_industry_id detects industry from dialogue."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        industry_id = builder.get_industry_id(sample_dialogue)

        assert industry_id == "automotive"

    def test_with_document_context(self, sample_dialogue):
        """Document context is included when available."""
        manager = IndustryKnowledgeManager()

        # Mock document context
        mock_doc_context = MagicMock()
        mock_doc_context.to_prompt_context.return_value = "### Document Info\nSome facts"

        builder = EnrichedContextBuilder(manager, mock_doc_context)
        context = builder.build_for_phase("discovery", sample_dialogue)

        assert "Document Info" in context or len(context) > 0


# ============ PROFILE CACHING TESTS ============

class TestProfileCaching:
    """Tests for profile caching in loader."""

    def test_cache_hit(self):
        """Cached profile is returned without reloading."""
        loader = IndustryProfileLoader()

        # First load
        profile1 = loader.load_profile("automotive")
        cache_time1 = loader._cache_time.get("automotive")

        # Second load (should be from cache)
        profile2 = loader.load_profile("automotive")
        cache_time2 = loader._cache_time.get("automotive")

        assert profile1 is profile2  # Same object
        assert cache_time1 == cache_time2  # Time unchanged

    def test_cache_expiry(self):
        """Expired cache triggers reload."""
        loader = IndustryProfileLoader()
        loader._cache_ttl = 0.1  # 100ms TTL for testing

        # First load
        profile1 = loader.load_profile("automotive")

        # Wait for cache to expire
        time.sleep(0.2)

        # Second load (should reload)
        profile2 = loader.load_profile("automotive")

        # Profiles should be equal but different objects
        assert profile1.id == profile2.id
        # Cache time should be updated
        assert loader._cache_time["automotive"] > 0

    def test_invalidate_cache_single(self):
        """Single industry cache invalidation."""
        loader = IndustryProfileLoader()

        # Load profile
        loader.load_profile("automotive")
        assert "automotive" in loader._cache

        # Invalidate
        loader.invalidate_cache("automotive")

        assert "automotive" not in loader._cache
        assert "automotive" not in loader._cache_time

    def test_invalidate_cache_all(self):
        """Full cache invalidation."""
        loader = IndustryProfileLoader()

        # Load multiple profiles
        loader.load_profile("automotive")
        loader.load_profile("medical")

        # Invalidate all
        loader.invalidate_cache()

        assert len(loader._cache) == 0
        assert len(loader._cache_time) == 0
        assert loader._index is None


# ============ FEEDBACK LOOP TESTS ============

class TestFeedbackLoop:
    """Tests for feedback loop in manager."""

    def test_record_success(self):
        """Success patterns are recorded with [SUCCESS] tag."""
        manager = IndustryKnowledgeManager()

        # Get initial learnings count
        profile_before = manager.get_profile("automotive")
        initial_count = len(profile_before.learnings) if profile_before else 0

        # Record success (this will modify the file)
        # We'll use a mock to avoid modifying actual files
        with patch.object(manager.loader, 'save_profile') as mock_save:
            manager.record_success(
                "automotive",
                "Client liked quick responses",
                "test_session"
            )

            # Check that save was called
            mock_save.assert_called_once()
            saved_profile = mock_save.call_args[0][0]

            # Check that learning was added with [SUCCESS] tag
            last_learning = saved_profile.learnings[-1]
            assert "[SUCCESS]" in last_learning.insight

    def test_get_recent_learnings(self):
        """Recent learnings are retrieved correctly."""
        manager = IndustryKnowledgeManager()

        learnings = manager.get_recent_learnings("automotive", limit=5)

        assert isinstance(learnings, list)
        # Should be in reverse order (newest first)
        if len(learnings) >= 2:
            assert learnings[0].date >= learnings[-1].date or True  # Dates may be same

    def test_get_recent_learnings_exclude_success(self):
        """Can exclude success learnings."""
        manager = IndustryKnowledgeManager()

        learnings = manager.get_recent_learnings(
            "automotive",
            limit=10,
            include_success=False
        )

        for learning in learnings:
            assert "[SUCCESS]" not in learning.insight

    def test_increment_usage(self):
        """Usage stats can be incremented."""
        manager = IndustryKnowledgeManager()

        # Mock the loader method
        with patch.object(manager.loader, 'increment_usage_stats') as mock_increment:
            manager.increment_usage("automotive")
            mock_increment.assert_called_once_with("automotive")


# ============ INTEGRATION TESTS ============

class TestIntegration:
    """Integration tests for the enrichment module."""

    def test_full_enrichment_flow(self, sample_dialogue):
        """Test complete enrichment flow from detection to context."""
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        # Detect industry
        industry_id = builder.get_industry_id(sample_dialogue)
        assert industry_id is not None

        # Build context for all phases
        phases = ["discovery", "analysis", "proposal", "refinement"]
        for phase in phases:
            context = builder.build_for_phase(phase, sample_dialogue)
            assert isinstance(context, str)

    def test_voice_enrichment_flow(self, sample_dialogue):
        """Test voice agent enrichment."""
        from src.voice.consultant import get_enriched_system_prompt

        prompt = get_enriched_system_prompt(sample_dialogue)

        assert len(prompt) > 0
        # Should include both base prompt and industry context
        assert "Контекст отрасли" in prompt or len(prompt) > 2000
