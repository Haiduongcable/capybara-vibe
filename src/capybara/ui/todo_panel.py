"""Persistent todo panel component for terminal UI."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from capybara.tools.builtin.todo import TodoItem, TodoStatus
from capybara.tools.builtin.todo_state import todo_state


class PersistentTodoPanel:
    """Persistent todo panel that displays at bottom of terminal.

    Subscribes to TodoStateManager and auto-updates when todos change.
    Supports visibility toggle via Ctrl+T keyboard shortcut.

    Matches Claude Code visual style:
    - Status icons: ☐ pending, ◎ in_progress, ☑ completed
    - Minimal borders (box.MINIMAL)
    - Left-aligned title
    - Auto-show when todos exist
    """

    def __init__(self, visible: bool = True) -> None:
        """Initialize persistent todo panel.

        Args:
            visible: Initial visibility state (default: True)
        """
        self.visible = visible
        self.todos: list[TodoItem] = []

        # Subscribe to state changes
        todo_state.subscribe(self._on_todos_updated)

    def _on_todos_updated(self, new_todos: list[TodoItem]) -> None:
        """Callback when todos change in state manager.

        Auto-shows panel when todos exist and it was hidden.

        Args:
            new_todos: Updated todo list from state manager
        """
        self.todos = new_todos

        # Auto-show panel when todos exist
        if new_todos and not self.visible:
            self.visible = True

    def toggle_visibility(self) -> None:
        """Toggle panel visibility (Ctrl+T handler)."""
        self.visible = not self.visible

    def show(self) -> None:
        """Show the panel."""
        self.visible = True

    def hide(self) -> None:
        """Hide the panel."""
        self.visible = False

    def render(self) -> RenderableType:
        """Render panel for Rich Layout.

        Returns empty Text if invisible or no todos.

        Returns:
            Panel with todo list or empty Text
        """
        if not self.visible or not self.todos:
            return Text("")

        items = []
        completed_count = 0

        for todo in self.todos:
            icon = self._get_icon(todo.status)
            style = self._get_style(todo.status)
            items.append(Text(f" {icon} {todo.content}", style=style))

            if todo.status == TodoStatus.COMPLETED:
                completed_count += 1

        # Add progress footer
        total = len(self.todos)
        footer_text = f" [{completed_count}/{total} tasks]"
        if completed_count < total:
            footer_text += " · Ctrl+T to hide"
        items.append(Text(footer_text, style="dim"))

        return Panel(
            Group(*items),
            title="[bold]Plan[/bold]",
            title_align="left",
            border_style="dim white",
            box=box.MINIMAL,
            padding=(0, 1),
        )

    def _get_icon(self, status: TodoStatus) -> str:
        """Get status icon for todo item.

        Args:
            status: Todo status

        Returns:
            Unicode icon character
        """
        if status == TodoStatus.COMPLETED:
            return "☑"  # Ballot box with check
        elif status == TodoStatus.IN_PROGRESS:
            return "◎"  # Bullseye (indicates focus)
        elif status == TodoStatus.CANCELLED:
            return "☒"  # Ballot box with X
        else:  # PENDING
            return "☐"  # Ballot box

    def _get_style(self, status: TodoStatus) -> str:
        """Get Rich style for todo item.

        Args:
            status: Todo status

        Returns:
            Rich style string
        """
        if status == TodoStatus.COMPLETED:
            return "dim green"
        elif status == TodoStatus.IN_PROGRESS:
            return "bold yellow"
        elif status == TodoStatus.CANCELLED:
            return "dim strike"
        else:  # PENDING
            return "white"

    def cleanup(self) -> None:
        """Cleanup observers on exit."""
        todo_state.unsubscribe(self._on_todos_updated)
