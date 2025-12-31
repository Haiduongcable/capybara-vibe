"""Tests for child agent error handling."""

from capybara.core.delegation.child_errors import ChildFailure, FailureCategory


def test_timeout_failure_formatting():
    """Test timeout failure message generation."""
    failure = ChildFailure(
        category=FailureCategory.TIMEOUT,
        message="Timed out after 300s",
        session_id="child_123",
        duration=300.0,
        completed_steps=["Created 2 files", "Modified 1 file"],
        files_modified=["src/new.py", "tests/test_new.py"],
        blocked_on="Insufficient time",
        suggested_retry=True,
        suggested_actions=["Increase timeout to 600s", "Break task into smaller subtasks"],
        tool_usage={"write_file": 2, "edit_file": 1},
        last_successful_tool="edit_file",
    )

    context = failure.to_context_string()

    assert "timeout" in context
    assert "Retryable: Yes" in context
    assert "Created 2 files" in context
    assert "src/new.py" in context
    assert "Increase timeout" in context
    assert "<retryable>true</retryable>" in context
    assert "<failure_category>timeout</failure_category>" in context


def test_non_retryable_failure():
    """Test invalid task failure (not retryable)."""
    failure = ChildFailure(
        category=FailureCategory.INVALID_TASK,
        message="Task unclear",
        session_id="child_456",
        duration=10.0,
        completed_steps=[],
        files_modified=[],
        blocked_on="Ambiguous requirements",
        suggested_retry=False,
        suggested_actions=["Clarify task requirements"],
        tool_usage={},
        last_successful_tool=None,
    )

    context = failure.to_context_string()

    assert "Retryable: No" in context
    assert "<retryable>false</retryable>" in context
    assert "invalid_task" in context
    assert "Clarify task requirements" in context


def test_tool_error_failure():
    """Test tool error with retryable suggestion."""
    failure = ChildFailure(
        category=FailureCategory.TOOL_ERROR,
        message="Permission denied",
        session_id="child_789",
        duration=5.0,
        completed_steps=[],
        files_modified=[],
        blocked_on="Cannot access /root/file.txt",
        suggested_retry=True,
        suggested_actions=["Check file permissions", "Run with sudo"],
        tool_usage={"read_file": 1},
        last_successful_tool=None,
    )

    context = failure.to_context_string()

    assert "tool_error" in context
    assert "Retryable: Yes" in context
    assert "Check file permissions" in context
    assert "<status>failed</status>" in context


def test_partial_success_with_files():
    """Test partial success showing modified files."""
    failure = ChildFailure(
        category=FailureCategory.PARTIAL_SUCCESS,
        message="Completed 2 of 5 tasks",
        session_id="child_abc",
        duration=120.0,
        completed_steps=["Implemented authentication", "Added tests"],
        files_modified=["src/auth.py", "tests/test_auth.py"],
        blocked_on="Missing database credentials",
        suggested_retry=True,
        suggested_actions=["Provide database credentials", "Use mock database"],
        tool_usage={"write_file": 2, "edit_file": 1},
        last_successful_tool="write_file",
    )

    context = failure.to_context_string()

    assert "Implemented authentication" in context
    assert "src/auth.py" in context
    assert "tests/test_auth.py" in context
    assert "Missing database credentials" in context


def test_empty_completed_steps():
    """Test failure with no completed work."""
    failure = ChildFailure(
        category=FailureCategory.TIMEOUT,
        message="Timed out immediately",
        session_id="child_xyz",
        duration=1.0,
        completed_steps=[],
        files_modified=[],
        blocked_on="Task took too long",
        suggested_retry=False,
        suggested_actions=["Simplify task"],
        tool_usage={},
        last_successful_tool=None,
    )

    context = failure.to_context_string()

    assert "None" in context  # Shows "None" for empty completed steps
    assert "none" in context.lower()  # Shows "none" for no files modified
