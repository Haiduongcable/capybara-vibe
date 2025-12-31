"""Integration tests for todo workflow."""

import pytest

from capybara.tools.builtin.todo import TodoItem, TodoStatus
from capybara.tools.builtin.todo_state import todo_state
from capybara.ui.todo_panel import PersistentTodoPanel


@pytest.fixture(autouse=True)
def clean_state():
    """Clean state before and after each test."""
    todo_state.clear_observers()
    todo_state.update_todos([])
    yield
    todo_state.clear_observers()
    todo_state.update_todos([])


def test_end_to_end_todo_workflow():
    """Test complete workflow: create todos → execute → update → complete."""
    # Create panel
    panel = PersistentTodoPanel(visible=False)
    assert panel.visible is False
    assert len(panel.todos) == 0

    # Step 1: Create todos (simulating agent creating a plan)
    todos = [
        TodoItem(id="1", content="Research existing code", status=TodoStatus.PENDING),
        TodoItem(id="2", content="Design solution", status=TodoStatus.PENDING),
        TodoItem(id="3", content="Implement feature", status=TodoStatus.PENDING),
    ]
    todo_state.update_todos(todos)

    # Panel should auto-show and receive todos
    assert panel.visible is True
    assert len(panel.todos) == 3

    # Step 2: Start first task
    todos[0] = TodoItem(id="1", content="Research existing code", status=TodoStatus.IN_PROGRESS)
    todo_state.update_todos(todos)
    assert panel.todos[0].status == TodoStatus.IN_PROGRESS

    # Step 3: Complete first task
    todos[0] = TodoItem(id="1", content="Research existing code", status=TodoStatus.COMPLETED)
    todo_state.update_todos(todos)
    assert panel.todos[0].status == TodoStatus.COMPLETED

    # Step 4: Start second task
    todos[1] = TodoItem(id="2", content="Design solution", status=TodoStatus.IN_PROGRESS)
    todo_state.update_todos(todos)
    assert panel.todos[1].status == TodoStatus.IN_PROGRESS

    # Step 5: Complete all tasks
    todos[1] = TodoItem(id="2", content="Design solution", status=TodoStatus.COMPLETED)
    todos[2] = TodoItem(id="3", content="Implement feature", status=TodoStatus.COMPLETED)
    todo_state.update_todos(todos)

    assert all(t.status == TodoStatus.COMPLETED for t in panel.todos)

    # Cleanup
    panel.cleanup()


def test_panel_visibility_toggle_workflow():
    """Test toggling panel visibility during workflow."""
    panel = PersistentTodoPanel(visible=True)

    # Add todos
    todos = [
        TodoItem(id="1", content="Task 1", status=TodoStatus.PENDING),
    ]
    todo_state.update_todos(todos)

    # Toggle off (Ctrl+T)
    panel.toggle_visibility()
    assert panel.visible is False

    # Render should return empty
    rendered = panel.render()
    assert str(rendered) == ""

    # Toggle back on
    panel.toggle_visibility()
    assert panel.visible is True

    # Render should show panel
    rendered = panel.render()
    assert rendered != ""

    panel.cleanup()


def test_panel_persists_across_updates():
    """Test panel persists and updates as state changes."""
    panel = PersistentTodoPanel(visible=True)

    # Initial todos
    todo_state.update_todos(
        [
            TodoItem(id="1", content="Task 1", status=TodoStatus.PENDING),
        ]
    )
    assert len(panel.todos) == 1

    # Add more todos
    todo_state.update_todos(
        [
            TodoItem(id="1", content="Task 1", status=TodoStatus.PENDING),
            TodoItem(id="2", content="Task 2", status=TodoStatus.PENDING),
            TodoItem(id="3", content="Task 3", status=TodoStatus.PENDING),
        ]
    )
    assert len(panel.todos) == 3

    # Remove todos
    todo_state.update_todos(
        [
            TodoItem(id="1", content="Task 1", status=TodoStatus.COMPLETED),
        ]
    )
    assert len(panel.todos) == 1
    assert panel.todos[0].status == TodoStatus.COMPLETED

    panel.cleanup()


def test_multiple_status_transitions():
    """Test todos can transition through multiple states."""
    panel = PersistentTodoPanel(visible=True)

    # Start with pending
    todo_state.update_todos(
        [
            TodoItem(id="1", content="Task 1", status=TodoStatus.PENDING),
        ]
    )
    assert panel.todos[0].status == TodoStatus.PENDING

    # Move to in_progress
    todo_state.update_todos(
        [
            TodoItem(id="1", content="Task 1", status=TodoStatus.IN_PROGRESS),
        ]
    )
    assert panel.todos[0].status == TodoStatus.IN_PROGRESS

    # Move to completed
    todo_state.update_todos(
        [
            TodoItem(id="1", content="Task 1", status=TodoStatus.COMPLETED),
        ]
    )
    assert panel.todos[0].status == TodoStatus.COMPLETED

    panel.cleanup()


def test_panel_shows_correct_icons_for_each_status():
    """Test panel renders correct icons for different statuses."""
    panel = PersistentTodoPanel(visible=True)

    todos = [
        TodoItem(id="1", content="Pending task", status=TodoStatus.PENDING),
        TodoItem(id="2", content="In progress task", status=TodoStatus.IN_PROGRESS),
        TodoItem(id="3", content="Completed task", status=TodoStatus.COMPLETED),
        TodoItem(id="4", content="Cancelled task", status=TodoStatus.CANCELLED),
    ]
    todo_state.update_todos(todos)

    # Verify icons
    assert panel._get_icon(TodoStatus.PENDING) == "☐"
    assert panel._get_icon(TodoStatus.IN_PROGRESS) == "◎"
    assert panel._get_icon(TodoStatus.COMPLETED) == "☑"
    assert panel._get_icon(TodoStatus.CANCELLED) == "☒"

    # Verify styles
    assert panel._get_style(TodoStatus.PENDING) == "white"
    assert panel._get_style(TodoStatus.IN_PROGRESS) == "bold yellow"
    assert panel._get_style(TodoStatus.COMPLETED) == "dim green"
    assert panel._get_style(TodoStatus.CANCELLED) == "dim strike"

    panel.cleanup()
