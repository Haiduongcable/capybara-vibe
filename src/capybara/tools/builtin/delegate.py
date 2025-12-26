"""Task delegation tool for spawning child agents."""

import asyncio
import time
from typing import Optional
from rich.console import Console

from capybara.core.agent import Agent, AgentConfig
from capybara.core.agent_status import AgentState, AgentStatus
from capybara.core.child_errors import ChildFailure, FailureCategory
from capybara.core.event_bus import EventType, get_event_bus
from capybara.core.execution_log import ExecutionLog
from capybara.core.logging import log_delegation, log_error
from capybara.core.prompts import build_child_system_prompt
from capybara.core.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory
from capybara.providers.router import ProviderRouter
from capybara.tools.base import AgentMode
from capybara.tools.registry import ToolRegistry


def _generate_execution_summary(
    response: str,
    execution_log: Optional[ExecutionLog],
    session_id: str,
    duration: float
) -> str:
    """Format comprehensive child execution report."""

    if not execution_log:
        # Fallback for parent agents or legacy
        return f"""{response}

<task_metadata>
  <session_id>{session_id}</session_id>
  <status>completed</status>
  <duration>{duration:.2f}s</duration>
</task_metadata>"""

    # Build detailed summary
    files_modified_list = ', '.join(sorted(execution_log.files_modified)) or 'none'
    files_read_list = ', '.join(sorted(execution_log.files_read)) or 'none'

    tool_summary = '\n    '.join(
        f"{tool}: {count}x"
        for tool, count in execution_log.tool_usage_summary.items()
    )

    error_section = ""
    if execution_log.errors:
        error_details = '\n    '.join(
            f"• {tool}: {msg[:100]}"
            for tool, msg in execution_log.errors
        )
        error_section = f"""
  <errors count="{len(execution_log.errors)}">
    {error_details}
  </errors>"""

    return f"""{response}

<execution_summary>
  <session_id>{session_id}</session_id>
  <status>completed</status>
  <duration>{duration:.2f}s</duration>
  <success_rate>{execution_log.success_rate:.0%}</success_rate>

  <files>
    <read count="{len(execution_log.files_read)}">{files_read_list}</read>
    <modified count="{len(execution_log.files_modified)}">{files_modified_list}</modified>
  </files>

  <tools total="{len(execution_log.tool_executions)}">
    {tool_summary}
  </tools>{error_section}
</execution_summary>"""


def _analyze_timeout_failure(child_agent, session_id, duration, timeout, prompt) -> ChildFailure:
    """Analyze timeout to provide recovery guidance."""
    exec_log = child_agent.execution_log

    # Extract completed work
    completed_steps = []
    if exec_log and exec_log.tool_executions:
        successful_writes = [te for te in exec_log.tool_executions
                            if te.tool_name == "write_file" and te.success]
        if successful_writes:
            completed_steps.append(f"Created {len(successful_writes)} files")

        successful_edits = [te for te in exec_log.tool_executions
                           if te.tool_name == "edit_file" and te.success]
        if successful_edits:
            completed_steps.append(f"Modified {len(successful_edits)} files")

    tool_count = len(exec_log.tool_executions) if exec_log else 0
    needs_more_time = tool_count > 0

    # Build suggested actions, filtering None
    actions = [
        f"Retry with timeout={int(timeout * 2)}s" if needs_more_time else None,
        "Break task into smaller subtasks"
    ]
    suggested_actions = [a for a in actions if a is not None]

    return ChildFailure(
        category=FailureCategory.TIMEOUT,
        message=f"Child timed out after {timeout}s",
        session_id=session_id,
        duration=duration,
        completed_steps=completed_steps,
        files_modified=list(exec_log.files_modified) if exec_log else [],
        blocked_on=f"Time limit insufficient",
        suggested_retry=needs_more_time,
        suggested_actions=suggested_actions,
        tool_usage=exec_log.tool_usage_summary if exec_log else {},
        last_successful_tool=exec_log.tool_executions[-1].tool_name if exec_log and exec_log.tool_executions else None
    )


