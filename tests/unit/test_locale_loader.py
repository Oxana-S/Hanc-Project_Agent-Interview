"""
Tests for src/config/locale_loader.py

Comprehensive tests for LocaleLoader class and global helper functions.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import yaml

from src.config.locale_loader import (
    LocaleLoader,
    get_locale_loader,
    t,
    set_locale,
    _default_loader,
)
import src.config.locale_loader as locale_loader_module


# ---------------------------------------------------------------------------
# Helper: create a locale directory tree with YAML files inside tmp_path
# ---------------------------------------------------------------------------

def _create_locale_files(tmp_path, locale, file_name, data):
    """Create a YAML locale file under tmp_path/<locale>/<file_name>.yaml."""
    locale_dir = tmp_path / locale
    locale_dir.mkdir(parents=True, exist_ok=True)
    file_path = locale_dir / f"{file_name}.yaml"
    file_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return file_path


# ===========================================================================
# 1. TestLocaleLoaderInit
# ===========================================================================

class TestLocaleLoaderInit:
    """Tests for LocaleLoader.__init__."""

    def test_init_default_base_path(self):
        """Default base_path points to <project_root>/locales."""
        loader = LocaleLoader()
        assert loader.base_path.name == "locales"
        assert loader.default_locale == "ru"
        assert loader._cache == {}

    def test_init_custom_base_path(self, tmp_path):
        """Custom base_path is stored correctly."""
        loader = LocaleLoader(base_path=tmp_path)
        assert loader.base_path == tmp_path

    def test_init_custom_default_locale(self, tmp_path):
        """Custom default_locale is stored correctly."""
        loader = LocaleLoader(base_path=tmp_path, default_locale="en")
        assert loader.default_locale == "en"


# ===========================================================================
# 2. TestLocaleLoaderGet
# ===========================================================================

class TestLocaleLoaderGet:
    """Tests for LocaleLoader.get() method."""

    @pytest.fixture
    def loader(self, tmp_path):
        """Loader with ru and en locale files."""
        ru_data = {
            "title": "Добро пожаловать",
            "phases": {
                "discovery": {
                    "title": "Знакомство с бизнесом"
                }
            },
            "errors": {
                "api_error": "Ошибка API: {{message}}"
            },
            "count": 42,
            "fallback_only": "Только в русском"
        }
        en_data = {
            "title": "Welcome",
            "phases": {
                "discovery": {
                    "title": "Business discovery"
                }
            },
            "errors": {
                "api_error": "API error: {{message}}"
            },
        }
        _create_locale_files(tmp_path, "ru", "ui", ru_data)
        _create_locale_files(tmp_path, "en", "ui", en_data)
        return LocaleLoader(base_path=tmp_path, default_locale="ru")

    def test_get_simple_key(self, loader):
        """Get a top-level string key."""
        assert loader.get("title") == "Добро пожаловать"

    def test_get_nested_key(self, loader):
        """Get a nested key via dot notation."""
        assert loader.get("phases.discovery.title") == "Знакомство с бизнесом"

    def test_get_with_variables(self, loader):
        """Variable substitution with {{var}} syntax."""
        result = loader.get("errors.api_error", message="timeout")
        assert result == "Ошибка API: timeout"

    def test_get_non_string_returns_str(self, loader):
        """Non-string result is converted via str()."""
        result = loader.get("count")
        assert result == "42"
        assert isinstance(result, str)

    def test_get_missing_key_raises_keyerror(self, loader):
        """Missing key in default locale raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            loader.get("nonexistent.key")
        assert "nonexistent.key" in str(exc_info.value)

    def test_get_fallback_to_default_locale(self, loader):
        """Key missing in 'en' falls back to default locale 'ru'."""
        result = loader.get("fallback_only", locale="en")
        assert result == "Только в русском"


# ===========================================================================
# 3. TestLocaleLoaderGetDict
# ===========================================================================

class TestLocaleLoaderGetDict:
    """Tests for LocaleLoader.get_dict() method."""

    @pytest.fixture
    def loader(self, tmp_path):
        data = {
            "phases": {
                "discovery": {
                    "title": "Знакомство",
                    "description": "Описание"
                }
            },
            "simple_key": "simple_value"
        }
        _create_locale_files(tmp_path, "ru", "ui", data)
        return LocaleLoader(base_path=tmp_path, default_locale="ru")

    def test_get_dict_returns_dict(self, loader):
        """get_dict returns a dict when key points to a dict."""
        result = loader.get_dict("phases.discovery")
        assert isinstance(result, dict)
        assert result["title"] == "Знакомство"
        assert result["description"] == "Описание"

    def test_get_dict_non_dict_wraps_in_dict(self, loader):
        """get_dict wraps non-dict result in {key: value}."""
        result = loader.get_dict("simple_key")
        assert isinstance(result, dict)
        assert result == {"simple_key": "simple_value"}

    def test_get_dict_missing_key_raises(self, loader):
        """get_dict raises KeyError for missing key."""
        with pytest.raises(KeyError):
            loader.get_dict("nonexistent")


