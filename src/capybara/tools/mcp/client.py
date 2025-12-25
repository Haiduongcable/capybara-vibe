"""MCP client for connecting to Model Context Protocol servers."""

import asyncio
from typing import Any, Optional

from capybara.core.config import MCPServerConfig


class MCPClient:
    """Client for connecting to MCP servers via stdio."""

    def __init__(self, name: str, config: MCPServerConfig) -> None:
        self.name = name
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._tools: list[dict[str, Any]] = []
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the MCP server."""
        try:
            # Import MCP only when needed (optional dependency)
            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client
            except ImportError:
                return False

            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env if self.config.env else None,
            )

            # Create and connect client
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize connection
                    await session.initialize()

                    # List available tools
                    tools_response = await session.list_tools()
                    self._tools = [
                        self._convert_tool_schema(tool)
                        for tool in tools_response.tools
                    ]
                    self._connected = True

            return True
        except Exception as e:
            print(f"Failed to connect to MCP server {self.name}: {e}")
            return False

    def _convert_tool_schema(self, mcp_tool: Any) -> dict[str, Any]:
        """Convert MCP tool schema to OpenAI format."""
        return {
            "type": "function",
            "function": {
                "name": f"{self.name}__{mcp_tool.name}",
                "description": mcp_tool.description or "",
                "parameters": mcp_tool.inputSchema if hasattr(mcp_tool, "inputSchema") else {},
            },
        }

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Get available tools in OpenAI format."""
        return self._tools

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._connected

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Strip server prefix from tool name
            if tool_name.startswith(f"{self.name}__"):
                tool_name = tool_name[len(self.name) + 2:]

            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env if self.config.env else None,
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    return str(result.content) if result.content else ""

        except Exception as e:
            return f"Error calling MCP tool: {e}"

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None
        self._connected = False