def _analyze_exception_failure(exception, child_agent, session_id, duration, prompt) -> ChildFailure:
    """Categorize exception and provide recovery guidance."""
    exec_log = child_agent.execution_log
    error_msg = str(exception)

    # Check exception type first (more reliable than string matching)
    if isinstance(exception, (PermissionError, FileNotFoundError, OSError, IOError)):
        category = FailureCategory.TOOL_ERROR
        actions = ["Check file permissions", "Verify file exists", "Install missing dependencies if tool failed"]
        retryable = True
    elif isinstance(exception, (ValueError, TypeError, KeyError, AttributeError)):
        category = FailureCategory.INVALID_TASK
        actions = ["Clarify task requirements", "Break into simpler tasks", "Provide more specific instructions"]
        retryable = False
    elif "permission denied" in error_msg.lower() or "not found" in error_msg.lower():
        category = FailureCategory.TOOL_ERROR
        actions = ["Check file permissions", "Verify file exists", "Install missing dependencies if tool failed"]
        retryable = True
    elif "invalid" in error_msg.lower():
        category = FailureCategory.INVALID_TASK
        actions = ["Clarify task requirements", "Break into simpler tasks", "Provide more specific instructions"]
        retryable = False
    else:
        category = FailureCategory.TOOL_ERROR
        actions = ["Review error in child session logs", "Fix environment", "Retry after fixing issue"]
        retryable = True

    return ChildFailure(
        category=category,
        message=f"{type(exception).__name__}: {error_msg}",
        session_id=session_id,
        duration=duration,
        completed_steps=[],
        files_modified=list(exec_log.files_modified) if exec_log else [],
        blocked_on=error_msg,
        suggested_retry=retryable,
        suggested_actions=actions,
        tool_usage=exec_log.tool_usage_summary if exec_log else {},
        last_successful_tool=None
    )


