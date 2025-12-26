# Multi-Agent UI Code Examples
## Ready-to-Use Patterns for Capybara

**Purpose:** Concrete, copy-paste-ready code examples for implementing multi-agent visualization in Capybara

---

## 1. Simple Sequential Display (Current Pattern)

**Use Case:** Single child agent at a time, linear execution

```python
# File: src/capybara/visualization/sequential_display.py

from rich.console import Console
from capybara.core.event_bus import Event, EventType

async def display_single_child(console: Console, event_bus, child_session_id: str):
    """Display one child agent's execution with box-drawing hierarchy.

    Output:
    ┌─ Delegated Task
    │ ▶ read_file
    │ ✓ bash
    │ ▶ grep
    └─ Task completed
    """
    console.print("\n[bold cyan]┌─ Delegated Task[/bold cyan]")

    async for event in event_bus.subscribe(child_session_id):
        if event.event_type == EventType.AGENT_START:
            console.print("│ [dim]Child agent started...[/dim]")

        elif event.event_type == EventType.TOOL_START:
            console.print(f"│ [cyan]▶ {event.tool_name}[/cyan]")

        elif event.event_type == EventType.TOOL_DONE:
            duration = event.metadata.get("duration_ms", 0)
            console.print(
                f"│ [green]✓ {event.tool_name}[/green]"
                f" [dim]({duration}ms)[/dim]"
            )

        elif event.event_type == EventType.TOOL_ERROR:
            error = event.metadata.get("error", "unknown")
            console.print(
                f"│ [red]✗ {event.tool_name}[/red]"
                f" [dim]{error}[/dim]"
            )

        elif event.event_type == EventType.AGENT_DONE:
            console.print("[bold cyan]└─ Task completed[/bold cyan]\n")
            break
```

---

## 2. Tree-Based Hierarchy Display

**Use Case:** Show parent-child relationship after execution completes

```python
# File: src/capybara/visualization/tree_hierarchy.py

from rich.tree import Tree
from rich.console import Console
from datetime import datetime

def display_session_hierarchy(console: Console, parent_session: dict, children_sessions: list[dict]):
    """Display execution hierarchy as tree after completion.

    Output:
    🔴 Multi-Agent Execution
    ├── 🔵 Parent Agent
    │   ├── Model: claude-opus-4.5
    │   └── Duration: 45.23s
    ├── 🟢 ✓ Research Task
    │   ├── ID: abc12345
    │   ├── Tools: 4
    │   └── Duration: 12.45s
    └── 🟡 ✓ Implementation
        ├── ID: def67890
        ├── Tools: 6
        └── Duration: 32.78s
    """
    root = Tree("[bold magenta]🔴 Multi-Agent Execution[/bold magenta]")

    # Parent node
    parent_node = root.add(
        f"[bold blue]🔵 Parent Agent[/bold blue]\n"
        f"Model: {parent_session['model']}\n"
        f"Duration: {parent_session.get('duration_sec', 0):.2f}s"
    )

    # Child nodes
    status_colors = {
        "completed": "green",
        "error": "red",
        "timeout": "orange",
    }
    status_icons = {
        "completed": "✓",
        "error": "✗",
        "timeout": "⚠",
    }

    for child in children_sessions:
        status = child.get("status", "unknown")
        color = status_colors.get(status, "yellow")
        icon = status_icons.get(status, "▶")

        child_node = root.add(
            f"[{color}]{icon} {child['title']}[/{color}]\n"
            f"ID: [dim]{child['id'][:8]}...[/dim]\n"
            f"Tools: {len(child.get('tool_history', []))}\n"
            f"Duration: [dim]{child.get('duration_sec', 0):.2f}s[/dim]"
        )

        # Show tool chain
        for tool in child.get("tool_history", [])[:5]:  # First 5 tools
            tool_status = "✓" if tool.get("status") == "success" else "✗"
            child_node.add(
                f"[dim]{tool_status} {tool['name']} "
                f"({tool.get('duration_ms', 0)}ms)[/dim]"
            )

        if len(child.get("tool_history", [])) > 5:
            remaining = len(child["tool_history"]) - 5
            child_node.add(f"[dim]... and {remaining} more[/dim]")

    console.print(root)
```

---

## 3. Live Progress with Multiple Children

**Use Case:** Real-time monitoring of 2-8 concurrent child agents

