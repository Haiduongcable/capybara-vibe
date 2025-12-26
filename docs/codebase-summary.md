# Codebase Summary

**Project:** Capybara Vibe Coding
**Type:** Async-first AI-powered CLI coding assistant
**Language:** Python 3.10+
**Architecture:** ReAct (Reason → Act → Observe) agent pattern
**Last Updated:** 2025-12-26

## Overview

Capybara Vibe Coding is an intelligent CLI coding assistant that leverages Large Language Models (LLMs) to help developers write, debug, and understand code through interactive assistance. The system implements a sophisticated multi-agent architecture with advanced execution tracking and failure recovery mechanisms.

## Core Technology Stack

- **Async Runtime:** asyncio for concurrent operations
- **LLM Integration:** LiteLLM (multi-provider support: OpenAI, Anthropic, Google, 100+ providers)
- **Validation:** Pydantic for configuration and data models
- **CLI Framework:** Click for command-line interface
- **UI/Display:** Rich for terminal formatting, prompt_toolkit for REPL
- **Token Management:** tiktoken for context window management
- **Database:** aiosqlite for conversation persistence

## Architecture Components

### 1. Agent System (`src/capybara/core/`)

**Main Agent (`agent.py`)**
- Implements ReAct loop (max 70 turns)
- Concurrent tool execution via `asyncio.gather()`
- Execution tracking for child agents (Phase 1 enhancement)
- Event bus integration for progress streaming
- Agent modes: PARENT (full access) vs CHILD (restricted)

**Execution Logging (`execution_log.py`)** - NEW
- `ExecutionLog`: Tracks files read/written/edited, tool executions, success rates
- `ToolExecution`: Records individual tool calls with duration and success status
- `FileOperation`: Tracks file modifications
- Comprehensive XML execution summaries for parent agents

**Failure Handling (`child_errors.py`)** - NEW
- `FailureCategory`: TIMEOUT, MISSING_CONTEXT, TOOL_ERROR, INVALID_TASK, PARTIAL_SUCCESS
- `ChildFailure`: Structured failure reports with recovery guidance
- Intelligent failure analysis with retry suggestions

**Session Management (`session_manager.py`)**
- Parent-child session hierarchy
- Database-backed session persistence
- Session event logging for audit trails

**Event Bus (`event_bus.py`)**
- Pub/sub system for agent communication
- Progress streaming from child to parent
- Event types: AGENT_START, TOOL_START, TOOL_DONE, TOOL_ERROR, AGENT_DONE

**System Prompts (`prompts.py`)**
- Separate prompts for parent (planning/delegation) and child (execution) agents
- Project context integration
- Task management guidelines

### 2. Memory System (`src/capybara/memory/`)

**Conversation Memory (`window.py`)**
- Sliding window with tiktoken token counting
- Default: 100K token limit
- System prompt preservation (never trimmed)
- FIFO message trimming when limits exceeded

**Conversation Storage (`storage.py`)**
- SQLite database: `~/.capybara/conversations.db`
- Tables: `conversations`, `messages`, `session_events`
- Parent-child relationship tracking
- Session metadata and event logging

### 3. Tool System (`src/capybara/tools/`)

**Tool Registry (`registry.py`)**
- Centralized tool management
- OpenAI function calling schema format
- Agent mode filtering (parent vs child)
- Tool permission system

**Built-in Tools (`builtin/`)**
- `filesystem.py`: read, write, edit, list, glob
- `bash.py`: Shell command execution
- `search.py`: grep functionality
- `search_replace.py`: Block-based code editing
- `todo.py`: Task management (parent agents only)
- `delegate.py`: Multi-agent task delegation (parent agents only)

**Tool Filtering**
- Child agents cannot access `todo` or `delegate_task` tools
- Permission-based tool execution
- Mode-aware tool registry filtering

### 4. Multi-Agent System (Phase 1 & 2 Enhancements)

**Task Delegation (`tools/builtin/delegate.py`)**
- Parent → child agent spawning
- Isolated child sessions with separate context
- Comprehensive execution reporting
- Structured failure recovery
- Timeout management with retry guidance

