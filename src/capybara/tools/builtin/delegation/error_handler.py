"""Error handling for sub-agent execution."""

import time
import asyncio

from capybara.core.agent import Agent
from capybara.core.logging import log_delegation
from capybara.memory.storage import ConversationStorage
from capybara.tools.builtin.delegation.failure_analysis import (
    analyze_timeout_failure,
    analyze_exception_failure
)


async def handle_timeout_error(
    child_agent: Agent,
    child_session_id: str,
    parent_agent: Agent,
    parent_session_id: str,
    storage: ConversationStorage,
    start_time: float,
    timeout: float,
    task: str
) -> str:
    """Handle sub-agent timeout error with logging and failure report."""

    # Update parent state
    if parent_agent.flow_renderer:
        if child_session_id in parent_agent.status.child_sessions:
            parent_agent.status.child_sessions.remove(child_session_id)

    # Analyze failure
    failure = analyze_timeout_failure(
        child_agent=child_agent,
        session_id=child_session_id,
        duration=time.time() - start_time,
        timeout=timeout,
        prompt=task
    )

    # Log event
    await storage.log_session_event(
        session_id=parent_session_id,
        event_type="delegation_timeout",
        metadata={
            "child_session_id": child_session_id,
            "duration": failure.duration,
            "category": failure.category.value
        }
    )

    # Log to session logger
    if parent_agent.session_logger:
        log_delegation(
            parent_agent.session_logger,
            action="timeout",
            parent_session=parent_session_id,
            child_session=child_session_id,
            duration=f"{failure.duration:.2f}s"
        )

    return failure.to_context_string()


async def handle_exception_error(
    exception: Exception,
    child_agent: Agent,
    child_session_id: str,
    parent_agent: Agent,
    parent_session_id: str,
    storage: ConversationStorage,
    start_time: float,
    task: str
) -> str:
    """Handle sub-agent exception error with logging and failure report."""

    # Import here to avoid circular dependency
    from capybara.core.logging import log_error

    # Update parent state
    if parent_agent.flow_renderer:
        if child_session_id in parent_agent.status.child_sessions:
            parent_agent.status.child_sessions.remove(child_session_id)

    # Analyze failure
    failure = analyze_exception_failure(
        exception=exception,
        child_agent=child_agent,
        session_id=child_session_id,
        duration=time.time() - start_time,
        prompt=task
    )

    # Log event
    await storage.log_session_event(
        session_id=parent_session_id,
        event_type="delegation_error",
        metadata={
            "child_session_id": child_session_id,
            "error": str(exception),
            "duration": failure.duration,
            "category": failure.category.value
        }
    )

    # Log to session logger
    if parent_agent.session_logger:
        log_delegation(
            parent_agent.session_logger,
            action="error",
            parent_session=parent_session_id,
            child_session=child_session_id,
            duration=f"{failure.duration:.2f}s",
            error=str(exception)
        )

    # Log error
    log_error(
        error=exception,
        context=f"sub_agent:child={child_session_id[:8]}",
        session_id=parent_session_id,
        agent_mode="parent"
    )

    return failure.to_context_string()
