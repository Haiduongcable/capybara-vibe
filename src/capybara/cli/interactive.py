"""Interactive chat with prompt_toolkit."""

import random
import uuid
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.panel import Panel

from capybara.core.agent import Agent, AgentConfig
from capybara.core.config import CapybaraConfig
from capybara.core.utils.context import build_project_context
from capybara.core.utils.interrupts import AgentInterruptException
from capybara.core.logging import get_logger
from capybara.core.utils.prompts import build_system_prompt
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory, MemoryConfig
from capybara.tools.base import ToolPermission, ToolSecurityConfig
from capybara.tools.builtin import registry as default_tools
from capybara.tools.mcp.bridge import MCPBridge
from capybara.tools.registry import ToolRegistry
from capybara.ui.todo_panel import PersistentTodoPanel

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
    mode: str = "standard",
    initial_message: str | None = None,
) -> None:
    """Interactive chat loop with async input and streaming output.

    Args:
        model: Model to use for completions
        stream: Whether to stream responses
        config: Optional configuration object
        mode: Operation mode (standard/safe/plan/auto)
    """
    from capybara.core.config import load_config

    config = config or load_config()
    console = Console()

    # Apply Mode Logic
    if mode != "standard":
        console.print(f"[bold yellow]Activating mode: {mode.upper()}[/bold yellow]")

        if mode == "safe":
            # Force ASK for everything
            for tool_name in ["bash", "write_file", "edit_file", "delete_file"]:
                config.tools.security[tool_name] = ToolSecurityConfig(permission=ToolPermission.ASK)

        elif mode == "auto":
            # Force ALWAYS for everything (CAUTION)
             for tool_name in ["bash", "write_file", "edit_file", "delete_file"]:
                config.tools.security[tool_name] = ToolSecurityConfig(permission=ToolPermission.ALWAYS)

        elif mode == "plan":
            # Disable dangerous tools
            for tool_name in ["bash", "write_file", "edit_file", "delete_file"]:
                config.tools.security[tool_name] = ToolSecurityConfig(permission=ToolPermission.NEVER)
            # Ensure safe tools are enabled
            config.tools.security["todo"] = ToolSecurityConfig(permission=ToolPermission.ALWAYS)

    # Setup agent with provider router
    from capybara.providers.router import ProviderRouter
    from capybara.core.delegation.session_manager import SessionManager

    # Generate session ID for logging
    session_id = str(uuid.uuid4())

    agent_config = AgentConfig(model=model, stream=stream)
    memory_config = MemoryConfig(max_tokens=config.memory.max_tokens)
    memory = ConversationMemory(config=memory_config)

    # Set system prompt
    project_context = await build_project_context()
    memory.set_system_prompt(build_system_prompt(project_context=project_context))

    # Initialize storage and session manager BEFORE agent creation
    storage = ConversationStorage()
    await storage.initialize()
    session_manager = SessionManager(storage)

    # Setup tools registry WITHOUT delegation first
    tools = ToolRegistry()
    from capybara.tools.builtin import register_builtin_tools

    # Register basic tools (no delegation yet, parent_agent=None)
    register_builtin_tools(
        tools,
        parent_session_id=None,  # Don't register solve_task yet
        parent_agent=None,
        session_manager=None,
        storage=None
    )

    provider = ProviderRouter(
        providers=config.providers,
        default_model=model,
        session_id=session_id,  # Enable API request logging
    )
    agent = Agent(
        config=agent_config,
        memory=memory,
        tools=tools,  # Pass full registry with basic tools
        console=console,
        provider=provider,
        tools_config=config.tools,
        session_id=session_id,  # Enable session-based logging
    )

    # NOW register sub-agent tool with actual agent reference
    from capybara.tools.builtin.delegation import register_sub_agent_tool
    register_sub_agent_tool(
        tools,
        parent_session_id=session_id,
        parent_agent=agent,
        session_manager=session_manager,
        storage=storage
    )

    # Filter tools by mode AFTER all tools registered
    agent.tools = tools.filter_by_mode(agent_config.mode)
    agent.tool_executor.tools = agent.tools  # Update executor reference

    # Post-Registry Mode Logic (Hiding Tools)
    if mode == "plan":
        # Completely hide tools so the agent doesn't even know they exist
        for tool_name in ["bash", "write_file", "edit_file", "delete_file"]:
            agent.tools.unregister(tool_name)

    # Setup MCP integration if enabled
    mcp_bridge = None
    if config.mcp.enabled:
        try:
            mcp_bridge = MCPBridge(config.mcp)
            connected = await mcp_bridge.connect_all()
            if connected > 0:
                mcp_count = mcp_bridge.register_with_registry(agent.tools)
                console.print(f"[dim]Connected to {connected} MCP servers ({mcp_count} tools)[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: MCP setup failed: {e}[/yellow]")

    # Initialize persistent todo panel
    todo_panel = PersistentTodoPanel(visible=True)

    def render_todo_panel():
        """Render todo panel if it has content."""
        if panel_content := todo_panel.render():
            console.print(panel_content)

    # Subscribe to todo state changes and render immediately
    def on_todos_changed(todos):
        """Callback when todos are updated - render panel immediately."""
        # Render panel immediately when todos change (even during agent execution)
        # This ensures users see the todo list as soon as it's created
        if todos:  # Only render if there are todos
            console.print()  # Add newline for spacing
            render_todo_panel()
            console.print()  # Add newline after panel

    from capybara.tools.builtin.todo_state import todo_state
    todo_state.subscribe(on_todos_changed)

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

    @bindings.add("c-t")
    def toggle_todos(event) -> None:  # type: ignore[no-untyped-def]
        """Toggle todo panel visibility (Ctrl+T)."""
        todo_panel.toggle_visibility()
        logger.info(f"Todo panel visibility toggled: {todo_panel.visible}")
        # Note: Panel will re-render on next agent response

    # Welcome message
    console.print(
        Panel.fit(
            f"[bold green]CapybaraVibeCoding[/bold green]\n"
            f"Model: {model}\n"
            "Type 'exit' to quit, '/clear' to reset, Ctrl+T to toggle todos",
            title="Welcome",
        )
    )

    logger.info(f"Interactive chat session started with model: {model}")

    # Main loop
    first_run = True
    try:
        while True:
            try:
                if first_run and initial_message:
                    # Automatically execute the initial message provided via CLI args
                    console.print(f">>> {initial_message}")
                    user_input = initial_message
                    first_run = False
                else:
                    with patch_stdout():
                        user_input = await session.prompt_async(">>> ", key_bindings=bindings)
                        first_run = False

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

                # Render todo panel if it has todos
                render_todo_panel()

            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
                # Still show todo panel even if interrupted
                render_todo_panel()
                continue
            except EOFError:
                break
            except AgentInterruptException:
                console.print("\n[yellow]Agent interrupted by user[/yellow]")
                # Show todo panel after agent interruption
                render_todo_panel()
                continue
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
    finally:
        # Clean up todo panel and state subscriptions
        todo_state.unsubscribe(on_todos_changed)
        todo_panel.cleanup()
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
        memory.add_batch(initial_messages)

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
