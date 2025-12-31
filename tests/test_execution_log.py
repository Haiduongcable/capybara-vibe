"""Tests for execution logging system."""

import pytest

from capybara.core.execution.execution_log import ExecutionLog, ToolExecution


def test_execution_log_file_tracking():
    """Test file operation tracking."""
    log = ExecutionLog()
    log.files_read.add("src/main.py")
    log.files_written.add("output.txt")
    log.files_edited.add("src/config.py")

    assert "src/main.py" in log.files_read
    assert "output.txt" in log.files_modified
    assert "src/config.py" in log.files_modified
    assert len(log.files_modified) == 2


def test_tool_usage_summary():
    """Test tool execution counting."""
    log = ExecutionLog()
    log.tool_executions.append(
        ToolExecution(
            tool_name="read_file",
            args={},
            result_summary="ok",
            success=True,
            duration=0.1,
            timestamp="2025-01-01",
        )
    )
    log.tool_executions.append(
        ToolExecution(
            tool_name="read_file",
            args={},
            result_summary="ok",
            success=True,
            duration=0.1,
            timestamp="2025-01-01",
        )
    )
    log.tool_executions.append(
        ToolExecution(
            tool_name="bash",
            args={},
            result_summary="ok",
            success=True,
            duration=0.5,
            timestamp="2025-01-01",
        )
    )

    summary = log.tool_usage_summary
    assert summary["read_file"] == 2
    assert summary["bash"] == 1


def test_success_rate_calculation():
    """Test success rate metric."""
    log = ExecutionLog()

    # 2 successes, 1 failure
    log.tool_executions = [
        ToolExecution("tool1", {}, "ok", True, 0.1, "2025-01-01"),
        ToolExecution("tool2", {}, "ok", True, 0.1, "2025-01-01"),
        ToolExecution("tool3", {}, "err", False, 0.1, "2025-01-01"),
    ]

    assert log.success_rate == pytest.approx(0.666, rel=0.01)


def test_empty_execution_log():
    """Test empty execution log has 100% success rate."""
    log = ExecutionLog()
    assert log.success_rate == 1.0
    assert len(log.files_modified) == 0
    assert len(log.tool_usage_summary) == 0


def test_error_tracking():
    """Test error recording."""
    log = ExecutionLog()
    log.errors.append(("bash", "Command not found"))
    log.errors.append(("read_file", "File not found"))

    assert len(log.errors) == 2
    assert log.errors[0] == ("bash", "Command not found")
    assert log.errors[1] == ("read_file", "File not found")


def test_files_modified_union():
    """Test files_modified includes both written and edited files."""
    log = ExecutionLog()
    log.files_written.add("new.py")
    log.files_written.add("test.py")
    log.files_edited.add("existing.py")

    assert len(log.files_modified) == 3
    assert "new.py" in log.files_modified
    assert "test.py" in log.files_modified
    assert "existing.py" in log.files_modified
