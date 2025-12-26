"""Tool registry for async tools with OpenAI schema format."""

import asyncio
import functools
import json
from typing import Any, Callable, Optional

from capybara.tools.base import AgentMode, ToolRestriction


class ToolRegistry:
    """Registry for async tools with OpenAI schema format."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: list[dict[str, Any]] = []
        self._restrictions: dict[str, ToolRestriction] = {}

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        if name in self._tools:
            del self._tools[name]
            self._schemas = [s for s in self._schemas if s["function"]["name"] != name]

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        allowed_modes: Optional[list[AgentMode]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register async tools.

        Args:
            name: Tool name (used in function calling)
            description: Tool description for the LLM
            parameters: JSON Schema for tool parameters
            allowed_modes: Optional list of agent modes allowed to use this tool

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            # Ensure async
            if not asyncio.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return func(*args, **kwargs)

                target_func = async_wrapper
            else:
                target_func = func

            self._tools[name] = target_func
            self._schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": {
                            "$schema": "http://json-schema.org/draft-07/schema#",
                            "additionalProperties": False,
                            **parameters,
                        },
                    },
                }
            )

            # Store restrictions
            if allowed_modes:
                self._restrictions[name] = ToolRestriction(allowed_modes=allowed_modes)

            return target_func

        return decorator

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        """Register a tool programmatically (non-decorator API).

        Args:
            name: Tool name
            func: Tool function (sync or async)
            description: Tool description
            parameters: JSON Schema for parameters
        """
        # Use decorator internally
        self.tool(name, description, parameters)(func)

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return result as string.

        Args:
            name: Tool name to execute
            arguments: Arguments to pass to the tool

        Returns:
            Tool result as string
        """
        if name not in self._tools:
            return f"Error: Unknown tool '{name}'"
        try:
            result = await self._tools[name](**arguments)
            return str(result) if not isinstance(result, str) else result
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Get a tool function by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI-format tool schemas."""
        return self._schemas

    def merge(self, other: "ToolRegistry") -> None:
        """Merge another registry into this one."""
        for name, func in other._tools.items():
            if name not in self._tools:
                self._tools[name] = func
        for schema in other._schemas:
            if schema not in self._schemas:
                self._schemas.append(schema)

    def to_json(self) -> str:
        """Export schemas as JSON."""
        return json.dumps(self._schemas, indent=2)

    def filter_by_mode(self, mode: AgentMode) -> "ToolRegistry":
        """Create filtered registry for specific agent mode."""
        filtered = ToolRegistry()

        for name, func in self._tools.items():
            restriction = self._restrictions.get(name)

            # If no restriction or mode allowed, include tool
            if not restriction or mode in restriction.allowed_modes:
                schema = next(s for s in self._schemas if s["function"]["name"] == name)
                filtered._tools[name] = func
                filtered._schemas.append(schema)
                if restriction:
                    filtered._restrictions[name] = restriction

        return filtered

    def is_tool_allowed(self, name: str, mode: AgentMode) -> bool:
        """Check if tool is allowed in mode."""
        restriction = self._restrictions.get(name)
        if not restriction:
            return True
        return mode in restriction.allowed_modes
