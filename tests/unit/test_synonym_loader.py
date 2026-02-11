"""
Tests for src/config/synonym_loader.py

Comprehensive tests for deep_merge function, SynonymLoader class,
and global helper functions.
"""

import pytest
from pathlib import Path
import yaml

from src.config.synonym_loader import (
    deep_merge,
    SynonymLoader,
    get_synonym_loader,
    get_industry_synonyms,
    get_function_synonyms,
    get_integration_synonyms,
    reload_all_loaders,
    _loaders,
)
import src.config.synonym_loader as synonym_loader_module


# ============================================================================
# Helper: write YAML file
# ============================================================================

def _write_yaml(path: Path, data: dict):
    """Write a dictionary to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


# ============================================================================
# 1. TestDeepMerge (7 tests)
# ============================================================================

class TestDeepMerge:
    """Tests for the standalone deep_merge function."""

    def test_merge_disjoint_dicts(self):
        """Merging two dicts with no overlapping keys combines them."""
        base = {"a": 1, "b": 2}
        override = {"c": 3, "d": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2, "c": 3, "d": 4}

    def test_merge_nested_dicts(self):
        """Nested dictionaries are merged recursively."""
        base = {"outer": {"a": 1, "b": 2}}
        override = {"outer": {"b": 99, "c": 3}}
        result = deep_merge(base, override)
        assert result == {"outer": {"a": 1, "b": 99, "c": 3}}

    def test_merge_lists_concatenate_and_dedup(self):
        """Lists are concatenated with duplicates removed, preserving order."""
        base = {"items": ["apple", "banana"]}
        override = {"items": ["banana", "cherry"]}
        result = deep_merge(base, override)
        assert result["items"] == ["apple", "banana", "cherry"]

    def test_merge_lists_case_insensitive_dedup(self):
        """List deduplication is case-insensitive for strings."""
        base = {"items": ["CRM", "sms"]}
        override = {"items": ["crm", "SMS", "email"]}
        result = deep_merge(base, override)
        # "CRM" is kept (first occurrence), "crm" and "SMS" are deduped
        assert result["items"] == ["CRM", "sms", "email"]

    def test_merge_scalar_override(self):
        """For scalar values with the same key, override wins."""
        base = {"version": "1.0", "name": "base"}
        override = {"version": "2.0"}
        result = deep_merge(base, override)
        assert result["version"] == "2.0"
        assert result["name"] == "base"

    def test_merge_empty_base(self):
        """Merging with an empty base returns the override."""
        base = {}
        override = {"a": 1, "b": [1, 2]}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": [1, 2]}

    def test_merge_empty_override(self):
        """Merging with an empty override returns the base unchanged."""
        base = {"a": 1, "nested": {"x": 10}}
        override = {}
        result = deep_merge(base, override)
        assert result == {"a": 1, "nested": {"x": 10}}


# ============================================================================
# 2. TestSynonymLoaderInit (4 tests)
# ============================================================================

class TestSynonymLoaderInit:
    """Tests for SynonymLoader initialization."""

    def test_init_default_config_dir(self):
        """Default config_dir resolves to project_root/config/synonyms."""
        loader = SynonymLoader()
        assert loader.config_dir.name == "synonyms"
        assert loader.config_dir.parent.name == "config"

    def test_init_custom_config_dir(self, tmp_path):
        """Custom config_dir is used as-is."""
        custom_dir = tmp_path / "my_synonyms"
        custom_dir.mkdir()
        loader = SynonymLoader(config_dir=custom_dir)
        assert loader.config_dir == custom_dir

    def test_init_supported_language(self):
        """A supported language is accepted."""
        loader = SynonymLoader(language="en")
        assert loader.language == "en"
        assert loader.current_language == "en"

    def test_init_unsupported_language_falls_back(self):
        """An unsupported language falls back to the default."""
        loader = SynonymLoader(language="fr")
        assert loader.language == SynonymLoader.DEFAULT_LANGUAGE


# ============================================================================
# 3. TestSynonymLoaderLoad (6 tests)
# ============================================================================

class TestSynonymLoaderLoad:
    """Tests for the _load method and file resolution logic."""

    def test_load_base_and_lang_files(self, tmp_path):
        """When both base.yaml and lang.yaml exist, they are deep-merged."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        base_data = {
            "meta": {"version": "1.0"},
            "industries": {
                "it": ["it", "software"],
            },
            "functions": {
                "support": ["support"],
            },
        }
        lang_data = {
            "meta": {"version": "1.0-ru"},
            "industries": {
                "it": ["айти", "программирование"],
                "медицина": ["медицина", "healthcare"],
            },
            "functions": {
                "support": ["поддержка"],
            },
        }

        _write_yaml(synonyms_dir / "base.yaml", base_data)
        _write_yaml(synonyms_dir / "ru.yaml", lang_data)

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        data = loader._load()

        # Meta: override wins (scalar)
        assert data["meta"]["version"] == "1.0-ru"
        # Industries: merged
        assert "it" in data["industries"]
        assert "медицина" in data["industries"]
        # Lists merged and deduped
        it_syns = data["industries"]["it"]
        assert "it" in it_syns
        assert "software" in it_syns
        assert "айти" in it_syns
        # Functions merged
        support_syns = data["functions"]["support"]
        assert "support" in support_syns
        assert "поддержка" in support_syns

    def test_load_base_only(self, tmp_path):
        """When only base.yaml exists, it is loaded without merging."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        base_data = {
            "meta": {"version": "base-only"},
            "industries": {"it": ["it", "tech"]},
        }
        _write_yaml(synonyms_dir / "base.yaml", base_data)

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        data = loader._load()

        assert data["meta"]["version"] == "base-only"
        assert data["industries"]["it"] == ["it", "tech"]

    def test_load_lang_only(self, tmp_path):
        """When only the language file exists, it is loaded without merging."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        lang_data = {
            "meta": {"version": "ru-only"},
            "industries": {"медицина": ["медицина"]},
        }
        _write_yaml(synonyms_dir / "ru.yaml", lang_data)

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        data = loader._load()

        assert data["meta"]["version"] == "ru-only"
        assert "медицина" in data["industries"]

    def test_load_legacy_fallback(self, tmp_path):
        """When no base/lang files exist, falls back to ../synonyms.yaml."""
        # config_dir = tmp_path/synonyms (empty directory)
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        # Legacy file lives at tmp_path/synonyms.yaml (parent of config_dir)
        legacy_data = {
            "meta": {"version": "legacy"},
            "industries": {"legacy_industry": ["legacy"]},
        }
        _write_yaml(tmp_path / "synonyms.yaml", legacy_data)

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        data = loader._load()

        assert data["meta"]["version"] == "legacy"
        assert "legacy_industry" in data["industries"]

    def test_load_no_files_returns_defaults(self, tmp_path):
        """When no files exist at all, default synonyms are returned."""
        empty_dir = tmp_path / "synonyms"
        empty_dir.mkdir()

        loader = SynonymLoader(config_dir=empty_dir, language="ru")
        data = loader._load()

        # Defaults include known keys
        assert "industries" in data
        assert "functions" in data
        assert "integrations" in data
        assert data["meta"]["version"] == "default"
        assert data["meta"]["language"] == "ru"

    def test_load_caching(self, tmp_path):
        """Second call returns cached data without re-reading files."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        base_data = {"meta": {"version": "cached"}, "industries": {"a": ["a"]}}
        _write_yaml(synonyms_dir / "base.yaml", base_data)

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")

        # First load
        data1 = loader._load()
        assert data1["meta"]["version"] == "cached"

        # Modify file on disk
        base_data["meta"]["version"] = "modified"
        _write_yaml(synonyms_dir / "base.yaml", base_data)

        # Second load should still return cached version
        data2 = loader._load()
        assert data2["meta"]["version"] == "cached"
        assert data1 is data2  # same object reference


# ============================================================================
# 4. TestSynonymLoaderGetters (6 tests)
# ============================================================================

class TestSynonymLoaderGetters:
    """Tests for the getter methods."""

    @pytest.fixture
    def loader(self, tmp_path):
        """Create a loader with a known YAML file."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        data = {
            "meta": {"version": "test", "language": "ru"},
            "industries": {
                "it": ["it", "software"],
                "медицина": ["медицина", "healthcare"],
            },
            "functions": {
                "запись": ["запись", "booking"],
            },
            "integrations": {
                "crm": ["crm", "битрикс"],
            },
            "canonical_mapping": {
                "healthcare": ["медицина", "healthcare"],
            },
        }
        _write_yaml(synonyms_dir / "base.yaml", data)
        return SynonymLoader(config_dir=synonyms_dir, language="ru")

    def test_get_industries(self, loader):
        """get_industries returns the industries dict from loaded data."""
        industries = loader.get_industries()
        assert "it" in industries
        assert "медицина" in industries
        assert industries["it"] == ["it", "software"]

    def test_get_functions(self, loader):
        """get_functions returns the functions dict from loaded data."""
        functions = loader.get_functions()
        assert "запись" in functions
        assert functions["запись"] == ["запись", "booking"]

    def test_get_integrations(self, loader):
        """get_integrations returns the integrations dict from loaded data."""
        integrations = loader.get_integrations()
        assert "crm" in integrations
        assert "битрикс" in integrations["crm"]

    def test_get_canonical_mapping(self, loader):
        """get_canonical_mapping returns canonical_mapping when present."""
        mapping = loader.get_canonical_mapping()
        assert "healthcare" in mapping

    def test_get_all_returns_three_keys(self, loader):
        """get_all returns a dict with exactly industries, functions, integrations."""
        result = loader.get_all()
        assert set(result.keys()) == {"industries", "functions", "integrations"}
        assert "it" in result["industries"]
        assert "запись" in result["functions"]
        assert "crm" in result["integrations"]

    def test_get_meta(self, loader):
        """get_meta returns the meta section of the data."""
        meta = loader.get_meta()
        assert meta["version"] == "test"
        assert meta["language"] == "ru"


