"""Main async agent with streaming and tool calling."""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from capybara.core.agent_status import AgentState, AgentStatus
from capybara.core.config import ToolsConfig
from capybara.core.event_bus import Event, EventType, get_event_bus
from capybara.core.execution_log import ExecutionLog, ToolExecution
from capybara.core.logging import (
    get_logger,
    get_session_log_manager,
    log_agent_behavior,
    log_error,
    log_tool_execution,
    log_state_change,
)
from capybara.core.streaming import non_streaming_completion, stream_completion
from capybara.memory.window import ConversationMemory
from capybara.providers.router import ProviderRouter
from capybara.tools.base import AgentMode, ToolPermission
from capybara.tools.builtin.todo import TodoStatus, get_todos
from capybara.tools.registry import ToolRegistry
from capybara.ui.flow_renderer import CommunicationFlowRenderer

logger = get_logger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    model: str = "capybara-gpt-5.2"
    max_turns: int = 70
    timeout: float = 300.0  # 5 minutes for complex tasks
    stream: bool = True
    mode: AgentMode = AgentMode.PARENT


class Agent:
    """Async agent with streaming and tool calling."""

    def __init__(
        self,
        config: AgentConfig,
        memory: ConversationMemory,
        tools: ToolRegistry,
        console: Console | None = None,
        provider: ProviderRouter | None = None,
        tools_config: ToolsConfig | None = None,
        session_id: str | None = None,
    ) -> None:
        self.config = config
        self.memory = memory
        # Filter tools by agent mode
        self.tools = tools.filter_by_mode(config.mode)
        self.console = console or Console()
        self.provider = provider or ProviderRouter(default_model=config.model)
        self.tools_config = tools_config or ToolsConfig()
        self.session_id = session_id
        self.event_bus = get_event_bus()

        # Create session-specific logger
        if session_id:
            log_manager = get_session_log_manager()
            self.session_logger = log_manager.create_session_logger(
                session_id=session_id,
                agent_mode=config.mode.value,
                log_level="INFO"
            )
        else:
            # Fallback to default logger if no session ID
            self.session_logger = None

        # Enable execution logging for child agents only
        self.execution_log: ExecutionLog | None = None
        if config.mode == AgentMode.CHILD:
            self.execution_log = ExecutionLog()

        # Initialize status tracking
        self.status = AgentStatus(
            session_id=session_id or "unknown",
            mode=config.mode.value,
            state=AgentState.IDLE
        )

        # Parent agents get flow renderer
        self.flow_renderer: CommunicationFlowRenderer | None = None
        if config.mode == AgentMode.PARENT:
            self.flow_renderer = CommunicationFlowRenderer(self.console)

    async def run(self, user_input: str) -> str:
        """Main agent loop with tool use.

        Args:
            user_input: User's message

        Returns:
            Final response from the agent
        """
        # Log to session logger if available
        if self.session_logger:
            self.session_logger.info(f"Agent run started with model: {self.config.model}")
            self.session_logger.info(f"User input: {user_input[:200]}...")
        else:
            logger.info(f"Agent run started with model: {self.config.model}")
            logger.info(f"User input: {user_input}")

        # Update state to thinking
        self._update_state(AgentState.THINKING, "Processing user input")

        # Publish agent start event
        if self.session_id:
            await self.event_bus.publish(Event(
                session_id=self.session_id,
                event_type=EventType.AGENT_START,
                metadata={"prompt": user_input[:100]}
            ))

        self.memory.add({"role": "user", "content": user_input})

        try:
            for turn in range(self.config.max_turns):
                if self.session_logger:
                    self.session_logger.info(f"Turn {turn + 1}/{self.config.max_turns}")
                else:
                    logger.info(f"Turn {turn + 1}/{self.config.max_turns}")

                # State: Getting LLM completion
                self._update_state(AgentState.THINKING, f"Turn {turn + 1}")

                response = await self._get_completion()
                self.memory.add(response)

                # Log assistant response
                if response.get("content"):
                    if self.session_logger:
                        self.session_logger.info(f"Agent response: {response['content'][:200]}...")
                    else:
                        logger.info(f"Agent response: {response['content'][:200]}...")

                tool_calls = response.get("tool_calls")
                if not tool_calls:
                    final_response = str(response.get("content", ""))
                    if self.session_logger:
                        self.session_logger.info("Agent completed successfully (no more tool calls)")
                    else:
                        logger.info("Agent completed successfully (no more tool calls)")

                    # Update state to completed
                    self._update_state(AgentState.COMPLETED)

                    # Publish agent done event
                    if self.session_id:
                        await self.event_bus.publish(Event(
                            session_id=self.session_id,
                            event_type=EventType.AGENT_DONE,
                            metadata={"turns": turn + 1, "status": "completed"}
                        ))

                    return final_response

                # State: Executing tools
                self._update_state(AgentState.EXECUTING_TOOLS, f"{len(tool_calls)} tools")

                results = await self._execute_tools(tool_calls)
                for result in results:
                    self.memory.add(result)

            if self.session_logger:
                self.session_logger.warning("Max turns exceeded")
            else:
                logger.warning("Max turns exceeded")

            # Update state to failed
            self._update_state(AgentState.FAILED, "Max turns exceeded")

            # Publish agent done event for max turns
            if self.session_id:
                await self.event_bus.publish(Event(
                    session_id=self.session_id,
                    event_type=EventType.AGENT_DONE,
                    metadata={"turns": self.config.max_turns, "status": "max_turns"}
                ))

            return "Max turns exceeded"
        except Exception as e:
            # Log error
            log_error(
                error=e,
                context="agent_run",
                session_id=self.session_id,
                agent_mode=self.config.mode.value
            )

            # Publish agent done event on error
            if self.session_id:
                await self.event_bus.publish(Event(
                    session_id=self.session_id,
                    event_type=EventType.AGENT_DONE,
                    metadata={"status": "error", "error": str(e)}
                ))
            raise

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
        if self.session_logger:
            self.session_logger.info(f"Executing {len(tool_calls)} tool call(s)")
        else:
            logger.info(f"Executing {len(tool_calls)} tool call(s)")

        # Track status of each tool
        tool_statuses = {tc["id"]: {"name": tc["function"]["name"], "status": "pending"} for tc in tool_calls}

        def render_status():
            """Build unified status display with flow + activity + todos."""
            panels = []

            # 1. Communication Flow (only for parent)
            if self.flow_renderer and self.config.mode == AgentMode.PARENT:
                flow_panel = self.flow_renderer.render()
                if flow_panel and self.status.child_sessions:  # Only show if there are active children
                    panels.append(flow_panel)

            # 2. Build Activity Panel (Tools)
            activity_items: list[Text | Group] = []
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

            if activity_items:
                activity_panel = Panel(
                    Group(*activity_items),
                    title="[bold blue]Active Capabilities[/bold blue]",
                    border_style="blue",
                    box=box.ROUNDED,
                    padding=(0, 1)
                )
                panels.append(activity_panel)

            # 3. Build Todo Panel (Context)
            todos = get_todos()

            if todos:
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
                    Group(*todo_items),
                    title="[bold]Plan[/bold]", # Minimal title
                    border_style="dim white",
                    box=box.MINIMAL,      # Minimal border
                    padding=(0, 1),
                    title_align="left"    # Claude style align
                )
                panels.append(todo_panel)

            # 4. Combine all panels
            if len(panels) == 0:
                return Text("No active status", style="dim")
            elif len(panels) == 1:
                return panels[0]
            else:
                return Group(*panels)

        async def execute_one(tc: dict[str, Any]) -> dict[str, Any]:
            tid = tc["id"]
            name = tc["function"]["name"]

            # Publish tool start event
            if self.session_id:
                await self.event_bus.publish(Event(
                    session_id=self.session_id,
                    event_type=EventType.TOOL_START,
                    tool_name=name,
                    metadata={"tool_call_id": tid}
                ))

            tool_statuses[tid]["status"] = "running"

            args_str = tc["function"]["arguments"]

            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as e:
                if self.session_logger:
                    self.session_logger.error(f"Failed to parse JSON arguments for tool {name}: {e}")
                else:
                    logger.error(f"Failed to parse JSON arguments for tool {name}: {e}")

                tool_statuses[tid]["status"] = "error"

                # Publish tool error event
                if self.session_id:
                    await self.event_bus.publish(Event(
                        session_id=self.session_id,
                        event_type=EventType.TOOL_ERROR,
                        tool_name=name,
                        metadata={"tool_call_id": tid, "error": str(e)}
                    ))

                return {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": f"Error: Invalid JSON arguments: {e}",
                }

            # Permission check
            if not await self._check_permission(name, args):
                 self.console.print(f"[red]❌ Tool execution denied: {name}[/red]")
                 tool_statuses[tid]["status"] = "error"

                 # Publish tool error event
                 if self.session_id:
                     await self.event_bus.publish(Event(
                         session_id=self.session_id,
                         event_type=EventType.TOOL_ERROR,
                         tool_name=name,
                         metadata={"tool_call_id": tid, "error": "Permission denied"}
                     ))

                 return {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": "Error: Tool execution denied by user or policy.",
                }

            # Log tool execution
            if self.session_logger:
                self.session_logger.info(f"Tool call: {name}")
                self.session_logger.debug(f"Tool arguments: {json.dumps(args, indent=2)}")
            else:
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

            import time
            start_time = time.time()
            success = False

            try:
                result = await self.tools.execute(name, args)
                success = True
                tool_statuses[tid]["status"] = "done"

                # Publish tool done event
                if self.session_id:
                    await self.event_bus.publish(Event(
                        session_id=self.session_id,
                        event_type=EventType.TOOL_DONE,
                        tool_name=name,
                        metadata={"tool_call_id": tid, "status": "success"}
                    ))

            except Exception as e:
                tool_statuses[tid]["status"] = "error"
                result = f"Error executing tool: {e}"

                # Log error
                log_error(
                    error=e,
                    context=f"tool_execution:{name}",
                    session_id=self.session_id,
                    agent_mode=self.config.mode.value
                )

                # Track error in execution log
                if self.execution_log:
                    self.execution_log.errors.append((name, str(e)))

                # Publish tool error event
                if self.session_id:
                    await self.event_bus.publish(Event(
                        session_id=self.session_id,
                        event_type=EventType.TOOL_ERROR,
                        tool_name=name,
                        metadata={"tool_call_id": tid, "error": str(e)}
                    ))

            # Record execution in log
            duration = time.time() - start_time
            self._record_tool_execution(name, args, str(result), success, duration)

            # Log tool result and execution
            result_str = str(result)
            if self.session_logger:
                if len(result_str) > 500:
                    self.session_logger.info(f"Tool result ({name}): {result_str[:500]}... [truncated]")
                else:
                    self.session_logger.info(f"Tool result ({name}): {result_str}")

                # Log structured tool execution event
                log_tool_execution(
                    self.session_logger,
                    tool_name=name,
                    status="success" if success else "error",
                    duration=duration
                )
            else:
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

    def _record_tool_execution(self, name: str, args: dict,
                               result: str, success: bool, duration: float):
        """Record tool execution in log."""
        if not self.execution_log:
            return

        from datetime import datetime, timezone

        self.execution_log.tool_executions.append(ToolExecution(
            tool_name=name,
            args=args.copy(),
            result_summary=str(result)[:200],
            success=success,
            duration=duration,
            timestamp=datetime.now(timezone.utc).isoformat()
        ))

        # Track file operations
        if name == "read_file":
            self.execution_log.files_read.add(args.get("file_path", ""))
        elif name == "write_file":
            self.execution_log.files_written.add(args.get("file_path", ""))
        elif name == "edit_file":
            self.execution_log.files_edited.add(args.get("file_path", ""))

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
        self.console.print("\n[bold yellow]⚠️  Permission Request[/bold yellow]")
        self.console.print(f"Tool: [cyan]{name}[/cyan]")
        self.console.print(f"Args: {json.dumps(args, indent=2)}")

        # Proper input handling in async context
        try:
            response = await asyncio.to_thread(self.console.input, "Approve? [y/N]: ")
            approved = response.lower().strip().startswith('y')

            # Log permission decision
            if self.session_logger:
                self.session_logger.info(f"Permission request for {name}: {'approved' if approved else 'denied'}")

            return approved
        except Exception as e:
            if self.session_logger:
                self.session_logger.error(f"Error getting user input: {e}")
            else:
                logger.error(f"Error getting user input: {e}")
            return False

    def _update_state(self, state: AgentState, action: str | None = None):
        """Update agent state and publish event."""
        old_state = self.status.state
        self.status.state = state
        self.status.current_action = action

        # Log state change
        if self.session_logger and old_state != state:
            log_state_change(
                self.session_logger,
                from_state=old_state.value,
                to_state=state.value,
                reason=action
            )

        # Publish state change event
        if self.session_id:
            asyncio.create_task(self.event_bus.publish(Event(
                session_id=self.session_id,
                event_type=EventType.AGENT_STATE_CHANGE,
                agent_state=state.value,
                message=action
            )))

        # Update flow renderer if parent
        if self.flow_renderer:
            self.flow_renderer.update_parent(self.status)
