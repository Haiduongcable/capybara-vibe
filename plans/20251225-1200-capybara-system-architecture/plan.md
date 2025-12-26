# CapybaraVibeCoding System Architecture Plan

> **Version:** 1.0.0  
> **Date:** 2025-12-25  
> **Status:** Ready for Implementation  
> **Inspired by:** Claude Code internal patterns + brainstorm.md requirements

---

## Executive Summary

This plan defines a comprehensive system architecture for **CapybaraVibeCoding**, an open-source AI coding assistant CLI built in Python. The architecture combines:

- **LiteLLM** for multi-provider support (100+ models)
- **Async streaming** for real-time token output
- **OpenAI-format tools** with MCP bridge for extensibility
- **Sliding window memory** with SQLite persistence
- **Click + Rich + prompt_toolkit** for production CLI UX

Key differentiators: MCP support (unique among Python tools), clean async architecture, configurable memory strategies, and maximum provider flexibility.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLI Interface Layer                                │
│                    Click (commands) + Rich (output) + prompt_toolkit (input)│
├─────────────────────────────────────────────────────────────────────────────┤
│                              Agent Core                                      │
│     ┌───────────────────────────────────────────────────────────────────┐   │
│     │                    Async Agent Loop                                │   │
│     │  user_input → completion → tool_calls → execution → response      │   │
│     └───────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Tool System Layer                                   │
│    ┌──────────────────┬───────────────────┬────────────────────────────┐   │
│    │   Built-in Tools │    MCP Bridge     │     Custom Tools           │   │
│    │  read, write,    │  stdio transport  │  (user-defined via        │   │
│    │  bash, glob,     │  tool discovery   │   decorator API)           │   │
│    │  grep, edit      │  schema conversion│                            │   │
│    └──────────────────┴───────────────────┴────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                         Memory Manager Layer                                 │
│    ┌──────────────────────────────────────────────────────────────────┐    │
│    │  Sliding Window (token-based) + System Prompt Preservation       │    │
│    │  SQLite Persistence (conversations, sessions)                    │    │
│    └──────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────────┤
│                         Provider Layer (LiteLLM)                             │
│    ┌──────────────────────────────────────────────────────────────────┐    │
│    │  Router: simple-shuffle strategy with fallback                   │    │
│    │  Streaming: acompletion + async for                              │    │
│    │  Tools: OpenAI format (auto-converted for Anthropic/Gemini)      │    │
│    └──────────────────────────────────────────────────────────────────┘    │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────────────────┤
│  OpenAI  │  Claude  │  Gemini  │  Ollama  │  Azure   │  Other 100+ models   │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────────────────┘
```

---

## Phase 1: Core Agent Loop Architecture

### 1.1 Agent Class Design

```python
# src/capybara/core/agent.py

import asyncio
import json
from typing import AsyncIterator, Optional
from dataclasses import dataclass, field
import litellm

@dataclass
class AgentConfig:
    model: str = "gpt-4o"
    max_turns: int = 10
    timeout: float = 120.0
    stream: bool = True

