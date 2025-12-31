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


class TodoPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TodoItem(BaseModel):
    id: str
    content: str
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM


# --- State ---

# In-memory storage for the session
_TODOS: list[TodoItem] = []


def get_todos() -> list[TodoItem]:
    """Get current list of todos (read-only copy)."""
    return list(_TODOS)


# --- Tool Implementation ---


def register_todo_tool(registry: ToolRegistry) -> None:
    """Register todo tool with the registry."""

    @registry.tool(
        name="todo",
        description=(
            "Manage a task list for complex multi-step tasks. Actions:\n"
            "- 'write': Create NEW todo list (only when no existing todos or all completed)\n"
            "- 'read': View current todos\n"
            "- 'update': Update specific todo by id (status, content, priority)\n"
            "- 'complete': Mark todo as completed (shorthand for update)\n"
            "- 'delete': Clear entire todo list (when plan changes)"
        ),
        allowed_modes=[AgentMode.PARENT],
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "update", "complete", "delete"],
                    "description": (
                        "Action: 'write' (create new list), 'read' (view), "
                        "'update' (modify todo), 'complete' (mark done), 'delete' (clear all)"
                    ),
                },
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
                            },
                            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                        "required": ["id", "content"],
                    },
                    "description": "List of todos (required for 'write' action).",
                },
                "id": {
                    "type": "string",
                    "description": "Todo ID (required for 'update' and 'complete' actions).",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                    "description": "New status (optional for 'update' action).",
                },
                "content": {
                    "type": "string",
                    "description": "New content (optional for 'update' action).",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "New priority (optional for 'update' action).",
                },
            },
            "required": ["action"],
        },
    )
    async def todo(
        action: str,
        todos: list[dict[str, Any]] | None = None,
        id: str | None = None,
        status: str | None = None,
        content: str | None = None,
        priority: str | None = None,
    ) -> str:
        """Manage the todo list."""
        global _TODOS

        if action == "read":
            return json.dumps(
                {
                    "message": f"Retrieved {len(_TODOS)} todos",
                    "todos": [t.model_dump() for t in _TODOS],
                    "total_count": len(_TODOS),
                },
                indent=2,
            )

        elif action == "write":
            # VALIDATION: Can only write when list is empty or all completed
            if _TODOS:
                all_completed = all(t.status == TodoStatus.COMPLETED for t in _TODOS)
                if not all_completed:
                    pending_count = sum(1 for t in _TODOS if t.status != TodoStatus.COMPLETED)
                    return (
                        f"Error: Cannot create new todo list while {pending_count} tasks are still pending. "
                        f"You must either:\n"
                        f"  1. Complete all current tasks, OR\n"
                        f"  2. Call todo(action='delete') to clear the current list first.\n"
                        f"Use todo(action='update', id='...', status='...') to modify existing todos."
                    )

            if todos is None:
                return "Error: 'todos' list is required for write action."

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
                        "total_count": len(_TODOS),
                    },
                    indent=2,
                )

            except Exception as e:
                return f"Error creating todos: {e}"

        elif action == "update":
            if not _TODOS:
                return "Error: No todos exist. Use todo(action='write', todos=[...]) to create a list first."

            if id is None:
                return "Error: 'id' parameter is required for update action."

            # Find todo by ID
            todo_to_update = None
            todo_index = -1
            for i, t in enumerate(_TODOS):
                if t.id == id:
                    todo_to_update = t
                    todo_index = i
                    break

            if todo_to_update is None:
                available_ids = [t.id for t in _TODOS]
                return f"Error: Todo with id='{id}' not found. Available IDs: {available_ids}"

            try:
                # Build update dict with only provided fields
                update_data = {"id": id, "content": todo_to_update.content}

                if status is not None:
                    update_data["status"] = status
                else:
                    update_data["status"] = todo_to_update.status.value

                if content is not None:
                    update_data["content"] = content

                if priority is not None:
                    update_data["priority"] = priority
                else:
                    update_data["priority"] = todo_to_update.priority.value

                # Create updated todo
                updated_todo = TodoItem(**update_data)  # type: ignore

                # VALIDATION: Check in_progress constraint
                new_list = _TODOS.copy()
                new_list[todo_index] = updated_todo

                in_progress_tasks = [t for t in new_list if t.status == TodoStatus.IN_PROGRESS]
                if len(in_progress_tasks) > 1:
                    in_progress_ids = [t.id for t in in_progress_tasks]
                    return (
                        f"Error: Only 1 task can be 'in_progress' at a time. "
                        f"Found {len(in_progress_tasks)} tasks would be in_progress: {in_progress_ids}. "
                        f"Complete the current task before starting another."
                    )

                # Apply update
                _TODOS[todo_index] = updated_todo

                # Notify state manager
                _notify_state_change(_TODOS)

                return json.dumps(
                    {
                        "message": f"Updated todo '{id}'",
                        "todo": updated_todo.model_dump(),
                        "total_count": len(_TODOS),
                    },
                    indent=2,
                )

            except Exception as e:
                return f"Error updating todo '{id}': {e}"

        elif action == "complete":
            if not _TODOS:
                return "Error: No todos exist. Use todo(action='write', todos=[...]) to create a list first."

            if id is None:
                return "Error: 'id' parameter is required for complete action."

            # Find and complete todo
            todo_to_complete = None
            todo_index = -1
            for i, t in enumerate(_TODOS):
                if t.id == id:
                    todo_to_complete = t
                    todo_index = i
                    break

            if todo_to_complete is None:
                available_ids = [t.id for t in _TODOS]
                return f"Error: Todo with id='{id}' not found. Available IDs: {available_ids}"

            try:
                # Mark as completed
                completed_todo = TodoItem(
                    id=todo_to_complete.id,
                    content=todo_to_complete.content,
                    status=TodoStatus.COMPLETED,
                    priority=todo_to_complete.priority,
                )

                _TODOS[todo_index] = completed_todo

                # Notify state manager
                _notify_state_change(_TODOS)

                completed_count = sum(1 for t in _TODOS if t.status == TodoStatus.COMPLETED)
                return json.dumps(
                    {
                        "message": f"Completed todo '{id}' ({completed_count}/{len(_TODOS)} done)",
                        "todo": completed_todo.model_dump(),
                        "total_count": len(_TODOS),
                        "completed_count": completed_count,
                    },
                    indent=2,
                )

            except Exception as e:
                return f"Error completing todo '{id}': {e}"

        elif action == "delete":
            if not _TODOS:
                return "No todos to delete."

            count = len(_TODOS)
            _TODOS.clear()

            # Notify state manager
            _notify_state_change([])

            return json.dumps(
                {"message": f"Deleted {count} todos. Todo list cleared.", "total_count": 0},
                indent=2,
            )

        else:
            return f"Error: Unknown action '{action}'. Valid actions: read, write, update, complete, delete"


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
