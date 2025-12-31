"""Agent status tracking for UI rendering."""

from dataclasses import dataclass, field
from enum import Enum


class AgentState(str, Enum):
    """Agent execution states."""

    IDLE = "idle"
    THINKING = "thinking"  # LLM generating response
    EXECUTING_TOOLS = "executing"  # Running tool calls
    WAITING_FOR_CHILD = "waiting"  # Delegated, awaiting child
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentStatus:
    """Current agent status for UI rendering."""

    session_id: str
    mode: str  # "parent" or "child"
    state: AgentState
    current_action: str | None = None  # "Running grep", "Delegating task", etc.
    child_sessions: list[str] = field(default_factory=list)
    parent_session: str | None = None
