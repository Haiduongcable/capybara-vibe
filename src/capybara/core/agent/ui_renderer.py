"""UI rendering for agent status display."""

from typing import TYPE_CHECKING

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from capybara.tools.base import AgentMode
from capybara.tools.builtin.todo import TodoStatus, get_todos

if TYPE_CHECKING:
    from capybara.ui.flow_renderer import CommunicationFlowRenderer


class AgentUIRenderer:
    """Handles UI rendering for agent status displays.

    Responsible for rendering:
    - Communication flow panel (parent agents only)
    - Activity panel (tool execution status)
    - Todo panel (task list)
    """

    def __init__(
        self,
        console: Console,
        agent_mode: AgentMode,
        flow_renderer: "CommunicationFlowRenderer | None" = None,
    ):
        """Initialize UI renderer.

        Args:
            console: Rich console for output
            agent_mode: Agent mode (parent/child)
            flow_renderer: Optional flow renderer for parent agents
        """
        self.console = console
        self.agent_mode = agent_mode
        self.flow_renderer = flow_renderer

    def render_status(
        self,
        tool_statuses: dict[str, dict[str, str]],
        has_active_children: bool = False,
    ) -> Text | Group | Panel:
        """Build unified status display with flow + activity + todos.

        Args:
            tool_statuses: Dict mapping tool_call_id to {name, status}
            has_active_children: Whether parent has active child sessions

        Returns:
            Renderable for Rich display
        """
        panels = []

        # 1. Communication Flow (only for parent with active children)
        if self.flow_renderer and self.agent_mode == AgentMode.PARENT:
            flow_panel = self.flow_renderer.render()
            if flow_panel and has_active_children:
                panels.append(flow_panel)

        # 2. Activity Panel (Tools)
        activity_panel = self._render_activity_panel(tool_statuses)
        if activity_panel:
            panels.append(activity_panel)

        # 3. Todo Panel
        todo_panel = self._render_todo_panel()
        if todo_panel:
            panels.append(todo_panel)

        # 4. Combine all panels
        if len(panels) == 0:
            return Text("No active status", style="dim")
        elif len(panels) == 1:
            return panels[0]
        else:
            return Group(*panels)

    def _render_activity_panel(self, tool_statuses: dict[str, dict[str, str]]) -> Panel | None:
        """Render activity panel showing tool execution status.

        Args:
            tool_statuses: Dict mapping tool_call_id to {name, status}

        Returns:
            Panel if there are items to show, None otherwise
        """
        activity_items: list[Text | Group] = []

        for _, info in tool_statuses.items():
            name = info["name"]
            status = info["status"]

            # UX: Don't show 'todo' tool if todos already visible
            # (Only if plan already exists - show tool during initialization)
            if name == "todo" and get_todos():
                continue

            if status == "pending":
                activity_items.append(Text(f"⏳ {name} (pending)", style="dim"))
            elif status == "running":
                activity_items.append(
                    Group(Spinner("dots", style="cyan"), Text(f" {name}", style="cyan"))
                )
            elif status == "done":
                activity_items.append(Text(f"✅ {name}", style="green"))
            elif status == "error":
                activity_items.append(Text(f"❌ {name} (failed)", style="red"))

        if not activity_items:
            return None

        return Panel(
            Group(*activity_items),
            title="[bold blue]Active Capabilities[/bold blue]",
            border_style="blue",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_todo_panel(self) -> Panel | None:
        """Render todo panel showing task list.

        Returns:
            Panel if there are todos, None otherwise
        """
        todos = get_todos()
        if not todos:
            return None

        todo_items = []
        for t in todos:
            icon = "☐"  # Default: ballot box
            style = "white"

            if t.status == TodoStatus.COMPLETED:
                icon = "☑"  # Checked ballot box
                style = "dim green"
            elif t.status == TodoStatus.IN_PROGRESS:
                icon = "◎"  # Bullseye for focus
                style = "bold yellow"
            elif t.status == TodoStatus.CANCELLED:
                icon = "☒"  # X ballot box
                style = "dim strike"

            todo_items.append(Text(f" {icon} {t.content}", style=style))

        return Panel(
            Group(*todo_items),
            title="[bold]Plan[/bold]",
            border_style="dim white",
            box=box.MINIMAL,
            padding=(0, 1),
            title_align="left",
        )
