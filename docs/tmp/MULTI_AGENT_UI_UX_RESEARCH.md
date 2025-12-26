# Multi-Agent Communication UI/UX Research
## Visualizing Agent Hierarchies in CLI Tools

**Research Date:** December 2025
**Focus:** Terminal UI patterns for parent→child agent communication, task delegation, and progress visualization

---

## Executive Summary

Modern CLI tools use consistent visual patterns to represent multi-agent communication:

1. **Hierarchical Tree View** - Best for showing parent-child relationships and nested task execution
2. **Live Progress Display** - Real-time status updates using Rich's `Live`+`Group` pattern
3. **Event-Driven Updates** - Async event buses broadcasting tool execution states
4. **Color-Coded States** - Visual indicators for pending/running/completed/error states
5. **Spinner + Progress Combo** - Spinners for indeterminate work, bars for determinate progress

**Key Finding:** Most production tools (Claude Desktop, Cursor, K9s) use **tree-based hierarchies with event-driven state changes**, not polling. This aligns perfectly with Capybara's EventBus architecture.

---

## 1. Real-World Implementation Patterns

### 1.1 Claude Desktop / Claude Code

**Architecture:**
- Parent agent maintains global context and planning
- Child agents (subagents) execute focused tasks in isolation
- Live progress panel shows each child's status

**Visual Indicators:**
```
┌─ Parent Agent
│  Status: Waiting for children
│
├─ Child 1: Research Task
│  ▶ read_file → ✓
│  ▶ grep → ✓
│  Status: Running [████░░░░] 60%
│
└─ Child 2: Implementation
   Status: Pending (waiting for parent)
```

**Key Features:**
- Context pills showing which files each agent accessed
- Step counters: `[Agent 1] Analyzing requirements... (Step 1/8)`
- Real-time status transitions
- Live output logs with color coding

