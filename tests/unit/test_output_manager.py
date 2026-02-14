"""
Tests for src/output/manager.py

Covers:
- OutputManager initialization
- Company directory creation with versioning
- Anketa saving (MD and JSON)
- Dialogue saving with phase formatting
- Slugify function
- Version detection
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from src.output.manager import OutputManager


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for output tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def output_manager(temp_output_dir):
    """Create OutputManager with temporary directory."""
    return OutputManager(base_dir=temp_output_dir)


@pytest.fixture
def sample_dialogue_history():
    """Sample dialogue history for testing."""
    return [
        {"role": "assistant", "content": "Здравствуйте!", "phase": "discovery"},
        {"role": "user", "content": "Привет", "phase": "discovery"},
        {"role": "assistant", "content": "Расскажите о компании", "phase": "discovery"},
        {"role": "user", "content": "Мы IT компания", "phase": "discovery"},
        {"role": "assistant", "content": "Вот мое предложение", "phase": "proposal"},
        {"role": "user", "content": "Отлично!", "phase": "proposal"},
    ]


@pytest.fixture
def sample_anketa_json():
    """Sample anketa data for testing."""
    return {
        "company_name": "Test Company",
        "industry": "IT",
        "agent_purpose": "Customer support",
        "created_at": datetime(2026, 2, 6, 12, 0, 0),
    }


# ============================================================================
# Initialization Tests
# ============================================================================

class TestOutputManagerInit:
    """Tests for OutputManager initialization."""

    def test_init_with_custom_dir(self, temp_output_dir):
        """Should initialize with custom base directory."""
        manager = OutputManager(base_dir=temp_output_dir)
        assert manager.base_dir == temp_output_dir
        assert temp_output_dir.exists()

    def test_init_with_default_dir(self):
        """Should use 'output' as default base directory."""
        with patch.object(Path, "mkdir"):
            manager = OutputManager()
            assert manager.base_dir == Path("output")

    def test_init_creates_base_dir(self, temp_output_dir):
        """Should create base directory if it doesn't exist."""
        new_dir = temp_output_dir / "new_output"
        manager = OutputManager(base_dir=new_dir)
        assert new_dir.exists()

    def test_init_with_nested_path(self, temp_output_dir):
        """Should create nested directory structure."""
        nested_dir = temp_output_dir / "level1" / "level2" / "output"
        manager = OutputManager(base_dir=nested_dir)
        assert nested_dir.exists()


# ============================================================================
# get_company_dir Tests
# ============================================================================

class TestGetCompanyDir:
    """Tests for get_company_dir method."""

    def test_creates_company_dir(self, output_manager):
        """Should create company directory."""
        company_dir = output_manager.get_company_dir("Test Company")
        assert company_dir.exists()
        assert company_dir.is_dir()

    def test_creates_date_subdirectory(self, output_manager):
        """Should create date subdirectory."""
        date = datetime(2026, 2, 6)
        company_dir = output_manager.get_company_dir("Test", date=date)
        assert "2026-02-06" in str(company_dir)

    def test_uses_current_date_by_default(self, output_manager):
        """Should use current date when not specified."""
        from datetime import timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        company_dir = output_manager.get_company_dir("Test")
        assert today in str(company_dir)

    def test_creates_slugified_company_name(self, output_manager):
        """Should slugify company name."""
        company_dir = output_manager.get_company_dir("Салон красоты Glamour")
        # Should contain transliterated slug
        assert "_v1" in company_dir.name
        assert "salon" in company_dir.name.lower()

    def test_first_version_is_v1(self, output_manager):
        """First company directory should be v1."""
        company_dir = output_manager.get_company_dir("Test")
        assert "_v1" in company_dir.name

    def test_increments_version_for_same_company(self, output_manager):
        """Should increment version for same company same day."""
        date = datetime(2026, 2, 6)
        dir1 = output_manager.get_company_dir("Test", date=date)
        dir2 = output_manager.get_company_dir("Test", date=date)
        dir3 = output_manager.get_company_dir("Test", date=date)

        assert "_v1" in dir1.name
        assert "_v2" in dir2.name
        assert "_v3" in dir3.name

    def test_different_companies_same_date_v1(self, output_manager):
        """Different companies should each start at v1."""
        date = datetime(2026, 2, 6)
        dir1 = output_manager.get_company_dir("Company A", date=date)
        dir2 = output_manager.get_company_dir("Company B", date=date)

        assert "_v1" in dir1.name
        assert "_v1" in dir2.name

    def test_same_company_different_dates_v1(self, output_manager):
        """Same company on different dates should start at v1."""
        dir1 = output_manager.get_company_dir("Test", date=datetime(2026, 2, 5))
        dir2 = output_manager.get_company_dir("Test", date=datetime(2026, 2, 6))

        assert "_v1" in dir1.name
        assert "_v1" in dir2.name

    def test_handles_unicode_company_name(self, output_manager):
        """Should handle Cyrillic company names."""
        company_dir = output_manager.get_company_dir("Компания Тест")
        assert company_dir.exists()
        assert "_v1" in company_dir.name

    def test_handles_special_characters(self, output_manager):
        """Should handle special characters in company name."""
        company_dir = output_manager.get_company_dir("Test & Co. (LLC)")
        assert company_dir.exists()
        assert "_v1" in company_dir.name

    def test_handles_empty_company_name(self, output_manager):
        """Should handle empty company name."""
        company_dir = output_manager.get_company_dir("")
        assert company_dir.exists()
        assert "unnamed_v1" in company_dir.name


