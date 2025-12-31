"""Event logging for agent behaviors and delegation tracking."""

import logging
from typing import Any


def log_agent_behavior(logger: logging.LoggerAdapter, event_type: str, details: dict[str, Any]):
    """Log agent behavior events with structured format.

    Args:
        logger: Session logger adapter
        event_type: Type of event (e.g., 'tool_execution', 'delegation', 'state_change')
        details: Event details dictionary
    """
    # Format details as key=value pairs
    detail_str = " | ".join(f"{k}={v}" for k, v in details.items())
    logger.info(f"EVENT:{event_type} | {detail_str}")


def log_delegation(
    logger: logging.LoggerAdapter, action: str, parent_session: str, child_session: str, **kwargs
):
    """Log delegation events between parent and child agents.

    Args:
        logger: Session logger adapter
        action: Delegation action ('start', 'complete', 'timeout', 'error')
        parent_session: Parent session ID
        child_session: Child session ID
        **kwargs: Additional context
    """
    details = {"action": action, "parent": parent_session[:8], "child": child_session[:8], **kwargs}
    log_agent_behavior(logger, "delegation", details)


def log_tool_execution(
    logger: logging.LoggerAdapter, tool_name: str, status: str, duration: float, **kwargs
):
    """Log tool execution events.

    Args:
        logger: Session logger adapter
        tool_name: Name of the tool
        status: Execution status ('success', 'error', 'timeout')
        duration: Execution duration in seconds
        **kwargs: Additional context (e.g., args, result)
    """
    details = {"tool": tool_name, "status": status, "duration": f"{duration:.2f}s", **kwargs}
    log_agent_behavior(logger, "tool_execution", details)


def log_state_change(
    logger: logging.LoggerAdapter, from_state: str, to_state: str, reason: str | None = None
):
    """Log agent state changes.

    Args:
        logger: Session logger adapter
        from_state: Previous state
        to_state: New state
        reason: Optional reason for state change
    """
    details = {
        "from": from_state,
        "to": to_state,
    }
    if reason:
        details["reason"] = reason

    log_agent_behavior(logger, "state_change", details)
