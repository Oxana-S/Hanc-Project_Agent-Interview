"""
Unit tests for knowledge module.
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import yaml

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.knowledge.models import (
    PainPoint, RecommendedFunction, TypicalIntegration, IndustryFAQ,
    TypicalObjection, Learning, IndustryMeta, SuccessBenchmarks,
    IndustrySpecifics, IndustryProfile, IndustryIndexEntry, IndustryIndex
)
from src.knowledge.loader import IndustryProfileLoader
from src.knowledge.matcher import IndustryMatcher
from src.knowledge.manager import IndustryKnowledgeManager, get_knowledge_manager
from src.knowledge.context_builder import KBContextBuilder, get_kb_context_builder


# ============ MODEL TESTS ============

class TestPainPoint:
    """Test PainPoint model."""

    def test_pain_point_default_severity(self):
        """Test default severity is medium."""
        pp = PainPoint(description="Customer wait times")
        assert pp.severity == "medium"
        assert pp.solution_hint is None

    def test_pain_point_with_all_fields(self):
        """Test pain point with all fields."""
        pp = PainPoint(
            description="High call volume",
            severity="high",
            solution_hint="Use queue management"
        )
        assert pp.description == "High call volume"
        assert pp.severity == "high"
        assert pp.solution_hint == "Use queue management"


class TestRecommendedFunction:
    """Test RecommendedFunction model."""

    def test_function_default_priority(self):
        """Test default priority is medium."""
        func = RecommendedFunction(name="Auto-dialer")
        assert func.priority == "medium"
        assert func.reason is None

    def test_function_with_all_fields(self):
        """Test function with all fields."""
        func = RecommendedFunction(
            name="CRM Integration",
            priority="high",
            reason="Essential for customer data"
        )
        assert func.name == "CRM Integration"
        assert func.priority == "high"
        assert func.reason == "Essential for customer data"


class TestTypicalIntegration:
    """Test TypicalIntegration model."""

    def test_integration_defaults(self):
        """Test integration default values."""
        integ = TypicalIntegration(name="CRM")
        assert integ.examples == []
        assert integ.priority == "medium"
        assert integ.reason is None

    def test_integration_with_examples(self):
        """Test integration with examples."""
        integ = TypicalIntegration(
            name="ERP Systems",
            examples=["SAP", "Oracle", "1C"],
            priority="high",
            reason="For inventory management"
        )
        assert integ.name == "ERP Systems"
        assert len(integ.examples) == 3
        assert "SAP" in integ.examples


class TestIndustryFAQ:
    """Test IndustryFAQ model."""

    def test_faq_creation(self):
        """Test FAQ creation."""
        faq = IndustryFAQ(
            question="What are your delivery times?",
            answer_template="Our standard delivery is 2-3 business days"
        )
        assert "delivery times" in faq.question
        assert "2-3" in faq.answer_template


class TestTypicalObjection:
    """Test TypicalObjection model."""

    def test_objection_creation(self):
        """Test objection creation."""
        obj = TypicalObjection(
            objection="It's too expensive",
            response="Let me explain our value proposition"
        )
        assert "expensive" in obj.objection
        assert "value proposition" in obj.response


class TestLearning:
    """Test Learning model."""

    def test_learning_creation(self):
        """Test learning creation."""
        learning = Learning(
            date="2024-01-15",
            insight="Customers prefer SMS notifications",
            source="test_logistics_001"
        )
        assert learning.date == "2024-01-15"
        assert "SMS" in learning.insight
        assert learning.source == "test_logistics_001"

    def test_learning_optional_source(self):
        """Test learning without source."""
        learning = Learning(date="2024-01-15", insight="Some insight")
        assert learning.source is None


class TestIndustryMeta:
    """Test IndustryMeta model."""

    def test_meta_defaults(self):
        """Test meta default values."""
        meta = IndustryMeta(id="logistics")
        assert meta.version == "1.0"
        assert meta.tests_run == 0
        assert meta.avg_validation_score == 0.0

    def test_meta_with_values(self):
        """Test meta with custom values."""
        meta = IndustryMeta(
            id="medical",
            version="2.0",
            created_at="2024-01-01",
            last_updated="2024-02-15",
            tests_run=10,
            avg_validation_score=0.85
        )
        assert meta.id == "medical"
        assert meta.tests_run == 10


class TestSuccessBenchmarks:
    """Test SuccessBenchmarks model."""

    def test_benchmarks_defaults(self):
        """Test default benchmark values."""
        benchmarks = SuccessBenchmarks()
        assert benchmarks.avg_call_duration_seconds == 180
        assert benchmarks.target_automation_rate == 0.6
        assert benchmarks.typical_kpis == []

    def test_benchmarks_with_kpis(self):
        """Test benchmarks with KPIs."""
        benchmarks = SuccessBenchmarks(
            avg_call_duration_seconds=240,
            target_automation_rate=0.75,
            typical_kpis=["Response time < 2s", "Resolution rate > 80%"]
        )
        assert len(benchmarks.typical_kpis) == 2


class TestIndustrySpecifics:
    """Test IndustrySpecifics model."""

    def test_specifics_defaults(self):
        """Test specifics default values."""
        specifics = IndustrySpecifics()
        assert specifics.compliance == []
        assert specifics.tone == []
        assert specifics.peak_times == []

    def test_specifics_with_values(self):
        """Test specifics with values."""
        specifics = IndustrySpecifics(
            compliance=["HIPAA", "GDPR"],
            tone=["professional", "empathetic"],
            peak_times=["morning", "evening"]
        )
        assert "HIPAA" in specifics.compliance
        assert len(specifics.tone) == 2


class TestIndustryProfile:
    """Test IndustryProfile model."""

    @pytest.fixture
    def sample_profile(self):
        """Create a sample industry profile."""
        return IndustryProfile(
            meta=IndustryMeta(id="logistics", version="1.0"),
            aliases=["доставка", "грузоперевозки"],
            typical_services=["Delivery", "Warehousing"],
            pain_points=[
                PainPoint(description="Lost packages", severity="high"),
                PainPoint(description="Delays", severity="medium")
            ],
            recommended_functions=[
                RecommendedFunction(name="Tracking", priority="high"),
                RecommendedFunction(name="Notifications", priority="medium")
            ],
            typical_integrations=[
                TypicalIntegration(name="GPS", examples=["Wialon", "Gurtam"])
            ],
            industry_faq=[
                IndustryFAQ(question="Where is my package?", answer_template="Let me check...")
            ],
            success_benchmarks=SuccessBenchmarks(typical_kpis=["Delivery rate > 95%"])
        )

    def test_profile_id_property(self, sample_profile):
        """Test profile id property."""
        assert sample_profile.id == "logistics"

    def test_profile_version_property(self, sample_profile):
        """Test profile version property."""
        assert sample_profile.version == "1.0"

    def test_get_high_priority_functions(self, sample_profile):
        """Test getting high priority functions."""
        high_priority = sample_profile.get_high_priority_functions()
        assert len(high_priority) == 1
        assert high_priority[0].name == "Tracking"

    def test_get_high_priority_integrations(self, sample_profile):
        """Test getting high priority integrations."""
        # No high priority integrations in fixture
        high_priority = sample_profile.get_high_priority_integrations()
        assert len(high_priority) == 0

    def test_get_high_severity_pain_points(self, sample_profile):
        """Test getting high severity pain points."""
        high_severity = sample_profile.get_high_severity_pain_points()
        assert len(high_severity) == 1
        assert high_severity[0].description == "Lost packages"

    def test_to_context_dict(self, sample_profile):
        """Test converting profile to context dict."""
        context = sample_profile.to_context_dict()

        assert context["industry_id"] == "logistics"
        assert "Delivery" in context["typical_services"]
        assert len(context["pain_points"]) == 2
        assert len(context["recommended_functions"]) == 2
        assert len(context["typical_integrations"]) == 1
        assert len(context["faq"]) == 1
        assert "typical_kpis" in context["success_benchmarks"]


class TestIndustryIndex:
    """Test IndustryIndex and IndustryIndexEntry models."""

    def test_index_entry_creation(self):
        """Test index entry creation."""
        entry = IndustryIndexEntry(
            file="logistics.yaml",
            name="Logistics",
            description="Logistics and delivery companies",
            aliases=["доставка", "грузоперевозки"]
        )
        assert entry.file == "logistics.yaml"
        assert len(entry.aliases) == 2

    def test_index_defaults(self):
        """Test index default values."""
        index = IndustryIndex()
        assert index.meta == {}
        assert index.industries == {}
        assert index.usage_stats == {}

    def test_index_with_industries(self):
        """Test index with industries."""
        index = IndustryIndex(
            meta={"version": "1.0"},
            industries={
                "logistics": IndustryIndexEntry(
                    file="logistics.yaml",
                    name="Logistics",
                    description="Logistics companies"
                )
            }
        )
        assert "logistics" in index.industries
        assert index.industries["logistics"].name == "Logistics"


# ============ LOADER TESTS ============

class TestIndustryProfileLoader:
    """Test IndustryProfileLoader class."""

    @pytest.fixture
    def mock_config_dir(self, tmp_path):
        """Create a temp directory with mock industry files."""
        industries_dir = tmp_path / "industries"
        industries_dir.mkdir()

        # Create index file
        index_data = {
            "meta": {"version": "1.0"},
            "industries": {
                "logistics": {
                    "file": "logistics.yaml",
                    "name": "Logistics",
                    "description": "Logistics companies",
                    "aliases": ["доставка"]
                }
            }
        }
        with open(industries_dir / "_index.yaml", "w", encoding="utf-8") as f:
            yaml.dump(index_data, f, allow_unicode=True)

        # Create logistics profile
        profile_data = {
            "meta": {
                "id": "logistics",
                "version": "1.0",
                "created_at": "2024-01-01",
                "last_updated": "2024-01-15",
                "tests_run": 5,
                "avg_validation_score": 0.82
            },
            "aliases": ["доставка", "грузоперевозки", "транспорт"],
            "typical_services": ["Доставка грузов", "Складирование"],
            "pain_points": [
                {"description": "Потерянные посылки", "severity": "high"},
                {"description": "Задержки", "severity": "medium"}
            ],
            "recommended_functions": [
                {"name": "Трекинг", "priority": "high", "reason": "Для отслеживания"}
            ],
            "typical_integrations": [
                {"name": "GPS", "examples": ["Wialon", "Gurtam"]}
            ],
            "industry_faq": [
                {"question": "Где мой груз?", "answer_template": "Проверяю..."}
            ],
            "typical_objections": [
                {"objection": "Дорого", "response": "Качество стоит денег"}
            ],
            "learnings": [],
            "success_benchmarks": {
                "avg_call_duration_seconds": 200,
                "typical_kpis": ["Доставка > 95%"]
            }
        }
        with open(industries_dir / "logistics.yaml", "w", encoding="utf-8") as f:
            yaml.dump(profile_data, f, allow_unicode=True)

        return industries_dir

    def test_loader_initialization(self, mock_config_dir):
        """Test loader initialization."""
        loader = IndustryProfileLoader(mock_config_dir)
        assert loader.config_dir == mock_config_dir
        assert loader._cache == {}
        assert loader._index is None

    def test_load_yaml_file_exists(self, mock_config_dir):
        """Test loading existing YAML file."""
        loader = IndustryProfileLoader(mock_config_dir)
        data = loader._load_yaml(mock_config_dir / "_index.yaml")

        assert "industries" in data
        assert "logistics" in data["industries"]

    def test_load_yaml_file_not_found(self, mock_config_dir):
        """Test loading non-existent YAML file."""
        loader = IndustryProfileLoader(mock_config_dir)
        data = loader._load_yaml(mock_config_dir / "nonexistent.yaml")

        assert data == {}

    def test_load_index(self, mock_config_dir):
        """Test loading industry index."""
        loader = IndustryProfileLoader(mock_config_dir)
        index = loader.load_index()

        assert isinstance(index, IndustryIndex)
        assert "logistics" in index.industries

    def test_load_index_caching(self, mock_config_dir):
        """Test index is cached after first load."""
        loader = IndustryProfileLoader(mock_config_dir)

        index1 = loader.load_index()
        index2 = loader.load_index()

        assert index1 is index2  # Same object (cached)

    def test_load_profile(self, mock_config_dir):
        """Test loading industry profile."""
        loader = IndustryProfileLoader(mock_config_dir)
        profile = loader.load_profile("logistics")

        assert isinstance(profile, IndustryProfile)
        assert profile.id == "logistics"
        assert len(profile.pain_points) == 2
        assert len(profile.recommended_functions) == 1

    def test_load_profile_not_found(self, mock_config_dir):
        """Test loading non-existent profile."""
        loader = IndustryProfileLoader(mock_config_dir)
        profile = loader.load_profile("nonexistent")

        assert profile is None

    def test_load_profile_caching(self, mock_config_dir):
        """Test profile is cached after first load."""
        loader = IndustryProfileLoader(mock_config_dir)

        profile1 = loader.load_profile("logistics")
        profile2 = loader.load_profile("logistics")

        assert profile1 is profile2  # Same object (cached)

    def test_get_all_industry_ids(self, mock_config_dir):
        """Test getting all industry IDs."""
        loader = IndustryProfileLoader(mock_config_dir)
        ids = loader.get_all_industry_ids()

        assert "logistics" in ids

    def test_reload_clears_cache(self, mock_config_dir):
        """Test reload clears cache."""
        loader = IndustryProfileLoader(mock_config_dir)

        # Load to populate cache
        loader.load_profile("logistics")
        loader.load_index()

        assert len(loader._cache) == 1
        assert loader._index is not None

        loader.reload()

        assert loader._cache == {}
        assert loader._index is None

    def test_save_yaml(self, mock_config_dir):
        """Test saving YAML file."""
        loader = IndustryProfileLoader(mock_config_dir)

        test_data = {"test": "data", "number": 123}
        test_path = mock_config_dir / "test_output.yaml"

        loader._save_yaml(test_path, test_data)

        assert test_path.exists()
        with open(test_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        assert loaded["test"] == "data"

    def test_save_profile(self, mock_config_dir):
        """Test saving a profile."""
        loader = IndustryProfileLoader(mock_config_dir)

        # Load and modify
        profile = loader.load_profile("logistics")
        profile.learnings.append(Learning(date="2024-02-01", insight="Test insight"))

        loader.save_profile(profile)

        # Reload and verify
        loader.reload()
        reloaded = loader.load_profile("logistics")

        assert len(reloaded.learnings) == 1
        assert reloaded.learnings[0].insight == "Test insight"


# ============ MATCHER TESTS ============

class TestIndustryMatcher:
    """Test IndustryMatcher class."""

    @pytest.fixture
    def mock_loader(self):
        """Create a mock loader with test data."""
        loader = MagicMock(spec=IndustryProfileLoader)

        # Mock index
        index = IndustryIndex(
            industries={
                "logistics": IndustryIndexEntry(
                    file="logistics.yaml",
                    name="Logistics",
                    description="Logistics companies",
                    aliases=["доставка", "грузоперевозки"]
                ),
                "medical": IndustryIndexEntry(
                    file="medical.yaml",
                    name="Medical",
                    description="Healthcare",
                    aliases=["клиника", "больница", "медцентр"]
                )
            }
        )
        loader.load_index.return_value = index

        # Mock profiles
        logistics_profile = MagicMock()
        logistics_profile.aliases = ["доставка", "грузоперевозки", "транспорт", "курьер"]

        medical_profile = MagicMock()
        medical_profile.aliases = ["клиника", "больница", "медцентр", "врач", "здоровье"]

        def load_profile_side_effect(industry_id):
            if industry_id == "logistics":
                return logistics_profile
            elif industry_id == "medical":
                return medical_profile
            return None

        loader.load_profile.side_effect = load_profile_side_effect

        return loader

    def test_matcher_initialization(self, mock_loader):
        """Test matcher initialization."""
        matcher = IndustryMatcher(mock_loader)

        assert matcher.loader is mock_loader
        assert matcher._alias_map == {}
        assert matcher._loaded is False

    def test_build_alias_map(self, mock_loader):
        """Test building alias map."""
        matcher = IndustryMatcher(mock_loader)
        matcher._build_alias_map()

        assert matcher._loaded is True
        assert len(matcher._alias_map) > 0
        assert "доставка" in matcher._alias_map
        assert matcher._alias_map["доставка"] == "logistics"

    def test_detect_logistics(self, mock_loader):
        """Test detecting logistics industry."""
        matcher = IndustryMatcher(mock_loader)

        result = matcher.detect("Мы занимаемся доставкой грузов по всей России")

        assert result == "logistics"

    def test_detect_medical(self, mock_loader):
        """Test detecting medical industry."""
        matcher = IndustryMatcher(mock_loader)

        result = matcher.detect("Наша клиника предоставляет медицинские услуги")

        assert result == "medical"

    def test_detect_no_match(self, mock_loader):
        """Test when no industry is detected."""
        matcher = IndustryMatcher(mock_loader)

        result = matcher.detect("Мы продаём обувь и одежду")

        assert result is None

    def test_detect_with_confidence(self, mock_loader):
        """Test detection with confidence score."""
        matcher = IndustryMatcher(mock_loader)

        industry, confidence = matcher.detect_with_confidence(
            "Наша курьерская служба доставки работает круглосуточно"
        )

        assert industry == "logistics"
        assert 0.0 <= confidence <= 1.0

    def test_detect_with_confidence_no_match(self, mock_loader):
        """Test confidence detection with no match."""
        matcher = IndustryMatcher(mock_loader)

        industry, confidence = matcher.detect_with_confidence("Просто какой-то текст")

        assert industry is None
        assert confidence == 0.0

    def test_get_all_aliases(self, mock_loader):
        """Test getting all aliases for an industry."""
        matcher = IndustryMatcher(mock_loader)

        aliases = matcher.get_all_aliases("logistics")

        assert len(aliases) > 0
        assert "доставка" in aliases

    def test_find_mentions(self, mock_loader):
        """Test finding mentions of an industry in text."""
        matcher = IndustryMatcher(mock_loader)

        mentions = matcher.find_mentions(
            "Мы курьеры, занимаемся доставкой",
            "logistics"
        )

        assert len(mentions) > 0

    def test_reload(self, mock_loader):
        """Test reloading matcher data."""
        matcher = IndustryMatcher(mock_loader)
        matcher._build_alias_map()

        assert matcher._loaded is True

        matcher.reload()

        assert matcher._loaded is False
        assert matcher._alias_map == {}

    def test_russian_stem_extraction(self, mock_loader):
        """Test Russian word stemming."""
        matcher = IndustryMatcher(mock_loader)

        # Test various Russian word forms
        assert matcher._get_russian_stem("грузоперевозками") != "грузоперевозками"
        assert matcher._get_russian_stem("short") == "short"  # Short word unchanged

    def test_word_pattern_russian(self, mock_loader):
        """Test word pattern for Russian words."""
        matcher = IndustryMatcher(mock_loader)

        pattern = matcher._make_word_pattern("доставка")

        # Should create a pattern that matches word boundaries
        assert pattern is not None
        assert len(pattern) > 0


# ============ MANAGER TESTS ============

class TestIndustryKnowledgeManager:
    """Test IndustryKnowledgeManager class."""

    @pytest.fixture
    def mock_manager(self, tmp_path):
        """Create manager with mock config directory."""
        industries_dir = tmp_path / "industries"
        industries_dir.mkdir()

        # Create minimal index
        index_data = {
            "meta": {"version": "1.0"},
            "industries": {
                "logistics": {
                    "file": "logistics.yaml",
                    "name": "Logistics",
                    "description": "Logistics",
                    "aliases": ["доставка"]
                }
            }
        }
        with open(industries_dir / "_index.yaml", "w", encoding="utf-8") as f:
            yaml.dump(index_data, f, allow_unicode=True)

        # Create profile
        profile_data = {
            "meta": {"id": "logistics", "version": "1.0"},
            "aliases": ["доставка"],
            "typical_services": ["Доставка"],
            "pain_points": [{"description": "Delays", "severity": "high", "solution_hint": "Tracking"}],
            "recommended_functions": [{"name": "Tracking", "priority": "high", "reason": "Essential"}],
            "typical_integrations": [{"name": "GPS", "examples": ["Wialon"], "priority": "high", "reason": "For tracking"}],
            "industry_faq": [{"question": "Where is my order?", "answer_template": "Let me check..."}],
            "typical_objections": [],
            "learnings": [],
            "success_benchmarks": {"typical_kpis": ["Delivery > 95%"]}
        }
        with open(industries_dir / "logistics.yaml", "w", encoding="utf-8") as f:
            yaml.dump(profile_data, f, allow_unicode=True)

        return IndustryKnowledgeManager(industries_dir)

    def test_manager_initialization(self, mock_manager):
        """Test manager initialization."""
        assert mock_manager.loader is not None
        assert mock_manager.matcher is not None

    def test_get_profile(self, mock_manager):
        """Test getting a profile."""
        profile = mock_manager.get_profile("logistics")

        assert profile is not None
        assert profile.id == "logistics"

    def test_get_profile_not_found(self, mock_manager):
        """Test getting non-existent profile."""
        profile = mock_manager.get_profile("nonexistent")

        assert profile is None

    def test_detect_industry(self, mock_manager):
        """Test industry detection."""
        result = mock_manager.detect_industry("Мы занимаемся доставкой")

        assert result == "logistics"

    def test_detect_industry_with_confidence(self, mock_manager):
        """Test industry detection with confidence."""
        industry, confidence = mock_manager.detect_industry_with_confidence(
            "Наша компания занимается доставкой"
        )

        assert industry == "logistics"
        assert confidence >= 0.0

    def test_get_context_for_interview(self, mock_manager):
        """Test getting interview context."""
        context = mock_manager.get_context_for_interview("logistics")

        assert context is not None
        assert "industry_id" in context
        assert context["industry_id"] == "logistics"

    def test_get_context_for_interview_not_found(self, mock_manager):
        """Test getting context for non-existent industry."""
        context = mock_manager.get_context_for_interview("nonexistent")

        assert context is None

    def test_get_recommended_functions(self, mock_manager):
        """Test getting recommended functions."""
        functions = mock_manager.get_recommended_functions("logistics")

        assert len(functions) >= 1
        assert functions[0]["name"] == "Tracking"
        assert "priority" in functions[0]

    def test_get_recommended_functions_not_found(self, mock_manager):
        """Test getting functions for non-existent industry."""
        functions = mock_manager.get_recommended_functions("nonexistent")

        assert functions == []

    def test_get_typical_integrations(self, mock_manager):
        """Test getting typical integrations."""
        integrations = mock_manager.get_typical_integrations("logistics")

        assert len(integrations) >= 1
        assert integrations[0]["name"] == "GPS"
        assert "examples" in integrations[0]

    def test_get_pain_points(self, mock_manager):
        """Test getting pain points."""
        pain_points = mock_manager.get_pain_points("logistics")

        assert len(pain_points) >= 1
        assert "description" in pain_points[0]
        assert "severity" in pain_points[0]

    def test_get_industry_faq(self, mock_manager):
        """Test getting industry FAQ."""
        faq = mock_manager.get_industry_faq("logistics")

        assert len(faq) >= 1
        assert "question" in faq[0]
        assert "answer_template" in faq[0]

    def test_get_all_industries(self, mock_manager):
        """Test getting all industry IDs."""
        industries = mock_manager.get_all_industries()

        assert "logistics" in industries

    def test_get_industry_summary(self, mock_manager):
        """Test getting industry summary."""
        summary = mock_manager.get_industry_summary("logistics")

        assert summary is not None
        assert summary["id"] == "logistics"
        assert "tests_run" in summary
        assert "pain_points_count" in summary

    def test_get_industry_summary_not_found(self, mock_manager):
        """Test getting summary for non-existent industry."""
        summary = mock_manager.get_industry_summary("nonexistent")

        assert summary is None

    def test_record_learning(self, mock_manager):
        """Test recording a learning."""
        mock_manager.record_learning(
            "logistics",
            "Customers prefer SMS updates",
            "test_001"
        )

        # Verify learning was added
        profile = mock_manager.get_profile("logistics")
        assert len(profile.learnings) >= 1

    def test_record_learning_not_found(self, mock_manager):
        """Test recording learning for non-existent industry."""
        # Should not raise error
        mock_manager.record_learning(
            "nonexistent",
            "Some insight",
            "test_001"
        )

    def test_update_metrics(self, mock_manager):
        """Test updating metrics."""
        initial_profile = mock_manager.get_profile("logistics")
        initial_tests = initial_profile.meta.tests_run

        mock_manager.update_metrics("logistics", 0.9)

        mock_manager.reload()
        updated_profile = mock_manager.get_profile("logistics")

        assert updated_profile.meta.tests_run == initial_tests + 1

    def test_update_metrics_not_found(self, mock_manager):
        """Test updating metrics for non-existent industry."""
        # Should not raise error
        mock_manager.update_metrics("nonexistent", 0.9)

    def test_reload(self, mock_manager):
        """Test reloading manager."""
        # Load some data first
        mock_manager.get_profile("logistics")

        # Reload should not raise error
        mock_manager.reload()


class TestGetKnowledgeManager:
    """Test global manager accessor."""

    def test_get_knowledge_manager_singleton(self):
        """Test that get_knowledge_manager returns singleton."""
        # Reset global state
        import src.knowledge.manager as manager_module
        manager_module._manager = None

        with patch.object(IndustryKnowledgeManager, '__init__', return_value=None):
            manager1 = get_knowledge_manager()
            manager2 = get_knowledge_manager()

            # Should return same instance
            assert manager1 is manager2


# ============ CONTEXT BUILDER TESTS ============

class TestKBContextBuilder:
    """Test KBContextBuilder class."""

    @pytest.fixture
    def sample_profile(self):
        """Create a sample profile for testing."""
        return IndustryProfile(
            meta=IndustryMeta(id="logistics", version="1.0"),
            typical_services=["Delivery", "Warehousing"],
            pain_points=[
                PainPoint(description="Delays", severity="high"),
                PainPoint(description="Lost packages", severity="medium")
            ],
            recommended_functions=[
                RecommendedFunction(name="Tracking", priority="high", reason="Essential"),
                RecommendedFunction(name="Notifications", priority="medium", reason="Nice to have")
            ],
            typical_integrations=[
                TypicalIntegration(name="GPS", examples=["Wialon", "Gurtam"])
            ],
            industry_faq=[
                IndustryFAQ(question="Where is my order?", answer_template="Let me check...")
            ],
            typical_objections=[
                TypicalObjection(objection="Too expensive", response="Quality has value")
            ],
            success_benchmarks=SuccessBenchmarks(
                typical_kpis=["Delivery rate > 95%", "Response time < 30s"]
            )
        )

    @pytest.fixture
    def builder_with_config(self, tmp_path):
        """Create builder with mock config."""
        config_path = tmp_path / "kb_context.yaml"
        config_data = {
            "sections": {
                "discovery": {
                    "enabled": True,
                    "header": "Industry Knowledge",
                    "blocks": [
                        {"key": "pain_points", "label": "Pain Points", "format": "severity_list"},
                        {"key": "typical_services", "label": "Services", "format": "bullet_list"}
                    ]
                },
                "analysis": {
                    "enabled": True,
                    "header": "Analysis Context",
                    "blocks": [
                        {"key": "recommended_functions", "label": "Functions", "format": "priority_list"}
                    ]
                },
                "disabled_phase": {
                    "enabled": False,
                    "header": "Disabled",
                    "blocks": []
                }
            },
            "formats": {
                "severity_list": {
                    "severity_labels": {"high": "!!!", "medium": "!!", "low": "!"}
                },
                "priority_list": {
                    "priority_labels": {"high": "ВАЖНО", "medium": "ЖЕЛАТЕЛЬНО", "low": "ОПЦИОНАЛЬНО"}
                }
            }
        }

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True)

        # Reset singleton state
        KBContextBuilder._loaded = False
        KBContextBuilder._config = {}

        return KBContextBuilder(config_path)

    def test_builder_initialization(self, builder_with_config):
        """Test builder initialization."""
        assert KBContextBuilder._loaded is True
        assert "sections" in KBContextBuilder._config

    def test_build_context_discovery(self, builder_with_config, sample_profile):
        """Test building context for discovery phase."""
        context = builder_with_config.build_context(sample_profile, "discovery")

        assert "Industry Knowledge" in context
        assert "logistics" in context
        assert "Pain Points" in context

    def test_build_context_disabled_phase(self, builder_with_config, sample_profile):
        """Test building context for disabled phase."""
        context = builder_with_config.build_context(sample_profile, "disabled_phase")

        assert context == ""

    def test_build_context_unknown_phase(self, builder_with_config, sample_profile):
        """Test building context for unknown phase."""
        context = builder_with_config.build_context(sample_profile, "unknown")

        assert context == ""

    def test_format_bullet_list(self, builder_with_config):
        """Test bullet list formatting."""
        data = ["Item 1", "Item 2", "Item 3"]
        result = builder_with_config._format_bullet_list(data, {})

        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_format_severity_list(self, builder_with_config):
        """Test severity list formatting."""
        data = [
            PainPoint(description="High issue", severity="high"),
            PainPoint(description="Medium issue", severity="medium")
        ]
        result = builder_with_config._format_severity_list(data, {"severity_labels": {"high": "!!!", "medium": "!!"}})

        assert "[!!!]" in result
        assert "[!!]" in result

    def test_format_priority_list(self, builder_with_config):
        """Test priority list formatting."""
        data = [
            RecommendedFunction(name="Feature", priority="high", reason="Important")
        ]
        labels = {"high": "ВАЖНО", "medium": "ЖЕЛАТЕЛЬНО"}
        result = builder_with_config._format_priority_list(data, {"priority_labels": labels})

        assert "[ВАЖНО]" in result
        assert "Feature" in result

    def test_format_integration_list(self, builder_with_config):
        """Test integration list formatting."""
        data = [
            TypicalIntegration(name="CRM", examples=["Salesforce", "HubSpot"])
        ]
        result = builder_with_config._format_integration_list(data, {})

        assert "CRM" in result
        assert "Salesforce" in result

    def test_format_qa_list(self, builder_with_config):
        """Test QA list formatting."""
        data = [
            IndustryFAQ(question="What is your price?", answer_template="Our prices start at...")
        ]
        result = builder_with_config._format_qa_list(data, {})

        assert "В:" in result
        assert "О:" in result

    def test_format_objection_list(self, builder_with_config):
        """Test objection list formatting."""
        data = [
            TypicalObjection(objection="Too expensive", response="Value proposition")
        ]
        result = builder_with_config._format_objection_list(data, {})

        assert "Возражение:" in result
        assert "Ответ:" in result

    def test_format_kpi_list(self, builder_with_config):
        """Test KPI list formatting."""
        data = SuccessBenchmarks(typical_kpis=["KPI 1", "KPI 2"])
        result = builder_with_config._format_kpi_list(data, {})

        assert "- KPI 1" in result
        assert "- KPI 2" in result

    def test_get_profile_data(self, builder_with_config, sample_profile):
        """Test getting profile data by key."""
        data = builder_with_config._get_profile_data(sample_profile, "pain_points")
        assert len(data) == 2

        data = builder_with_config._get_profile_data(sample_profile, "nonexistent")
        assert data is None


class TestGetKBContextBuilder:
    """Test singleton accessor for KB context builder."""

    def test_get_kb_context_builder(self, tmp_path):
        """Test getting KB context builder."""
        # Reset singleton
        import src.knowledge.context_builder as cb_module
        cb_module._builder = None
        KBContextBuilder._loaded = False
        KBContextBuilder._config = {}

        # Create minimal config
        config_path = tmp_path / "kb_context.yaml"
        with open(config_path, "w") as f:
            yaml.dump({"sections": {}, "formats": {}}, f)

        builder1 = get_kb_context_builder(config_path)
        builder2 = get_kb_context_builder()

        assert builder1 is builder2


# ============ INTEGRATION TESTS ============

class TestKnowledgeModuleIntegration:
    """Integration tests for knowledge module."""

    @pytest.fixture
    def full_setup(self, tmp_path):
        """Create full setup with all components."""
        industries_dir = tmp_path / "industries"
        industries_dir.mkdir()

        # Create comprehensive index
        index_data = {
            "meta": {"version": "1.0"},
            "industries": {
                "logistics": {
                    "file": "logistics.yaml",
                    "name": "Логистика",
                    "description": "Логистические компании",
                    "aliases": ["доставка", "грузоперевозки", "транспорт"]
                },
                "medical": {
                    "file": "medical.yaml",
                    "name": "Медицина",
                    "description": "Медицинские учреждения",
                    "aliases": ["клиника", "больница", "медцентр"]
                }
            }
        }
        with open(industries_dir / "_index.yaml", "w", encoding="utf-8") as f:
            yaml.dump(index_data, f, allow_unicode=True)

        # Create logistics profile
        logistics_data = {
            "meta": {"id": "logistics", "version": "1.0"},
            "aliases": ["доставка", "грузоперевозки"],
            "typical_services": ["Доставка грузов"],
            "pain_points": [{"description": "Задержки", "severity": "high"}],
            "recommended_functions": [{"name": "Трекинг", "priority": "high"}],
            "typical_integrations": [{"name": "GPS", "examples": ["Wialon"]}],
            "industry_faq": [],
            "typical_objections": [],
            "learnings": [],
            "success_benchmarks": {}
        }
        with open(industries_dir / "logistics.yaml", "w", encoding="utf-8") as f:
            yaml.dump(logistics_data, f, allow_unicode=True)

        # Create medical profile
        medical_data = {
            "meta": {"id": "medical", "version": "1.0"},
            "aliases": ["клиника", "больница"],
            "typical_services": ["Приём пациентов"],
            "pain_points": [{"description": "Очереди", "severity": "high"}],
            "recommended_functions": [{"name": "Запись", "priority": "high"}],
            "typical_integrations": [{"name": "МИС", "examples": ["Инфоклиника"]}],
            "industry_faq": [],
            "typical_objections": [],
            "learnings": [],
            "success_benchmarks": {}
        }
        with open(industries_dir / "medical.yaml", "w", encoding="utf-8") as f:
            yaml.dump(medical_data, f, allow_unicode=True)

        return IndustryKnowledgeManager(industries_dir)

    def test_full_workflow(self, full_setup):
        """Test complete workflow."""
        manager = full_setup

        # 1. Detect industry from dialogue
        dialogue = "Здравствуйте! Мы логистическая компания, занимаемся доставкой грузов."
        industry = manager.detect_industry(dialogue)
        assert industry == "logistics"

        # 2. Get profile
        profile = manager.get_profile(industry)
        assert profile is not None
        assert profile.id == "logistics"

        # 3. Get context for interview
        context = manager.get_context_for_interview(industry)
        assert "industry_id" in context

        # 4. Get recommendations
        functions = manager.get_recommended_functions(industry)
        assert len(functions) >= 1

        # 5. Record learning
        manager.record_learning(industry, "Test insight", "integration_test")

        # 6. Update metrics
        manager.update_metrics(industry, 0.85)

    def test_multi_industry_detection(self, full_setup):
        """Test detecting multiple industries."""
        manager = full_setup

        # Test logistics
        result1 = manager.detect_industry("Мы занимаемся доставкой и грузоперевозками")
        assert result1 == "logistics"

        # Test medical
        result2 = manager.detect_industry("Наша клиника принимает пациентов")
        assert result2 == "medical"

        # Test ambiguous
        result3 = manager.detect_industry("Просто какая-то компания")
        assert result3 is None
