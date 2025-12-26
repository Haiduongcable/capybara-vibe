"""Tests for SessionManager."""

import pytest
from pathlib import Path

from capybara.core.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage


@pytest.mark.asyncio
async def test_create_child_session(tmp_path: Path):
    """Test creating child session with parent relationship."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    manager = SessionManager(storage)

    # Create parent
    parent_id = "parent123"
    await storage.create_session(parent_id, "gpt-4", "Parent Session")

    # Create child
    child_id = await manager.create_child_session(parent_id, "gpt-4", "Do research")

    # Verify hierarchy
    assert await manager.is_child_session(child_id)
    children = await manager.get_children(parent_id)
    assert child_id in children


@pytest.mark.asyncio
async def test_get_hierarchy(tmp_path: Path):
    """Test getting session hierarchy information."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    manager = SessionManager(storage)

    # Create parent
    parent_id = "parent456"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    # Create child
    child_id = await manager.create_child_session(parent_id, "gpt-4", "Child task")

    # Get child hierarchy
    hierarchy = await manager.get_hierarchy(child_id)
    assert hierarchy["parent_id"] == parent_id
    assert hierarchy["agent_mode"] == "child"

    # Get parent hierarchy
    parent_hierarchy = await manager.get_hierarchy(parent_id)
    assert parent_hierarchy["parent_id"] is None
    assert parent_hierarchy["agent_mode"] == "parent"


@pytest.mark.asyncio
async def test_get_agent_mode(tmp_path: Path):
    """Test getting agent mode for sessions."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    manager = SessionManager(storage)

    # Create parent
    parent_id = "parent789"
    await storage.create_session(parent_id, "gpt-4", "Parent")

    # Create child
    child_id = await manager.create_child_session(parent_id, "gpt-4", "Child")

    assert await manager.get_agent_mode(parent_id) == "parent"
    assert await manager.get_agent_mode(child_id) == "child"


@pytest.mark.asyncio
async def test_session_event_logging(tmp_path: Path):
    """Test logging and retrieving session events."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    session_id = "test123"
    await storage.create_session(session_id, "gpt-4", "Test")

    # Log events
    await storage.log_session_event(session_id, "tool_start", "bash", {"cmd": "ls"})
    await storage.log_session_event(session_id, "tool_done", "bash", {"status": "success"})

    # Retrieve
    events = await storage.get_session_events(session_id)
    assert len(events) == 2
    # Events ordered DESC, so most recent first
    assert events[0]["event_type"] == "tool_done"
    assert events[1]["event_type"] == "tool_start"
    assert events[1]["metadata"]["cmd"] == "ls"


@pytest.mark.asyncio
async def test_multiple_children(tmp_path: Path):
    """Test parent with multiple children."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    manager = SessionManager(storage)

    parent_id = "multi_parent"
    await storage.create_session(parent_id, "gpt-4", "Parent with multiple children")

    # Create 3 children
    child1 = await manager.create_child_session(parent_id, "gpt-4", "Task 1")
    child2 = await manager.create_child_session(parent_id, "gpt-4", "Task 2")
    child3 = await manager.create_child_session(parent_id, "gpt-4", "Task 3")

    # Verify all children
    children = await manager.get_children(parent_id)
    assert len(children) == 3
    assert child1 in children
    assert child2 in children
    assert child3 in children


@pytest.mark.asyncio
async def test_backward_compatibility(tmp_path: Path):
    """Test that sessions without parent_id work (backward compatibility)."""
    storage = ConversationStorage(tmp_path / "test.db")
    await storage.initialize()

    manager = SessionManager(storage)

    # Create old-style session (parent_id will be NULL)
    old_session_id = "old_session"
    await storage.create_session(old_session_id, "gpt-4", "Old Session")

    # Should not be a child
    assert not await manager.is_child_session(old_session_id)
    assert await manager.get_agent_mode(old_session_id) == "parent"
