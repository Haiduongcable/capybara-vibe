"""Pytest configuration and fixtures."""

import pytest
from capybara.tools.registry import ToolRegistry
from capybara.memory.window import ConversationMemory, MemoryConfig


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Create a fresh tool registry."""
    return ToolRegistry()


@pytest.fixture
def memory() -> ConversationMemory:
    """Create a conversation memory instance."""
    return ConversationMemory(config=MemoryConfig(max_tokens=10000))