class Agent:
    """Async agent with streaming and tool calling."""
    
    def __init__(
        self,
        config: AgentConfig,
        memory: "ConversationMemory",
        tools: "ToolRegistry",
        console: "Console"
    ):
        self.config = config
        self.memory = memory
        self.tools = tools
        self.console = console
        
    async def run(self, user_input: str) -> str:
        """Main agent loop with tool use."""
        self.memory.add({"role": "user", "content": user_input})
        
        for turn in range(self.config.max_turns):
            # Get LLM response with streaming
            response = await self._get_completion()
            self.memory.add(response)
            
            # Check for tool calls
            tool_calls = response.get("tool_calls")
            if not tool_calls:
                return response.get("content", "")
            
            # Execute tools concurrently
            results = await self._execute_tools(tool_calls)
            for result in results:
                self.memory.add(result)
        
        return "Max turns exceeded"
    
    async def _get_completion(self) -> dict:
        """Stream completion with tool call collection."""
        collected_content = []
        collected_tool_calls = {}
        
        response = await litellm.acompletion(
            model=self.config.model,
            messages=self.memory.get_messages(),
            tools=self.tools.schemas if self.tools.schemas else None,
            stream=self.config.stream,
            timeout=self.config.timeout,
            stream_options={"include_usage": True}
        )
        
        # Stream with Rich Live display
        from rich.live import Live
        from rich.markdown import Markdown
        
        with Live(console=self.console, refresh_per_second=4) as live:
            async for chunk in response:
                delta = chunk.choices[0].delta
                
                # Collect content
                if delta.content:
                    collected_content.append(delta.content)
                    live.update(Markdown("".join(collected_content)))
                
                # Collect tool calls (streamed incrementally)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        if tc.id:
                            collected_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                collected_tool_calls[idx]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                collected_tool_calls[idx]["function"]["arguments"] += tc.function.arguments
        
        # Build response message
        message = {"role": "assistant"}
        if collected_content:
            message["content"] = "".join(collected_content)
        if collected_tool_calls:
            message["tool_calls"] = list(collected_tool_calls.values())
        
        return message
    
    async def _execute_tools(self, tool_calls: list) -> list[dict]:
        """Execute multiple tools concurrently."""
        async def execute_one(tc: dict) -> dict:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            
            self.console.print(f"[dim]→ {name}({list(args.keys())})[/dim]")
            result = await self.tools.execute(name, args)
            
            return {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result if isinstance(result, str) else json.dumps(result)
            }
        
        results = await asyncio.gather(
            *[execute_one(tc) for tc in tool_calls],
            return_exceptions=True
        )
        
        # Handle exceptions
        return [
            r if isinstance(r, dict) else {
                "role": "tool",
                "tool_call_id": "error",
                "content": f"Error: {r}"
            }
            for r in results
        ]
```

### 1.2 Streaming Patterns

**Key patterns from research:**

1. **True async streaming:** Use `async for` with `await acompletion()` - never synchronous iteration
2. **Chunk collection:** Buffer tool call arguments as they stream
3. **Live display:** Rich Live at 4fps for smooth UX
4. **Timeout protection:** Always set `timeout` parameter

```python
# Streaming completion pattern
async def stream_completion():
    response = await litellm.acompletion(
        model="gpt-4o",
        messages=messages,
        stream=True,
        timeout=30,  # CRITICAL: Prevent hanging
        stream_options={"include_usage": True}  # Token tracking
    )
    
    async for chunk in response:  # MUST use async for
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

---

## Phase 2: Tool System Design

### 2.1 Tool Registry (OpenAI Format)

```python
# src/capybara/tools/registry.py

from typing import Callable, Any
import asyncio
import functools

class ToolRegistry:
    """Registry for async tools with OpenAI schema format."""
    
    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._schemas: list[dict] = []
    
    def tool(
        self,
        name: str,
        description: str,
        parameters: dict
    ):
        """Decorator to register async tools."""
        def decorator(func: Callable):
            # Ensure async
            if not asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    return func(*args, **kwargs)
                target_func = async_wrapper
            else:
                target_func = func
            
            self._tools[name] = target_func
            self._schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "additionalProperties": False,
                        **parameters
                    }
                }
            })
            return target_func
        return decorator
    
    async def execute(self, name: str, arguments: dict) -> str:
        """Execute tool and return result as string."""
        if name not in self._tools:
            return f"Error: Unknown tool '{name}'"
        try:
            result = await self._tools[name](**arguments)
            return str(result) if not isinstance(result, str) else result
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
    
    @property
    def schemas(self) -> list[dict]:
        return self._schemas
```

### 2.2 Built-in Tools (Claude Code Inspired)

