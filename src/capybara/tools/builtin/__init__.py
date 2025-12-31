"""Built-in tools: filesystem, bash, search."""

from typing import Optional

from capybara.tools.builtin.bash import register_bash_tools
from capybara.tools.builtin.filesystem import register_filesystem_tools
from capybara.tools.builtin.search import register_search_tools
from capybara.tools.builtin.todo import register_todo_tool
from capybara.tools.registry import ToolRegistry


def register_builtin_tools(
    registry: ToolRegistry,
    parent_session_id: str | None = None,
    parent_agent: object | None = None,
    session_manager: object | None = None,
    storage: object | None = None,
) -> None:
    """Register all built-in tools.

    Args:
        registry: Tool registry to register tools with
        parent_session_id: Optional session ID for task solving (enables solve_task)
        parent_agent: Optional parent agent reference (enables solve_task)
        session_manager: Optional session manager (enables solve_task)
        storage: Optional conversation storage (enables solve_task)
    """
    register_filesystem_tools(registry)
    register_bash_tools(registry)
    register_search_tools(registry)
    register_search_tools(registry)

    register_todo_tool(registry)

    # Only register sub-agent if dependencies provided
    if all([parent_session_id, parent_agent, session_manager, storage]):
        from capybara.tools.builtin.delegation import register_sub_agent_tool
        register_sub_agent_tool(
            registry,
            parent_session_id,
            parent_agent,  # type: ignore
            session_manager,  # type: ignore
            storage  # type: ignore
        )


# Create and populate the default registry (without delegation)
registry = ToolRegistry()
register_builtin_tools(registry)

__all__ = ["registry", "register_builtin_tools"]
