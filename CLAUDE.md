# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Capybara Vibe Coding is an **async-first, AI-powered CLI coding assistant** implementing the ReAct (Reason → Act → Observe) agent pattern. Built on Python 3.10+ with LiteLLM for multi-provider LLM support, featuring MCP (Model Context Protocol) integration for extensibility.

**Key Stack:** asyncio, LiteLLM, Pydantic, Rich, prompt_toolkit, tiktoken, aiosqlite

## Essential Commands

### Installation & Setup
```bash
# Install in development mode
pip install -e .

# Initialize configuration (creates ~/.capybara/config.yaml)
capybara init

# Run tests
pytest

# Run tests with coverage
pytest --cov=capybara --cov-report=term-missing

# Type checking
mypy src/capybara

# Code formatting/linting
ruff check src/
ruff format src/
```

### Development Workflow
```bash
# Interactive chat mode
capybara chat

# Single-run mode
capybara run "your prompt here"

# Test specific module
pytest tests/test_memory.py -v

# Run in different operation modes
capybara chat --mode safe    # Asks before dangerous actions
capybara chat --mode plan    # Disables writes/bash
capybara chat --mode auto    # Never asks permission
```

## Architecture Patterns

### ReAct Agent Loop
The core agent (`src/capybara/core/agent.py`) implements a **max 70-turn loop** that prevents infinite reasoning:
1. Add user message to memory
2. Get LLM completion with tool schemas
3. Execute tool calls **concurrently** via `asyncio.gather()`
4. Add results to memory, repeat until no more tool calls

**Critical:** Tools must be async. Use `@registry.tool()` decorator for registration with OpenAI function calling schema format.

### Async-First Design
**All core operations are async:**
- Agent loop: `async def run()`
- Tool execution: `async def execute()`
- LLM calls: `async def complete()`
- Storage: `async def save_message()`
- MCP communication: `async def call_tool()`

Use `asyncio.gather()` for concurrent tool execution when LLM requests multiple tools.

### Memory System (Sliding Window)
Located in `src/capybara/memory/window.py`:
- **System prompt preserved** (never trimmed, always first message)
- **Token-aware sliding window** using tiktoken (default: 100K tokens)
- FIFO trimming when limits exceeded
- Message format: `[{role: str, content: str, tool_calls?: list, tool_call_id?: str}]`

### Tool Registry Pattern
`src/capybara/tools/registry.py` provides centralized tool management:

```python
@registry.tool(
    name="tool_name",
    description="Description for LLM",
    parameters={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "..."}
        },
        "required": ["param"]
    }
)
async def tool_name(param: str) -> str:
    # Implementation
    return result
```

**Key points:**
- Tools return strings (success) or error messages
- Schemas follow OpenAI function calling format
- Multiple registries can be merged with `registry.merge()`
- Concurrent execution of tool calls in agent loop

### Task Delegation (Multi-Agent)

Capybara supports **parent→child agent delegation** for parallel and specialized work.

**Architecture:**
```
Parent Session (full context, planning, delegation)
  └── Child Session 1 (isolated, task-focused)
  └── Child Session 2 (isolated, task-focused)
```

**Key Components:**
- **Session Hierarchy:** `src/capybara/core/session_manager.py` manages parent-child relationships
- **Agent Modes:** `AgentMode.PARENT` (full access) vs `AgentMode.CHILD` (restricted)
- **Tool Filtering:** Child agents cannot use `todo` or `delegate_task` tools
- **Event Bus:** `src/capybara/core/event_bus.py` streams child progress to parent
- **Prompts:** Separate system prompts for parent (planning) and child (execution)

**Usage Example:**
```python
# Parent agent delegates research task
delegate_task(
    prompt="""
    Research the top 5 Python async web frameworks in 2024.
    For each framework, provide:
    - GitHub stars and activity
    - Key features
    - Performance benchmarks (if available)
    """,
    timeout=180
)
```

**Child Agent Limitations:**
- ❌ No access to parent's conversation history
- ❌ Cannot create or modify todo lists
- ❌ Cannot delegate to further children (no recursion)
- ✅ Full tool access (read, write, edit, bash, grep, etc.)
- ✅ Works with only the prompt context provided

**Progress Display:**

Basic (Phase 1-2):
```
┌─ Delegated Task
│ Child agent started...
│ ▶ bash
│ ✓ bash
│ ▶ read_file
│ ✓ read_file
└─ Task completed
```

Enhanced Flow Visualization (Phase 3):
```
┌─────────────── Agent Communication Flow ────────────────┐
│ ⏳ [parent] waiting: Delegated task                     │
│ └── ⚙️ [child] executing: Running grep on src/         │
└─────────────────────────────────────────────────────────┘
```

**Session Storage:**
All sessions persisted in `~/.capybara/conversations.db` with:
- `parent_id` column for hierarchy tracking
- `agent_mode` column (parent/child)
- `session_events` table for audit trail

