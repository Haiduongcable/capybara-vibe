# MCP Integration Patterns for Python CLI Tools

**Research Date:** December 25, 2025
**Focus:** Production-ready MCP integration for Python CLI applications
**Key Sources:** Official MCP Python SDK, FastMCP 2.0, OpenAI Agents SDK, MCP Specification 2025-03-26

---

## 1. MCP Python SDK Overview

### What is MCP?

Model Context Protocol (MCP) is an open standard developed by Anthropic that enables LLM applications to:
- Discover and call external tools (exposed by MCP servers)
- Access resources and prompts in a standardized way
- Use multiple transport mechanisms (stdio, SSE, HTTP streaming)

Key design principle: **Separates context provision from LLM interaction**, allowing servers to expose tools/data through a single standardized interface.

### Official Python SDK

- **Repository:** [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
- **Package:** `mcp` on PyPI
- **Specification:** 2025-03-26 (latest)
- **Status:** Production-ready, actively maintained
- **Alternative Framework:** FastMCP 2.0 (wrapper providing additional features)

---

## 2. MCP Python SDK Client Implementation Patterns

### 2.1 Basic Client Lifecycle Pattern

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio

server_params = StdioServerParameters(
    command="python",
    args=["path/to/server.py"],
    env={"CUSTOM_VAR": "value"}
)

async def main():
    # Context manager handles subprocess spawning/killing
    async with stdio_client(server_params) as (read, write):
        # Context manager handles session lifecycle
        async with ClientSession(read, write) as session:
            # Initialize handshake with server
            await session.initialize()

            # Discover available tools
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                print(f"Tool: {tool.name}")

            # Call a tool
            result = await session.call_tool(
                name="tool_name",
                arguments={"param": "value"}
            )
            print(f"Result: {result}")

asyncio.run(main())
```

### 2.2 Core Components

| Component | Role | Lifecycle |
|-----------|------|-----------|
| `StdioServerParameters` | Configures subprocess spawning (command, args, env) | Static config |
| `stdio_client()` | Spawns subprocess, manages stdin/stdout pipes | Context manager |
| `ClientSession` | Protocol handler, sends init/requests, receives responses | Context manager |
| `session.initialize()` | Capability negotiation (required first step) | Async operation |
| `session.list_tools()` | Discovers available tools | Async operation |
| `session.call_tool()` | Executes tool with arguments | Async operation |

### 2.3 Multi-Server Pattern (Stateless)

For multiple independent tool calls without maintaining session state:

```python
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

async def call_tool_on_server(server_config, tool_name, args):
    """Execute single tool call, creates fresh session for each call"""
    if server_config.get("type") == "stdio":
        params = StdioServerParameters(
            command=server_config["command"],
            args=server_config["args"]
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, args)
    elif server_config.get("type") == "sse":
        params = dict(server_config["params"])  # URL, headers, etc.
        async with sse_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, args)
```

**Note:** Stateless approach spawns new subprocess per call (resource overhead). Use for: ad-hoc operations, isolated sandboxes. For frequent calls, maintain persistent session.

### 2.4 Persistent Session Pattern (Stateful)

For maintaining context across multiple tool calls:

```python
class MCPClientManager:
    def __init__(self, server_params):
        self.server_params = server_params
        self.session = None
        self._client_ctx = None

    async def connect(self):
        """Establish persistent connection"""
        self._client_ctx = stdio_client(self.server_params)
        read, write = await self._client_ctx.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()

    async def call_tool(self, name, args):
        """Reuse session for multiple calls"""
        if not self.session:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self.session.call_tool(name, args)

    async def disconnect(self):
        """Clean up persistent session"""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self._client_ctx:
            await self._client_ctx.__aexit__(None, None, None)

# Usage
manager = MCPClientManager(StdioServerParameters(...))
try:
    await manager.connect()
    result1 = await manager.call_tool("tool1", {...})
    result2 = await manager.call_tool("tool2", {...})
finally:
    await manager.disconnect()
```

---

## 3. Transport Options & Implementation

### 3.1 Stdio Transport (PRIMARY)

**Best For:** CLI tools, local development, subprocess-based execution

```python
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters

