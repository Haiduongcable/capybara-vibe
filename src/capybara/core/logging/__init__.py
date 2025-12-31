"""Enhanced logging configuration for CapybaraVibeCoding.

Features:
- Session-based log files (one per chat session)
- Agent type tracking (parent vs child)
- Delegation event logging
- Error-only .log files
- Structured logging with context
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from .session_logger import SessionLoggerAdapter, SessionLogManager, get_session_log_manager
from .error_logger import ErrorLogManager, get_error_log_manager, log_error
from .event_logger import log_agent_behavior, log_delegation, log_tool_execution, log_state_change
from .api_logger import APILogger

__all__ = [
    # Session logging
    'SessionLoggerAdapter',
    'SessionLogManager',
    'get_session_log_manager',
    # Error logging
    'ErrorLogManager',
    'get_error_log_manager',
    'log_error',
    # Event logging
    'log_agent_behavior',
    'log_delegation',
    'log_tool_execution',
    'log_state_change',
    # API logging
    'APILogger',
    # Base setup
    'setup_logging',
    'get_logger',
]


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    console_output: bool = False,
) -> logging.Logger:
    """Setup logging with file and optional console output.

    This function sets up the base logging infrastructure. For session-specific
    logging, use SessionLogManager.create_session_logger() instead.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files (default: ~/.capybara/logs)
        console_output: Whether to also log to console

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("capybara")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create log directory
    if log_dir is None:
        log_dir = Path.home() / ".capybara" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log file with timestamp
    log_file = log_dir / f"capybara_{datetime.now():%Y%m%d}.log"

    # File handler - detailed format
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - minimal format (only if requested)
    if console_output:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("litellm").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    logger.info(f"Logging initialized - log file: {log_file}")
    return logger


def get_logger(name: str = "capybara") -> logging.Logger:
    """Get logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
