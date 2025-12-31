"""Progress display for sub-agent execution."""

import time
from typing import Any

from rich.console import Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from capybara.core.agent import Agent
from capybara.core.agent.status import AgentState, AgentStatus
from capybara.core.delegation.event_bus import EventType, get_event_bus


def _format_tool_args(args: dict[str, Any]) -> str:
    """Format tool arguments for display (like main agent).

    Args:
        args: Tool arguments dictionary

    Returns:
        Formatted argument string like "path='file.txt', limit=100"
    """
    if not args:
        return ""

    display_args = []
    for k, v in args.items():
        v_str = str(v)
        # Truncate long values
        if len(v_str) > 100:
            v_str = v_str[:100] + "..."
        # Quote string values
        if isinstance(v, str):
            v_str = f"'{v_str}'"
        display_args.append(f"{k}={v_str}")

    return ", ".join(display_args)


async def display_sub_agent_progress(
    parent_agent: Agent, child_session_id: str, task: str, timeout: float, parent_session_id: str
) -> None:
    """Display sub-agent work progress with minimal output.

    Shows:
    - Opening box before execution starts
    - Simplified activity messages (not every tool call)
    - Final status with tool count and duration
    - Closing box symbol

    Does NOT spam console with per-tool output or status panels.
    """
    task_start = time.time()
    event_bus = get_event_bus()

    # Render static header (outside Live to avoid flickering)
    parent_agent.console.print(
        "\n[bold cyan]╭──────────────────────────── SubAgent ─────────────────────────────╮[/bold cyan]"
    )
    parent_agent.console.print(f"[bold cyan]│[/bold cyan] [dim]Task: {task[:62]}...[/dim]")
    parent_agent.console.print(
        f"[bold cyan]│[/bold cyan] ⚙️  Autonomous execution (timeout: {timeout}s)"
    )
    parent_agent.console.print("[bold cyan]│[/bold cyan]")

    # Track child status in flow renderer
    if parent_agent.flow_renderer:
        child_status = AgentStatus(
            session_id=child_session_id,
            mode="child",
            state=AgentState.THINKING,
            parent_session=parent_session_id,
        )
        parent_agent.flow_renderer.update_child(child_session_id, child_status)

    # Track display state
    tool_count = 0
    is_thinking = True
    tool_lines: list[Text] = []  # Accumulated tool execution lines

    def render_progress():
        """Build current progress display with spinner if thinking."""
        lines: list[Text | Group] = []

        # Add accumulated tool lines
        for line in tool_lines:
            lines.append(line)

        # Add spinner if thinking
        if is_thinking:
            lines.append(
                Group(
                    Text("│ ", style="bold cyan"), Spinner("dots", text="Thinking...", style="cyan")
                )
            )

        return Group(*lines) if lines else Text("")

    # Use Live display for animated spinner
    with Live(
        render_progress(), console=parent_agent.console, refresh_per_second=10, transient=True
    ) as live:
        async for event in event_bus.subscribe(child_session_id):
            if event.event_type == EventType.AGENT_STATE_CHANGE:
                # Update flow renderer but DON'T print internal state messages
                new_state = AgentState(event.agent_state)

                # Update thinking state
                if new_state == AgentState.THINKING:
                    is_thinking = True
                elif new_state == AgentState.EXECUTING_TOOLS:
                    is_thinking = False

                if parent_agent.flow_renderer:
                    child_status.state = new_state
                    child_status.current_action = event.message
                    parent_agent.flow_renderer.update_child(child_session_id, child_status)

                # Update Live display
                live.update(render_progress())

            elif event.event_type == EventType.TOOL_START:
                tool_count += 1
                tool_name = event.tool_name or "unknown"
                tool_args = event.metadata.get("args", {})

                # Format arguments like main agent does
                args_display = _format_tool_args(tool_args)
                tool_line = Text.from_markup(
                    f"[bold cyan]│[/bold cyan] [dim]> {tool_name}({args_display})[/dim]"
                )
                tool_lines.append(tool_line)
                is_thinking = False

                # Update Live display
                live.update(render_progress())

            elif event.event_type == EventType.AGENT_DONE:
                elapsed = time.time() - task_start
                status = event.metadata.get("status", "completed")

                # Clear thinking state
                is_thinking = False

                # Add final status line
                if status == "completed":
                    status_line = Text.from_markup(
                        f"[bold cyan]│[/bold cyan] [green]✅ Work completed in {elapsed:.1f}s ({tool_count} tools used)[/green]"
                    )
                else:
                    error_msg = event.metadata.get("error", status)
                    status_line = Text.from_markup(
                        f"[bold cyan]│[/bold cyan] [red]❌ Work failed: {error_msg}[/red]"
                    )

                tool_lines.append(status_line)
                live.update(render_progress())
                break

    # After Live context ends, print all accumulated lines permanently
    # (Live was transient, so everything disappeared - reprint for history)
    for line in tool_lines:
        parent_agent.console.print(line)

    # Print closing box
    parent_agent.console.print(
        "[bold cyan]╰────────────────────────────────────────────────────────────────────╮[/bold cyan]\n"
    )

    # Cleanup flow renderer
    if parent_agent.flow_renderer:
        parent_agent.flow_renderer.remove_child(child_session_id)
