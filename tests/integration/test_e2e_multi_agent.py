"""End-to-end integration tests for complete multi-agent workflow."""

from pathlib import Path
from unittest.mock import patch

import pytest

from capybara.core.agent import Agent, AgentConfig
from capybara.core.agent.status import AgentState
from capybara.core.delegation.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory
from capybara.tools.base import AgentMode
from capybara.tools.builtin import register_builtin_tools
from capybara.tools.builtin.delegation.sub_agent_tool import execute_sub_agent
from capybara.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_complete_parent_child_workflow(tmp_path: Path):
    """Test complete parent→child workflow with all Phase 1-3 features."""
    storage = ConversationStorage(tmp_path / "e2e.db")
    await storage.initialize()

    parent_id = "e2e_parent"
    await storage.create_session(parent_id, "gpt-4", "E2E Parent")

    manager = SessionManager(storage)

    # Create parent agent with full tools
    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "E2E Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools, session_id=parent_id)

    # Register tools
    register_builtin_tools(
        parent_tools,
        parent_session_id=parent_id,
        parent_agent=parent_agent,
        session_manager=manager,
        storage=storage,
    )

    # Mock child agent execution
    execution_count = 0

    async def mock_run(self, prompt):
        nonlocal execution_count
        execution_count += 1

        # Simulate child doing work
        if self.execution_log:
            # Add some fake tool executions
            from datetime import datetime, timezone

            from capybara.core.execution.execution_log import ToolExecution

            self.execution_log.tool_executions.append(
                ToolExecution(
                    tool_name="read_file",
                    args={"file_path": "test.py"},
                    result_summary="File read successfully",
                    success=True,
                    duration=0.1,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            self.execution_log.files_read.add("test.py")

            self.execution_log.tool_executions.append(
                ToolExecution(
                    tool_name="write_file",
                    args={"file_path": "output.txt", "content": "result"},
                    result_summary="File written",
                    success=True,
                    duration=0.05,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            self.execution_log.files_written.add("output.txt")

        # Publish done event
        if self.session_id:
            from capybara.core.delegation.event_bus import Event, EventType

            await self.event_bus.publish(
                Event(
                    session_id=self.session_id,
                    event_type=EventType.AGENT_DONE,
                    metadata={"status": "completed", "turns": 2},
                )
            )

        return "Task completed successfully. Created output.txt with analysis results."

    with patch.object(Agent, "run", side_effect=mock_run):
        # Verify parent starts in IDLE
        assert parent_agent.status.state == AgentState.IDLE
        assert parent_agent.flow_renderer is not None

        # Delegate task
        result = await execute_sub_agent(
            task="Analyze test.py and create a summary",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=10.0,
        )

        # Verify child executed
        assert execution_count == 1

        # Verify result contains comprehensive execution summary (Phase 1)
        assert "<execution_summary>" in result
        assert "<files>" in result
        assert "<tools" in result
        assert "test.py" in result
        assert "output.txt" in result
        assert "read_file" in result
        assert "write_file" in result

        # Verify child session was created
        children = await manager.get_children(parent_id)
        assert len(children) == 1

        # Verify parent status updated (Phase 3)
        assert len(parent_agent.status.child_sessions) == 0  # Child removed after completion

        # Verify events logged
        events = await storage.get_session_events(parent_id)
        event_types = [e["event_type"] for e in events]
        assert "delegation_start" in event_types
        assert "delegation_complete" in event_types


@pytest.mark.asyncio
async def test_child_failure_with_recovery_guidance(tmp_path: Path):
    """Test Phase 2 failure categorization in end-to-end workflow."""
    storage = ConversationStorage(tmp_path / "e2e_fail.db")
    await storage.initialize()

    parent_id = "e2e_fail_parent"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    manager = SessionManager(storage)

    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools, session_id=parent_id)

    register_builtin_tools(
        parent_tools,
        parent_session_id=parent_id,
        parent_agent=parent_agent,
        session_manager=manager,
        storage=storage,
    )

    # Mock child that fails with tool error
    async def failing_run(self, prompt):
        # Add some successful executions first
        if self.execution_log:
            from datetime import datetime, timezone

            from capybara.core.execution.execution_log import ToolExecution

            self.execution_log.tool_executions.append(
                ToolExecution(
                    tool_name="write_file",
                    args={"file_path": "partial.txt"},
                    result_summary="Partial work done",
                    success=True,
                    duration=0.1,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            self.execution_log.files_written.add("partial.txt")

        raise PermissionError("Cannot write to /root/protected.txt")

    with patch.object(Agent, "run", side_effect=failing_run):
        result = await execute_sub_agent(
            task="Write to protected location",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=5.0,
        )

        # Verify structured failure response (Phase 2)
        assert "failed" in result.lower()
        assert "<status>failed</status>" in result
        assert "<failure_category>tool_error</failure_category>" in result
        assert "<retryable>true</retryable>" in result

        # Verify recovery guidance
        assert "Suggested recovery actions" in result or "suggested_actions" in result.lower()
        assert "partial.txt" in result  # Shows partial work done

        # Verify events logged
        events = await storage.get_session_events(parent_id)
        event_types = [e["event_type"] for e in events]
        assert "delegation_error" in event_types


@pytest.mark.asyncio
async def test_timeout_with_partial_progress(tmp_path: Path):
    """Test Phase 2 timeout handling with partial progress tracking."""
    import asyncio

    storage = ConversationStorage(tmp_path / "e2e_timeout.db")
    await storage.initialize()

    parent_id = "e2e_timeout_parent"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    manager = SessionManager(storage)

    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools, session_id=parent_id)

    register_builtin_tools(
        parent_tools,
        parent_session_id=parent_id,
        parent_agent=parent_agent,
        session_manager=manager,
        storage=storage,
    )

    # Mock slow child that makes partial progress
    async def slow_run(self, prompt):
        # Do some work first
        if self.execution_log:
            from datetime import datetime, timezone

            from capybara.core.execution.execution_log import ToolExecution

            self.execution_log.tool_executions.append(
                ToolExecution(
                    tool_name="write_file",
                    args={"file_path": "file1.txt"},
                    result_summary="First file created",
                    success=True,
                    duration=0.1,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            self.execution_log.files_written.add("file1.txt")

            self.execution_log.tool_executions.append(
                ToolExecution(
                    tool_name="write_file",
                    args={"file_path": "file2.txt"},
                    result_summary="Second file created",
                    success=True,
                    duration=0.1,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            self.execution_log.files_written.add("file2.txt")

        # Then hang
        await asyncio.sleep(10)
        return "Should not reach here"

    with patch.object(Agent, "run", side_effect=slow_run):
        result = await execute_sub_agent(
            task="Slow task",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=0.5,  # Short timeout
        )

        # Verify structured timeout failure (Phase 2)
        assert "timed out" in result.lower() or "timeout" in result.lower()
        assert "<status>failed</status>" in result
        assert "<failure_category>timeout</failure_category>" in result
        assert "<retryable>" in result

        # Verify partial progress tracked
        assert "Created 2 files" in result or "file1.txt" in result
        assert "Work completed before failure" in result or "completed_steps" in result.lower()

        # Verify retry suggestion
        assert "timeout=" in result.lower() or "retry" in result.lower()
