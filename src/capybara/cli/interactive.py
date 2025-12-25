"""Interactive chat with prompt_toolkit."""

import random
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.panel import Panel

from capybara.core.agent import Agent, AgentConfig
from capybara.core.config import CapybaraConfig
from capybara.core.logging import get_logger
from capybara.core.prompts import build_system_prompt
from capybara.core.context import build_project_context
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory, MemoryConfig
from capybara.tools.builtin import registry as default_tools
from capybara.tools.mcp.bridge import MCPBridge
from capybara.tools.registry import ToolRegistry

console = Console()
logger = get_logger(__name__)

# Random agent names for thinking message
AGENT_NAMES = [
    "Nova", "Atlas", "Luna", "Orion", "Phoenix", "Sage",
    "Echo", "Zara", "Nexus", "Cipher", "Aurora", "Titan",
    "Vega", "Iris", "Quantum", "Stella", "Neo", "Lyra"
]


async def interactive_chat(
    model: str,
    stream: bool = True,
    config: CapybaraConfig | None = None,
) -> None:
    """Interactive chat loop with async input and streaming output.

    Args:
        model: Model to use for completions
        stream: Whether to stream responses
        config: Optional configuration object
    """
    from capybara.core.config import load_config

    config = config or load_config()

    # Setup tools registry with builtin tools
    tools = ToolRegistry()
    tools.merge(default_tools)

    # Setup MCP integration if enabled
    mcp_bridge = None
    if config.mcp.enabled:
        try:
            mcp_bridge = MCPBridge(config.mcp)
            connected = await mcp_bridge.connect_all()
            if connected > 0:
                mcp_count = mcp_bridge.register_with_registry(tools)
                console.print(f"[dim]Connected to {connected} MCP servers ({mcp_count} tools)[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: MCP setup failed: {e}[/yellow]")

    # Setup agent with provider router
    from capybara.providers.router import ProviderRouter

    agent_config = AgentConfig(model=model, stream=stream)
    memory_config = MemoryConfig(max_tokens=config.memory.max_tokens)
    memory = ConversationMemory(config=memory_config)

    # Set system prompt
    project_context = await build_project_context()
    memory.set_system_prompt(build_system_prompt(project_context=project_context))

    provider = ProviderRouter(providers=config.providers, default_model=model)
    agent = Agent(
        config=agent_config,
        memory=memory,
        tools=tools,
        console=console,
        provider=provider,
        tools_config=config.tools,
    )

    # Setup prompt_toolkit
    history_file = Path.home() / ".capybara" / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_file)),
        multiline=False,
    )

    # Keybindings
    bindings = KeyBindings()

    @bindings.add("c-c")
    def interrupt(event) -> None:  # type: ignore[no-untyped-def]
        """Handle Ctrl+C gracefully."""
        raise KeyboardInterrupt()

    # Welcome message
    console.print(
        Panel.fit(
            f"[bold green]CapybaraVibeCoding[/bold green]\n"
            f"Model: {model}\n"
            "Type 'exit' to quit, '/clear' to reset",
            title="Welcome",
        )
    )

    logger.info(f"Interactive chat session started with model: {model}")

    # Main loop
    try:
        while True:
            try:
                with patch_stdout():
                    user_input = await session.prompt_async(">>> ", key_bindings=bindings)

                if not user_input.strip():
                    continue
                if user_input.lower() in ("exit", "quit"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                if user_input == "/clear":
                    memory.clear()
                    console.print("[dim]Conversation cleared[/dim]")
                    continue
                if user_input == "/tokens":
                    console.print(f"[dim]Token count: {memory.get_token_count():,}[/dim]")
                    continue

                # Show thinking message via spinner in stream_completion
                # agent_name = random.choice(AGENT_NAMES)
                # console.print(f"[dim italic]{agent_name} thinking...[/dim italic]")

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
    finally:
        # Clean up MCP connections
        if mcp_bridge:
            await mcp_bridge.disconnect_all()


async def interactive_chat_with_session(
    session_id: str,
    model: str,
    stream: bool = True,
    config: CapybaraConfig | None = None,
    initial_messages: list[dict] | None = None,
    storage: ConversationStorage | None = None,
) -> None:
    """Interactive chat with session persistence.

    Args:
        session_id: Session ID to save messages to
        model: Model to use for completions
        stream: Whether to stream responses
        config: Optional configuration object
        initial_messages: Optional initial messages to load
        storage: Optional storage instance (will create if not provided)
    """
    from capybara.core.config import load_config

    config = config or load_config()

    # Initialize storage if not provided
    if storage is None:
        storage = ConversationStorage()
        await storage.initialize()
    elif not storage._initialized:
        await storage.initialize()

    # Setup tools registry with builtin tools
    tools = ToolRegistry()
    tools.merge(default_tools)

    # Setup MCP integration if enabled
    mcp_bridge = None
    if config.mcp.enabled:
        try:
            mcp_bridge = MCPBridge(config.mcp)
            connected = await mcp_bridge.connect_all()
            if connected > 0:
                mcp_count = mcp_bridge.register_with_registry(tools)
                console.print(f"[dim]Connected to {connected} MCP servers ({mcp_count} tools)[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: MCP setup failed: {e}[/yellow]")

    # Setup agent with loaded messages and provider router
    from capybara.providers.router import ProviderRouter

    agent_config = AgentConfig(model=model, stream=stream)
    memory_config = MemoryConfig(max_tokens=config.memory.max_tokens)
    memory = ConversationMemory(config=memory_config)

    # Set system prompt
    project_context = await build_project_context()
    memory.set_system_prompt(build_system_prompt(project_context=project_context))

    # Load initial messages if provided
    if initial_messages:
        for msg in initial_messages:
            memory.add(msg)

    provider = ProviderRouter(providers=config.providers, default_model=model)
    agent = Agent(
        config=agent_config,
        memory=memory,
        tools=tools,
        console=console,
        provider=provider,
        tools_config=config.tools,
    )

    # Setup prompt_toolkit
    history_file = Path.home() / ".capybara" / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_file)),
        multiline=False,
    )

    # Keybindings
    bindings = KeyBindings()

    @bindings.add("c-c")
    def interrupt(event) -> None:  # type: ignore[no-untyped-def]
        """Handle Ctrl+C gracefully."""
        raise KeyboardInterrupt()

    # Welcome message
    console.print(
        Panel.fit(
            f"[bold green]CapybaraVibeCoding[/bold green] (Session: {session_id})\n"
            f"Model: {model}\n"
            "Type 'exit' to quit, '/clear' to reset",
            title="Welcome",
        )
    )

    # Main loop with persistence
    try:
        while True:
            try:
                with patch_stdout():
                    user_input = await session.prompt_async(">>> ", key_bindings=bindings)

                if not user_input.strip():
                    continue
                if user_input.lower() in ("exit", "quit"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                if user_input == "/clear":
                    memory.clear()
                    console.print("[dim]Conversation cleared[/dim]")
                    continue
                if user_input == "/tokens":
                    console.print(f"[dim]Token count: {memory.get_token_count():,}[/dim]")
                    continue

                # Save user message
                await storage.save_message(session_id, {"role": "user", "content": user_input})

                # Show thinking message with random agent name
                agent_name = random.choice(AGENT_NAMES)
                console.print(f"[dim italic]{agent_name} thinking...[/dim italic]")

                # Run agent
                response = await agent.run(user_input)

                # Save assistant response
                await storage.save_message(session_id, {"role": "assistant", "content": response})

                console.print()  # Newline after response

            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
                continue
            except EOFError:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
    finally:
        # Clean up MCP connections
        if mcp_bridge:
            await mcp_bridge.disconnect_all()
