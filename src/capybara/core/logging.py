"""Logging module - backward compatibility wrapper.

This module maintains backward compatibility while the actual implementation
has been moved to the logging/ subdirectory for better organization.
"""

from .logging import (
    SessionLoggerAdapter,
    SessionLogManager,
    get_session_log_manager,
    ErrorLogManager,
    get_error_log_manager,
    log_error,
    log_agent_behavior,
    log_delegation,
    log_tool_execution,
    log_state_change,
    setup_logging,
    get_logger,
)

__all__ = [
    'SessionLoggerAdapter',
    'SessionLogManager',
    'get_session_log_manager',
    'ErrorLogManager',
    'get_error_log_manager',
    'log_error',
    'log_agent_behavior',
    'log_delegation',
    'log_tool_execution',
    'log_state_change',
    'setup_logging',
    'get_logger',
]