```python
# src/capybara/tools/builtin/filesystem.py

import aiofiles
from pathlib import Path
from ..registry import ToolRegistry

registry = ToolRegistry()

@registry.tool(
    name="read_file",
    description="""Read contents of a file.
    
Usage:
- Returns file content with line numbers
- Supports offset/limit for large files
- Use for reading code, config, or any text file""",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file"
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start from (1-indexed)",
                "default": 1
            },
            "limit": {
                "type": "integer",
                "description": "Max lines to read",
                "default": 500
            }
        },
        "required": ["path"]
    }
)
async def read_file(path: str, offset: int = 1, limit: int = 500) -> str:
    """Read file with line numbers."""
    try:
        async with aiofiles.open(path, 'r') as f:
            lines = await f.readlines()
        
        # Apply offset/limit
        start = max(0, offset - 1)
        end = start + limit
        selected = lines[start:end]
        
        # Format with line numbers
        result = []
        for i, line in enumerate(selected, start=start + 1):
            result.append(f"{i:4d}→{line.rstrip()}")
        
        return "\n".join(result) if result else "(empty file)"
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except Exception as e:
        return f"Error: {e}"


@registry.tool(
    name="write_file",
    description="""Write content to a file, creating if needed.
    
Usage:
- Creates parent directories automatically
- Overwrites existing content""",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute file path"},
            "content": {"type": "string", "description": "Content to write"}
        },
        "required": ["path", "content"]
    }
)
async def write_file(path: str, content: str) -> str:
    """Write content to file."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, 'w') as f:
            await f.write(content)
        return f"Successfully wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


@registry.tool(
    name="edit_file",
    description="""Edit file by replacing old_string with new_string.
    
Usage:
- old_string must be unique in the file
- Use replace_all=true to replace all occurrences""",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_string": {"type": "string", "description": "Text to replace"},
            "new_string": {"type": "string", "description": "Replacement text"},
            "replace_all": {"type": "boolean", "default": False}
        },
        "required": ["path", "old_string", "new_string"]
    }
)
async def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Edit file with string replacement."""
    try:
        async with aiofiles.open(path, 'r') as f:
            content = await f.read()
        
        # Check uniqueness
        count = content.count(old_string)
        if count == 0:
            return f"Error: '{old_string}' not found in {path}"
        if count > 1 and not replace_all:
            return f"Error: '{old_string}' found {count} times. Use replace_all=true or provide more context."
        
        # Replace
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        
        async with aiofiles.open(path, 'w') as f:
            await f.write(new_content)
        
        return f"Replaced {count if replace_all else 1} occurrence(s) in {path}"
    except Exception as e:
        return f"Error: {e}"


@registry.tool(
    name="glob",
    description="Find files matching a glob pattern",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g., **/*.py)"},
            "path": {"type": "string", "description": "Base directory", "default": "."}
        },
        "required": ["pattern"]
    }
)
async def glob_files(pattern: str, path: str = ".") -> str:
    """Find files matching glob pattern."""
    import glob as glob_module
    from pathlib import Path
    
    base = Path(path)
    matches = list(base.glob(pattern))
    
    if not matches:
        return f"No files match '{pattern}' in {path}"
    
    # Sort by modification time (newest first)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    return "\n".join(str(m) for m in matches[:100])  # Limit to 100


@registry.tool(
    name="bash",
    description="""Execute a bash command.
    
Usage:
- Use for git, npm, docker, etc.
- Prefer specialized tools for file operations
- Timeout: 120 seconds by default""",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "timeout": {"type": "number", "description": "Timeout in seconds", "default": 120}
        },
        "required": ["command"]
    }
)
async def bash(command: str, timeout: float = 120) -> str:
    """Execute bash command."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )
        
        output = stdout.decode() + stderr.decode()
        return output[:30000] if output else "(no output)"
    except asyncio.TimeoutError:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
```

### 2.3 MCP Bridge

