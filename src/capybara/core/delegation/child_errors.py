"""Structured failure handling for child agents."""

from dataclasses import dataclass
from enum import Enum


class FailureCategory(str, Enum):
    """Child agent failure classifications."""

    TIMEOUT = "timeout"  # Needs more time
    MISSING_CONTEXT = "missing_context"  # Insufficient info in prompt
    TOOL_ERROR = "tool_error"  # External tool/dependency failed
    INVALID_TASK = "invalid_task"  # Task impossible/unclear
    PARTIAL_SUCCESS = "partial"  # Some work done, hit blocker


@dataclass
class ChildFailure:
    """Structured failure report from child agent."""

    category: FailureCategory
    message: str
    session_id: str
    duration: float

    # Partial progress
    completed_steps: list[str]
    files_modified: list[str]

    # Recovery guidance
    blocked_on: str | None
    suggested_retry: bool
    suggested_actions: list[str]

    # Execution context
    tool_usage: dict[str, int]
    last_successful_tool: str | None

    def to_context_string(self) -> str:
        """Format for parent LLM context."""
        actions = "\n  ".join(f"• {a}" for a in self.suggested_actions)
        completed = (
            "\n  ".join(f"✓ {s}" for s in self.completed_steps)
            if self.completed_steps
            else "  None"
        )

        blocked_section = f"\nBlocked on: {self.blocked_on}\n" if self.blocked_on else "\n"

        return f"""Child agent failed: {self.message}

Category: {self.category.value}
Duration: {self.duration:.1f}s
Retryable: {"Yes" if self.suggested_retry else "No"}

Work completed before failure:
  {completed}

Files modified: {", ".join(self.files_modified) if self.files_modified else "none"}{blocked_section}
Suggested recovery actions:
  {actions}

<task_metadata>
  <session_id>{self.session_id}</session_id>
  <status>failed</status>
  <failure_category>{self.category.value}</failure_category>
  <retryable>{"true" if self.suggested_retry else "false"}</retryable>
</task_metadata>"""
