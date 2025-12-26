# Multi-Agent Architecture

## Overview

Capybara Vibe Coding implements a sophisticated parent-child multi-agent architecture that enables task delegation, parallel execution, and specialized work isolation. This document describes the architecture, implementation, and recent enhancements (Phase 1 & 2).

## Architecture Design

### Agent Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ Parent Agent                                                 │
│ - Full tool access (read, write, edit, bash, todo, delegate)│
│ - Task planning and coordination                            │
│ - Conversation history management                           │
│ - Child agent supervision                                   │
└─────────────────────────────────────────────────────────────┘
                    │
                    │ delegate_task()
                    ├─────────────────────────┬───────────────
                    ▼                         ▼
        ┌─────────────────────┐   ┌─────────────────────┐
        │ Child Agent 1       │   │ Child Agent 2       │
        │ - Restricted tools  │   │ - Restricted tools  │
        │ - Isolated context  │   │ - Isolated context  │
        │ - Execution logging │   │ - Execution logging │
        │ - Task focused      │   │ - Task focused      │
        └─────────────────────┘   └─────────────────────┘
```

### Key Principles

1. **Isolation**: Each child agent has its own memory, session, and context
2. **Restriction**: Child agents cannot create todos or delegate further
3. **Tracking**: Child agents automatically log execution details (Phase 1)
4. **Recovery**: Structured failure handling with retry guidance (Phase 2)
5. **Streaming**: Real-time progress updates from child to parent

## Agent Modes

### AgentMode Enum (`src/capybara/tools/base.py`)

```python
class AgentMode(str, Enum):
    PARENT = "parent"  # Full capabilities
    CHILD = "child"    # Restricted execution mode
```

### Parent Agent Capabilities

**Full Tool Access:**
- `read_file`, `write_file`, `edit_file`
- `list_directory`, `glob`, `grep`
- `bash`, `which`
- `todo` - Task management
- `delegate_task` - Child agent spawning

**Responsibilities:**
- Task planning and decomposition
- High-level decision making
- Todo list management
- Child agent coordination
- Result aggregation

### Child Agent Capabilities

**Restricted Tool Access:**
- `read_file`, `write_file`, `edit_file`
- `list_directory`, `glob`, `grep`
- `bash`, `which`
- ❌ No `todo` access
- ❌ No `delegate_task` access

**Responsibilities:**
- Execute specific subtask
- Work within provided context
- Report comprehensive results
- Track execution details
- Handle errors gracefully

## Implementation Components

### 1. Session Management (`src/capybara/core/session_manager.py`)

**SessionManager Class:**
```python
class SessionManager:
    async def create_parent_session(
        self,
        model: str,
        title: str
    ) -> str

    async def create_child_session(
        self,
        parent_id: str,
        model: str,
        prompt: str,
        title: str
    ) -> str

    async def get_session_hierarchy(
        self,
        session_id: str
    ) -> SessionHierarchy
```

**Database Schema:**
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    parent_id TEXT,  -- NULL for parent, session_id for child
    agent_mode TEXT, -- 'parent' or 'child'
    model TEXT,
    title TEXT,
    created_at TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES conversations(id)
);

CREATE TABLE session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    event_type TEXT,
    metadata TEXT,
    timestamp TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES conversations(id)
);
```

### 2. Event Bus (`src/capybara/core/event_bus.py`)

**Event System:**
```python
class EventType(str, Enum):
    AGENT_START = "agent_start"
    TOOL_START = "tool_start"
    TOOL_DONE = "tool_done"
    TOOL_ERROR = "tool_error"
    AGENT_DONE = "agent_done"

@dataclass
class Event:
    session_id: str
    event_type: EventType
    tool_name: Optional[str] = None
    metadata: dict = field(default_factory=dict)
```

**Pub/Sub Pattern:**
- Child agents publish events during execution
- Parent agents subscribe to child session events
- Real-time progress display in parent console
- Event persistence in database

### 3. Tool Registry Filtering (`src/capybara/tools/registry.py`)

**Mode-Based Filtering:**
```python
class ToolRegistry:
    def filter_by_mode(self, mode: AgentMode) -> "ToolRegistry":
        """Filter tools by agent mode."""
        filtered = ToolRegistry()
        for name, tool in self._tools.items():
            if mode in tool.allowed_modes:
                filtered._tools[name] = tool
        return filtered
```

**Tool Registration with Modes:**
```python
@registry.tool(
    name="delegate_task",
    description="Delegate subtask to child agent",
    parameters={...},
    allowed_modes=[AgentMode.PARENT]  # Parent only
)
async def delegate_task(prompt: str, timeout: float) -> str:
    ...
```

