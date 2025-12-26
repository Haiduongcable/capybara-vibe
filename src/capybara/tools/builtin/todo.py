from __future__ import annotations

import json
from typing import Any, List, Optional
from enum import Enum
from pydantic import BaseModel
from capybara.tools.registry import ToolRegistry

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
_TODOS: List[TodoItem] = []

def get_todos() -> List[TodoItem]:
    """Get current list of todos (read-only copy)."""
    return list(_TODOS)

# --- Tool Implementation ---

def register_todo_tool(registry: ToolRegistry) -> None:
    """Register todo tool with the registry."""

    @registry.tool(
        name="todo",
        description="Manage a task list. Use this to track progress on complex multi-step tasks. You can 'read' current todos or 'write' to update the list.",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write"],
                    "description": "Action to perform: 'read' to view todos, 'write' to update them."
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
                                "enum": ["pending", "in_progress", "completed", "cancelled"]
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high"]
                            }
                        },
                        "required": ["id", "content"]
                    },
                    "description": "List of todos to save (required for 'write' action)."
                }
            },
            "required": ["action"]
        }
    )
    async def todo(action: str, todos: Optional[List[dict[str, Any]]] = None) -> str:
        """Manage the todo list."""
        global _TODOS
        
        if action == "read":
            return json.dumps({
                "message": f"Retrieved {len(_TODOS)} todos",
                "todos": [t.model_dump() for t in _TODOS],
                "total_count": len(_TODOS)
            }, indent=2)
            
        elif action == "write":
            if todos is None:
                return "Error: 'todos' list is required for write action."
                
            try:
                # Validate and parse
                new_list = [TodoItem(**item) for item in todos]
                
                # Check uniqueness of IDs
                ids = [t.id for t in new_list]
                if len(ids) != len(set(ids)):
                    return "Error: Todo IDs must be unique."
                    
                # Update state
                _TODOS = new_list
                
                return json.dumps({
                    "message": f"Updated {len(_TODOS)} todos",
                    "todos": [t.model_dump() for t in _TODOS],
                    "total_count": len(_TODOS)
                }, indent=2)
                
            except Exception as e:
                return f"Error updating todos: {e}"
                
        else:
            return f"Error: Unknown action '{action}'"
