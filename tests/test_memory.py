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

    def test_message_sequence_integrity_on_trim(self) -> None:
        """Test that assistant messages with tool_calls and tool results are removed together."""
        config = MemoryConfig(max_tokens=200)
        memory = ConversationMemory(config=config)

        # Add user message
        memory.add({"role": "user", "content": "Read a file"})

        # Add assistant with tool_calls
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

        # Add tool result
        memory.add({
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "File contents here"
        })

        # Add more messages to trigger trimming
        for i in range(10):
            memory.add({"role": "user", "content": f"Another message {i} with enough content to trigger token limit trimming eventually."})

        # Verify no orphaned tool messages exist
        messages = memory.get_messages()
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool":
                # There should be a preceding assistant message with tool_calls
                assert i > 0, "Tool message found at start of messages (orphaned)"
                # Search backwards for assistant with tool_calls
                found_parent = False
                for j in range(i - 1, -1, -1):
                    if messages[j].get("role") == "assistant" and messages[j].get("tool_calls"):
                        found_parent = True
                        break
                assert found_parent, f"Tool message at index {i} has no parent assistant with tool_calls"

    def test_trimming_preserves_valid_sequence(self) -> None:
        """Test that trimming maintains valid message sequences."""
        config = MemoryConfig(max_tokens=150)
        memory = ConversationMemory(config=config)

        # Create a sequence: user → assistant with tool_calls → tool results
        memory.add({"role": "user", "content": "Message 1"})
        memory.add({
            "role": "assistant",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "test", "arguments": "{}"}
            }]
        })
        memory.add({"role": "tool", "tool_call_id": "call_1", "content": "Result 1"})

        # Add another complete sequence
        memory.add({"role": "user", "content": "Message 2"})
        memory.add({
            "role": "assistant",
            "tool_calls": [{
                "id": "call_2",
                "type": "function",
                "function": {"name": "test", "arguments": "{}"}
            }]
        })
        memory.add({"role": "tool", "tool_call_id": "call_2", "content": "Result 2"})

        # Add more messages to force trimming
        for i in range(5):
            memory.add({"role": "user", "content": f"Long message {i} " * 20})

        # Get final messages
        messages = memory.get_messages()

        # Verify that if there's an assistant with tool_calls, its tool results are present
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Check that following messages include corresponding tool results
                tool_call_ids = {tc["id"] for tc in msg["tool_calls"]}
                # Look for tool results in following messages
                found_results = set()
                for j in range(i + 1, len(messages)):
                    if messages[j].get("role") == "tool":
                        found_results.add(messages[j].get("tool_call_id"))
                    elif messages[j].get("role") in ("user", "assistant"):
                        # Stop looking after next user/assistant message
                        break

                # All tool calls should have results (or all should be missing if trimmed)
                # For this test, we expect complete sequences if they're present
                if found_results:
                    # If we found some results, we should find all of them
                    assert found_results == tool_call_ids, \
                        f"Incomplete tool results: expected {tool_call_ids}, found {found_results}"

    def test_find_removable_messages(self) -> None:
        """Test _find_removable_messages helper."""
        memory = ConversationMemory()

        # Test 1: Single user message
        memory.add({"role": "user", "content": "Hello"})
        assert memory._find_removable_messages() == 1

        # Test 2: Assistant with tool_calls followed by tool results
        memory.clear()
        memory.add({
            "role": "assistant",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "test", "arguments": "{}"}
            }]
        })
        memory.add({"role": "tool", "tool_call_id": "call_1", "content": "Result"})
        # Should remove both assistant and tool message
        assert memory._find_removable_messages() == 2

        # Test 3: Assistant with multiple tool results
        memory.clear()
        memory.add({
            "role": "assistant",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "test1", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "test2", "arguments": "{}"}}
            ]
        })
        memory.add({"role": "tool", "tool_call_id": "call_1", "content": "Result 1"})
        memory.add({"role": "tool", "tool_call_id": "call_2", "content": "Result 2"})
        # Should remove assistant + 2 tool messages
        assert memory._find_removable_messages() == 3

    def test_remove_orphaned_tool_messages(self) -> None:
        """Test that orphaned tool messages at the start are removed."""
        memory = ConversationMemory()

        # Manually create a scenario with orphaned tool messages
        # (simulating what could happen after trimming)
        memory._messages = [
            {"role": "tool", "tool_call_id": "call_1", "content": "Orphaned result 1"},
            {"role": "tool", "tool_call_id": "call_2", "content": "Orphaned result 2"},
            {"role": "user", "content": "Hello"},
        ]

        # Call the cleanup method
        memory._remove_orphaned_tool_messages()

        # Should have removed the orphaned tool messages
        messages = memory.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_batch_add_prevents_incremental_trimming(self) -> None:
        """Test that add_batch is more efficient and prevents orphaned messages during load."""
        config = MemoryConfig(max_tokens=200)
        memory = ConversationMemory(config=config)

        # Create messages that would cause issues if added one by one
        messages_to_load = [
            {"role": "user", "content": "Read a file"},
            {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "/test.txt"}'
                    }
                }]
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "File contents here"
            },
            {"role": "user", "content": "Now do something else with a very long message " * 20},
        ]

        # Use batch add
        memory.add_batch(messages_to_load)

        # Verify no orphaned tool messages exist
        final_messages = memory.get_messages()
        for i, msg in enumerate(final_messages):
            if msg.get("role") == "tool":
                # Should not be at the start
                assert i > 0, "Tool message found at start (orphaned)"

    def test_orphaned_tool_message_removal_during_session_load(self) -> None:
        """Test the specific bug: orphaned tool messages after loading session and trimming."""
        config = MemoryConfig(max_tokens=150)
        memory = ConversationMemory(config=config)

        # Simulate a stored session with tool calls
        stored_messages = [
            {"role": "user", "content": "Old message 1"},
            {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_old",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "old.txt"}'}
                }]
            },
            {"role": "tool", "tool_call_id": "call_old", "content": "Old file contents"},
            {"role": "user", "content": "Recent message " * 30},  # Long message to trigger trim
        ]

        # Load using batch add (which should handle trimming correctly)
        memory.add_batch(stored_messages)

        # Get messages and verify structure
        messages = memory.get_messages()

        # First message should NOT be a tool message
        if messages:
            assert messages[0].get("role") != "tool", \
                "First message is orphaned tool message - this is the bug we're fixing!"

    def test_trim_removes_orphaned_tools_after_token_limit(self) -> None:
        """Test that trimming by token limit properly removes orphaned tool messages."""
        config = MemoryConfig(max_tokens=100)
        memory = ConversationMemory(config=config)

        # Add a sequence that will be trimmed
        memory.add({"role": "user", "content": "First"})
        memory.add({
            "role": "assistant",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]
        })
        memory.add({"role": "tool", "tool_call_id": "call_1", "content": "Result"})

        # Add a very long message to force trimming
        memory.add({"role": "user", "content": "Very long message that will cause trimming " * 50})

        # Verify no orphaned tool messages
        messages = memory.get_messages()
        if messages and messages[0].get("role") == "tool":
            pytest.fail("Found orphaned tool message at start after trimming")

    def test_safety_valve_prevents_all_messages_deletion(self) -> None:
        """Test that safety valve keeps at least 1 message even if all are orphaned tools."""
        config = MemoryConfig(max_tokens=150)
        memory = ConversationMemory(config=config)

        # Simulate the bug scenario: aggressive trimming leaves only tool messages
        memory.add({"role": "user", "content": "Read files"})
        memory.add({
            "role": "assistant",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "file1.txt"}'}},
                {"id": "call_2", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "file2.txt"}'}},
                {"id": "call_3", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "file3.txt"}'}},
            ]
        })
        # Add large tool results to trigger aggressive trimming
        memory.add({"role": "tool", "tool_call_id": "call_1", "content": "Large file content " * 100})
        memory.add({"role": "tool", "tool_call_id": "call_2", "content": "Large file content " * 100})
        memory.add({"role": "tool", "tool_call_id": "call_3", "content": "Large file content " * 100})

        # Get messages - safety valve should keep at least 1
        messages = memory.get_messages()

        # Should have system + at least 1 message
        assert len(messages) >= 2, "Safety valve failed: all messages were deleted"

        # Count non-system messages
        non_system = [m for m in messages if m.get("role") != "system"]
        assert len(non_system) >= 1, "Safety valve failed: no non-system messages remain"

    def test_safety_valve_with_only_tool_messages(self) -> None:
        """Test edge case: memory has only tool messages after trimming."""
        memory = ConversationMemory()

        # Manually create scenario with only orphaned tool messages
        memory._messages = [
            {"role": "tool", "tool_call_id": "call_1", "content": "Result 1"},
            {"role": "tool", "tool_call_id": "call_2", "content": "Result 2"},
            {"role": "tool", "tool_call_id": "call_3", "content": "Result 3"},
        ]

        # Trigger cleanup
        memory._remove_orphaned_tool_messages()

        # Should keep at least 1 message (the last tool message)
        messages = memory.get_messages()
        non_system = [m for m in messages if m.get("role") != "system"]
        assert len(non_system) == 1, f"Expected 1 message, got {len(non_system)}"
        assert non_system[0].get("role") == "tool", "Last message should be a tool message"

    def test_logging_during_trimming(self, caplog) -> None:
        """Test that trimming operations are logged."""
        import logging
        caplog.set_level(logging.INFO, logger="capybara.memory")

        config = MemoryConfig(max_tokens=200)
        memory = ConversationMemory(config=config)

        # Add messages that will trigger trimming
        memory.add({"role": "user", "content": "Message 1"})
        memory.add({"role": "assistant", "content": "Response 1"})
        memory.add({"role": "user", "content": "Very long message " * 100})

        # Check that trimming was logged
        log_messages = [record.message for record in caplog.records]
        trimming_logs = [msg for msg in log_messages if "Memory trimming" in msg]

        assert len(trimming_logs) > 0, "No trimming logs found"

        # Verify log contains key information
        summary_log = [msg for msg in trimming_logs if "trimming complete" in msg]
        if summary_log:
            # Check that summary contains token counts
            assert "tokens" in summary_log[0].lower()
            assert "messages" in summary_log[0].lower()
