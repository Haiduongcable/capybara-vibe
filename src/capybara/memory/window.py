"""Sliding window memory with token-based trimming."""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import tiktoken

logger = logging.getLogger("capybara.memory")


@dataclass
class MemoryConfig:
    """Configuration for conversation memory."""

    max_messages: Optional[int] = None
    max_tokens: int = 100_000
    model: str = "gpt-4o"  # For tokenizer selection


class ConversationMemory:
    """Sliding window memory with token counting."""

    def __init__(self, config: Optional[MemoryConfig] = None) -> None:
        self.config = config or MemoryConfig()
        self._messages: list[dict[str, Any]] = []
        self._system_prompt: Optional[dict[str, Any]] = None
        self._encoder = self._get_encoder()

    def _get_encoder(self) -> tiktoken.Encoding:
        """Get the appropriate tokenizer."""
        try:
            return tiktoken.encoding_for_model(self.config.model)
        except KeyError:
            return tiktoken.get_encoding("cl100k_base")

    def set_system_prompt(self, content: str) -> None:
        """Set the system prompt (always preserved)."""
        self._system_prompt = {"role": "system", "content": content}

    def add(self, message: dict[str, Any]) -> None:
        """Add a message to memory."""
        if message.get("role") == "system":
            self._system_prompt = message
        else:
            self._messages.append(message)
            self._trim()

    def add_batch(self, messages: list[dict[str, Any]]) -> None:
        """Add multiple messages to memory at once (more efficient than adding one by one).

        This is useful when loading messages from storage to avoid trimming after each message.
        Trimming only happens once after all messages are added.
        """
        for message in messages:
            if message.get("role") == "system":
                self._system_prompt = message
            else:
                self._messages.append(message)
        # Trim once after all messages are added
        self._trim()

    def _count_tokens(self, message: dict[str, Any]) -> int:
        """Count tokens in a message."""
        content = message.get("content", "")
        if content:
            return len(self._encoder.encode(content))

        # Handle tool calls
        tool_calls = message.get("tool_calls", [])
        tokens = 0
        for tc in tool_calls:
            if isinstance(tc, dict):
                func = tc.get("function", {})
                tokens += len(self._encoder.encode(func.get("name", "")))
                tokens += len(self._encoder.encode(func.get("arguments", "")))
        return tokens

    def _trim(self) -> None:
        """Trim messages to fit within limits while preserving message sequence integrity.

        Ensures that assistant messages with tool_calls and their corresponding tool
        results are removed together to prevent malformed message sequences.
        """
        # Capture initial state for logging
        initial_message_count = len(self._messages)
        initial_tokens = sum(self._count_tokens(m) for m in self._messages)
        if self._system_prompt:
            initial_tokens += self._count_tokens(self._system_prompt)

        trimmed_by_count = False
        trimmed_by_tokens = False

        # Trim by message count
        if self.config.max_messages and len(self._messages) > self.config.max_messages:
            before_count = len(self._messages)
            self._messages = self._messages[-self.config.max_messages :]
            removed_count = before_count - len(self._messages)
            trimmed_by_count = True
            logger.info(
                f"Memory trimmed by message count: removed {removed_count} messages "
                f"({before_count} → {len(self._messages)})"
            )

        # Trim by token count with message sequence awareness
        total_tokens = sum(self._count_tokens(m) for m in self._messages)
        if self._system_prompt:
            total_tokens += self._count_tokens(self._system_prompt)

        messages_removed_by_tokens = 0
        if total_tokens > self.config.max_tokens:
            logger.info(
                f"Memory trimming started: {total_tokens:,} tokens > {self.config.max_tokens:,} limit "
                f"({len(self._messages)} messages)"
            )

        while total_tokens > self.config.max_tokens and len(self._messages) > 1:
            # Find how many messages to remove while preserving sequence integrity
            messages_to_remove = self._find_removable_messages()

            if not messages_to_remove:
                # Can't safely remove any messages, stop trimming
                logger.warning(
                    f"Memory trimming stopped: cannot safely remove messages "
                    f"(still {total_tokens:,} tokens, {len(self._messages)} messages)"
                )
                break

            # Safety check: Don't remove if it would leave us with 0 messages
            if messages_to_remove >= len(self._messages):
                logger.warning(
                    f"Memory trimming stopped: would remove all messages "
                    f"(keeping at least 1 message even if over token limit)"
                )
                break

            # Remove messages and update token count
            for _ in range(messages_to_remove):
                if self._messages and len(self._messages) > 1:  # Keep at least 1
                    removed = self._messages.pop(0)
                    removed_tokens = self._count_tokens(removed)
                    total_tokens -= removed_tokens
                    messages_removed_by_tokens += 1
                    trimmed_by_tokens = True

        # After trimming, validate no orphaned tool messages remain at the start
        messages_before_cleanup = len(self._messages)
        self._remove_orphaned_tool_messages()
        orphaned_removed = messages_before_cleanup - len(self._messages)

        # Log final trimming summary
        final_message_count = len(self._messages)
        final_tokens = sum(self._count_tokens(m) for m in self._messages)
        if self._system_prompt:
            final_tokens += self._count_tokens(self._system_prompt)

        if trimmed_by_count or trimmed_by_tokens or orphaned_removed > 0:
            logger.info(
                f"Memory trimming complete: "
                f"tokens {initial_tokens:,} → {final_tokens:,}, "
                f"messages {initial_message_count} → {final_message_count} "
                f"(removed: {messages_removed_by_tokens} by tokens, {orphaned_removed} orphaned tools)"
            )

    def _remove_orphaned_tool_messages(self) -> None:
        """Remove any orphaned tool messages at the start of the message list.

        Tool messages at the start are invalid because they reference tool_calls
        from a previous assistant message that was removed during trimming.

        SAFETY: Always keeps at least 1 non-tool message to prevent empty message list.
        """
        # Safety valve: Keep removing orphaned tools but preserve at least 1 message
        while (self._messages and
               self._messages[0].get("role") == "tool" and
               len(self._messages) > 1):
            self._messages.pop(0)

    def _find_removable_messages(self) -> int:
        """Find how many messages can be safely removed from the front.

        Returns the number of messages that can be removed while maintaining
        valid message sequences (tool messages must follow tool_calls).

        Returns:
            Number of messages that can be safely removed (0 if none)
        """
        if not self._messages:
            return 0

        # Start with removing at least 1 message
        count = 1
        first_msg = self._messages[0]

        # If first message is assistant with tool_calls, must remove tool results too
        if (first_msg.get("role") == "assistant" and
            first_msg.get("tool_calls")):
            # Count consecutive tool messages following this assistant message
            idx = 1
            while idx < len(self._messages):
                if self._messages[idx].get("role") == "tool":
                    count += 1
                    idx += 1
                else:
                    break

        # If first message is a tool result, find its parent assistant message
        elif first_msg.get("role") == "tool":
            # This shouldn't happen in valid sequences, but handle it
            # Find all consecutive tool messages from the start
            idx = 0
            while idx < len(self._messages) and self._messages[idx].get("role") == "tool":
                count = idx + 1
                idx += 1

        return count

    def get_messages(self) -> list[dict[str, Any]]:
        """Get all messages including system prompt."""
        messages = []
        if self._system_prompt:
            messages.append(self._system_prompt)
        messages.extend(self._messages)
        return messages

    def clear(self) -> None:
        """Clear conversation history (keeps system prompt)."""
        self._messages = []

    def get_token_count(self) -> int:
        """Get current token count."""
        total = sum(self._count_tokens(m) for m in self._messages)
        if self._system_prompt:
            total += self._count_tokens(self._system_prompt)
        return total

    @property
    def message_count(self) -> int:
        """Get current message count (excluding system prompt)."""
        return len(self._messages)