# ============================================================================
# 5. TestSynonymLoaderLanguage (4 tests)
# ============================================================================

class TestSynonymLoaderLanguage:
    """Tests for language switching."""

    def test_set_language_valid(self, tmp_path):
        """set_language with a valid language switches and reloads."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        ru_data = {"meta": {"language": "ru"}, "industries": {"ru_ind": ["ru"]}}
        en_data = {"meta": {"language": "en"}, "industries": {"en_ind": ["en"]}}
        _write_yaml(synonyms_dir / "ru.yaml", ru_data)
        _write_yaml(synonyms_dir / "en.yaml", en_data)

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        assert loader.current_language == "ru"
        assert "ru_ind" in loader.get_industries()

        loader.set_language("en")
        assert loader.current_language == "en"
        assert "en_ind" in loader.get_industries()

    def test_set_language_invalid_falls_back(self, tmp_path):
        """set_language with an unsupported language falls back to default."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()
        _write_yaml(synonyms_dir / "ru.yaml", {"meta": {"language": "ru"}})

        loader = SynonymLoader(config_dir=synonyms_dir, language="en")
        loader.set_language("de")  # unsupported
        assert loader.current_language == SynonymLoader.DEFAULT_LANGUAGE

    def test_set_language_same_no_reload(self, tmp_path):
        """set_language with the same language does not clear cache."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()
        _write_yaml(synonyms_dir / "ru.yaml", {"meta": {"language": "ru"}, "industries": {"a": ["a"]}})

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        loader._load()  # populate cache
        cache_before = loader._cache

        loader.set_language("ru")  # same language
        assert loader._cache is cache_before  # cache not cleared

    def test_current_language_property(self):
        """current_language returns the current language setting."""
        loader = SynonymLoader(language="en")
        assert loader.current_language == "en"

        loader = SynonymLoader(language="ru")
        assert loader.current_language == "ru"


# ============================================================================
# 6. TestSynonymLoaderReload (2 tests)
# ============================================================================

class TestSynonymLoaderReload:
    """Tests for reload and is_loaded."""

    def test_reload_clears_cache(self, tmp_path):
        """reload() clears cache and re-reads from disk."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()

        data = {"meta": {"version": "v1"}, "industries": {"a": ["a"]}}
        _write_yaml(synonyms_dir / "base.yaml", data)

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        loader._load()
        assert loader.get_meta()["version"] == "v1"

        # Modify file on disk
        data["meta"]["version"] = "v2"
        _write_yaml(synonyms_dir / "base.yaml", data)

        # Without reload, cached version is returned
        assert loader.get_meta()["version"] == "v1"

        # After reload, new version is picked up
        loader.reload()
        assert loader.get_meta()["version"] == "v2"

    def test_is_loaded_property(self, tmp_path):
        """is_loaded is False initially, True after loading from files."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()
        _write_yaml(synonyms_dir / "base.yaml", {"meta": {"version": "1"}})

        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        assert loader.is_loaded is False

        loader._load()
        assert loader.is_loaded is True


# ============================================================================
# 7. TestGlobalFunctions (4 tests)
# ============================================================================

class TestGlobalFunctions:
    """Tests for module-level helper functions."""

    @pytest.fixture(autouse=True)
    def reset_global_loaders(self):
        """Reset the global _loaders dict before and after each test."""
        synonym_loader_module._loaders.clear()
        yield
        synonym_loader_module._loaders.clear()

    def test_get_synonym_loader_caching(self):
        """get_synonym_loader returns the same instance for the same language."""
        loader1 = get_synonym_loader("ru")
        loader2 = get_synonym_loader("ru")
        assert loader1 is loader2

        loader_en = get_synonym_loader("en")
        assert loader_en is not loader1
        assert loader_en.current_language == "en"

    def test_get_industry_synonyms_shortcut(self):
        """get_industry_synonyms returns industries from the loader."""
        result = get_industry_synonyms("ru")
        assert isinstance(result, dict)
        # Should have at least the default industries
        assert len(result) > 0

    def test_get_function_synonyms_shortcut(self):
        """get_function_synonyms returns functions from the loader."""
        result = get_function_synonyms("ru")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_reload_all_loaders(self, tmp_path):
        """reload_all_loaders reloads every cached loader."""
        synonyms_dir = tmp_path / "synonyms"
        synonyms_dir.mkdir()
        _write_yaml(synonyms_dir / "base.yaml", {"meta": {"version": "old"}})
        _write_yaml(synonyms_dir / "ru.yaml", {"meta": {"language": "ru"}})

        # Create a loader with known config_dir so we can control files
        loader = SynonymLoader(config_dir=synonyms_dir, language="ru")
        synonym_loader_module._loaders["ru"] = loader

        loader._load()
        assert loader.get_meta().get("version") == "old"

        # Modify on disk
        _write_yaml(synonyms_dir / "base.yaml", {"meta": {"version": "new"}})

        reload_all_loaders()
        assert loader.get_meta().get("version") == "new"