```python
# File: src/capybara/visualization/concurrent_progress.py

from rich.live import Live
from rich.console import Group
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    SpinnerColumn,
    TimeRemainingColumn,
)
from rich.panel import Panel
from capybara.core.event_bus import EventType
import asyncio
from typing import Dict

class ConcurrentAgentVisualizer:
    """Display multiple child agents with unified Live display."""

    def __init__(self, console):
        self.console = console
        self.agent_progress: Dict[str, Progress] = {}
        self.agent_tasks: Dict[str, int] = {}
        self.agent_tool_counts: Dict[str, int] = {}

    async def visualize(self, event_bus, child_session_ids: list[str]):
        """Monitor all children concurrently.

        Output:
        Parent Agent
        ████████░░ 45%

        Child 1: Research
        ██████████ 100% (4 tools completed)

        Child 2: Testing
        ███████░░░ 70% (3 tools completed)

        Child 3: Docs
        ██░░░░░░░░ 20% (1 tool completed)
        """
        # Create progress objects for each child
        progresses = []
        for child_id in child_session_ids:
            progress = Progress(
                SpinnerColumn(),
                TextColumn(
                    f"[bold cyan]{child_id}[/bold cyan] "
                    "{{task.description}}"
                ),
                BarColumn(bar_width=20),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            )
            task_id = progress.add_task("starting", total=100, visible=True)

            self.agent_progress[child_id] = progress
            self.agent_tasks[child_id] = task_id
            self.agent_tool_counts[child_id] = 0
            progresses.append(progress)

        # Add parent progress at top
        parent_progress = Progress(
            TextColumn("[bold magenta]Parent Agent[/bold magenta]"),
            BarColumn(bar_width=20),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        parent_task = parent_progress.add_task("delegating", total=100)
        progresses.insert(0, parent_progress)

        # Display all together
        with Live(
            Group(*progresses),
            console=self.console,
            refresh_per_second=4
        ) as live:
            # Monitor all children concurrently
            tasks = [
                self._monitor_child(event_bus, child_id)
                for child_id in child_session_ids
            ]

            # Wait for all or timeout
            try:
                await asyncio.gather(*tasks)
                parent_progress.update(parent_task, completed=100)
            except asyncio.TimeoutError:
                parent_progress.update(parent_task, description="timed out")

    async def _monitor_child(self, event_bus, child_id: str):
        """Monitor single child's progress."""
        progress = self.agent_progress[child_id]
        task_id = self.agent_tasks[child_id]

        async for event in event_bus.subscribe(child_id):
            if event.event_type == EventType.TOOL_DONE:
                self.agent_tool_counts[child_id] += 1
                tool_count = self.agent_tool_counts[child_id]

                # Estimate progress: 100 / tool_count steps
                progress.update(
                    task_id,
                    description=f"{tool_count} tools completed",
                    advance=min(100 / max(tool_count, 1), 25),
                )

            elif event.event_type == EventType.TOOL_ERROR:
                error = event.metadata.get("error", "unknown")
                progress.update(
                    task_id,
                    description=f"[red]Error: {error}[/red]",
                )
                break

            elif event.event_type == EventType.AGENT_DONE:
                progress.update(
                    task_id,
                    description="✓ completed",
                    completed=100,
                )
                break
```

**Usage:**
```python
visualizer = ConcurrentAgentVisualizer(console)
await visualizer.visualize(event_bus, ["child_1", "child_2", "child_3"])
```

---

## 4. Inline Status During Thinking

**Use Case:** Show parent's status while waiting for children

```python
# File: src/capybara/visualization/parent_status.py

from rich.spinner import Spinner
from rich.text import Text
from rich.console import Console
from rich.live import Live
import asyncio

async def show_parent_thinking(
    console: Console,
    parent_prompt: str,
    children_count: int,
    timeout: float = 300.0
):
    """Show parent agent thinking/planning while delegating.

    Output:
    🤔 Planning task distribution...

    Will delegate to: 3 child agents
    - Research: Query documentation
    - Implementation: Write code
    - Testing: Create test suite

    ⏳ Waiting for children... (elapsed: 12.34s)
    """
    console.print(f"\n[bold cyan]🤔 Planning task distribution...[/bold cyan]")
    console.print(f"\nWill delegate to: [bold]{children_count}[/bold] child agents")

    # Show what each child will do (parsed from parent_prompt)
    tasks = _parse_delegation_tasks(parent_prompt)
    for i, task in enumerate(tasks[:3], 1):
        console.print(f"  [dim]{i}.[/dim] {task}")

    # Spinner for waiting
    spinner = Spinner("dots", text="Waiting for children...", style="yellow")

    start_time = asyncio.get_event_loop().time()

    with Live(spinner, console=console, refresh_per_second=1) as live:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                console.print(
                    f"[red]⚠ Timeout after {elapsed:.2f}s[/red]"
                )
                break

            live.update(
                Spinner(
                    "dots",
                    text=f"Waiting for children... (elapsed: {elapsed:.2f}s)",
                    style="yellow"
                )
            )
            await asyncio.sleep(0.5)

def _parse_delegation_tasks(prompt: str) -> list[str]:
    """Extract subtasks from delegation prompt."""
    # Simple heuristic: split on "1.", "2.", etc. or bullet points
    lines = prompt.split("\n")
    tasks = []
    for line in lines:
        line = line.strip()
        if line and any(line.startswith(p) for p in ["- ", "* ", "1.", "2.", "3."]):
            tasks.append(line.lstrip("-*123.").strip())
    return tasks[:10]
```