**Implementation Files:**
- `src/capybara/tools/builtin/delegate.py` - Delegation tool (Phase 1-3 enhancements)
- `src/capybara/core/session_manager.py` - Session hierarchy
- `src/capybara/core/event_bus.py` - Progress events and state changes
- `src/capybara/core/prompts.py` - Parent/child prompts
- `src/capybara/tools/base.py` - AgentMode enum
- `src/capybara/memory/storage.py` - Session storage
- `src/capybara/core/execution_log.py` - **NEW:** Execution tracking (Phase 1)
- `src/capybara/core/child_errors.py` - **NEW:** Failure recovery (Phase 2)
- `src/capybara/core/agent_status.py` - **NEW:** Agent status tracking (Phase 3)
- `src/capybara/ui/flow_renderer.py` - **NEW:** Visual flow rendering (Phase 3)

**Phase 1: Enhanced Child Execution Tracking**

Child agents now automatically track all operations:
- **Files:** Read, written, and edited files
- **Tools:** All tool executions with success/failure status
- **Metrics:** Success rates, execution duration
- **Errors:** Comprehensive error collection

Parent agents receive XML execution summaries:
```xml
<execution_summary>
  <session_id>child-123</session_id>
  <status>completed</status>
  <duration>45.23s</duration>
  <success_rate>95%</success_rate>
  <files>
    <read count="5">src/auth.py, tests/test_auth.py, ...</read>
    <modified count="2">src/auth.py, tests/test_auth.py</modified>
  </files>
  <tools total="12">
    read_file: 5x
    edit_file: 2x
    bash: 3x
  </tools>
</execution_summary>
```

**Phase 2: Intelligent Failure Recovery**

Failed delegations return structured failure reports:
- **Categorization:** TIMEOUT, TOOL_ERROR, MISSING_CONTEXT, INVALID_TASK, PARTIAL_SUCCESS
- **Partial Progress:** Track completed work before failure
- **Recovery Guidance:** Actionable retry suggestions
- **Context:** Files modified, blocked reasons, suggested actions

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
  • Install missing dependencies
```

**Phase 3: Enhanced UI Communication Flow**

Real-time visual tracking of parent-child agent communication:
- **AgentStatus tracking:** Live state monitoring (idle, thinking, executing, waiting, completed, failed)
- **Flow renderer:** Rich-based tree visualization showing agent hierarchy
- **State-aware styling:** Color-coded states with emojis and action descriptions
- **Event-driven updates:** Automatic UI refresh on state changes

```python
# Agent states
class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"           # LLM generating response
    EXECUTING_TOOLS = "executing"   # Running tool calls
    WAITING_FOR_CHILD = "waiting"   # Delegated, awaiting child
    COMPLETED = "completed"
    FAILED = "failed"
```

Visual flow examples:
```
# Parent with active child
┌─────────────── Agent Communication Flow ────────────────┐
│ 🤔 [parent] thinking: Planning next steps              │
│ └── ⚙️ [child] executing: Running tests in tests/      │
└─────────────────────────────────────────────────────────┘

# Multiple children
┌─────────────── Agent Communication Flow ────────────────┐
│ ⏳ [parent] waiting: Managing delegations              │
│ ├── ⚙️ [child] executing: Testing backend              │
│ └── 🤔 [child] thinking: Analyzing frontend            │
└─────────────────────────────────────────────────────────┘

# Completed with results
┌─────────────── Agent Communication Flow ────────────────┐
│ ✅ [parent] completed                                   │
│ └── ✅ [child] completed                                │
└─────────────────────────────────────────────────────────┘
```

**Integration:**
- Parent agents automatically get `flow_renderer` instance
- Child agents have no flow renderer (zero overhead)
- Compatible with Phase 1 execution tracking and Phase 2 failure recovery
- Completely optional - agents work without UI components

**Performance Impact:**
- Child agents: 2-3% overhead (minimal)
- Parent agents: <1% overhead (flow renderer)
- Memory: ~1KB per 100 tool executions + ~2KB for flow renderer

### MCP Integration Architecture
`src/capybara/tools/mcp/` implements Model Context Protocol for external tools:
- **MCPBridge** manages multiple MCP servers
- **MCPClient** handles individual stdio connections
- **Tool naming:** `{server_name}__{tool_name}` to prevent collisions
- Lifecycle: connect_all() → register_with_registry() → call_tool() → disconnect_all()

### Provider Router (LiteLLM)
`src/capybara/providers/router.py` abstracts multiple LLM providers:
- **Single provider mode:** Direct `litellm.acompletion()` calls
- **Multi-provider mode:** Automatic fallback and load balancing
- Supports OpenAI, Anthropic, Google, and 100+ providers
- **Streaming** and non-streaming completion methods

### Configuration System
Pydantic-based config in `src/capybara/core/config.py`:
- **Priority:** Environment vars > YAML file > Defaults
- **Location:** `~/.capybara/config.yaml`
- **Validation:** Runtime type checking via Pydantic models
- Models: CapybaraConfig, ProviderConfig, MemoryConfig, ToolsConfig, MCPConfig

## Critical Implementation Details

### Search-Replace Tool
`src/capybara/tools/builtin/search_replace.py` uses **block-based matching**, not line numbers:
```
<<<<<<< SEARCH
exact block to find
=======
replacement content
>>>>>>> REPLACE
```
This prevents hallucinated line number issues.

### Safety Guardrails
`src/capybara/core/safety.py` defines dangerous paths:
- Root directories: `/`, `/usr`, `/etc`, `/var`, `/bin`, `/sbin`
- User home directory root (subdirs allowed)
- Agent won't auto-scan these directories

### Streaming Engine
`src/capybara/core/streaming.py` handles real-time token display:
- **Rich Live display** with Markdown rendering (4 FPS refresh)
- Assembles **streamed tool calls** from delta chunks by index
- Transient display that clears after completion

### LiteLLM Configuration
**CRITICAL:** Import `suppress_litellm_output()` FIRST in CLI entrypoints to prevent spam:
```python
from capybara.core.litellm_config import suppress_litellm_output
suppress_litellm_output()
```

### Error Handling Pattern
```python
try:
    result = await tool_function(**args)
    return str(result)
