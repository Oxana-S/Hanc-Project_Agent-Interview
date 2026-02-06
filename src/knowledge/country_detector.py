"""
Country Detector - detects country from phone, language, or explicit selection.

Combination approach:
1. Phone code — primary signal (+49 → Germany)
2. Language detection — from dialogue text
3. Manual override — user can switch
"""

import re
from typing import Dict, List, Optional, Tuple

import structlog
import yaml
from pathlib import Path

logger = structlog.get_logger("knowledge")


class CountryDetector:
    """
    Detects country and region from various signals.

    Priority:
    1. Explicit country override (highest)
    2. Phone code detection
    3. Language detection (lowest)
    """

    # Language to likely countries mapping (most common first)
    LANGUAGE_COUNTRY_MAP: Dict[str, List[str]] = {
        "de": ["de", "at", "ch"],
        "fr": ["fr", "ch", "ca"],
        "it": ["it", "ch"],
        "es": ["es", "ar", "mx"],
        "pt": ["pt", "br"],
        "en": ["us", "ca", "gb"],
        "ru": ["ru"],
        "ar": ["ae", "sa", "qa"],
        "zh": ["cn"],
        "vi": ["vn"],
        "id": ["id"],
        "ro": ["ro"],
        "bg": ["bg"],
        "hu": ["hu"],
        "el": ["gr"],
    }

    # Phone code patterns (with country code)
    PHONE_PATTERNS = [
        (r"^\+49", "de"),
        (r"^\+41", "ch"),
        (r"^\+43", "at"),
        (r"^\+33", "fr"),
        (r"^\+39", "it"),
        (r"^\+34", "es"),
        (r"^\+351", "pt"),
        (r"^\+40", "ro"),
        (r"^\+359", "bg"),
        (r"^\+36", "hu"),
        (r"^\+30", "gr"),
        (r"^\+1", "us"),  # Could also be CA
        (r"^\+55", "br"),
        (r"^\+54", "ar"),
        (r"^\+52", "mx"),
        (r"^\+971", "ae"),
        (r"^\+966", "sa"),
        (r"^\+974", "qa"),
        (r"^\+86", "cn"),
        (r"^\+84", "vn"),
        (r"^\+62", "id"),
        (r"^\+7", "ru"),
    ]

    # Country to region mapping
    COUNTRY_REGION_MAP: Dict[str, str] = {
        # Europe
        "de": "eu", "ch": "eu", "at": "eu", "fr": "eu", "it": "eu",
        "es": "eu", "pt": "eu", "ro": "eu", "bg": "eu", "hu": "eu", "gr": "eu",
        # North America
        "us": "na", "ca": "na",
        # Latin America
        "br": "latam", "ar": "latam", "mx": "latam",
        # Middle East
        "ae": "mena", "sa": "mena", "qa": "mena",
        # Southeast Asia
        "cn": "sea", "vn": "sea", "id": "sea",
        # Russia
        "ru": "ru",
    }

    def __init__(self, countries_file: Optional[Path] = None):
        """
        Initialize detector.

        Args:
            countries_file: Path to _countries.yaml for additional metadata
        """
        self._countries_meta: Dict[str, dict] = {}
        self._phone_code_map: Dict[str, str] = {}

        if countries_file is None:
            project_root = Path(__file__).parent.parent.parent
            countries_file = project_root / "config" / "industries" / "_countries.yaml"

        self._load_countries_meta(countries_file)

    def _load_countries_meta(self, path: Path):
        """Load country metadata from YAML."""
        if not path.exists():
            logger.warning("Countries file not found", path=str(path))
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self._countries_meta = data.get("countries", {})
                self._phone_code_map = data.get("phone_code_map", {})
        except Exception as e:
            logger.error("Failed to load countries file", error=str(e))

    def detect(
        self,
        phone: Optional[str] = None,
        dialogue_text: Optional[str] = None,
        explicit_country: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Detect region and country from available signals.

        Args:
            phone: Phone number with country code
            dialogue_text: Text from dialogue for language detection
            explicit_country: Explicit country selection (overrides all)

        Returns:
            Tuple of (region, country) or (None, None) if not detected
        """
        # Priority 1: Explicit override
        if explicit_country:
            country = explicit_country.lower()
            region = self.COUNTRY_REGION_MAP.get(country)
            if region:
                logger.debug(
                    "Country detected from explicit override",
                    country=country,
                    region=region
                )
                return region, country

        # Priority 2: Phone code
        if phone:
            country = self._detect_from_phone(phone)
            if country:
                region = self.COUNTRY_REGION_MAP.get(country)
                logger.debug(
                    "Country detected from phone",
                    phone=phone,
                    country=country,
                    region=region
                )
                return region, country

        # Priority 3: Language detection
        if dialogue_text:
            country = self._detect_from_language(dialogue_text)
            if country:
                region = self.COUNTRY_REGION_MAP.get(country)
                logger.debug(
                    "Country detected from language",
                    country=country,
                    region=region
                )
                return region, country

        return None, None

    def _detect_from_phone(self, phone: str) -> Optional[str]:
        """Detect country from phone number."""
        # Normalize phone
        phone = phone.strip().replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+" + phone

        # Try phone_code_map first (from YAML)
        for code, country in self._phone_code_map.items():
            if phone.startswith(code):
                return country

        # Fall back to built-in patterns
        for pattern, country in self.PHONE_PATTERNS:
            if re.match(pattern, phone):
                return country

        return None

    def _detect_from_language(self, text: str) -> Optional[str]:
        """
        Detect country from text language.

        Uses simple heuristics based on character sets and common words.
        """
        text_lower = text.lower()

        # Russian indicators (check first - Cyrillic is definitive)
        if re.search(r"[а-яА-ЯёЁ]", text):
            return "ru"

        # Arabic indicators
        if re.search(r"[\u0600-\u06FF]", text):
            return "ae"  # Default to UAE for Arabic

        # Chinese indicators
        if re.search(r"[\u4e00-\u9fff]", text):
            return "cn"

        # Vietnamese indicators
        if any(c in text for c in "ăâđêôơư"):
            return "vn"

        # German indicators - check common words and special chars
        german_words = ["wir", "sind", "ist", "und", "für", "nicht", "mit", "sie", "ein", "eine"]
        german_chars = ["ß", "ü", "ö", "ä"]
        if any(c in text_lower for c in german_chars) or \
           sum(1 for w in german_words if f" {w} " in f" {text_lower} ") >= 2:
            return "de"

        # French indicators
        french_words = ["nous", "vous", "sommes", "sont", "avec", "pour", "dans", "une", "les"]
        french_chars = ["ç", "œ", "ê", "î", "ô", "û"]
        if any(c in text_lower for c in french_chars) or \
           sum(1 for w in french_words if f" {w} " in f" {text_lower} ") >= 2:
            return "fr"

        # Portuguese indicators (check before Spanish - some overlap)
        portuguese_words = ["empresa", "logística", "uma", "são", "estão", "você", "nós"]
        portuguese_chars = ["ã", "õ"]
        if any(c in text_lower for c in portuguese_chars) or \
           sum(1 for w in portuguese_words if f" {w} " in f" {text_lower} ") >= 2:
            # "você" is more common in Brazilian Portuguese
            if "você" in text_lower or "vocês" in text_lower:
                return "br"
            return "br"  # Default to Brazil for Portuguese

        # Spanish indicators
        spanish_words = ["somos", "estamos", "nosotros", "empresa", "para", "con", "los", "las"]
        spanish_chars = ["ñ", "¿", "¡"]
        if any(c in text_lower for c in spanish_chars) or \
           sum(1 for w in spanish_words if f" {w} " in f" {text_lower} ") >= 2:
            return "es"

        # Italian indicators
        italian_words = ["siamo", "sono", "abbiamo", "nostro", "nostra", "azienda", "gli", "che"]
        if sum(1 for w in italian_words if f" {w} " in f" {text_lower} ") >= 2:
            return "it"

        # Default: if Latin script with English words, assume English/US
        english_words = ["we", "are", "is", "the", "and", "our", "have", "company"]
        if sum(1 for w in english_words if f" {w} " in f" {text_lower} ") >= 2:
            return "us"

        # Fallback for any Latin text
        if re.search(r"[a-zA-Z]", text):
            return "us"

        return None

    def get_country_meta(self, country: str) -> Optional[dict]:
        """Get metadata for a country."""
        return self._countries_meta.get(country)

    def get_region_for_country(self, country: str) -> Optional[str]:
        """Get region code for a country."""
        return self.COUNTRY_REGION_MAP.get(country.lower())

    def get_all_countries(self, region: Optional[str] = None) -> List[str]:
        """Get list of all supported countries, optionally filtered by region."""
        if region:
            return [c for c, r in self.COUNTRY_REGION_MAP.items() if r == region]
        return list(self.COUNTRY_REGION_MAP.keys())


# Singleton instance
_detector: Optional[CountryDetector] = None


def get_country_detector() -> CountryDetector:
    """Get singleton CountryDetector instance."""
    global _detector
    if _detector is None:
        _detector = CountryDetector()
    return _detector