# ============================================================================
# save_anketa Tests
# ============================================================================

class TestSaveAnketa:
    """Tests for save_anketa method."""

    def test_saves_md_file(self, output_manager, temp_output_dir):
        """Should save anketa.md file."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_anketa(
            company_dir,
            anketa_md="# Test Anketa\n\nContent here",
            anketa_json={"key": "value"}
        )
        assert result["md"].exists()
        assert result["md"].name == "anketa.md"

    def test_saves_json_file(self, output_manager):
        """Should save anketa.json file."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_anketa(
            company_dir,
            anketa_md="# Test",
            anketa_json={"company": "Test", "value": 123}
        )
        assert result["json"].exists()
        assert result["json"].name == "anketa.json"

    def test_md_content_correct(self, output_manager):
        """Should write correct MD content."""
        company_dir = output_manager.get_company_dir("Test")
        md_content = "# Анкета\n\nСодержимое анкеты"
        result = output_manager.save_anketa(
            company_dir,
            anketa_md=md_content,
            anketa_json={}
        )
        saved_content = result["md"].read_text(encoding="utf-8")
        assert saved_content == md_content

    def test_json_content_correct(self, output_manager):
        """Should write correct JSON content."""
        company_dir = output_manager.get_company_dir("Test")
        json_data = {"company": "Test", "items": [1, 2, 3]}
        result = output_manager.save_anketa(
            company_dir,
            anketa_md="",
            anketa_json=json_data
        )
        saved_content = json.loads(result["json"].read_text(encoding="utf-8"))
        assert saved_content == json_data

    def test_json_handles_datetime(self, output_manager, sample_anketa_json):
        """Should serialize datetime objects in JSON."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_anketa(
            company_dir,
            anketa_md="",
            anketa_json=sample_anketa_json
        )
        saved = json.loads(result["json"].read_text(encoding="utf-8"))
        assert saved["created_at"] == "2026-02-06T12:00:00"

    def test_json_preserves_unicode(self, output_manager):
        """Should preserve Unicode characters in JSON."""
        company_dir = output_manager.get_company_dir("Test")
        json_data = {"name": "Тестовая компания", "city": "Москва"}
        result = output_manager.save_anketa(
            company_dir,
            anketa_md="",
            anketa_json=json_data
        )
        saved = json.loads(result["json"].read_text(encoding="utf-8"))
        assert saved["name"] == "Тестовая компания"
        assert saved["city"] == "Москва"

    def test_json_is_indented(self, output_manager):
        """Should format JSON with indentation."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_anketa(
            company_dir,
            anketa_md="",
            anketa_json={"key": "value"}
        )
        content = result["json"].read_text(encoding="utf-8")
        assert "  " in content  # 2-space indent

    def test_returns_both_paths(self, output_manager):
        """Should return dict with both paths."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_anketa(
            company_dir,
            anketa_md="",
            anketa_json={}
        )
        assert "md" in result
        assert "json" in result
        assert isinstance(result["md"], Path)
        assert isinstance(result["json"], Path)


# ============================================================================
# save_dialogue Tests
# ============================================================================

class TestSaveDialogue:
    """Tests for save_dialogue method."""

    def test_saves_dialogue_file(self, output_manager, sample_dialogue_history):
        """Should save dialogue.md file."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test Company",
            client_name="Иван"
        )
        assert result.exists()
        assert result.name == "dialogue.md"

    def test_dialogue_contains_company_name(self, output_manager, sample_dialogue_history):
        """Should include company name in header."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test Company",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "Test Company" in content

    def test_dialogue_contains_date(self, output_manager, sample_dialogue_history):
        """Should include date in metadata."""
        company_dir = output_manager.get_company_dir("Test")
        start_time = datetime(2026, 2, 6, 14, 30, 0)
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test",
            client_name="Иван",
            start_time=start_time
        )
        content = result.read_text(encoding="utf-8")
        assert "2026-02-06" in content
        assert "14:30:00" in content

    def test_dialogue_contains_duration(self, output_manager, sample_dialogue_history):
        """Should include duration in metadata."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test",
            client_name="Иван",
            duration_seconds=300.0  # 5 minutes
        )
        content = result.read_text(encoding="utf-8")
        assert "5.0 мин" in content

    def test_dialogue_contains_message_count(self, output_manager, sample_dialogue_history):
        """Should include message count."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert str(len(sample_dialogue_history)) in content

    def test_dialogue_formats_assistant_messages(self, output_manager, sample_dialogue_history):
        """Should format assistant messages correctly."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "**AI-Консультант:**" in content

    def test_dialogue_formats_user_messages(self, output_manager, sample_dialogue_history):
        """Should format user messages with client name."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "**Клиент (Иван):**" in content

    def test_dialogue_includes_phase_headers(self, output_manager, sample_dialogue_history):
        """Should include phase headers."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "ЗНАКОМСТВО" in content or "Discovery" in content
        assert "ПРЕДЛОЖЕНИЕ" in content or "Proposal" in content

    def test_dialogue_quotes_content(self, output_manager):
        """Should quote message content."""
        dialogue = [{"role": "user", "content": "Test message", "phase": "discovery"}]
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=dialogue,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "> Test message" in content

    def test_dialogue_handles_multiline_content(self, output_manager):
        """Should handle multiline message content."""
        dialogue = [{"role": "user", "content": "Line 1\nLine 2\nLine 3", "phase": "discovery"}]
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=dialogue,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "> Line 1" in content
        assert "> Line 2" in content
        assert "> Line 3" in content

    def test_dialogue_empty_history(self, output_manager):
        """Should handle empty dialogue history."""
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=[],
            company_name="Test",
            client_name="Иван"
        )
        assert result.exists()

    def test_dialogue_handles_unknown_role(self, output_manager):
        """Should handle unknown roles."""
        dialogue = [{"role": "system", "content": "System message", "phase": "discovery"}]
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=dialogue,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "**system:**" in content

    def test_dialogue_handles_unknown_phase(self, output_manager):
        """Should handle unknown phases."""
        dialogue = [{"role": "user", "content": "Test", "phase": "custom_phase"}]
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=dialogue,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        assert "CUSTOM_PHASE" in content

    def test_dialogue_uses_current_time_by_default(self, output_manager, sample_dialogue_history):
        """Should use current time when start_time not specified."""
        from datetime import timezone
        company_dir = output_manager.get_company_dir("Test")
        result = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Test",
            client_name="Иван"
        )
        content = result.read_text(encoding="utf-8")
        # Should contain today's UTC date (matches production code's timezone.utc)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert today in content


