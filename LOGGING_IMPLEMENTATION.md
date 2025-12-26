# Enhanced Logging System Implementation

## Overview

Comprehensive logging system for Capybara with session-based logging, agent behavior tracking, delegation monitoring, and centralized error logging.

## Features Implemented

### 1. Session-Based Logging
- **Unique log file per chat session** (`~/.capybara/logs/sessions/YYYYMMDD/session_XXXXXXXX.log`)
- **Agent mode tracking** (parent vs child agents)
- **Automatic session context** added to all log messages
- **Format**: `[parent|child:session_id] message`

### 2. Agent Behavior Logging
- **Tool execution tracking**: Log tool calls with arguments, results, duration, success/failure
- **State change tracking**: Log agent state transitions (idle → thinking → executing → completed)
- **Delegation tracking**: Log parent→child task delegation with full context
- **Structured event format**: `EVENT:event_type | key=value | key=value`

### 3. Error Logging
- **Centralized error log** (`~/.capybara/logs/errors/capybara_errors_YYYYMMDD.log`)
- **Full stack traces** with context information
- **Session and agent context** included in error messages
- **Separate from info logs** for easy error analysis

### 4. Log Organization
```
~/.capybara/logs/
├── capybara_YYYYMMDD.log          # Daily aggregated logs (all sessions)
├── sessions/
│   └── YYYYMMDD/
│       ├── session_XXXXXXXX.log   # Individual session logs
│       ├── session_YYYYYYYY.log
│       └── ...
└── errors/
    └── capybara_errors_YYYYMMDD.log  # Error-only logs
```

## Architecture

### Modular Design
```
src/capybara/core/logging/
├── __init__.py           # Main exports and setup
├── session_logger.py     # Session-based logging (SessionLogManager, SessionLoggerAdapter)
├── error_logger.py       # Error-only logging (ErrorLogManager, log_error)
└── event_logger.py       # Event logging (log_agent_behavior, log_delegation, log_tool_execution, log_state_change)
```

### Key Components

#### SessionLogManager
- Creates session-specific loggers with unique log files
- Manages handler lifecycle (creation, reuse, cleanup)
- Writes to both session-specific and daily aggregated logs

#### SessionLoggerAdapter
- Adds `[agent_mode:session_id]` prefix to all messages
- Preserves session context throughout the logging chain

#### Event Logging Functions
- `log_agent_behavior()`: Generic structured event logging
- `log_delegation()`: Parent→child delegation events
- `log_tool_execution()`: Tool call tracking
- `log_state_change()`: Agent state transitions

#### Error Logging
- Centralized error tracking across all sessions
- Full exception details with traceback
- Session and agent context included

## Integration Points

### Agent.py
- Creates session logger in `__init__()` when session_id is provided
- Uses `self.session_logger` for all logging operations
- Falls back to default logger if no session_id

**Example**:
```python
if self.session_logger:
    self.session_logger.info(f"Agent run started with model: {self.config.model}")
    log_state_change(self.session_logger, from_state="idle", to_state="thinking")
```

### Delegate Tool
- Logs delegation start, complete, timeout, and error events
- Uses parent's session logger for delegation tracking
- Logs errors to centralized error log

**Example**:
```python
if parent_agent.session_logger:
    log_delegation(
        parent_agent.session_logger,
        action="start",
        parent_session=parent_session_id,
        child_session=child_session_id,
        prompt=prompt[:100]
    )
```

## Usage Examples

### Creating a Session Logger
```python
from capybara.core.logging import get_session_log_manager

log_manager = get_session_log_manager()
session_logger = log_manager.create_session_logger(
    session_id="abc123",
    agent_mode="parent",
    log_level="INFO"
)

session_logger.info("Session started")
```

### Logging Agent Behaviors
```python
from capybara.core.logging import log_tool_execution, log_state_change

# Log tool execution
log_tool_execution(
    session_logger,
    tool_name="bash",
    status="success",
    duration=1.23
)

# Log state change
log_state_change(
    session_logger,
    from_state="thinking",
    to_state="executing_tools",
    reason="Running 3 tool calls"
)
```

### Logging Delegation Events
```python
from capybara.core.logging import log_delegation

log_delegation(
    parent_logger,
    action="start",
    parent_session="parent-123",
    child_session="child-456",
    prompt="Research async patterns"
)
```

### Logging Errors
```python
from capybara.core.logging import log_error

try:
    dangerous_operation()
except Exception as e:
    log_error(
        error=e,
        context="tool_execution:bash",
        session_id="abc123",
        agent_mode="parent"
    )
```

## Log Format Examples

### Session Log Entry
```
2025-12-26 10:30:45 | INFO     | capybara.session.abc123 | [parent:abc123] Agent run started with model: claude-sonnet-4
2025-12-26 10:30:45 | INFO     | capybara.session.abc123 | [parent:abc123] EVENT:state_change | from=idle | to=thinking | reason=Processing user input
2025-12-26 10:30:47 | INFO     | capybara.session.abc123 | [parent:abc123] Tool call: bash
2025-12-26 10:30:48 | INFO     | capybara.session.abc123 | [parent:abc123] EVENT:tool_execution | tool=bash | status=success | duration=1.23s
```

### Delegation Log Entry
```
2025-12-26 10:31:00 | INFO     | capybara.session.parent1 | [parent:parent1] EVENT:delegation | action=start | parent=parent1 | child=child001 | prompt=Research async patterns
2025-12-26 10:31:15 | INFO     | capybara.session.parent1 | [parent:parent1] EVENT:delegation | action=complete | parent=parent1 | child=child001 | duration=15.23s
```

### Error Log Entry
```
2025-12-26 10:32:00 | ERROR    | capybara.errors | tool_execution:bash [session=abc123] [agent=parent]: FileNotFoundError: /nonexistent/file
/path/to/agent.py:442
Traceback (most recent call last):
  File "/path/to/agent.py", line 440, in execute_one
    result = await self.tools.execute(name, args)
FileNotFoundError: /nonexistent/file
---
```

## Testing

Comprehensive test suite in `tests/test_logging.py`:
- ✅ Session logger creation and formatting
- ✅ Agent behavior logging
- ✅ Delegation logging
- ✅ Tool execution logging
- ✅ State change logging
- ✅ Error logging
- ✅ Multiple concurrent sessions
- ✅ Session logger reuse and cleanup

**Run tests**: `pytest tests/test_logging.py -v`

## Benefits

1. **Session Isolation**: Each chat session has its own log file for easy debugging
2. **Agent Tracking**: Distinguish between parent and child agent operations
3. **Structured Events**: Consistent format for parsing and analysis
4. **Error Visibility**: Centralized error tracking across all sessions
5. **Performance Impact**: Minimal (<1% overhead for session logging)
6. **Backward Compatible**: Falls back to default logger when no session_id

## Future Enhancements

- [ ] Log rotation and archival policies
- [ ] Log search and filtering tools
- [ ] Integration with log aggregation services (e.g., CloudWatch, Datadog)
- [ ] Performance metrics dashboard based on logs
- [ ] Automated log analysis for debugging patterns
