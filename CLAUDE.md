# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Capybara Vibe Coding** is an async-first AI-powered CLI coding assistant implementing the ReAct agent pattern with multi-agent delegation support. The system enables a parent agent to delegate complex tasks to autonomous sub-agents that work independently and return comprehensive work reports.

## Development Commands

### Installation & Setup

```bash
# Install package in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Initialize configuration
capybara init
# This creates ~/.capybara/config.yaml
```

### Running the CLI

```bash
# Interactive chat mode
capybara chat

# Interactive chat with specific model
capybara chat --model gpt-4o

# Interactive chat with operation mode (standard/safe/plan/auto)
capybara chat --mode safe

# Run single prompt and exit
capybara run "your prompt here"

# Resume previous session
capybara sessions              # List sessions
capybara resume <session_id>   # Resume specific session

# Configure default model
capybara model                 # Interactive selection
capybara model gpt-4o         # Set directly
```

### Testing

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_agent.py

# Run tests with coverage
pytest --cov=src/capybara --cov-report=html

# Skip slow tests
pytest -m "not slow"

# Skip integration tests
pytest -m "not integration"

# Run only integration tests
pytest -m integration
```

### Code Quality

```bash
# Run linter
ruff check src tests

# Auto-fix linting issues
ruff check --fix src tests

# Format code
ruff format src tests

# Type checking
mypy src/capybara
```

## Architecture Overview

### Core Architecture: Parent-Child Agent System

The system implements a hierarchical agent architecture where:

1. **Parent Agent** (`AgentMode.PARENT`):
   - Handles user interaction and conversation flow
   - Decides when to create todo lists for complex tasks
   - Can delegate self-contained tasks to child agents via `sub_agent` tool
   - Waits for child completion and receives comprehensive work reports
   - Has access to `CommunicationFlowRenderer` for UI updates

2. **Child Agent** (`AgentMode.CHILD`):
   - Executes delegated tasks autonomously without user interaction
   - Works with full tool access (read, write, edit, bash, grep, etc.)
   - CANNOT delegate further (no `sub_agent` tool access)
   - CANNOT create/manage todo lists
   - Maintains `ExecutionLog` to track all actions
   - Returns detailed work report to parent on completion

### Key Modules

#### `src/capybara/core/agent/`
- `agent.py`: Main `Agent` class orchestrating execution flow
- `state_manager.py`: Manages agent state transitions and event publishing
- `status.py`: Defines `AgentState` and `AgentStatus` data structures
- `ui_renderer.py`: Handles UI rendering for parent agents

#### `src/capybara/core/delegation/`
- `session_manager.py`: Manages parent-child session hierarchy
- `event_bus.py`: Event-driven communication between agents

#### `src/capybara/tools/builtin/delegation/`
- `sub_agent_tool.py`: Core delegation tool implementation
- `agent_setup.py`: Creates configured child agents
- `progress_display.py`: Real-time progress tracking for child agents
- `work_report.py`: Generates comprehensive work summaries
- `error_handler.py`: Handles timeout and execution errors
- `failure_analysis.py`: Analyzes and categorizes failures

#### `src/capybara/memory/`
- `window.py`: Token-based sliding window memory with automatic trimming
- `storage.py`: SQLite-based conversation persistence with session management

#### `src/capybara/providers/`
- `router.py`: LiteLLM-based multi-provider routing with fallback support

#### `src/capybara/tools/`
- `registry.py`: Tool registry with OpenAI schema format and mode-based filtering
- `builtin/`: Core tools (bash, filesystem, search_replace, todo_state)
- `mcp/`: Model Context Protocol integration for external tools

#### `src/capybara/ui/`
- `flow_renderer.py`: Real-time communication flow visualization
- `todo_panel.py`: Todo list panel rendering
- `todo_live_panel.py`: Live updating todo list panel

### Tool Access Control

Tools are filtered by agent mode using `allowed_modes`:

```python
# Example: Sub-agent tool only for parent agents
@registry.tool(
    name="sub_agent",
    description="...",
    parameters={...},
    allowed_modes=[AgentMode.PARENT]  # Only parent can delegate
)
```

### Operation Modes

The CLI supports multiple operation modes:

- **standard**: Full tool access, default behavior
- **safe**: All write operations require user approval (ASK permission)
- **plan**: Read-only mode, dangerous tools (bash, write_file, edit_file) removed from registry
- **auto**: Future mode for automatic complexity detection

### Logging Architecture

**Session-based logging**: Each agent gets a `SessionLoggerAdapter` that writes to:
- Session-specific log file: `~/.capybara/logs/sessions/<session_id>.log`
- Child agents write to parent's log file (via `parent_session_id`)
- Enables single consolidated log per conversation session

**Log types**:
- Delegation events (start/end/timeout)
- Tool execution (calls, results, errors)
- State transitions
- Error analysis and failure categorization

### Configuration System

Configuration lives in `~/.capybara/config.yaml`:

```yaml
providers:
  - name: default
    model: gpt-4o
    api_key: sk-...
    rpm: 3500
    tpm: 90000

