"""Session-based logging with unique log files per session."""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional


class SessionLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds session and agent context to all log messages."""

    def process(self, msg, kwargs):
        """Add session and agent context to log message."""
        extra = self.extra or {}
        session_id = str(extra.get('session_id', 'unknown'))
        agent_mode = str(extra.get('agent_mode', 'unknown'))

        # Format: [parent|child:session_id] message
        prefix = f"[{agent_mode}:{session_id[:8]}]"
        return f"{prefix} {msg}", kwargs


class SessionLogManager:
    """Manages session-based logging with separate log files per session."""

    def __init__(self, base_log_dir: Optional[Path] = None):
        """Initialize session log manager.

        Args:
            base_log_dir: Base directory for log files (default: ~/.capybara/logs)
        """
        if base_log_dir is None:
            self.base_log_dir = Path.home() / ".capybara" / "logs"
        else:
            self.base_log_dir = base_log_dir

        self.base_log_dir.mkdir(parents=True, exist_ok=True)

        # Session directory structure: logs/sessions/YYYYMMDD/
        self.session_log_dir = self.base_log_dir / "sessions" / f"{datetime.now():%Y%m%d}"
        self.session_log_dir.mkdir(parents=True, exist_ok=True)

        # Track active session handlers
        self._session_handlers: dict[str, tuple[logging.FileHandler, logging.FileHandler]] = {}

    def create_session_logger(
        self,
        session_id: str,
        agent_mode: str = "parent",
        log_level: str = "INFO",
        parent_session_id: Optional[str] = None
    ) -> SessionLoggerAdapter:
        """Create a session-specific logger with its own log file.

        Args:
            session_id: Unique session identifier
            agent_mode: Agent type ('parent' or 'child')
            log_level: Logging level
            parent_session_id: If provided (for child agents), write to parent's log file instead

        Returns:
            SessionLoggerAdapter with session context
        """
        # Use parent_session_id for log file if provided (child agents)
        log_session_id = parent_session_id if parent_session_id else session_id

        # Create base logger
        logger_name = f"capybara.session.{session_id}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, log_level.upper()))

        # Prevent duplicate handlers
        if session_id in self._session_handlers:
            # Return existing adapter
            return SessionLoggerAdapter(
                logger,
                {'session_id': session_id, 'agent_mode': agent_mode}
            )

        # Create session log file: sessions/YYYYMMDD/session_{log_session_id[:8]}.log
        # Child agents will write to parent's log file when parent_session_id is provided
        log_file = self.session_log_dir / f"session_{log_session_id[:8]}.log"

        # File handler - detailed format
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Also add to main daily log for aggregation
        daily_log = self.base_log_dir / f"capybara_{datetime.now():%Y%m%d}.log"
        daily_handler = logging.FileHandler(daily_log, encoding="utf-8")
        daily_handler.setLevel(logging.INFO)
        daily_handler.setFormatter(file_formatter)
        logger.addHandler(daily_handler)

        # Store handler reference
        self._session_handlers[session_id] = (file_handler, daily_handler)

        # Create adapter with session context
        adapter = SessionLoggerAdapter(
            logger,
            {'session_id': session_id, 'agent_mode': agent_mode}
        )

        adapter.info(f"Session logger initialized (mode={agent_mode})")
        return adapter

    def close_session_logger(self, session_id: str):
        """Close and cleanup session logger handlers.

        Args:
            session_id: Session ID to close
        """
        if session_id not in self._session_handlers:
            return

        logger_name = f"capybara.session.{session_id}"
        logger = logging.getLogger(logger_name)

        # Remove and close handlers
        file_handler, daily_handler = self._session_handlers[session_id]
        logger.removeHandler(file_handler)
        logger.removeHandler(daily_handler)
        file_handler.close()
        daily_handler.close()

        del self._session_handlers[session_id]


# Global session log manager instance
_session_manager = None


def get_session_log_manager() -> SessionLogManager:
    """Get global session log manager instance.

    Returns:
        SessionLogManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionLogManager()
    return _session_manager
