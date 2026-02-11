"""
Unit tests for CountryDetector - country/region detection from phone, language, or explicit selection.
"""

import pytest
import yaml
import sys
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.knowledge.country_detector import CountryDetector, get_country_detector
import src.knowledge.country_detector as country_detector_module


# ============ INIT TESTS ============

class TestCountryDetectorInit:
    """Test CountryDetector initialization and YAML loading."""

    def test_init_with_countries_file(self, tmp_path):
        """Loading a valid _countries.yaml populates meta and phone_code_map."""
        countries_yaml = tmp_path / "_countries.yaml"
        countries_yaml.write_text(yaml.dump({
            "countries": {
                "de": {"name": "Germany", "currency": "EUR"},
                "ru": {"name": "Russia", "currency": "RUB"},
            },
            "phone_code_map": {"+49": "de", "+7": "ru"},
        }))
        detector = CountryDetector(countries_file=countries_yaml)

        assert detector._countries_meta["de"]["name"] == "Germany"
        assert detector._countries_meta["ru"]["name"] == "Russia"
        assert len(detector._countries_meta) == 2

    def test_init_file_not_found(self, tmp_path):
        """Non-existent countries file results in empty meta dicts (no crash)."""
        fake_path = tmp_path / "nonexistent.yaml"
        detector = CountryDetector(countries_file=fake_path)

        assert detector._countries_meta == {}
        assert detector._phone_code_map == {}

    def test_init_loads_phone_code_map(self, tmp_path):
        """phone_code_map from YAML is loaded and usable for phone detection."""
        countries_yaml = tmp_path / "_countries.yaml"
        countries_yaml.write_text(yaml.dump({
            "countries": {},
            "phone_code_map": {"+49": "de", "+7": "ru", "+1": "us"},
        }))
        detector = CountryDetector(countries_file=countries_yaml)

        assert detector._phone_code_map["+49"] == "de"
        assert detector._phone_code_map["+7"] == "ru"
        assert detector._phone_code_map["+1"] == "us"
        assert len(detector._phone_code_map) == 3


# ============ PHONE DETECTION TESTS ============

class TestDetectFromPhone:
    """Test _detect_from_phone with various phone number formats."""

    @pytest.fixture(autouse=True)
    def setup_detector(self, tmp_path):
        """Create a detector with an empty countries file (uses built-in PHONE_PATTERNS)."""
        countries_yaml = tmp_path / "_countries.yaml"
        countries_yaml.write_text(yaml.dump({"countries": {}, "phone_code_map": {}}))
        self.detector = CountryDetector(countries_file=countries_yaml)

    def test_detect_german_phone(self):
        """German phone +49... maps to 'de'."""
        assert self.detector._detect_from_phone("+491761234567") == "de"

    def test_detect_russian_phone(self):
        """Russian phone +7... maps to 'ru'."""
        assert self.detector._detect_from_phone("+79161234567") == "ru"

    def test_detect_us_phone(self):
        """US phone +1... maps to 'us'."""
        assert self.detector._detect_from_phone("+12025551234") == "us"

    def test_detect_swiss_phone(self):
        """Swiss phone +41... maps to 'ch'."""
        assert self.detector._detect_from_phone("+41791234567") == "ch"

    def test_detect_uae_phone(self):
        """UAE phone +971... maps to 'ae'."""
        assert self.detector._detect_from_phone("+971501234567") == "ae"

    def test_detect_phone_without_plus(self):
        """Phone number without '+' prefix still detects correctly (auto-prepended)."""
        assert self.detector._detect_from_phone("491761234567") == "de"

    def test_detect_phone_with_spaces(self):
        """Phone number with spaces and dashes is normalized before detection."""
        assert self.detector._detect_from_phone("+49 176 123 456") == "de"
        assert self.detector._detect_from_phone("+49-176-123-456") == "de"

    def test_detect_unknown_phone_code(self):
        """Unknown phone code returns None."""
        assert self.detector._detect_from_phone("+999123456789") is None