**Execution Tracking**
- Automatic logging for child agents (AgentMode.CHILD)
- Files read/written/edited tracking
- Tool usage statistics
- Success rate calculation
- Error collection and reporting

**Failure Recovery**
- Categorized failures with specific recovery actions
- Partial progress tracking
- Retry suggestions based on failure type
- Blocked reason identification
- Actionable recovery steps for parent agents

### 5. Provider System (`src/capybara/providers/`)

**Provider Router (`router.py`)**
- Single provider mode for direct LLM calls
- Multi-provider mode with automatic fallback
- Streaming and non-streaming completions
- Support for 100+ LLM providers via LiteLLM

### 6. Configuration (`src/capybara/core/config.py`)

**Configuration Models**
- `CapybaraConfig`: Main configuration
- `ProviderConfig`: LLM provider settings
- `MemoryConfig`: Conversation memory limits
- `ToolsConfig`: Tool behavior settings
- `MCPConfig`: Model Context Protocol servers

**Priority:** Environment variables > YAML file > Defaults
**Location:** `~/.capybara/config.yaml`

### 7. MCP Integration (`src/capybara/tools/mcp/`)

**MCP Bridge (`bridge.py`)**
- Multi-server management
- Tool registration with namespacing
- Lifecycle management

**MCP Client (`client.py`)**
- Stdio-based server communication
- Individual server connections
- Tool execution proxying

## Key Features

### Multi-Agent Architecture

**Parent Agents:**
- Full tool access
- Task planning and delegation
- Todo list management
- Conversation history access
- Child agent spawning

**Child Agents:**
- Task-focused execution
- Isolated context (no parent history)
- Restricted tool access (no todo/delegate)
- Comprehensive execution logging
- Structured failure reporting

### Execution Tracking (Phase 1)

Child agents automatically track:
- Files read, written, and edited
- Tool execution history with timestamps
- Success rates and error collection
- Execution duration
- Tool usage patterns

Parent agents receive:
- XML execution summaries
- File modification lists
- Tool usage statistics
- Success rate metrics
- Error details

### Intelligent Failure Recovery (Phase 2)

**Failure Categories:**
- **TIMEOUT**: Task needs more time
- **MISSING_CONTEXT**: Insufficient information in prompt
- **TOOL_ERROR**: External dependency failure
- **INVALID_TASK**: Task impossible or unclear
- **PARTIAL_SUCCESS**: Some work done, hit blocker

**Recovery Guidance:**
- Completed work summary
- Files modified before failure
- Blocked reason identification
- Retry suggestions (yes/no)
- Actionable recovery steps
- Tool usage context

### Agent Modes

```python
class AgentMode(str, Enum):
    PARENT = "parent"  # Full access, can delegate
    CHILD = "child"    # Restricted, execution-focused
```

### Session Hierarchy

```
Parent Session
├── metadata: agent_mode=PARENT
├── tools: all tools including todo, delegate
└── Child Session 1
    ├── metadata: agent_mode=CHILD, parent_id=<parent_session_id>
    ├── tools: filtered (no todo, no delegate)
    └── execution_log: enabled
```

## Data Flow

### Delegation Flow

```
1. Parent calls delegate_task(prompt, timeout)
2. SessionManager creates child session
3. Child agent initializes with:
   - Separate memory
   - Filtered tool registry
   - Execution logging enabled
   - Event bus subscription
4. Child executes task with progress streaming
5. On success:
   - Execution log collected
   - XML summary generated
   - Parent receives comprehensive report
6. On failure:
   - Failure categorized
   - Partial progress captured
   - Recovery guidance provided
   - Parent receives structured failure report
```

### Event Streaming

```
Child Agent                Event Bus              Parent Agent
    |                          |                        |
    |-- AGENT_START ---------> |                        |
    |                          | -----> display ------> |
    |-- TOOL_START ----------> |                        |
    |                          | -----> display ------> |
    |-- TOOL_DONE -----------> |                        |
    |                          | -----> display ------> |
    |-- AGENT_DONE ----------> |                        |
    |                          | -----> display ------> |
```

