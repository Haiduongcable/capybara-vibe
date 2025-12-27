"""Sub-agent tool for delegating autonomous work."""

import asyncio
import time

from capybara.core.agent import Agent
from capybara.core.agent.status import AgentState
from capybara.core.logging import log_delegation, log_error
from capybara.core.delegation.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage
from capybara.tools.base import AgentMode
from capybara.tools.registry import ToolRegistry
from capybara.tools.builtin.delegation.agent_setup import create_sub_agent
from capybara.tools.builtin.delegation.progress_display import display_sub_agent_progress
from capybara.tools.builtin.delegation.success_handler import handle_success
from capybara.tools.builtin.delegation.error_handler import (
    handle_timeout_error,
    handle_exception_error
)


async def execute_sub_agent(
    task: str,
    parent_session_id: str,
    parent_agent: Agent,
    session_manager: SessionManager,
    storage: ConversationStorage,
    timeout: float = 180.0,
) -> str:
    """Execute sub-agent to complete autonomous work task.

    Sub-agent inherits parent's LLM configuration and tools (except delegation/todo).
    Works autonomously without asking questions.
    Returns comprehensive work report for parent agent.

    Args:
        task: Comprehensive task description with context
        parent_session_id: Parent's session ID
        parent_agent: Parent agent instance
        session_manager: Session manager for hierarchy
        storage: Storage for persistence
        timeout: Max execution time in seconds (default: 180s / 3min)

    Returns:
        Comprehensive work report including:
        - Work completed summary
        - Files modified (created/edited/deleted)
        - Tools used
        - Errors encountered (if any)
        - Success rate
    """

    start_time = time.time()

    # Create child session
    child_session_id = await session_manager.create_child_session(
        parent_id=parent_session_id,
        model=parent_agent.config.model,
        prompt=task,
        title=f"Subtask: {task[:50]}..."
    )

    # Create configured sub-agent (inherits parent's provider/API keys)
    child_agent = create_sub_agent(
        parent_agent=parent_agent,
        child_session_id=child_session_id,
        parent_session_id=parent_session_id,
        timeout=timeout
    )

    # Update parent state
    if parent_agent.flow_renderer:
        parent_agent._update_state(
            AgentState.WAITING_FOR_CHILD,
            f"Sub-agent working: {task[:40]}..."
        )
        parent_agent.status.child_sessions.append(child_session_id)

    # Log delegation start
    await storage.log_session_event(
        session_id=parent_session_id,
        event_type="delegation_start",
        metadata={"child_session_id": child_session_id, "task": task[:100]}
    )

    if parent_agent.session_logger:
        log_delegation(
            parent_agent.session_logger,
            action="start",
            parent_session=parent_session_id,
            child_session=child_session_id,
            prompt=task[:100]
        )

    try:
        # Execute sub-agent and display progress concurrently
        response, _ = await asyncio.wait_for(
            asyncio.gather(
                child_agent.run(task),
                display_sub_agent_progress(
                    parent_agent=parent_agent,
                    child_session_id=child_session_id,
                    task=task,
                    timeout=timeout,
                    parent_session_id=parent_session_id
                )
            ),
            timeout=timeout
        )

        # Handle successful execution
        return await handle_success(
            response=response,
            child_agent=child_agent,
            child_session_id=child_session_id,
            parent_agent=parent_agent,
            parent_session_id=parent_session_id,
            storage=storage,
            duration=time.time() - start_time
        )

    except asyncio.TimeoutError:
        return await handle_timeout_error(
            child_agent=child_agent,
            child_session_id=child_session_id,
            parent_agent=parent_agent,
            parent_session_id=parent_session_id,
            storage=storage,
            start_time=start_time,
            timeout=timeout,
            task=task
        )

    except Exception as e:
        return await handle_exception_error(
            exception=e,
            child_agent=child_agent,
            child_session_id=child_session_id,
            parent_agent=parent_agent,
            parent_session_id=parent_session_id,
            storage=storage,
            start_time=start_time,
            task=task
        )


def register_sub_agent_tool(
    registry: ToolRegistry,
    parent_session_id: str,
    parent_agent: Agent,
    session_manager: SessionManager,
    storage: ConversationStorage
) -> None:
    """Register sub_agent tool for autonomous work delegation.

    Tool enables parent agent to delegate self-contained tasks to specialized
    sub-agent that works autonomously and returns comprehensive work report.
    """

    @registry.tool(
        name="sub_agent",
        description=(
            "Delegate autonomous work to sub-agent. Use for self-contained tasks requiring "
            "multiple steps (reading files, editing code, running commands). "
            "Sub-agent works independently without asking questions and returns comprehensive "
            "work report including files modified, tools used, and actions taken. "
            "Perfect for: code refactoring, file extraction, testing, documentation generation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Comprehensive task description with all necessary context. Include: "
                        "specific files/directories involved, expected outcomes, requirements. "
                        "Sub-agent has full tool access (read, write, edit, bash, grep, etc.) "
                        "but NO access to your conversation history - provide complete context."
                    )
                },
                "timeout": {
                    "type": "number",
                    "description": "Maximum execution time in seconds (default: 180s)",
                    "default": 180.0
                }
            },
            "required": ["task"]
        },
        allowed_modes=[AgentMode.PARENT]
    )
    async def sub_agent(task: str, timeout: float = 180.0) -> str:
        """Execute sub-agent for autonomous work task."""
        return await execute_sub_agent(
            task=task,
            parent_session_id=parent_session_id,
            parent_agent=parent_agent,
            session_manager=session_manager,
            storage=storage,
            timeout=timeout
        )