# ============================================================================
# _format_dialogue_md Tests
# ============================================================================

class TestFormatDialogueMd:
    """Tests for _format_dialogue_md internal method."""

    def test_format_basic_structure(self, output_manager):
        """Should create basic markdown structure."""
        result = output_manager._format_dialogue_md(
            dialogue_history=[],
            company_name="Test",
            client_name="Client",
            duration_seconds=60,
            start_time=datetime(2026, 2, 6, 12, 0)
        )
        assert "# Диалог: Test" in result
        assert "**Дата:**" in result
        assert "**Длительность:**" in result
        assert "**Сообщений:**" in result

    def test_format_phase_transition(self, output_manager):
        """Should add phase headers on transition."""
        dialogue = [
            {"role": "user", "content": "A", "phase": "discovery"},
            {"role": "user", "content": "B", "phase": "proposal"},
        ]
        result = output_manager._format_dialogue_md(
            dialogue_history=dialogue,
            company_name="Test",
            client_name="Client",
            duration_seconds=0,
            start_time=datetime.now()
        )
        # Should have both phase headers
        lines = result.split("\n")
        phase_headers = [l for l in lines if l.startswith("## ")]
        assert len(phase_headers) == 2


# ============================================================================
# _get_next_version Tests
# ============================================================================

class TestGetNextVersion:
    """Tests for _get_next_version internal method."""

    def test_returns_1_for_empty_dir(self, output_manager, temp_output_dir):
        """Should return 1 for empty directory."""
        date_dir = temp_output_dir / "2026-02-06"
        date_dir.mkdir()
        version = output_manager._get_next_version(date_dir, "test")
        assert version == 1

    def test_returns_1_for_nonexistent_dir(self, output_manager, temp_output_dir):
        """Should return 1 for non-existent directory."""
        date_dir = temp_output_dir / "nonexistent"
        version = output_manager._get_next_version(date_dir, "test")
        assert version == 1

    def test_increments_version(self, output_manager, temp_output_dir):
        """Should increment version when previous exists."""
        date_dir = temp_output_dir / "2026-02-06"
        date_dir.mkdir()
        (date_dir / "test_v1").mkdir()
        (date_dir / "test_v2").mkdir()

        version = output_manager._get_next_version(date_dir, "test")
        assert version == 3

    def test_handles_gaps_in_versions(self, output_manager, temp_output_dir):
        """Should use max+1 even with gaps."""
        date_dir = temp_output_dir / "2026-02-06"
        date_dir.mkdir()
        (date_dir / "test_v1").mkdir()
        (date_dir / "test_v5").mkdir()  # Gap in versions

        version = output_manager._get_next_version(date_dir, "test")
        assert version == 6

    def test_ignores_other_companies(self, output_manager, temp_output_dir):
        """Should only count matching company directories."""
        date_dir = temp_output_dir / "2026-02-06"
        date_dir.mkdir()
        (date_dir / "other_v1").mkdir()
        (date_dir / "other_v2").mkdir()
        (date_dir / "test_v1").mkdir()

        version = output_manager._get_next_version(date_dir, "test")
        assert version == 2

    def test_ignores_files(self, output_manager, temp_output_dir):
        """Should ignore files, only count directories."""
        date_dir = temp_output_dir / "2026-02-06"
        date_dir.mkdir()
        (date_dir / "test_v1").mkdir()
        (date_dir / "test_v2.txt").touch()  # File, not directory

        version = output_manager._get_next_version(date_dir, "test")
        assert version == 2

    def test_handles_similar_names(self, output_manager, temp_output_dir):
        """Should not match similar but different names."""
        date_dir = temp_output_dir / "2026-02-06"
        date_dir.mkdir()
        (date_dir / "test_company_v1").mkdir()  # Different slug
        (date_dir / "test_v1").mkdir()

        version = output_manager._get_next_version(date_dir, "test")
        assert version == 2


