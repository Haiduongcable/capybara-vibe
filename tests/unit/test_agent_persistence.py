"""Tests for agent persistence integration (Phase 3)."""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from capybara.core.agent.agent import Agent, AgentConfig
from capybara.core.config.settings import PersistenceConfig, ToolsConfig
from capybara.memory.window import ConversationMemory
from capybara.tools.registry import ToolRegistry
from capybara.tools.base import AgentMode


def create_mock_litellm_response(content: str, tool_calls=None):
    """Create a mock LiteLLM response object."""
    response = MagicMock()
    choice = MagicMock()
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    choice.message = message
    response.choices = [choice]
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    return response


@pytest.fixture
def mock_storage():
    """Mock storage for testing."""
    storage = AsyncMock()
    storage.initialize = AsyncMock()
    storage.save_session_metadata = AsyncMock()
    storage.load_session_metadata = AsyncMock()
    return storage


@pytest.fixture
def mock_provider():
    """Mock provider for testing."""
    provider = Mock()
    provider.complete_non_streaming = AsyncMock(
        return_value=create_mock_litellm_response("Test response")
    )
    provider.api_logger = None
    return provider


@pytest.mark.asyncio
async def test_agent_initializes_persistence_for_parent():
    """Test that parent agents initialize persistence."""
    config = AgentConfig(mode=AgentMode.PARENT, stream=False)
    memory = ConversationMemory()
    tools = ToolRegistry()
    persistence_config = PersistenceConfig(enabled=True, save_metadata=True)

    agent = Agent(
        config=config,
        memory=memory,
        tools=tools,
        session_id="test-session",
        persistence_config=persistence_config,
    )

    # Parent agents should have storage and metadata collector
    assert agent.storage is not None
    assert agent.metadata_collector is not None
    assert agent.metadata_collector.session_id == "test-session"


@pytest.mark.asyncio
async def test_agent_no_persistence_for_child():
    """Test that child agents don't initialize persistence."""
    config = AgentConfig(mode=AgentMode.CHILD, stream=False)
    memory = ConversationMemory()
    tools = ToolRegistry()
    persistence_config = PersistenceConfig(enabled=True, save_metadata=True)

    agent = Agent(
        config=config,
        memory=memory,
        tools=tools,
        session_id="test-session",
        persistence_config=persistence_config,
    )

    # Child agents should not have storage or metadata collector
    assert agent.storage is None
    assert agent.metadata_collector is None


@pytest.mark.asyncio
async def test_agent_no_persistence_when_disabled():
    """Test that persistence is disabled when config says so."""
    config = AgentConfig(mode=AgentMode.PARENT, stream=False)
    memory = ConversationMemory()
    tools = ToolRegistry()
    persistence_config = PersistenceConfig(enabled=False)

    agent = Agent(
        config=config,
        memory=memory,
        tools=tools,
        session_id="test-session",
        persistence_config=persistence_config,
    )

    # Should not have storage when disabled
    assert agent.storage is None
    assert agent.metadata_collector is None


@pytest.mark.asyncio
async def test_agent_auto_save_after_turn(mock_storage, mock_provider):
    """Test that agent auto-saves metadata after each turn."""
    config = AgentConfig(mode=AgentMode.PARENT, stream=False, max_turns=1)
    memory = ConversationMemory()
    tools = ToolRegistry()
    persistence_config = PersistenceConfig(
        enabled=True, save_metadata=True, auto_save=True
    )

    agent = Agent(
        config=config,
        memory=memory,
        tools=tools,
        provider=mock_provider,
        session_id="test-session",
        persistence_config=persistence_config,
    )

    # Replace storage with mock
    agent.storage = mock_storage

    # Run agent
    response = await agent.run("Test input")

    # Verify storage was initialized
    mock_storage.initialize.assert_called_once()

    # Verify metadata was saved (after turn and on completion)
    assert mock_storage.save_session_metadata.call_count >= 1

    # Verify turn stats were updated
    assert agent.metadata_collector.metadata.total_turns == 1
    assert agent.metadata_collector.metadata.total_prompt_tokens == 100
    assert agent.metadata_collector.metadata.total_completion_tokens == 50

    # Verify session was marked as ended
    assert agent.metadata_collector.metadata.ended_at is not None


