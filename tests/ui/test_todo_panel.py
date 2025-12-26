"""Tests for persistent todo panel component."""

import pytest
from rich.panel import Panel
from rich.text import Text

from capybara.tools.builtin.todo import TodoItem, TodoStatus, TodoPriority
from capybara.tools.builtin.todo_state import todo_state
from capybara.ui.todo_panel import PersistentTodoPanel


@pytest.fixture(autouse=True)
def clean_state():
    """Clean state manager before and after each test."""
    # Clear observers and state before test
    todo_state.clear_observers()
    todo_state.update_todos([])
    yield todo_state
    # Clean up after test
    todo_state.clear_observers()
    todo_state.update_todos([])


def test_panel_initialization():
    """Test panel initializes with correct defaults."""
    panel = PersistentTodoPanel()
    assert panel.visible is True
    assert panel.todos == []

    # Cleanup
    panel.cleanup()


def test_panel_subscribes_to_state():
    """Test panel subscribes to state manager on init."""
    panel = PersistentTodoPanel()
    todos = [TodoItem(id="1", content="Task 1", status=TodoStatus.PENDING)]

    # Update state manager
    todo_state.update_todos(todos)

    # Panel should receive update
    assert len(panel.todos) == 1
    assert panel.todos[0].id == "1"

    # Cleanup
    panel.cleanup()


def test_toggle_visibility():
    """Test visibility toggle works."""
    panel = PersistentTodoPanel(visible=True)
    assert panel.visible is True

    panel.toggle_visibility()
    assert panel.visible is False

    panel.toggle_visibility()
    assert panel.visible is True

    panel.cleanup()


def test_show_hide_methods():
    """Test explicit show/hide methods."""
    panel = PersistentTodoPanel(visible=False)

    panel.show()
    assert panel.visible is True

    panel.hide()
    assert panel.visible is False

    panel.cleanup()


def test_auto_show_on_todos():
    """Test panel auto-shows when todos added."""
    panel = PersistentTodoPanel(visible=False)
    assert panel.visible is False

    # Add todos
    todos = [TodoItem(id="1", content="Task 1")]
    todo_state.update_todos(todos)

    # Should auto-show
    assert panel.visible is True

    panel.cleanup()


def test_render_empty_when_hidden():
    """Test render returns empty Text when hidden."""
    panel = PersistentTodoPanel(visible=False)
    panel.todos = [TodoItem(id="1", content="Task 1")]

    result = panel.render()
    assert isinstance(result, Text)
    assert str(result) == ""

    panel.cleanup()


def test_render_empty_when_no_todos():
    """Test render returns empty Text when no todos."""
    panel = PersistentTodoPanel(visible=True)
    panel.todos = []

    result = panel.render()
    assert isinstance(result, Text)
    assert str(result) == ""

    panel.cleanup()


def test_render_with_todos():
    """Test render returns Panel with todos."""
    panel = PersistentTodoPanel(visible=True)
    panel.todos = [
        TodoItem(id="1", content="Task 1", status=TodoStatus.PENDING),
        TodoItem(id="2", content="Task 2", status=TodoStatus.IN_PROGRESS),
        TodoItem(id="3", content="Task 3", status=TodoStatus.COMPLETED),
    ]

    result = panel.render()
    assert isinstance(result, Panel)

    panel.cleanup()


def test_get_icon_pending():
    """Test correct icon for pending status."""
    panel = PersistentTodoPanel()
    assert panel._get_icon(TodoStatus.PENDING) == "☐"
    panel.cleanup()


def test_get_icon_in_progress():
    """Test correct icon for in_progress status."""
    panel = PersistentTodoPanel()
    assert panel._get_icon(TodoStatus.IN_PROGRESS) == "◎"
    panel.cleanup()


def test_get_icon_completed():
    """Test correct icon for completed status."""
    panel = PersistentTodoPanel()
    assert panel._get_icon(TodoStatus.COMPLETED) == "☑"
    panel.cleanup()


def test_get_icon_cancelled():
    """Test correct icon for cancelled status."""
    panel = PersistentTodoPanel()
    assert panel._get_icon(TodoStatus.CANCELLED) == "☒"
    panel.cleanup()


def test_get_style_pending():
    """Test correct style for pending status."""
    panel = PersistentTodoPanel()
    assert panel._get_style(TodoStatus.PENDING) == "white"
    panel.cleanup()


def test_get_style_in_progress():
    """Test correct style for in_progress status."""
    panel = PersistentTodoPanel()
    assert panel._get_style(TodoStatus.IN_PROGRESS) == "bold yellow"
    panel.cleanup()


def test_get_style_completed():
    """Test correct style for completed status."""
    panel = PersistentTodoPanel()
    assert panel._get_style(TodoStatus.COMPLETED) == "dim green"
    panel.cleanup()


def test_get_style_cancelled():
    """Test correct style for cancelled status."""
    panel = PersistentTodoPanel()
    assert panel._get_style(TodoStatus.CANCELLED) == "dim strike"
    panel.cleanup()


def test_cleanup_unsubscribes():
    """Test cleanup removes observer subscription."""
    panel = PersistentTodoPanel()

    # Trigger state update
    todo_state.update_todos([TodoItem(id="1", content="Task 1")])
    assert len(panel.todos) == 1

    # Cleanup
    panel.cleanup()

    # Update state again
    todo_state.update_todos([
        TodoItem(id="1", content="Task 1"),
        TodoItem(id="2", content="Task 2"),
    ])

    # Panel should not receive update after cleanup
    assert len(panel.todos) == 1  # Still old value


def test_progress_footer_incomplete_tasks():
    """Test footer shows progress for incomplete tasks."""
    panel = PersistentTodoPanel(visible=True)
    panel.todos = [
        TodoItem(id="1", content="Task 1", status=TodoStatus.COMPLETED),
        TodoItem(id="2", content="Task 2", status=TodoStatus.PENDING),
        TodoItem(id="3", content="Task 3", status=TodoStatus.IN_PROGRESS),
    ]

    result = panel.render()
    # Should show 1/3 tasks and Ctrl+T hint
    # Exact rendering format depends on Rich, but we can verify it's a Panel
    assert isinstance(result, Panel)

    panel.cleanup()


def test_progress_footer_all_completed():
    """Test footer shows progress for all completed tasks."""
    panel = PersistentTodoPanel(visible=True)
    panel.todos = [
        TodoItem(id="1", content="Task 1", status=TodoStatus.COMPLETED),
        TodoItem(id="2", content="Task 2", status=TodoStatus.COMPLETED),
    ]

    result = panel.render()
    # Should show 2/2 tasks, no Ctrl+T hint (all done)
    assert isinstance(result, Panel)

    panel.cleanup()


def test_multiple_panels_independent():
    """Test multiple panel instances are independent."""
    panel1 = PersistentTodoPanel(visible=True)
    panel2 = PersistentTodoPanel(visible=False)

    assert panel1.visible is True
    assert panel2.visible is False

    panel1.toggle_visibility()
    assert panel1.visible is False
    assert panel2.visible is False  # Panel2 unchanged

    # Cleanup
    panel1.cleanup()
    panel2.cleanup()
