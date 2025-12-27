"""Streaming response handling for agent completions."""

from typing import Any, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

from capybara.providers.router import ProviderRouter
import re

def _clean_content(content: str) -> str:
    """Remove tool call echoes from the model output.
    
    Some models echo the tool call as text before executing it, using multiline formatting.
    This regex uses DOTALL (?s) to match across newlines, stripping the call.
    """
    # Whitelist of tools to detect
    tool_names = r"todo|read_file|write_file|edit_file|search_replace|delete_file|list_directory|glob|grep|bash|which"
    
    # Match > toolname(...) across newlines, non-greedy to stop at first closing paren
    # Note: Does not handle nested parenthesis perfectly, but handles standard repr() output well.
    p = r'(?s)> \s*(?:' + tool_names + r')\s*\(.*?\)'
    return re.sub(p, '', content)


async def stream_completion(
    provider: ProviderRouter,
    messages: list[dict[str, Any]],
    model: str,
    tools: Optional[list[dict[str, Any]]],
    timeout: float,
    console: Console,
) -> dict[str, Any]:
    """Stream completion with Rich Live display.

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

    spinner = Spinner("dots", text="Thinking...", style="cyan")
    
    with Live(renderable=spinner, console=console, refresh_per_second=10, transient=True) as live:
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
            if delta.content:
                collected_content.append(delta.content)
                # Show content + spinner at the bottom while streaming
                display_content = _clean_content("".join(collected_content))
                if display_content.strip():
                     live.update(Group(
                        Markdown(display_content),
                        Spinner("dots", style="cyan")
                    ))
                else:
                    live.update(Spinner("dots", style="cyan"))

            # Collect tool calls (streamed incrementally)
            if delta.tool_calls:
                _collect_tool_calls(delta.tool_calls, collected_tool_calls)
                # If we are only getting tool calls now (content finished or interleaved)
                # Ensure we still show the spinner with context
                display_content = _clean_content("".join(collected_content))
                if display_content.strip():
                     live.update(Group(
                        Markdown(display_content),
                        Text("🔨 Preparing tool execution...", style="dim cyan"),
                        Spinner("dots", style="cyan")
                    ))
                else:
                    live.update(Group(
                        Text("🔨 Preparing tool execution...", style="dim cyan"),
                        Spinner("dots", style="cyan")
                    ))

    # Print final content
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
    tools: Optional[list[dict[str, Any]]],
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
