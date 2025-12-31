"""MCP bridge for integrating MCP tools into the tool registry."""

from typing import Any

from capybara.core.config import MCPConfig
from capybara.tools.mcp.client import MCPClient
from capybara.tools.registry import ToolRegistry


class MCPBridge:
    """Bridge between MCP servers and the tool registry."""

    def __init__(self, config: MCPConfig) -> None:
        self.config = config
        self._clients: dict[str, MCPClient] = {}

    async def connect_all(self) -> int:
        """Connect to all configured MCP servers.

        Returns:
            Number of successfully connected servers
        """
        if not self.config.enabled:
            return 0

        connected = 0
        for name, server_config in self.config.servers.items():
            client = MCPClient(name, server_config)
            if await client.connect():
                self._clients[name] = client
                connected += 1

        return connected

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Get all tools from connected MCP servers."""
        tools = []
        for client in self._clients.values():
            tools.extend(client.tools)
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call an MCP tool by its prefixed name.

        Args:
            tool_name: Tool name with server prefix (e.g., "server__tool")
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        # Find which server owns this tool
        for name, client in self._clients.items():
            if tool_name.startswith(f"{name}__"):
                return await client.call_tool(tool_name, arguments)

        return f"Error: No MCP server found for tool '{tool_name}'"

    def register_with_registry(self, registry: ToolRegistry) -> int:
        """Register all MCP tools with a tool registry.

        Args:
            registry: Tool registry to register with

        Returns:
            Number of tools registered
        """
        count = 0
        for _, client in self._clients.items():
            for tool_schema in client.tools:
                tool_name = tool_schema["function"]["name"]

                # Create wrapper function for this tool with proper closure
                def make_wrapper(captured_name: str):
                    async def call_mcp_tool(**kwargs: Any) -> str:
                        return await self.call_tool(captured_name, kwargs)

                    return call_mcp_tool

                registry.register(
                    name=tool_name,
                    func=make_wrapper(tool_name),
                    description=tool_schema["function"]["description"],
                    parameters=tool_schema["function"].get("parameters", {}),
                )
                count += 1

        return count

    @property
    def connected_servers(self) -> list[str]:
        """Get names of connected servers."""
        return list(self._clients.keys())

    @property
    def tool_count(self) -> int:
        """Get total number of available MCP tools."""
        return sum(len(client.tools) for client in self._clients.values())