server_params = StdioServerParameters(
    command="uv",  # or "python", "node", etc.
    args=["run", "server.py", "stdio"],
    env={"PYTHONPATH": "/custom/path"}
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        # ... use session
```

**Subprocess Management:**
- Python spawns subprocess via `subprocess.Popen`
- Pipes connected: stdin ← client writes, stdout → client reads
- Server sees same pipes as child process
- Client kills process on context exit (SIGTERM → SIGKILL)
- No network latency, tight coupling

**Advantages:**
- Direct process control
- No network overhead
- Tight integration with CLI tool
- Simple error propagation

**Disadvantages:**
- Subprocess per connection (resource-heavy for many clients)
- Platform-specific process handling
- Not suitable for remote servers

### 3.2 SSE Transport (DEPRECATED - Migrate to HTTP Stream)

**Status:** Deprecated as of MCP spec 2025-03-26
**Migration:** Use HTTP Stream (Streamable HTTP) transport instead

**Legacy Usage (still supported for compatibility):**

```python
from mcp.client.sse import sse_client

sse_params = {
    "url": "http://localhost:8000/sse",
    "headers": {"Authorization": "Bearer token"}
}

async with sse_client(sse_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        # ... use session
```

**Issues with SSE:**
- Server-Sent Events is one-way (server → client only)
- Requires bidirectional handling workaround
- High-level frameworks misuse timeouts (breaking context manager protocol)

### 3.3 HTTP Stream Transport (RECOMMENDED - NEW)

**Introduced:** MCP Spec 2025-03-26
**Status:** Production-ready, recommended for new implementations

```python
from mcp.client.streamable_http import streamable_http_client

http_params = {
    "url": "http://localhost:8000/mcp",
    "headers": {"Authorization": "Bearer token"},
    "timeout": 30  # seconds
}

async with streamable_http_client(http_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        # ... use session
```

**Advantages over SSE:**
- True bidirectional HTTP streaming
- Cleaner protocol implementation
- Better timeout handling
- Easier to proxy and scale
- Backward compatible proxy support

**When to Use Each Transport:**

| Transport | Use Case | Stateless | Performance |
|-----------|----------|-----------|-------------|
| **stdio** | Local CLI, dev, subprocess | Can be both | Lowest latency |
| **HTTP Stream** | Remote servers, scaling, API-based | Both | Low latency |
| **SSE (legacy)** | Existing servers, backward compat | Usually | Medium latency |

---

## 4. Tool Discovery & Schema Bridging

### 4.1 Tool Discovery Pattern

```python
async def discover_tools(session):
    """Discover all available tools from MCP server"""
    response = await session.list_tools()
    # response.tools is list[Tool]
    # Each Tool has: name, description, inputSchema (JSONSchema)
    return {tool.name: tool for tool in response.tools}

async def print_tool_info(session):
    tools = await discover_tools(session)
    for name, tool in tools.items():
        print(f"\nTool: {name}")
        print(f"Description: {tool.description}")
        print(f"Input Schema: {tool.input_schema}")
```

### 4.2 MCP Tool Schema Structure

MCP uses JSON Schema (draft 2020-12) for input schemas:

```json
{
  "name": "search_files",
  "description": "Search files by pattern",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "File glob pattern"
      },
      "limit": {
        "type": "integer",
        "description": "Max results"
      }
    },
    "required": ["pattern"]
  }
}
```

### 4.3 MCP to OpenAI Function Schema Conversion

**Key Difference:** OpenAI wraps functions, MCP flattens them

**Conversion Pattern:**

```python
def convert_mcp_tool_to_openai(mcp_tool):
    """Convert MCP Tool to OpenAI function_calling format"""
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": mcp_tool.input_schema or {
                "type": "object",
                "properties": {}
            }
        }
    }

async def get_openai_tools(session):
    """Get all MCP tools converted to OpenAI format"""
    tools = await session.list_tools()
    return [convert_mcp_tool_to_openai(tool) for tool in tools.tools]
```

**Important Edge Case:** OpenAI requires `properties` field
- MCP allows omitting `properties` (means no parameters)
- OpenAI API fails without `properties`
- Fix: Add empty `"properties": {}` if missing

```python
def ensure_openai_compatible(openai_schema):
    """Ensure schema has properties field for OpenAI compatibility"""
    if "function" in openai_schema:
        params = openai_schema["function"].get("parameters", {})
        if "properties" not in params:
            params["properties"] = {}
        openai_schema["function"]["parameters"] = params
    return openai_schema