# ============ LANGUAGE DETECTION TESTS ============

class TestDetectFromLanguage:
    """Test _detect_from_language with various text samples."""

    @pytest.fixture(autouse=True)
    def setup_detector(self, tmp_path):
        countries_yaml = tmp_path / "_countries.yaml"
        countries_yaml.write_text(yaml.dump({"countries": {}, "phone_code_map": {}}))
        self.detector = CountryDetector(countries_file=countries_yaml)

    def test_detect_russian_cyrillic(self):
        """Cyrillic text is detected as Russian."""
        assert self.detector._detect_from_language("Мы компания по разработке программного обеспечения") == "ru"

    def test_detect_arabic_script(self):
        """Arabic script is detected as UAE (default Arabic country)."""
        assert self.detector._detect_from_language("نحن شركة تقنية") == "ae"

    def test_detect_chinese_characters(self):
        """Chinese characters are detected as China."""
        assert self.detector._detect_from_language("我们是一家科技公司") == "cn"

    def test_detect_vietnamese_chars(self):
        """Vietnamese-specific diacritical characters detect Vietnam."""
        assert self.detector._detect_from_language("Chúng tôi là một công ty ở Việt Nam") == "vn"

    def test_detect_german_chars(self):
        """German special characters (sharp-s, umlauts) detect Germany."""
        assert self.detector._detect_from_language("Straße in München") == "de"
        assert self.detector._detect_from_language("Wir sind für Sie da") == "de"

    def test_detect_german_words(self):
        """Two or more German common words detect Germany."""
        assert self.detector._detect_from_language("wir sind eine Firma") == "de"

    def test_detect_french_chars(self):
        """French-specific characters (cedilla, ligature) detect France."""
        assert self.detector._detect_from_language("Le garçon mange") == "fr"
        assert self.detector._detect_from_language("L'œuvre est belle") == "fr"

    def test_detect_portuguese_chars(self):
        """Portuguese tilde characters (ã, õ) detect Brazil (default Portuguese)."""
        assert self.detector._detect_from_language("São Paulo é uma cidade grande") == "br"
        assert self.detector._detect_from_language("Nós temos boas opiniões") == "br"

    def test_detect_spanish_chars(self):
        """Spanish-specific characters (tilde-n, inverted punctuation) detect Spain."""
        assert self.detector._detect_from_language("El niño juega en España") == "es"
        assert self.detector._detect_from_language("¿Cómo estás?") == "es"

    def test_detect_english_words_fallback(self):
        """Text with common English words detects US."""
        assert self.detector._detect_from_language("We are a company and we have the best service") == "us"

    def test_detect_latin_text_defaults_to_us(self):
        """Latin-script text without strong language signals defaults to US."""
        assert self.detector._detect_from_language("lorem ipsum dolor sit amet") == "us"


# ============ DETECT (PRIORITY) TESTS ============

