"""
Centralized logging configuration for Hanc.AI.

Separates logs into multiple files by direction/component:

    logs/
    ├── server.log          # HTTP API requests
    ├── agent.log           # Agent lifecycle (startup, steps 1-5, ready)
    ├── livekit.log         # LiveKit events (rooms, tokens, connections)
    ├── dialogue.log        # Dialogue messages (who said what, when)
    ├── anketa.log          # Anketa extraction, updates, generation
    ├── azure.log           # Azure OpenAI Realtime (WSS, model)
    ├── session.log         # Session lifecycle (create, status, finalize)
    ├── deepseek.log        # DeepSeek LLM API calls, retries, errors
    ├── notifications.log   # Email, webhooks
    ├── output.log          # File saving (OutputManager)
    ├── knowledge.log       # Industry knowledge base (loader, matcher, manager)
    ├── documents.log       # Document parsing and analysis
    ├── config.log          # Configuration loading (synonyms, etc.)
    ├── storage.log         # Storage layer (Redis, PostgreSQL)
    └── errors.log          # ALL errors from ALL components (ERROR+)

Usage:
    from src.logging_config import setup_logging
    setup_logging("server")   # activates: server, livekit, session, notifications
    setup_logging("agent")    # activates: agent, livekit, dialogue, anketa, azure,
                              #            session, deepseek, output
"""

import logging
import sys
from pathlib import Path

import structlog

LOGS_DIR = Path(__file__).parent.parent / "logs"

# ---------------------------------------------------------------------------
# Category → file mapping
# ---------------------------------------------------------------------------

LOG_CATEGORIES = {
    "server": "server.log",
    "agent": "agent.log",
    "livekit": "livekit.log",
    "dialogue": "dialogue.log",
    "anketa": "anketa.log",
    "azure": "azure.log",
    "session": "session.log",
    "deepseek": "deepseek.log",
    "notifications": "notifications.log",
    "output": "output.log",
    "knowledge": "knowledge.log",
    "documents": "documents.log",
    "config": "config.log",
    "storage": "storage.log",
}

# Which categories each process activates
PROCESS_CATEGORIES = {
    "server": ["server", "livekit", "session", "notifications", "config", "storage"],
    "agent": [
        "agent", "livekit", "dialogue", "anketa",
        "azure", "session", "deepseek", "output",
        "knowledge", "documents", "config", "storage",
    ],
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_initialized = False


def setup_logging(component: str = "app", level: str = "DEBUG") -> None:
    """Configure logging with per-category file handlers.

    Args:
        component: Process name ("server" or "agent").
                   Determines which log files are created.
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR).
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.DEBUG)

    # -----------------------------------------------------------------------
    # Root logger: console + errors.log
    # -----------------------------------------------------------------------
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_h = logging.StreamHandler(sys.stdout)
    console_h.setLevel(log_level)
    console_h.setFormatter(fmt)
    root.addHandler(console_h)

    # errors.log — catches ERROR+ from every logger via propagation
    errors_h = logging.FileHandler(str(LOGS_DIR / "errors.log"), encoding="utf-8")
    errors_h.setLevel(logging.ERROR)
    errors_h.setFormatter(fmt)
    root.addHandler(errors_h)

    # -----------------------------------------------------------------------
    # Per-category loggers with dedicated file handlers
    # -----------------------------------------------------------------------
    categories = PROCESS_CATEGORIES.get(component, list(LOG_CATEGORIES.keys()))

    for category in categories:
        log_file = LOG_CATEGORIES.get(category)
        if not log_file:
            continue

        cat_logger = logging.getLogger(category)
        cat_logger.setLevel(log_level)
        # Don't add duplicate handlers on re-import
        if not cat_logger.handlers:
            file_h = logging.FileHandler(
                str(LOGS_DIR / log_file), encoding="utf-8",
            )
            file_h.setLevel(log_level)
            file_h.setFormatter(fmt)
            cat_logger.addHandler(file_h)
        # Propagate to root so console + errors.log still work
        cat_logger.propagate = True

    # -----------------------------------------------------------------------
    # structlog → stdlib bridge
    # -----------------------------------------------------------------------
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    init_logger = structlog.get_logger(component)
    init_logger.info(
        "logging_initialized",
        component=component,
        categories=categories,
        level=level,
    )
