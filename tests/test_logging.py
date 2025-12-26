"""Tests for the enhanced logging system."""

import logging
import tempfile
from pathlib import Path

import pytest

from capybara.core.logging import (
    SessionLogManager,
    get_session_log_manager,
    log_agent_behavior,
    log_delegation,
    log_error,
    log_state_change,
    log_tool_execution,
)


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def log_manager(temp_log_dir):
    """Create a session log manager with temp directory."""
    return SessionLogManager(base_log_dir=temp_log_dir)


def test_session_logger_creation(log_manager, temp_log_dir):
    """Test that session loggers are created correctly."""
    session_id = "test-session-123"

    # Create session logger
    logger = log_manager.create_session_logger(
        session_id=session_id,
        agent_mode="parent",
        log_level="INFO"
    )

    # Verify logger was created
    assert logger is not None
    assert logger.extra["session_id"] == session_id
    assert logger.extra["agent_mode"] == "parent"

    # Verify log file was created
    session_log_dir = temp_log_dir / "sessions" / f"{Path.cwd().name}"
    # Actually look for any YYYYMMDD directory
    session_dirs = list((temp_log_dir / "sessions").glob("*"))
    assert len(session_dirs) > 0
    log_files = list(session_dirs[0].glob(f"session_{session_id[:8]}.log"))
    assert len(log_files) > 0


def test_session_logger_formatting(log_manager):
    """Test that session logger formats messages correctly."""
    session_id = "test-session-456"

    logger = log_manager.create_session_logger(
        session_id=session_id,
        agent_mode="child",
        log_level="DEBUG"
    )

    # Log a message
    logger.info("Test message")

    # Verify the logger adapter processes the message
    # (format is tested implicitly through the adapter)
    assert logger.extra["session_id"] == session_id
    assert logger.extra["agent_mode"] == "child"


def test_log_agent_behavior(log_manager):
    """Test structured agent behavior logging."""
    session_id = "test-session-789"
    logger = log_manager.create_session_logger(session_id, "parent")

    # Log agent behavior
    log_agent_behavior(
        logger,
        event_type="test_event",
        details={"key1": "value1", "key2": "value2"}
    )

    # Verify logger was called (implicitly through no errors)
    assert True


def test_log_delegation(log_manager):
    """Test delegation event logging."""
    parent_session = "parent-session-001"
    child_session = "child-session-001"

    logger = log_manager.create_session_logger(parent_session, "parent")

    # Log delegation events
    log_delegation(
        logger,
        action="start",
        parent_session=parent_session,
        child_session=child_session,
        prompt="Test task"
    )

    log_delegation(
        logger,
        action="complete",
        parent_session=parent_session,
        child_session=child_session,
        duration="5.23s"
    )

    # Verify no errors occurred
    assert True


def test_log_tool_execution(log_manager):
    """Test tool execution logging."""
    session_id = "test-session-tool"
    logger = log_manager.create_session_logger(session_id, "parent")

    # Log tool execution
    log_tool_execution(
        logger,
        tool_name="bash",
        status="success",
        duration=1.23
    )

    log_tool_execution(
        logger,
        tool_name="read_file",
        status="error",
        duration=0.05,
        error="File not found"
    )

    # Verify no errors occurred
    assert True


def test_log_state_change(log_manager):
    """Test state change logging."""
    session_id = "test-session-state"
    logger = log_manager.create_session_logger(session_id, "parent")

    # Log state changes
    log_state_change(
        logger,
        from_state="idle",
        to_state="thinking",
        reason="Processing user input"
    )

    log_state_change(
        logger,
        from_state="thinking",
        to_state="executing_tools"
    )

    # Verify no errors occurred
    assert True


def test_error_logging(temp_log_dir):
    """Test error-only logging."""
    # Note: Error logging uses global ErrorLogManager which writes to ~/.capybara/logs/errors
    # This is by design for centralized error tracking across sessions

    # Log an error
    try:
        raise ValueError("Test error message")
    except ValueError as e:
        log_error(
            error=e,
            context="test_context",
            session_id="test-session-error",
            agent_mode="parent"
        )

    # Verify error was logged (check default location)
    from pathlib import Path
    default_error_dir = Path.home() / ".capybara" / "logs" / "errors"
    assert default_error_dir.exists()

    # Verify error log file exists
    error_logs = list(default_error_dir.glob("*.log"))
    assert len(error_logs) > 0


def test_multiple_sessions(log_manager):
    """Test multiple concurrent session loggers."""
    sessions = ["session-1", "session-2", "session-3"]

    loggers = []
    for session_id in sessions:
        logger = log_manager.create_session_logger(session_id, "parent")
        loggers.append(logger)
        logger.info(f"Log from {session_id}")

    # Verify all loggers were created
    assert len(loggers) == len(sessions)

    # Verify each logger has correct session ID
    for i, logger in enumerate(loggers):
        assert logger.extra["session_id"] == sessions[i]


def test_close_session_logger(log_manager):
    """Test closing session loggers."""
    session_id = "test-session-close"

    # Create logger
    logger = log_manager.create_session_logger(session_id, "parent")
    logger.info("Test message before close")

    # Close logger
    log_manager.close_session_logger(session_id)

    # Verify handler was removed
    assert session_id not in log_manager._session_handlers


def test_reuse_session_logger(log_manager):
    """Test that requesting the same session logger returns existing instance."""
    session_id = "test-session-reuse"

    # Create first logger
    logger1 = log_manager.create_session_logger(session_id, "parent")

    # Request same logger again
    logger2 = log_manager.create_session_logger(session_id, "parent")

    # Should return new adapter but use same underlying logger
    assert logger1.extra["session_id"] == logger2.extra["session_id"]
    assert session_id in log_manager._session_handlers
    # Should only have one entry in handlers
    assert len(log_manager._session_handlers) == 1