---

## 5. Error Display with Context

**Use Case:** Show child errors with surrounding context

```python
# File: src/capybara/visualization/error_display.py

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.traceback import Traceback

def display_child_error(
    console: Console,
    child_id: str,
    error_type: str,
    error_message: str,
    context: dict = None,
):
    """Display child agent error with context.

    Output:
    ┌─ ✗ Child Agent Failed
    │
    │ Child ID: abc12345
    │ Error Type: TimeoutError
    │ Message: Agent execution exceeded 300s timeout
    │
    │ Last Tool Executed: bash (42.5s)
    │ Tools Completed: 4/8
    │
    └─ Check child session logs for details
    """
    context = context or {}

    error_panel = Panel(
        f"[red]✗ Child Agent Failed[/red]\n\n"
        f"[bold]Child ID:[/bold] {child_id}\n"
        f"[bold]Error Type:[/bold] [red]{error_type}[/red]\n"
        f"[bold]Message:[/bold] {error_message}\n\n"
        f"[bold]Context:[/bold]\n"
        f"  Last Tool: {context.get('last_tool', 'N/A')}\n"
        f"  Duration: {context.get('duration_sec', 'N/A')}s\n"
        f"  Tools Completed: {context.get('tools_done', 0)}/{context.get('tools_total', '?')}\n\n"
        f"[dim]Check logs for detailed traceback[/dim]",
        border_style="red",
        title="[red]Error[/red]",
    )

    console.print(error_panel)
```

---

## 6. Token Usage Tracker

**Use Case:** Show token consumption across agents

```python
# File: src/capybara/visualization/token_tracker.py

from rich.table import Table
from rich.console import Console
from typing import Dict

def display_token_usage(
    console: Console,
    parent_tokens: Dict[str, int],
    children_tokens: Dict[str, Dict[str, int]],
    token_limits: Dict[str, int],
):
    """Display token usage per agent.

    Output:
    Token Usage Summary
    ┌──────────────────┬─────────┬────────┬──────────┐
    │ Agent            │ Tokens  │ Limit  │ Usage %  │
    ├──────────────────┼─────────┼────────┼──────────┤
    │ Parent           │ 2,048   │ 4,096  │ 50.0%    │
    │ Child 1: Res     │ 1,234   │ 4,096  │ 30.1%    │
    │ Child 2: Impl    │ 3,456   │ 4,096  │ 84.4%    │
    │ Child 3: Test    │ 512     │ 4,096  │ 12.5%    │
    ├──────────────────┼─────────┼────────┼──────────┤
    │ TOTAL            │ 7,250   │ 16,384 │ 44.2%    │
    └──────────────────┴─────────┴────────┴──────────┘
    """
    table = Table(title="Token Usage Summary", show_header=True)

    table.add_column("Agent", style="cyan", no_wrap=False)
    table.add_column("Tokens", justify="right", style="magenta")
    table.add_column("Limit", justify="right", style="dim")
    table.add_column("Usage %", justify="right")

    # Parent
    parent_used = parent_tokens.get("used", 0)
    parent_limit = token_limits.get("parent", 4096)
    parent_pct = 100 * parent_used / max(parent_limit, 1)
    parent_color = "green" if parent_pct < 70 else "yellow" if parent_pct < 85 else "red"

    table.add_row(
        "Parent",
        f"[magenta]{parent_used:,}[/magenta]",
        f"{parent_limit:,}",
        f"[{parent_color}]{parent_pct:.1f}%[/{parent_color}]",
    )

    # Children
    total_used = parent_used
    total_limit = parent_limit

    for child_id, tokens in children_tokens.items():
        child_used = tokens.get("used", 0)
        child_limit = token_limits.get("child", 4096)
        child_pct = 100 * child_used / max(child_limit, 1)
        child_color = (
            "green" if child_pct < 70
            else "yellow" if child_pct < 85
            else "red"
        )

        table.add_row(
            f"{child_id[:15]}",
            f"[magenta]{child_used:,}[/magenta]",
            f"{child_limit:,}",
            f"[{child_color}]{child_pct:.1f}%[/{child_color}]",
        )

        total_used += child_used
        total_limit += child_limit

    # Total row
    total_pct = 100 * total_used / max(total_limit, 1)
    total_color = (
        "green" if total_pct < 70
        else "yellow" if total_pct < 85
        else "red"
    )

    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold magenta]{total_used:,}[/bold magenta]",
        f"[bold]{total_limit:,}[/bold]",
        f"[bold {total_color}]{total_pct:.1f}%[/bold {total_color}]",
    )

    console.print(table)
```

