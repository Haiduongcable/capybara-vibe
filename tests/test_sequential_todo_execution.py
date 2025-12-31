"""Test sequential todo execution enforcement."""

import pytest

from capybara.tools.builtin.todo import register_todo_tool
from capybara.tools.registry import ToolRegistry


@pytest.fixture
async def todo_tool():
    """Create todo tool for testing."""
    registry = ToolRegistry()
    register_todo_tool(registry)
    tool = registry.get_tool("todo")
    assert tool is not None
    return tool


@pytest.mark.asyncio
async def test_single_in_progress_task_allowed(todo_tool):
    """Test that exactly 1 in_progress task is allowed."""
    todos = [
        {"id": "1", "content": "Task 1", "status": "in_progress"},
        {"id": "2", "content": "Task 2", "status": "pending"},
        {"id": "3", "content": "Task 3", "status": "completed"},
    ]

    result = await todo_tool(action="write", todos=todos)

    # Should succeed
    assert "Error" not in result
    assert "Updated 3 todos" in result


@pytest.mark.asyncio
async def test_multiple_in_progress_tasks_rejected(todo_tool):
    """Test that multiple in_progress tasks are rejected."""
    todos = [
        {"id": "1", "content": "Task 1", "status": "in_progress"},
        {"id": "2", "content": "Task 2", "status": "in_progress"},
        {"id": "3", "content": "Task 3", "status": "pending"},
    ]

    result = await todo_tool(action="write", todos=todos)

    # Should fail with clear error
    assert "Error" in result
    assert "Only 1 task can be 'in_progress' at a time" in result
    assert "Found 2 tasks in_progress" in result
    assert "['1', '2']" in result


@pytest.mark.asyncio
async def test_no_in_progress_tasks_allowed(todo_tool):
    """Test that having 0 in_progress tasks is allowed."""
    todos = [
        {"id": "1", "content": "Task 1", "status": "pending"},
        {"id": "2", "content": "Task 2", "status": "pending"},
        {"id": "3", "content": "Task 3", "status": "completed"},
    ]

    result = await todo_tool(action="write", todos=todos)

    # Should succeed
    assert "Error" not in result
    assert "Updated 3 todos" in result


@pytest.mark.asyncio
async def test_transition_between_tasks(todo_tool):
    """Test sequential task transitions."""
    # Start with task 1 in progress
    todos_step1 = [
        {"id": "1", "content": "Task 1", "status": "in_progress"},
        {"id": "2", "content": "Task 2", "status": "pending"},
    ]

    result1 = await todo_tool(action="write", todos=todos_step1)
    assert "Error" not in result1

    # Complete task 1, start task 2
    todos_step2 = [
        {"id": "1", "content": "Task 1", "status": "completed"},
        {"id": "2", "content": "Task 2", "status": "in_progress"},
    ]

    result2 = await todo_tool(action="write", todos=todos_step2)
    assert "Error" not in result2

    # Attempt to mark both as in_progress (should fail)
    todos_step3 = [
        {"id": "1", "content": "Task 1", "status": "in_progress"},
        {"id": "2", "content": "Task 2", "status": "in_progress"},
    ]

    result3 = await todo_tool(action="write", todos=todos_step3)
    assert "Error" in result3
    assert "Only 1 task can be 'in_progress'" in result3


@pytest.mark.asyncio
async def test_three_in_progress_tasks_rejected(todo_tool):
    """Test that 3+ in_progress tasks are also rejected."""
    todos = [
        {"id": "1", "content": "Task 1", "status": "in_progress"},
        {"id": "2", "content": "Task 2", "status": "in_progress"},
        {"id": "3", "content": "Task 3", "status": "in_progress"},
    ]

    result = await todo_tool(action="write", todos=todos)

    # Should fail
    assert "Error" in result
    assert "Only 1 task can be 'in_progress' at a time" in result
    assert "Found 3 tasks in_progress" in result
