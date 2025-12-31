"""Tests for delegation tool."""

from pathlib import Path
from unittest.mock import patch

import pytest

from capybara.core.agent import Agent, AgentConfig
from capybara.core.delegation.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory
from capybara.tools.base import AgentMode
from capybara.tools.builtin.delegation.sub_agent_tool import execute_sub_agent
from capybara.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_delegate_creates_child_session(tmp_path: Path):
    """Test that delegation creates a child session."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    parent_id = "parent123"
    await storage.create_session(parent_id, "gpt-4", "Parent Session")

    manager = SessionManager(storage)

    # Create minimal parent agent
    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools)

    # Mock child agent execution
    async def mock_run(self, prompt):
        # Publish AGENT_DONE event so progress display completes
        if self.session_id:
            from capybara.core.delegation.event_bus import Event, EventType

            await self.event_bus.publish(
                Event(
                    session_id=self.session_id,
                    event_type=EventType.AGENT_DONE,
                    metadata={"status": "completed"},
                )
            )
        return f"Child completed: {prompt}"

    # Patch Agent.run temporarily
    # Patch Agent.run temporarily
    with patch.object(Agent, "run", side_effect=mock_run):
        result = await execute_sub_agent(
            task="Test task",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=5.0,
        )

        # Verify child session created
        children = await manager.get_children(parent_id)
        assert len(children) == 1

        # Verify execution summary in response
        assert "<execution_summary>" in result
        assert "<session_id>" in result
        assert "<status>completed</status>" in result
        assert "Child completed: Test task" in result


@pytest.mark.asyncio
async def test_delegate_timeout_handling(tmp_path: Path):
    """Test delegation timeout handling."""
    import asyncio

    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    parent_id = "parent456"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    manager = SessionManager(storage)

    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools)

    # Mock slow agent
    async def slow_run(self, prompt):
        await asyncio.sleep(10)  # Longer than timeout
        return "Should not reach here"

    with patch.object(Agent, "run", side_effect=slow_run):
        result = await execute_sub_agent(
            task="Slow task",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=0.5,  # Very short timeout
        )

        # Verify timeout message with structured failure
        assert "timed out" in result
        assert "<status>failed</status>" in result
        assert "<failure_category>timeout</failure_category>" in result
        assert "<retryable>true</retryable>" in result or "<retryable>false</retryable>" in result


@pytest.mark.asyncio
async def test_delegate_error_handling(tmp_path: Path):
    """Test delegation error handling."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    parent_id = "parent789"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    manager = SessionManager(storage)

    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools)

    # Mock failing agent
    async def failing_run(self, prompt):
        raise ValueError("Simulated error")

    with patch.object(Agent, "run", side_effect=failing_run):
        result = await execute_sub_agent(
            task="Failing task",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=5.0,
        )

        # Verify error message with structured failure
        assert "failed" in result
        assert "ValueError" in result
        assert "<status>failed</status>" in result
        assert (
            "<failure_category>tool_error</failure_category>" in result
            or "<failure_category>invalid_task</failure_category>" in result
        )


@pytest.mark.asyncio
async def test_delegate_logs_events(tmp_path: Path):
    """Test that delegation logs start/complete events."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    parent_id = "parent_events"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    manager = SessionManager(storage)

    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools)

    async def mock_run(self, prompt):
        # Publish AGENT_DONE event so progress display completes
        if self.session_id:
            from capybara.core.delegation.event_bus import Event, EventType

            await self.event_bus.publish(
                Event(
                    session_id=self.session_id,
                    event_type=EventType.AGENT_DONE,
                    metadata={"status": "completed"},
                )
            )
        return "Done"

    with patch.object(Agent, "run", side_effect=mock_run):
        await execute_sub_agent(
            task="Event test",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=5.0,
        )

        # Check events were logged
        events = await storage.get_session_events(parent_id)
        assert len(events) >= 2  # At least start and complete

        event_types = [e["event_type"] for e in events]
        assert "delegation_start" in event_types
        assert "delegation_complete" in event_types


@pytest.mark.asyncio
async def test_child_mode_no_delegation(tmp_path: Path):
    """Test that child agents cannot use sub_agent."""
    from capybara.tools.builtin import register_builtin_tools

    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    parent_id = "parent_check"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    manager = SessionManager(storage)

    # Create parent agent
    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools)

    # Register tools WITH delegation for parent
    register_builtin_tools(
        parent_tools,
        parent_session_id=parent_id,
        parent_agent=parent_agent,
        session_manager=manager,
        storage=storage,
    )

    # Filter for parent mode (should have solve_task)
    parent_filtered = parent_tools.filter_by_mode(AgentMode.PARENT)
    assert "sub_agent" in parent_filtered.list_tools()

    # Filter for child mode (should NOT have solve_task)
    child_filtered = parent_tools.filter_by_mode(AgentMode.CHILD)
    assert "sub_agent" not in child_filtered.list_tools()
