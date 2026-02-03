"""
Document parser for DocumentReviewer.

Handles:
- Adding/removing instructions block
- Readonly section protection
- Content extraction
- Diff generation
"""

import re
import difflib
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .models import ReviewConfig


@dataclass
class ParsedDocument:
    """Parsed document with separated sections."""
    instructions: Optional[str]
    content: str
    readonly_sections: List[Tuple[int, int, str]]  # (start_line, end_line, content)


class DocumentParser:
    """Parses and manipulates document content."""

    def __init__(self, config: ReviewConfig):
        """
        Initialize parser.

        Args:
            config: Review configuration
        """
        self.config = config

    def prepare_for_edit(self, content: str) -> str:
        """
        Prepare document for editing by adding instructions.

        Args:
            content: Original document content

        Returns:
            Content with instructions prepended
        """
        if not self.config.instructions:
            return content

        instructions_block = (
            self.config.instructions_prefix +
            self.config.instructions +
            self.config.instructions_suffix
        )

        return instructions_block + content

    def extract_after_edit(self, content: str) -> str:
        """
        Extract document content after editing, removing instructions.

        Args:
            content: Edited content with instructions

        Returns:
            Clean content without instructions
        """
        if not self.config.instructions:
            return content

        # Find and remove instructions block
        prefix = self.config.instructions_prefix
        suffix = self.config.instructions_suffix.rstrip('\n')

        # Try to find the instructions block
        if content.startswith(prefix):
            # Find the end of instructions block
            suffix_pos = content.find(suffix)
            if suffix_pos != -1:
                # Remove the instructions block
                content = content[suffix_pos + len(suffix):].lstrip('\n')

        return content

    def mark_readonly_sections(self, content: str) -> str:
        """
        Mark sections as readonly with visual indicators.

        Args:
            content: Document content

        Returns:
            Content with readonly markers
        """
        if not self.config.readonly_sections:
            return content

        lines = content.split('\n')
        result = []
        in_readonly = False
        readonly_pattern = None

        for i, line in enumerate(lines):
            # Check if this line starts a readonly section
            for pattern in self.config.readonly_sections:
                if re.match(pattern, line):
                    if not in_readonly:
                        result.append(self.config.readonly_marker)
                        in_readonly = True
                        readonly_pattern = pattern
                    break

            result.append(line)

            # Check if readonly section ends (empty line or new section)
            if in_readonly:
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if not next_line.strip() or (
                    next_line.startswith('#') and
                    not re.match(readonly_pattern, next_line)
                ):
                    result.append(self.config.readonly_marker)
                    in_readonly = False
                    readonly_pattern = None

        return '\n'.join(result)

    def validate_readonly_preserved(
        self,
        original: str,
        edited: str
    ) -> List[str]:
        """
        Validate that readonly sections weren't modified.

        Args:
            original: Original content
            edited: Edited content

        Returns:
            List of error messages for modified readonly sections
        """
        if not self.config.readonly_sections:
            return []

        errors = []
        original_sections = self._extract_readonly_sections(original)
        edited_sections = self._extract_readonly_sections(edited)

        for section_id, original_content in original_sections.items():
            edited_content = edited_sections.get(section_id)

            if edited_content is None:
                errors.append(f"Readonly секция '{section_id}' была удалена")
            elif edited_content != original_content:
                errors.append(f"Readonly секция '{section_id}' была изменена")

        return errors

    def _extract_readonly_sections(self, content: str) -> dict:
        """Extract readonly sections from content."""
        sections = {}
        lines = content.split('\n')
        current_section = None
        current_content = []

        for line in lines:
            # Check for section headers matching readonly patterns
            for pattern in self.config.readonly_sections:
                match = re.match(pattern, line)
                if match:
                    # Save previous section
                    if current_section:
                        sections[current_section] = '\n'.join(current_content)

                    # Start new section
                    current_section = line.strip()
                    current_content = [line]
                    break
            else:
                if current_section:
                    # Check if section ended
                    if line.startswith('#') or (not line.strip() and not current_content[-1].strip()):
                        sections[current_section] = '\n'.join(current_content)
                        current_section = None
                        current_content = []
                    else:
                        current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content)

        return sections

    def generate_diff(
        self,
        original: str,
        edited: str,
        context_lines: int = 3
    ) -> str:
        """
        Generate unified diff between original and edited content.

        Args:
            original: Original content
            edited: Edited content
            context_lines: Number of context lines

        Returns:
            Unified diff string
        """
        original_lines = original.splitlines(keepends=True)
        edited_lines = edited.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            edited_lines,
            fromfile='original',
            tofile='edited',
            n=context_lines
        )

        return ''.join(diff)

    def count_changes(self, original: str, edited: str) -> dict:
        """
        Count changes between original and edited content.

        Args:
            original: Original content
            edited: Edited content

        Returns:
            Dict with change counts
        """
        original_lines = original.splitlines()
        edited_lines = edited.splitlines()

        matcher = difflib.SequenceMatcher(None, original_lines, edited_lines)

        added = 0
        removed = 0
        modified = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'insert':
                added += j2 - j1
            elif tag == 'delete':
                removed += i2 - i1
            elif tag == 'replace':
                modified += max(i2 - i1, j2 - j1)

        return {
            'added': added,
            'removed': removed,
            'modified': modified,
            'total': added + removed + modified
        }


def strip_markdown_comments(content: str) -> str:
    """
    Remove HTML comments from markdown content.

    Args:
        content: Markdown content

    Returns:
        Content without HTML comments
    """
    # Remove single-line comments
    content = re.sub(r'<!--.*?-->', '', content)

    # Remove multi-line comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    return content


def extract_markdown_sections(content: str) -> dict:
    """
    Extract sections from markdown by headers.

    Args:
        content: Markdown content

    Returns:
        Dict mapping header text to section content
    """
    sections = {}
    current_header = None
    current_content = []

    for line in content.split('\n'):
        if line.startswith('#'):
            # Save previous section
            if current_header:
                sections[current_header] = '\n'.join(current_content)

            # Start new section
            current_header = line.lstrip('#').strip()
            current_content = []
        else:
            current_content.append(line)

    # Save last section
    if current_header:
        sections[current_header] = '\n'.join(current_content)

    return sections