**Source:** [Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk), [Claude Subagents Guide](https://www.cursor-ide.com/blog/claude-subagents)

---

### 1.2 Cursor IDE

**Architecture:**
- Lead Agent (orchestrator) maintains global state
- Multiple background agents run in parallel (up to 8)
- Each agent operates in isolated sandbox (git worktrees or remote)
- Progress panel shows all agents simultaneously

**Visual Display:**
```
Agent View Sidebar:
┌─ Agent 1 [COMPLETED] ✓
│  Steps: 8/8
│  Output: "Generated auth module"
│
├─ Agent 2 [RUNNING] ▶
│  Steps: 5/12
│  Current: "Generating tests..."
│
└─ Agent 3 [QUEUED] ⏳
   Ready to start
```

**Status Format:** `[Agent N] <action>... (Step X/Y)`

**Key Innovation:**
- Parallel multi-agent execution with isolation
- Per-agent step progression tracking
- Global orchestrator state tracking completed/pending subtasks

**Source:** [Cursor 2.0: Multi-Agent Coding Setup](https://mashblog.com/posts/cursor-2-multi-setup), [Mastering Cursor IDE](https://medium.com/@roberto.g.infante/mastering-cursor-ide-10-best-practices-building-a-daily-task-manager-app-0b26524411c1)

---

### 1.3 Kubernetes / K9s

**Pattern:** Resource hierarchy with live status updates

```
NAMESPACE  NAME           READY  UP-TO-DATE  AVAILABLE
default    parent-job     0/1    1           0
├── child-job-1          1/1    1           1      ✓
├── child-job-2          0/1    1           0      ▶
└── child-job-3          0/1    0           0      ⏳
```

**K9s Features:**
- Real-time resource monitoring
- Color-coded status: green (ready), yellow (pending), red (error)
- Hierarchical resource viewing
- Live log streaming with namespace isolation

**Relevance:** K9s demonstrates terminal UI patterns for managing distributed systems with parent-child relationships.

**Source:** [K9s - Manage Your Kubernetes Clusters](https://k9scli.io/), [Kubernetes Visualization Tools](https://www.digitalocean.com/community/conceptual-articles/kubernetes-visualization-tools)

---

## 2. Terminal UI Library Patterns

### 2.1 Rich Library Architecture

**Core Components for Multi-Agent Display:**

#### Tree Widget
```python
from rich.tree import Tree

root = Tree("[bold magenta]Multi-Agent Execution[/bold magenta]")
parent = root.add("[blue]Parent Agent[/blue]")
parent.add("[dim]Waiting for children[/dim]")

child1 = root.add("[green]Child 1: Research[/green]")
child1.add("[cyan]▶ read_file[/cyan]")
child1.add("[green]✓ bash[/green]")
child1.add("[red]✗ network_error[/red]")

child2 = root.add("[yellow]Child 2: Testing[/yellow]")
child2.add("[dim]⏳ Pending[/dim]")

console.print(root)
```

**Visual Output:**
```
🔴 Multi-Agent Execution
├── 🔵 Parent Agent
│   └── ⏳ Waiting for children
├── 🟢 Child 1: Research
│   ├── ▶ read_file
│   ├── ✓ bash
│   └── ✗ network_error
└── 🟡 Child 2: Testing
    └── ⏳ Pending
```

**Advantages:**
- Native hierarchy support
- Custom labels and icons
- Styling per node
- Low memory footprint

**Source:** [Rich Tree Documentation](https://rich.readthedocs.io/en/stable/tree.html), [Rendering Trees in Terminal](https://www.willmcgugan.com/blog/tech/post/rich-tree/), [Practical Rich Guide](https://medium.com/@jainsnehasj6/a-practical-guide-to-rich-12-ways-to-instantly-beautify-your-python-terminal-3a4a3434d04a)

---

#### Live + Group Pattern (Dynamic Updates)

```python
from rich.live import Live
from rich.console import Group
from rich.progress import Progress, TextColumn, BarColumn
from rich.spinner import Spinner

# Create multiple progress objects
parent_progress = Progress(
    TextColumn("[cyan]Parent Agent[/cyan]"),
    BarColumn(),
)
task_parent = parent_progress.add_task("planning", total=100)

child1_progress = Progress(
    TextColumn("[green]Child 1[/green]"),
    BarColumn(),
)
task_child1 = child1_progress.add_task("researching", total=100)

child2_progress = Progress(
    TextColumn("[yellow]Child 2[/yellow]"),
    BarColumn(),
)
task_child2 = child2_progress.add_task("testing", total=100)

# Display all together with single Live instance
async def monitor_agents():
    with Live(
        Group(parent_progress, child1_progress, child2_progress),
        refresh_per_second=4,
        transient=True
    ) as live:
        # Update as events arrive from EventBus
        parent_progress.update(task_parent, advance=25)
        child1_progress.update(task_child1, advance=50)
        child2_progress.update(task_child2, advance=75)
```

**Output:**
```
Parent Agent
████████░░ 25%

Child 1
██████████ 50%

Child 2
███████████████░░ 75%
```

**Key Constraints:**
- Only ONE `Live` instance per console
- Multiple `Progress` objects must share the same `Live`
- Use `Group` (formerly `RenderGroup`) to combine renderables

**Source:** [Rich Progress Documentation](https://rich.readthedocs.io/en/stable/progress.html), [Multiple Progress Bars Discussion](https://github.com/Textualize/rich/discussions/1500), [Dynamic Progress Example](https://github.com/Textualize/rich/blob/master/examples/dynamic_progress.py)

---

#### Nested Panels + Layout

```python
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Console

console = Console()

# Create layout
layout = Layout()
layout.split_column(
    Layout(name="parent"),
    Layout(name="children")
)

# Parent section
parent_content = Panel(
    "[bold blue]Parent Agent[/bold blue]\n"
    "Status: Waiting for 2 children\n"
    "Model: claude-opus-4.5",
    border_style="blue",
    title="Parent"
)
layout["parent"].update(parent_content)

# Children section
layout["children"].split_row(
    Layout(name="child1"),
    Layout(name="child2")
)

child1_content = Panel(
    "[bold green]Child 1: Research[/bold green]\n"
    "▶ bash (5 remaining)\n"
    "[████░░░░] 40%",
    border_style="green",
    title="Child 1"
)
layout["children"]["child1"].update(child1_content)

child2_content = Panel(
    "[bold yellow]Child 2: Testing[/bold yellow]\n"
    "⏳ Queued\n"
    "[░░░░░░░░] 0%",
    border_style="yellow",
    title="Child 2"
)
layout["children"]["child2"].update(child2_content)

console.print(layout)
```

**Visual Output:**
```
┌─ Parent ────────────────────────┐
│ Parent Agent                     │
│ Status: Waiting for 2 children   │
│ Model: claude-opus-4.5           │
└──────────────────────────────────┘

┌─ Child 1 ──────────┐ ┌─ Child 2 ──────────┐
│ Child 1: Research  │ │ Child 2: Testing   │
│ ▶ bash             │ │ ⏳ Queued          │
│ ████░░░░ 40%       │ │ ░░░░░░░░ 0%        │
└────────────────────┘ └────────────────────┘
```

**Source:** [Rich Layout Documentation](https://rich.readthedocs.io/en/stable/layout.html), [Building Rich Console Interfaces](https://medium.com/trabe/building-rich-console-interfaces-in-python-16338cc30eaa)

---

### 2.2 Textual TUI Framework

**Multi-Agent Architecture:**

```python
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, ProgressBar, Label
from textual.reactive import reactive

class AgentStatus(Static):
    """Individual agent status widget."""
    state = reactive("pending")  # pending, running, completed, error

    def render(self):
        icons = {
            "pending": "⏳",
            "running": "▶",
            "completed": "✓",
            "error": "✗"
        }
        colors = {
            "pending": "yellow",
            "running": "blue",
            "completed": "green",
            "error": "red"
        }
        return f"[{colors[self.state]}]{icons[self.state]} {self.id}[/{colors[self.state]}]"

class MultiAgentMonitor(Static):
    """Parent-child agent monitoring."""

    def compose(self) -> ComposeResult:
        with Container(id="parent-section"):
            yield Label("[bold blue]Parent Agent[/bold blue]")
            yield ProgressBar(id="parent_progress")

        with Horizontal(id="children-section"):
            yield AgentStatus(id="child_1")
            yield AgentStatus(id="child_2")
            yield AgentStatus(id="child_3")

    async def update_agent(self, agent_id: str, state: str):
        widget = self.query_one(f"#{agent_id}", AgentStatus)
        widget.state = state
```

**Advantages:**
- Full TUI application framework
- Reactive state management
- Composable widgets
- Mouse support
- Proper terminal handling

**Source:** [Textual ProgressBar Widget](https://textual.textualize.io/widgets/progress_bar/), [Textual Tutorial](https://textual.textualize.io/tutorial/), [Real Python Textual Guide](https://realpython.com/python-textual/)

---

## 3. Color & Visual Encoding Schemes

### 3.1 State Color Mapping

| State | Color | Symbol | Usage |
|-------|-------|--------|-------|
| Pending | Yellow | ⏳ 🟡 | Task waiting in queue |
| Running | Blue/Cyan | ▶ 🔵 | Currently executing |
| Success | Green | ✓ 🟢 | Completed successfully |
| Error | Red | ✗ 🔴 | Failed or error state |
| Waiting | Cyan (dim) | ⌛ | Blocked on parent/dependency |
| Timeout | Orange | ⚠ | Execution timeout |

### 3.2 Tool Execution Indicators

```
Tool Start:  [cyan]▶ tool_name[/cyan]
Tool Done:   [green]✓ tool_name[/green]
Tool Error:  [red]✗ tool_name: error message[/red]
Tool Skip:   [dim]⊘ tool_name[/dim]
```

### 3.3 Hierarchy Indicators

```
Box Drawing Characters:
├── Child item
│   ├── Tool
│   └── Tool
└── Child item

ASCII Fallback:
+-- Child item
|   +-- Tool
|   `-- Tool
`-- Child item
```

---

## 4. Real-Time Progress Visualization Patterns

### 4.1 Event-Driven Architecture (Capybara Model)

**Current Implementation:**

```python
# From delegate.py - lines 85-113
async def display_child_progress():
    """Display child progress with enhanced formatting."""
    parent_agent.console.print(
        "\n[bold cyan]┌─ Delegated Task[/bold cyan]"
    )

    async for event in event_bus.subscribe(child_session_id):
        if event.event_type == EventType.AGENT_START:
            parent_agent.console.print(
                "│ [dim]Child agent started...[/dim]"
            )
        elif event.event_type == EventType.TOOL_START:
            parent_agent.console.print(
                f"│ [cyan]▶ {event.tool_name}[/cyan]"
            )
        elif event.event_type == EventType.TOOL_DONE:
            parent_agent.console.print(
                f"│ [green]✓ {event.tool_name}[/green]"
            )
        elif event.event_type == EventType.TOOL_ERROR:
            error_msg = event.metadata.get("error", "unknown error")
            parent_agent.console.print(
                f"│ [red]✗ {event.tool_name}: {error_msg}[/red]"
            )
        elif event.event_type == EventType.AGENT_DONE:
            parent_agent.console.print(
                "[bold cyan]└─ Task completed[/bold cyan]\n"
            )
            break
```

**Strengths:**
- Async streaming via EventBus
- Real-time event handling
- Clean hierarchical ASCII art
- Matches Capybara's architecture

**Enhancement Opportunities:**
- Add elapsed time tracking
- Show tool duration
- Display token usage per tool
- Add per-agent spinner during thinking

---

### 4.2 Enhanced Multi-Child Display

**Proposed Pattern for Multiple Concurrent Agents:**

```python
from rich.live import Live
from rich.tree import Tree
from rich.spinner import Spinner
from typing import Dict

class ChildAgentDisplays:
    """Manages display for multiple child agents."""

    def __init__(self, parent_console):
        self.console = parent_console
        self.root = Tree("[bold magenta]Multi-Agent Execution[/bold magenta]")
        self.child_nodes: Dict[str, "TreeNode"] = {}

    async def display_all(self, event_bus):
        """Display all children concurrently."""

        with Live(self.root, console=self.console, refresh_per_second=4):
            async for event in event_bus.subscribe_to_all():
                child_id = event.session_id

                # Create child node if new
                if child_id not in self.child_nodes:
                    self.child_nodes[child_id] = self.root.add(
                        f"[bold blue]{child_id}[/bold blue]"
                    )

                child_node = self.child_nodes[child_id]

                # Update based on event type
                if event.event_type == EventType.TOOL_START:
                    child_node.label = f"[blue]{child_id}[/blue] [cyan]▶[/cyan]"
                    child_node.add(f"[cyan]▶ {event.tool_name}[/cyan]")

                elif event.event_type == EventType.TOOL_DONE:
                    # Remove the running tool entry, add completed
                    child_node.label = f"[green]{child_id}[/green] [green]✓[/green]"
                    # Note: Rich Tree doesn't support removing nodes,
                    # so we rebuild or update display
```

**Limitation:** Rich's Tree doesn't support dynamic node updates. Better approach uses Live + Group with multiple Progress objects.

---

### 4.3 Concurrent Agents with Live Progress

```python
from rich.live import Live
from rich.console import Group
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn
from rich.panel import Panel
import asyncio

class MultiAgentVisualizer:
    """Visualize multiple agents with unified Live display."""

    def __init__(self, console, max_agents=8):
        self.console = console
        self.max_agents = max_agents
        self.agents: Dict[str, dict] = {}  # session_id -> progress_task

    async def monitor(self, event_bus):
        """Monitor all agents with single Live instance."""

        # Shared progress object for all agents
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}[/cyan]"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )

        with Live(progress, console=self.console, refresh_per_second=4):
            async for event in event_bus.subscribe_all():
                child_id = event.session_id

                # Create task if new agent
                if child_id not in self.agents:
                    task_id = progress.add_task(
                        f"{child_id[:20]}...",
                        total=100
                    )
                    self.agents[child_id] = {
                        "task_id": task_id,
                        "tool_count": 0,
                        "state": "running"
                    }

                # Update progress based on events
                if event.event_type == EventType.TOOL_DONE:
                    agent = self.agents[child_id]
                    agent["tool_count"] += 1
                    # Advance by approximate amount
                    progress.update(
                        agent["task_id"],
                        advance=10,
                        description=f"{child_id}: {agent['tool_count']} tools"
                    )

                elif event.event_type == EventType.AGENT_DONE:
                    agent = self.agents[child_id]
                    progress.update(
                        agent["task_id"],
                        completed=100,
                        description=f"{child_id} ✓"
                    )
```

---

## 5. CLI Tool Patterns Analysis

### 5.1 Spinner Patterns for Indeterminate Work

**Best Practices:**

| Library | Spinner | Code |
|---------|---------|------|
| Rich | Dots/Line/Dots2 | `Spinner("dots", text="Working...")` |
| Textual | Built-in widget | `Static(Spinner(...))` |
| prompt_toolkit | Progress bar with indeterminate | `ProgressBar(formatter=...)` |

**Visual Examples:**
```
Working...  ⣾  (rotating)
Processing  ⠋  (bouncing)
Thinking    ◐  (smooth rotation)
```

### 5.2 Progress Bar Patterns for Determinate Work

```python
# Simple bar
[████████░░] 80%

# With labels
Downloading [████████░░] 80% (4.2 MB / 5 MB)

# Multiple bars (tool execution steps)
Research      [██████░░░░] 60%
Implementation [████████░░] 80%
Testing       [██░░░░░░░░] 20%
```

### 5.3 Tree View Patterns for Hierarchy

```
Project Structure
├── 📁 src/
│   ├── agent.py ✓
│   ├── tools/
│   │   ├── __init__.py ✓
│   │   └── builtin.py ▶
│   └── memory.py ⏳
├── 📁 tests/
│   ├── test_agent.py ✓
│   └── test_tools.py ✗
└── 📄 README.md ✓
```

---

## 6. Capybara-Specific Integration Recommendations

### 6.1 Enhanced Event Types

Current events in `event_bus.py`:
```python
class EventType(str, Enum):
    TOOL_START = "tool_start"
    TOOL_DONE = "tool_done"
    TOOL_ERROR = "tool_error"
    AGENT_START = "agent_start"
    AGENT_DONE = "agent_done"
```

**Recommended Additions:**
```python
class EventType(str, Enum):
    # Current
    TOOL_START = "tool_start"
    TOOL_DONE = "tool_done"
    TOOL_ERROR = "tool_error"
    AGENT_START = "agent_start"
    AGENT_DONE = "agent_done"

    # New: parent-child relationship
    AGENT_WAITING = "agent_waiting"  # Parent waiting for child
    CHILD_ACCEPTED = "child_accepted"  # Child accepted task

    # New: progress tracking
    TURN_START = "turn_start"  # Start of ReAct turn
    TURN_COMPLETE = "turn_complete"  # End of ReAct turn

    # New: resource tracking
    TOKEN_COUNT = "token_count"  # Tokens used in this step

    # New: timing
    AGENT_TIMEOUT_WARNING = "agent_timeout_warning"  # 80% of timeout reached
```

### 6.2 Enhanced Event Metadata

```python
@dataclass
class Event:
    session_id: str
    event_type: EventType
    tool_name: Optional[str] = None

    # Enhanced metadata
    metadata: dict = field(default_factory=dict)
    # Additional fields for visualization:
    # - duration_ms: float (for tool execution time)
    # - tokens_used: int (for token tracking)
    # - turn_number: int (for ReAct turn progress)
    # - parent_session_id: str (for hierarchy tracking)
    # - message: str (human-readable status)

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

### 6.3 Visualization Module Architecture

```
src/capybara/visualization/
├── __init__.py
├── progress.py          # Progress bar + Group patterns
├── tree_display.py      # Tree-based agent hierarchy
├── events.py            # Event rendering utilities
└── themes.py            # Color schemes and icons
```

---

## 7. Code Examples: Implementation Patterns

### 7.1 Tree-Based Hierarchy (Static)

```python
# Recommended for simple sequential execution
from rich.tree import Tree
from rich.console import Console

def display_delegation_hierarchy(root_session, children_sessions):
    console = Console()

    root = Tree(f"[bold magenta]{root_session['name']}[/bold magenta]")
    root_node = root.add(
        f"[blue]Parent: {root_session['model']}[/blue]"
    )

    for child in children_sessions:
        status_color = "green" if child["status"] == "completed" else "yellow"
        status_icon = "✓" if child["status"] == "completed" else "▶"

        child_node = root.add(
            f"[{status_color}]{status_icon} {child['title']}[/{status_color}]"
        )
        child_node.add(f"[dim]ID: {child['id'][:8]}[/dim]")
        child_node.add(f"[dim]Duration: {child['duration']:.2f}s[/dim]")

    console.print(root)

# Usage
display_delegation_hierarchy(
    parent_session,
    [child1_session, child2_session]
)
```

**Output:**
```
🔴 Parent Agent
├── 🔵 Parent: claude-opus-4.5
├── 🟢 ✓ Research Task
│   ├── ID: abc12345
│   └── Duration: 12.45s
└── 🟡 ▶ Testing Task
    ├── ID: def67890
    └── Duration: 5.32s
```

---

### 7.2 Live Progress with Event Bus

```python
# Recommended for real-time agent monitoring
from rich.live import Live
from rich.console import Group
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn
from rich.text import Text
import asyncio

async def visualize_child_agent(console, event_bus, child_session_id):
    """Stream child agent progress with live updates."""

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}[/cyan]"),
        BarColumn(),
    )

    task_id = progress.add_task("executing", total=None)

    with Live(progress, console=console, refresh_per_second=4):
        tool_count = 0

        async for event in event_bus.subscribe(child_session_id):
            if event.event_type == EventType.TOOL_DONE:
                tool_count += 1
                progress.update(
                    task_id,
                    description=f"Completed {tool_count} tools"
                )

            elif event.event_type == EventType.AGENT_DONE:
                progress.update(task_id, completed=True)
                break

            elif event.event_type == EventType.TOOL_ERROR:
                error_msg = event.metadata.get("error", "unknown")
                progress.update(
                    task_id,
                    description=f"Error: {error_msg}"
                )
                break
```

---

### 7.3 Multi-Child Concurrent Display

```python
# For parallel child agents
from rich.live import Live
from rich.console import Group
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn
import asyncio
from typing import Dict

class MultiChildVisualizer:
    def __init__(self, console, event_bus):
        self.console = console
        self.event_bus = event_bus
        self.children_progress: Dict[str, Progress] = {}
        self.children_tasks: Dict[str, int] = {}

    async def visualize_all(self, child_session_ids: list[str]):
        """Monitor all children concurrently."""

        # Create individual progress objects for each child
        progresses = []
        for child_id in child_session_ids:
            progress = Progress(
                SpinnerColumn(),
                TextColumn(f"[bold]{child_id[:20]}[/bold] {{task.description}}"),
                BarColumn(),
            )
            task_id = progress.add_task("starting", total=None)

            self.children_progress[child_id] = progress
            self.children_tasks[child_id] = task_id
            progresses.append(progress)

        # Display all in single Live
        with Live(Group(*progresses), console=self.console, refresh_per_second=4):
            # Subscribe to all children
            tasks = [
                self._monitor_child(child_id)
                for child_id in child_session_ids
            ]
            await asyncio.gather(*tasks)

    async def _monitor_child(self, child_id: str):
        """Monitor single child agent."""
        progress = self.children_progress[child_id]
        task_id = self.children_tasks[child_id]
        tool_count = 0

        async for event in self.event_bus.subscribe(child_id):
            if event.event_type == EventType.TOOL_DONE:
                tool_count += 1
                progress.update(
                    task_id,
                    description=f"{tool_count} tools completed"
                )
            elif event.event_type == EventType.AGENT_DONE:
                progress.update(
                    task_id,
                    description="✓ Done",
                    completed=True
                )
                break
```

---

## 8. Terminal UI Library Comparison

| Library | Hierarchy | Live Updates | Async Support | Learning Curve | Use Case |
|---------|-----------|--------------|---------------|-----------------|----------|
| **Rich** | Tree + Group | Live display | Good (async iterators) | Low | Progress display, mixed content |
| **Textual** | Custom widgets | Reactive | Excellent | Medium | Full TUI apps, mouse input |
| **Blessed** | Manual | Update methods | Basic | Medium | Simple terminal control |
| **Prompt Toolkit** | Tables | Manual refresh | Good | High | Interactive CLI apps |
| **Click** | None | Limited | None | Low | Command-line argument parsing |

**Recommendation for Capybara:** Rich + async EventBus pattern
- Minimal overhead for progress visualization
- Aligns with existing Capybara architecture
- Easy to extend with nested agents
- Low coupling to core agent logic

---

## 9. Best Practices Summary

### 9.1 Visual Hierarchy

✅ **DO:**
- Use indentation and box drawing for nesting
- Color-code states consistently
- Provide one indicator per state change
- Use symbols (✓, ▶, ✗) universally

❌ **DON'T:**
- Exceed 3 color intensity levels (bright, normal, dim)
- Use blinking or overly animated elements
- Hide critical status information
- Update more than 4 fps (flicker)

### 9.2 Performance

✅ **DO:**
- Refresh at 2-4 fps (not every event)
- Cache progress objects in Live
- Use transient displays for temporary messages
- Aggregate rapid events (multiple tools executed)

❌ **DON'T:**
- Recreate Live instance per event
- Use multiple Live instances (only one active)
- Poll for status (use event-driven)
- Print unbounded output during progress tracking

### 9.3 Information Density

**Good Density:**
```
Child 1: Research  ████████░░ 80%  [4 tools completed, 1 pending]
```

**Poor Density (too much):**
```
Child 1: Research
████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 80% (4/5 tools)
Tokens: 2048/4096
Duration: 12.34s
Status: RUNNING
```

**Poor Density (too little):**
```
Child 1: 80%
```

---

## 10. References & Sources

### Framework Documentation
- [Rich Library - Tree Widget](https://rich.readthedocs.io/en/stable/tree.html)
- [Rich - Progress Display](https://rich.readthedocs.io/en/stable/progress.html)
- [Rich - Layout System](https://rich.readthedocs.io/en/stable/layout.html)
- [Textual TUI Framework](https://textual.textualize.io/)
- [Real Python - Rich Package](https://realpython.com/python-rich-package/)

### Multi-Agent Systems
- [Building Agents with Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Claude Subagents Guide - Cursor IDE](https://www.cursor-ide.com/blog/claude-subagents)
- [OpenCode - Multi-Agent Orchestration](https://github.com/sst/opencode)
- [Multi-Agent Observability for Claude Code](https://github.com/disler/claude-code-hooks-multi-agent-observability)

### Terminal UI Patterns
- [K9s - Kubernetes Terminal UI](https://k9scli.io/)
- [CLI UX Best Practices - Evil Martians](https://evilmartians.com/chronicles/cli-ux-best-practices-3-patterns-for-improving-progress-displays)
- [Kubernetes Visualization Tools](https://www.digitalocean.com/community/conceptual-articles/kubernetes-visualization-tools)

### Rich Library Examples
- [Dynamic Progress Example](https://github.com/Textualize/rich/blob/master/examples/dynamic_progress.py)
- [Multiple Progress Bars Discussion](https://github.com/Textualize/rich/discussions/1500)
- [Building Rich Console Interfaces](https://medium.com/trabe/building-rich-console-interfaces-in-python-16338cc30eaa)

---

## Unresolved Questions

1. **Token Tracking UI:** Should parent show total token usage across all children? How to display per-child token budgets without cluttering?

2. **Deeply Nested Agents:** If child agents delegate to further children (currently disallowed), how would a 3-level hierarchy display? Would tree view still work or need pagination?

3. **Agent Failure Modes:** Should failed child agents show error traces inline in progress tree, or link to separate logs?

4. **Terminal Width Adaptation:** How to collapse/expand hierarchy when terminal width < 80 chars?

5. **Real-Time Filtering:** Should parent be able to hide/show specific children's progress without stopping execution?

---

**Document Generated:** 2025-12-26
**Research Scope:** Multi-agent CLI UI/UX patterns
**Target Implementation:** Capybara EventBus-based visualization enhancement
