#!/usr/bin/env python
"""Demo script to test the enhanced logging system."""

import asyncio
from capybara.core.logging import (
    get_session_log_manager,
    log_delegation,
    log_tool_execution,
    log_state_change,
    log_error,
)


async def demo_session_logging():
    """Demonstrate session-based logging."""
    print("🔍 Testing Enhanced Logging System\n")

    # Create session logger
    log_manager = get_session_log_manager()

    print("1. Creating parent session logger...")
    parent_logger = log_manager.create_session_logger(
        session_id="demo-parent-001",
        agent_mode="parent",
        log_level="INFO"
    )
    parent_logger.info("Parent session started")

    # Log state changes
    print("2. Logging state changes...")
    log_state_change(
        parent_logger,
        from_state="idle",
        to_state="thinking",
        reason="Processing user request"
    )

    # Log tool execution
    print("3. Logging tool execution...")
    log_tool_execution(
        parent_logger,
        tool_name="bash",
        status="success",
        duration=1.23
    )

    # Create child session
    print("4. Creating child session logger...")
    child_logger = log_manager.create_session_logger(
        session_id="demo-child-001",
        agent_mode="child",
        log_level="INFO"
    )

    # Log delegation
    print("5. Logging delegation events...")
    log_delegation(
        parent_logger,
        action="start",
        parent_session="demo-parent-001",
        child_session="demo-child-001",
        prompt="Test delegation task"
    )

    # Child does work
    child_logger.info("Child processing delegated task")
    log_tool_execution(
        child_logger,
        tool_name="read_file",
        status="success",
        duration=0.15
    )

    # Complete delegation
    log_delegation(
        parent_logger,
        action="complete",
        parent_session="demo-parent-001",
        child_session="demo-child-001",
        duration="2.45s"
    )

    # Log an error
    print("6. Logging error...")
    try:
        raise ValueError("Demo error for testing")
    except ValueError as e:
        log_error(
            error=e,
            context="demo_script",
            session_id="demo-parent-001",
            agent_mode="parent"
        )

    # Cleanup
    print("7. Closing session loggers...")
    log_manager.close_session_logger("demo-parent-001")
    log_manager.close_session_logger("demo-child-001")

    print("\n✅ Logging demo completed!")
    print("\nCheck logs at:")
    print("  - ~/.capybara/logs/sessions/<date>/session_demo-par.log")
    print("  - ~/.capybara/logs/sessions/<date>/session_demo-chi.log")
    print("  - ~/.capybara/logs/errors/capybara_errors_<date>.log")
    print("  - ~/.capybara/logs/capybara_<date>.log")


if __name__ == "__main__":
    asyncio.run(demo_session_logging())
