"""Tests for conversation memory."""

import pytest
from capybara.memory.window import ConversationMemory, MemoryConfig


class TestConversationMemory:
    """Test ConversationMemory functionality."""

    def test_add_message(self) -> None:
        """Test adding messages."""
        memory = ConversationMemory()
        memory.add({"role": "user", "content": "Hello"})
        memory.add({"role": "assistant", "content": "Hi there!"})

        messages = memory.get_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_system_prompt(self) -> None:
        """Test system prompt handling."""
        memory = ConversationMemory()
        memory.set_system_prompt("You are a helpful assistant.")
        memory.add({"role": "user", "content": "Hello"})

        messages = memory.get_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_prompt_preserved_on_clear(self) -> None:
        """Test that system prompt is preserved when clearing."""
        memory = ConversationMemory()
        memory.set_system_prompt("System prompt")
        memory.add({"role": "user", "content": "Hello"})
        memory.clear()

        messages = memory.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "system"

    def test_message_limit_trimming(self) -> None:
        """Test trimming by message count."""
        config = MemoryConfig(max_messages=3)
        memory = ConversationMemory(config=config)

        for i in range(5):
            memory.add({"role": "user", "content": f"Message {i}"})

        assert memory.message_count == 3
        messages = memory.get_messages()
        assert messages[0]["content"] == "Message 2"

    def test_token_limit_trimming(self) -> None:
        """Test trimming by token count."""
        config = MemoryConfig(max_tokens=100)
        memory = ConversationMemory(config=config)

        # Add messages until we exceed limit
        for i in range(10):
            memory.add({"role": "user", "content": f"This is message number {i} with some content."})

        # Should have trimmed old messages
        assert memory.get_token_count() <= 100

    def test_token_counting(self) -> None:
        """Test token counting."""
        memory = ConversationMemory()
        memory.add({"role": "user", "content": "Hello world"})

        # Token count should be positive
        assert memory.get_token_count() > 0

    def test_tool_call_token_counting(self) -> None:
        """Test token counting with tool calls."""
        memory = ConversationMemory()
        memory.add({
            "role": "assistant",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path": "/test.txt"}'
                }
            }]
        })

        # Should count tool call tokens
        assert memory.get_token_count() > 0