```python
# src/capybara/tools/mcp/bridge.py

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
from typing import Optional

class MCPBridge:
    """Bridge MCP servers to OpenAI tool format."""
    
    def __init__(self, server_config: dict):
        self.server_params = StdioServerParameters(
            command=server_config["command"],
            args=server_config.get("args", []),
            env=server_config.get("env", {})
        )
        self.session: Optional[ClientSession] = None
        self._client_ctx = None
        self._tools_cache: dict = {}
    
    async def connect(self):
        """Establish connection to MCP server."""
        self._client_ctx = stdio_client(self.server_params)
        read, write = await self._client_ctx.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()
        
        # Cache tools
        tools_response = await self.session.list_tools()
        for tool in tools_response.tools:
            self._tools_cache[tool.name] = tool
    
    async def disconnect(self):
        """Clean up connection."""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self._client_ctx:
            await self._client_ctx.__aexit__(None, None, None)
    
    def get_openai_schemas(self) -> list[dict]:
        """Convert MCP tools to OpenAI format."""
        schemas = []
        for tool in self._tools_cache.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": f"mcp__{tool.name}",
                    "description": tool.description,
                    "parameters": tool.input_schema or {
                        "type": "object",
                        "properties": {}
                    }
                }
            })
        return schemas
    
    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call MCP tool and return result."""
        if not self.session:
            return "Error: MCP session not connected"
        
        # Strip prefix
        actual_name = name.replace("mcp__", "")
        
        try:
            result = await asyncio.wait_for(
                self.session.call_tool(actual_name, arguments),
                timeout=30.0
            )
            
            if hasattr(result, 'is_error') and result.is_error:
                return f"Error: {result.content}"
            
            return str(result.content)
        except asyncio.TimeoutError:
            return "Error: MCP tool call timed out"
        except Exception as e:
            return f"Error: {e}"


class MCPManager:
    """Manage multiple MCP server connections."""
    
    def __init__(self, config: dict):
        self.config = config
        self.bridges: dict[str, MCPBridge] = {}
    
    async def connect_all(self):
        """Connect to all configured MCP servers."""
        for name, server_config in self.config.get("servers", {}).items():
            bridge = MCPBridge(server_config)
            try:
                await bridge.connect()
                self.bridges[name] = bridge
            except Exception as e:
                print(f"Failed to connect to MCP server '{name}': {e}")
    
    async def disconnect_all(self):
        """Disconnect all MCP servers."""
        for bridge in self.bridges.values():
            await bridge.disconnect()
    
    def get_all_schemas(self) -> list[dict]:
        """Get combined tool schemas from all servers."""
        schemas = []
        for bridge in self.bridges.values():
            schemas.extend(bridge.get_openai_schemas())
        return schemas
    
    async def call_tool(self, name: str, arguments: dict) -> str:
        """Route tool call to appropriate MCP server."""
        for bridge in self.bridges.values():
            if name.replace("mcp__", "") in bridge._tools_cache:
                return await bridge.call_tool(name, arguments)
        return f"Error: MCP tool '{name}' not found"
```

---

## Phase 3: Memory Management System

### 3.1 Sliding Window Memory

```python
# src/capybara/memory/window.py

from dataclasses import dataclass, field
from typing import Optional
import tiktoken

@dataclass
class MemoryConfig:
    max_messages: Optional[int] = None     # None = unlimited
    max_tokens: Optional[int] = 100_000    # Token-based limit
    preserve_system: bool = True           # Always keep system prompt
    model: str = "gpt-4"                   # For token counting

@dataclass
class ConversationMemory:
    config: MemoryConfig
    messages: list[dict] = field(default_factory=list)
    
    def __post_init__(self):
        try:
            self._encoder = tiktoken.encoding_for_model(self.config.model)
        except KeyError:
            self._encoder = tiktoken.get_encoding("cl100k_base")
    
    def add(self, message: dict) -> None:
        """Add message and trim if needed."""
        self.messages.append(message)
        self._trim()
    
    def get_messages(self) -> list[dict]:
        """Get current message list."""
        return self.messages.copy()
    
    def clear(self, keep_system: bool = True) -> None:
        """Clear conversation, optionally keeping system prompt."""
        if keep_system and self.config.preserve_system:
            self.messages = [m for m in self.messages if m["role"] == "system"]
        else:
            self.messages = []
    
    def _count_tokens(self, messages: list[dict]) -> int:
        """Count tokens in messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if content:
                total += len(self._encoder.encode(str(content)))
            # Tool calls add tokens too
            if "tool_calls" in msg:
                total += len(self._encoder.encode(str(msg["tool_calls"])))
        return total
    
    def _trim(self) -> None:
        """Trim messages to fit within limits."""
        if not self.messages:
            return
        
        # Separate system messages
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        other_msgs = [m for m in self.messages if m["role"] != "system"]
        
        # Trim by message count
        if self.config.max_messages and len(other_msgs) > self.config.max_messages:
            other_msgs = other_msgs[-self.config.max_messages:]
        
        # Trim by token count (keep most recent)
        if self.config.max_tokens:
            while (
                other_msgs and
                self._count_tokens(system_msgs + other_msgs) > self.config.max_tokens
            ):
                other_msgs.pop(0)
        
        self.messages = system_msgs + other_msgs if self.config.preserve_system else other_msgs
```

### 3.2 SQLite Persistence

