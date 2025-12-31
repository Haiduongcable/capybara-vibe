"""Todo state management with observer pattern for UI updates."""

from __future__ import annotations

from collections.abc import Callable

from capybara.tools.builtin.todo import TodoItem


class TodoStateManager:
    """Manages global todo state and notifies observers of changes.

    Uses observer pattern to decouple state management from UI rendering.
    Observers are called synchronously in the main thread (asyncio-safe).
    """

    def __init__(self) -> None:
        self._todos: list[TodoItem] = []
        self._observers: list[Callable[[list[TodoItem]], None]] = []

    def get_todos(self) -> list[TodoItem]:
        """Get current todo list (read-only copy)."""
        return list(self._todos)

    def update_todos(self, new_todos: list[TodoItem]) -> None:
        """Update state and notify all observers.

        Args:
            new_todos: New todo list to replace current state
        """
        self._todos = list(new_todos)
        self._notify()

    def subscribe(self, callback: Callable[[list[TodoItem]], None]) -> None:
        """Subscribe to state changes.

        Args:
            callback: Function to call when todos change. Receives List[TodoItem].
        """
        if callback not in self._observers:
            self._observers.append(callback)

    def unsubscribe(self, callback: Callable[[list[TodoItem]], None]) -> None:
        """Unsubscribe from state changes.

        Args:
            callback: Previously subscribed callback to remove
        """
        if callback in self._observers:
            self._observers.remove(callback)

    def clear_observers(self) -> None:
        """Remove all observers (cleanup on exit)."""
        self._observers.clear()

    def _notify(self) -> None:
        """Notify all observers of state change."""
        for callback in self._observers:
            try:
                callback(self._todos)
            except Exception as e:
                # Don't let observer errors break state management
                # Log error but continue notifying other observers
                import logging

                logging.getLogger(__name__).error(f"Error in todo state observer: {e}")


# Global singleton instance
todo_state = TodoStateManager()
