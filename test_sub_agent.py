"""Test sub_agent tool refactor and API key propagation fix."""

import asyncio
import sys

sys.path.insert(0, 'src')

from capybara.core.agent import Agent, AgentConfig
from capybara.core.delegation.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory, MemoryConfig
from capybara.providers.router import ProviderRouter
from capybara.tools.base import AgentMode
from capybara.tools.builtin import register_builtin_tools
from capybara.tools.builtin.delegation import register_sub_agent_tool
from capybara.tools.registry import ToolRegistry
from rich.console import Console


async def test_sub_agent_registration():
    """Test 1: Verify sub_agent tool is registered correctly."""
    print("\n=== Test 1: Sub-Agent Registration ===")

    # Create mock dependencies
    storage = ConversationStorage()
    await storage.initialize()
    session_manager = SessionManager(storage)

    import uuid
    parent_session_id = str(uuid.uuid4())
    await storage.create_session(
        session_id=parent_session_id,
        model="test-model",
        title="Test Parent Session"
    )

    # Create parent agent
    tools = ToolRegistry()
    register_builtin_tools(tools)

    memory = ConversationMemory(config=MemoryConfig())
    provider = ProviderRouter(default_model="test-model")
    console = Console()

    parent_agent = Agent(
        config=AgentConfig(model="test-model", mode=AgentMode.PARENT),
        memory=memory,
        tools=tools,
        console=console,
        provider=provider,
        session_id=parent_session_id
    )

    # Register sub_agent
    register_sub_agent_tool(
        tools,
        parent_session_id=parent_session_id,
        parent_agent=parent_agent,
        session_manager=session_manager,
        storage=storage
    )

    # Verify registration
    all_tools = tools.list_tools()
    assert 'sub_agent' in all_tools, "sub_agent not registered"
    print("✅ sub_agent tool registered")

    # Verify tool details
    tool_func = tools.get_tool('sub_agent')
    assert tool_func is not None, "sub_agent function is None"
    print("✅ sub_agent function accessible")

    # Verify filtering by mode
    parent_tools = tools.filter_by_mode(AgentMode.PARENT)
    assert 'sub_agent' in parent_tools.list_tools(), "sub_agent not in PARENT mode"
    print("✅ sub_agent available to PARENT mode")

    child_tools = tools.filter_by_mode(AgentMode.CHILD)
    assert 'sub_agent' not in child_tools.list_tools(), "sub_agent should NOT be in CHILD mode"
    print("✅ sub_agent correctly excluded from CHILD mode")

    # Storage cleanup (no close method needed)
    print("\n✅ Test 1 PASSED: Registration working correctly\n")


async def test_api_key_inheritance():
    """Test 2: Verify sub-agent inherits parent's provider (API keys)."""
    print("\n=== Test 2: API Key Inheritance ===")

    # Create parent agent with custom provider
    storage = ConversationStorage()
    await storage.initialize()
    session_manager = SessionManager(storage)

    import uuid
    parent_session_id = str(uuid.uuid4())
    await storage.create_session(
        session_id=parent_session_id,
        model="test-model",
        title="Test Parent Session"
    )

    tools = ToolRegistry()
    register_builtin_tools(tools)

    memory = ConversationMemory(config=MemoryConfig())

    # Custom provider to track
    custom_provider = ProviderRouter(default_model="test-model")
    custom_provider._test_marker = "PARENT_PROVIDER"  # Mark for tracking

    console = Console()

    parent_agent = Agent(
        config=AgentConfig(model="test-model", mode=AgentMode.PARENT),
        memory=memory,
        tools=tools,
        console=console,
        provider=custom_provider,
        session_id=parent_session_id
    )

    # Import agent setup to verify provider inheritance
    from capybara.tools.builtin.delegation.agent_setup import create_sub_agent

    child_session_id = await session_manager.create_child_session(
        parent_id=parent_session_id,
        model="test-model",
        prompt="Test task",
        title="Test Child"
    )

    child_agent = create_sub_agent(
        parent_agent=parent_agent,
        child_session_id=child_session_id,
        parent_session_id=parent_session_id,
        timeout=60.0
    )

    # Verify child uses parent's provider
    assert child_agent.provider is custom_provider, "Child agent did not inherit parent provider"
    assert hasattr(child_agent.provider, '_test_marker'), "Provider not the same instance"
    assert child_agent.provider._test_marker == "PARENT_PROVIDER", "Wrong provider instance"
    print("✅ Child agent inherits parent's provider (API keys)")

    # Storage cleanup (no close method needed)
    print("\n✅ Test 2 PASSED: API key inheritance working\n")


async def test_tool_schema():
    """Test 3: Verify sub_agent tool has correct schema."""
    print("\n=== Test 3: Tool Schema Validation ===")

    storage = ConversationStorage()
    await storage.initialize()
    session_manager = SessionManager(storage)

    import uuid
    parent_session_id = str(uuid.uuid4())
    await storage.create_session(
        session_id=parent_session_id,
        model="test-model",
        title="Test Parent Session"
    )

    tools = ToolRegistry()
    register_builtin_tools(tools)

    memory = ConversationMemory(config=MemoryConfig())
    provider = ProviderRouter(default_model="test-model")
    console = Console()

    parent_agent = Agent(
        config=AgentConfig(model="test-model", mode=AgentMode.PARENT),
        memory=memory,
        tools=tools,
        console=console,
        provider=provider,
        session_id=parent_session_id
    )

    register_sub_agent_tool(
        tools,
        parent_session_id=parent_session_id,
        parent_agent=parent_agent,
        session_manager=session_manager,
        storage=storage
    )

    # Get schema
    schemas = tools.schemas
    sub_agent_schema = next(
        (s for s in schemas if s['function']['name'] == 'sub_agent'),
        None
    )

    assert sub_agent_schema is not None, "sub_agent schema not found"
    print("✅ sub_agent schema exists")

    # Verify schema structure
    func_def = sub_agent_schema['function']
    assert 'name' in func_def, "Missing name in schema"
    assert func_def['name'] == 'sub_agent', "Wrong tool name"
    print("✅ Tool name is 'sub_agent'")

    assert 'description' in func_def, "Missing description"
    assert 'autonomous' in func_def['description'].lower(), "Description doesn't mention autonomous work"
    print("✅ Description mentions autonomous work")

    assert 'parameters' in func_def, "Missing parameters"
    params = func_def['parameters']['properties']

    assert 'task' in params, "Missing 'task' parameter"
    assert params['task']['type'] == 'string', "Task parameter not string"
    print("✅ 'task' parameter defined correctly")

    assert 'timeout' in params, "Missing 'timeout' parameter"
    assert params['timeout']['type'] == 'number', "Timeout parameter not number"
    assert params['timeout']['default'] == 180.0, "Wrong default timeout"
    print("✅ 'timeout' parameter defined correctly (default: 180s)")

    assert 'task' in func_def['parameters']['required'], "'task' not marked as required"
    print("✅ 'task' marked as required")

    # Storage cleanup (no close method needed)
    print("\n✅ Test 3 PASSED: Tool schema correct\n")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("SUB-AGENT REFACTOR VALIDATION TESTS")
    print("="*60)

    try:
        await test_sub_agent_registration()
        await test_api_key_inheritance()
        await test_tool_schema()

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nSummary:")
        print("- ✅ sub_agent tool registered and accessible")
        print("- ✅ API key inheritance working (child uses parent's provider)")
        print("- ✅ Tool schema correct (task required, timeout=180s default)")
        print("- ✅ PARENT mode has sub_agent, CHILD mode does not")
        print("\n")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