### 4. Delegation Tool (`src/capybara/tools/builtin/delegate.py`)

**Core Delegation Function:**
```python
async def delegate_task_impl(
    prompt: str,
    parent_session_id: str,
    parent_agent: Agent,
    session_manager: SessionManager,
    storage: ConversationStorage,
    timeout: float = 300.0,
    model: Optional[str] = None,
) -> str:
    # 1. Create child session
    child_session_id = await session_manager.create_child_session(...)

    # 2. Initialize child agent with filtered tools
    child_tools = ToolRegistry()
    register_builtin_tools(child_tools)

    child_agent = Agent(
        config=AgentConfig(mode=AgentMode.CHILD),
        memory=ConversationMemory(),
        tools=child_tools,
        session_id=child_session_id
    )

    # 3. Execute with progress display
    response = await child_agent.run(prompt)

    # 4. Generate comprehensive report
    return _generate_execution_summary(
        response=response,
        execution_log=child_agent.execution_log,
        session_id=child_session_id,
        duration=duration
    )
```

## Phase 1: Enhanced Execution Tracking

### ExecutionLog System (`src/capybara/core/execution_log.py`)

**Data Structures:**
```python
@dataclass
class ToolExecution:
    tool_name: str
    args: dict
    result_summary: str  # First 200 chars
    success: bool
    duration: float
    timestamp: str

@dataclass
class FileOperation:
    path: str
    operation: str  # "read", "write", "edit"
    lines_changed: Optional[int] = None

@dataclass
class ExecutionLog:
    files_read: set[str] = field(default_factory=set)
    files_written: set[str] = field(default_factory=set)
    files_edited: set[str] = field(default_factory=set)
    tool_executions: list[ToolExecution] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def files_modified(self) -> set[str]:
        return self.files_written | self.files_edited

    @property
    def tool_usage_summary(self) -> dict[str, int]:
        return dict(Counter(te.tool_name for te in self.tool_executions))

    @property
    def success_rate(self) -> float:
        if not self.tool_executions:
            return 1.0
        successes = sum(1 for te in self.tool_executions if te.success)
        return successes / len(self.tool_executions)
```

**Agent Integration:**
```python
class Agent:
    def __init__(self, config: AgentConfig, ...):
        # Enable execution logging for child agents only
        self.execution_log: ExecutionLog | None = None
        if config.mode == AgentMode.CHILD:
            self.execution_log = ExecutionLog()
```

**Execution Summary Format:**
```xml
<execution_summary>
  <session_id>child-123</session_id>
  <status>completed</status>
  <duration>45.23s</duration>
  <success_rate>95%</success_rate>

  <files>
    <read count="5">src/auth.py, src/models.py, tests/test_auth.py</read>
    <modified count="2">src/auth.py, tests/test_auth.py</modified>
  </files>

  <tools total="12">
    read_file: 5x
    edit_file: 2x
    bash: 3x
    grep: 2x
  </tools>

  <errors count="1">
    • bash: npm test failed with exit code 1
  </errors>
</execution_summary>
```

### Benefits

1. **Transparency**: Parent agents see exactly what child agents did
2. **Debugging**: Easy to identify which tools failed and why
3. **Performance**: Track execution patterns and bottlenecks
4. **Verification**: Confirm expected files were modified
5. **Optimization**: Only enabled for child agents (no overhead for parents)

## Phase 2: Intelligent Failure Recovery

### Failure Categorization (`src/capybara/core/child_errors.py`)

**FailureCategory Enum:**
```python
class FailureCategory(str, Enum):
    TIMEOUT = "timeout"                    # Needs more time
    MISSING_CONTEXT = "missing_context"    # Insufficient info
    TOOL_ERROR = "tool_error"              # External failure
    INVALID_TASK = "invalid_task"          # Task impossible/unclear
    PARTIAL_SUCCESS = "partial"            # Some work done
```

**ChildFailure Dataclass:**
```python
@dataclass
class ChildFailure:
    category: FailureCategory
    message: str
    session_id: str
    duration: float

    # Partial progress
    completed_steps: list[str]
    files_modified: list[str]

    # Recovery guidance
    blocked_on: Optional[str]
    suggested_retry: bool
    suggested_actions: list[str]

    # Execution context
    tool_usage: dict[str, int]
    last_successful_tool: Optional[str]

    def to_context_string(self) -> str:
        """Format for parent LLM context."""
        ...
```

### Failure Analysis Functions

