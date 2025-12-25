"""Tests for tool registry."""

import pytest
from capybara.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


class TestToolRegistry:
    """Test ToolRegistry functionality."""

    def test_register_sync_tool(self, registry: ToolRegistry) -> None:
        """Test registering a sync function."""

        @registry.tool(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
        )
        def sync_tool() -> str:
            return "sync result"

        assert "test_tool" in registry.list_tools()
        assert len(registry.schemas) == 1
        assert registry.schemas[0]["function"]["name"] == "test_tool"

    def test_register_async_tool(self, registry: ToolRegistry) -> None:
        """Test registering an async function."""

        @registry.tool(
            name="async_tool",
            description="An async test tool",
            parameters={"type": "object", "properties": {}},
        )
        async def async_tool() -> str:
            return "async result"

        assert "async_tool" in registry.list_tools()

    @pytest.mark.asyncio
    async def test_execute_tool(self, registry: ToolRegistry) -> None:
        """Test executing a registered tool."""

        @registry.tool(
            name="greet",
            description="Greet someone",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        result = await registry.execute("greet", {"name": "World"})
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry: ToolRegistry) -> None:
        """Test executing an unknown tool."""
        result = await registry.execute("unknown", {})
        assert "Error: Unknown tool" in result

    @pytest.mark.asyncio
    async def test_execute_tool_with_error(self, registry: ToolRegistry) -> None:
        """Test executing a tool that raises an error."""

        @registry.tool(
            name="failing",
            description="A failing tool",
            parameters={"type": "object", "properties": {}},
        )
        def failing() -> str:
            raise ValueError("Something went wrong")

        result = await registry.execute("failing", {})
        assert "Error: ValueError:" in result

    def test_schema_format(self, registry: ToolRegistry) -> None:
        """Test that schemas are in OpenAI format."""

        @registry.tool(
            name="test",
            description="Test tool",
            parameters={
                "type": "object",
                "properties": {"arg": {"type": "string"}},
                "required": ["arg"],
            },
        )
        def test_fn(arg: str) -> str:
            return arg

        schema = registry.schemas[0]
        assert schema["type"] == "function"
        assert "function" in schema
        assert schema["function"]["name"] == "test"
        assert schema["function"]["description"] == "Test tool"
        assert "$schema" in schema["function"]["parameters"]
