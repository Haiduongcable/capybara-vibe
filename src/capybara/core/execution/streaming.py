"""Streaming response handling for agent completions."""

import re
import time
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

from capybara.providers.router import ProviderRouter


def _clean_content(content: str) -> str:
    """Remove tool call echoes from the model output.

    Some models echo the tool call as text before executing it, using multiline formatting.
    This regex uses DOTALL (?s) to match across newlines, stripping the call.
    """
    # Whitelist of tools to detect
    tool_names = (
        r"todo|read_file|write_file|edit_file|delete_file|list_directory|glob|grep|bash|which"
    )

    # Match > toolname(...) across newlines, non-greedy to stop at first closing paren
    # Note: Does not handle nested parenthesis perfectly, but handles standard repr() output well.
    p = r"(?s)> \s*(?:" + tool_names + r")\s*\(.*?\)"
    return re.sub(p, "", content)


def _update_display(
    live: Live,
    collected_content: list[str],
    collected_tool_calls: dict[int, dict[str, Any]],
) -> None:
    """Update Live display with current content and smart status indicators."""
    display_content = _clean_content("".join(collected_content))

    # Dynamic threshold based on terminal height
    # Reserve space for: status line (1) + continuation hint (1) + spinner (1) + prompt area (3) + buffer (2) = 8 lines
    terminal_height = live.console.size.height
    RESERVED_LINES = 4
    max_content_lines = max(int(terminal_height / 2) - RESERVED_LINES, 5)  # Minimum 5 lines

    # Calculate line count
    line_count = display_content.count("\n")
    is_long_message = line_count > max_content_lines

    if collected_tool_calls:
        # Show tool preparation message
        if display_content.strip():
            live.update(
                Group(
                    Markdown(display_content),
                    Text("🔨 Preparing tool execution...", style="dim cyan"),
                    Spinner("dots", style="cyan"),
                )
            )
        else:
            live.update(
                Group(
                    Text("🔨 Preparing tool execution...", style="dim cyan"),
                    Spinner("dots", style="cyan"),
                )
            )
    elif display_content.strip():
        # Show content + spinner with smart status for long messages
        if is_long_message:
            # For long messages: show truncated preview + status
            lines = display_content.split("\n")
            truncated_lines = lines[:max_content_lines]
            truncated_content = "\n".join(truncated_lines)

            char_count = len(display_content)
            status_text = Text(
                f"✍️  Typing long message... ({char_count} chars, {line_count} lines)",
                style="dim yellow",
            )

            live.update(
                Group(
                    Markdown(truncated_content),
                    Text("... (message continues below)", style="dim italic"),
                    status_text,
                    Spinner("dots", style="cyan"),
                )
            )
        else:
            # Short messages: show full content
            live.update(Group(Markdown(display_content), Spinner("dots", style="cyan")))
    else:
        # Just spinner
        live.update(Spinner("dots", style="cyan"))


async def stream_completion(
    provider: ProviderRouter,
    messages: list[dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]] | None,
    timeout: float,
    console: Console,
) -> dict[str, Any]:
    """Stream completion with adaptive display for long messages.

    - Short messages: Full Live display with markdown
    - Long messages: Truncated preview + status indicator in Live

    Args:
        provider: Provider router for LLM calls
        messages: Conversation messages
        model: Model to use
        tools: Tool schemas
        timeout: Request timeout
        console: Rich console for output

    Returns:
        Assembled response message dict
    """
    collected_content: list[str] = []
    collected_tool_calls: dict[int, dict[str, Any]] = {}

    # Batching state for smooth updates
    last_update_time = time.time()
    UPDATE_INTERVAL = 0.05  # 50ms batching

    spinner = Spinner("dots", text="Thinking...", style="cyan")

    with Live(
        renderable=spinner,
        console=console,
        refresh_per_second=20,
        transient=True,
        vertical_overflow="ellipsis",
    ) as live:
        async for chunk in provider.complete(
            messages=messages,
            model=model,
            tools=tools,
            stream=True,
            timeout=timeout,
        ):
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Collect content
            content_updated = False
            if delta.content:
                collected_content.append(delta.content)
                content_updated = True

            # Collect tool calls
            if delta.tool_calls:
                _collect_tool_calls(delta.tool_calls, collected_tool_calls)
                content_updated = True

            # Batched updates
            if content_updated:
                now = time.time()
                if now - last_update_time >= UPDATE_INTERVAL:
                    _update_display(live, collected_content, collected_tool_calls)
                    last_update_time = now

        # Final update
        _update_display(live, collected_content, collected_tool_calls)

    # Print final full content
    full_content = "".join(collected_content)
    clean_content = _clean_content(full_content)
    if clean_content.strip():
        console.print(Markdown(clean_content))

    return _build_message(collected_content, collected_tool_calls)


def _collect_tool_calls(
    tool_calls: list[Any],
    collected: dict[int, dict[str, Any]],
) -> None:
    """Collect streaming tool call chunks into complete calls."""
    for tc in tool_calls:
        idx = tc.index
        if idx not in collected:
            collected[idx] = {
                "id": tc.id or "",
                "type": "function",
                "function": {"name": "", "arguments": ""},
            }
        if tc.id:
            collected[idx]["id"] = tc.id
        if tc.function:
            if tc.function.name:
                collected[idx]["function"]["name"] = tc.function.name
            if tc.function.arguments:
                collected[idx]["function"]["arguments"] += tc.function.arguments


def _build_message(
    content: list[str],
    tool_calls: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Build response message from collected content and tool calls."""
    message: dict[str, Any] = {"role": "assistant"}
    if content:
        message["content"] = "".join(content)
    if tool_calls:
        message["tool_calls"] = list(tool_calls.values())
    return message


async def non_streaming_completion(
    provider: ProviderRouter,
    messages: list[dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]] | None,
    timeout: float,
    console: Console,
) -> dict[str, Any]:
    """Handle non-streaming completion.

    Args:
        provider: Provider router for LLM calls
        messages: Conversation messages
        model: Model to use
        tools: Tool schemas
        timeout: Request timeout
        console: Rich console for output

    Returns:
        Response message dict
    """
    response = await provider.complete_non_streaming(
        messages=messages,
        model=model,
        tools=tools,
        timeout=timeout,
    )

    choice = response.choices[0]
    message: dict[str, Any] = {"role": "assistant"}

    if choice.message.content:
        message["content"] = choice.message.content
        console.print(Markdown(choice.message.content))

    if choice.message.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]

    return message
