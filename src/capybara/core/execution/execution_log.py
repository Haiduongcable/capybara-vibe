"""Execution tracking for child agent operations."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolExecution:
    """Single tool call record."""
    tool_name: str
    args: dict
    result_summary: str  # First 200 chars
    success: bool
    duration: float
    timestamp: str


@dataclass
class FileOperation:
    """File modification record."""
    path: str
    operation: str  # "read", "write", "edit"
    lines_changed: Optional[int] = None


@dataclass
class ExecutionLog:
    """Comprehensive child agent execution log."""
    files_read: set[str] = field(default_factory=set)
    files_written: set[str] = field(default_factory=set)
    files_edited: set[str] = field(default_factory=set)
    tool_executions: list[ToolExecution] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (tool, error_msg)

    @property
    def files_modified(self) -> set[str]:
        """All files written or edited."""
        return self.files_written | self.files_edited

    @property
    def tool_usage_summary(self) -> dict[str, int]:
        """Count of each tool used."""
        return dict(Counter(te.tool_name for te in self.tool_executions))

    @property
    def success_rate(self) -> float:
        """Percentage of successful tool calls."""
        if not self.tool_executions:
            return 1.0
        successes = sum(1 for te in self.tool_executions if te.success)
        return successes / len(self.tool_executions)
