"""Error-only logging to separate error log files."""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional


class ErrorLogManager:
    """Manages error-only logging with separate error log files."""

    def __init__(self, base_log_dir: Optional[Path] = None):
        """Initialize error log manager.

        Args:
            base_log_dir: Base directory for log files (default: ~/.capybara/logs)
        """
        if base_log_dir is None:
            self.base_log_dir = Path.home() / ".capybara" / "logs"
        else:
            self.base_log_dir = base_log_dir

        # Error log directory
        self.error_log_dir = self.base_log_dir / "errors"
        self.error_log_dir.mkdir(parents=True, exist_ok=True)

    def get_error_logger(self) -> logging.Logger:
        """Get error-only logger that writes to separate error.log file.

        Returns:
            Logger configured for errors only
        """
        error_logger = logging.getLogger("capybara.errors")

        # Only configure once
        if error_logger.handlers:
            return error_logger

        error_logger.setLevel(logging.ERROR)

        # Error log file: errors/capybara_errors_YYYYMMDD.log
        error_log = self.error_log_dir / f"capybara_errors_{datetime.now():%Y%m%d}.log"

        error_handler = logging.FileHandler(error_log, encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s\n"
            "%(pathname)s:%(lineno)d\n"
            "%(message)s\n"
            "---",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        error_handler.setFormatter(error_formatter)
        error_logger.addHandler(error_handler)

        return error_logger


# Global error log manager instance
_error_manager = None


def get_error_log_manager() -> ErrorLogManager:
    """Get global error log manager instance.

    Returns:
        ErrorLogManager instance
    """
    global _error_manager
    if _error_manager is None:
        _error_manager = ErrorLogManager()
    return _error_manager


def log_error(
    error: Exception,
    context: str,
    session_id: Optional[str] = None,
    agent_mode: Optional[str] = None
):
    """Log error to error-only log file.

    Args:
        error: Exception object
        context: Context description (e.g., 'tool_execution', 'agent_run')
        session_id: Optional session ID
        agent_mode: Optional agent mode
    """
    error_logger = get_error_log_manager().get_error_logger()

    session_info = f" [session={session_id[:8]}]" if session_id else ""
    agent_info = f" [agent={agent_mode}]" if agent_mode else ""

    error_logger.error(
        f"{context}{session_info}{agent_info}: {type(error).__name__}: {error}",
        exc_info=True
    )