```python
# src/capybara/memory/storage.py

import aiosqlite
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

class ConversationStorage:
    """SQLite-based conversation persistence."""
    
    def __init__(self, db_path: str = "~/.capybara/conversations.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self):
        """Create tables if needed."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    model TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    tool_calls TEXT,
                    created_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            await db.commit()
    
    async def create_session(self, model: str, title: Optional[str] = None) -> str:
        """Create new conversation session."""
        import uuid
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, title or f"Session {session_id}", model, now, now)
            )
            await db.commit()
        
        return session_id
    
    async def save_message(self, session_id: str, message: dict):
        """Save message to session."""
        now = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    message.get("role"),
                    message.get("content"),
                    json.dumps(message.get("tool_calls")) if "tool_calls" in message else None,
                    now
                )
            )
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id)
            )
            await db.commit()
    
    async def load_session(self, session_id: str) -> list[dict]:
        """Load messages from session."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role, content, tool_calls FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,)
            ) as cursor:
                messages = []
                async for row in cursor:
                    msg = {"role": row[0]}
                    if row[1]:
                        msg["content"] = row[1]
                    if row[2]:
                        msg["tool_calls"] = json.loads(row[2])
                    messages.append(msg)
                return messages
    
    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent sessions."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, title, model, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ) as cursor:
                return [
                    {"id": r[0], "title": r[1], "model": r[2], "updated_at": r[3]}
                    async for r in cursor
                ]
```

---

## Phase 4: Provider Abstraction (LiteLLM)

### 4.1 Router Configuration

```python
# src/capybara/providers/router.py

from litellm import Router
from litellm.router import RetryPolicy

def create_router(config: dict) -> Router:
    """Create LiteLLM router with fallback and retry logic."""
    
    model_list = []
    
    # Build model list from config
    for i, provider in enumerate(config.get("providers", [])):
        model_list.append({
            "model_name": provider.get("name", "default"),
            "litellm_params": {
                "model": provider["model"],
                "api_key": provider.get("api_key"),
                "api_base": provider.get("api_base"),
                "rpm": provider.get("rpm", 3500),
                "tpm": provider.get("tpm", 90000)
            },
            "order": i + 1
        })
    
    # Retry policy per error type
    retry_policy = RetryPolicy(
        ContentPolicyViolationErrorRetries=3,
        AuthenticationErrorRetries=0,  # Don't retry auth errors
        BadRequestErrorRetries=1,
        TimeoutErrorRetries=2,
        RateLimitErrorRetries=3,
        APIConnectionErrorRetries=2
    )
    
    return Router(
        model_list=model_list,
        routing_strategy="simple-shuffle",  # Recommended for production
        retry_policy=retry_policy,
        num_retries=3,
        timeout=30,
        cooldown_time=30
    )
```

### 4.2 Provider Capability Detection

```python
# src/capybara/providers/capabilities.py

from litellm import supports_parallel_function_calling, get_max_tokens

def get_model_capabilities(model: str) -> dict:
    """Get model capabilities for dynamic configuration."""
    return {
        "parallel_tool_calls": supports_parallel_function_calling(model=model),
        "max_tokens": get_max_tokens(model),
        "supports_streaming": True,  # All major providers
        "supports_tools": True  # Via LiteLLM conversion
    }
```

---

## Phase 5: CLI Interface Structure

### 5.1 Click Command Structure

```python
# src/capybara/cli/main.py

import asyncio
import click
from rich.console import Console
from rich.panel import Panel

console = Console()

@click.group()
@click.version_option(prog_name="capybara")
def cli():
    """CapybaraVibeCoding - AI-powered coding assistant."""
    pass

@cli.command()
@click.option("--model", "-m", default="gpt-4o", help="Model to use")
@click.option("--no-stream", is_flag=True, help="Disable streaming")
def chat(model: str, no_stream: bool):
    """Start interactive chat session."""
    asyncio.run(_chat_async(model, not no_stream))

@cli.command()
@click.argument("prompt")
@click.option("--model", "-m", default="gpt-4o")
def run(prompt: str, model: str):
    """Run a single prompt and exit."""
    asyncio.run(_run_async(prompt, model))

@cli.command()
def init():
    """Initialize configuration in ~/.capybara/"""
    from .commands.config import init_config
    init_config()

@cli.command()
def sessions():
    """List conversation sessions."""
    asyncio.run(_list_sessions())
```

