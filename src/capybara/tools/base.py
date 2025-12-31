from enum import Enum

from pydantic import BaseModel, Field


class ToolPermission(Enum):
    ALWAYS = "always"  # Auto-approve
    ASK = "ask"  # Prompt user
    NEVER = "never"  # Block


class AgentMode(str, Enum):
    """Agent execution mode."""

    PARENT = "parent"  # Full access
    CHILD = "child"  # Restricted (no todo/delegation)


class ToolSecurityConfig(BaseModel):
    permission: ToolPermission = ToolPermission.ASK
    allowlist: list[str] = []  # Auto-approve patterns (regex)
    denylist: list[str] = []  # Block patterns (regex)


class ToolRestriction(BaseModel):
    """Tool restrictions by agent mode."""

    allowed_modes: list[AgentMode] = Field(
        default_factory=lambda: [AgentMode.PARENT, AgentMode.CHILD]
    )
