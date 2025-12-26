"""Main async agent with streaming and tool calling."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner
from rich.panel import Panel
from rich.columns import Columns
from rich.table import Table
from rich import box

import re
from capybara.core.logging import get_logger
from capybara.tools.builtin.todo import get_todos, TodoStatus
from capybara.core.streaming import non_streaming_completion, stream_completion
from capybara.core.config import ToolsConfig
from capybara.memory.window import ConversationMemory
from capybara.providers.router import ProviderRouter
from capybara.tools.base import ToolPermission, ToolSecurityConfig
from capybara.tools.registry import ToolRegistry

logger = get_logger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    model: str = "capybara-gpt-5.2"
    max_turns: int = 70
    timeout: float = 300.0  # 5 minutes for complex tasks
    stream: bool = True


class Agent:
    """Async agent with streaming and tool calling."""

    def __init__(
        self,
        config: AgentConfig,
        memory: ConversationMemory,
        tools: ToolRegistry,
        console: Optional[Console] = None,
        provider: Optional[ProviderRouter] = None,
        tools_config: Optional[ToolsConfig] = None,
    ) -> None:
        self.config = config
        self.memory = memory
        self.tools = tools
        self.console = console or Console()
        self.provider = provider or ProviderRouter(default_model=config.model)
        self.tools_config = tools_config or ToolsConfig()

    async def run(self, user_input: str) -> str:
        """Main agent loop with tool use.

        Args:
            user_input: User's message

        Returns:
            Final response from the agent
        """
        logger.info(f"Agent run started with model: {self.config.model}")
        logger.info(f"User input: {user_input}")

        self.memory.add({"role": "user", "content": user_input})

        for turn in range(self.config.max_turns):
            logger.info(f"Turn {turn + 1}/{self.config.max_turns}")

            response = await self._get_completion()
            self.memory.add(response)

            # Log assistant response
            if response.get("content"):
                logger.info(f"Agent response: {response['content'][:200]}...")

            tool_calls = response.get("tool_calls")
            if not tool_calls:
                final_response = response.get("content", "")
                logger.info(f"Agent completed successfully (no more tool calls)")
                return final_response

            results = await self._execute_tools(tool_calls)
            for result in results:
                self.memory.add(result)

        logger.warning("Max turns exceeded")
        return "Max turns exceeded"

    async def _get_completion(self) -> dict[str, Any]:
        """Get completion from LLM (streaming or non-streaming)."""
        tool_schemas = self.tools.schemas if self.tools.schemas else None
        messages = self.memory.get_messages()

        if self.config.stream:
            return await stream_completion(
                provider=self.provider,
                messages=messages,
                model=self.config.model,
                tools=tool_schemas,
                timeout=self.config.timeout,
                console=self.console,
            )
        else:
            return await non_streaming_completion(
                provider=self.provider,
                messages=messages,
                model=self.config.model,
                tools=tool_schemas,
                timeout=self.config.timeout,
                console=self.console,
            )

    async def _execute_tools(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute multiple tools concurrently."""
        logger.info(f"Executing {len(tool_calls)} tool call(s)")

        # Track status of each tool
        tool_statuses = {tc["id"]: {"name": tc["function"]["name"], "status": "pending"} for tc in tool_calls}
        
        def render_status():
            # 1. Build Activity Panel (Tools)
            activity_items = []
            for tc in tool_calls:
                tid = tc["id"]
                info = tool_statuses[tid]
                name = info["name"]
                status = info["status"]
                
                # UX Improvement: Don't show 'todo' tool in the activity list
                # ONLY IF the plan is already visible (todos exist).
                # If list is empty, show the tool so user sees we are initializing.
                if name == "todo" and get_todos():
                    continue
                
                if status == "pending":
                    activity_items.append(Text(f"⏳ {name} (pending)", style="dim"))
                elif status == "running":
                    activity_items.append(Group(Spinner("dots", style="cyan"), Text(f" {name}", style="cyan")))
                elif status == "done":
                    activity_items.append(Text(f"✅ {name}", style="green"))
                elif status == "error":
                    activity_items.append(Text(f"❌ {name} (failed)", style="red"))
            
            activity_panel = Panel(
                Group(*activity_items),
                title="[bold blue]Active Capabilities[/bold blue]",
                border_style="blue",
                box=box.ROUNDED,
                padding=(0, 1)
            )

            # 2. Build Todo Panel (Context)
            todos = get_todos()
            
            todo_items = []
            for t in todos:
                icon = "☐"
                style = "white"
                
                if t.status == TodoStatus.COMPLETED:
                    icon = "☑" # Checked ballot box
                    style = "dim green"
                elif t.status == TodoStatus.IN_PROGRESS:
                    icon = "◎" # Bullseye for focus
                    style = "bold yellow"
                elif t.status == TodoStatus.CANCELLED:
                    icon = "☒"
                    style = "dim strike"
                
                todo_items.append(Text(f" {icon} {t.content}", style=style))

            todo_panel = Panel(
                Group(*todo_items) if todo_items else Text("No tasks plan created yet.", style="dim"),
                title="[bold]Plan[/bold]", # Minimal title
                border_style="dim white",
                box=box.MINIMAL,      # Minimal border
                padding=(0, 1),
                title_align="left"    # Claude style align
            )

            # 3. Combine Panels Smartly
            # If no activity (e.g. only todo tool running), just show Plan
            if not activity_items:
                 return todo_panel
            
            # If no todos, just show Activity (e.g. simple query)
            if not todos:
                return activity_panel

            # Both exist: Top-Bottom Stack
            return Group(activity_panel, todo_panel)

        async def execute_one(tc: dict[str, Any]) -> dict[str, Any]:
            tid = tc["id"]
            name = tc["function"]["name"]
            tool_statuses[tid]["status"] = "running"
            
            args_str = tc["function"]["arguments"]

            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON arguments for tool {name}: {e}")
                tool_statuses[tid]["status"] = "error"
                return {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": f"Error: Invalid JSON arguments: {e}",
                }

            # Permission check
            if not await self._check_permission(name, args):
                 self.console.print(f"[red]❌ Tool execution denied: {name}[/red]")
                 tool_statuses[tid]["status"] = "error"
                 return {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": "Error: Tool execution denied by user or policy.",
                }

            # Log tool execution
            logger.info(f"Tool call: {name}")
            logger.info(f"Tool arguments: {json.dumps(args, indent=2)}")

            # Format args for display (printed ABOVE the live status)
            display_args = []
            for k, v in args.items():
                v_str = str(v)
                if len(v_str) > 100:
                    v_str = v_str[:100] + "..."
                if isinstance(v, str):
                    v_str = f"'{v_str}'"
                display_args.append(f"{k}={v_str}")
            
            args_display = ", ".join(display_args)
            # We must print nicely above the Live region, but Live dictates how printing works.
            # Using self.console.print usually prints above.
            self.console.print(f"[dim]> {name}({args_display})[/dim]")
            
            try:
                result = await self.tools.execute(name, args)
                tool_statuses[tid]["status"] = "done"
            except Exception as e:
                tool_statuses[tid]["status"] = "error"
                result = f"Error executing tool: {e}"

            # Log tool result
            result_str = str(result)
            if len(result_str) > 500:
                logger.info(f"Tool result ({name}): {result_str[:500]}... [truncated]")
            else:
                logger.info(f"Tool result ({name}): {result_str}")

            return {
                "role": "tool",
                "tool_call_id": tid,
                "content": result if isinstance(result, str) else json.dumps(result),
            }

        # Run with Live display
        with Live(render_status(), console=self.console, refresh_per_second=10, transient=True) as live:
            
            # Helper to update live display periodically or on state change could be added
            # But asyncio.gather won't easily yield back to update render_status unless we explicitly loop
            # or use a periodic update task. 
            # Actually, Live() auto-refreshes in a separate thread/timer if refresh_per_second is set
            # BUT render_status() is called on refresh. We need to make sure render_status reads current state.
            
            # Define a wrapper to update UI
            async def update_loop():
                while any(s["status"] in ("pending", "running") for s in tool_statuses.values()):
                    live.update(render_status())
                    await asyncio.sleep(0.1)
                live.update(render_status()) # Final update

            # Execute tasks
            # We can't use wait() easily with Live in main thread blocking? 
            # Actually asyncio.gather is fine. The Live context manager handles the display thread.
            # We just need to make sure `render_status` picks up changes.
            # `tool_statuses` is mutated in `execute_one`, so `render_status` (called by Live's thread) sees it.
            
            results = await asyncio.gather(
                *[execute_one(tc) for tc in tool_calls],
                return_exceptions=True,
            )
            
            # Ensure final state is shown briefly
            live.update(render_status())
            
        processed: list[dict[str, Any]] = []
        for i, r in enumerate(results):
            if isinstance(r, dict):
                processed.append(r)
            else:
                processed.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_calls[i].get("id", "error"),
                        "content": f"Error: {r}",
                    }
                )

        return processed

    async def _check_permission(self, name: str, args: dict[str, Any]) -> bool:
        """Check if tool execution is allowed by security policy."""
        # Use default dict get for now if security is dict
        security_config = self.tools_config.security.get(name)
        
        # If no explicit config, default to ALLOW for backward compatibility
        if not security_config:
            return True

        permission = security_config.permission

        if permission == ToolPermission.NEVER:
            return False

        if permission == ToolPermission.ALWAYS:
            return True

        if permission == ToolPermission.ASK:
            # Check allowlist
            args_str = str(args)
            for pattern in security_config.allowlist:
                if re.search(pattern, args_str):
                    return True
            
            # Check denylist
            for pattern in security_config.denylist:
                if re.search(pattern, args_str):
                    return False
            
            # Ask user
            return await self._ask_user_permission(name, args)

        return True

    async def _ask_user_permission(self, name: str, args: dict[str, Any]) -> bool:
        """Prompt user for permission to execute tool."""
        self.console.print(f"\n[bold yellow]⚠️  Permission Request[/bold yellow]")
        self.console.print(f"Tool: [cyan]{name}[/cyan]")
        self.console.print(f"Args: {json.dumps(args, indent=2)}")
        
        # Proper input handling in async context
        try:
            response = await asyncio.to_thread(self.console.input, "Approve? [y/N]: ")
            return response.lower().strip().startswith('y')
        except Exception as e:
            logger.error(f"Error getting user input: {e}")
            return False