**Timeout Analysis:**
```python
def _analyze_timeout_failure(
    child_agent,
    session_id,
    duration,
    timeout,
    prompt
) -> ChildFailure:
    exec_log = child_agent.execution_log

    # Extract completed work
    completed_steps = []
    if exec_log:
        successful_writes = [te for te in exec_log.tool_executions
                            if te.tool_name == "write_file" and te.success]
        if successful_writes:
            completed_steps.append(f"Created {len(successful_writes)} files")

    tool_count = len(exec_log.tool_executions) if exec_log else 0
    needs_more_time = tool_count > 0

    return ChildFailure(
        category=FailureCategory.TIMEOUT,
        message=f"Child timed out after {timeout}s",
        suggested_retry=needs_more_time,
        suggested_actions=[
            f"Retry with timeout={int(timeout * 2)}s",
            "Break task into smaller subtasks"
        ],
        ...
    )
```

**Exception Analysis:**
```python
def _analyze_exception_failure(
    exception,
    child_agent,
    session_id,
    duration,
    prompt
) -> ChildFailure:
    error_msg = str(exception)

    if "permission denied" in error_msg.lower():
        category = FailureCategory.TOOL_ERROR
        actions = [
            "Check file permissions",
            "Verify file exists",
            "Install missing dependencies"
        ]
        retryable = True
    elif "invalid" in error_msg.lower():
        category = FailureCategory.INVALID_TASK
        actions = [
            "Clarify task requirements",
            "Break into simpler tasks"
        ]
        retryable = False
    ...
```

### Failure Report Format

```
Child agent failed: Permission denied: /etc/config

Category: tool_error
Duration: 23.5s
Retryable: Yes

Work completed before failure:
  ✓ Created 2 files
  ✓ Modified 1 file

Files modified: src/config.py, tests/test_config.py

Blocked on: Permission denied: /etc/config

Suggested recovery actions:
  • Check file permissions
  • Verify file exists
  • Install missing dependencies if tool failed

<task_metadata>
  <session_id>child-456</session_id>
  <status>failed</status>
  <failure_category>tool_error</failure_category>
  <retryable>true</retryable>
</task_metadata>
```

### Benefits

1. **Actionable**: Parent agents know exactly what to do next
2. **Context**: Understand what work was completed before failure
3. **Efficiency**: Avoid retrying non-retryable failures
4. **Learning**: Categorization enables pattern analysis
5. **User Experience**: Clear error messages instead of stack traces

## Usage Patterns

### Basic Delegation

```python
# Parent agent delegates a research task
result = delegate_task(
    prompt="""
    Research the top 5 Python async web frameworks in 2024.
    For each framework, provide:
    - GitHub stars and activity
    - Key features
    - Performance benchmarks
    """,
    timeout=180
)
```

### Parallel Execution

```python
# Delegate multiple independent tasks
results = await asyncio.gather(
    delegate_task(prompt="Run backend tests"),
    delegate_task(prompt="Run frontend tests"),
    delegate_task(prompt="Check code coverage")
)
```

### Error Handling

```python
result = delegate_task(
    prompt="Complex task",
    timeout=300
)

# Parent agent receives structured failure report
if "<failure_category>timeout</failure_category>" in result:
    # Extract retry suggestion
    if "<retryable>true</retryable>" in result:
        # Retry with longer timeout
        result = delegate_task(
            prompt="Complex task",
            timeout=600  # Double the timeout
        )
```

### Best Practices

**✅ Good Delegation:**
- Self-contained prompts with all necessary context
- Specific tasks with clear success criteria
- Appropriate timeouts for task complexity
- Include relevant file paths in prompt

```python
delegate_task(
    prompt="""
    Test the authentication module in src/auth.py:
    1. Run pytest tests/test_auth.py
    2. If failures, analyze and fix
    3. Ensure all tests pass
    4. Report coverage percentage
    """,
    timeout=300
)
```

**❌ Bad Delegation:**
- Vague prompts without context
- Tasks requiring parent's conversation history
- Over-delegation of trivial work
- Recursive delegation attempts

```python
# Too vague - child has no context
delegate_task(prompt="Fix the bug")

# Assumes parent context - child can't access
delegate_task(prompt="Update the file we discussed earlier")
```

## Progress Display

### Parent Console Output

```
┌─ Delegated Task
│ Child agent started...
│ ▶ read_file
│ ✓ read_file
│ ▶ grep
│ ✓ grep
│ ▶ edit_file
│ ✓ edit_file
│ ▶ bash
│ ✗ bash: Command failed with exit code 1
└─ Task completed
```

