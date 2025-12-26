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
│   ├── agent.py         # ReAct agent loop
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
└── tools/               # Tool system
    ├── base.py          # Base tool classes
    ├── registry.py      # Tool registry
    ├── builtin/         # Built-in tools
    │   ├── filesystem.py      # read, write, edit, list, glob
    │   ├── bash.py            # Shell execution
    │   ├── search.py          # grep
    │   ├── search_replace.py  # Block-based editing
    │   └── todo.py            # Task management
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