```

### 4.4 Tool Calling with Schema-Aware Validation

```python
from typing import Any
import json

async def call_tool_with_validation(
    session,
    tool_name: str,
    arguments: dict[str, Any]
):
    """Call tool with schema validation"""
    # Get tool schema for validation
    tools_response = await session.list_tools()
    tool = next(
        (t for t in tools_response.tools if t.name == tool_name),
        None
    )

    if not tool:
        raise ValueError(f"Tool '{tool_name}' not found")

    # Validate arguments against input schema
    required_props = tool.input_schema.get("required", [])
    for prop in required_props:
        if prop not in arguments:
            raise ValueError(f"Missing required argument: {prop}")

    # Call tool
    return await session.call_tool(tool_name, arguments)
```

---

## 5. MCP Lifecycle & Protocol Management

### 5.1 Three-Phase Lifecycle (Specification 2025-03-26)

**Phase 1: Initialization**
- Client sends `initialize` request with protocol version, capabilities
- Server responds with supported version, capabilities
- Client sends `initialized` notification
- **This phase MUST complete before operation phase**

```python
async def initialize_session(session):
    """Complete MCP initialization handshake"""
    try:
        init_response = await session.initialize()
        # Check negotiated capabilities
        if "tools" in init_response.capabilities:
            print("Server supports tools")
        if "resources" in init_response.capabilities:
            print("Server supports resources")
        return init_response
    except Exception as e:
        raise RuntimeError(f"Initialization failed: {e}")
```

**Phase 2: Operation**
- Normal tool/resource/prompt operations
- Both parties use negotiated capabilities only
- Requests/responses handled via JSON-RPC 2.0

**Phase 3: Shutdown**
- Transport-specific termination
- stdio: Close stdin, wait for process termination
- HTTP: Close connections
- **Context managers handle this automatically**

### 5.2 Protocol Version Negotiation

```python
SUPPORTED_VERSIONS = ["2025-03-26", "2024-11-05"]

async def get_negotiated_version(session):
    """Determine protocol version negotiated with server"""
    init_result = await session.initialize()
    return init_result.protocol_version
```

### 5.3 Capability Discovery

```python
async def get_server_capabilities(session):
    """Discover server capabilities"""
    init_result = await session.initialize()
    caps = init_result.capabilities

    return {
        "supports_tools": "tools" in caps,
        "supports_resources": "resources" in caps,
        "supports_prompts": "prompts" in caps,
        "supports_logging": "logging" in caps
    }
```

---

## 6. Error Handling & Recovery Patterns

### 6.1 Error Type Classification

**Transport-Level Errors:**
- Network timeouts, connection refused, broken pipes
- Handle with retry + exponential backoff
- May require process restart

**Protocol-Level Errors:**
- Invalid JSON, malformed requests, unsupported methods
- JSON-RPC 2.0 error responses
- Cannot recover - fix client code

**Application-Level Errors:**
- Tool execution failures, business logic errors
- Returned via `isError` flag in tool response
- LLM can see and reason about these

### 6.2 Retry Pattern with Exponential Backoff

```python
import asyncio
from typing import TypeVar, Callable, Any

T = TypeVar('T')

async def call_with_retry(
    func: Callable[..., Any],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0
) -> Any:
    """
    Call async function with exponential backoff retry.

    Useful for transient failures:
    - Timeout errors
    - Temporary connection issues
    - Server temporarily unavailable
    """
    last_error = None
    delay = initial_delay

    for attempt in range(max_attempts):
        try:
            return await func()
        except (ConnectionError, TimeoutError, asyncio.TimeoutError) as e:
            last_error = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)
                delay *= backoff_factor
            continue

    raise RuntimeError(
        f"Failed after {max_attempts} attempts: {last_error}"
    )

# Usage
async def call_tool_with_retry(session, tool_name, args):
    async def _call():
        return await session.call_tool(tool_name, args)

    return await call_with_retry(_call, max_attempts=3)