class TestDetect:
    """Test the main detect() method and its priority logic."""

    @pytest.fixture(autouse=True)
    def setup_detector(self, tmp_path):
        countries_yaml = tmp_path / "_countries.yaml"
        countries_yaml.write_text(yaml.dump({"countries": {}, "phone_code_map": {}}))
        self.detector = CountryDetector(countries_file=countries_yaml)

    def test_detect_explicit_country_highest_priority(self):
        """Explicit country overrides phone and language."""
        region, country = self.detector.detect(
            phone="+491761234567",
            dialogue_text="We are a company",
            explicit_country="fr"
        )
        assert country == "fr"
        assert region == "eu"

    def test_detect_phone_over_language(self):
        """Phone detection takes priority over language when no explicit country."""
        region, country = self.detector.detect(
            phone="+491761234567",
            dialogue_text="We are a company and we have the best service"
        )
        assert country == "de"
        assert region == "eu"

    def test_detect_language_fallback(self):
        """Language detection used when no phone or explicit country."""
        region, country = self.detector.detect(
            dialogue_text="Мы компания по разработке"
        )
        assert country == "ru"
        assert region == "ru"

    def test_detect_no_signals_returns_none(self):
        """No signals at all returns (None, None)."""
        region, country = self.detector.detect()
        assert region is None
        assert country is None

    def test_detect_explicit_unknown_country_falls_through(self):
        """Explicit country not in COUNTRY_REGION_MAP falls through to phone."""
        region, country = self.detector.detect(
            phone="+491761234567",
            explicit_country="zz"
        )
        # "zz" not in map, so falls through to phone detection
        assert country == "de"
        assert region == "eu"

    def test_detect_all_three_signals_uses_explicit(self):
        """When all three signals present, explicit country wins."""
        region, country = self.detector.detect(
            phone="+79161234567",
            dialogue_text="Мы компания по разработке",
            explicit_country="US"
        )
        assert country == "us"
        assert region == "na"


# ============ HELPER METHOD TESTS ============

class TestHelperMethods:
    """Test get_country_meta, get_region_for_country, get_all_countries."""

    @pytest.fixture(autouse=True)
    def setup_detector(self, tmp_path):
        countries_yaml = tmp_path / "_countries.yaml"
        countries_yaml.write_text(yaml.dump({
            "countries": {
                "de": {"name": "Germany", "currency": "EUR", "timezone": "CET"},
                "us": {"name": "United States", "currency": "USD"},
            },
            "phone_code_map": {},
        }))
        self.detector = CountryDetector(countries_file=countries_yaml)

    def test_get_country_meta(self):
        """Returns metadata dict for a known country, None for unknown."""
        meta = self.detector.get_country_meta("de")
        assert meta is not None
        assert meta["name"] == "Germany"
        assert meta["currency"] == "EUR"

        assert self.detector.get_country_meta("zz") is None

    def test_get_region_for_country(self):
        """Returns region code for known countries, None for unknown."""
        assert self.detector.get_region_for_country("de") == "eu"
        assert self.detector.get_region_for_country("us") == "na"
        assert self.detector.get_region_for_country("br") == "latam"
        assert self.detector.get_region_for_country("zz") is None

    def test_get_all_countries_no_filter(self):
        """Returns all countries in COUNTRY_REGION_MAP when no region filter."""
        all_countries = self.detector.get_all_countries()
        assert "de" in all_countries
        assert "us" in all_countries
        assert "ru" in all_countries
        assert "br" in all_countries
        # Should match the number of entries in COUNTRY_REGION_MAP
        assert len(all_countries) == len(CountryDetector.COUNTRY_REGION_MAP)

    def test_get_all_countries_filtered_by_region(self):
        """Filtering by region returns only countries in that region."""
        eu_countries = self.detector.get_all_countries(region="eu")
        assert "de" in eu_countries
        assert "fr" in eu_countries
        assert "ch" in eu_countries
        assert "us" not in eu_countries
        assert "ru" not in eu_countries

        latam_countries = self.detector.get_all_countries(region="latam")
        assert "br" in latam_countries
        assert "ar" in latam_countries
        assert "mx" in latam_countries
        assert len(latam_countries) == 3


# ============ SINGLETON TESTS ============

class TestGetCountryDetector:
    """Test get_country_detector singleton function."""

    def teardown_method(self):
        """Reset the module-level singleton after each test."""
        country_detector_module._detector = None

    def test_singleton_pattern(self):
        """Calling get_country_detector twice returns the same instance."""
        country_detector_module._detector = None
        d1 = get_country_detector()
        d2 = get_country_detector()
        assert d1 is d2

    def test_returns_country_detector_instance(self):
        """get_country_detector returns a CountryDetector instance."""
        country_detector_module._detector = None
        detector = get_country_detector()
        assert isinstance(detector, CountryDetector)