### 5.2 Interactive Chat with prompt_toolkit

```python
# src/capybara/cli/interactive.py

import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.panel import Panel
from pathlib import Path

console = Console()

async def interactive_chat(model: str, stream: bool = True):
    """Interactive chat loop with async input and streaming output."""
    
    from ..core.agent import Agent, AgentConfig
    from ..memory.window import ConversationMemory, MemoryConfig
    from ..tools.builtin import registry as default_tools
    
    # Setup
    config = AgentConfig(model=model, stream=stream)
    memory = ConversationMemory(config=MemoryConfig())
    agent = Agent(config=config, memory=memory, tools=default_tools, console=console)
    
    # Setup prompt_toolkit
    history_file = Path.home() / ".capybara" / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    
    session = PromptSession(
        history=FileHistory(str(history_file)),
        multiline=False
    )
    
    # Keybindings
    bindings = KeyBindings()
    
    @bindings.add('c-c')
    def interrupt(event):
        """Handle Ctrl+C gracefully."""
        raise KeyboardInterrupt()
    
    # Welcome
    console.print(Panel.fit(
        f"[bold green]CapybaraVibeCoding[/bold green]\n"
        f"Model: {model}\n"
        "Type 'exit' to quit, '/clear' to reset",
        title="Welcome"
    ))
    
    # Main loop
    while True:
        try:
            with patch_stdout():
                user_input = await session.prompt_async(
                    ">>> ",
                    key_bindings=bindings
                )
            
            if not user_input.strip():
                continue
            if user_input.lower() in ("exit", "quit"):
                console.print("[dim]Goodbye![/dim]")
                break
            if user_input == "/clear":
                memory.clear()
                console.print("[dim]Conversation cleared[/dim]")
                continue
            
            # Run agent
            await agent.run(user_input)
            console.print()  # Newline after response
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
            continue
        except EOFError:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
```

---

## Phase 6: Configuration System

### 6.1 Pydantic Configuration

```python
# src/capybara/core/config.py

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import yaml

class ProviderConfig(BaseModel):
    name: str = "default"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    rpm: int = 3500
    tpm: int = 90000

class MemoryConfig(BaseModel):
    max_messages: Optional[int] = None
    max_tokens: int = 100_000
    persist: bool = True

class ToolsConfig(BaseModel):
    bash_enabled: bool = True
    bash_timeout: int = 120
    filesystem_enabled: bool = True
    allowed_paths: list[str] = ["."]

class MCPServerConfig(BaseModel):
    command: str
    args: list[str] = []
    env: dict[str, str] = {}

class MCPConfig(BaseModel):
    enabled: bool = False
    servers: dict[str, MCPServerConfig] = {}

class CapybaraConfig(BaseSettings):
    """Main configuration."""
    providers: list[ProviderConfig] = Field(default_factory=lambda: [ProviderConfig()])
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    
    class Config:
        env_prefix = "CAPYBARA_"
        env_file = ".env"

def load_config() -> CapybaraConfig:
    """Load config from file and environment."""
    config_path = Path.home() / ".capybara" / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
            return CapybaraConfig(**data)
    return CapybaraConfig()
```

### 6.2 Default Configuration File

```yaml
# ~/.capybara/config.yaml

providers:
  - name: openai
    model: gpt-4o
    # api_key: set via OPENAI_API_KEY env var
    rpm: 3500
    tpm: 90000
  - name: anthropic
    model: claude-3-5-sonnet-20241022
    # api_key: set via ANTHROPIC_API_KEY env var
    rpm: 4000
    tpm: 100000

memory:
  max_tokens: 100000
  persist: true

tools:
  bash_enabled: true
  bash_timeout: 120
  filesystem_enabled: true
  allowed_paths: ["."]

mcp:
  enabled: false
  servers:
    # example:
    #   command: python
    #   args: ["-m", "my_mcp_server"]
```

---

## Project Structure

