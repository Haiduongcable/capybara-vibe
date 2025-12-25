"""Streaming response handling for agent completions."""

from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner

from capybara.providers.router import ProviderRouter


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
    
    with Live(renderable=spinner, console=console, refresh_per_second=4, transient=True) as live:
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
                live.update(Markdown("".join(collected_content)))

            # Collect tool calls (streamed incrementally)
            if delta.tool_calls:
                _collect_tool_calls(delta.tool_calls, collected_tool_calls)

    # Print final content
    if collected_content:
        console.print(Markdown("".join(collected_content)))

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
