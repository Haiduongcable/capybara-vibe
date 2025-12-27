"""Integration tests for end-to-end delegation flows."""

import pytest
from pathlib import Path

from capybara.core.agent import Agent, AgentConfig
from capybara.core.delegation.session_manager import SessionManager
from capybara.memory.window import ConversationMemory
from capybara.memory.storage import ConversationStorage
from capybara.tools.registry import ToolRegistry
from capybara.tools.base import AgentMode
from capybara.tools.builtin import register_builtin_tools


@pytest.mark.asyncio
async def test_delegation_creates_child_and_completes(tmp_path: Path):
    """Test that parent can delegate task and child completes successfully."""

    # Setup storage
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    # Create parent session
    parent_id = "parent_integration"
    await storage.create_session(parent_id, "gpt-4", "Parent Session")

    # Setup session manager
    session_manager = SessionManager(storage)

    # Setup parent agent
    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test parent"})
    parent_tools = ToolRegistry()

    # Register tools including delegation
    register_builtin_tools(
        parent_tools,
        parent_session_id=parent_id,
        parent_agent=None,  # Will be set after agent creation
        session_manager=session_manager,
        storage=storage
    )

    # Create agent after tools are registered
    parent_agent = Agent(parent_config, parent_memory, parent_tools)

    # Re-register with actual agent reference
    parent_tools = ToolRegistry()
    register_builtin_tools(
        parent_tools,
        parent_session_id=parent_id,
        parent_agent=parent_agent,
        session_manager=session_manager,
        storage=storage
    )
    parent_agent.tools = parent_tools.filter_by_mode(AgentMode.PARENT)

    # Mock Agent.run to simulate child execution
    async def mock_child_run(self, prompt):
        from capybara.core.delegation.event_bus import Event, EventType
        if self.session_id:
            await self.event_bus.publish(Event(
                session_id=self.session_id,
                event_type=EventType.AGENT_DONE,
                metadata={"status": "completed"}
            ))
        return f"Task completed: {prompt}"

    original_run = Agent.run
    Agent.run = mock_child_run

    try:
        # Execute task solving via solve_task tool
        result = await parent_agent.tools.execute(
            "solve_task",
            {"task": "Test integration task", "timeout": 10.0}
        )

        # Verify result contains execution summary
        assert "<execution_summary>" in result
        assert "<session_id>" in result
        assert "<status>completed</status>" in result
        assert "<success_rate>" in result
        assert "<files>" in result
        assert "<tools" in result

        # Verify child session was created
        children = await session_manager.get_children(parent_id)
        assert len(children) == 1

        # Verify child has correct mode
        child_id = children[0]
        child_mode = await session_manager.get_agent_mode(child_id)
        assert child_mode == "child"

        # Verify events were logged
        events = await storage.get_session_events(parent_id)
        event_types = [e["event_type"] for e in events]
        assert "delegation_start" in event_types
        assert "delegation_complete" in event_types

    finally:
        Agent.run = original_run


@pytest.mark.asyncio
async def test_child_agent_cannot_delegate(tmp_path: Path):
    """Test that child agent doesn't have access to solve_task tool."""

    # Setup child agent directly
    child_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.CHILD)
    child_memory = ConversationMemory()
    child_memory.add({"role": "system", "content": "Test child"})
    child_tools = ToolRegistry()

    # Register tools (without delegation dependencies)
    register_builtin_tools(child_tools)

    child_agent = Agent(child_config, child_memory, child_tools)

    # Verify solve_task is not available to child
    available_tools = child_agent.tools.list_tools()
    assert "solve_task" not in available_tools
    assert "todo" not in available_tools  # Also verify todo is restricted


@pytest.mark.asyncio
async def test_session_hierarchy_persists(tmp_path: Path):
    """Test that session hierarchy is correctly persisted in database."""

    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    # Create parent
    parent_id = "parent_persist"
    await storage.create_session(parent_id, "gpt-4", "Parent Session")

    manager = SessionManager(storage)

    # Create multiple children
    child1_id = await manager.create_child_session(
        parent_id=parent_id,
        model="gpt-4",
        prompt="Task 1",
        title="Child 1"
    )

    child2_id = await manager.create_child_session(
        parent_id=parent_id,
        model="gpt-4",
        prompt="Task 2",
        title="Child 2"
    )

    # Verify parent session
    parent_info = await storage.get_session_hierarchy(parent_id)
    assert parent_info["id"] == parent_id
    assert parent_info.get("parent_id") is None  # Parent has no parent

    # Verify children via manager
    children = await manager.get_children(parent_id)
    assert len(children) == 2
    assert child1_id in children
    assert child2_id in children

    # Verify each child knows its parent
    for child_id in [child1_id, child2_id]:
        child_info = await storage.get_session_hierarchy(child_id)
        assert child_info["parent_id"] == parent_id
        assert child_info["agent_mode"] == "child"