async def delegate_task_impl(
    prompt: str,
    parent_session_id: str,
    parent_agent: Agent,
    session_manager: SessionManager,
    storage: ConversationStorage,
    timeout: float = 300.0,
    model: Optional[str] = None,
) -> str:
    """Core delegation logic (separated for testability)."""

    start_time = time.time()
    child_model = model or parent_agent.config.model

    # 1. Create child session
    child_session_id = await session_manager.create_child_session(
        parent_id=parent_session_id,
        model=child_model,
        prompt=prompt,
        title=f"Subtask: {prompt[:50]}..."
    )

    # 2. Initialize child agent
    from capybara.memory.window import MemoryConfig
    child_memory = ConversationMemory(
        config=MemoryConfig(max_tokens=100_000)
    )
    child_memory.set_system_prompt(build_child_system_prompt())

    child_config = AgentConfig(
        model=child_model,
        max_turns=70,
        timeout=timeout,
        stream=True,
        mode=AgentMode.CHILD  # Restricted mode
    )

    # Clone parent's tool registry and filter for child mode
    # Import here to avoid circular dependency
    from capybara.tools.builtin import register_builtin_tools

    child_tools = ToolRegistry()
    register_builtin_tools(child_tools)

    child_console = Console()  # Separate console for child output

    child_agent = Agent(
        config=child_config,
        memory=child_memory,
        tools=child_tools,
        console=child_console,
        provider=ProviderRouter(default_model=child_model),
        tools_config=parent_agent.tools_config,
        session_id=child_session_id  # Enable event publishing
    )

    # 3. Update parent state to waiting
    if parent_agent.flow_renderer:
        parent_agent._update_state(
            AgentState.WAITING_FOR_CHILD,
            f"Delegated: {prompt[:40]}..."
        )
        parent_agent.status.child_sessions.append(child_session_id)

    # 4. Log start event
    await storage.log_session_event(
        session_id=parent_session_id,
        event_type="delegation_start",
        metadata={"child_session_id": child_session_id, "prompt": prompt[:100]}
    )

    # Log delegation to parent's session logger
    if parent_agent.session_logger:
        log_delegation(
            parent_agent.session_logger,
            action="start",
            parent_session=parent_session_id,
            child_session=child_session_id,
            prompt=prompt[:100]
        )

    # 5. Subscribe to child events for progress display
    event_bus = get_event_bus()

    async def display_child_progress():
        """Display child progress with flow visualization."""
        # Show delegation start
        parent_agent.console.print("\n[bold cyan]┌─ Delegating Task[/bold cyan]")
        parent_agent.console.print(f"│ [dim]Prompt: {prompt[:60]}...[/dim]")
        parent_agent.console.print(f"│ [dim]Child session: {child_session_id[:8]}...[/dim]")
        parent_agent.console.print("│")

        # Update flow renderer with initial child status
        if parent_agent.flow_renderer:
            child_status = AgentStatus(
                session_id=child_session_id,
                mode="child",
                state=AgentState.THINKING,
                parent_session=parent_session_id
            )
            parent_agent.flow_renderer.update_child(child_session_id, child_status)

        # Subscribe to child events
        async for event in event_bus.subscribe(child_session_id):
            if event.event_type == EventType.AGENT_START:
                parent_agent.console.print("│ [cyan]▶ Child started[/cyan]")

            elif event.event_type == EventType.AGENT_STATE_CHANGE:
                # Update child status in flow
                if parent_agent.flow_renderer:
                    child_status.state = AgentState(event.agent_state)
                    child_status.current_action = event.message
                    parent_agent.flow_renderer.update_child(child_session_id, child_status)

            elif event.event_type == EventType.TOOL_START:
                parent_agent.console.print(f"│ [cyan]  ⚙️  {event.tool_name}[/cyan]")

            elif event.event_type == EventType.TOOL_DONE:
                parent_agent.console.print(f"│ [green]  ✓ {event.tool_name}[/green]")

            elif event.event_type == EventType.TOOL_ERROR:
                error_msg = event.metadata.get("error", "unknown")
                parent_agent.console.print(f"│ [red]  ✗ {event.tool_name}: {error_msg[:40]}[/red]")

            elif event.event_type == EventType.AGENT_DONE:
                status_emoji = "✅" if event.metadata.get("status") == "completed" else "❌"
                parent_agent.console.print(f"│ {status_emoji} Child completed")
                parent_agent.console.print("[bold cyan]└─ Task Complete[/bold cyan]\n")
                break

        # Remove child from flow
        if parent_agent.flow_renderer:
            parent_agent.flow_renderer.remove_child(child_session_id)

    try:
        # 5. Execute child agent and progress display concurrently with timeout
        response, _ = await asyncio.wait_for(
            asyncio.gather(
                child_agent.run(prompt),
                display_child_progress()
            ),
            timeout=timeout
        )

        # 5. Save child messages to storage
        for msg in child_memory.get_messages():
            await storage.save_message(child_session_id, msg)

        duration = time.time() - start_time

        # 6. Update parent state back to executing
        if parent_agent.flow_renderer:
            parent_agent.status.child_sessions.remove(child_session_id)
            parent_agent._update_state(
                AgentState.EXECUTING_TOOLS,
                "Processing child response"
            )

        # 7. Log completion event
        await storage.log_session_event(
            session_id=parent_session_id,
            event_type="delegation_complete",
            metadata={
                "child_session_id": child_session_id,
                "duration": duration,
                "status": "completed"
            }
        )

        # Log delegation completion
        if parent_agent.session_logger:
            log_delegation(
                parent_agent.session_logger,
                action="complete",
                parent_session=parent_session_id,
                child_session=child_session_id,
                duration=f"{duration:.2f}s"
            )

        # 8. Generate comprehensive execution summary
        return _generate_execution_summary(
            response=response,
            execution_log=child_agent.execution_log,
            session_id=child_session_id,
            duration=duration
        )

    except asyncio.TimeoutError:
        # Update parent state
        if parent_agent.flow_renderer:
            if child_session_id in parent_agent.status.child_sessions:
                parent_agent.status.child_sessions.remove(child_session_id)

        # Analyze timeout with partial progress
        failure = _analyze_timeout_failure(
            child_agent=child_agent,
            session_id=child_session_id,
            duration=time.time() - start_time,
            timeout=timeout,
            prompt=prompt
        )

        await storage.log_session_event(
            session_id=parent_session_id,
            event_type="delegation_timeout",
            metadata={
                "child_session_id": child_session_id,
                "duration": failure.duration,
                "category": failure.category.value,
                "completed_steps": failure.completed_steps
            }
        )

        # Log delegation timeout
        if parent_agent.session_logger:
            log_delegation(
                parent_agent.session_logger,
                action="timeout",
                parent_session=parent_session_id,
                child_session=child_session_id,
                duration=f"{failure.duration:.2f}s",
                category=failure.category.value
            )

        return failure.to_context_string()

    except Exception as e:
        # Update parent state
        if parent_agent.flow_renderer:
            if child_session_id in parent_agent.status.child_sessions:
                parent_agent.status.child_sessions.remove(child_session_id)

        # Categorize exception and provide recovery guidance
        failure = _analyze_exception_failure(
            exception=e,
            child_agent=child_agent,
            session_id=child_session_id,
            duration=time.time() - start_time,
            prompt=prompt
        )

        await storage.log_session_event(
            session_id=parent_session_id,
            event_type="delegation_error",
            metadata={
                "child_session_id": child_session_id,
                "error": str(e),
                "duration": failure.duration,
                "category": failure.category.value,
                "error_type": type(e).__name__
            }
        )

        # Log delegation error
        if parent_agent.session_logger:
            log_delegation(
                parent_agent.session_logger,
                action="error",
                parent_session=parent_session_id,
                child_session=child_session_id,
                duration=f"{failure.duration:.2f}s",
                category=failure.category.value,
                error=str(e)
            )

        # Log to error log
        log_error(
            error=e,
            context=f"delegation:child={child_session_id[:8]}",
            session_id=parent_session_id,
            agent_mode="parent"
        )

        return failure.to_context_string()