```
capybara-vibe-coding/
├── src/
│   └── capybara/
│       ├── __init__.py
│       ├── __main__.py
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py           # Click entrypoint
│       │   ├── interactive.py    # prompt_toolkit chat
│       │   └── commands/
│       │       ├── chat.py
│       │       ├── run.py
│       │       ├── config.py
│       │       └── sessions.py
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── agent.py          # Main async agent loop
│       │   ├── conversation.py   # Message handling
│       │   └── config.py         # Pydantic settings
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── router.py         # LiteLLM router
│       │   ├── capabilities.py   # Model capability detection
│       │   └── schema.py         # OpenAI tool schema types
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py       # Tool registration
│       │   ├── executor.py       # Async execution
│       │   ├── builtin/
│       │   │   ├── __init__.py
│       │   │   ├── filesystem.py
│       │   │   ├── bash.py
│       │   │   └── search.py
│       │   └── mcp/
│       │       ├── __init__.py
│       │       ├── client.py
│       │       └── bridge.py
│       │
│       └── memory/
│           ├── __init__.py
│           ├── window.py         # Sliding window
│           ├── tokenizer.py      # Token counting
│           └── storage.py        # SQLite persistence
│
├── tests/
│   ├── conftest.py
│   ├── test_agent.py
│   ├── test_tools.py
│   ├── test_memory.py
│   └── test_mcp.py
│
├── pyproject.toml
├── README.md
├── LICENSE
└── .github/
    └── workflows/
        └── ci.yml
```

---

## Dependencies

```toml
[project]
name = "capybara-vibe-coding"
version = "0.1.0"
description = "AI-powered coding assistant CLI"
requires-python = ">=3.10"
dependencies = [
    "litellm>=1.40.0",
    "click>=8.1.0",
    "rich>=13.0.0",
    "prompt-toolkit>=3.0.36",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "pyyaml>=6.0.0",
    "tiktoken>=0.5.0",
    "aiofiles>=23.0.0",
    "aiosqlite>=0.19.0",
]

[project.optional-dependencies]
mcp = ["mcp>=1.0.0"]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
capybara = "capybara.cli.main:cli"
```

---

## Implementation Phases

### Phase 1: Foundation
- Project scaffolding (pyproject.toml, structure)
- Config system with pydantic-settings
- Basic LiteLLM integration with streaming
- Click + Rich CLI entrypoint

### Phase 2: Core Agent
- Async agent loop with tool calling
- Built-in tools (read, write, edit, glob, bash)
- Concurrent tool execution
- Error handling and timeouts

### Phase 3: Memory & Persistence
- Sliding window with token counting
- SQLite conversation storage
- Session management (list, continue)

### Phase 4: MCP Integration
- MCP client with stdio transport
- Tool discovery and schema bridging
- Multi-server management

### Phase 5: Polish
- Interactive chat with prompt_toolkit
- Progress indicators
- Keyboard interrupt handling
- Multi-line input support

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Provider Layer | LiteLLM | 100+ models, unified API, maintained |
| Tool Schema | OpenAI format | Industry standard, LiteLLM converts |
| Streaming | async for + acompletion | True non-blocking, token-by-token |
| Memory | Sliding window + SQLite | Balance cost vs context, persistence |
| CLI Framework | Click + Rich + prompt_toolkit | Best combo for command + interactive |
| MCP Transport | stdio | Lowest latency for local servers |
| Config | Pydantic + YAML | Type safety, env var support |

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| LiteLLM tool inconsistency | Test matrix across providers, fallback modes |
| MCP complexity | Start stdio-only, defer advanced transport |
| Streaming edge cases | Timeout + chunk buffer + error recovery |
| Token counting variance | Use tiktoken, accept some inaccuracy |
| Provider rate limits | Router with simple-shuffle + retry policy |

---

## Success Metrics

### MVP (v0.1.0)
- Chat with 3+ providers
- File read/write/edit tools
- Bash execution with timeout
- Sliding window memory
- Basic CLI working

### v0.2.0
- MCP integration complete
- SQLite persistence
- 5+ built-in tools
- Session continuation

### v1.0.0
- Production stable
- Test coverage >80%
- Documentation complete
- 10+ MCP server compatibility

---

## References

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [MCP Specification](https://modelcontextprotocol.io/)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Rich Documentation](https://rich.readthedocs.io/)
- [Click Documentation](https://click.palletsprojects.com/)
- [prompt_toolkit Documentation](https://python-prompt-toolkit.readthedocs.io/)

---

*Plan generated: 2025-12-25*
*Ready for implementation*
