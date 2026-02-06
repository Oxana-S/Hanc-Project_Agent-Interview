"""
Tests for src/config/prompt_loader.py

Comprehensive tests for PromptLoader class and helper functions.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
import tempfile
import os

from src.config.prompt_loader import (
    PromptLoader,
    get_prompt_loader,
    get_prompt,
    render_prompt,
    _default_loader
)


class TestPromptLoaderInit:
    """Tests for PromptLoader initialization."""

    def test_init_with_default_path(self):
        """Test initialization with default path."""
        loader = PromptLoader()
        assert loader.base_path.exists()
        assert loader.base_path.name == "prompts"
        assert loader._cache == {}

    def test_init_with_custom_path(self, tmp_path):
        """Test initialization with custom path."""
        loader = PromptLoader(base_path=tmp_path)
        assert loader.base_path == tmp_path
        assert loader._cache == {}

    def test_init_converts_string_to_path(self, tmp_path):
        """Test that string path is converted to Path object."""
        loader = PromptLoader(base_path=str(tmp_path))
        assert isinstance(loader.base_path, Path)


class TestPromptLoaderGet:
    """Tests for PromptLoader.get() method."""

    @pytest.fixture
    def loader_with_test_file(self, tmp_path):
        """Create a loader with a test YAML file."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        test_file = prompts_dir / "test.yaml"
        test_file.write_text("""
meta:
  version: "1.0"
system_prompt: |
  You are a helpful assistant.
user_prompt_template: |
  Hello, {{name}}!
nested:
  deep:
    value: "nested_value"
""")
        return PromptLoader(base_path=prompts_dir)

    def test_get_entire_file(self, loader_with_test_file):
        """Test getting entire file contents."""
        data = loader_with_test_file.get("test")
        assert isinstance(data, dict)
        assert "meta" in data
        assert "system_prompt" in data

    def test_get_specific_key(self, loader_with_test_file):
        """Test getting specific key from file."""
        result = loader_with_test_file.get("test", "system_prompt")
        assert "helpful assistant" in result

    def test_get_nested_key_with_dot_notation(self, loader_with_test_file):
        """Test getting nested key using dot notation."""
        result = loader_with_test_file.get("test", "nested.deep.value")
        assert result == "nested_value"

    def test_get_meta_version(self, loader_with_test_file):
        """Test getting nested meta version."""
        result = loader_with_test_file.get("test", "meta.version")
        assert result == "1.0"

    def test_get_nonexistent_key_raises_error(self, loader_with_test_file):
        """Test that nonexistent key raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            loader_with_test_file.get("test", "nonexistent_key")
        assert "nonexistent_key" in str(exc_info.value)

    def test_get_nonexistent_nested_key_raises_error(self, loader_with_test_file):
        """Test that nonexistent nested key raises KeyError."""
        with pytest.raises(KeyError):
            loader_with_test_file.get("test", "meta.nonexistent")

    def test_get_nonexistent_file_raises_error(self, loader_with_test_file):
        """Test that nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            loader_with_test_file.get("nonexistent_file")


class TestPromptLoaderRender:
    """Tests for PromptLoader.render() method."""

    @pytest.fixture
    def loader_with_templates(self, tmp_path):
        """Create a loader with template files."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        test_file = prompts_dir / "templates.yaml"
        test_file.write_text("""
