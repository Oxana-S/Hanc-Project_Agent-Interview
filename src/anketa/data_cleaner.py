"""
Data cleaning utilities for anketa extraction.

Handles:
- JSON repair and parsing with retry
- Dialogue marker removal
- Field value sanitization
- Role-based data extraction from dialogue
"""

import re
import json
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import structlog

logger = structlog.get_logger("anketa")


# ============================================================================
# JSON REPAIR
# ============================================================================

class JSONRepair:
    """Robust JSON parsing with multiple repair strategies."""

    # Common JSON errors and their fixes
    FIXES = [
        # Trailing commas before ] or }
        (r',\s*([}\]])', r'\1'),
        # Missing commas between array elements
        (r'"\s*\n\s*"', '",\n"'),
        # Single quotes instead of double
        (r"(?<![\\])'", '"'),
        # Unquoted keys
        (r'(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":'),
        # Python-style None/True/False
        (r'\bNone\b', 'null'),
        (r'\bTrue\b', 'true'),
        (r'\bFalse\b', 'false'),
        # Remove comments
        (r'//.*?$', '', re.MULTILINE),
        (r'/\*.*?\*/', '', re.DOTALL),
    ]

    @classmethod
    def parse(cls, text: str, max_retries: int = 3) -> Tuple[Dict[str, Any], bool]:
        """
        Parse JSON with automatic repair.

        Args:
            text: Raw text potentially containing JSON
            max_retries: Number of repair attempts

        Returns:
            Tuple of (parsed_dict, was_repaired)

        Raises:
            json.JSONDecodeError if all repair attempts fail
        """
        # Step 1: Extract JSON from markdown
        json_text = cls._extract_json(text)

        # Step 2: Try direct parse
        try:
            return json.loads(json_text), False
        except json.JSONDecodeError:
            pass

        # Step 3: Apply incremental fixes
        repaired = json_text
        for i in range(max_retries):
            repaired = cls._apply_fixes(repaired)
            try:
                result = json.loads(repaired)
                logger.info(f"JSON repaired after {i+1} fix iterations")
                return result, True
            except json.JSONDecodeError:
                continue

        # Step 4: Try balanced extraction
        balanced = cls._find_balanced_json(repaired)
        try:
            return json.loads(balanced), True
        except json.JSONDecodeError:
            pass

        # Step 5: Try minimal extraction (just first level)
        minimal = cls._extract_minimal_json(repaired)
        try:
            return json.loads(minimal), True
        except json.JSONDecodeError as e:
            logger.error(
                "All JSON repair attempts failed",
                original_length=len(text),
                error=str(e)
            )
            raise

    @classmethod
    def _extract_json(cls, text: str) -> str:
        """Extract JSON content from markdown or mixed text."""
        # Try markdown code blocks first
        if "```json" in text:
            match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
            if match:
                return match.group(1).strip()

        if "```" in text:
            match = re.search(r'```\s*([\s\S]*?)\s*```', text)
            if match:
                content = match.group(1).strip()
                if content.startswith('{'):
                    return content

        # Find JSON object boundaries
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            return text[start:end + 1]

        return text.strip()

    @classmethod
    def _apply_fixes(cls, text: str) -> str:
        """Apply all fix patterns."""
        result = text
        for pattern, replacement, *flags in cls.FIXES:
            flag = flags[0] if flags else 0
            result = re.sub(pattern, replacement, result, flags=flag)
        return result

    @classmethod
    def _find_balanced_json(cls, text: str) -> str:
        """Find first balanced JSON object."""
        start = text.find('{')
        if start == -1:
            return text

        brace_count = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start:i + 1]

        return text[start:]

    @classmethod
    def _extract_minimal_json(cls, text: str) -> str:
        """Extract minimal valid JSON with just top-level fields."""
        # Try to extract key-value pairs at top level
        pairs = []
        pattern = r'"([^"]+)"\s*:\s*("[^"]*"|null|true|false|\d+(?:\.\d+)?|\[.*?\]|\{.*?\})'

        for match in re.finditer(pattern, text, re.DOTALL):
            key = match.group(1)
            value = match.group(2)
            # Validate value is parseable
            try:
                json.loads(value)
                pairs.append(f'"{key}": {value}')
            except json.JSONDecodeError:
                # Try to quote as string
                if not value.startswith('"'):
                    safe_value = json.dumps(value)
                    pairs.append(f'"{key}": {safe_value}')

        if pairs:
            return '{' + ', '.join(pairs) + '}'
        return text