## Directory Structure

```
src/capybara/
├── __main__.py                      # Entry point
├── cli/                             # CLI commands
│   ├── main.py                      # Click commands
│   ├── interactive.py               # REPL interface
│   └── commands/                    # Subcommands
├── core/                            # Core engine
│   ├── agent.py                     # ReAct agent loop
│   ├── execution_log.py             # NEW: Execution tracking
│   ├── child_errors.py              # NEW: Failure handling
│   ├── session_manager.py           # Session hierarchy
│   ├── event_bus.py                 # Event streaming
│   ├── prompts.py                   # System prompts
│   ├── streaming.py                 # Rich display
│   ├── config.py                    # Configuration
│   ├── safety.py                    # Path validation
│   ├── context.py                   # Project context
│   └── litellm_config.py            # LiteLLM setup
├── memory/                          # Conversation management
│   ├── window.py                    # Sliding window
│   └── storage.py                   # SQLite persistence
├── providers/                       # LLM abstraction
│   └── router.py                    # Multi-provider router
└── tools/                           # Tool system
    ├── base.py                      # Base classes
    ├── registry.py                  # Tool registry
    ├── builtin/                     # Built-in tools
    │   ├── filesystem.py
    │   ├── bash.py
    │   ├── search.py
    │   ├── search_replace.py
    │   ├── todo.py                  # MODIFIED: Parent only
    │   └── delegate.py              # MODIFIED: Enhanced reporting
    └── mcp/                         # MCP integration
        ├── bridge.py
        └── client.py
```

## Testing

- **Framework:** pytest with pytest-asyncio
- **Async mode:** Auto (configured in pyproject.toml)
- **Coverage target:** 80%+
- **Test structure:**
  - Unit tests: `tests/test_*.py`
  - Integration tests: `tests/integration/`

**Recent Test Status:**
- 92/92 tests passing (100%)
- Enhanced test coverage for execution logging and failure handling
- Integration tests for delegation flow

## Recent Enhancements

### Phase 1: Enhanced Child Execution Tracking
- **Files:** `execution_log.py`, `agent.py`, `delegate.py`
- **Features:**
  - Comprehensive tool execution tracking
  - File operation logging
  - Success rate calculation
  - XML execution summaries
- **Performance:** Logging only enabled for child agents

### Phase 2: Intelligent Failure Recovery
- **Files:** `child_errors.py`, `delegate.py`
- **Features:**
  - Structured failure categorization
  - Partial progress tracking
  - Intelligent retry guidance
  - Recovery action suggestions
  - Comprehensive failure reports

### Implementation Metrics
- 9 files modified/created
- ~500 lines of production code
- 92/92 tests passing
- Code quality: 8.5/10
- Zero critical issues

## Configuration

**Location:** `~/.capybara/config.yaml`

```yaml
# Example configuration
providers:
  - model: gpt-4
    api_key: ${OPENAI_API_KEY}
  - model: claude-3-opus
    api_key: ${ANTHROPIC_API_KEY}

memory:
  max_tokens: 100000

tools:
  safe_mode: false

mcp:
  servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem"]
```

## Development Workflow

```bash
# Install development dependencies
pip install -e .

# Run tests with coverage
pytest --cov=capybara --cov-report=term-missing

# Type checking
mypy src/capybara

# Code formatting
ruff check src/
ruff format src/

# Interactive chat
capybara chat

# Single command execution
capybara run "your prompt"
```

## Security Considerations

- Sensitive path protection (`core/safety.py`)
- API key management via environment variables
- Safe mode for dangerous operations
- Validation of file paths and commands
- No credentials in code or commits

## Performance Optimizations

- Concurrent tool execution via `asyncio.gather()`
- Token-aware memory trimming
- Conditional execution logging (child agents only)
- Streaming responses for better UX
- Connection pooling for database operations

## Future Enhancements

Potential areas for expansion:
- Recursive delegation (child → grandchild)
- Advanced execution analytics
- Machine learning-based failure prediction
- Enhanced context sharing between agents
- Distributed agent execution
- Real-time collaboration features
