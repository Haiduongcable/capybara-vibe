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
from rich.align import Align
from rich.table import Table
from rich.text import Text
from rich import box
import os
from capybara import __version__

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from capybara.core.agent import Agent, AgentConfig
    from capybara.core.config import CapybaraConfig
    from capybara.memory.storage import ConversationStorage

from capybara.core.logging import get_logger
# CapybaraConfig is needed for type hints in function signatures at runtime?
# python 3.10+ handles string annotations but for safety I import it if it's light.
# settings.py is light-ish.
from capybara.core.config import CapybaraConfig
from capybara.memory.storage import ConversationStorage

# Remove heavy imports from top-level
# from capybara.core.agent import ... -> Moved to functions
# from capybara.core.utils.context -> Moved to functions
# from capybara.tools... -> Moved to functions

console = Console()
logger = get_logger(__name__)

# Random agent names for thinking message
AGENT_NAMES = [
    "Nova",
    "Atlas",
    "Luna",
    "Orion",
    "Phoenix",
    "Sage",
    "Echo",
    "Zara",
    "Nexus",
    "Cipher",
    "Aurora",
    "Titan",
    "Vega",
    "Iris",
    "Quantum",
    "Stella",
    "Neo",
    "Lyra",
]


def _get_display_info(config: CapybaraConfig, model: str) -> tuple[str, str]:
    """Get display info for provider and model."""
    if not config or not config.providers:
        return "Unknown", model

    for provider in config.providers:
        # Check against the configured model name (short name)
        if provider.model == model:
            return provider.name, provider.model
            
    # Fallback to defaults or raw model string
    return "Default", model



CAPYBARA_ASCII_ART = r"""
   ______                   __
  / ____/____ _____  __  __/ /_  ____ __________ _
 / /    / __ `/ __ \/ / / / __ \/ __ `/ ___/ __ `/
/ /___ / /_/ / /_/ / /_/ / /_/ / /_/ / /  / /_/ / 
\____/ \__,_/ .___/\__, /_.___/\__,_/_/   \__,_/  
           /_/    /____/                          
"""

def _print_welcome_panel(config: CapybaraConfig, model: str, session_id: str | None = None) -> None:
    """Print the welcome panel with professional layout."""
    provider_name, display_model = _get_display_info(config, model)
    user_name = os.environ.get("USER", os.environ.get("USERNAME", "User"))
    cwd = os.getcwd()
    
    # Create the main grid for the panel content (2 columns)
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(ratio=2)  # Main content
    grid.add_column(ratio=1)  # specific tips/info
    
    # Left Column Content
    left_content = Table.grid(padding=(0, 1))
    left_content.add_row(Text(f"Welcome back, {"HaiDuong"}!", style="bold blue"))
    left_content.add_row(Align.left(Text(CAPYBARA_ASCII_ART, style="bold green")))
    
    # Info section in left column
    info_table = Table.grid(padding=(0, 2))
    info_table.add_row("Provider:", Text(provider_name, style="cyan"))
    info_table.add_row("Model:", Text(display_model, style="cyan"))
    
    display_cwd = cwd
    if len(cwd) > 40:
        display_cwd = "..." + cwd[-37:]
    info_table.add_row("Path:", Text(display_cwd, style="dim"))
    
    if session_id:
        info_table.add_row("Session:", Text(session_id[:8], style="dim"))
        
    left_content.add_row(info_table)
    
    # Right Column Content (Tips)
    right_content = Table.grid(padding=(0, 1))
    right_content.add_row(Text("Tips for getting started", style="bold underline"))
    right_content.add_row("")
    right_content.add_row("• /clear to reset context")
    right_content.add_row("• Ctrl+T to toggle Todo Panel")
    right_content.add_row("• /tools to see tools")
    right_content.add_row("• 'exit' to quit")
    right_content.add_row("")
    
    if config and hasattr(config, "features"):
        mode_str = "Auto" if config.features.complexity_threshold else "Standard"
        right_content.add_row(Text("Mode:", style="dim"), Text(mode_str, style="dim"))

    # Add columns to main grid
    grid.add_row(left_content, right_content)
    
    # Create the panel
    panel = Panel(
        grid,
        title=f"[bold]Capybara Vibe v{__version__}[/bold]",
        subtitle="[dim]AI-Powered Coding Assistant[/dim]",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)


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
    
    # Show UI immediately to reduce perceived latency
    # Show UI immediately to reduce perceived latency
    _print_welcome_panel(config, model)

    with console.status("[dim]Loading engine...[/dim]", spinner="dots"):
        # Delayed imports for performance
        from capybara.core.agent import Agent, AgentConfig
        from capybara.core.utils.context import build_project_context
        from capybara.core.utils.interrupts import AgentInterruptException
        from capybara.core.utils.prompts import build_system_prompt
        from capybara.memory.window import ConversationMemory, MemoryConfig
        from capybara.tools.base import ToolPermission, ToolSecurityConfig
        from capybara.tools.builtin import registry as default_tools
        from capybara.tools.mcp.bridge import MCPBridge
        from capybara.tools.registry import ToolRegistry
        from capybara.ui.todo_panel import PersistentTodoPanel

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
                    config.tools.security[tool_name] = ToolSecurityConfig(
                        permission=ToolPermission.ALWAYS
                    )

            elif mode == "plan":
                # Disable dangerous tools
                for tool_name in ["bash", "write_file", "edit_file", "delete_file"]:
                    config.tools.security[tool_name] = ToolSecurityConfig(
                        permission=ToolPermission.NEVER
                    )
                # Ensure safe tools are enabled
                config.tools.security["todo"] = ToolSecurityConfig(permission=ToolPermission.ALWAYS)

        # Setup agent with provider router
        from capybara.core.delegation.session_manager import SessionManager
        from capybara.providers.router import ProviderRouter

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
            storage=None,
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
            storage=storage,
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
                    console.print(
                        f"[dim]Connected to {connected} MCP servers ({mcp_count} tools)[/dim]"
                    )
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
    def interrupt(event) -> None:
        """Handle Ctrl+C gracefully."""
        raise KeyboardInterrupt()

    @bindings.add("c-t")
    def toggle_todos(event) -> None:
        """Toggle todo panel visibility (Ctrl+T)."""
        todo_panel.toggle_visibility()
        logger.info(f"Todo panel visibility toggled: {todo_panel.visible}")
        # Note: Panel will re-render on next agent response

    # Welcome message already shown at start
    # _print_welcome_panel(config, model)

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

    # Show UI immediately
    # Show UI immediately
    _print_welcome_panel(config, model, session_id=session_id)
    
    with console.status("[dim]Loading session engine...[/dim]", spinner="dots"):
        from capybara.core.agent import Agent, AgentConfig
        from capybara.core.utils.context import build_project_context
        from capybara.core.utils.prompts import build_system_prompt
        from capybara.memory.window import ConversationMemory, MemoryConfig
        from capybara.tools.builtin import registry as default_tools
        from capybara.tools.mcp.bridge import MCPBridge
        from capybara.tools.registry import ToolRegistry

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
                    console.print(
                        f"[dim]Connected to {connected} MCP servers ({mcp_count} tools)[/dim]"
                    )
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
    def interrupt(event) -> None:
        """Handle Ctrl+C gracefully."""
        raise KeyboardInterrupt()

    # Welcome message already shown at start
    # _print_welcome_panel(config, model, session_id=session_id)

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