# ============================================================================
# _slugify Tests
# ============================================================================

class TestSlugify:
    """Tests for _slugify internal method."""

    def test_lowercase(self, output_manager):
        """Should convert to lowercase."""
        assert output_manager._slugify("TEST") == "test"

    def test_spaces_to_underscores(self, output_manager):
        """Should convert spaces to underscores."""
        assert output_manager._slugify("hello world") == "hello_world"

    def test_hyphens_to_underscores(self, output_manager):
        """Should convert hyphens to underscores."""
        assert output_manager._slugify("hello-world") == "hello_world"

    def test_removes_special_characters(self, output_manager):
        """Should remove special characters."""
        result = output_manager._slugify("Test & Co. (LLC)")
        assert "&" not in result
        assert "." not in result
        assert "(" not in result

    def test_cyrillic_transliteration(self, output_manager):
        """Should transliterate Cyrillic."""
        result = output_manager._slugify("Компания")
        assert result == "kompaniya"

    def test_cyrillic_complex(self, output_manager):
        """Should handle complex Cyrillic names."""
        result = output_manager._slugify("Салон красоты Glamour")
        assert "salon" in result
        assert "krasoty" in result
        assert "glamour" in result

    def test_mixed_cyrillic_latin(self, output_manager):
        """Should handle mixed Cyrillic and Latin."""
        result = output_manager._slugify("Компания Test")
        assert "kompaniya" in result
        assert "test" in result

    def test_removes_multiple_underscores(self, output_manager):
        """Should collapse multiple underscores."""
        result = output_manager._slugify("hello   world")
        assert "__" not in result
        assert result == "hello_world"

    def test_preserves_numbers(self, output_manager):
        """Should preserve numbers."""
        result = output_manager._slugify("Company123")
        assert "123" in result

    def test_max_length(self, output_manager):
        """Should limit slug length to 50 characters."""
        long_name = "A" * 100
        result = output_manager._slugify(long_name)
        assert len(result) <= 50

    def test_empty_string(self, output_manager):
        """Should return 'unnamed' for empty string."""
        result = output_manager._slugify("")
        assert result == "unnamed"

    def test_only_special_chars(self, output_manager):
        """Should return 'unnamed' for string with only special chars."""
        result = output_manager._slugify("!@#$%")
        assert result == "unnamed"

    def test_unicode_normalization(self, output_manager):
        """Should normalize Unicode characters."""
        # Test with composed vs decomposed Unicode
        result = output_manager._slugify("café")
        assert "caf" in result

    def test_specific_cyrillic_letters(self, output_manager):
        """Should correctly transliterate specific letters."""
        assert "zh" in output_manager._slugify("ж")
        assert "ch" in output_manager._slugify("ч")
        assert "sh" in output_manager._slugify("ш")
        assert "sch" in output_manager._slugify("щ")
        assert "yu" in output_manager._slugify("ю")
        assert "ya" in output_manager._slugify("я")

    def test_hard_soft_signs_removed(self, output_manager):
        """Should remove hard and soft signs."""
        # ъ and ь should be removed
        result = output_manager._slugify("объём")
        assert "ob" in result
        assert "em" in result


