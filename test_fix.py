#!/usr/bin/env python3
"""Test the CLI tool registration fix."""

import asyncio
from capybara.core.agent import Agent, AgentConfig
from capybara.core.session_manager import SessionManager
from capybara.memory.storage import ConversationStorage
from capybara.memory.window import ConversationMemory
from capybara.tools.base import AgentMode
from capybara.tools.builtin import register_builtin_tools
from capybara.tools.registry import ToolRegistry

async def test_cli_initialization():
    """Simulate the fixed CLI initialization flow."""
    print("=== Testing Fixed CLI Initialization ===\n")

    # Simulate the FIXED initialization from interactive.py
    session_id = "test_session"

    # Step 1: Initialize storage and session manager BEFORE agent
    storage = ConversationStorage()
    await storage.initialize()
    session_manager = SessionManager(storage)

    # Step 2: Setup tools registry BEFORE agent creation
    tools = ToolRegistry()
    register_builtin_tools(
        tools,
        parent_session_id=session_id,
        parent_agent=None,  # Placeholder
        session_manager=session_manager,
        storage=storage
    )

    # Step 3: Filter tools by mode
    filtered_tools = tools.filter_by_mode(AgentMode.PARENT)

    print(f"Tools registered: {len(filtered_tools._tools)}")
    print(f"Tool names: {list(filtered_tools._tools.keys())}\n")

    # Step 4: Create agent with FULL registry
    agent_config = AgentConfig(model="gpt-4", stream=False, mode=AgentMode.PARENT)
    memory = ConversationMemory()
    memory.add({"role": "system", "content": "Test"})

    agent = Agent(
        config=agent_config,
        memory=memory,
        tools=filtered_tools,  # FULL registry, not empty!
        session_id=session_id
    )

    # Step 5: Verify tool_executor has tools
    print("=== Verification ===")
    print(f"Agent.tools: {len(agent.tools._tools)} tools")
    print(f"Agent.tool_executor.tools: {len(agent.tool_executor.tools._tools)} tools")
    print()

    # Check specific tools
    critical_tools = ['todo', 'list_directory', 'read_file', 'write_file', 'bash']
    print("Critical tools check:")
    for tool_name in critical_tools:
        in_agent = tool_name in agent.tools._tools
        in_executor = tool_name in agent.tool_executor.tools._tools
        status = "✅" if (in_agent and in_executor) else "❌"
        print(f"  {status} {tool_name}: agent={in_agent}, executor={in_executor}")

    # Test tool execution
    print("\n=== Test Tool Execution ===")
    try:
        # Try executing list_directory (should work now)
        result = await agent.tool_executor.tools.execute("list_directory", {"path": "."})
        print(f"✅ list_directory executed successfully")
        print(f"   Result preview: {result[:100]}...")
    except Exception as e:
        print(f"❌ Tool execution failed: {e}")

    print("\n=== FIX VERIFICATION ===")
    if len(agent.tool_executor.tools._tools) > 0:
        print("✅ FIX SUCCESSFUL - Tools accessible in executor!")
    else:
        print("❌ FIX FAILED - Executor still has empty registry!")

if __name__ == "__main__":
    asyncio.run(test_cli_initialization())
