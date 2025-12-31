"""Tests for Phase 3: UI Communication Flow."""

from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from capybara.core.agent import Agent, AgentConfig
from capybara.core.agent.status import AgentState, AgentStatus
from capybara.core.delegation.event_bus import Event, EventType
from capybara.core.delegation.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory
from capybara.tools.base import AgentMode
from capybara.tools.builtin.delegation.sub_agent_tool import execute_sub_agent
from capybara.tools.registry import ToolRegistry
from capybara.ui.flow_renderer import CommunicationFlowRenderer


def test_agent_status_initialization():
    """Test AgentStatus dataclass initialization."""
    status = AgentStatus(session_id="test123", mode="parent", state=AgentState.IDLE)

    assert status.session_id == "test123"
    assert status.mode == "parent"
    assert status.state == AgentState.IDLE
    assert status.current_action is None
    assert status.child_sessions == []
    assert status.parent_session is None


def test_agent_state_enum():
    """Test all AgentState enum values."""
    assert AgentState.IDLE.value == "idle"
    assert AgentState.THINKING.value == "thinking"
    assert AgentState.EXECUTING_TOOLS.value == "executing"
    assert AgentState.WAITING_FOR_CHILD.value == "waiting"
    assert AgentState.COMPLETED.value == "completed"
    assert AgentState.FAILED.value == "failed"


def test_flow_renderer_initialization():
    """Test CommunicationFlowRenderer initialization."""
    console = Console()
    renderer = CommunicationFlowRenderer(console)

    assert renderer.console == console
    assert renderer.parent_status is None
    assert renderer.child_statuses == {}


def test_flow_renderer_update_parent():
    """Test updating parent status in flow renderer."""
    console = Console()
    renderer = CommunicationFlowRenderer(console)

    status = AgentStatus(session_id="parent1", mode="parent", state=AgentState.THINKING)

    renderer.update_parent(status)
    assert renderer.parent_status == status


def test_flow_renderer_update_child():
    """Test updating child status in flow renderer."""
    console = Console()
    renderer = CommunicationFlowRenderer(console)

    child_status = AgentStatus(session_id="child1", mode="child", state=AgentState.EXECUTING_TOOLS)

    renderer.update_child("child1", child_status)
    assert "child1" in renderer.child_statuses
    assert renderer.child_statuses["child1"] == child_status


def test_flow_renderer_remove_child():
    """Test removing child from flow renderer."""
    console = Console()
    renderer = CommunicationFlowRenderer(console)

    child_status = AgentStatus(session_id="child1", mode="child", state=AgentState.COMPLETED)

    renderer.update_child("child1", child_status)
    assert "child1" in renderer.child_statuses

    renderer.remove_child("child1")
    assert "child1" not in renderer.child_statuses


def test_parent_agent_has_flow_renderer():
    """Test that parent agents get flow renderer."""
    config = AgentConfig(model="gpt-4", mode=AgentMode.PARENT)
    memory = ConversationMemory()
    memory.add({"role": "system", "content": "Test"})
    tools = ToolRegistry()

    agent = Agent(config, memory, tools, session_id="parent1")

    assert agent.flow_renderer is not None
    assert isinstance(agent.flow_renderer, CommunicationFlowRenderer)
    assert agent.status.mode == "parent"
    assert agent.status.state == AgentState.IDLE


def test_child_agent_no_flow_renderer():
    """Test that child agents don't get flow renderer."""
    config = AgentConfig(model="gpt-4", mode=AgentMode.CHILD)
    memory = ConversationMemory()
    memory.add({"role": "system", "content": "Test"})
    tools = ToolRegistry()

    agent = Agent(config, memory, tools, session_id="child1")

    assert agent.flow_renderer is None
    assert agent.status.mode == "child"
    assert agent.status.state == AgentState.IDLE


def test_event_bus_state_change_events():
    """Test new state change event types."""
    assert EventType.AGENT_STATE_CHANGE.value == "agent_state_change"
    assert EventType.DELEGATION_START.value == "delegation_start"
    assert EventType.DELEGATION_COMPLETE.value == "delegation_complete"
    assert EventType.CHILD_RESPONSE.value == "child_response"


def test_event_with_agent_state():
    """Test Event with agent_state and message fields."""
    event = Event(
        session_id="test123",
        event_type=EventType.AGENT_STATE_CHANGE,
        agent_state="thinking",
        message="Processing turn 1",
    )

    assert event.session_id == "test123"
    assert event.event_type == EventType.AGENT_STATE_CHANGE
    assert event.agent_state == "thinking"
    assert event.message == "Processing turn 1"


@pytest.mark.asyncio
async def test_parent_state_updates_during_delegation(tmp_path: Path):
    """Test parent agent state updates during delegation."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    parent_id = "parent_state_test"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    manager = SessionManager(storage)

    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools, session_id=parent_id)

    # Mock child agent run
    async def mock_run(self, prompt):
        if self.session_id:
            from capybara.core.delegation.event_bus import Event, EventType

            await self.event_bus.publish(
                Event(
                    session_id=self.session_id,
                    event_type=EventType.AGENT_DONE,
                    metadata={"status": "completed"},
                )
            )
        return f"Completed: {prompt}"

    with patch.object(Agent, "run", side_effect=mock_run):
        # Parent should start in IDLE
        assert parent_agent.status.state == AgentState.IDLE
        assert len(parent_agent.status.child_sessions) == 0

        # Delegate task
        result = await execute_sub_agent(
            task="Test delegation",
            parent_session_id=parent_id,
            parent_agent=parent_agent,
            session_manager=manager,
            storage=storage,
            timeout=5.0,
        )

        # After delegation completes, child should be removed
        assert len(parent_agent.status.child_sessions) == 0

        # Result should contain execution summary
        assert "<execution_summary>" in result or "<task_metadata>" in result


@pytest.mark.asyncio
async def test_flow_renderer_tracks_multiple_children(tmp_path: Path):
    """Test flow renderer tracks multiple child sessions."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    parent_id = "parent_multi"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    _ = SessionManager(storage)

    parent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    parent_memory = ConversationMemory()
    parent_memory.add({"role": "system", "content": "Test"})
    parent_tools = ToolRegistry()
    parent_agent = Agent(parent_config, parent_memory, parent_tools, session_id=parent_id)

    # Manually add child sessions
    child1_id = "child1"
    child2_id = "child2"

    parent_agent.status.child_sessions.append(child1_id)
    parent_agent.status.child_sessions.append(child2_id)

    assert len(parent_agent.status.child_sessions) == 2
    assert child1_id in parent_agent.status.child_sessions
    assert child2_id in parent_agent.status.child_sessions

    # Add child statuses to flow renderer
    if parent_agent.flow_renderer:
        child1_status = AgentStatus(
            session_id=child1_id, mode="child", state=AgentState.EXECUTING_TOOLS
        )
        child2_status = AgentStatus(session_id=child2_id, mode="child", state=AgentState.THINKING)

        parent_agent.flow_renderer.update_child(child1_id, child1_status)
        parent_agent.flow_renderer.update_child(child2_id, child2_status)

        assert len(parent_agent.flow_renderer.child_statuses) == 2
        assert (
            parent_agent.flow_renderer.child_statuses[child1_id].state == AgentState.EXECUTING_TOOLS
        )
        assert parent_agent.flow_renderer.child_statuses[child2_id].state == AgentState.THINKING