# ============================================================================
# Integration Tests
# ============================================================================

class TestOutputManagerIntegration:
    """Integration tests for OutputManager."""

    def test_full_workflow(self, output_manager, sample_dialogue_history, sample_anketa_json):
        """Should complete full save workflow."""
        # Create company directory
        company_dir = output_manager.get_company_dir(
            "Тестовая Компания",
            date=datetime(2026, 2, 6)
        )

        # Save anketa
        anketa_result = output_manager.save_anketa(
            company_dir,
            anketa_md="# Тест\n\nСодержимое",
            anketa_json=sample_anketa_json
        )

        # Save dialogue
        dialogue_path = output_manager.save_dialogue(
            company_dir,
            dialogue_history=sample_dialogue_history,
            company_name="Тестовая Компания",
            client_name="Иван Петров",
            duration_seconds=300,
            start_time=datetime(2026, 2, 6, 10, 0)
        )

        # Verify all files exist
        assert company_dir.exists()
        assert anketa_result["md"].exists()
        assert anketa_result["json"].exists()
        assert dialogue_path.exists()

        # Verify content
        assert "Тест" in anketa_result["md"].read_text(encoding="utf-8")
        json_content = json.loads(anketa_result["json"].read_text(encoding="utf-8"))
        assert json_content["company_name"] == "Test Company"
        dialogue_content = dialogue_path.read_text(encoding="utf-8")
        assert "Тестовая Компания" in dialogue_content

    def test_multiple_sessions_same_company(self, output_manager):
        """Should handle multiple sessions for same company."""
        date = datetime(2026, 2, 6)

        # First session
        dir1 = output_manager.get_company_dir("Test Company", date=date)
        output_manager.save_anketa(dir1, "Session 1", {"session": 1})

        # Second session
        dir2 = output_manager.get_company_dir("Test Company", date=date)
        output_manager.save_anketa(dir2, "Session 2", {"session": 2})

        # Verify different directories
        assert dir1 != dir2
        assert "_v1" in dir1.name
        assert "_v2" in dir2.name

        # Verify both have correct content
        assert "Session 1" in (dir1 / "anketa.md").read_text(encoding="utf-8")
        assert "Session 2" in (dir2 / "anketa.md").read_text(encoding="utf-8")

    def test_directory_structure(self, temp_output_dir):
        """Should create correct directory structure."""
        manager = OutputManager(base_dir=temp_output_dir)
        date = datetime(2026, 2, 6)

        company_dir = manager.get_company_dir("Test", date=date)
        manager.save_anketa(company_dir, "# Test", {})

        # Verify structure: output/2026-02-06/test_v1/anketa.md
        expected_structure = temp_output_dir / "2026-02-06"
        assert expected_structure.exists()
        assert (expected_structure / "test_v1").exists()
        assert (expected_structure / "test_v1" / "anketa.md").exists()
