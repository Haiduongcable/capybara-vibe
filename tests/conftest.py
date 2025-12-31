"""Pytest configuration and fixtures."""

import pytest

from capybara.memory.window import ConversationMemory, MemoryConfig
from capybara.tools.registry import ToolRegistry


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Create a fresh tool registry."""
    return ToolRegistry()


@pytest.fixture
def memory() -> ConversationMemory:
    """Create a conversation memory instance."""
    return ConversationMemory(config=MemoryConfig(max_tokens=10000))
