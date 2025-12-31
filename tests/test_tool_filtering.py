"""Tests for tool filtering by agent mode."""

import pytest

from capybara.tools.base import AgentMode
from capybara.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_parent_mode_has_all_tools():
    """Test parent mode has access to all tools."""
    registry = ToolRegistry()

    @registry.tool("allowed_all", "Test tool", {})
    async def allowed():
        return "ok"

    @registry.tool("parent_only", "Test tool", {}, allowed_modes=[AgentMode.PARENT])
    async def parent():
        return "ok"

    parent_reg = registry.filter_by_mode(AgentMode.PARENT)
    assert len(parent_reg.list_tools()) == 2
    assert "allowed_all" in parent_reg.list_tools()
    assert "parent_only" in parent_reg.list_tools()


@pytest.mark.asyncio
async def test_child_mode_filtered():
    """Test child mode has restricted access."""
    registry = ToolRegistry()

    @registry.tool("allowed_all", "Test tool", {})
    async def allowed():
        return "ok"

    @registry.tool("parent_only", "Test tool", {}, allowed_modes=[AgentMode.PARENT])
    async def parent():
        return "ok"

    child_reg = registry.filter_by_mode(AgentMode.CHILD)
    assert len(child_reg.list_tools()) == 1
    assert "allowed_all" in child_reg.list_tools()
    assert "parent_only" not in child_reg.list_tools()


@pytest.mark.asyncio
async def test_is_tool_allowed():
    """Test is_tool_allowed method."""
    registry = ToolRegistry()

    @registry.tool("unrestricted", "Test", {})
    async def unrestricted():
        return "ok"

    @registry.tool("parent_only", "Test", {}, allowed_modes=[AgentMode.PARENT])
    async def parent_only():
        return "ok"

    # Unrestricted tool allowed for both
    assert registry.is_tool_allowed("unrestricted", AgentMode.PARENT)
    assert registry.is_tool_allowed("unrestricted", AgentMode.CHILD)

    # Parent-only tool
    assert registry.is_tool_allowed("parent_only", AgentMode.PARENT)
    assert not registry.is_tool_allowed("parent_only", AgentMode.CHILD)


@pytest.mark.asyncio
async def test_child_cannot_use_todo():
    """Test that child mode cannot access todo tool."""
    from capybara.tools.builtin.todo import register_todo_tool

    registry = ToolRegistry()
    register_todo_tool(registry)

    # Parent has todo
    parent_reg = registry.filter_by_mode(AgentMode.PARENT)
    assert "todo" in parent_reg.list_tools()

    # Child does not
    child_reg = registry.filter_by_mode(AgentMode.CHILD)
    assert "todo" not in child_reg.list_tools()


@pytest.mark.asyncio
async def test_filter_preserves_restrictions():
    """Test that filtering preserves restriction metadata."""
    registry = ToolRegistry()

    @registry.tool("parent_only", "Test", {}, allowed_modes=[AgentMode.PARENT])
    async def parent_only():
        return "ok"

    parent_reg = registry.filter_by_mode(AgentMode.PARENT)

    # Should still have restriction info
    assert not parent_reg.is_tool_allowed("parent_only", AgentMode.CHILD)
    assert parent_reg.is_tool_allowed("parent_only", AgentMode.PARENT)


@pytest.mark.asyncio
async def test_multiple_modes_allowed():
    """Test tool can specify multiple allowed modes."""
    registry = ToolRegistry()

    @registry.tool(
        "both_modes",
        "Test",
        {},
        allowed_modes=[AgentMode.PARENT, AgentMode.CHILD],
    )
    async def both_modes():
        return "ok"

    parent_reg = registry.filter_by_mode(AgentMode.PARENT)
    child_reg = registry.filter_by_mode(AgentMode.CHILD)

    assert "both_modes" in parent_reg.list_tools()
    assert "both_modes" in child_reg.list_tools()
