"""Click CLI entrypoint for CapybaraVibeCoding."""

import asyncio

# IMPORTANT: Import litellm config FIRST to suppress verbose output
from capybara.core.config.litellm_config import suppress_litellm_output
suppress_litellm_output()

import click
from rich.console import Console
from rich.panel import Panel

from capybara import __version__
from capybara.core.config import init_config, load_config, save_config
from capybara.core.logging import setup_logging

# Initialize logging on module load
logger = setup_logging(log_level="INFO", console_output=False)

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="capybara")
def cli() -> None:
    """CapybaraVibeCoding - AI-powered coding assistant."""
    pass


@cli.command()
@click.option("--model", "-m", default=None, help="Model to use (default from config)")
@click.option("--no-stream", is_flag=True, help="Disable streaming output")
@click.option(
    "--mode", 
    type=click.Choice(["standard", "safe", "plan", "auto"]), 
    default="standard",
    help="Operation mode (standard, safe, plan, auto)"
)
@click.argument("message", required=False)
def chat(message: str | None, model: str | None, no_stream: bool, mode: str) -> None:
    """Start interactive chat session.
    
    Optionally provide a MESSAGE to start the conversation immediately.
    """
    asyncio.run(_chat_async(model, not no_stream, mode, message))


@cli.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="Model to use")
@click.option("--no-stream", is_flag=True, help="Disable streaming")
@click.option(
    "--mode", 
    type=click.Choice(["standard", "safe", "plan", "auto"]), 
    default="standard",
    help="Operation mode (standard, safe, plan, auto)"
)
def run(prompt: str, model: str | None, no_stream: bool, mode: str) -> None:
    """Run a single prompt and exit."""
    asyncio.run(_run_async(prompt, model, not no_stream, mode))


@cli.command()
@click.option("--cli", "use_cli", is_flag=True, help="Use CLI prompts instead of web UI")
@click.option("--no-browser", is_flag=True, help="Don't auto-open browser (print URL instead)")
def init(use_cli: bool, no_browser: bool) -> None:
    """Initialize configuration via web UI.

    Opens a local web server with a configuration UI in your browser.
    Use --cli for terminal-only environments.
    """
    if use_cli:
        # Fallback to simple config creation
        config_path = init_config()
        console.print(f"[green]Configuration initialized at:[/green] {config_path}")
        console.print("[dim]Edit this file to configure providers, memory, and tools.[/dim]")
    else:
        # Web UI
        console.print("[bold]Starting configuration UI...[/bold]")
        try:
            from capybara.web.server import run_server

            asyncio.run(run_server(open_browser=not no_browser))
            console.print("[green]Configuration saved![/green]")
        except KeyboardInterrupt:
            console.print("[dim]Configuration cancelled.[/dim]")


@cli.command()
def config() -> None:
    """Show current configuration."""
    cfg = load_config()
    console.print(Panel.fit(
        f"[bold]Model:[/bold] {cfg.default_model}\n"
        f"[bold]Providers:[/bold] {len(cfg.providers)}\n"
        f"[bold]Memory max tokens:[/bold] {cfg.memory.max_tokens:,}\n"
        f"[bold]MCP enabled:[/bold] {cfg.mcp.enabled}",
        title="Current Configuration",
    ))


@cli.command()
@click.argument("name", required=False)
def model(name: str | None) -> None:
    """Get or set the default AI model."""
    cfg = load_config()

    if name:
        if not cfg.providers:
            console.print("[red]No providers configured.[/red]")
            return

        # Update the first provider (assumed default)
        cfg.providers[0].model = name
        save_config(cfg)
        console.print(f"[green]Default model updated to:[/green] {name}")
    else:
        # Interactive model selection
        if not cfg.providers:
            console.print("[red]No providers configured.[/red]")
            return

        # Show current model
        console.print(f"[bold]Current default model:[/bold] {cfg.default_model}\n")

        # Get available models from all providers (deduplicated, preserving order)
        seen = set()
        available_models = []
        for provider in cfg.providers:
            if provider.model not in seen:
                seen.add(provider.model)
                available_models.append(provider.model)

        if not available_models:
            console.print("[yellow]No models configured in providers.[/yellow]")
            return

        # Display available models
        console.print("[bold]Available models:[/bold]")
        for idx, model_name in enumerate(available_models, 1):
            current_marker = " [green](current)[/green]" if model_name == cfg.default_model else ""
            console.print(f"  {idx}. {model_name}{current_marker}")

        # Prompt for selection
        try:
            from prompt_toolkit import prompt as pt_prompt
            from prompt_toolkit.validation import Validator, ValidationError

            class NumberValidator(Validator):
                def validate(self, document):
                    text = document.text
                    if not text:
                        return
                    if not text.isdigit() or int(text) < 1 or int(text) > len(available_models):
                        raise ValidationError(
                            message=f"Please enter a number between 1 and {len(available_models)}"
                        )

            console.print()
            selection = pt_prompt(
                "Select model (enter number): ",
                validator=NumberValidator()
            )

            if selection:
                selected_idx = int(selection) - 1
                selected_model = available_models[selected_idx]

                # Update the first provider (assumed default)
                cfg.providers[0].model = selected_model
                save_config(cfg)
                console.print(f"\n[green]✓ Default model updated to:[/green] {selected_model}")
        except KeyboardInterrupt:
            console.print("\n[dim]Selection cancelled[/dim]")
        except Exception as e:
            console.print(f"\n[red]Error during selection: {e}[/red]")