@pytest.mark.asyncio
async def test_agent_tracks_tool_stats(mock_storage):
    """Test that agent tracks tool statistics."""
    config = AgentConfig(mode=AgentMode.PARENT, stream=False, max_turns=2)
    memory = ConversationMemory()
    tools = ToolRegistry()
    persistence_config = PersistenceConfig(
        enabled=True, save_metadata=True, auto_save=True
    )

    # Mock provider that returns a tool call
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "test_tool"
    tool_call.function.arguments = "{}"

    provider = Mock()
    provider.complete_non_streaming = AsyncMock(
        side_effect=[
            create_mock_litellm_response("Using test tool", tool_calls=[tool_call]),
            create_mock_litellm_response("Done"),
        ]
    )
    provider.api_logger = None

    # Register a test tool
    def test_tool():
        return "success"

    tools.register(
        name="test_tool",
        func=test_tool,
        description="Test tool",
        parameters={"type": "object", "properties": {}},
    )

    agent = Agent(
        config=config,
        memory=memory,
        tools=tools,
        provider=provider,
        session_id="test-session",
        persistence_config=persistence_config,
    )

    # Replace storage with mock
    agent.storage = mock_storage

    # Inject metadata collector into tool executor
    agent.tool_executor.metadata_collector = agent.metadata_collector

    # Run agent
    response = await agent.run("Test input")

    # Verify tool stats were tracked
    metadata = agent.metadata_collector.metadata
    assert metadata.tool_calls_agreed >= 1  # Tool was agreed
    assert metadata.tool_calls_succeeded >= 1  # Tool succeeded


@pytest.mark.asyncio
async def test_agent_saves_metadata_on_error(mock_storage, mock_provider):
    """Test that metadata is saved even when agent encounters error."""
    config = AgentConfig(mode=AgentMode.PARENT, stream=False, max_turns=1)
    memory = ConversationMemory()
    tools = ToolRegistry()
    persistence_config = PersistenceConfig(
        enabled=True, save_metadata=True, auto_save=True
    )

    # Mock provider that raises error
    error_provider = Mock()
    error_provider.complete_non_streaming = AsyncMock(side_effect=RuntimeError("Test error"))
    error_provider.api_logger = None

    agent = Agent(
        config=config,
        memory=memory,
        tools=tools,
        provider=error_provider,
        session_id="test-session",
        persistence_config=persistence_config,
    )

    # Replace storage with mock
    agent.storage = mock_storage

    # Run agent and expect error
    with pytest.raises(RuntimeError):
        await agent.run("Test input")

    # Verify metadata was still saved
    assert mock_storage.save_session_metadata.call_count >= 1

    # Verify session was marked as ended
    assert agent.metadata_collector.metadata.ended_at is not None


@pytest.mark.asyncio
async def test_metadata_includes_git_and_environment():
    """Test that metadata includes git and environment info."""
    config = AgentConfig(mode=AgentMode.PARENT, stream=False)
    memory = ConversationMemory()
    tools = ToolRegistry()
    persistence_config = PersistenceConfig(
        enabled=True,
        save_metadata=True,
        collect_git=True,
        collect_environment=True,
    )

    agent = Agent(
        config=config,
        memory=memory,
        tools=tools,
        session_id="test-session",
        persistence_config=persistence_config,
    )

    # Get metadata dict
    metadata = agent.metadata_collector.get_metadata_dict()

    # Verify structure
    assert "git" in metadata
    assert "environment" in metadata
    assert "stats" in metadata
    assert "timestamps" in metadata

    # Verify environment fields are collected
    assert metadata["environment"]["working_directory"] is not None
    assert metadata["environment"]["os"] is not None
    assert metadata["environment"]["shell"] is not None
    assert metadata["environment"]["python_version"] is not None
