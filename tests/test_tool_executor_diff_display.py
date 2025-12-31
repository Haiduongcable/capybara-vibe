"""Integration tests for tool_executor diff display functionality."""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from rich.console import Console
from rich.panel import Panel

from capybara.core.config.settings import ToolsConfig
from capybara.core.execution.tool_executor import ToolExecutor
from capybara.tools.base import AgentMode
from capybara.tools.builtin.filesystem import register_filesystem_tools
from capybara.tools.registry import ToolRegistry


@pytest.fixture
def temp_file():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Line 1: Original content\nLine 2: Keep this\nLine 3: Old line")
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def tool_registry():
    """Create a tool registry with filesystem tools."""
    registry = ToolRegistry()
    register_filesystem_tools(registry)
    return registry


@pytest.fixture
def console_output():
    """Create a StringIO for capturing console output."""
    return StringIO()


@pytest.fixture
def mock_ui_renderer():
    """Create a mock UI renderer."""
    mock = Mock()
    mock.render_status.return_value = Panel("Test Status")
    return mock


@pytest.fixture
def tool_executor(tool_registry, console_output):
    """Create a ToolExecutor with test console."""
    console = Console(file=console_output, force_terminal=True, width=120)
    return ToolExecutor(
        tools=tool_registry,
        console=console,
        tools_config=ToolsConfig(),
        agent_mode=AgentMode.PARENT,
        session_id="test-session",
    )


@pytest.mark.asyncio
async def test_edit_file_displays_diff_immediately(
    tool_executor, temp_file, console_output, mock_ui_renderer
):
    """Verify that edit_file displays formatted diff to console immediately."""

    # Create tool call for edit_file
    tool_calls = [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "edit_file",
                "arguments": f'{{"path": "{temp_file}", "old_string": "Old line", "new_string": "New line", "replace_all": false}}',
            },
        }
    ]

    # Execute the tool
    results = await tool_executor.execute_tools(tool_calls, mock_ui_renderer)

    # Get console output
    output = console_output.getvalue()

    # Verify diff content is present (no box panel anymore)
    assert "Update(" in output, "Diff header missing"
    assert "Added" in output or "Removed" in output, "Change summary missing"
    assert "Old line" in output, "Old content not shown"
    assert "New line" in output, "New content not shown"

    # Verify result was returned correctly
    assert len(results) == 1
    assert results[0]["role"] == "tool"
    assert "Update(" in results[0]["content"]


@pytest.mark.asyncio
async def test_edit_file_error_does_not_display_diff(
    tool_executor, console_output, mock_ui_renderer
):
    """Verify that error results do not trigger diff display."""

    # Create tool call with non-existent file
    tool_calls = [
        {
            "id": "call_456",
            "type": "function",
            "function": {
                "name": "edit_file",
                "arguments": '{"path": "/nonexistent/file.txt", "old_string": "foo", "new_string": "bar", "replace_all": false}',
            },
        }
    ]

    # Execute the tool
    results = await tool_executor.execute_tools(tool_calls, mock_ui_renderer)

    # Get console output
    output = console_output.getvalue()

    # Verify NO diff was displayed (since it's an error)
    assert "Update(" not in output, "Should not show diff for errors"

    # Verify error result was returned
    assert len(results) == 1
    assert "Error" in results[0]["content"]


@pytest.mark.asyncio
async def test_edit_file_multiple_replacements_shows_all(
    tool_executor, temp_file, console_output, mock_ui_renderer
):
    """Verify diff shows all replacements when replace_all=true."""

    # First, add more content to file
    with open(temp_file, "w") as f:
        f.write("foo bar\nfoo baz\nfoo qux")

    # Create tool call with replace_all
    tool_calls = [
        {
            "id": "call_789",
            "type": "function",
            "function": {
                "name": "edit_file",
                "arguments": f'{{"path": "{temp_file}", "old_string": "foo", "new_string": "FOO", "replace_all": true}}',
            },
        }
    ]

    # Execute the tool
    results = await tool_executor.execute_tools(tool_calls, mock_ui_renderer)

    # Get console output
    output = console_output.getvalue()

    # Verify diff was displayed
    assert "Update(" in output

    # Verify multiple replacements message
    assert "3 occurrences" in results[0]["content"]
    assert "FOO" in output  # New content should be visible


@pytest.mark.asyncio
async def test_other_tools_do_not_trigger_diff_display(
    tool_executor, temp_file, console_output, mock_ui_renderer
):
    """Verify that non-edit_file tools don't trigger diff rendering."""

    # Use read_file tool instead
    tool_calls = [
        {
            "id": "call_read",
            "type": "function",
            "function": {
                "name": "read_file",
                "arguments": f'{{"path": "{temp_file}"}}',
            },
        }
    ]

    # Execute the tool
    results = await tool_executor.execute_tools(tool_calls, mock_ui_renderer)

    # Get console output
    output = console_output.getvalue()

    # Verify NO diff (read_file doesn't produce diffs)
    assert "Update(" not in output

    # But result should be successful
    assert len(results) == 1
    assert "Line 1:" in results[0]["content"]


@pytest.mark.asyncio
async def test_diff_display_handles_special_characters(
    tool_executor, console_output, mock_ui_renderer
):
    """Verify diff rendering handles special characters correctly."""

    # Create temp file with special chars
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Line with $pecial & <chars>")
        temp_path = f.name

    try:
        tool_calls = [
            {
                "id": "call_special",
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "arguments": f'{{"path": "{temp_path}", "old_string": "$pecial & <chars>", "new_string": "normal text", "replace_all": false}}',
                },
            }
        ]

        # Execute
        _ = await tool_executor.execute_tools(tool_calls, mock_ui_renderer)

        # Get output
        output = console_output.getvalue()

        # Verify special chars are handled
        assert "Update(" in output
        assert "normal text" in output

    finally:
        Path(temp_path).unlink(missing_ok=True)