# ============================================================================
# DIALOGUE CLEANER
# ============================================================================

@dataclass
class DialoguePattern:
    """Pattern for detecting dialogue contamination."""
    pattern: re.Pattern
    description: str
    severity: str  # "high", "medium", "low"


class DialogueCleaner:
    """
    Removes dialogue markers and contamination from extracted field values.

    Detects and removes:
    - Role markers (Консультант:, Клиент:, USER:, ASSISTANT:)
    - Greeting phrases at the start
    - Question phrases
    - Conversation flow markers
    """

    # Patterns that indicate dialogue contamination
    DIALOGUE_PATTERNS = [
        # Role markers
        DialoguePattern(
            re.compile(r'^(Консультант|Клиент|USER|ASSISTANT|AI|Bot)\s*:?\s*', re.IGNORECASE),
            "Role marker at start",
            "high"
        ),
        # Inline role markers
        DialoguePattern(
            re.compile(r'(Консультант|Клиент|USER|ASSISTANT)\s*:', re.IGNORECASE),
            "Inline role marker",
            "high"
        ),
        # Greeting phrases that shouldn't be in data fields
        DialoguePattern(
            re.compile(r'^(Здравствуйте|Добрый день|Добрый вечер|Привет|Приветствую)[,!.]?\s*', re.IGNORECASE),
            "Greeting phrase",
            "medium"
        ),
        # Question starters in non-question fields
        DialoguePattern(
            re.compile(r'^(Расскажите|Скажите|Подскажите|Могли бы вы)\s+', re.IGNORECASE),
            "Question phrase",
            "medium"
        ),
        # Confirmation phrases
        DialoguePattern(
            re.compile(r'^(Да,?\s*|Нет,?\s*|Конечно,?\s*|Хорошо,?\s*|Отлично,?\s*|Понятно,?\s*)(.*)', re.IGNORECASE | re.DOTALL),
            "Confirmation phrase",
            "low"
        ),
        # Filler phrases
        DialoguePattern(
            re.compile(r'^(Э{1,3},?\s*|М{1,3},?\s*|Ну,?\s*|Так,?\s*|Вот,?\s*)', re.IGNORECASE),
            "Filler phrase",
            "low"
        ),
        # "Let me explain" type phrases
        DialoguePattern(
            re.compile(r'^(Давайте|Позвольте|Сейчас|Итак)[,\s]+', re.IGNORECASE),
            "Transitional phrase",
            "low"
        ),
        # v3.2: Long conversational responses (shouldn't be in data fields)
        DialoguePattern(
            re.compile(r'^(Благодарю|Спасибо|Верно|Именно|Совершенно|Абсолютно)[,!.\s]', re.IGNORECASE),
            "Conversational response",
            "medium"
        ),
        # v3.2: Phrases indicating full dialogue capture
        DialoguePattern(
            re.compile(r'(вы полностью|вы точно|как вы описали|как вы сказали|всё верно)', re.IGNORECASE),
            "Dialogue confirmation",
            "high"
        ),
    ]

    # v3.2: Patterns that indicate entire value is dialogue (for strict fields)
    FULL_DIALOGUE_INDICATORS = [
        re.compile(r'^(Да|Нет|Конечно|Хорошо|Отлично|Понятно|Благодарю|Спасибо|Верно)[,!.\s]', re.IGNORECASE),
        re.compile(r'(уловили суть|всё верно|именно так|правильно понял|точно подметили)', re.IGNORECASE),
        re.compile(r'\?$'),  # Ends with question mark
        re.compile(r'.{200,}'),  # Too long for identifier fields
    ]

    # Fields that should never contain dialogue
    STRICT_FIELDS = {
        'company_name', 'industry', 'specialization', 'website',
        'contact_name', 'contact_role', 'agent_name', 'language',
        'voice_gender', 'voice_tone', 'call_direction'
    }

    # Fields that may have limited dialogue (descriptions)
    DESCRIPTION_FIELDS = {
        'agent_purpose', 'business_description', 'specialization'
    }

    def __init__(self, strict_mode: bool = True):
        """
        Initialize cleaner.

        Args:
            strict_mode: If True, remove all dialogue patterns.
                        If False, only remove high-severity patterns.
        """
        self.strict_mode = strict_mode

    def clean(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Clean all dialogue contamination from data dict.

        Args:
            data: Dictionary with potentially contaminated values

        Returns:
            Tuple of (cleaned_data, list_of_changes)
        """
        cleaned = {}
        changes = []

        for key, value in data.items():
            if isinstance(value, str):
                new_value, field_changes = self._clean_string(key, value)
                cleaned[key] = new_value
                changes.extend(field_changes)
            elif isinstance(value, list):
                new_list = []
                for item in value:
                    if isinstance(item, str):
                        new_item, item_changes = self._clean_string(f"{key}[]", item)
                        new_list.append(new_item)
                        changes.extend(item_changes)
                    elif isinstance(item, dict):
                        new_item, item_changes = self.clean(item)
                        new_list.append(new_item)
                        changes.extend(item_changes)
                    else:
                        new_list.append(item)
                cleaned[key] = new_list
            elif isinstance(value, dict):
                new_value, nested_changes = self.clean(value)
                cleaned[key] = new_value
                changes.extend(nested_changes)
            else:
                cleaned[key] = value

        return cleaned, changes

    def _clean_string(self, field_name: str, value: str) -> Tuple[str, List[str]]:
        """Clean a single string value."""
        if not value or not value.strip():
            return value, []

        original = value
        changes = []
        cleaned = value.strip()

        # Determine strictness based on field type
        is_strict_field = field_name in self.STRICT_FIELDS
        min_severity = "low" if (self.strict_mode or is_strict_field) else "high"

        # v3.2: For strict fields, check if entire value is dialogue (should be rejected)
        if is_strict_field:
            for indicator in self.FULL_DIALOGUE_INDICATORS:
                if indicator.search(cleaned):
                    changes.append(f"{field_name}: rejected full dialogue value")
                    logger.debug(
                        "Rejected dialogue value for strict field",
                        field=field_name,
                        value_preview=cleaned[:50]
                    )
                    return "", changes

        severity_order = {"high": 0, "medium": 1, "low": 2}

        # Apply patterns
        for pattern_info in self.DIALOGUE_PATTERNS:
            if severity_order[pattern_info.severity] > severity_order[min_severity]:
                continue

            match = pattern_info.pattern.search(cleaned)
            if match:
                # For confirmation phrases, keep the content after the phrase
                if pattern_info.description == "Confirmation phrase" and match.group(2):
                    cleaned = match.group(2).strip()
                else:
                    cleaned = pattern_info.pattern.sub('', cleaned).strip()

                if cleaned != original:
                    changes.append(f"{field_name}: removed {pattern_info.description}")

        # Additional cleaning for strict fields
        if is_strict_field:
            # Remove any remaining punctuation patterns from greetings
            cleaned = re.sub(r'^[,!.:\s]+', '', cleaned)
            # Remove trailing punctuation that looks like dialogue
            cleaned = re.sub(r'[?!]+$', '', cleaned)
            # Limit length for identifier-like fields
            if field_name in {'company_name', 'agent_name', 'contact_name'}:
                if len(cleaned) > 100:
                    # Take first meaningful part
                    parts = re.split(r'[,;.]', cleaned)
                    cleaned = parts[0].strip()[:100]
                    changes.append(f"{field_name}: truncated long value")

        return cleaned, changes

    def clean_anketa_dict(self, anketa_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Clean an entire anketa dictionary.

        Convenience method that applies field-specific cleaning rules.
        """
        return self.clean(anketa_data)


# ============================================================================
# SMART EXTRACTOR
# ============================================================================

class SmartExtractor:
    """
    Extracts structured data from dialogue by analyzing speaker roles.

    Instead of relying purely on LLM extraction, this class parses
    the dialogue to find client statements that contain factual data.
    """

    # Patterns to find in client messages
    EXTRACTION_PATTERNS = {
        'company_name': [
            r'(?:компания|фирма|организация|мы)\s+[«"]?([А-ЯЁа-яё\w\s\-]+)[»"]?',
            r'[«"]([А-ЯЁA-Za-z\w\s\-]+)[»"]',
            r'называется\s+[«"]?([А-ЯЁа-яё\w\s\-]+)[»"]?',
        ],
        'industry': [
            r'(?:отрасль|сфера|направление)\s*[-:–]?\s*([А-ЯЁа-яё\w\s\-/]+)',
            r'(?:занимаемся|работаем в сфере|в области)\s+([А-ЯЁа-яё\w\s\-]+)',
        ],
        'contact_name': [
            r'меня зовут\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)',
            r'это\s+([А-ЯЁ][а-яё]+),?\s+(?:директор|руководитель|менеджер)',
        ],
        'contact_role': [
            r'я\s+[-–]?\s*([а-яё]+\s*(?:директор|руководитель|менеджер|владелец|основатель))',
            r'(?:должность|позиция)\s*[-:–]?\s*([А-ЯЁа-яё\w\s\-]+)',
        ],
        'employee_count': [
            r'(\d+)\s*(?:человек|сотрудник|работник)',
            r'штат[еа]?\s*[-:–]?\s*(\d+)',
        ],
        'website': [
            r'(https?://[^\s]+)',
            r'сайт\s*[-:–]?\s*([а-яёa-z0-9\-\.]+\.[a-zа-яё]{2,})',
        ],
    }

    def __init__(self):
        """Initialize extractor with compiled patterns."""
        self._compiled_patterns = {}
        for field, patterns in self.EXTRACTION_PATTERNS.items():
            self._compiled_patterns[field] = [
                re.compile(p, re.IGNORECASE | re.UNICODE)
                for p in patterns
            ]

    def extract_from_dialogue(
        self,
        dialogue: List[Dict[str, str]],
        existing_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract structured data from dialogue messages.

        Args:
            dialogue: List of {role, content} messages
            existing_data: Optional existing data to augment (not override)

        Returns:
            Dictionary with extracted values
        """
        extracted = {}

        # Only process client messages for factual data
        client_messages = [
            msg['content'] for msg in dialogue
            if msg.get('role', '').lower() in ('user', 'client', 'клиент')
        ]

        # Combine all client text
        client_text = ' '.join(client_messages)

        # Extract each field
        for field, patterns in self._compiled_patterns.items():
            # Skip if already have good data
            if existing_data and existing_data.get(field):
                continue

            for pattern in patterns:
                match = pattern.search(client_text)
                if match:
                    value = match.group(1).strip()
                    # Basic validation
                    if self._validate_extracted_value(field, value):
                        extracted[field] = value
                        break

        return extracted

    def _validate_extracted_value(self, field: str, value: str) -> bool:
        """Validate that extracted value makes sense for field type."""
        if not value or len(value) < 2:
            return False

        # Field-specific validation
        if field == 'website':
            # Should look like a URL or domain
            return '.' in value and len(value) < 200

        if field == 'employee_count':
            # Should be a reasonable number
            try:
                num = int(re.sub(r'\D', '', value))
                return 1 <= num <= 1000000
            except ValueError:
                return False

        if field in ('company_name', 'contact_name'):
            # Should be reasonable length, not a sentence
            return len(value) < 100 and value.count(' ') < 5

        return True

    def merge_with_llm_data(
        self,
        dialogue_data: Dict[str, Any],
        llm_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge dialogue-extracted data with LLM-extracted data.

        Dialogue data takes precedence for strict fields (company_name, etc.)
        LLM data takes precedence for descriptive fields (agent_purpose, etc.)
        """
        merged = dict(llm_data)

        # Fields where dialogue extraction is more reliable
        reliable_fields = {
            'company_name', 'contact_name', 'contact_role',
            'website', 'employee_count'
        }

        for field, value in dialogue_data.items():
            if field in reliable_fields:
                # Prefer dialogue-extracted for these
                if value and (not merged.get(field) or len(str(merged.get(field, ''))) > len(str(value)) * 3):
                    merged[field] = value
            else:
                # Only fill if LLM missed it
                if not merged.get(field) and value:
                    merged[field] = value

        return merged


# ============================================================================
# ANKETA POST-PROCESSOR
# ============================================================================

class AnketaPostProcessor:
    """
    Post-processing pipeline for FinalAnketa.

    Applies multiple cleaning and enrichment stages:
    1. Dialogue contamination removal
    2. Value normalization
    3. Field validation
    4. Default value injection
    """

    def __init__(
        self,
        strict_cleaning: bool = True,
        normalize_values: bool = True,
        inject_defaults: bool = True
    ):
        """
        Initialize post-processor.

        Args:
            strict_cleaning: Remove all dialogue patterns
            normalize_values: Normalize field values (case, whitespace)
            inject_defaults: Fill missing fields with sensible defaults
        """
        self.cleaner = DialogueCleaner(strict_mode=strict_cleaning)
        self.normalize_values = normalize_values
        self.inject_defaults = inject_defaults

    def process(self, anketa_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Process anketa data through all stages.

        Args:
            anketa_data: Raw anketa dictionary

        Returns:
            Tuple of (processed_data, processing_report)
        """
        report = {
            "cleaning_changes": [],
            "normalization_changes": [],
            "defaults_applied": [],
            "warnings": []
        }

        data = dict(anketa_data)

        # Stage 1: Clean dialogue contamination
        data, cleaning_changes = self.cleaner.clean(data)
        report["cleaning_changes"] = cleaning_changes

        # Stage 2: Normalize values
        if self.normalize_values:
            data, norm_changes = self._normalize(data)
            report["normalization_changes"] = norm_changes

        # Stage 3: Validate and warn
        warnings = self._validate(data)
        report["warnings"] = warnings

        # Stage 4: Inject defaults
        if self.inject_defaults:
            data, defaults = self._inject_defaults(data)
            report["defaults_applied"] = defaults

        logger.info(
            "Post-processing completed",
            cleaning_changes=len(report["cleaning_changes"]),
            normalization_changes=len(report["normalization_changes"]),
            defaults_applied=len(report["defaults_applied"]),
            warnings=len(report["warnings"])
        )

        return data, report

    def _normalize(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Normalize field values."""
        changes = []
        normalized = dict(data)

        # Normalize string fields
        string_normalizations = {
            'language': lambda v: v.lower()[:2] if v else 'ru',
            'voice_gender': lambda v: v.lower() if v in ['male', 'female', 'Male', 'Female'] else 'female',
            'call_direction': lambda v: v.lower() if v else 'inbound',
        }

        for field, normalizer in string_normalizations.items():
            if field in normalized and normalized[field]:
                old_value = normalized[field]
                try:
                    new_value = normalizer(old_value)
                    if new_value != old_value:
                        normalized[field] = new_value
                        changes.append(f"{field}: '{old_value}' -> '{new_value}'")
                except Exception:
                    pass

        # Clean whitespace from all string fields
        for key, value in normalized.items():
            if isinstance(value, str):
                cleaned = ' '.join(value.split())
                if cleaned != value:
                    normalized[key] = cleaned
                    changes.append(f"{key}: normalized whitespace")

        return normalized, changes

    def _validate(self, data: Dict[str, Any]) -> List[str]:
        """Validate data and return warnings."""
        warnings = []

        # Check for suspiciously long values
        for field in ['company_name', 'agent_name', 'industry']:
            value = data.get(field, '')
            if isinstance(value, str) and len(value) > 150:
                warnings.append(f"{field} is unusually long ({len(value)} chars)")

        # Check for empty required fields
        required = ['company_name', 'industry', 'agent_purpose']
        for field in required:
            if not data.get(field):
                warnings.append(f"Required field '{field}' is empty")

        # Check for invalid enum values
        valid_directions = ['inbound', 'outbound', 'both']
        if data.get('call_direction') and data['call_direction'].lower() not in valid_directions:
            warnings.append(f"Invalid call_direction: {data.get('call_direction')}")

        return warnings

    def _inject_defaults(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Inject default values for missing fields."""
        defaults_applied = []
        result = dict(data)

        defaults = {
            'language': 'ru',
            'voice_gender': 'female',
            'voice_tone': 'professional',
            'call_direction': 'inbound',
        }

        for field, default_value in defaults.items():
            if not result.get(field):
                result[field] = default_value
                defaults_applied.append(f"{field} = '{default_value}'")

        # Generate agent_name if missing
        if not result.get('agent_name') and result.get('company_name'):
            result['agent_name'] = f"Ассистент {result['company_name']}"
            defaults_applied.append(f"agent_name = '{result['agent_name']}'")

        return result, defaults_applied