memory:
  max_tokens: 100000
  persist: true

tools:
  bash_enabled: true
  bash_timeout: 120
  security:
    bash:
      permission: ASK  # AUTO, ASK, DENY

mcp:
  enabled: false
  servers: {}

features:
  auto_complexity_detection: false
  auto_delegation: false
  unified_ui: false
```

### MCP (Model Context Protocol) Integration

The system supports external MCP servers for extending tool capabilities:

- `src/capybara/tools/mcp/client.py`: MCP client implementation
- `src/capybara/tools/mcp/bridge.py`: Bridges MCP tools into the registry
- Configure servers in `config.yaml` under `mcp.servers`
- Tools from MCP servers automatically registered when enabled

### Tool Output Display

The system provides immediate visual feedback for certain tool executions:

**File Edit Diff Display** (`edit_file` tool):
- Displays formatted diff output immediately after file modification
- Shows in a green-bordered Rich panel with syntax highlighting
- Color scheme:
  - **Green**: additions (+)
  - **Red strikethrough**: deletions (-)
  - **Dim**: context lines and line numbers
  - **Yellow**: change summary (⎿)
  - **Bold**: header (Update(filename))
- Output is persistent in terminal history for easy review
- Automatically rendered by `ToolExecutor` when `edit_file` succeeds

**Implementation**:
- `src/capybara/ui/diff_renderer.py`: Rich-formatted diff rendering
- `src/capybara/core/execution/tool_executor.py`: Detects and renders diffs
- `src/capybara/tools/builtin/diff_formatter.py`: Generates diff text

**Example output**:
```
╭──────────────────────── File Modified: /path/to/file.py ─────────────────────╮
│                                                                              │
│  Update(file.py)                                                             │
│    ⎿  Added 1 line, Removed 1 line                                           │
│          1  def function():                                                  │
│            -    old_implementation()                                         │
│          2 +    new_implementation()                                         │
│          3      return True                                                  │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Implementation Guidelines

### Adding New Tools

Tools must be async and registered with proper mode restrictions:

```python
@registry.tool(
    name="my_tool",
    description="Tool description for LLM",
    parameters={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "Param description"}
        },
        "required": ["param"]
    },
    allowed_modes=[AgentMode.PARENT, AgentMode.CHILD]  # Optional mode filter
)
async def my_tool(param: str) -> str:
    """Implementation."""
    return result
```

### Testing Patterns

- Use `pytest-asyncio` for async tests
- Mock LLM responses in unit tests
- Use `conftest.py` for shared fixtures
- Separate unit tests from integration tests using markers
- Test both parent and child agent modes

### Event-Driven Communication

Agents communicate via event bus for state changes:

```python
self.event_bus.publish(Event(
    type=EventType.DELEGATION_START,
    session_id=session_id,
    data={"child_id": child_id}
))
```

## Project Structure Notes

- Package source: `src/capybara/`
- Tests: `tests/` (mirrors src structure)
- Entry point: `capybara.cli.main:cli` (installed as `capybara` command)
- Configuration: `~/.capybara/config.yaml`
- Session logs: `~/.capybara/logs/sessions/<session_id>.log`
- Conversation DB: `~/.capybara/conversations.db`
- Git branch: `feat/multi-agent` (current development)