def register_delegate_tool(
    registry: ToolRegistry,
    parent_session_id: str,
    parent_agent: Agent,
    session_manager: SessionManager,
    storage: ConversationStorage
) -> None:
    """Register delegation tool with dependency injection."""

    @registry.tool(
        name="delegate_task",
        description=(
            "Delegate a complex subtask to a specialized child agent. "
            "Use this when you need to parallelize work or isolate a "
            "specific task (e.g., 'research X', 'test Y', 'analyze Z'). "
            "The child agent has full tool access except todo and delegation. "
            "Returns child's response plus session metadata."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task description for the child agent. Be specific and self-contained."
                },
                "timeout": {
                    "type": "number",
                    "description": "Maximum execution time in seconds (default: 300)",
                    "default": 300.0
                },
                "model": {
                    "type": "string",
                    "description": "Optional: Override LLM model for child (default: inherit from parent)"
                }
            },
            "required": ["prompt"]
        },
        allowed_modes=[AgentMode.PARENT]
    )
    async def delegate_task(
        prompt: str,
        timeout: float = 300.0,
        model: Optional[str] = None
    ) -> str:
        """Delegate task to child agent."""
        return await delegate_task_impl(
            prompt=prompt,
            parent_session_id=parent_session_id,
            parent_agent=parent_agent,
            session_manager=session_manager,
            storage=storage,
            timeout=timeout,
            model=model
        )
