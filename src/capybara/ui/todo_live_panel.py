"""Live-updating todo panel that renders independently from agent output."""

import asyncio
from typing import Optional

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from capybara.tools.builtin.todo import TodoItem, TodoStatus


class LiveTodoPanel:
    """Live-updating todo panel displayed in a fixed terminal location.

    Runs in background and updates independently from agent processing.
    Uses Rich Live display to maintain persistent position.
    """

    def __init__(self, console: Console, visible: bool = True) -> None:
        """Initialize live todo panel.

        Args:
            console: Rich console for rendering
            visible: Initial visibility state
        """
        self.console = console
        self.visible = visible
        self.todos: list[TodoItem] = []
        self._live: Optional[Live] = None
        self._task: Optional[asyncio.Task] = None

    def update_todos(self, new_todos: list[TodoItem]) -> None:
        """Update todo list and refresh display.

        Args:
            new_todos: Updated todo list
        """
        self.todos = new_todos

        # Auto-show when todos exist
        if new_todos and not self.visible:
            self.visible = True

        # Update live display if running
        if self._live:
            self._live.update(self._render())

    def toggle_visibility(self) -> None:
        """Toggle panel visibility."""
        self.visible = not self.visible
        if self._live:
            self._live.update(self._render())

    def show(self) -> None:
        """Show the panel."""
        self.visible = True
        if self._live:
            self._live.update(self._render())

    def hide(self) -> None:
        """Hide the panel."""
        self.visible = False
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Text | Panel:
        """Render panel content.

        Returns:
            Panel with todo list or empty Text if hidden
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
        """Get status icon."""
        if status == TodoStatus.COMPLETED:
            return "☑"
        elif status == TodoStatus.IN_PROGRESS:
            return "◎"
        elif status == TodoStatus.CANCELLED:
            return "☒"
        else:
            return "☐"

    def _get_style(self, status: TodoStatus) -> str:
        """Get Rich style for status."""
        if status == TodoStatus.COMPLETED:
            return "dim green"
        elif status == TodoStatus.IN_PROGRESS:
            return "bold yellow"
        elif status == TodoStatus.CANCELLED:
            return "dim strike"
        else:
            return "white"

    async def start(self) -> None:
        """Start live display in background task."""
        if self._live or self._task:
            return  # Already running

        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=4,
            transient=False,
            auto_refresh=True
        )

        self._task = asyncio.create_task(self._run_live())

    async def _run_live(self) -> None:
        """Run live display loop."""
        try:
            self._live.start()
            # Keep alive until stopped
            while True:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            if self._live:
                self._live.stop()

    async def stop(self) -> None:
        """Stop live display."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._live:
            self._live.stop()
            self._live = None