simple: "Hello, {{name}}!"
multiple: "{{greeting}}, {{name}}! Welcome to {{place}}."
with_if: |
  Hello!
  {{#if show_extra}}
  This is extra content.
  {{/if}}
  Goodbye!
with_each: |
  Items:
  {{#each items}}
  - {{this}}
  {{/each}}
with_each_dict: |
  Users:
  {{#each users}}
  {{@index}}. {{this.name}} ({{this.role}})
  {{/each}}
non_string_template:
  nested: "value"
""")
        return PromptLoader(base_path=prompts_dir)

    def test_render_simple_substitution(self, loader_with_templates):
        """Test simple variable substitution."""
        result = loader_with_templates.render("templates", "simple", name="World")
        assert result == "Hello, World!"

    def test_render_multiple_variables(self, loader_with_templates):
        """Test multiple variable substitution."""
        result = loader_with_templates.render(
            "templates", "multiple",
            greeting="Hi",
            name="Alice",
            place="Wonderland"
        )
        assert result == "Hi, Alice! Welcome to Wonderland."

    def test_render_missing_variable_removed(self, loader_with_templates):
        """Test that missing variables are removed."""
        result = loader_with_templates.render("templates", "simple")
        assert result == "Hello, !"
        assert "{{name}}" not in result

    def test_render_none_value_becomes_empty(self, loader_with_templates):
        """Test that None value becomes empty string."""
        result = loader_with_templates.render("templates", "simple", name=None)
        assert result == "Hello, !"

    def test_render_conditional_true(self, loader_with_templates):
        """Test conditional rendering when condition is true."""
        result = loader_with_templates.render("templates", "with_if", show_extra=True)
        assert "This is extra content." in result

    def test_render_conditional_false(self, loader_with_templates):
        """Test conditional rendering when condition is false."""
        result = loader_with_templates.render("templates", "with_if", show_extra=False)
        assert "This is extra content." not in result

    def test_render_conditional_missing(self, loader_with_templates):
        """Test conditional rendering when condition variable is missing."""
        result = loader_with_templates.render("templates", "with_if")
        assert "This is extra content." not in result

    def test_render_each_with_list(self, loader_with_templates):
        """Test each loop with simple list."""
        result = loader_with_templates.render(
            "templates", "with_each",
            items=["apple", "banana", "cherry"]
        )
        assert "- apple" in result
        assert "- banana" in result
        assert "- cherry" in result

    def test_render_each_with_dict_list(self, loader_with_templates):
        """Test each loop with list of dicts."""
        result = loader_with_templates.render(
            "templates", "with_each_dict",
            users=[
                {"name": "Alice", "role": "admin"},
                {"name": "Bob", "role": "user"}
            ]
        )
        assert "1. Alice (admin)" in result
        assert "2. Bob (user)" in result

    def test_render_each_with_empty_list(self, loader_with_templates):
        """Test each loop with empty list."""
        result = loader_with_templates.render("templates", "with_each", items=[])
        assert "Items:" in result
        # Should not have any list items

    def test_render_each_with_non_list(self, loader_with_templates):
        """Test each loop with non-list value."""
        result = loader_with_templates.render("templates", "with_each", items="not a list")
        assert "Items:" in result

    def test_render_non_string_raises_error(self, loader_with_templates):
        """Test that rendering non-string template raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            loader_with_templates.render("templates", "non_string_template")
        assert "Expected string template" in str(exc_info.value)


class TestPromptLoaderCache:
    """Tests for PromptLoader caching functionality."""

    @pytest.fixture
    def loader_with_file(self, tmp_path):
        """Create a loader with a test file."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        test_file = prompts_dir / "cached.yaml"
        test_file.write_text("value: original")
        return PromptLoader(base_path=prompts_dir), test_file

    def test_file_is_cached(self, loader_with_file):
        """Test that file is cached after first load."""
        loader, _ = loader_with_file

        # First load
        loader.get("cached")
        assert "cached" in loader._cache

    def test_cached_file_not_reloaded(self, loader_with_file):
        """Test that cached file is not reloaded."""
        loader, test_file = loader_with_file

        # First load
        result1 = loader.get("cached", "value")
        assert result1 == "original"

        # Modify file
        test_file.write_text("value: modified")

        # Second load should return cached value
        result2 = loader.get("cached", "value")
        assert result2 == "original"

    def test_clear_cache(self, loader_with_file):
        """Test clear_cache method."""
        loader, test_file = loader_with_file

        # Load and cache
        loader.get("cached")
        assert "cached" in loader._cache

        # Clear cache
        loader.clear_cache()
        assert loader._cache == {}

    def test_reload_file(self, loader_with_file):
        """Test reload method."""
        loader, test_file = loader_with_file

        # First load
        result1 = loader.get("cached", "value")
        assert result1 == "original"

        # Modify file
        test_file.write_text("value: modified")

        # Reload
        loader.reload("cached")
        result2 = loader.get("cached", "value")
        assert result2 == "modified"

    def test_reload_uncached_file(self, loader_with_file):
        """Test reload on uncached file."""
        loader, _ = loader_with_file

        # Reload without prior load should work
        data = loader.reload("cached")
        assert "value" in data


class TestPromptLoaderProcessConditionals:
    """Tests for _process_conditionals method."""

    def test_simple_if_true(self):
        """Test simple if condition when true."""
        loader = PromptLoader()
        template = "Start {{#if show}}SHOWN{{/if}} End"
        result = loader._process_conditionals(template, {"show": True})
        assert result == "Start SHOWN End"

    def test_simple_if_false(self):
        """Test simple if condition when false."""
        loader = PromptLoader()
        template = "Start {{#if show}}SHOWN{{/if}} End"
        result = loader._process_conditionals(template, {"show": False})
        assert result == "Start  End"

    def test_if_with_truthy_string(self):
        """Test if condition with truthy string value."""
        loader = PromptLoader()
        template = "{{#if name}}Hello {{name}}{{/if}}"
        result = loader._process_conditionals(template, {"name": "Alice"})
        assert "Hello" in result

    def test_if_with_empty_string(self):
        """Test if condition with empty string (falsy)."""
        loader = PromptLoader()
        template = "{{#if name}}Hello{{/if}}"
        result = loader._process_conditionals(template, {"name": ""})
        assert result == ""

    def test_multiple_if_blocks(self):
        """Test multiple if blocks."""
        loader = PromptLoader()
        template = "{{#if a}}A{{/if}} {{#if b}}B{{/if}}"
        result = loader._process_conditionals(template, {"a": True, "b": False})
        assert result == "A "

    def test_if_with_multiline_content(self):
        """Test if with multiline content."""
        loader = PromptLoader()
        template = """{{#if show}}
Line 1
Line 2
{{/if}}"""
        result = loader._process_conditionals(template, {"show": True})
        assert "Line 1" in result
        assert "Line 2" in result


class TestPromptLoaderProcessLoops:
    """Tests for _process_loops method."""

    def test_each_with_simple_list(self):
        """Test each with simple string list."""
        loader = PromptLoader()
        template = "{{#each items}}{{this}},{{/each}}"
        result = loader._process_loops(template, {"items": ["a", "b", "c"]})
        assert result == "a,b,c,"

    def test_each_with_index(self):
        """Test each with @index."""
        loader = PromptLoader()
        template = "{{#each items}}{{@index}}.{{this}} {{/each}}"
        result = loader._process_loops(template, {"items": ["a", "b"]})
        assert "1.a" in result
        assert "2.b" in result

    def test_each_with_dict_items(self):
        """Test each with dict items."""
        loader = PromptLoader()
        template = "{{#each users}}{{this.name}}:{{this.age}} {{/each}}"
        result = loader._process_loops(template, {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ]
        })
        assert "Alice:30" in result
        assert "Bob:25" in result

    def test_each_with_dict_shorthand(self):
        """Test each with dict shorthand (without 'this.')."""
        loader = PromptLoader()
        template = "{{#each users}}{{name}} {{/each}}"
        result = loader._process_loops(template, {
            "users": [{"name": "Alice"}, {"name": "Bob"}]
        })
        assert "Alice" in result
        assert "Bob" in result

    def test_each_with_empty_list(self):
        """Test each with empty list."""
        loader = PromptLoader()
        template = "Items: {{#each items}}{{this}}{{/each}}"
        result = loader._process_loops(template, {"items": []})
        assert result == "Items: "

    def test_each_with_missing_variable(self):
        """Test each with missing variable."""
        loader = PromptLoader()
        template = "{{#each items}}{{this}}{{/each}}"
        result = loader._process_loops(template, {})
        assert result == ""

    def test_each_with_non_list_value(self):
        """Test each with non-list value."""
        loader = PromptLoader()
        template = "{{#each items}}{{this}}{{/each}}"
        result = loader._process_loops(template, {"items": "string"})
        assert result == ""


class TestGlobalFunctions:
    """Tests for global helper functions."""

    def test_get_prompt_loader_returns_loader(self):
        """Test get_prompt_loader returns a PromptLoader instance."""
        loader = get_prompt_loader()
        assert isinstance(loader, PromptLoader)

    def test_get_prompt_loader_returns_same_instance(self):
        """Test get_prompt_loader returns singleton."""
        loader1 = get_prompt_loader()
        loader2 = get_prompt_loader()
        assert loader1 is loader2

    def test_get_prompt_loads_real_file(self):
        """Test get_prompt loads actual prompt file."""
        # This tests with real prompts directory
        result = get_prompt("voice/consultant", "system_prompt")
        assert isinstance(result, str)
        assert len(result) > 50  # Should be substantial content

    def test_get_prompt_entire_file(self):
        """Test get_prompt returns entire file when no key."""
        result = get_prompt("voice/consultant")
        assert isinstance(result, dict)
        assert "system_prompt" in result

    def test_render_prompt_substitutes_variables(self):
        """Test render_prompt with variable substitution."""
        result = render_prompt(
            "anketa/expert", "user_prompt_template",
            company_name="TestCompany",
            industry="IT",
            agent_purpose="support"
        )
        assert "TestCompany" in result
        assert "IT" in result


class TestRealPromptFiles:
    """Integration tests with real prompt files."""

    def test_voice_consultant_prompt_exists(self):
        """Test voice/consultant.yaml exists and has expected structure."""
        data = get_prompt("voice/consultant")
        assert "system_prompt" in data

    def test_voice_review_prompt_exists(self):
        """Test voice/review.yaml exists and has expected structure."""
        data = get_prompt("voice/review")
        assert "system_prompt" in data

    def test_llm_analyze_answer_prompt_exists(self):
        """Test llm/analyze_answer.yaml exists."""
        data = get_prompt("llm/analyze_answer")
        assert "system_prompt" in data
        assert "user_prompt_template" in data

    def test_llm_complete_anketa_prompt_exists(self):
        """Test llm/complete_anketa.yaml exists."""
        data = get_prompt("llm/complete_anketa")
        assert "system_prompt" in data

    def test_llm_generation_prompt_exists(self):
        """Test llm/generation.yaml exists."""
        data = get_prompt("llm/generation")
        assert "dialogues" in data or "restrictions" in data

    def test_anketa_extract_prompt_exists(self):
        """Test anketa/extract.yaml exists."""
        data = get_prompt("anketa/extract")
        assert "system_prompt" in data

    def test_anketa_expert_prompt_exists(self):
        """Test anketa/expert.yaml exists."""
        data = get_prompt("anketa/expert")
        assert "system_prompt" in data
        assert "user_prompt_template" in data

    def test_consultant_discovery_prompt_exists(self):
        """Test consultant/discovery.yaml exists."""
        data = get_prompt("consultant/discovery")
        assert "system_prompt" in data
