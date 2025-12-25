"""Tests for conversation storage."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from capybara.memory.storage import ConversationStorage


@pytest.fixture
def temp_db() -> Path:
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def storage(temp_db: Path) -> ConversationStorage:
    """Create a storage instance with temp database."""
    return ConversationStorage(db_path=temp_db)


class TestConversationStorage:
    """Test ConversationStorage functionality."""

    @pytest.mark.asyncio
    async def test_create_session(self, storage: ConversationStorage) -> None:
        """Test creating a session."""
        session_id = str(uuid4())
        await storage.create_session(session_id, "gpt-4o", "Test Session")

        sessions = await storage.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == session_id
        assert sessions[0]["title"] == "Test Session"
        assert sessions[0]["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_save_and_load_messages(self, storage: ConversationStorage) -> None:
        """Test saving and loading messages."""
        session_id = str(uuid4())
        await storage.create_session(session_id, "gpt-4o")

        # Save messages
        await storage.save_message(session_id, {"role": "user", "content": "Hello"})
        await storage.save_message(session_id, {"role": "assistant", "content": "Hi!"})

        # Load messages
        messages = await storage.load_session(session_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi!"

    @pytest.mark.asyncio
    async def test_save_tool_calls(self, storage: ConversationStorage) -> None:
        """Test saving messages with tool calls."""
        session_id = str(uuid4())
        await storage.create_session(session_id, "gpt-4o")

        tool_msg = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "/test"}'},
                }
            ],
        }
        await storage.save_message(session_id, tool_msg)

        messages = await storage.load_session(session_id)
        assert len(messages) == 1
        assert "tool_calls" in messages[0]
        assert messages[0]["tool_calls"][0]["function"]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_delete_session(self, storage: ConversationStorage) -> None:
        """Test deleting a session."""
        session_id = str(uuid4())
        await storage.create_session(session_id, "gpt-4o")
        await storage.save_message(session_id, {"role": "user", "content": "Hello"})

        await storage.delete_session(session_id)

        sessions = await storage.list_sessions()
        assert len(sessions) == 0

        messages = await storage.load_session(session_id)
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_update_session_title(self, storage: ConversationStorage) -> None:
        """Test updating session title."""
        session_id = str(uuid4())
        await storage.create_session(session_id, "gpt-4o", "Original")

        await storage.update_session_title(session_id, "Updated Title")

        sessions = await storage.list_sessions()
        assert sessions[0]["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_list_sessions_ordering(self, storage: ConversationStorage) -> None:
        """Test that sessions are ordered by updated_at."""
        id1 = str(uuid4())
        id2 = str(uuid4())

        await storage.create_session(id1, "gpt-4o", "First")
        await storage.create_session(id2, "gpt-4o", "Second")

        # Update first session
        await storage.save_message(id1, {"role": "user", "content": "Update"})

        sessions = await storage.list_sessions()
        assert sessions[0]["id"] == id1  # Most recently updated
        assert sessions[1]["id"] == id2
