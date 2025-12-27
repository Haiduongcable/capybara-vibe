#!/usr/bin/env python3
"""Debug script to check tool registration."""

import asyncio
from capybara.tools.registry import ToolRegistry
from capybara.tools.builtin import register_builtin_tools
from capybara.tools.base import AgentMode

async def main():
    # Test 1: Basic registration
    print("=== Test 1: Basic Tool Registration ===")
    tools = ToolRegistry()
    register_builtin_tools(tools)

    print(f"Total tools registered: {len(tools._tools)}")
    print(f"Tool names: {list(tools._tools.keys())}")
    print()

    # Test 2: Filtered registry for PARENT mode
    print("=== Test 2: Filtered Registry (PARENT mode) ===")
    filtered = tools.filter_by_mode(AgentMode.PARENT)
    print(f"Filtered tools: {len(filtered._tools)}")
    print(f"Filtered tool names: {list(filtered._tools.keys())}")
    print()

    # Test 3: Check specific tools
    print("=== Test 3: Check Specific Tools ===")
    check_tools = ['todo', 'list_directory', 'read_file', 'write_file']
    for tool_name in check_tools:
        in_original = tool_name in tools._tools
        in_filtered = tool_name in filtered._tools
        print(f"{tool_name}: original={in_original}, filtered={in_filtered}")
    print()

    # Test 4: Check schemas
    print("=== Test 4: Check Schemas ===")
    print(f"Original schemas: {len(tools._schemas)}")
    print(f"Filtered schemas: {len(filtered._schemas)}")
    for schema in filtered._schemas:
        print(f"  - {schema['function']['name']}")

if __name__ == "__main__":
    asyncio.run(main())