except Exception as e:
    return f"Error: {type(e).__name__}: {e}"
```
Errors are returned as strings to LLM context, not raised.

### Session Persistence
`src/capybara/memory/storage.py` uses aiosqlite:
- **Database:** `~/.capybara/conversations.db`
- **Tables:** `conversations`, `messages`
- Save messages during chat for resume functionality

## Testing Patterns

- **Async tests:** Use `pytest-asyncio` with `asyncio_mode = "auto"` in pyproject.toml
- **Unit tests:** `tests/test_*.py` for individual components
- **Integration tests:** `tests/integration/` for end-to-end flows
- **Coverage target:** 80%+ (configured in pyproject.toml)

## Common Gotchas

1. **DNS errors:** Uninstall aiodns if you see DNS resolution failures: `pip uninstall -y aiodns`
2. **Tool not found:** Check `src/capybara/tools/builtin/__init__.py` for registration
3. **Max turns exceeded:** Agent hit 70-turn limit, check for reasoning loops
4. **Memory trimming:** System prompt is preserved, but old messages get FIFO trimmed at 100K tokens
5. **Tool schemas:** Must be valid JSON Schema with `type: "object"` and `properties`

## Directory Structure

```
src/capybara/
├── __main__.py           # Entry point
├── cli/                  # Click commands and interactive mode
│   ├── main.py          # CLI definitions
│   ├── interactive.py   # prompt_toolkit REPL
│   └── commands/        # Subcommands
├── core/                 # Core engine
│   ├── agent.py         # ReAct agent loop (with execution tracking)
│   ├── execution_log.py # NEW: Execution tracking (Phase 1)
│   ├── child_errors.py  # NEW: Failure recovery (Phase 2)
│   ├── agent_status.py  # NEW: Status tracking (Phase 3)
│   ├── session_manager.py # Session hierarchy
│   ├── event_bus.py     # Event streaming and state changes
│   ├── streaming.py     # Rich streaming display
│   ├── prompts.py       # System prompts
│   ├── config.py        # Pydantic config models
│   ├── safety.py        # Path validation
│   ├── context.py       # Startup context gathering
│   └── litellm_config.py # LiteLLM suppression
├── memory/              # Conversation management
│   ├── window.py        # Sliding window with tiktoken
│   └── storage.py       # SQLite persistence
├── providers/           # LLM abstraction
│   └── router.py        # LiteLLM router
├── ui/                  # UI components (Phase 3)
│   └── flow_renderer.py # Communication flow visualization
└── tools/               # Tool system
    ├── base.py          # Base tool classes
    ├── registry.py      # Tool registry
    ├── builtin/         # Built-in tools
    │   ├── filesystem.py      # read, write, edit, list, glob
    │   ├── bash.py            # Shell execution
    │   ├── search.py          # grep
    │   ├── search_replace.py  # Block-based editing
    │   ├── todo.py            # Task management
    │   └── delegate.py        # ENHANCED: Comprehensive reporting
    └── mcp/             # MCP integration
        ├── bridge.py    # Multi-server manager
        └── client.py    # Single server client
```

## When Making Changes

- **Adding builtin tools:** Create in `tools/builtin/`, register in `__init__.py`
- **Adding MCP servers:** Update `~/.capybara/config.yaml` mcp.servers section
- **Modifying agent behavior:** Edit `core/prompts.py` for system prompt changes
- **Changing memory limits:** Update MemoryConfig in `config.py` or user's config.yaml
- **New providers:** Add to config.yaml providers list (LiteLLM handles the rest)

## Git Commit Standards

All agent-generated commits include co-author signature:
```
Co-authored-by: Capybara Vibe <agent@capybara.ai>
```
