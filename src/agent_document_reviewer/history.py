"""
Version history management for DocumentReviewer.

Provides:
- In-memory version storage
- File-based persistence
- Version comparison
- Rollback capability
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from collections import deque

import structlog

from .models import DocumentVersion, ReviewConfig

logger = structlog.get_logger()


class VersionHistory:
    """
    Manages document version history.

    Supports both in-memory and file-based persistence.
    """

    def __init__(
        self,
        config: ReviewConfig,
        document_id: Optional[str] = None,
        storage_dir: Optional[str] = None
    ):
        """
        Initialize version history.

        Args:
            config: Review configuration
            document_id: Unique document identifier
            storage_dir: Directory for persisting history
        """
        self.config = config
        self.document_id = document_id or "default"
        self.storage_dir = Path(storage_dir) if storage_dir else None

        # Use deque for efficient bounded storage
        self._versions: deque = deque(maxlen=config.max_history_versions)

        # Load existing history if available
        if self.storage_dir:
            self._load_history()

    @property
    def current_version(self) -> int:
        """Get current version number."""
        if not self._versions:
            return 0
        return self._versions[-1].version

    @property
    def versions(self) -> List[DocumentVersion]:
        """Get all versions as list."""
        return list(self._versions)

    def add_version(
        self,
        content: str,
        author: str = "user",
        comment: Optional[str] = None
    ) -> DocumentVersion:
        """
        Add new version to history.

        Args:
            content: Document content
            author: Who made the change
            comment: Optional comment about changes

        Returns:
            Created DocumentVersion
        """
        version = DocumentVersion(
            version=self.current_version + 1,
            content=content,
            created_at=datetime.now(),
            author=author,
            comment=comment
        )

        self._versions.append(version)

        logger.info(
            "Version added",
            document_id=self.document_id,
            version=version.version,
            author=author
        )

        # Persist if storage configured
        if self.storage_dir:
            self._save_history()

        return version

    def get_version(self, version_num: int) -> Optional[DocumentVersion]:
        """
        Get specific version.

        Args:
            version_num: Version number to retrieve

        Returns:
            DocumentVersion or None if not found
        """
        for v in self._versions:
            if v.version == version_num:
                return v
        return None

    def get_latest(self) -> Optional[DocumentVersion]:
        """Get most recent version."""
        if not self._versions:
            return None
        return self._versions[-1]

    def get_previous(self, version_num: Optional[int] = None) -> Optional[DocumentVersion]:
        """
        Get version before specified version.

        Args:
            version_num: Reference version (default: current)

        Returns:
            Previous version or None
        """
        if not self._versions:
            return None

        if version_num is None:
            version_num = self.current_version

        for i, v in enumerate(self._versions):
            if v.version == version_num and i > 0:
                return self._versions[i - 1]

        return None

    def compare_versions(
        self,
        version1: int,
        version2: int
    ) -> Optional[Dict[str, Any]]:
        """
        Compare two versions.

        Args:
            version1: First version number
            version2: Second version number

        Returns:
            Comparison result or None if versions not found
        """
        v1 = self.get_version(version1)
        v2 = self.get_version(version2)

        if not v1 or not v2:
            return None

        lines1 = v1.content.splitlines()
        lines2 = v2.content.splitlines()

        return {
            'version1': version1,
            'version2': version2,
            'lines_v1': len(lines1),
            'lines_v2': len(lines2),
            'lines_diff': len(lines2) - len(lines1),
            'time_diff_seconds': (v2.created_at - v1.created_at).total_seconds()
        }

    def rollback_to(self, version_num: int) -> Optional[DocumentVersion]:
        """
        Rollback to specific version (creates new version with old content).

        Args:
            version_num: Version to rollback to

        Returns:
            New version with rolled back content
        """
        target = self.get_version(version_num)
        if not target:
            logger.warning("Rollback target not found", version=version_num)
            return None

        return self.add_version(
            content=target.content,
            author="system",
            comment=f"Rollback to version {version_num}"
        )

    def clear(self):
        """Clear all version history."""
        self._versions.clear()
        logger.info("History cleared", document_id=self.document_id)

        if self.storage_dir:
            self._delete_history_file()

    def _get_history_path(self) -> Path:
        """Get path to history file."""
        return self.storage_dir / f"{self.document_id}_history.json"

    def _save_history(self):
        """Save history to file."""
        if not self.storage_dir:
            return

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        filepath = self._get_history_path()

        data = {
            'document_id': self.document_id,
            'versions': [v.to_dict() for v in self._versions]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.debug("History saved", path=str(filepath))

    def _load_history(self):
        """Load history from file."""
        if not self.storage_dir:
            return

        filepath = self._get_history_path()
        if not filepath.exists():
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for v_data in data.get('versions', []):
                version = DocumentVersion.from_dict(v_data)
                self._versions.append(version)

            logger.debug(
                "History loaded",
                path=str(filepath),
                versions=len(self._versions)
            )

        except Exception as e:
            logger.warning("Failed to load history", path=str(filepath), error=str(e))

    def _delete_history_file(self):
        """Delete history file."""
        if not self.storage_dir:
            return

        filepath = self._get_history_path()
        if filepath.exists():
            filepath.unlink()
            logger.debug("History file deleted", path=str(filepath))


class InMemoryHistory(VersionHistory):
    """Version history without persistence."""

    def __init__(self, config: ReviewConfig, document_id: Optional[str] = None):
        super().__init__(config, document_id, storage_dir=None)


def create_history(
    config: ReviewConfig,
    document_id: Optional[str] = None,
    persist: bool = False,
    storage_dir: str = "output/history"
) -> VersionHistory:
    """
    Factory function to create appropriate history instance.

    Args:
        config: Review configuration
        document_id: Document identifier
        persist: Whether to persist history to disk
        storage_dir: Directory for persistence

    Returns:
        VersionHistory instance
    """
    if persist and config.enable_history:
        return VersionHistory(config, document_id, storage_dir)
    elif config.enable_history:
        return InMemoryHistory(config, document_id)
    else:
        # Disabled history - return minimal instance
        disabled_config = ReviewConfig(
            enable_history=True,
            max_history_versions=1
        )
        return InMemoryHistory(disabled_config, document_id)