# ===========================================================================
# 4. TestLocaleLoaderLoadFile
# ===========================================================================

class TestLocaleLoaderLoadFile:
    """Tests for LocaleLoader._load_file() method."""

    def test_load_file_reads_yaml(self, tmp_path):
        """_load_file reads and parses a real YAML file."""
        data = {"greeting": "Привет", "nested": {"key": "value"}}
        _create_locale_files(tmp_path, "ru", "ui", data)
        loader = LocaleLoader(base_path=tmp_path)

        result = loader._load_file("ru", "ui")
        assert result["greeting"] == "Привет"
        assert result["nested"]["key"] == "value"

    def test_load_file_caching(self, tmp_path):
        """Second call to _load_file returns the cached data (no re-read)."""
        data = {"value": "original"}
        file_path = _create_locale_files(tmp_path, "ru", "ui", data)
        loader = LocaleLoader(base_path=tmp_path)

        first = loader._load_file("ru", "ui")
        assert first["value"] == "original"

        # Overwrite the file on disk
        file_path.write_text(yaml.dump({"value": "modified"}), encoding="utf-8")

        second = loader._load_file("ru", "ui")
        # Should still return cached (original) data
        assert second["value"] == "original"

    def test_load_file_not_found_raises(self, tmp_path):
        """_load_file raises FileNotFoundError for missing file."""
        loader = LocaleLoader(base_path=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader._load_file("ru", "nonexistent")


# ===========================================================================
# 5. TestLocaleLoaderMisc
# ===========================================================================

class TestLocaleLoaderMisc:
    """Tests for set_locale, get_available_locales, clear_cache."""

    def test_set_locale_changes_default(self, tmp_path):
        """set_locale changes the default_locale attribute."""
        loader = LocaleLoader(base_path=tmp_path, default_locale="ru")
        loader.set_locale("en")
        assert loader.default_locale == "en"

    def test_get_available_locales(self, tmp_path):
        """get_available_locales lists locale directories."""
        (tmp_path / "ru").mkdir()
        (tmp_path / "en").mkdir()
        (tmp_path / "de").mkdir()
        # Also create a regular file that should NOT appear
        (tmp_path / "README.md").write_text("ignore me")

        loader = LocaleLoader(base_path=tmp_path)
        locales = loader.get_available_locales()
        assert sorted(locales) == ["de", "en", "ru"]

    def test_clear_cache_empties_cache(self, tmp_path):
        """clear_cache removes all cached entries."""
        data = {"key": "value"}
        _create_locale_files(tmp_path, "ru", "ui", data)
        loader = LocaleLoader(base_path=tmp_path)

        # Populate cache
        loader._load_file("ru", "ui")
        assert len(loader._cache) == 1

        loader.clear_cache()
        assert loader._cache == {}


# ===========================================================================
# 6. TestGlobalFunctions
# ===========================================================================

class TestGlobalFunctions:
    """Tests for module-level get_locale_loader, t, set_locale."""

    def setup_method(self):
        """Reset global singleton before each test."""
        locale_loader_module._default_loader = None

    def teardown_method(self):
        """Clean up global singleton after each test."""
        locale_loader_module._default_loader = None

    def test_get_locale_loader_singleton(self):
        """get_locale_loader returns the same instance on repeated calls."""
        loader1 = get_locale_loader()
        loader2 = get_locale_loader()
        assert loader1 is loader2
        assert isinstance(loader1, LocaleLoader)

    def test_t_shortcut(self):
        """t() delegates to get_locale_loader().get()."""
        mock_loader = MagicMock()
        mock_loader.get.return_value = "Привет"

        with patch.object(locale_loader_module, "_default_loader", mock_loader):
            # Patch so get_locale_loader returns our mock
            with patch(
                "src.config.locale_loader.get_locale_loader",
                return_value=mock_loader,
            ):
                result = t("greeting", name="World")

        mock_loader.get.assert_called_once_with("greeting", name="World")
        assert result == "Привет"

    def test_set_locale_global(self):
        """set_locale() delegates to get_locale_loader().set_locale()."""
        mock_loader = MagicMock()

        with patch(
            "src.config.locale_loader.get_locale_loader",
            return_value=mock_loader,
        ):
            set_locale("en")

        mock_loader.set_locale.assert_called_once_with("en")
