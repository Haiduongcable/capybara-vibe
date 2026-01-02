from __future__ import annotations

import json
from enum import Enum

# Import state manager for UI integration
# Circular import is safe because todo_state.py only imports TodoItem
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from capybara.tools.base import AgentMode
from capybara.tools.registry import ToolRegistry

if TYPE_CHECKING:
    pass

# --- Data Models ---


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoItem(BaseModel):
    id: str
    content: str
    status: TodoStatus = TodoStatus.PENDING


# --- State ---

# In-memory storage for the session
_TODOS: list[TodoItem] = []


def get_todos() -> list[TodoItem]:
    """Get current list of todos (read-only copy)."""
    return list(_TODOS)


# --- Tool Implementation ---


def register_todo_tool(registry: ToolRegistry) -> None:
    """Register todo tools with the registry."""

    @registry.tool(
        name="write_todo",
        description=(
            "Create a NEW todo list. "
            "Can only be used when the current list is empty or all tasks are completed. "
            "If tasks remain, you must complete them or use delete_todo() first."
        ),
        allowed_modes=[AgentMode.PARENT],
        parameters={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                "default": "pending",
                            },
                        },
                        "required": ["id", "content"],
                    },
                    "description": "List of todos to create.",
                },
            },
            "required": ["todos"],
        },
    )
    async def write_todo(todos: list[dict[str, Any]]) -> str:
        """Create a new todo list."""
        global _TODOS

        # VALIDATION: Can only write when list is empty or all completed
        if _TODOS:
            all_completed = all(t.status == TodoStatus.COMPLETED for t in _TODOS)
            if not all_completed:
                pending_count = sum(1 for t in _TODOS if t.status != TodoStatus.COMPLETED)
                return (
                    f"Error: Cannot create new todo list while {pending_count} tasks are still pending. "
                    f"You must either:\n"
                    f"  1. Complete all current tasks, OR\n"
                    f"  2. Call delete_todo() to clear the current list first.\n"
                    f"Use update_todo_status(id='...', status='...') to modify existing todos."
                )

        try:
            # Validate and parse
            new_list = [TodoItem(**item) for item in todos]

            # Check uniqueness of IDs
            ids = [t.id for t in new_list]
            if len(ids) != len(set(ids)):
                return "Error: Todo IDs must be unique."

            # CRITICAL: Enforce sequential execution - only 1 task can be in_progress
            in_progress_tasks = [t for t in new_list if t.status == TodoStatus.IN_PROGRESS]
            if len(in_progress_tasks) > 1:
                in_progress_ids = [t.id for t in in_progress_tasks]
                return (
                    f"Error: Only 1 task can be 'in_progress' at a time. "
                    f"Found {len(in_progress_tasks)} tasks in_progress: {in_progress_ids}. "
                    f"Complete the current task before starting another."
                )

            # Update state
            _TODOS = new_list

            # Notify state manager for UI updates
            _notify_state_change(new_list)

            return json.dumps(
                {
                    "message": f"Created {len(_TODOS)} todos",
                    "todos": [t.model_dump() for t in _TODOS],
                },
                indent=2,
            )

        except Exception as e:
            return f"Error creating todos: {e}"

    @registry.tool(
        name="read_todo",
        description="View the current todo list.",
        allowed_modes=[AgentMode.PARENT],
        parameters={"type": "object", "properties": {}, "required": []},
    )
    async def read_todo() -> str:
        """Read the current todo list."""
        return json.dumps(
            {
                "message": f"Retrieved {len(_TODOS)} todos",
                "todos": [t.model_dump() for t in _TODOS],
            },
            indent=2,
        )

    @registry.tool(
        name="update_todo_status",
        description="Update the status of a specific todo item.",
        allowed_modes=[AgentMode.PARENT],
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The ID of the todo to update."},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                    "description": "The new status.",
                },
            },
            "required": ["id", "status"],
        },
    )
    async def update_todo_status(id: str, status: str) -> str:
        """Update a todo's status."""
        global _TODOS

        if not _TODOS:
            return "Error: No todos exist. Use write_todo(...) to create a list first."

        # Find todo by ID
        todo_index = -1
        todo_to_update = None
        for i, t in enumerate(_TODOS):
            if t.id == id:
                todo_to_update = t
                todo_index = i
                break

        if todo_to_update is None:
            available_ids = [t.id for t in _TODOS]
            return f"Error: Todo with id='{id}' not found. Available IDs: {available_ids}"

        # Prevent updating already completed tasks (unless moving FROM completed, but usually not intended)
        # User constraint: "don't update for processed task (old task)"
        # But maybe they want to reopen? Assuming strict "don't update processed" means if it's completed, don't touch.
        # However, the user might want to correct a mistake. Let's strictly follow "don't update for processed task"
        if todo_to_update.status == TodoStatus.COMPLETED or todo_to_update.status == TodoStatus.CANCELLED:
             return f"Error: Cannot update todo '{id}' because it is already {todo_to_update.status.value}. Use write_todo to start new tasks if needed."

        try:
            # Validate in_progress constraint if we are setting to in_progress
            if status == TodoStatus.IN_PROGRESS and todo_to_update.status != TodoStatus.IN_PROGRESS:
                current_in_progress = [t for t in _TODOS if t.status == TodoStatus.IN_PROGRESS]
                if current_in_progress:
                     return (
                        f"Error: Only 1 task can be 'in_progress' at a time. "
                        f"Task '{current_in_progress[0].id}' is currently in_progress. "
                        f"Complete or cancel it before starting '{id}'."
                    )

            # Update the status
            new_status = TodoStatus(status)
            updated_todo = todo_to_update.model_copy(update={"status": new_status})
            
            _TODOS[todo_index] = updated_todo

            # Notify state manager
            _notify_state_change(_TODOS)

            return json.dumps(
                {
                    "message": f"Updated todo '{id}' status to '{status}'",
                    "todo": updated_todo.model_dump(),
                },
                indent=2,
            )

        except ValueError:
             return f"Error: Invalid status '{status}'."
        except Exception as e:
            return f"Error updating todo '{id}': {e}"

    @registry.tool(
        name="delete_todo",
        description="Delete the entire todo list. Use this when the plan changes completely.",
        allowed_modes=[AgentMode.PARENT],
        parameters={"type": "object", "properties": {}, "required": []},
    )
    async def delete_todo() -> str:
        """Delete all todos."""
        global _TODOS
        count = len(_TODOS)
        _TODOS = []
        
        # Notify state manager
        _notify_state_change([])

        return json.dumps(
            {"message": f"Deleted {count} todos. Todo list cleared."},
            indent=2,
        )


def _notify_state_change(todos: list[TodoItem]) -> None:
    """Notify state manager of todo changes for UI updates.

    Lazy import to avoid circular dependency issues.
    """
    try:
        from capybara.tools.builtin.todo_state import todo_state

        todo_state.update_todos(todos)
    except ImportError:
        # State manager not available, skip notification
        pass
