"""Communication flow renderer for parent-child agent visualization."""

from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from capybara.core.agent.status import AgentState, AgentStatus


class CommunicationFlowRenderer:
    """Renders parent↔child communication flow."""

    def __init__(self, console: Console):
        self.console = console
        self.parent_status: Optional[AgentStatus] = None
        self.child_statuses: dict[str, AgentStatus] = {}

    def render(self) -> Panel:
        """Build communication flow tree visualization."""

        if not self.parent_status:
            return Panel(
                Text("No active agents", style="dim"),
                title="Agent Flow",
                border_style="dim"
            )

        # Build tree
        tree = Tree(self._format_agent_node(self.parent_status))

        # Add children
        for child_id in self.parent_status.child_sessions:
            child_status = self.child_statuses.get(child_id)
            if child_status:
                tree.add(self._format_agent_node(child_status))

        return Panel(
            tree,
            title="[bold cyan]Agent Communication Flow[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED
        )

    def _format_agent_node(self, status: AgentStatus) -> Text:
        """Format single agent node with state indicator."""

        # State icon and color
        if status.state == AgentState.THINKING:
            icon = "🤔"
            style = "yellow"
        elif status.state == AgentState.EXECUTING_TOOLS:
            icon = "⚙️"
            style = "cyan"
        elif status.state == AgentState.WAITING_FOR_CHILD:
            icon = "⏳"
            style = "magenta"
        elif status.state == AgentState.COMPLETED:
            icon = "✅"
            style = "green"
        elif status.state == AgentState.FAILED:
            icon = "❌"
            style = "red"
        else:  # IDLE
            icon = "💤"
            style = "dim"

        # Agent type badge
        mode_badge = "[parent]" if status.mode == "parent" else "[child]"

        # Current action
        action_text = f": {status.current_action}" if status.current_action else ""

        return Text.from_markup(
            f"{icon} {mode_badge} {status.state.value}{action_text}",
            style=style
        )

    def update_parent(self, status: AgentStatus):
        """Update parent agent status."""
        self.parent_status = status

    def update_child(self, session_id: str, status: AgentStatus):
        """Update child agent status."""
        self.child_statuses[session_id] = status

    def remove_child(self, session_id: str):
        """Remove completed/failed child from display."""
        self.child_statuses.pop(session_id, None)
