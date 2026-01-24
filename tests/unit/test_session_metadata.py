"""Tests for session metadata collection."""

import pytest
from pathlib import Path
from capybara.core.utils.session_metadata import SessionMetadata, SessionMetadataCollector
import tempfile
import os


def test_session_metadata_dataclass():
    """Test SessionMetadata dataclass initialization and defaults."""
    metadata = SessionMetadata()

    # Check defaults
    assert metadata.total_turns == 0
    assert metadata.total_prompt_tokens == 0
    assert metadata.total_completion_tokens == 0
    assert metadata.total_cost == 0.0
    assert metadata.tool_calls_agreed == 0
    assert metadata.tool_calls_rejected == 0
    assert metadata.tool_calls_failed == 0
    assert metadata.tool_calls_succeeded == 0
    assert metadata.ended_at is None
    assert metadata.started_at is not None
    assert metadata.last_activity is not None


def test_session_metadata_to_dict():
    """Test converting metadata to dictionary."""
    metadata = SessionMetadata(
        git_commit="abc123",
        git_branch="main",
        working_directory="/path/to/project",
        total_turns=5,
    )

    data = metadata.to_dict()

    assert data["git"]["commit"] == "abc123"
    assert data["git"]["branch"] == "main"
    assert data["environment"]["working_directory"] == "/path/to/project"
    assert data["stats"]["total_turns"] == 5
    assert "timestamps" in data
    assert data["timestamps"]["ended_at"] is None


def test_session_metadata_from_dict():
    """Test creating metadata from dictionary."""
    data = {
        "git": {"commit": "abc123", "branch": "main", "status": "clean"},
        "environment": {
            "working_directory": "/test",
            "os": "macOS",
            "shell": "/bin/zsh",
            "python_version": "3.10.0",
        },
        "stats": {
            "total_turns": 10,
            "total_prompt_tokens": 1000,
            "total_completion_tokens": 500,
            "total_cost": 0.05,
            "tool_calls_agreed": 5,
            "tool_calls_rejected": 1,
            "tool_calls_failed": 0,
            "tool_calls_succeeded": 5,
        },
        "timestamps": {
            "started_at": "2026-01-06T10:00:00Z",
            "last_activity": "2026-01-06T10:30:00Z",
            "ended_at": "2026-01-06T10:30:00Z",
        },
    }

    metadata = SessionMetadata.from_dict(data)

    assert metadata.git_commit == "abc123"
    assert metadata.git_branch == "main"
    assert metadata.working_directory == "/test"
    assert metadata.total_turns == 10
    assert metadata.total_prompt_tokens == 1000
    assert metadata.ended_at == "2026-01-06T10:30:00Z"


def test_session_metadata_collector_initialization():
    """Test metadata collector initialization."""
    collector = SessionMetadataCollector(session_id="test-123")

    # Environment should be collected
    assert collector.metadata.os_name is not None
    assert collector.metadata.working_directory is not None
    assert collector.metadata.shell is not None
    assert collector.metadata.python_version is not None

    # Check Python version format
    assert "." in collector.metadata.python_version


def test_session_metadata_collector_git_in_repo():
    """Test git context collection in a git repository."""
    # Use the current project directory which is a git repo
    collector = SessionMetadataCollector(
        session_id="test-git",
        working_dir=Path.cwd(),
    )

    # Should have git info (this project is a git repo)
    assert collector.metadata.git_commit is not None
    assert collector.metadata.git_branch is not None
    assert len(collector.metadata.git_commit) > 0


def test_session_metadata_collector_git_not_in_repo():
    """Test git context collection in non-git directory."""
    # Create a temporary directory (not a git repo)
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = SessionMetadataCollector(
            session_id="test-no-git",
            working_dir=Path(tmpdir),
        )

        # Should gracefully handle missing git
        # Git fields will be None
        assert collector.metadata.git_commit is None or collector.metadata.git_commit == ""


