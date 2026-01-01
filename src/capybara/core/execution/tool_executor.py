"""Tool execution logic for agents."""

import asyncio
import json
import re
import time
from typing import Any

from rich.console import Console
from rich.live import Live

from capybara.core.config.settings import ToolsConfig
from capybara.core.delegation.event_bus import Event, EventBus, EventType
from capybara.core.execution.execution_log import ExecutionLog, ToolExecution
from capybara.core.logging import SessionLoggerAdapter, get_logger, log_error, log_tool_execution
from capybara.tools.base import AgentMode, ToolPermission
from capybara.tools.registry import ToolRegistry
from capybara.ui.diff_renderer import render_diff

logger = get_logger(__name__)


class ToolExecutor:
    """Handles tool execution with permission checking and event publishing.

    Responsible for:
    - Executing tool calls concurrently
    - Permission checking and user prompts
    - Event publishing (tool start/done/error)
    - Execution logging and tracking
    - Result processing
    """

    def __init__(
        self,
        tools: ToolRegistry,
        console: Console,
        tools_config: ToolsConfig,
        agent_mode: AgentMode,
        session_id: str | None = None,
        session_logger: SessionLoggerAdapter | None = None,
        execution_log: ExecutionLog | None = None,
        event_bus: EventBus | None = None,
    ):
        """Initialize tool executor.

        Args:
            tools: Tool registry
            console: Rich console for output
            tools_config: Tool security configuration
            agent_mode: Agent mode (parent/child)
            session_id: Optional session ID for events
            session_logger: Optional session logger
            execution_log: Optional execution log for tracking
            event_bus: Optional event bus for publishing
        """
        self.tools = tools
        self.console = console
        self.tools_config = tools_config
        self.agent_mode = agent_mode
        self.session_id = session_id
        self.session_logger = session_logger
        self.execution_log = execution_log
        self.event_bus = event_bus
        self._approve_all = False  # Track "approve all" permission state

    async def execute_tools(
        self,
        tool_calls: list[dict[str, Any]],
        ui_renderer: Any,  # AgentUIRenderer - avoid circular import
    ) -> list[dict[str, Any]]:
        """Execute multiple tools concurrently with Live UI display.

        Args:
            tool_calls: List of tool call dicts with id, function.name, function.arguments
            ui_renderer: UI renderer for status display

        Returns:
            List of tool result dicts with role="tool", tool_call_id, content
        """
        if self.session_logger:
            self.session_logger.info(f"Executing {len(tool_calls)} tool call(s)")
        else:
            logger.info(f"Executing {len(tool_calls)} tool call(s)")

        # Track status of each tool
        tool_statuses = {
            tc["id"]: {"name": tc["function"]["name"], "status": "pending"} for tc in tool_calls
        }

        def render_status():
            """Render current status via UI renderer."""
            return ui_renderer.render_status(
                tool_statuses=tool_statuses,
                has_active_children=False,  # Will be set by caller if needed
            )

        async def execute_one(tc: dict[str, Any]) -> dict[str, Any]:
            """Execute a single tool call."""
            tid = tc["id"]
            name = tc["function"]["name"]

            args_str = tc["function"]["arguments"]

            # Parse arguments first (needed for event)
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as e:
                if self.session_logger:
                    self.session_logger.error(
                        f"Failed to parse JSON arguments for tool {name}: {e}"
                    )
                else:
                    logger.error(f"Failed to parse JSON arguments for tool {name}: {e}")

                tool_statuses[tid]["status"] = "error"

                # Publish tool error event
                if self.session_id and self.event_bus:
                    await self.event_bus.publish(
                        Event(
                            session_id=self.session_id,
                            event_type=EventType.TOOL_ERROR,
                            tool_name=name,
                            metadata={"tool_call_id": tid, "error": str(e)},
                        )
                    )

                return {
                    "role": "tool",
                    "tool_call_id": tid,
                    "content": f"Error: Invalid JSON arguments: {e}",
                }

            # Publish tool start event (with parsed arguments for progress display)
            if self.session_id and self.event_bus:
                await self.event_bus.publish(
                    Event(
                        session_id=self.session_id,
                        event_type=EventType.TOOL_START,
                        tool_name=name,
                        metadata={"tool_call_id": tid, "args": args},
                    )
                )

            tool_statuses[tid]["status"] = "running"

            # Permission check
            if not await self._check_permission(name, args):
                self.console.print(f"[red]❌ Tool execution denied: {name}[/red]")
                tool_statuses[tid]["status"] = "error"

                # Publish tool error event
                if self.session_id and self.event_bus:
                    await self.event_bus.publish(
                        Event(
                            session_id=self.session_id,
                            event_type=EventType.TOOL_ERROR,
                            tool_name=name,
                            metadata={"tool_call_id": tid, "error": "Permission denied"},
                        )
                    )

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

            # Display args
            self._display_tool_args(name, args)

            # Execute tool
            start_time = time.time()
            success = False

            try:
                result = await self.tools.execute(name, args)

                # Check if result is an error string (semantic failure)
                result_str = str(result)
                is_error_result = result_str.startswith("Error:")

                # Display diff output for edit_file tool (if successful)
                if not is_error_result and name == "edit_file" and "Update(" in result_str:
                    file_path = args.get("path", "unknown file")
                    render_diff(result_str, file_path, self.console)

                if is_error_result:
                    # Tool returned error - treat as failure for logging
                    success = False
                    tool_statuses[tid]["status"] = "error"

                    # Track error in execution log
                    if self.execution_log:
                        self.execution_log.errors.append((name, result_str))

                    # Publish tool error event
                    if self.session_id and self.event_bus:
                        await self.event_bus.publish(
                            Event(
                                session_id=self.session_id,
                                event_type=EventType.TOOL_ERROR,
                                tool_name=name,
                                metadata={"tool_call_id": tid, "error": result_str},
                            )
                        )
                else:
                    # Tool succeeded
                    success = True
                    tool_statuses[tid]["status"] = "done"

                    # Publish tool done event
                    if self.session_id and self.event_bus:
                        await self.event_bus.publish(
                            Event(
                                session_id=self.session_id,
                                event_type=EventType.TOOL_DONE,
                                tool_name=name,
                                metadata={"tool_call_id": tid, "status": "success"},
                            )
                        )

            except Exception as e:
                tool_statuses[tid]["status"] = "error"
                result = f"Error executing tool: {e}"

                # Log error
                log_error(
                    error=e,
                    context=f"tool_execution:{name}",
                    session_id=self.session_id,
                    agent_mode=self.agent_mode.value,
                )

                # Track error in execution log
                if self.execution_log:
                    self.execution_log.errors.append((name, str(e)))

                # Publish tool error event
                if self.session_id and self.event_bus:
                    await self.event_bus.publish(
                        Event(
                            session_id=self.session_id,
                            event_type=EventType.TOOL_ERROR,
                            tool_name=name,
                            metadata={"tool_call_id": tid, "error": str(e)},
                        )
                    )

            # Record execution
            duration = time.time() - start_time
            self._record_tool_execution(name, args, str(result), success, duration)

            # Log result
            self._log_tool_result(name, result, success, duration)

            return {
                "role": "tool",
                "tool_call_id": tid,
                "content": result if isinstance(result, str) else json.dumps(result),
            }

        # Separate tools by permission requirement
        needs_permission = []
        auto_approved = []

        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
                if await self._needs_user_permission(name, args):
                    needs_permission.append(tc)
                else:
                    auto_approved.append(tc)
            except json.JSONDecodeError:
                # If args can't be parsed, treat as auto-approved (will fail in execute_one)
                auto_approved.append(tc)

        # Execute permission-required tools SEQUENTIALLY without Live UI
        results_with_permission = []
        if needs_permission:
            for tc in needs_permission:
                result = await execute_one(tc)
                results_with_permission.append(result)

        # Check if we're executing sub_agent (which has its own progress display)
        has_sub_agent = any(tc["function"]["name"] == "sub_agent" for tc in auto_approved)

        # Execute auto-approved tools in PARALLEL with Live UI
        results_auto = []
        if auto_approved:
            if has_sub_agent:
                # Sub-agent handles its own progress display, don't show Live panel
                results_auto = await asyncio.gather(
                    *[execute_one(tc) for tc in auto_approved],
                    return_exceptions=True,
                )
            else:
                # Normal tools: show Live status panel
                with Live(
                    render_status(),
                    console=self.console,
                    refresh_per_second=20,
                    transient=True,
                    vertical_overflow="visible",
                ) as live:
                    results_auto = await asyncio.gather(
                        *[execute_one(tc) for tc in auto_approved],
                        return_exceptions=True,
                    )

                    # Final update
                    live.update(render_status())

        # Combine results (permission-required first, then auto-approved)
        results = results_with_permission + list(results_auto)

        # Process results
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

    async def _needs_user_permission(self, name: str, args: dict[str, Any]) -> bool:
        """Check if a tool will require user permission prompt."""
        security_config = self.tools_config.security.get(name)

        # No config = no permission needed
        if not security_config:
            return False

        permission = security_config.permission

        # NEVER and ALWAYS don't require user prompt
        if permission in (ToolPermission.NEVER, ToolPermission.ALWAYS):
            return False

        if permission == ToolPermission.ASK:
            # Check if allowlist matches (would auto-approve)
            args_str = str(args)
            for pattern in security_config.allowlist:
                if re.search(pattern, args_str):
                    return False

            # Check if denylist matches (would auto-deny)
            for pattern in security_config.denylist:
                if re.search(pattern, args_str):
                    return False

            # Check if approve_all is set
            if self._approve_all:
                return False

            # Otherwise, needs user prompt
            return True

        return False

    async def _check_permission(self, name: str, args: dict[str, Any]) -> bool:
        """Check if tool execution is allowed by security policy."""
        security_config = self.tools_config.security.get(name)

        # No config = default allow
        if not security_config:
            return True

        permission = security_config.permission

        if permission == ToolPermission.NEVER:
            return False

        if permission == ToolPermission.ALWAYS:
            return True

        if permission == ToolPermission.ASK:
            # Check approve_all flag first
            if self._approve_all:
                return True

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

    def _truncate_args(self, args: dict[str, Any]) -> tuple[str, bool]:
        """Truncate arguments for display. Returns (truncated_str, was_truncated)."""
        MAX_ARG_LENGTH = 100
        MAX_TOTAL_LENGTH = 500

        truncated_args = {}
        was_truncated = False

        for key, value in args.items():
            value_str = str(value)

            if len(value_str) > MAX_ARG_LENGTH:
                # For large values, show type and size info
                if isinstance(value, str):
                    lines = value.count("\n") + 1
                    size_kb = len(value) / 1024
                    if size_kb < 1:
                        truncated_args[key] = f"<{len(value)} chars, {lines} lines>"
                    else:
                        truncated_args[key] = f"<{size_kb:.1f}KB, {lines} lines>"
                elif isinstance(value, list | tuple):
                    truncated_args[key] = f"<{type(value).__name__} with {len(value)} items>"
                elif isinstance(value, dict):
                    truncated_args[key] = f"<dict with {len(value)} keys>"
                else:
                    truncated_args[key] = f"<{type(value).__name__}>"
                was_truncated = True
            else:
                truncated_args[key] = value

        # Format as function call
        args_parts = []
        for key, value in truncated_args.items():
            if isinstance(value, str) and not value.startswith("<"):
                args_parts.append(f'{key}="{value}"')
            else:
                args_parts.append(f"{key}={value}")

        result = ", ".join(args_parts)
        if len(result) > MAX_TOTAL_LENGTH:
            result = result[:MAX_TOTAL_LENGTH] + "..."
            was_truncated = True

        return result, was_truncated

    async def _ask_user_permission(self, name: str, args: dict[str, Any]) -> bool:
        """Prompt user for permission with simple typing menu."""
        from rich.panel import Panel

        # Truncate arguments for display
        truncated_args, has_more = self._truncate_args(args)
        full_args = json.dumps(args, indent=2)

        while True:  # Loop to allow "View Full Args" option
            # Display tool call with truncated args
            self.console.print(
                f"\n[bold yellow]🔒 Permission:[/bold yellow] [cyan]{name}[/cyan]({truncated_args})"
            )
            if has_more:
                self.console.print("[dim]   (args truncated, type 'v' to view full)[/dim]")

            # Show inline menu options
            self.console.print(
                "   [green]y[/green]=Accept  [red]n[/red]=Deny  [yellow]a[/yellow]=Approve All  [cyan]v[/cyan]=View Full"
            )

            # Get user choice
            try:
                response = await asyncio.to_thread(self.console.input, "   Choice [y/n/a/v]: ")

                choice = response.lower().strip()

                if choice == "y" or choice == "":
                    if self.session_logger:
                        self.session_logger.info(f"Permission request for {name}: approved")
                    self.console.print("[green]   ✓ Accepted[/green]\n")
                    return True

                elif choice == "n":
                    if self.session_logger:
                        self.session_logger.info(f"Permission request for {name}: denied")
                    self.console.print("[red]   ✗ Denied[/red]\n")
                    return False

                elif choice == "a":
                    self._approve_all = True
                    if self.session_logger:
                        self.session_logger.info("User enabled 'approve all' mode")
                    self.console.print("[yellow]   ✓✓ Approve all enabled[/yellow]\n")
                    return True

                elif choice == "v":
                    # Show full arguments
                    self.console.print("\n[bold cyan]Full Arguments:[/bold cyan]")
                    self.console.print(
                        Panel(
                            full_args,
                            border_style="cyan",
                            padding=(1, 1),
                        )
                    )
                    self.console.print()
                    continue  # Loop back to show menu again

                else:
                    self.console.print(
                        f"[red]   Invalid choice '{choice}'. Please use y/n/a/v[/red]"
                    )
                    continue

            except KeyboardInterrupt:
                self.console.print("\n[red]   ✗ Denied (interrupted)[/red]\n")
                return False
            except Exception as e:
                if self.session_logger:
                    self.session_logger.error(f"Error getting user input: {e}")
                else:
                    logger.error(f"Error getting user input: {e}")
                self.console.print("[red]   ✗ Error, denying by default[/red]\n")
                return False

    def _display_tool_args(self, name: str, args: dict[str, Any]) -> None:
        """Display tool arguments above Live region."""
        display_args = []
        for k, v in args.items():
            v_str = str(v)
            if len(v_str) > 100:
                v_str = v_str[:100] + "..."
            if isinstance(v, str):
                v_str = f"'{v_str}'"
            display_args.append(f"{k}={v_str}")

        args_display = ", ".join(display_args)
        self.console.print(f"[dim]> {name}({args_display})[/dim]")

    def _record_tool_execution(
        self, name: str, args: dict, result: str, success: bool, duration: float
    ) -> None:
        """Record tool execution in log."""
        if not self.execution_log:
            return

        from datetime import datetime, timezone

        self.execution_log.tool_executions.append(
            ToolExecution(
                tool_name=name,
                args=args.copy(),
                result_summary=str(result)[:200],
                success=success,
                duration=duration,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

        # Track file operations
        if name == "read_file":
            self.execution_log.files_read.add(args.get("file_path", ""))
        elif name == "write_file":
            self.execution_log.files_written.add(args.get("file_path", ""))
        elif name == "edit_file":
            self.execution_log.files_edited.add(args.get("file_path", ""))

    def _log_tool_result(self, name: str, result: Any, success: bool, duration: float) -> None:
        """Log tool result."""
        result_str = str(result)

        if self.session_logger:
            if len(result_str) > 500:
                self.session_logger.info(f"Tool result ({name}): {result_str[:500]}... [truncated]")
            else:
                self.session_logger.info(f"Tool result ({name}): {result_str}")

            # Log structured event
            log_tool_execution(
                self.session_logger,
                tool_name=name,
                status="success" if success else "error",
                duration=duration,
            )
        else:
            if len(result_str) > 500:
                logger.info(f"Tool result ({name}): {result_str[:500]}... [truncated]")
            else:
                logger.info(f"Tool result ({name}): {result_str}")
