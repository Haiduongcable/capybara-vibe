"""Tests for session metadata storage."""

import pytest
from pathlib import Path
from capybara.memory.storage import ConversationStorage
import aiosqlite
import tempfile
import os


@pytest.fixture
async def storage():
    """Create a temporary storage instance for testing."""
    # Use a temporary file for testing
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_fd)

    storage = ConversationStorage(db_path=Path(temp_path))
    await storage.initialize()

    yield storage

    # Cleanup
    try:
        os.unlink(temp_path)
    except (FileNotFoundError, PermissionError, OSError):
        pass


@pytest.mark.asyncio
async def test_metadata_column_migration(storage):
    """Test that metadata column is added on init."""
    # Verify column exists
    async with aiosqlite.connect(storage.db_path) as db:
        cursor = await db.execute("PRAGMA table_info(sessions)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        assert "metadata" in column_names


@pytest.mark.asyncio
async def test_save_and_load_metadata(storage):
    """Test saving and loading metadata."""
    # Create session
    session_id = "test-session-123"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # Save metadata
    metadata = {
        "git": {"commit": "abc123", "branch": "main"},
        "stats": {"total_turns": 5, "total_prompt_tokens": 1000},
    }
    await storage.save_session_metadata(session_id, metadata)

    # Load metadata
    loaded = await storage.load_session_metadata(session_id)
    assert loaded is not None
    assert loaded["git"]["commit"] == "abc123"
    assert loaded["stats"]["total_turns"] == 5


@pytest.mark.asyncio
async def test_load_nonexistent_metadata(storage):
    """Test loading metadata for session without metadata."""
    # Create session without metadata
    session_id = "test-no-metadata"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # Load should return None
    loaded = await storage.load_session_metadata(session_id)
    assert loaded is None


@pytest.mark.asyncio
async def test_metadata_update(storage):
    """Test updating existing metadata."""
    session_id = "test-update"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # Save initial metadata
    metadata_v1 = {"stats": {"total_turns": 1}}
    await storage.save_session_metadata(session_id, metadata_v1)

    # Update metadata
    metadata_v2 = {"stats": {"total_turns": 5}}
    await storage.save_session_metadata(session_id, metadata_v2)

    # Load should return updated version
    loaded = await storage.load_session_metadata(session_id)
    assert loaded["stats"]["total_turns"] == 5


@pytest.mark.asyncio
async def test_metadata_with_complex_structure(storage):
    """Test saving and loading complex metadata structure."""
    session_id = "test-complex"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # Save complex metadata matching the planned structure
    metadata = {
        "git": {
            "commit": "664eed6abc",
            "branch": "master",
            "status": "clean"
        },
        "environment": {
            "working_directory": "/path/to/project",
            "os": "macOS",
            "shell": "/bin/zsh",
            "python_version": "3.10.0"
        },
        "stats": {
            "total_turns": 5,
            "total_prompt_tokens": 12000,
            "total_completion_tokens": 3000,
            "total_cost": 0.045,
            "tool_calls_agreed": 8,
            "tool_calls_rejected": 0,
            "tool_calls_failed": 1,
            "tool_calls_succeeded": 7
        },
        "timestamps": {
            "started_at": "2026-01-06T16:20:30.123456Z",
            "last_activity": "2026-01-06T16:25:45.654321Z",
            "ended_at": None
        }
    }
    await storage.save_session_metadata(session_id, metadata)

    # Load and verify all fields
    loaded = await storage.load_session_metadata(session_id)
    assert loaded is not None
    assert loaded["git"]["commit"] == "664eed6abc"
    assert loaded["environment"]["os"] == "macOS"
    assert loaded["stats"]["total_turns"] == 5
    assert loaded["stats"]["tool_calls_agreed"] == 8
    assert loaded["timestamps"]["ended_at"] is None


@pytest.mark.asyncio
async def test_migration_idempotency(storage):
    """Test that running migration multiple times is safe."""
    # Initialize again (should be safe)
    await storage._init_db()

    # Verify column still exists and is usable
    session_id = "test-idempotent"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    metadata = {"test": "data"}
    await storage.save_session_metadata(session_id, metadata)

    loaded = await storage.load_session_metadata(session_id)
    assert loaded == {"test": "data"}


@pytest.mark.asyncio
async def test_backward_compatibility(storage):
    """Test that existing sessions without metadata work correctly."""
    # Create session (metadata will be NULL)
    session_id = "test-backward-compat"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # Should be able to load session
    messages = await storage.load_session(session_id)
    assert messages == []  # No messages yet

    # Metadata should be None
    metadata = await storage.load_session_metadata(session_id)
    assert metadata is None

    # Should be able to save metadata later
    new_metadata = {"added": "later"}
    await storage.save_session_metadata(session_id, new_metadata)

    loaded = await storage.load_session_metadata(session_id)
    assert loaded == {"added": "later"}


@pytest.mark.asyncio
async def test_save_nonexistent_session(storage):
    """Test saving metadata for nonexistent session raises error."""
    with pytest.raises(RuntimeError, match="not found"):
        await storage.save_session_metadata("nonexistent-id", {"test": "data"})


@pytest.mark.asyncio
async def test_json_serialization_error(storage):
    """Test that non-serializable objects raise ValueError."""
    from datetime import datetime

    session_id = "test-json-error"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # datetime objects are not JSON serializable by default
    metadata = {"timestamp": datetime.now()}

    with pytest.raises(ValueError, match="not JSON-serializable"):
        await storage.save_session_metadata(session_id, metadata)


@pytest.mark.asyncio
async def test_metadata_size_limit(storage):
    """Test that metadata exceeding 1MB raises ValueError."""
    session_id = "test-size-limit"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # Create metadata larger than 1MB
    large_metadata = {"data": "x" * 1_100_000}  # >1MB

    with pytest.raises(ValueError, match="too large"):
        await storage.save_session_metadata(session_id, large_metadata)


@pytest.mark.asyncio
async def test_corrupted_json_load(storage):
    """Test that corrupted JSON in database raises ValueError."""
    session_id = "test-corrupted"
    await storage.create_session(session_id, model="gpt-4o", title="Test")

    # Manually insert corrupted JSON into database
    import aiosqlite
    async with aiosqlite.connect(storage.db_path) as db:
        await db.execute(
            "UPDATE sessions SET metadata = ? WHERE id = ?",
            ("{invalid json}", session_id),
        )
        await db.commit()

    # Loading should raise ValueError
    with pytest.raises(ValueError, match="Corrupted metadata"):
        await storage.load_session_metadata(session_id)