@cli.command()
def sessions() -> None:
    """List recent conversation sessions."""
    asyncio.run(_list_sessions())


@cli.command()
@click.argument("session_id")
@click.option("--model", "-m", default=None, help="Model to use")
def resume(session_id: str, model: str | None) -> None:
    """Resume a previous conversation session."""
    asyncio.run(_resume_async(session_id, model))


async def _chat_async(model: str | None, stream: bool, mode: str = "standard", initial_message: str | None = None) -> None:
    """Async chat implementation."""
    from capybara.cli.interactive import interactive_chat

    cfg = load_config()
    model = model or cfg.default_model

    await interactive_chat(model=model, stream=stream, config=cfg, mode=mode, initial_message=initial_message)


async def _run_async(prompt: str, model: str | None, stream: bool, mode: str = "standard") -> None:
    """Async single-run implementation."""
    import uuid
    from capybara.core.agent import Agent, AgentConfig
    from capybara.core.utils.prompts import build_system_prompt
    from capybara.core.utils.context import build_project_context
    from capybara.memory.window import ConversationMemory, MemoryConfig
    from capybara.tools.builtin import registry as default_tools
    from capybara.tools.mcp.bridge import MCPBridge
    from capybara.tools.registry import ToolRegistry

    cfg = load_config()
    model = model or cfg.default_model

    # Setup tools registry
    tools = ToolRegistry()
    tools.merge(default_tools)

    # Apply Mode Logic (Duplicate of interactive.py logic - should refactor, but kept inline for now)
    from capybara.core.config import ToolSecurityConfig, ToolPermission

    if mode == "plan":
        # Remove dangerous tools from registry to hide them
        for tool_name in ["bash", "write_file", "edit_file", "delete_file"]:
            tools.unregister(tool_name)
    elif mode == "safe":
        # Force ASK permission
        for tool_name in ["bash", "write_file", "edit_file", "delete_file"]:
             cfg.tools.security[tool_name] = ToolSecurityConfig(permission=ToolPermission.ASK)

    # Setup MCP integration if enabled
    mcp_bridge = None
    if cfg.mcp.enabled:
        try:
            mcp_bridge = MCPBridge(cfg.mcp)
            connected = await mcp_bridge.connect_all()
            if connected > 0:
                mcp_bridge.register_with_registry(tools)
        except Exception:
            pass  # Silent failure for one-off commands

    try:
        from capybara.providers.router import ProviderRouter

        # Generate session ID for logging
        session_id = str(uuid.uuid4())

        agent_config = AgentConfig(model=model, stream=stream)
        memory = ConversationMemory(config=MemoryConfig(max_tokens=cfg.memory.max_tokens))

        # Set system prompt
        project_context = await build_project_context()
        memory.set_system_prompt(build_system_prompt(project_context=project_context))

        provider = ProviderRouter(providers=cfg.providers, default_model=model)
        agent = Agent(
            config=agent_config,
            memory=memory,
            tools=tools,
            console=console,
            provider=provider,
            tools_config=cfg.tools,
            session_id=session_id,  # Enable session-based logging
        )

        await agent.run(prompt)
    finally:
        # Clean up MCP connections
        if mcp_bridge:
            await mcp_bridge.disconnect_all()


async def _list_sessions() -> None:
    """List recent conversation sessions."""
    from capybara.memory.storage import ConversationStorage
    from rich.table import Table

    storage = ConversationStorage()
    await storage.initialize()

    sessions = await storage.list_sessions(limit=20)

    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return

    table = Table(title="Recent Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Model", style="yellow")
    table.add_column("Updated", style="dim")

    for session in sessions:
        table.add_row(
            session["id"],
            session["title"],
            session["model"],
            session["updated_at"][:16],  # Trim to minute precision
        )

    console.print(table)
    console.print(f"\n[dim]Use 'capybara resume <session_id>' to continue a session[/dim]")


async def _resume_async(session_id: str, model: str | None) -> None:
    """Resume a previous conversation session."""
    from capybara.memory.storage import ConversationStorage

    cfg = load_config()
    model = model or cfg.default_model

    # Load session
    storage = ConversationStorage()
    await storage.initialize()
    messages = await storage.load_session(session_id)

    if not messages:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        return

    console.print(f"[green]Resuming session '{session_id}' ({len(messages)} messages)[/green]")

    # Continue in interactive mode with loaded messages
    from capybara.cli.interactive import interactive_chat_with_session

    await interactive_chat_with_session(
        session_id=session_id,
        model=model,
        stream=True,
        config=cfg,
        initial_messages=messages,
        storage=storage,
    )


if __name__ == "__main__":
    cli()
