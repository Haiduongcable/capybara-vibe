"""Core capybara modules - refactored for better organization.

For backward compatibility, all classes are re-exported from this module.
New code should import from submodules directly:
- capybara.core.agent
- capybara.core.execution
- capybara.core.delegation
- capybara.core.config
- capybara.core.utils
- capybara.core.logging
"""

# Agent components
from capybara.core.agent import (
    Agent,
    AgentConfig,
    AgentState,
    AgentStatus,
    AgentStateManager,
    AgentUIRenderer,
)

# Execution
from capybara.core.execution import (
    ExecutionLog,
    ToolExecution,
    ToolExecutor,
    non_streaming_completion,
    stream_completion,
)

# Delegation
from capybara.core.delegation import (
    ChildFailure,
    Event,
    EventBus,
    EventType,
    FailureCategory,
    SessionManager,
    get_event_bus,
)

# Config
from capybara.core.config import (
    DANGEROUS_DIRECTORY_WARNING,
    CapybaraConfig,
    MCPConfig,
    MCPServerConfig,
    MemoryConfig,
    ProviderConfig,
    ToolSecurityConfig,
    ToolsConfig,
    is_dangerous_directory,
    load_config,
    save_config,
    init_config,
    suppress_litellm_output,
)

# Utils
from capybara.core.utils import (
    AgentInterruptException,
    build_child_system_prompt,
    build_project_context,
    build_system_prompt,
)

# Logging (already has its own module)
from capybara.core.logging import (
    SessionLoggerAdapter,
    get_logger,
    get_session_log_manager,
    log_delegation,
    log_error,
    log_state_change,
    log_tool_execution,
)

__all__ = [
    # Agent
    "Agent",
    "AgentConfig",
    "AgentState",
    "AgentStatus",
    "AgentStateManager",
    "AgentUIRenderer",
    # Execution
    "ExecutionLog",
    "ToolExecution",
    "ToolExecutor",
    "stream_completion",
    "non_streaming_completion",
    # Delegation
    "SessionManager",
    "EventBus",
    "Event",
    "EventType",
    "get_event_bus",
    "ChildFailure",
    "FailureCategory",
    # Config
    "CapybaraConfig",
    "ProviderConfig",
    "MemoryConfig",
    "ToolsConfig",
    "ToolSecurityConfig",
    "MCPConfig",
    "MCPServerConfig",
    "load_config",
    "save_config",
    "init_config",
    "suppress_litellm_output",
    "is_dangerous_directory",
    "DANGEROUS_DIRECTORY_WARNING",
    # Utils
    "build_project_context",
    "build_system_prompt",
    "build_child_system_prompt",
    "AgentInterruptException",
    # Logging
    "get_logger",
    "get_session_log_manager",
    "SessionLoggerAdapter",
    "log_error",
    "log_delegation",
    "log_tool_execution",
    "log_state_change",
]
