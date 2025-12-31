"""Tests for API logging functionality."""

import json
from pathlib import Path
import pytest

from capybara.core.logging.api_logger import APILogger


class TestAPILogger:
    """Test APILogger functionality."""

    def test_logger_initialization(self, tmp_path: Path) -> None:
        """Test that logger initializes correctly."""
        session_id = "test_session_123"
        logger = APILogger(session_id=session_id, log_dir=tmp_path)

        assert logger.session_id == session_id
        assert logger.session_log_dir == tmp_path / session_id
        assert logger.session_log_dir.exists()
        assert logger.request_count == 0

    def test_log_request(self, tmp_path: Path) -> None:
        """Test logging API requests."""
        logger = APILogger(session_id="test_session", log_dir=tmp_path)

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        request_id = logger.log_request(
            messages=messages,
            model="gpt-4o",
            tools=tools,
            metadata={"stream": True},
        )

        assert request_id == 1
        assert logger.request_count == 1

        # Verify log file was created
        log_file = logger.session_log_dir / "request_001.json"
        assert log_file.exists()

        # Verify log content
        with open(log_file) as f:
            log_data = json.load(f)

        assert log_data["request_id"] == 1
        assert log_data["session_id"] == "test_session"
        assert log_data["model"] == "gpt-4o"
        assert log_data["message_count"] == 2
        assert log_data["messages"] == messages
        assert log_data["tools"] == tools
        assert log_data["metadata"]["stream"] is True

    def test_log_response_success(self, tmp_path: Path) -> None:
        """Test logging successful API responses."""
        logger = APILogger(session_id="test_session", log_dir=tmp_path)

        request_id = logger.log_request(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4o",
        )

        response_data = {"chunks": 10, "streamed": True}
        logger.log_response(request_id=request_id, response=response_data)

        # Verify log file was created
        log_file = logger.session_log_dir / "response_001.json"
        assert log_file.exists()

        # Verify log content
        with open(log_file) as f:
            log_data = json.load(f)

        assert log_data["request_id"] == request_id
        assert log_data["response"] == response_data
        assert "error" not in log_data

    def test_log_response_error(self, tmp_path: Path) -> None:
        """Test logging API errors."""
        logger = APILogger(session_id="test_session", log_dir=tmp_path)

        request_id = logger.log_request(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4o",
        )

        error = ValueError("Test error message")
        logger.log_response(request_id=request_id, response=None, error=error)

        # Verify log file was created
        log_file = logger.session_log_dir / "response_001.json"
        assert log_file.exists()

        # Verify log content
        with open(log_file) as f:
            log_data = json.load(f)

        assert log_data["request_id"] == request_id
        assert "response" not in log_data
        assert log_data["error"]["type"] == "ValueError"
        assert log_data["error"]["message"] == "Test error message"

    def test_log_memory_state(self, tmp_path: Path) -> None:
        """Test logging memory state."""
        logger = APILogger(session_id="test_session", log_dir=tmp_path)

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User message"},
            {"role": "assistant", "content": "Assistant response"},
        ]

        logger.log_memory_state(
            messages=messages,
            token_count=150,
            context="before_completion_turn_1",
        )

        # Find the memory state log file
        log_files = list(logger.session_log_dir.glob("memory_state_*.json"))
        assert len(log_files) == 1

        # Verify log content
        with open(log_files[0]) as f:
            log_data = json.load(f)

        assert log_data["session_id"] == "test_session"
        assert log_data["context"] == "before_completion_turn_1"
        assert log_data["token_count"] == 150
        assert log_data["message_count"] == 3
        assert log_data["messages"] == messages

    def test_multiple_requests(self, tmp_path: Path) -> None:
        """Test logging multiple requests in sequence."""
        logger = APILogger(session_id="test_session", log_dir=tmp_path)

        # Log 3 requests
        for i in range(3):
            request_id = logger.log_request(
                messages=[{"role": "user", "content": f"Message {i}"}],
                model="gpt-4o",
            )
            assert request_id == i + 1

        assert logger.request_count == 3

        # Verify all log files exist
        for i in range(1, 4):
            log_file = logger.session_log_dir / f"request_{i:03d}.json"
            assert log_file.exists()
