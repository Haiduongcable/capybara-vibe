"""Tests for todo state management."""

from capybara.tools.builtin.todo import TodoItem, TodoStatus
from capybara.tools.builtin.todo_state import TodoStateManager, todo_state


def test_todo_state_manager_initialization():
    """Test state manager initializes with empty state."""
    manager = TodoStateManager()
    assert manager.get_todos() == []


def test_update_todos():
    """Test updating todo state."""
    manager = TodoStateManager()
    todos = [
        TodoItem(id="1", content="Task 1", status=TodoStatus.PENDING),
        TodoItem(id="2", content="Task 2", status=TodoStatus.IN_PROGRESS),
    ]

    manager.update_todos(todos)
    assert len(manager.get_todos()) == 2
    assert manager.get_todos()[0].id == "1"
    assert manager.get_todos()[1].status == TodoStatus.IN_PROGRESS


def test_get_todos_returns_copy():
    """Test that get_todos returns a copy, not reference."""
    manager = TodoStateManager()
    todos = [TodoItem(id="1", content="Task 1")]
    manager.update_todos(todos)

    # Modify returned list
    returned = manager.get_todos()
    returned.append(TodoItem(id="2", content="Task 2"))

    # Original state should be unchanged
    assert len(manager.get_todos()) == 1


def test_observer_notification():
    """Test observers are notified on state changes."""
    manager = TodoStateManager()
    notifications = []

    def observer(todos):
        notifications.append(len(todos))

    manager.subscribe(observer)

    # Update state
    manager.update_todos([TodoItem(id="1", content="Task 1")])
    assert notifications == [1]

    manager.update_todos(
        [
            TodoItem(id="1", content="Task 1"),
            TodoItem(id="2", content="Task 2"),
        ]
    )
    assert notifications == [1, 2]


def test_multiple_observers():
    """Test multiple observers can subscribe."""
    manager = TodoStateManager()
    calls_a = []
    calls_b = []

    def observer_a(todos):
        calls_a.append(len(todos))

    def observer_b(todos):
        calls_b.append(len(todos))

    manager.subscribe(observer_a)
    manager.subscribe(observer_b)

    manager.update_todos([TodoItem(id="1", content="Task 1")])

    assert calls_a == [1]
    assert calls_b == [1]


def test_unsubscribe():
    """Test unsubscribing removes observer."""
    manager = TodoStateManager()
    calls = []

    def observer(todos):
        calls.append(len(todos))

    manager.subscribe(observer)
    manager.update_todos([TodoItem(id="1", content="Task 1")])
    assert calls == [1]

    manager.unsubscribe(observer)
    manager.update_todos([TodoItem(id="2", content="Task 2")])
    # No new notification
    assert calls == [1]


def test_clear_observers():
    """Test clearing all observers."""
    manager = TodoStateManager()
    calls = []

    def observer(todos):
        calls.append(len(todos))

    manager.subscribe(observer)
    manager.clear_observers()
    manager.update_todos([TodoItem(id="1", content="Task 1")])

    # No notifications after clear
    assert calls == []


def test_observer_exception_handling():
    """Test that observer errors don't break state management."""
    manager = TodoStateManager()
    calls = []

    def failing_observer(todos):
        raise ValueError("Observer error")

    def working_observer(todos):
        calls.append(len(todos))

    manager.subscribe(failing_observer)
    manager.subscribe(working_observer)

    # Should not raise, working observer should still be called
    manager.update_todos([TodoItem(id="1", content="Task 1")])
    assert calls == [1]


def test_global_singleton():
    """Test global todo_state singleton exists."""
    assert todo_state is not None
    assert isinstance(todo_state, TodoStateManager)


def test_duplicate_subscription_prevented():
    """Test that subscribing same callback twice doesn't duplicate."""
    manager = TodoStateManager()
    calls = []

    def observer(todos):
        calls.append(len(todos))

    manager.subscribe(observer)
    manager.subscribe(observer)  # Subscribe again

    manager.update_todos([TodoItem(id="1", content="Task 1")])

    # Should only be called once
    assert calls == [1]
