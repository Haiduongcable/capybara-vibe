"""Session metadata collection utilities."""

import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SessionMetadata:
    """Session metadata structure."""

    # Git context
    git_commit: str | None = None
    git_branch: str | None = None
    git_status: str | None = None

    # Environment
    working_directory: str | None = None
    os_name: str | None = None
    shell: str | None = None
    python_version: str | None = None

    # Statistics (will be updated during session)
    total_turns: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0

    # Tool call statistics
    tool_calls_agreed: int = 0
    tool_calls_rejected: int = 0
    tool_calls_failed: int = 0
    tool_calls_succeeded: int = 0

    # Timestamps
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "git": {
                "commit": self.git_commit,
                "branch": self.git_branch,
                "status": self.git_status,
            },
            "environment": {
                "working_directory": self.working_directory,
                "os": self.os_name,
                "shell": self.shell,
                "python_version": self.python_version,
            },
            "stats": {
                "total_turns": self.total_turns,
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
                "total_cost": self.total_cost,
                "tool_calls_agreed": self.tool_calls_agreed,
                "tool_calls_rejected": self.tool_calls_rejected,
                "tool_calls_failed": self.tool_calls_failed,
                "tool_calls_succeeded": self.tool_calls_succeeded,
            },
            "timestamps": {
                "started_at": self.started_at,
                "last_activity": self.last_activity,
                "ended_at": self.ended_at,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMetadata":
        """Create from dictionary (JSON deserialization)."""
        git = data.get("git", {})
        env = data.get("environment", {})
        stats = data.get("stats", {})
        timestamps = data.get("timestamps", {})

        return cls(
            git_commit=git.get("commit"),
            git_branch=git.get("branch"),
            git_status=git.get("status"),
            working_directory=env.get("working_directory"),
            os_name=env.get("os"),
            shell=env.get("shell"),
            python_version=env.get("python_version"),
            total_turns=stats.get("total_turns", 0),
            total_prompt_tokens=stats.get("total_prompt_tokens", 0),
            total_completion_tokens=stats.get("total_completion_tokens", 0),
            total_cost=stats.get("total_cost", 0.0),
            tool_calls_agreed=stats.get("tool_calls_agreed", 0),
            tool_calls_rejected=stats.get("tool_calls_rejected", 0),
            tool_calls_failed=stats.get("tool_calls_failed", 0),
            tool_calls_succeeded=stats.get("tool_calls_succeeded", 0),
            started_at=timestamps.get("started_at", datetime.now(timezone.utc).isoformat()),
            last_activity=timestamps.get(
                "last_activity", datetime.now(timezone.utc).isoformat()
            ),
            ended_at=timestamps.get("ended_at"),
        )


class SessionMetadataCollector:
    """Collects and manages session metadata."""

    def __init__(self, session_id: str, working_dir: Path | None = None):
        """Initialize metadata collector.

        Args:
            session_id: Session ID
            working_dir: Working directory (default: current directory)
        """
        self.session_id = session_id
        self.working_dir = working_dir or Path.cwd()
        self.metadata = SessionMetadata()

        # Collect static metadata on init
        self._collect_environment()
        self._collect_git_context()

    def _collect_environment(self) -> None:
        """Collect environment information."""
        self.metadata.working_directory = str(self.working_dir)

        platform_map = {
            "win32": "Windows",
            "darwin": "macOS",
            "linux": "Linux",
        }
        self.metadata.os_name = platform_map.get(sys.platform, "Unix-like")

        if sys.platform == "win32":
            self.metadata.shell = os.environ.get("COMSPEC", "cmd.exe")
        else:
            self.metadata.shell = os.environ.get("SHELL", "/bin/sh")

        self.metadata.python_version = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

    def _collect_git_context(self) -> None:
        """Collect git repository context with timeout."""
        try:
            # Get current commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                self.metadata.git_commit = result.stdout.strip()

            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                self.metadata.git_branch = result.stdout.strip()

            # Get git status (short)
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                status = result.stdout.strip()
                self.metadata.git_status = status if status else "clean"
        except Exception:
            # Git not available or not a repo - graceful fallback
            pass

    def update_turn_stats(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Update statistics after a conversation turn.

        Args:
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens generated
            cost: Cost of this turn in USD
        """
        self.metadata.total_turns += 1
        self.metadata.total_prompt_tokens += prompt_tokens
        self.metadata.total_completion_tokens += completion_tokens
        self.metadata.total_cost += cost
        self.metadata.last_activity = datetime.now(timezone.utc).isoformat()

    def update_tool_stats(
        self,
        agreed: int = 0,
        rejected: int = 0,
        failed: int = 0,
        succeeded: int = 0,
    ) -> None:
        """Update tool call statistics.

        Args:
            agreed: Number of tool calls approved by user
            rejected: Number of tool calls rejected by user
            failed: Number of tool calls that failed
            succeeded: Number of tool calls that succeeded
        """
        self.metadata.tool_calls_agreed += agreed
        self.metadata.tool_calls_rejected += rejected
        self.metadata.tool_calls_failed += failed
        self.metadata.tool_calls_succeeded += succeeded
        self.metadata.last_activity = datetime.now(timezone.utc).isoformat()

    def mark_ended(self) -> None:
        """Mark session as ended."""
        self.metadata.ended_at = datetime.now(timezone.utc).isoformat()

    def get_metadata_dict(self) -> dict[str, Any]:
        """Get metadata as dictionary for JSON serialization."""
        return self.metadata.to_dict()
