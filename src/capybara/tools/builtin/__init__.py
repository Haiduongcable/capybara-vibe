"""Built-in tools: filesystem, bash, search."""

from capybara.tools.builtin.bash import register_bash_tools
from capybara.tools.builtin.filesystem import register_filesystem_tools
from capybara.tools.builtin.search import register_search_tools
from capybara.tools.builtin.search_replace import register_search_replace_tools
from capybara.tools.builtin.todo import register_todo_tool
from capybara.tools.registry import ToolRegistry

# Create and populate the default registry
registry = ToolRegistry()
register_filesystem_tools(registry)
register_bash_tools(registry)
register_search_tools(registry)
register_search_replace_tools(registry)
register_todo_tool(registry)

__all__ = ["registry"]
