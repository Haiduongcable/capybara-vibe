"""Sliding window memory with token-based trimming."""

from dataclasses import dataclass, field
from typing import Any, Optional

import tiktoken


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
        """Trim messages to fit within limits."""
        # Trim by message count
        if self.config.max_messages and len(self._messages) > self.config.max_messages:
            self._messages = self._messages[-self.config.max_messages :]

        # Trim by token count
        total_tokens = sum(self._count_tokens(m) for m in self._messages)
        if self._system_prompt:
            total_tokens += self._count_tokens(self._system_prompt)

        while total_tokens > self.config.max_tokens and len(self._messages) > 1:
            removed = self._messages.pop(0)
            total_tokens -= self._count_tokens(removed)

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
