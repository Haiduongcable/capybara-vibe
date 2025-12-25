# CapybaraVibeCoding Architecture

**Version:** 1.0
**Date:** 2025-12-25
**Type:** AI Coding Assistant CLI

---

## Table of Contents

1. [High-Level Overview](#high-level-overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Agent Architecture](#agent-architecture)
5. [Memory System](#memory-system)
6. [Tools System](#tools-system)
7. [MCP Integration](#mcp-integration)
8. [Provider Router](#provider-router)
9. [Streaming Engine](#streaming-engine)
10. [Configuration System](#configuration-system)
11. [Data Flow](#data-flow)
12. [CLI Interface](#cli-interface)
13. [Implementation Details](#implementation-details)

---

## High-Level Overview

CapybaraVibeCoding is an **async-first, tool-enabled AI coding assistant** built on Python 3.10+ that provides interactive and single-run code assistance through a terminal interface.

### Key Characteristics

- **Architecture Pattern:** ReAct (Reason → Act → Observe) agent loop
- **Concurrency Model:** Async/await throughout (asyncio)
- **LLM Integration:** Multi-provider support via LiteLLM
- **Tool System:** OpenAI function calling format with async execution
- **Memory:** Token-aware sliding window with optional persistence
- **Extensibility:** MCP (Model Context Protocol) for external tools

### Technology Stack

```
Python 3.10+
├── async/await (asyncio)
├── LiteLLM (multi-provider LLM abstraction)
├── Pydantic (configuration & validation)
├── Rich (terminal UI & markdown)
├── prompt_toolkit (interactive CLI)
├── tiktoken (token counting)
├── aiosqlite (async session storage)
└── YAML (configuration format)
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ capybara run │  │ capybara chat│  │ capybara init│  ...     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
└─────────┼──────────────────┼──────────────────┼────────────────┘
          │                  │                  │
          └──────────────────┴──────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      Agent Core                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Agent (agent.py)                                          │ │
│  │  • Main ReAct loop (max 10 turns)                          │ │
│  │  • Tool calling orchestration                              │ │
│  │  • Streaming/non-streaming coordination                    │ │
│  └────────────┬─────────────────┬─────────────────┬───────────┘ │
│               │                 │                 │             │
│      ┌────────▼─────┐  ┌────────▼─────┐  ┌───────▼────────┐   │
│      │   Memory     │  │ Tool Registry│  │ ProviderRouter │   │
│      │  (window.py) │  │(registry.py) │  │  (router.py)   │   │
│      └──────────────┘  └──────┬───────┘  └────────────────┘   │
└────────────────────────────────┼──────────────────────────────┘
                                 │
                    ┌────────────┴──────────────┐
                    │                           │
           ┌────────▼────────┐       ┌─────────▼─────────┐
           │  Builtin Tools  │       │   MCP Bridge      │
           │ • filesystem    │       │  (external tools) │
           │ • bash          │       └───────────────────┘
           │ • search        │
           └─────────────────┘
```

### Communication Flow

```
User Input
    │
    ▼
┌────────────────┐
│  CLI Handler   │ (interactive.py / main.py)
└───────┬────────┘
        │
        ▼
┌────────────────┐
│  Agent.run()   │ ◄──────────┐
└───────┬────────┘            │
        │                     │
        ▼                     │
┌────────────────┐            │
│  LLM Provider  │            │
│  (via Router)  │            │
└───────┬────────┘            │
        │                     │
        ├─► Text Response ────┘ (return to user)
        │
        └─► Tool Calls
              │
              ▼
        ┌──────────────┐
        │ Tool Registry│
        │   execute()  │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │ Tool Results │──────┐
        └──────────────┘      │
                              │
        Loop back to LLM ◄────┘
```

---

## Core Components

### 1. Agent (`src/capybara/core/agent.py`)

**Purpose:** Main orchestration engine implementing the ReAct pattern.

**Key Methods:**
```python
async def run(user_input: str) -> str:
    """Main agent loop with tool use."""
    # 1. Add user message to memory
    # 2. Loop up to max_turns:
    #    - Get LLM completion
    #    - Check for tool calls
    #    - Execute tools concurrently
    #    - Add results to memory
    # 3. Return final response
```

**Configuration:**
```python
@dataclass
class AgentConfig:
    model: str = "gpt-4o"
    max_turns: int = 10         # Prevent infinite loops
    timeout: float = 120.0      # Per-request timeout
    stream: bool = True         # Enable streaming
```

**Dependencies:**
- `memory`: ConversationMemory (manages context)
- `tools`: ToolRegistry (available tools)
- `provider`: ProviderRouter (LLM access)
- `console`: Rich Console (output formatting)

**Tool Execution:** Concurrent execution via `asyncio.gather()` for parallel tool calls.

---

### 2. System Prompt (`src/capybara/core/prompts.py`)

**Purpose:** Define agent behavior, capabilities, and response format.

**Key Features:**
- 8 Core Principles (Read Before Write, Tool Usage, Code Quality, Security, etc.)
- Task Completion Format (mandatory summary at end)
- Available Tools documentation
- Common Workflows (Code Review, Bug Investigation, etc.)

**Applied At:**
- `interactive.py:73` - Chat mode
- `interactive.py:205` - Session-based chat
- `main.py:126` - Single-run mode

---

## Agent Architecture

### ReAct Loop Implementation

```python
# Pseudo-code representation
def agent_loop(user_input):
    memory.add(user_input)

    for turn in range(max_turns):
        # REASON: Get LLM response
        response = await get_completion(
            messages=memory.get_messages(),
            tools=tool_schemas
        )

        memory.add(response)

        # Check if done
        if no tool_calls in response:
            return response.content

        # ACT: Execute tools
        tool_results = await execute_tools_concurrently(
            response.tool_calls
        )

        # OBSERVE: Add results to context
        for result in tool_results:
            memory.add(result)

    return "Max turns exceeded"
```

### Turn Limit Protection

- **Default:** 70 turns maximum 
- **Prevents:** Infinite loops from confused LLMs
- **Behavior:** Returns "Max turns exceeded" message if limit hit

### Concurrent Tool Execution

**Why:** LLMs can request multiple tool calls in a single response.

**Implementation:**
```python
async def _execute_tools(tool_calls):
    tasks = [execute_one(tc) for tc in tool_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return process_results(results)
```

**Benefits:**
- Faster execution (parallel I/O operations)
- Handles 3+ tool calls efficiently
- Graceful error handling per tool

---

## Memory System

### Architecture

```
ConversationMemory (window.py)
    │
    ├─► System Prompt (always preserved)
    │
    ├─► Message Buffer (sliding window)
    │   └─► Auto-trimming by token count
    │
    └─► Token Counter (tiktoken)
        └─► cl100k_base encoding
```

### Implementation (`src/capybara/memory/window.py`)

**Class:** `ConversationMemory`

**Configuration:**
```python
@dataclass
class MemoryConfig:
    max_messages: Optional[int] = None  # Message count limit
    max_tokens: int = 100_000           # Token limit
    model: str = "gpt-4o"               # For tokenizer
```

**Key Features:**

1. **System Prompt Preservation**
   ```python
   def set_system_prompt(content: str):
       self._system_prompt = {"role": "system", "content": content}
   # Never trimmed, always first message
   ```

2. **Sliding Window**
   ```python
   def _trim():
       # Remove oldest messages when over limit
       while total_tokens > max_tokens and len(messages) > 1:
           messages.pop(0)  # FIFO
   ```

3. **Token Counting**
   ```python
   def _count_tokens(message):
       encoder = tiktoken.encoding_for_model(model)
       return len(encoder.encode(content))
   ```

4. **Message Format**
   ```python
   [
       {"role": "system", "content": "..."},      # Prompt
       {"role": "user", "content": "..."},        # User
       {"role": "assistant", "content": "..."},   # Response
       {"role": "tool", "tool_call_id": "...", "content": "..."}  # Results
   ]
   ```

### Storage Layer (`src/capybara/memory/storage.py`)

**Purpose:** Persist conversations to SQLite for session resumption.

**Database Schema:**
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    model TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT,
    role TEXT,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    created_at TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
```

**Location:** `~/.capybara/conversations.db`

**Usage:**
```python
storage = ConversationStorage()
await storage.initialize()

# Save
await storage.save_message(session_id, message)

# Load
messages = await storage.load_session(session_id)

# List
sessions = await storage.list_sessions(limit=20)
```

---

## Tools System

### Architecture

```
ToolRegistry (registry.py)
    │
    ├─► Builtin Tools
    │   ├─► Filesystem (read, write, edit, list, glob)
    │   ├─► Bash (execute shell commands)
    │   └─► Search (grep pattern matching)
    │
    └─► MCP Tools (via MCPBridge)
        └─► External servers (stdio protocol)
```

### Tool Registry (`src/capybara/tools/registry.py`)

**Purpose:** Central registry for all tools with OpenAI function calling schema.

**Key Methods:**

1. **Registration (Decorator)**
   ```python
   @registry.tool(
       name="read_file",
       description="Read a file with line numbers",
       parameters={
           "type": "object",
           "properties": {
               "path": {"type": "string", "description": "File path"}
           },
           "required": ["path"]
       }
   )
   async def read_file(path: str) -> str:
       # Implementation
       pass
   ```

2. **Registration (Programmatic)**
   ```python
   registry.register(
       name="my_tool",
       func=my_async_function,
       description="Tool description",
       parameters={...}
   )
   ```

3. **Execution**
   ```python
   result = await registry.execute(
       name="read_file",
       arguments={"path": "/path/to/file"}
   )
   # Returns: string result or error message
   ```

4. **Schema Export**
   ```python
   schemas = registry.schemas
   # Returns: List of OpenAI function schemas
   # Format: [{"type": "function", "function": {...}}]
   ```

5. **Merging Registries**
   ```python
   main_registry.merge(builtin_tools)
   # Combines two registries without duplicates
   ```

### Builtin Tools

**Location:** `src/capybara/tools/builtin/`

#### Filesystem Tools (`filesystem.py`)

| Tool | Description | Parameters |
|------|-------------|------------|
| `read_file` | Read file with line numbers | `path: str, offset?: int, limit?: int` |
| `write_file` | Create/overwrite file | `path: str, content: str` |
| `edit_file` | String replacement in file | `path: str, old: str, new: str, replace_all?: bool` |
| `list_directory` | List directory contents | `path?: str` |
| `glob` | Find files by pattern | `pattern: str, path?: str` |

**Safety Features:**
- Path validation (allowed_paths check)
- Line number display for navigation
- Atomic file operations

#### Bash Tools (`bash.py`)

| Tool | Description | Parameters |
|------|-------------|------------|
| `bash` | Execute shell command | `command: str, timeout?: float` |
| `which` | Check if command exists | `command: str` |

**Safety Features:**
- Configurable timeout (default: 120s)
- stdout + stderr capture
- Exit code handling

#### Search Tools (`search.py`)

| Tool | Description | Parameters |
|------|-------------|------------|
| `grep` | Search files for pattern | `pattern: str, path?: str, glob?: str, flags?: str` |

**Features:**
- Regex support
- Glob filtering
- Case-insensitive option
- Line number output

### Tool Schema Format

**OpenAI Function Calling Standard:**
```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file with line numbers",
    "parameters": {
      "$schema": "http://json-schema.org/draft-07/schema#",
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Absolute or relative file path"
        }
      },
      "required": ["path"],
      "additionalProperties": false
    }
  }
}
```

---

## MCP Integration

### Model Context Protocol

**Purpose:** Extend agent capabilities with external tools via standard protocol.

**Protocol:** [Model Context Protocol Specification](https://modelcontextprotocol.io/)

**Transport:** stdio (standard input/output)

### Architecture

```
MCPBridge (bridge.py)
    │
    ├─► MCPClient 1 (e.g., "filesystem")
    │   ├─► stdio transport
    │   ├─► Tool list
    │   └─► call_tool()
    │
    ├─► MCPClient 2 (e.g., "database")
    │   ├─► stdio transport
    │   ├─► Tool list
    │   └─► call_tool()
    │
    └─► Register all → ToolRegistry
```

### MCPBridge (`src/capybara/tools/mcp/bridge.py`)

**Purpose:** Manage multiple MCP servers and integrate their tools.

**Lifecycle:**

1. **Initialization**
   ```python
   mcp_bridge = MCPBridge(config.mcp)
   ```

2. **Connection**
   ```python
   connected = await mcp_bridge.connect_all()
   # Returns: Number of successfully connected servers
   ```

3. **Registration**
   ```python
   tool_count = mcp_bridge.register_with_registry(tool_registry)
   # Adds all MCP tools to registry with prefixed names
   ```

4. **Execution**
   ```python
   result = await mcp_bridge.call_tool(
       tool_name="server__tool_name",
       arguments={...}
   )
   ```

5. **Cleanup**
   ```python
   await mcp_bridge.disconnect_all()
   ```

**Tool Naming:** `{server_name}__{tool_name}`
- Example: `filesystem__read_file`
- Prevents name collisions between servers

### MCPClient (`src/capybara/tools/mcp/client.py`)

**Purpose:** Individual MCP server connection handler.

**Features:**
- stdio subprocess management
- JSON-RPC message protocol
- Tool discovery on connection
- Async tool invocation

**Configuration:**
```yaml
mcp:
  enabled: true
  servers:
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
      env:
        MCP_ENV_VAR: "value"
```

### Integration Flow

```
1. Agent requests tool execution
   ↓
2. ToolRegistry.execute("server__tool")
   ↓
3. MCPBridge.call_tool("server__tool", args)
   ↓
4. MCPClient.call_tool() → JSON-RPC over stdio
   ↓
5. External MCP server processes request
   ↓
6. Response flows back through chain
   ↓
7. Result added to conversation memory
```

---

## Provider Router

### Purpose

Abstract multiple LLM providers behind unified interface using LiteLLM.

### Architecture (`src/capybara/providers/router.py`)

**Class:** `ProviderRouter`

**Modes:**

1. **Single Provider Mode** (default)
   - Direct `litellm.acompletion()` calls
   - Pass api_key and api_base directly
   - No router overhead

2. **Multi-Provider Mode** (when >1 provider)
   - Uses LiteLLM Router
   - Automatic fallback
   - Load balancing
   - Rate limiting

### Configuration

```python
@dataclass
class ProviderConfig:
    name: str = "default"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    rpm: int = 3500   # Requests per minute
    tpm: int = 90000  # Tokens per minute
```

### Supported Providers (via LiteLLM)

- OpenAI (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
- Anthropic (claude-3-opus, claude-3-sonnet, claude-3-haiku)
- Google (gemini-pro, gemini-flash)
- Custom OpenAI-compatible endpoints
- 100+ other providers

### Methods

1. **Streaming Completion**
   ```python
   async def complete(
       messages, model, tools, stream=True, timeout=120
   ) -> AsyncIterator[Any]:
       # Yields chunks as they arrive
   ```

2. **Non-Streaming Completion**
   ```python
   async def complete_non_streaming(
       messages, model, tools, timeout=120
   ) -> Any:
       # Returns complete response
   ```

### Fallback Strategy

**When Router enabled (multi-provider):**
```
Primary Provider
    ↓ (fails)
Fallback Provider 1
    ↓ (fails)
Fallback Provider 2
    ↓
Error returned to agent
```

**Routing Strategy:** `simple-shuffle`
- Randomize provider order
- Respect rate limits (rpm/tpm)
- Retry with exponential backoff

---

## Streaming Engine

### Purpose

Real-time token-by-token display with concurrent tool call collection.

### Architecture (`src/capybara/core/streaming.py`)

**Two Modes:**

1. **Streaming Mode**
   - Rich Live display
   - Markdown rendering
   - Incremental updates (4 FPS)

2. **Non-Streaming Mode**
   - Wait for complete response
   - Single markdown render

### Streaming Flow

```
LLM Stream
    │
    ├─► Text Deltas
    │   ├─► Collect to buffer
    │   ├─► Update Rich Live display
    │   └─► Render as Markdown
    │
    └─► Tool Call Deltas
        ├─► Collect by index
        ├─► Assemble complete tool calls
        └─► Return in response message
```

### Implementation Details

**Chunk Processing:**
```python
async for chunk in provider.complete(...):
    delta = chunk.choices[0].delta

    # Text content
    if delta.content:
        buffer.append(delta.content)
        live.update(Markdown("".join(buffer)))

    # Tool calls (streamed incrementally)
    if delta.tool_calls:
        collect_tool_calls(delta.tool_calls, tool_calls_dict)
```

**Tool Call Assembly:**
```python
# Chunks arrive like:
# {"index": 0, "id": "call_123", "function": {"name": "read_file"}}
# {"index": 0, "function": {"arguments": '{"path":'}}
# {"index": 0, "function": {"arguments": '"/file.py"}'}}

# Assembled into:
{
    "id": "call_123",
    "type": "function",
    "function": {
        "name": "read_file",
        "arguments": '{"path": "/file.py"}'
    }
}
```

**Rich Live Display:**
- Refresh rate: 4 FPS
- Transient: Clears after completion
- Markdown rendering: Syntax highlighting, formatting

---

## Configuration System

### Architecture

```
Pydantic Models (config.py)
    │
    ├─► YAML File (~/.capybara/config.yaml)
    │
    ├─► Environment Variables (CAPYBARA_*)
    │
    └─► Programmatic Defaults
```

### Configuration Hierarchy

**Priority (highest to lowest):**
1. Environment variables (`CAPYBARA_*`)
2. YAML file (`~/.capybara/config.yaml`)
3. Default values in code

### Configuration Models

**Main Config:**
```python
class CapybaraConfig:
    providers: list[ProviderConfig]
    memory: MemoryConfig
    tools: ToolsConfig
    mcp: MCPConfig
```

**Provider Config:**
```python
class ProviderConfig:
    name: str = "default"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    rpm: int = 3500
    tpm: int = 90000
```

**Memory Config:**
```python
class MemoryConfig:
    max_messages: Optional[int] = None
    max_tokens: int = 100_000
    persist: bool = True
```

**Tools Config:**
```python
class ToolsConfig:
    bash_enabled: bool = True
    bash_timeout: int = 120
    filesystem_enabled: bool = True
    allowed_paths: list[str] = ["."]
```

**MCP Config:**
```python
class MCPConfig:
    enabled: bool = False
    servers: dict[str, MCPServerConfig] = {}

class MCPServerConfig:
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
```

### YAML Example

```yaml
providers:
  - name: default
    model: openai/codevista-gpt-5-mini
    api_key: sk-xxx
    api_base: https://api.example.com
    rpm: 15
    tpm: 90000

memory:
  max_tokens: 100000
  persist: true

tools:
  bash_enabled: true
  bash_timeout: 120
  filesystem_enabled: true
  allowed_paths:
    - .
    - /home/user/projects

mcp:
  enabled: true
  servers:
    filesystem:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "."]
```

### Initialization

```python
# Create default config
capybara init  # Creates ~/.capybara/config.yaml

# Load config
config = load_config()  # Loads from ~/.capybara/config.yaml

# Show config
capybara config  # Display current configuration
```

---

## Data Flow

### Single-Run Mode (`capybara run "prompt"`)

```
1. CLI parses command
   ↓
2. Load configuration
   ↓
3. Initialize components:
   - ToolRegistry (builtin tools)
   - MCPBridge (if enabled)
   - ConversationMemory
   - ProviderRouter
   - Agent
   ↓
4. Set system prompt
   ↓
5. Agent.run(prompt)
   ├─► Add user message to memory
   ├─► Loop (max 10 turns):
   │   ├─► Get LLM completion
   │   ├─► Display response (streaming/non-streaming)
   │   ├─► Execute tool calls (if any)
   │   └─► Add results to memory
   └─► Return final response
   ↓
6. Cleanup:
   - Disconnect MCP servers
   - Close connections
   ↓
7. Exit
```

### Interactive Chat Mode (`capybara chat`)

```
1. CLI parses command
   ↓
2. Load configuration
   ↓
3. Initialize components (same as single-run)
   ↓
4. Setup prompt_toolkit:
   - History file (~/.capybara/history)
   - Key bindings (Ctrl+C)
   - Multiline support
   ↓
5. Display welcome panel
   ↓
6. Main loop:
   ├─► Prompt user for input
   ├─► Handle special commands:
   │   ├─► /clear → Clear memory
   │   ├─► /tokens → Show token count
   │   └─► exit/quit → Exit
   ├─► Show thinking message (random agent name)
   ├─► Agent.run(user_input)
   └─► Loop back
   ↓
7. Cleanup on exit
```

### Session Resume Mode (`capybara resume <session_id>`)

```
1. CLI parses command
   ↓
2. Load configuration
   ↓
3. Initialize ConversationStorage
   ↓
4. Load session messages from SQLite
   ↓
5. Initialize components
   ↓
6. Restore conversation history to memory
   ↓
7. Enter interactive loop (same as chat)
   ├─► But save messages to storage
   └─► Update session timestamps
```

### Message Flow Through System

```
User Input: "Read file.py and explain it"
    │
    ▼
Memory: [system, user("Read file.py...")]
    │
    ▼
LLM Request: {messages: [...], tools: [...]}
    │
    ▼
LLM Response: {
    tool_calls: [
        {name: "read_file", args: {path: "file.py"}}
    ]
}
    │
    ▼
Memory: [system, user, assistant(tool_calls)]
    │
    ▼
Tool Execution: read_file(path="file.py")
    │
    ▼
Tool Result: "1→import os\n2→import sys\n..."
    │
    ▼
Memory: [system, user, assistant, tool(result)]
    │
    ▼
LLM Request: {messages: [...], tools: [...]}
    │
    ▼
LLM Response: {
    content: "This file imports os and sys..."
}
    │
    ▼
Memory: [system, user, assistant, tool, assistant(final)]
    │
    ▼
User sees: "This file imports os and sys..."
```

---

## CLI Interface

### Commands

| Command | Description | Example |
|---------|-------------|---------|
| `capybara init` | Initialize configuration | `capybara init` |
| `capybara config` | Show current config | `capybara config` |
| `capybara run` | Single-run prompt | `capybara run "Fix bug in auth.py"` |
| `capybara chat` | Interactive chat | `capybara chat -m gpt-4o` |
| `capybara sessions` | List saved sessions | `capybara sessions` |
| `capybara resume` | Resume session | `capybara resume <session_id>` |

### CLI Options

**Global:**
- `--version` - Show version
- `--help` - Show help

**Run/Chat:**
- `-m, --model <model>` - Override default model
- `--no-stream` - Disable streaming output

### Interactive Commands

**In Chat Mode:**
- `exit` or `quit` - Exit chat
- `/clear` - Clear conversation history
- `/tokens` - Show current token count

### Directory Structure

```
~/.capybara/
├── config.yaml           # User configuration
├── conversations.db      # Session storage (SQLite)
├── history              # Command history (prompt_toolkit)
└── logs/
    └── capybara_YYYYMMDD.log  # Daily logs
```

### Logging

**Location:** `.capybara/logs/capybara_YYYYMMDD.log`

**Levels:**
- INFO: Agent initialization, turn start/end
- DEBUG: Tool calls, arguments, results
- WARNING/ERROR: Failures, exceptions

**Format:**
```
2025-12-25 23:07:23 | INFO | capybara.core.agent | Agent run started with model: gpt-4o
2025-12-25 23:07:24 | DEBUG | capybara.core.agent | Tool: read_file, Args: {'path': 'agent.py'}
2025-12-25 23:07:25 | DEBUG | capybara.core.agent | Tool read_file result: 1→"""Main async agent...
```

---

## Implementation Details

### Async Patterns

**Everywhere async:**
```python
# Agent
async def run(user_input: str) -> str

# Tools
async def read_file(path: str) -> str

# Provider
async def complete(...) -> AsyncIterator

# MCP
async def call_tool(name: str, args: dict) -> str

# Storage
async def save_message(...) -> None
```

**Concurrent Execution:**
```python
# Multiple tool calls in parallel
results = await asyncio.gather(
    execute_tool_1(),
    execute_tool_2(),
    execute_tool_3(),
    return_exceptions=True
)
```

### Error Handling

**Tool Execution:**
```python
try:
    result = await tool_function(**args)
    return str(result)
except Exception as e:
    return f"Error: {type(e).__name__}: {e}"
```

**Agent Loop:**
```python
try:
    response = await agent.run(prompt)
except KeyboardInterrupt:
    print("Interrupted")
except Exception as e:
    print(f"Error: {e}")
finally:
    await cleanup()
```

**MCP Connection:**
```python
try:
    client = MCPClient(name, config)
    if await client.connect():
        clients[name] = client
except Exception as e:
    logger.warning(f"MCP server {name} failed: {e}")
    # Continue with other servers
```

### Type Safety

**Pydantic Models:**
- Configuration validation
- Runtime type checking
- Auto-documentation

**Type Hints:**
- All functions typed
- mypy compatible
- IDE autocomplete

### Performance Optimizations

1. **Streaming**: Token-by-token display for better UX
2. **Concurrent Tools**: Parallel execution of multiple tools
3. **Token Counting**: Efficient sliding window with tiktoken
4. **Connection Pooling**: LiteLLM handles HTTP connection reuse
5. **Async I/O**: Non-blocking file and network operations

### Security Considerations

1. **Path Validation**: `allowed_paths` check for filesystem operations
2. **Command Injection**: No shell=True in bash execution
3. **API Key Storage**: Stored in config file with appropriate permissions
4. **Timeout Protection**: All operations have timeouts
5. **Input Validation**: Pydantic models validate all inputs

### Testing

**Coverage:**
- Unit tests for core components
- Integration tests for end-to-end flows
- Manual testing for CLI interactions

**Test Files:**
```
tests/
├── test_agent.py
├── test_memory.py
├── test_tools.py
├── test_config.py
└── test_integration.py
```

---

## Extension Points

### Adding New Builtin Tools

```python
# In src/capybara/tools/builtin/my_tools.py

from capybara.tools.registry import ToolRegistry

def register_my_tools(registry: ToolRegistry) -> None:
    @registry.tool(
        name="my_tool",
        description="My tool description",
        parameters={
            "type": "object",
            "properties": {
                "arg": {"type": "string"}
            },
            "required": ["arg"]
        }
    )
    async def my_tool(arg: str) -> str:
        # Implementation
        return result

# Then in __init__.py:
from .my_tools import register_my_tools
register_my_tools(registry)
```

### Adding MCP Servers

```yaml
# In ~/.capybara/config.yaml
mcp:
  enabled: true
  servers:
    my_server:
      command: "python"
      args: ["-m", "my_mcp_server"]
      env:
        API_KEY: "xxx"
```

### Custom System Prompts

```python
# Edit src/capybara/core/prompts.py
DEFAULT_SYSTEM_PROMPT = """
Your custom prompt here...
"""
```

### Adding New Providers

```yaml
# In ~/.capybara/config.yaml
providers:
  - name: my_provider
    model: "provider/model-name"
    api_key: "xxx"
    api_base: "https://api.provider.com"
    rpm: 100
    tpm: 50000
```

---

## Troubleshooting

### Common Issues

**Issue:** DNS resolution errors
- **Cause:** aiodns library conflicts
- **Fix:** `pip uninstall -y aiodns`

**Issue:** LiteLLM spam output
- **Cause:** Verbose logging enabled
- **Fix:** Already handled in `litellm_config.py`

**Issue:** Tool not found
- **Cause:** Tool not registered
- **Fix:** Check `builtin/__init__.py` initialization

**Issue:** Session not found
- **Cause:** Database not initialized
- **Fix:** `storage.initialize()` before loading

---

## Version History

**v1.0 (2025-12-25)**
- Initial architecture documentation
- Agent, Memory, Tools, MCP systems documented
- Complete data flow diagrams
- Configuration and CLI reference

---

**End of Architecture Document**
