"""
External editor handling for DocumentReviewer.

Supports:
- Auto-detection of system editor ($EDITOR, $VISUAL)
- Common editors: vim, nano, code, subl, etc.
- Timeout handling
- Cross-platform support
"""

import os
import sys
import subprocess
import tempfile
import time
import signal
from pathlib import Path
from typing import Optional, List, Tuple
from contextlib import contextmanager

import structlog

from .models import ReviewConfig, ReviewStatus

logger = structlog.get_logger()


class EditorError(Exception):
    """Error during editor operations."""
    pass


class EditorTimeoutError(EditorError):
    """Editor session timed out."""
    pass


class ExternalEditor:
    """Handles external editor interactions."""

    # Common editors with their typical arguments
    KNOWN_EDITORS = {
        "vim": [],
        "nvim": [],
        "nano": [],
        "emacs": [],
        "code": ["--wait"],      # VS Code needs --wait to block
        "subl": ["--wait"],      # Sublime Text
        "atom": ["--wait"],      # Atom
        "gedit": ["--wait"],     # GNOME Editor
        "notepad": [],           # Windows Notepad
        "notepad++": [],         # Notepad++
    }

    # Fallback editor chain
    FALLBACK_EDITORS = ["nano", "vim", "vi", "notepad"]

    def __init__(self, config: ReviewConfig):
        """
        Initialize editor handler.

        Args:
            config: Review configuration
        """
        self.config = config
        self.editor_cmd, self.editor_args = self._detect_editor()
        logger.info("Editor configured", editor=self.editor_cmd, args=self.editor_args)

    def _detect_editor(self) -> Tuple[str, List[str]]:
        """
        Detect the editor to use.

        Returns:
            Tuple of (editor_command, arguments)
        """
        # 1. Use explicitly configured editor
        if self.config.editor:
            editor = self.config.editor
            args = self.config.editor_args or self._get_editor_args(editor)
            return editor, args

        # 2. Check environment variables
        for env_var in ["EDITOR", "VISUAL"]:
            editor = os.environ.get(env_var)
            if editor:
                args = self._get_editor_args(editor)
                return editor, args

        # 3. Try fallback editors
        for editor in self.FALLBACK_EDITORS:
            if self._editor_exists(editor):
                args = self._get_editor_args(editor)
                return editor, args

        raise EditorError(
            "Не найден редактор. Установите переменную окружения $EDITOR "
            "или укажите редактор в конфигурации."
        )

    def _get_editor_args(self, editor: str) -> List[str]:
        """Get default arguments for known editor."""
        editor_name = Path(editor).stem.lower()
        return self.KNOWN_EDITORS.get(editor_name, [])

    def _editor_exists(self, editor: str) -> bool:
        """Check if editor exists in PATH."""
        try:
            subprocess.run(
                ["which", editor] if sys.platform != "win32" else ["where", editor],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @contextmanager
    def _timeout_handler(self, timeout_seconds: int):
        """Context manager for timeout handling on Unix."""
        if sys.platform == "win32":
            # Windows doesn't support SIGALRM
            yield
            return

        def handler(signum, frame):
            raise EditorTimeoutError(
                f"Время редактирования истекло ({timeout_seconds // 60} мин)"
            )

        old_handler = signal.signal(signal.SIGALRM, handler)
        signal.alarm(timeout_seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    def create_temp_file(self, content: str) -> Path:
        """
        Create temporary file with content.

        Args:
            content: File content

        Returns:
            Path to temporary file
        """
        fd, path = tempfile.mkstemp(
            prefix=self.config.temp_file_prefix,
            suffix=self.config.temp_file_suffix
        )
        try:
            with os.fdopen(fd, 'w', encoding=self.config.encoding) as f:
                f.write(content)
        except Exception:
            os.close(fd)
            raise

        logger.debug("Temp file created", path=path)
        return Path(path)

    def read_file(self, path: Path) -> str:
        """Read content from file."""
        with open(path, 'r', encoding=self.config.encoding) as f:
            return f.read()

    def open_editor(self, filepath: Path) -> Tuple[ReviewStatus, float]:
        """
        Open editor with file and wait for completion.

        Args:
            filepath: Path to file to edit

        Returns:
            Tuple of (status, duration_seconds)
        """
        cmd = [self.editor_cmd] + self.editor_args + [str(filepath)]
        timeout_seconds = self.config.timeout_minutes * 60

        logger.info("Opening editor", cmd=cmd, timeout_min=self.config.timeout_minutes)

        start_time = time.time()

        try:
            if sys.platform == "win32":
                # Windows: use subprocess timeout
                result = subprocess.run(
                    cmd,
                    timeout=timeout_seconds,
                    check=False
                )
            else:
                # Unix: use signal-based timeout
                with self._timeout_handler(timeout_seconds):
                    result = subprocess.run(cmd, check=False)

            duration = time.time() - start_time

            if result.returncode != 0:
                logger.warning("Editor exited with error", returncode=result.returncode)
                return ReviewStatus.ERROR, duration

            return ReviewStatus.COMPLETED, duration

        except EditorTimeoutError:
            duration = time.time() - start_time
            logger.warning("Editor timeout", duration=duration)
            return ReviewStatus.TIMEOUT, duration

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.warning("Editor timeout (subprocess)", duration=duration)
            return ReviewStatus.TIMEOUT, duration

        except Exception as e:
            duration = time.time() - start_time
            logger.error("Editor error", error=str(e))
            return ReviewStatus.ERROR, duration

    def cleanup(self, filepath: Path):
        """Remove temporary file."""
        try:
            if filepath.exists():
                filepath.unlink()
                logger.debug("Temp file removed", path=str(filepath))
        except Exception as e:
            logger.warning("Failed to remove temp file", path=str(filepath), error=str(e))


def detect_terminal_editor() -> Optional[str]:
    """
    Detect if running in terminal and return appropriate editor.

    Returns:
        Editor name or None if not in terminal
    """
    # Check if running in interactive terminal
    if not sys.stdin.isatty():
        return None

    # Return configured or default editor
    return os.environ.get("EDITOR", "nano")


def is_gui_available() -> bool:
    """Check if GUI is available for graphical editors."""
    if sys.platform == "darwin":
        return True  # macOS always has GUI

    if sys.platform == "win32":
        return True  # Windows always has GUI

    # Linux: check for DISPLAY
    return bool(os.environ.get("DISPLAY"))
