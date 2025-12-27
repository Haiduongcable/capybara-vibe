"""Tool execution logic for agents."""

import asyncio
import json
import re
import time
from typing import Any

from rich.console import Console
from rich.live import Live

from capybara.core.delegation.event_bus import Event, EventType, EventBus
from capybara.core.execution.execution_log import ExecutionLog, ToolExecution
from capybara.core.logging import SessionLoggerAdapter, get_logger, log_error, log_tool_execution
from capybara.core.config.settings import ToolsConfig
from capybara.tools.base import AgentMode, ToolPermission
from capybara.tools.registry import ToolRegistry

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
            tc["id"]: {"name": tc["function"]["name"], "status": "pending"}
            for tc in tool_calls
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

            # Publish tool start event
            if self.session_id and self.event_bus:
                await self.event_bus.publish(
                    Event(
                        session_id=self.session_id,
                        event_type=EventType.TOOL_START,
                        tool_name=name,
                        metadata={"tool_call_id": tid},
                    )
                )

            tool_statuses[tid]["status"] = "running"

            args_str = tc["function"]["arguments"]

            # Parse arguments
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as e:
                if self.session_logger:
                    self.session_logger.error(f"Failed to parse JSON arguments for tool {name}: {e}")
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

        # Run with Live display
        with Live(
            render_status(), console=self.console, refresh_per_second=10, transient=True
        ) as live:
            results = await asyncio.gather(
                *[execute_one(tc) for tc in tool_calls],
                return_exceptions=True,
            )

            # Final update
            live.update(render_status())

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

        try:
            response = await asyncio.to_thread(self.console.input, "Approve? [y/N]: ")
            approved = response.lower().strip().startswith("y")

            # Log decision
            if self.session_logger:
                self.session_logger.info(
                    f"Permission request for {name}: {'approved' if approved else 'denied'}"
                )

            return approved
        except Exception as e:
            if self.session_logger:
                self.session_logger.error(f"Error getting user input: {e}")
            else:
                logger.error(f"Error getting user input: {e}")
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

    def _log_tool_result(
        self, name: str, result: Any, success: bool, duration: float
    ) -> None:
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
