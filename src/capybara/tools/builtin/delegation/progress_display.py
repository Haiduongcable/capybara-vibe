"""Progress display for sub-agent execution."""

import time

from capybara.core.agent import Agent
from capybara.core.agent.status import AgentState, AgentStatus
from capybara.core.delegation.event_bus import EventType, get_event_bus


async def display_sub_agent_progress(
    parent_agent: Agent,
    child_session_id: str,
    task: str,
    timeout: float,
    parent_session_id: str
) -> None:
    """Display sub-agent work progress with minimal output.

    Shows:
    - Task description (truncated)
    - Timeout setting
    - Final status (completed or failed with error)
    - Tool count and duration

    Does NOT spam console with per-tool output.
    """
    task_start = time.time()
    event_bus = get_event_bus()

    parent_agent.console.print("\n[bold cyan]┌─ Sub-Agent Working[/bold cyan]")
    parent_agent.console.print(f"│ [dim]Task: {task[:70]}...[/dim]")
    parent_agent.console.print(f"│ ⚙️  Autonomous execution (timeout: {timeout}s)")
    parent_agent.console.print("│")

    # Track child status in flow renderer
    if parent_agent.flow_renderer:
        child_status = AgentStatus(
            session_id=child_session_id,
            mode="child",
            state=AgentState.THINKING,
            parent_session=parent_session_id
        )
        parent_agent.flow_renderer.update_child(child_session_id, child_status)

    # Subscribe to child events
    tool_count = 0
    async for event in event_bus.subscribe(child_session_id):
        if event.event_type == EventType.AGENT_STATE_CHANGE:
            if parent_agent.flow_renderer:
                child_status.state = AgentState(event.agent_state)
                child_status.current_action = event.message
                parent_agent.flow_renderer.update_child(child_session_id, child_status)

        elif event.event_type == EventType.TOOL_START:
            tool_count += 1

        elif event.event_type == EventType.AGENT_DONE:
            elapsed = time.time() - task_start
            status = event.metadata.get("status", "completed")

            if status == "completed":
                parent_agent.console.print(
                    f"│ [green]✅ Work completed in {elapsed:.1f}s ({tool_count} tools used)[/green]"
                )
            else:
                error_msg = event.metadata.get("error", status)
                parent_agent.console.print(f"│ [red]❌ Work failed: {error_msg}[/red]")

            parent_agent.console.print("[bold cyan]└─ Work Report Ready[/bold cyan]\n")
            break

    # Cleanup flow renderer
    if parent_agent.flow_renderer:
        parent_agent.flow_renderer.remove_child(child_session_id)