```

### 6.3 Circuit Breaker Pattern

```python
import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Too many failures, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    async def call(self, func, *args, **kwargs):
        """Execute function through circuit breaker"""
        if self.state == CircuitState.OPEN:
            if (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise RuntimeError("Circuit breaker is OPEN - service unavailable")

        try:
            result = await func(*args, **kwargs)
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
            raise

# Usage
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

async def call_tool_with_circuit_breaker(session, tool_name, args):
    async def _call():
        return await session.call_tool(tool_name, args)

    return await breaker.call(_call)
```

### 6.4 Comprehensive Error Handler

```python
from dataclasses import dataclass

@dataclass
class ToolCallResult:
    success: bool
    data: Any = None
    error: str = None
    error_type: str = None  # "transport", "protocol", "application"

async def call_tool_safely(
    session,
    tool_name: str,
    arguments: dict
) -> ToolCallResult:
    """Call tool with comprehensive error handling"""
    try:
        result = await session.call_tool(tool_name, arguments)

        # Check for application-level errors
        if hasattr(result, 'is_error') and result.is_error:
            return ToolCallResult(
                success=False,
                error=str(result.content),
                error_type="application"
            )

        return ToolCallResult(success=True, data=result)

    except ConnectionError as e:
        return ToolCallResult(
            success=False,
            error=f"Connection failed: {e}",
            error_type="transport"
        )
    except TimeoutError as e:
        return ToolCallResult(
            success=False,
            error=f"Request timeout: {e}",
            error_type="transport"
        )
    except ValueError as e:
        return ToolCallResult(
            success=False,
            error=f"Invalid request: {e}",
            error_type="protocol"
        )
    except Exception as e:
        return ToolCallResult(
            success=False,
            error=f"Unexpected error: {e}",
            error_type="unknown"
        )
```

---

## 7. Timeout Handling

### 7.1 Timeout Configuration Strategy

**MCP Specification Requirements:**
- Implementations SHOULD establish timeouts for all requests
- Prevent hung connections and resource exhaustion
- Allow per-request timeout configuration
- Enforce maximum timeout (regardless of progress notifications)

```python
import asyncio
from typing import Optional

async def call_tool_with_timeout(
    session,
    tool_name: str,
    arguments: dict,
    request_timeout: float = 30.0,
    max_timeout: float = 300.0  # Hard limit
) -> Any:
    """
    Call tool with request-level timeout.

    Args:
        request_timeout: Timeout for this specific request
        max_timeout: Absolute maximum (hard limit)
    """
    # Enforce maximum timeout
    effective_timeout = min(request_timeout, max_timeout)

    try:
        return await asyncio.wait_for(
            session.call_tool(tool_name, arguments),
            timeout=effective_timeout
        )
    except asyncio.TimeoutError:
        # Handle timeout - attempt cancellation notification
        # (MCP spec allows sending cancellation)
        raise TimeoutError(
            f"Tool call exceeded {effective_timeout}s timeout"
        )
```

### 7.2 Connection Timeout Management

```python
async def connect_with_timeout(
    server_params,
    connection_timeout: float = 10.0
) -> ClientSession:
    """Establish MCP connection with timeout"""
    try:
        # Timeout for subprocess spawn + initialization
        async with asyncio.timeout(connection_timeout):
            async with stdio_client(server_params) as (read, write):
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                return session
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"Failed to connect within {connection_timeout}s"
        )
```

### 7.3 Progress Monitoring (Reset Timeout on Progress)

```python
async def call_tool_with_progress_monitoring(
    session,
    tool_name: str,
    arguments: dict,
    request_timeout: float = 30.0,
    max_absolute_timeout: float = 300.0
):
    """
    Call tool with timeout reset on progress notifications.

    Per MCP spec: can reset timeout when receiving progress notifications,
    but must enforce absolute maximum timeout.
    """
    start_time = asyncio.get_event_loop().time()

    async def check_max_timeout():
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > max_absolute_timeout:
            raise TimeoutError(
                f"Absolute maximum timeout ({max_absolute_timeout}s) exceeded"
            )

    try:
        # Actual implementation depends on SDK progress notification support
        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments),
            timeout=request_timeout
        )
        await check_max_timeout()
        return result
    except asyncio.TimeoutError:
        # Check if we hit request timeout or max absolute
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= max_absolute_timeout:
            raise TimeoutError(f"Absolute maximum timeout exceeded")
        else:
            raise TimeoutError(f"Request timeout ({request_timeout}s) exceeded")
```

---

## 8. Connection Pooling Pattern

### 8.1 Single-Server Connection Pool

For maintaining multiple persistent connections to one MCP server:

```python
import asyncio
from collections import deque
from dataclasses import dataclass

