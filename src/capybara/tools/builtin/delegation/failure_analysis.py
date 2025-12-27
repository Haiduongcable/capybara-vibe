"""Failure analysis for sub-agent execution."""

from capybara.core.delegation.child_errors import ChildFailure, FailureCategory


def analyze_timeout_failure(child_agent, session_id: str, duration: float, timeout: float, prompt: str) -> ChildFailure:
    """Analyze timeout to provide recovery guidance."""
    exec_log = child_agent.execution_log

    # Extract completed work
    completed_steps = []
    if exec_log and exec_log.tool_executions:
        successful_writes = [te for te in exec_log.tool_executions
                            if te.tool_name == "write_file" and te.success]
        if successful_writes:
            completed_steps.append(f"Created {len(successful_writes)} files")

        successful_edits = [te for te in exec_log.tool_executions
                           if te.tool_name == "edit_file" and te.success]
        if successful_edits:
            completed_steps.append(f"Modified {len(successful_edits)} files")

    tool_count = len(exec_log.tool_executions) if exec_log else 0
    needs_more_time = tool_count > 0

    # Build suggested actions, filtering None
    actions = [
        f"Retry with timeout={int(timeout * 2)}s" if needs_more_time else None,
        "Break task into smaller subtasks"
    ]
    suggested_actions = [a for a in actions if a is not None]

    return ChildFailure(
        category=FailureCategory.TIMEOUT,
        message=f"Sub-agent timed out after {timeout}s",
        session_id=session_id,
        duration=duration,
        completed_steps=completed_steps,
        files_modified=list(exec_log.files_modified) if exec_log else [],
        blocked_on="Time limit insufficient",
        suggested_retry=needs_more_time,
        suggested_actions=suggested_actions,
        tool_usage=exec_log.tool_usage_summary if exec_log else {},
        last_successful_tool=exec_log.tool_executions[-1].tool_name if exec_log and exec_log.tool_executions else None
    )


def analyze_exception_failure(exception: Exception, child_agent, session_id: str, duration: float, prompt: str) -> ChildFailure:
    """Categorize exception and provide recovery guidance."""
    exec_log = child_agent.execution_log
    error_msg = str(exception)

    # Check exception type first (more reliable than string matching)
    if isinstance(exception, (PermissionError, FileNotFoundError, OSError, IOError)):
        category = FailureCategory.TOOL_ERROR
        actions = ["Check file permissions", "Verify file exists", "Install missing dependencies if tool failed"]
        retryable = True
    elif isinstance(exception, (ValueError, TypeError, KeyError, AttributeError)):
        category = FailureCategory.INVALID_TASK
        actions = ["Clarify task requirements", "Break into simpler tasks", "Provide more specific instructions"]
        retryable = False
    elif "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
        category = FailureCategory.TOOL_ERROR
        actions = ["Check API key configuration", "Verify environment variables", "Check provider settings"]
        retryable = True
    elif "permission denied" in error_msg.lower() or "not found" in error_msg.lower():
        category = FailureCategory.TOOL_ERROR
        actions = ["Check file permissions", "Verify file exists", "Install missing dependencies if tool failed"]
        retryable = True
    elif "invalid" in error_msg.lower():
        category = FailureCategory.INVALID_TASK
        actions = ["Clarify task requirements", "Break into simpler tasks", "Provide more specific instructions"]
        retryable = False
    else:
        category = FailureCategory.TOOL_ERROR
        actions = ["Review error in sub-agent session logs", "Fix environment", "Retry after fixing issue"]
        retryable = True

    return ChildFailure(
        category=category,
        message=f"{type(exception).__name__}: {error_msg}",
        session_id=session_id,
        duration=duration,
        completed_steps=[],
        files_modified=list(exec_log.files_modified) if exec_log else [],
        blocked_on=error_msg,
        suggested_retry=retryable,
        suggested_actions=actions,
        tool_usage=exec_log.tool_usage_summary if exec_log else {},
        last_successful_tool=None
    )