---

## 7. Integration with Delegate Tool

**Use Case:** Drop-in enhancement to `delegate.py`

```python
# File: src/capybara/tools/builtin/delegate_enhanced.py

# Replace display_child_progress() in delegate.py with:

from capybara.visualization.concurrent_progress import ConcurrentAgentVisualizer

async def display_child_progress_enhanced():
    """Enhanced progress display with multiple concurrent agents."""

    # Single child (current behavior)
    if len(child_session_ids) == 1:
        await display_single_child(
            parent_agent.console,
            event_bus,
            child_session_ids[0]
        )
    # Multiple children (new behavior)
    else:
        visualizer = ConcurrentAgentVisualizer(parent_agent.console)
        await visualizer.visualize(event_bus, child_session_ids)

    # Then show summary
    display_session_hierarchy(
        parent_agent.console,
        parent_session,
        children_sessions
    )
```

---

## 8. Real-Time Statistics Ticker

**Use Case:** Show live metrics while agents run

```python
# File: src/capybara/visualization/stats_ticker.py

from rich.live import Live
from rich.console import Console
from rich.text import Text
from datetime import datetime
import time

class StatsTicker:
    """Display real-time statistics during multi-agent execution."""

    def __init__(self, console: Console):
        self.console = console
        self.start_time = time.time()
        self.tool_executions = 0
        self.tools_per_second = 0.0

    def update(self):
        """Render current statistics."""
        elapsed = time.time() - self.start_time
        self.tools_per_second = self.tool_executions / max(elapsed, 1)

        stats_text = (
            f"[dim]Elapsed:[/dim] {elapsed:.1f}s | "
            f"[dim]Tools:[/dim] {self.tool_executions} | "
            f"[dim]Rate:[/dim] {self.tools_per_second:.2f} tools/sec"
        )

        return Text(stats_text, style="dim cyan")

    async def run_ticker(self, event_bus, timeout=300):
        """Update stats in bottom bar during execution."""
        with Live(self.update(), console=self.console, refresh_per_second=1):
            start = time.time()

            async for event in event_bus.subscribe_all():
                if event.event_type == "tool_done":
                    self.tool_executions += 1

                # Update display
                elapsed = time.time() - self.start_time
                if elapsed > timeout:
                    break

                # Periodically render (every 1s)
                if int(elapsed) % 1 == 0:
                    # Would update Live display here
                    pass
```

---

## 9. Color Scheme Definitions

**Use Case:** Consistent theming across visualizations

```python
# File: src/capybara/visualization/themes.py

from enum import Enum
from typing import Dict

class AgentState(str, Enum):
    """Agent execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"
    WAITING = "waiting"  # Parent waiting for child

# Color mapping per state
STATE_COLORS: Dict[AgentState, str] = {
    AgentState.PENDING: "yellow",
    AgentState.RUNNING: "blue",
    AgentState.COMPLETED: "green",
    AgentState.ERROR: "red",
    AgentState.TIMEOUT: "orange",
    AgentState.WAITING: "cyan",
}

# Icons per state
STATE_ICONS: Dict[AgentState, str] = {
    AgentState.PENDING: "⏳",
    AgentState.RUNNING: "▶",
    AgentState.COMPLETED: "✓",
    AgentState.ERROR: "✗",
    AgentState.TIMEOUT: "⚠",
    AgentState.WAITING: "⌛",
}

# Box drawing characters
BOX_TOP = "┌─"
BOX_MID = "│"
BOX_BOT = "└─"

def format_agent_status(state: AgentState, agent_id: str) -> str:
    """Format agent status with color and icon."""
    color = STATE_COLORS[state]
    icon = STATE_ICONS[state]
    return f"[{color}]{icon} {agent_id}[/{color}]"

# Color for different agent hierarchy levels
HIERARCHY_COLORS = {
    "parent": "magenta",
    "child_1": "green",
    "child_2": "yellow",
    "child_3": "cyan",
    "child_n": "blue",
}
```

---

## 10. Integration Checklist

**To use these patterns in Capybara:**

- [ ] Create `src/capybara/visualization/` directory
- [ ] Add `__init__.py` with exports
- [ ] Copy code examples as separate modules
- [ ] Update `delegate.py` to use enhanced display
- [ ] Add optional `--visualize` CLI flag
- [ ] Document new event types in `event_bus.py`
- [ ] Add tests in `tests/visualization/`
- [ ] Update CLAUDE.md with visualization patterns

---

**Last Updated:** 2025-12-26
**Status:** Ready for implementation