@dataclass
class PooledConnection:
    session: ClientSession
    in_use: bool = False
    last_used: float = 0

class MCPConnectionPool:
    def __init__(
        self,
        server_params: StdioServerParameters,
        pool_size: int = 5,
        timeout: float = 30.0
    ):
        self.server_params = server_params
        self.pool_size = pool_size
        self.timeout = timeout
        self.connections: deque[PooledConnection] = deque()
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Create pool of connections"""
        for _ in range(self.pool_size):
            async with stdio_client(self.server_params) as (read, write):
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                self.connections.append(PooledConnection(session=session))

    async def acquire(self) -> ClientSession:
        """Get available connection from pool"""
        async with self._lock:
            while self.connections:
                conn = self.connections.popleft()
                if not conn.in_use:
                    conn.in_use = True
                    return conn.session

            # All connections in use - wait for one to be released
            raise RuntimeError("No available connections in pool")

    async def release(self, session: ClientSession):
        """Return connection to pool"""
        async with self._lock:
            for conn in self.connections:
                if conn.session == session:
                    conn.in_use = False
                    break

    async def close(self):
        """Close all connections"""
        async with self._lock:
            for conn in self.connections:
                await conn.session.__aexit__(None, None, None)
            self.connections.clear()

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, *args):
        await self.close()

# Usage
async def main():
    server_params = StdioServerParameters(command="python", args=["server.py"])

    async with MCPConnectionPool(server_params, pool_size=5) as pool:
        # Multiple concurrent tool calls using pooled connections
        tasks = []
        for i in range(10):
            session = await pool.acquire()
            try:
                task = asyncio.create_task(
                    session.call_tool(f"tool_{i % 3}", {})
                )
                tasks.append(task)
            finally:
                await pool.release(session)

        await asyncio.gather(*tasks)
```

### 8.2 Multi-Server Pool

For managing connections to multiple MCP servers:

```python
class MultiServerMCPPool:
    def __init__(self, server_configs: dict[str, dict]):
        """
        server_configs: {
            "server1": {"command": "python", "args": ["server.py"]},
            "server2": {"command": "node", "args": ["server.js"]}
        }
        """
        self.pools = {
            name: MCPConnectionPool(
                StdioServerParameters(**config),
                pool_size=3
            )
            for name, config in server_configs.items()
        }

    async def initialize(self):
        for pool in self.pools.values():
            await pool.initialize()

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict
    ):
        """Call tool on specific server"""
        if server_name not in self.pools:
            raise ValueError(f"Unknown server: {server_name}")

        pool = self.pools[server_name]
        session = await pool.acquire()
        try:
            return await session.call_tool(tool_name, arguments)
        finally:
            await pool.release(session)

    async def close(self):
        for pool in self.pools.values():
            await pool.close()
```

---

## 9. Best Practices Summary

### Design Principles

1. **Use Context Managers:** Always use `async with` for session/client lifecycle
   ```python
   async with stdio_client(...) as (read, write):
       async with ClientSession(read, write) as session:
           # Session auto-closes on exit
   ```

2. **Stateless vs Stateful:**
   - **Stateless:** New connection per call (simpler, higher resource cost)
   - **Stateful:** Persistent connection (efficient, context preserved)
   - Choose based on call frequency and context needs

3. **Initialize First:** `await session.initialize()` must be first operation
   ```python
   async with ClientSession(read, write) as session:
       await session.initialize()  # Required before any other ops
       tools = await session.list_tools()
   ```

4. **Schema Validation:** Validate tool arguments before calling
   - Check required parameters
   - Convert MCP schema to OpenAI format if needed
   - Handle missing `properties` field for OpenAI compatibility

5. **Error Handling Layers:**
   - Transport: retry with backoff, circuit breaker
   - Protocol: fail fast, fix client code
   - Application: let LLM see and reason about errors

6. **Timeout Strategy:**
   - Set per-request timeouts (30s default)
   - Enforce absolute maximum (300s)
   - Reset on progress notifications if supported
   - Always handle asyncio.TimeoutError

7. **Resource Cleanup:**
   - Use context managers (automatic cleanup)
   - For manual management, call `__aexit__` explicitly
   - Close connections in finally blocks or error handlers

8. **Production Checklist:**
   - [ ] Timeouts configured for all operations
   - [ ] Error handling for transport/protocol/application layers
   - [ ] Connection pooling for high-throughput scenarios
   - [ ] Logging for debugging (JSON-RPC messages, errors, timing)
   - [ ] Health checks or periodic connection verification
   - [ ] Graceful degradation if server unavailable
   - [ ] Tests covering error scenarios

### OpenAI Integration Pattern

```python
# Convert MCP tools to OpenAI format
async def get_tools_for_openai(session):
    mcp_tools = await session.list_tools()
    openai_tools = []

    for tool in mcp_tools.tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema or {
                    "type": "object",
                    "properties": {}
                }
            }
        }
        openai_tools.append(openai_tool)

    return openai_tools

# Use with OpenAI SDK
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    tools=await get_tools_for_openai(session)
)
```

---

## 10. Recommended Architecture for Python CLI

### Layered Design

```
┌─────────────────────────────────────┐
│  CLI Application (argparse/click)   │
├─────────────────────────────────────┤
│  Tool Invocation Layer              │
│  (error handling, timeouts)         │
├─────────────────────────────────────┤
│  MCP Client Manager                 │
│  (connection pooling, schema conv.) │
├─────────────────────────────────────┤
│  Transport Layer                    │
│  (stdio, HTTP, SSE)                 │
├─────────────────────────────────────┤
│  MCP Python SDK                     │
├─────────────────────────────────────┤
│  MCP Server (external process)      │
└─────────────────────────────────────┘
```

### Implementation Template

```python
class DDCodeCLIWithMCP:
    def __init__(self, mcp_servers: dict[str, dict]):
        self.pool = MultiServerMCPPool(mcp_servers)

    async def initialize(self):
        await self.pool.initialize()

    async def execute_tool(
        self,
        server: str,
        tool: str,
        args: dict,
        timeout: float = 30.0
    ) -> ToolCallResult:
        """Execute tool with full error handling"""
        try:
            result = await asyncio.wait_for(
                self.pool.call_tool(server, tool, args),
                timeout=timeout
            )
            return ToolCallResult(success=True, data=result)
        except asyncio.TimeoutError:
            return ToolCallResult(success=False, error="Timeout",
                                error_type="transport")
        except Exception as e:
            return ToolCallResult(success=False, error=str(e),
                                error_type="unknown")

    async def close(self):
        await self.pool.close()
```

---

## 11. FastMCP 2.0 Alternative

**When to Consider FastMCP:**
- Need higher-level abstractions (server composition, OpenAPI generation)
- Enterprise auth (OAuth providers, WorkOS, Auth0, Azure)
- Built-in testing utilities
- Production deployment tools

**When to Stick with Official SDK:**
- Minimal dependencies preferred
- Full control over lifecycle
- Custom transport implementation
- Learning MCP protocol details

**FastMCP Client Example:**

```python
from fastmcp import Client

async def main():
    # FastMCP auto-detects transport type
    async with Client("path/to/server.py") as client:
        result = await client.call_tool("tool_name", {"param": "value"})
        print(result)
```

---

## 12. Unresolved Questions & Open Items

1. **Connection Idle Timeout:** MCP spec allows resetting timeout on progress notifications - how to detect progress notifications in official Python SDK? (Not clearly documented)

2. **Subprocess Resource Limits:** How to handle memory/CPU limits on spawned MCP server processes? (Requires subprocess resource limiting, not MCP-specific)

3. **Distributed/Remote Stdio:** Can stdio transport work over SSH/remote execution? (Technically possible but not standard pattern, HTTP Stream recommended instead)

4. **Tool Result Streaming:** How to handle large tool results that benefit from streaming? (SDK supports but documentation sparse)

5. **Authentication Patterns:** Official SDK doesn't document secure token passing for HTTP transports - recommended patterns unclear

6. **Version Compatibility:** How to handle breaking changes between protocol versions 2024-11-05 → 2025-03-26? (Fallback strategy not specified)

---

## References

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Client Development Guide](https://modelcontextprotocol.io/docs/develop/build-client)
- [MCP Specification 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle)
- [FastMCP 2.0](https://github.com/jlowin/fastmcp)
- [OpenAI Agents SDK - MCP Integration](https://openai.github.io/openai-agents-python/mcp/)
- [Real Python - Building MCP Clients](https://realpython.com/python-mcp-client/)

---

**Last Updated:** December 25, 2025
**Status:** Research Complete - Ready for Implementation Planning
