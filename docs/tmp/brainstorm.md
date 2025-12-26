# CapybaraVibeCoding 🦫 - Technical Brainstorm

> AI-powered coding assistant CLI with multi-provider support
>
> **Status**: Brainstorm Complete | **Date**: 2024-12-25

---

## Executive Summary

**CapybaraVibeCoding** is an open-source CLI coding assistant inspired by Claude Code, designed to work with multiple LLM providers through LiteLLM. Built in Python with async architecture for optimal streaming and concurrent tool execution.

### Core Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.10+ | Ecosystem, accessibility, open source friendly |
| Provider Layer | LiteLLM | 100+ models, unified API, maintained |
| Tool Schema | OpenAI format | Industry standard, wide adoption |
| Memory | Sliding window (configurable) | Balance cost vs context |
| Concurrency | Async (asyncio) | Native streaming, clean concurrent tools |
| CLI Framework | Click + Rich | Modern, good DX |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Interface                          │
│                    (Click + Rich + prompt_toolkit)          │
├─────────────────────────────────────────────────────────────┤
│                       Agent Core                            │
│              (async conversation loop, tool dispatch)       │
├─────────────────────────────────────────────────────────────┤
│                     Tool Registry                           │
│    ┌───────────────┬───────────────┬───────────────┐       │
│    │   Built-in    │     MCP       │    Custom     │       │
│    │    Tools      │    Bridge     │    Tools      │       │
│    └───────────────┴───────────────┴───────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                    Memory Manager                           │
│           (sliding window + sqlite persistence)             │
├─────────────────────────────────────────────────────────────┤
│                   Provider Layer                            │
│                      (LiteLLM)                              │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│  OpenAI  │  Gemini  │  Claude  │  Ollama  │  Other 100+     │
└──────────┴──────────┴──────────┴──────────┴─────────────────┘
```

---

## Project Structure

```
capybara-vibe-coding/
├── src/
│   └── capybara/
│       ├── __init__.py
│       ├── __main__.py           # python -m capybara
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py           # click entrypoint
│       │   ├── commands/
│       │   │   ├── chat.py       # interactive chat
│       │   │   ├── run.py        # single prompt
│       │   │   └── config.py     # config management
│       │   └── ui.py             # rich output helpers
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── agent.py          # main async agent loop
│       │   ├── conversation.py   # message handling
│       │   └── config.py         # pydantic settings
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py           # abstract provider protocol
│       │   ├── litellm_provider.py
│       │   └── schema.py         # OpenAI tool schema types
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py       # tool registration system
│       │   ├── executor.py       # async tool execution
│       │   ├── builtin/
│       │   │   ├── __init__.py
│       │   │   ├── filesystem.py # read, write, glob, grep
│       │   │   ├── bash.py       # shell execution
│       │   │   └── search.py     # code search
│       │   └── mcp/
│       │       ├── __init__.py
│       │       ├── client.py     # MCP client wrapper
│       │       └── bridge.py     # MCP to OpenAI schema
│       │
│       └── memory/
│           ├── __init__.py
│           ├── window.py         # sliding window logic
│           ├── tokenizer.py      # token counting
│           └── storage.py        # sqlite persistence
│
├── tests/
│   ├── conftest.py
│   ├── test_agent.py
│   ├── test_tools.py
│   └── test_memory.py
│
├── pyproject.toml
├── README.md
├── LICENSE                       # MIT recommended
├── CONTRIBUTING.md
└── .github/
    └── workflows/
        └── ci.yml
```

---

## Core Components Design

### 1. Tool Registry (OpenAI Schema)

```python
# src/capybara/tools/registry.py
from typing import Callable, Any
from pydantic import BaseModel
import asyncio

class ToolSchema(BaseModel):
    """OpenAI function calling format"""
    type: str = "function"
    function: dict

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._schemas: list[dict] = []

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict
    ):
        """Decorator to register async tools"""
        def decorator(func: Callable):
            # Ensure async
            if not asyncio.iscoroutinefunction(func):
                raise ValueError(f"Tool {name} must be async")

            self._tools[name] = func
            self._schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            })
            return func
        return decorator

    async def execute(self, name: str, arguments: dict) -> str:
        if name not in self._tools:
            return f"Error: Unknown tool '{name}'"
        try:
            result = await self._tools[name](**arguments)
            return str(result)
        except Exception as e:
            return f"Error: {e}"

    @property
    def schemas(self) -> list[dict]:
        return self._schemas

