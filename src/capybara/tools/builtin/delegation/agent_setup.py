"""Sub-agent creation and configuration."""

from rich.console import Console

from capybara.core.agent import Agent, AgentConfig
from capybara.core.utils.prompts import build_child_system_prompt
from capybara.memory.window import ConversationMemory, MemoryConfig
from capybara.tools.base import AgentMode
from capybara.tools.registry import ToolRegistry


def create_sub_agent(
    parent_agent: Agent,
    child_session_id: str,
    parent_session_id: str,
    timeout: float
) -> Agent:
    """Create and configure sub-agent for autonomous work.

    Sub-agent configuration:
    - Inherits parent's model and provider (API keys)
    - Gets CHILD mode tools (excludes sub_agent/todo)
    - Uses work-focused system prompt
    - Has own console for isolated output
    - Tracks execution via execution_log

    Args:
        parent_agent: Parent agent to inherit config from
        child_session_id: Session ID for child
        parent_session_id: Parent's session ID for logging
        timeout: Max execution time

    Returns:
        Configured sub-agent ready for execution
    """

    # Initialize child memory with work-focused prompt
    child_memory = ConversationMemory(config=MemoryConfig(max_tokens=100_000))
    child_memory.set_system_prompt(build_child_system_prompt())

    # Configure child for autonomous work
    child_config = AgentConfig(
        model=parent_agent.config.model,
        max_turns=70,
        timeout=timeout,
        stream=True,
        mode=AgentMode.CHILD  # Restricted mode (no delegation/todo)
    )

    # Setup child tools (filtered by CHILD mode)
    from capybara.tools.builtin import register_builtin_tools
    child_tools = ToolRegistry()
    register_builtin_tools(child_tools)

    # Create child with isolated console
    child_console = Console()

    # Create agent (inherits parent's provider for API keys)
    return Agent(
        config=child_config,
        memory=child_memory,
        tools=child_tools,
        console=child_console,
        provider=parent_agent.provider,  # CRITICAL: Inherit API keys
        tools_config=parent_agent.tools_config,
        session_id=child_session_id,
        parent_session_id=parent_session_id
    )