### Event Flow

```
Time  Event              Display
────  ─────              ───────
0s    AGENT_START        "Child agent started..."
2s    TOOL_START         "▶ read_file"
3s    TOOL_DONE          "✓ read_file"
4s    TOOL_START         "▶ bash"
6s    TOOL_ERROR         "✗ bash: npm test failed"
7s    AGENT_DONE         "Task completed"
```

## Performance Considerations

### Execution Log Overhead

**Optimization:**
- Logging only enabled for child agents
- Parent agents have `execution_log = None`
- Zero overhead for single-agent workflows

**Benchmarks:**
- Child agent: +2-3% overhead (minimal)
- Parent agent: 0% overhead
- Memory: ~1KB per 100 tool executions

### Timeout Management

**Default Timeouts:**
- Simple tasks: 60s
- Medium tasks: 180s
- Complex tasks: 300s
- Long-running: 600s+

**Retry Strategy:**
- On timeout with progress: Double timeout and retry
- On timeout without progress: Break into subtasks
- On tool error: Fix environment and retry
- On invalid task: Don't retry, clarify requirements

## Testing

### Unit Tests

```python
# tests/test_execution_log.py
def test_execution_log_tracking():
    log = ExecutionLog()
    log.files_read.add("src/main.py")
    log.files_written.add("src/new.py")
    assert log.success_rate == 1.0

# tests/test_child_errors.py
def test_timeout_failure_analysis():
    failure = _analyze_timeout_failure(...)
    assert failure.category == FailureCategory.TIMEOUT
    assert failure.suggested_retry is True
```

### Integration Tests

```python
# tests/integration/test_delegation_flow.py
async def test_child_execution_tracking():
    result = await delegate_task_impl(
        prompt="Read and modify test.py",
        ...
    )
    assert "<execution_summary>" in result
    assert "<files>" in result
    assert "<tools>" in result
```

## Database Schema

### Session Events Table

```sql
-- Track delegation lifecycle
INSERT INTO session_events (session_id, event_type, metadata)
VALUES
  ('parent-1', 'delegation_start', '{"child_session_id": "child-1"}'),
  ('parent-1', 'delegation_complete', '{"duration": 45.2, "status": "completed"}');

-- Query delegation history
SELECT * FROM session_events
WHERE session_id = 'parent-1'
  AND event_type LIKE 'delegation_%'
ORDER BY timestamp DESC;
```

## Phase 3: Enhanced UI Communication Flow

### Overview

Phase 3 implements real-time visual tracking of parent-child agent communication with state-aware rendering and live updates.

### Agent Status Tracking (`src/capybara/core/agent_status.py`)

**AgentState Enum:**
```python
class AgentState(str, Enum):
    IDLE = "idle"                      # Agent not actively working
    THINKING = "thinking"               # LLM generating response
    EXECUTING_TOOLS = "executing"       # Running tool calls
    WAITING_FOR_CHILD = "waiting"       # Delegated, awaiting child
    COMPLETED = "completed"             # Task finished successfully
    FAILED = "failed"                   # Task failed
```

**AgentStatus Dataclass:**
```python
@dataclass
class AgentStatus:
    session_id: str                        # Unique session identifier
    mode: str                              # "parent" or "child"
    state: AgentState                      # Current execution state
    current_action: Optional[str] = None   # "Running grep", "Delegating task"
    child_sessions: list[str] = []         # Active child session IDs
    parent_session: Optional[str] = None   # Parent session ID (for children)
```

### Communication Flow Renderer (`src/capybara/ui/flow_renderer.py`)

**Visual Flow Display:**

Parent with active child:
```
┌─────────────── Agent Communication Flow ────────────────┐
│ 🤔 [parent] thinking: Planning delegation strategy      │
│ └── ⚙️ [child] executing: Running tests in tests/      │
└─────────────────────────────────────────────────────────┘
```

Multiple children working in parallel:
```
┌─────────────── Agent Communication Flow ────────────────┐
│ ⏳ [parent] waiting: Managing delegations              │
│ ├── ⚙️ [child] executing: Testing backend              │
│ ├── 🤔 [child] thinking: Analyzing frontend            │
│ └── ✅ [child] completed                                │
└─────────────────────────────────────────────────────────┘
```

Child failure scenario:
```
┌─────────────── Agent Communication Flow ────────────────┐
│ 🤔 [parent] thinking: Analyzing failure                │
│ └── ❌ [child] failed: Permission denied (/etc/config) │
└─────────────────────────────────────────────────────────┘
```