# Built-in tools
registry = ToolRegistry()

@registry.tool(
    name="read_file",
    description="Read the contents of a file at the specified path",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative file path"
            }
        },
        "required": ["path"]
    }
)
async def read_file(path: str) -> str:
    import aiofiles
    async with aiofiles.open(path, 'r') as f:
        return await f.read()

@registry.tool(
    name="write_file",
    description="Write content to a file, creating it if it doesn't exist",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"}
        },
        "required": ["path", "content"]
    }
)
async def write_file(path: str, content: str) -> str:
    import aiofiles
    async with aiofiles.open(path, 'w') as f:
        await f.write(content)
    return f"Successfully wrote to {path}"

@registry.tool(
    name="bash",
    description="Execute a bash command and return output",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"}
        },
        "required": ["command"]
    }
)
async def bash(command: str) -> str:
    import asyncio
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode() + stderr.decode()
    return output or "(no output)"
```

### 2. Memory: Sliding Window

```python
# src/capybara/memory/window.py
from dataclasses import dataclass, field
from typing import Optional
import tiktoken

@dataclass
class MemoryConfig:
    max_messages: Optional[int] = None    # None = unlimited
    max_tokens: Optional[int] = 100_000   # token-based limit
    preserve_system: bool = True          # always keep system prompt
    model: str = "gpt-4"                  # for token counting

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
        self.messages.append(message)
        self._trim()

    def _count_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if content:
                total += len(self._encoder.encode(content))
        return total

    def _trim(self) -> None:
        if not self.messages:
            return

        # Separate system messages
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        other_msgs = [m for m in self.messages if m["role"] != "system"]

        # Trim by message count
        if self.config.max_messages and len(other_msgs) > self.config.max_messages:
            other_msgs = other_msgs[-self.config.max_messages:]

        # Trim by token count
        if self.config.max_tokens:
            while (
                other_msgs and
                self._count_tokens(system_msgs + other_msgs) > self.config.max_tokens
            ):
                other_msgs.pop(0)

        self.messages = system_msgs + other_msgs if self.config.preserve_system else other_msgs

    def get_messages(self) -> list[dict]:
        return self.messages.copy()

    def clear(self) -> None:
        system_msgs = [m for m in self.messages if m["role"] == "system"]
        self.messages = system_msgs if self.config.preserve_system else []
```

### 3. Async Agent Core

```python
# src/capybara/core/agent.py
import asyncio
import json
from typing import AsyncIterator
import litellm
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from capybara.tools.registry import ToolRegistry
from capybara.memory.window import ConversationMemory