def test_update_turn_stats():
    """Test updating turn statistics."""
    collector = SessionMetadataCollector(session_id="test-turns")

    initial_turns = collector.metadata.total_turns
    initial_tokens = collector.metadata.total_prompt_tokens

    collector.update_turn_stats(prompt_tokens=100, completion_tokens=50, cost=0.01)

    assert collector.metadata.total_turns == initial_turns + 1
    assert collector.metadata.total_prompt_tokens == initial_tokens + 100
    assert collector.metadata.total_completion_tokens == 50
    assert collector.metadata.total_cost == 0.01


def test_update_turn_stats_multiple():
    """Test updating turn statistics multiple times."""
    collector = SessionMetadataCollector(session_id="test-multiple")

    collector.update_turn_stats(prompt_tokens=100, completion_tokens=50, cost=0.01)
    collector.update_turn_stats(prompt_tokens=200, completion_tokens=100, cost=0.02)

    assert collector.metadata.total_turns == 2
    assert collector.metadata.total_prompt_tokens == 300
    assert collector.metadata.total_completion_tokens == 150
    assert collector.metadata.total_cost == 0.03


def test_update_tool_stats():
    """Test updating tool call statistics."""
    collector = SessionMetadataCollector(session_id="test-tools")

    collector.update_tool_stats(agreed=1, succeeded=1)
    assert collector.metadata.tool_calls_agreed == 1
    assert collector.metadata.tool_calls_succeeded == 1
    assert collector.metadata.tool_calls_rejected == 0
    assert collector.metadata.tool_calls_failed == 0

    collector.update_tool_stats(rejected=1)
    assert collector.metadata.tool_calls_rejected == 1

    collector.update_tool_stats(failed=1)
    assert collector.metadata.tool_calls_failed == 1


def test_mark_ended():
    """Test marking session as ended."""
    collector = SessionMetadataCollector(session_id="test-end")

    assert collector.metadata.ended_at is None

    collector.mark_ended()

    assert collector.metadata.ended_at is not None
    assert "T" in collector.metadata.ended_at  # ISO format


def test_get_metadata_dict():
    """Test getting metadata as dictionary."""
    collector = SessionMetadataCollector(session_id="test-dict")

    collector.update_turn_stats(prompt_tokens=100, completion_tokens=50, cost=0.01)
    collector.update_tool_stats(agreed=1, succeeded=1)

    data = collector.get_metadata_dict()

    assert isinstance(data, dict)
    assert "git" in data
    assert "environment" in data
    assert "stats" in data
    assert "timestamps" in data

    assert data["stats"]["total_turns"] == 1
    assert data["stats"]["tool_calls_agreed"] == 1


def test_metadata_round_trip():
    """Test converting metadata to dict and back."""
    collector = SessionMetadataCollector(session_id="test-roundtrip")

    collector.update_turn_stats(prompt_tokens=100, completion_tokens=50, cost=0.01)
    collector.update_tool_stats(agreed=2, succeeded=2)
    collector.mark_ended()

    # Convert to dict
    data = collector.get_metadata_dict()

    # Create new metadata from dict
    restored = SessionMetadata.from_dict(data)

    # Verify all fields preserved
    assert restored.total_turns == 1
    assert restored.total_prompt_tokens == 100
    assert restored.total_completion_tokens == 50
    assert restored.total_cost == 0.01
    assert restored.tool_calls_agreed == 2
    assert restored.tool_calls_succeeded == 2
    assert restored.ended_at is not None


def test_last_activity_updates():
    """Test that last_activity timestamp updates correctly."""
    collector = SessionMetadataCollector(session_id="test-activity")

    initial_activity = collector.metadata.last_activity

    # Small delay to ensure timestamp changes
    import time
    time.sleep(0.01)

    collector.update_turn_stats(prompt_tokens=100)

    # last_activity should have been updated
    assert collector.metadata.last_activity != initial_activity
    assert collector.metadata.last_activity > initial_activity