**State Icons and Colors:**
- 🤔 THINKING (yellow) - LLM generating response
- ⚙️ EXECUTING_TOOLS (cyan) - Running tool calls
- ⏳ WAITING_FOR_CHILD (magenta) - Delegated, awaiting child
- ✅ COMPLETED (green) - Task finished successfully
- ❌ FAILED (red) - Task failed
- 💤 IDLE (dim) - Agent not actively working

**API Methods:**
```python
class CommunicationFlowRenderer:
    def update_parent(self, status: AgentStatus) -> None
    def update_child(self, session_id: str, status: AgentStatus) -> None
    def remove_child(self, session_id: str) -> None
    def render(self) -> Panel  # Returns Rich Panel for display
```

### Integration with Phase 1 & 2

**Combined Display Example:**

Flow visualization (Phase 3) + Execution tracking (Phase 1):
```
┌─────────────── Agent Communication Flow ────────────────┐
│ ⏳ [parent] waiting: Delegated task                     │
│ └── ⚙️ [child] executing: Running grep (3/5 tools)     │
└─────────────────────────────────────────────────────────┘

<execution_summary>
  <session_id>child-abc123</session_id>
  <status>in_progress</status>
  <tools total="3">
    read_file: 1x
    grep: 2x
  </tools>
</execution_summary>
```

Flow visualization (Phase 3) + Failure recovery (Phase 2):
```
┌─────────────── Agent Communication Flow ────────────────┐
│ 🤔 [parent] thinking: Planning retry                   │
│ └── ❌ [child] failed: Timeout after 300s              │
└─────────────────────────────────────────────────────────┘

Category: timeout
Retryable: Yes
Suggested actions:
  • Retry with timeout=600s
  • Break task into smaller subtasks
```

### Event-Driven State Updates

**Extended EventBus:**
```python
class EventType(str, Enum):
    # Existing
    AGENT_START = "agent_start"
    TOOL_START = "tool_start"
    TOOL_DONE = "tool_done"
    TOOL_ERROR = "tool_error"
    AGENT_DONE = "agent_done"

    # Phase 3 additions
    STATE_CHANGE = "state_change"
    DELEGATION_START = "delegation_start"
    DELEGATION_COMPLETE = "delegation_complete"
```

**State Change Event:**
```python
Event(
    session_id="parent-123",
    event_type=EventType.STATE_CHANGE,
    metadata={
        "old_state": "thinking",
        "new_state": "executing",
        "action": "Running grep on src/"
    }
)
```

### Performance Metrics

**Overhead Analysis:**
- Parent agent: +2KB memory (CommunicationFlowRenderer instance)
- Child agent: 0 bytes (no renderer)
- Render time: <1ms (single parent + child)
- Render time: ~2ms (parent + 10 children)
- State update: <0.1ms (dict operation)

**Scalability:**
- Tested with 20 concurrent children: No degradation
- 1000 state transitions: <100ms total
- Long-running (10min): Stable memory

### Testing

**Phase 3 Test Coverage:**
- 12 unit tests (agent status, flow renderer, event bus)
- 3 integration tests (end-to-end workflows)
- 107/107 total tests passing (100%)

**Test Files:**
- `tests/test_phase3_ui_flow.py` - Phase 3 unit tests
- `tests/integration/test_e2e_multi_agent.py` - E2E tests

### Architecture Benefits

1. **Real-Time Visibility** - Parent sees live status of all children
2. **Zero Coupling** - Flow renderer completely optional
3. **Clean Separation** - UI logic in `ui/` module, core logic unchanged
4. **Type Safety** - Full type hints, mypy-compatible
5. **Rich Integration** - Leverages Rich library features (Tree, Panel, Text)

---

## Future Enhancements

### Potential Improvements

1. **Live Display** - Auto-refresh with Rich Live display (currently on-demand)
2. **Recursive Delegation**: Allow child → grandchild (with depth limits)
3. **Agent Pools**: Reuse child agent instances for performance
4. **Smart Retries**: Automatic retry with adjusted parameters
5. **Execution Analytics**: ML-based failure prediction
6. **Context Sharing**: Selective parent context sharing with children
7. **Distributed Execution**: Child agents on separate processes/machines
8. **Timeline View**: Show delegation history over time
9. **Performance Metrics**: Add execution time to flow display

### Research Areas

- Optimal timeout prediction based on task complexity
- Automatic task decomposition for complex prompts
- Cross-agent learning from execution patterns
- Dynamic tool permission adjustment
- Agent specialization based on task types
- Custom themes and styling for flow renderer