class Agent:
    def __init__(
        self,
        model: str,
        memory: ConversationMemory,
        tools: ToolRegistry,
        console: Console
    ):
        self.model = model
        self.memory = memory
        self.tools = tools
        self.console = console

    async def run(self, user_input: str) -> str:
        """Main agent loop with tool use"""
        self.memory.add({"role": "user", "content": user_input})

        while True:
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

    async def _get_completion(self) -> dict:
        """Stream completion from LLM"""
        collected_content = []
        collected_tool_calls = {}

        response = await litellm.acompletion(
            model=self.model,
            messages=self.memory.get_messages(),
            tools=self.tools.schemas if self.tools.schemas else None,
            stream=True
        )

        with Live(console=self.console, refresh_per_second=10) as live:
            async for chunk in response:
                delta = chunk.choices[0].delta

                # Collect content
                if delta.content:
                    collected_content.append(delta.content)
                    live.update(Markdown("".join(collected_content)))

                # Collect tool calls
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
        """Execute multiple tools concurrently"""
        async def execute_one(tc: dict) -> dict:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])

            self.console.print(f"[dim]Executing: {name}({args})[/dim]")
            result = await self.tools.execute(name, args)

            return {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result
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

### 4. Configuration

```python
# src/capybara/core/config.py
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

class ProviderConfig(BaseModel):
    default: str = "openai"
    model: str = "gpt-4o"
    api_base: Optional[str] = None

class MemoryConfig(BaseModel):
    sliding_window: Optional[int] = 50  # None = unlimited
    max_tokens: Optional[int] = 100_000
    persist: bool = True

class ToolsConfig(BaseModel):
    bash_enabled: bool = True
    bash_timeout: int = 30
    filesystem_enabled: bool = True
    allowed_paths: list[str] = ["."]

class MCPServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}

class MCPConfig(BaseModel):
    enabled: bool = False
    servers: list[MCPServerConfig] = []

class CapybaraConfig(BaseSettings):
    """Main configuration loaded from ~/.capybara/config.yaml"""
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)

    class Config:
        env_prefix = "CAPYBARA_"
        env_file = ".env"

def load_config() -> CapybaraConfig:
    config_path = Path.home() / ".capybara" / "config.yaml"
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f)
            return CapybaraConfig(**data)
    return CapybaraConfig()
```

### 5. CLI Interface

```python
# src/capybara/cli/main.py
import asyncio
import click
from rich.console import Console
from rich.panel import Panel
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from capybara.core.config import load_config
from capybara.core.agent import Agent
from capybara.memory.window import ConversationMemory, MemoryConfig
from capybara.tools.registry import registry as default_tools

console = Console()

@click.group()
@click.version_option(prog_name="capybara")
def cli():
    """🦫 CapybaraVibeCoding - Vibe-driven AI coding assistant"""
    pass

@cli.command()
@click.option("--model", "-m", help="Model to use (e.g., gpt-4o, claude-3-opus)")
@click.option("--provider", "-p", help="Provider (openai/anthropic/google)")
@click.option("--no-stream", is_flag=True, help="Disable streaming")
def chat(model: str, provider: str, no_stream: bool):
    """Start an interactive chat session"""
    asyncio.run(_chat_async(model, provider, no_stream))

async def _chat_async(model: str, provider: str, no_stream: bool):
    config = load_config()

    # Override with CLI args
    if model:
        config.provider.model = model

    # Setup memory
    mem_config = MemoryConfig(
        max_messages=config.memory.sliding_window,
        max_tokens=config.memory.max_tokens
    )
    memory = ConversationMemory(config=mem_config)

    # Setup agent
    agent = Agent(
        model=config.provider.model,
        memory=memory,
        tools=default_tools,
        console=console
    )

    # Welcome message
    console.print(Panel.fit(
        "[bold green]🦫 CapybaraVibeCoding[/bold green]\n"
        f"Model: {config.provider.model}\n"
        "Type 'exit' to quit, '/clear' to reset conversation",
        title="Welcome"
    ))

    # Setup prompt with history
    session = PromptSession(
        history=FileHistory(str(Path.home() / ".capybara" / "history"))
    )

    while True:
        try:
            user_input = await asyncio.to_thread(
                session.prompt,
                ">>> "
            )

            if not user_input.strip():
                continue
            if user_input.lower() in ("exit", "quit"):
                console.print("[dim]Goodbye! 🦫[/dim]")
                break
            if user_input == "/clear":
                memory.clear()
                console.print("[dim]Conversation cleared[/dim]")
                continue

            await agent.run(user_input)
            console.print()  # newline after response

        except KeyboardInterrupt:
            console.print("\n[dim]Use 'exit' to quit[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

@cli.command()
@click.argument("prompt")
@click.option("--model", "-m", help="Model to use")
def run(prompt: str, model: str):
    """Run a single prompt and exit"""
    asyncio.run(_run_async(prompt, model))

async def _run_async(prompt: str, model: str):
    config = load_config()
    if model:
        config.provider.model = model

    memory = ConversationMemory(config=MemoryConfig())
    agent = Agent(
        model=config.provider.model,
        memory=memory,
        tools=default_tools,
        console=console
    )

    await agent.run(prompt)

@cli.command()
def init():
    """Initialize configuration in ~/.capybara/"""
    config_dir = Path.home() / ".capybara"
    config_dir.mkdir(exist_ok=True)

    config_file = config_dir / "config.yaml"
    if config_file.exists():
        console.print("[yellow]Config already exists[/yellow]")
        return

    default_config = """# CapybaraVibeCoding Configuration
provider:
  default: openai
  model: gpt-4o

memory:
  sliding_window: 50  # null for unlimited context
  max_tokens: 100000
  persist: true

tools:
  bash_enabled: true
  bash_timeout: 30
  filesystem_enabled: true
  allowed_paths: ["."]

mcp:
  enabled: false
  servers: []
"""
    config_file.write_text(default_config)
    console.print(f"[green]Created config at {config_file}[/green]")

if __name__ == "__main__":
    cli()
```

---

## Dependencies

```toml
# pyproject.toml
[project]
name = "capybara-vibe-coding"
version = "0.1.0"
description = "AI-powered coding assistant CLI with multi-provider support"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
keywords = ["ai", "coding", "assistant", "cli", "llm"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "litellm>=1.40.0",
    "click>=8.1.0",
    "rich>=13.0.0",
    "prompt-toolkit>=3.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "pyyaml>=6.0.0",
    "tiktoken>=0.5.0",
    "aiofiles>=23.0.0",
    "aiosqlite>=0.19.0",
]

[project.optional-dependencies]
mcp = ["mcp>=0.1.0"]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
capybara = "capybara.cli.main:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]

[tool.mypy]
python_version = "3.10"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## Development Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Project scaffolding (pyproject.toml, structure)
- [ ] Config system with pydantic-settings
- [ ] Basic LiteLLM integration
- [ ] Streaming output with Rich
- [ ] CLI entrypoint (chat, run, init commands)

### Phase 2: Tools System (Week 3-4)
- [ ] Tool registry with decorators
- [ ] Built-in tools: read_file, write_file, bash, glob, grep
- [ ] Async tool execution with `asyncio.gather`
- [ ] Agent loop with tool calling
- [ ] Error handling and timeouts

### Phase 3: Memory & Persistence (Week 5)
- [ ] Sliding window implementation
- [ ] Token counting with tiktoken
- [ ] SQLite conversation storage
- [ ] Session management (list, continue, delete)

### Phase 4: MCP Integration (Week 6-8)
- [ ] MCP client using official SDK
- [ ] Server lifecycle management (spawn, kill)
- [ ] Tool discovery from MCP servers
- [ ] Bridge MCP tools to OpenAI schema
- [ ] Config-based MCP server definitions

### Phase 5: Polish (Week 9-10)
- [ ] Comprehensive error messages
- [ ] Keyboard shortcuts (Ctrl+C handling)
- [ ] Multi-line input support
- [ ] Syntax highlighting for code
- [ ] Progress indicators for long operations
- [ ] Documentation and examples

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LiteLLM tool calling inconsistency | High | Test matrix across providers, fallback modes |
| MCP complexity | High | Start with stdio transport only, defer advanced features |
| Streaming edge cases | Medium | Robust chunk collection, timeout handling |
| Token counting accuracy | Medium | Use tiktoken, accept some variance |
| Open source maintenance burden | Medium | Clear contribution guidelines, issue templates |

---

## Competitive Analysis

| Feature | Claude Code | Aider | Open Interpreter | Capybara (Target) |
|---------|-------------|-------|------------------|-------------------|
| Multi-provider | No | Yes | Yes | Yes |
| MCP support | Yes | No | No | Yes |
| Tool use | Advanced | Basic | Advanced | Advanced |
| Open source | No | Yes | Yes | Yes |
| Python | No | Yes | Yes | Yes |
| Streaming | Yes | Yes | Yes | Yes |

**Capybara differentiators**:
1. MCP support (unique among Python tools)
2. Clean async architecture
3. Configurable memory strategies
4. LiteLLM for maximum provider flexibility

---

## Success Metrics

### MVP (v0.1.0)
- [ ] Chat with 3+ providers working
- [ ] File read/write tools functional
- [ ] Bash execution with timeout
- [ ] Sliding window memory working
- [ ] 10+ GitHub stars

### v0.2.0
- [ ] MCP integration complete
- [ ] SQLite persistence
- [ ] 5+ built-in tools
- [ ] 50+ GitHub stars

### v1.0.0
- [ ] Production stable
- [ ] Comprehensive test coverage (>80%)
- [ ] Documentation site
- [ ] 500+ GitHub stars

---

## Next Steps

1. **Initialize repository** with project structure
2. **Setup development environment** (uv, pre-commit)
3. **Implement Phase 1** foundation
4. **Create GitHub repo** with README, LICENSE
5. **Start building community** early

---

## References

- [LiteLLM Documentation](https://docs.litellm.ai/)
- [MCP Specification](https://modelcontextprotocol.io/)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Rich Documentation](https://rich.readthedocs.io/)
- [Click Documentation](https://click.palletsprojects.com/)

---

*Document generated during brainstorming session - 2024-12-25*
*Ready for implementation phase* 🦫
