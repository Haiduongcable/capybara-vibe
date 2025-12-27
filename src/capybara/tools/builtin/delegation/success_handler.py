"""Success handling for sub-agent execution."""

from capybara.core.agent import Agent
from capybara.core.agent.status import AgentState
from capybara.core.logging import log_delegation
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory
from capybara.tools.builtin.delegation.work_report import generate_work_report


async def handle_success(
    response: str,
    child_agent: Agent,
    child_session_id: str,
    parent_agent: Agent,
    parent_session_id: str,
    storage: ConversationStorage,
    duration: float
) -> str:
    """Handle successful sub-agent execution with logging and work report."""

    # Save child messages to storage
    for msg in child_agent.memory.get_messages():
        await storage.save_message(child_session_id, msg)

    # Update parent state
    if parent_agent.flow_renderer:
        parent_agent.status.child_sessions.remove(child_session_id)
        parent_agent._update_state(
            AgentState.EXECUTING_TOOLS,
            "Processing work report"
        )

    # Log completion event
    await storage.log_session_event(
        session_id=parent_session_id,
        event_type="delegation_complete",
        metadata={
            "child_session_id": child_session_id,
            "duration": duration,
            "status": "completed"
        }
    )

    # Log to session logger
    if parent_agent.session_logger:
        log_delegation(
            parent_agent.session_logger,
            action="complete",
            parent_session=parent_session_id,
            child_session=child_session_id,
            duration=f"{duration:.2f}s"
        )

    # Generate comprehensive work report
    return generate_work_report(
        response=response,
        execution_log=child_agent.execution_log,
        session_id=child_session_id,
        duration=duration
    )
