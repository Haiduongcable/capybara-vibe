# Research Report: LiteLLM Best Practices for AI Coding Agents (2025)

**Research Date:** December 25, 2025
**Focus Period:** 2024-2025
**Last Updated:** 2025-12-25

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Research Methodology](#research-methodology)
3. [Key Findings](#key-findings)
4. [Async Streaming Patterns](#async-streaming-patterns)
5. [Tool Calling Support](#tool-calling-support)
6. [Provider Fallback Strategies](#provider-fallback-strategies)
7. [Token Management](#token-management)
8. [Implementation Recommendations](#implementation-recommendations)
9. [Common Pitfalls](#common-pitfalls)
10. [Resources](#resources)

---

## Executive Summary

LiteLLM provides a unified interface for 100+ LLM APIs with production-grade patterns for building AI agents. Key findings:

**Streaming:** Use `acompletion()` with `async for` for true non-blocking streaming. Avoid synchronous patterns that fake streaming. LiteLLM protects against infinite loops with configurable `REPEATED_STREAMING_CHUNK_LIMIT` (default 100).

**Tool Calling:** Provider differences significantly impact agent complexity. OpenAI uses role-based tool messages; Anthropic/Gemini use content blocks. LiteLLM handles conversion but nested schema management varies. Parallel tool calls are supported but have known issues across Gemini/Bedrock.

**Fallbacks & Routing:** Router supports 6+ strategies (simple-shuffle recommended for production). Retry logic with exponential backoff for rate limits. Known issue: usage-based-routing-v2 ignores retry settings and fails on rate limits.

**Token Management:** Built-in token counting for major providers, context window validation pre-call. Cost tracking integrated. Tokenizer accuracy issues with vLLM-hosted models.

---

## Research Methodology

**Sources Consulted:** 12 authoritative sources
**Date Range:** 2024-2025
**Search Terms:** async streaming, tool calling, router fallback, retry logic, token counting, provider differences

**Verification Approach:** Cross-referenced official LiteLLM docs, GitHub issues, community implementations

---

## Key Findings

### 1. Technology Overview

LiteLLM is a Python SDK + Proxy Server providing:
- Unified interface to 100+ LLM APIs
- OpenAI-compatible format abstraction
- Cost tracking, guardrails, load balancing, logging
- Support: Bedrock, Azure, OpenAI, VertexAI, Cohere, Anthropic, SageMaker, HuggingFace, vLLM, NVIDIA NIM

**Current Version Context:** Latest releases (v1.80+) include Gemini 3.0 support, parallel tool call improvements, streaming enhancements.

### 2. Current State & Trends

**2025 Developments:**
- Gemini 3.0 integration with thought signature support
- Improved parallel tool call handling (ongoing issues)
- Response format mapping (json_schema across providers)
- Enhanced async streaming with usage tracking

**Known Gaps:**
- Parallel tool calls broken on Gemini models
- Bedrock multi-message format issues for tool results
- Usage-based-routing-v2 retry logic incomplete
- Tokenizer accuracy issues with vLLM-hosted models

---

## Async Streaming Patterns

### Pattern 1: Basic Async Streaming with Error Handling

```python
from litellm import acompletion
import asyncio

async def stream_completion_with_error_handling():
    try:
        response = await acompletion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Explain async streaming"}],
            stream=True,
            timeout=30  # Prevent hanging
        )

        # TRUE async iteration - non-blocking
        async for chunk in response:
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)

    except Exception as e:
        print(f"Streaming error: {type(e).__name__}: {e}")
        # Implement retry logic here

asyncio.run(stream_completion_with_error_handling())
```

**Key Points:**
- `async for` enables true non-blocking iteration
- Synchronous `for` loops wait for entire iterator - breaks streaming benefits
- Delta content appears in `chunk.choices[0].delta.content`
- Use `timeout` to prevent hanging connections

### Pattern 2: Chunk Type Detection and Content Handling

```python
from litellm import acompletion
from typing import AsyncGenerator

async def stream_with_chunk_detection() -> AsyncGenerator[str, None]:
    response = await acompletion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Stream response"}],
        stream=True,
        stream_options={"include_usage": True}  # Get token counts
    )

    async for chunk in response:
        # Handle text content
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

        # Handle tool calls in streaming
        if hasattr(chunk.choices[0].delta, 'tool_calls'):
            for tool_call in chunk.choices[0].delta.tool_calls or []:
                yield f"[TOOL_CALL: {tool_call.function.name}]"

        # Final chunk with usage info
        if chunk.usage and chunk.choices[0].finish_reason == "stop":
            yield f"\n[TOKENS: {chunk.usage.completion_tokens}]"
```

**Chunk Handling Strategy:**
- Content chunks have `.delta.content`
- Tool calls appear in `.delta.tool_calls`
- Final chunk includes usage when `include_usage=True`
- `finish_reason` indicates completion type

### Pattern 3: Infinite Loop Protection

```python
import litellm

# Configure protection (default is 100)
litellm.REPEATED_STREAMING_CHUNK_LIMIT = 100

async def protected_stream():
    try:
        response = await acompletion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True
        )

        async for chunk in response:
            # If chunk repeats >100 times, raises litellm.InternalServerError
            print(chunk)

    except litellm.InternalServerError as e:
        print(f"Infinite loop detected: {e}")
        # Implement circuit breaker pattern
```

**Configuration:**
- Set `litellm.REPEATED_STREAMING_CHUNK_LIMIT` per application need
- Raise `InternalServerError` when limit exceeded
- Use for circuit breaker + retry logic

### Pattern 4: Error Recovery During Streaming

```python
async def resilient_streaming():
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            response = await acompletion(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Test"}],
                stream=True
            )

            accumulated_content = ""
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    accumulated_content += chunk.choices[0].delta.content

            return accumulated_content

        except litellm.APIError as e:
            retry_count += 1
            wait_time = 2 ** retry_count  # Exponential backoff
            print(f"Retry {retry_count} after {wait_time}s")
            await asyncio.sleep(wait_time)
        except litellm.RateLimitError as e:
            # Handle rate limit with exponential backoff
            await asyncio.sleep(int(e.response.headers.get('retry-after', 60)))

    raise Exception("Max retries exceeded")
```

---

## Tool Calling Support

### Provider Difference Matrix

| Aspect | OpenAI | Anthropic | Gemini |
|--------|--------|-----------|--------|
| **Message Role** | user, assistant, tool | user, assistant | user, model |
| **Tool Results Format** | Dedicated tool message | Content block in assistant | Content block in model |
| **Parallel Calls** | Native support | Supported | Not working in LiteLLM |
| **Streaming Tool Args** | Yes | Yes | Limited |
| **Schema Format** | JSON Schema | JSON Schema | JSON Schema + config |
| **Response Format** | response_format | output_format | response_format |

### Pattern 1: Tool Definition in OpenAI Format

```python
from litellm import completion
import json

# Define tools once in OpenAI format
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Search for code patterns in repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'async def')"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "File pattern (e.g., '*.py')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"]
            }
        }
    }
]

# LiteLLM handles conversion for Anthropic/Gemini
response = completion(
    model="gpt-4o-mini",  # Works with any provider
    messages=[{"role": "user", "content": "Find async patterns"}],
    tools=tools,
    tool_choice="auto"
)
```

**Provider Abstraction:**
- Define tools once in OpenAI format
- LiteLLM converts internally for Anthropic/Gemini
- No schema conversion needed on your end

### Pattern 2: Handling Tool Calls in Sequential Mode

```python
from litellm import completion

def agent_loop_with_tools():
    messages = [
        {"role": "user", "content": "Find async patterns in code"}
    ]

    while True:
        response = completion(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        # Check for tool calls
        if response.choices[0].message.tool_calls:
            # Process each tool call sequentially
            for tool_call in response.choices[0].message.tool_calls:
                result = execute_tool(
                    tool_call.function.name,
                    json.loads(tool_call.function.arguments)
                )

                # Add assistant response
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call]
                })

                # Add tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })

        elif response.choices[0].finish_reason == "stop":
            return response.choices[0].message.content
        else:
            break

def execute_tool(name: str, args: dict):
    if name == "search_codebase":
        return {"results": ["found patterns..."]}
    elif name == "read_file":
        return {"content": "file contents..."}
```

**Tool Call Handling:**
- Check `response.choices[0].message.tool_calls`
- Preserve tool_call_id for result mapping
- Iterate sequentially for each tool call
- Add results as tool messages

### Pattern 3: Parallel Tool Calls (With Caveats)

```python
from litellm import completion

async def parallel_tool_calls():
    # IMPORTANT: parallel_tool_calls parameter support varies

    response = completion(
        model="gpt-4o-mini",  # OpenAI: fully supported
        messages=[{"role": "user", "content": "Process multiple items"}],
        tools=tools,
        parallel_tool_calls=True,  # Enable parallel execution
        tool_choice="auto"
    )

    if response.choices[0].message.tool_calls:
        tool_calls = response.choices[0].message.tool_calls

        # Execute ALL tool calls in parallel
        import asyncio

        results = await asyncio.gather(*[
            execute_tool_async(tc.function.name, json.loads(tc.function.arguments))
            for tc in tool_calls
        ])

        # Build messages - all results in ONE assistant message
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls  # All calls in one message
        })

        # Add all results
        for tool_call, result in zip(tool_calls, results):
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })
```

**Parallel Call Constraints:**
- OpenAI: Full support
- Anthropic: Supported but not well-documented
- Gemini: Raises `UnsupportedParamsError` - NOT supported in LiteLLM
- Bedrock: Multiple message format issue when converting results

### Pattern 4: Checking Provider Capabilities

```python
from litellm import supports_parallel_function_calling

def select_calling_strategy(model: str):
    if supports_parallel_function_calls(model=model):
        # Use parallel execution
        parallel_tool_calls = True
    else:
        # Fall back to sequential
        parallel_tool_calls = False

    return {
        "model": model,
        "parallel_tool_calls": parallel_tool_calls,
        "messages": [...],
        "tools": [...]
    }
```

**Provider Detection:**
- Use `supports_parallel_function_calling()` before setting parameter
- Prevents `UnsupportedParamsError` on Gemini/others
- Enables provider-agnostic agent code

---

## Provider Fallback Strategies

### Strategy 1: Simple-Shuffle Router (Recommended for Production)

```python
from litellm import Router

# Recommended configuration for production
router = Router(
    model_list=[
        {
            "model_name": "gpt-4o-mini",
            "litellm_params": {
                "model": "openai/gpt-4o-mini",
                "api_key": "sk-...",
                "rpm": 3500,  # Requests per minute
                "tpm": 90000  # Tokens per minute
            },
            "order": 1  # Try first
        },
        {
            "model_name": "gpt-4o-mini",
            "litellm_params": {
                "model": "azure/gpt-4o-mini",
                "api_key": "...",
                "api_base": "...",
                "rpm": 2500,
                "tpm": 60000
            },
            "order": 2  # Fallback
        },
        {
            "model_name": "gpt-4o-mini",
            "litellm_params": {
                "model": "openai/gpt-4-turbo",
                "api_key": "...",
                "rpm": 500,
                "tpm": 150000
            },
            "order": 3  # Last resort
        }
    ],
    routing_strategy="simple-shuffle",  # Default, recommended
    fallback_multiplier=1.5,  # Scale limits for fallback
    timeout=30,
    num_retries=3  # Retry failed calls
)

# Use as normal
response = router.completion(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**Simple-Shuffle Benefits:**
- Minimal latency overhead (recommended for production)
- Respects RPM/TPM limits
- Automatic fallback when primary exhausted
- Order parameter prioritizes deployments

### Strategy 2: Retry and Cooldown Configuration

```python
from litellm import Router
from litellm.router import RetryPolicy, AllowedFailsPolicy

# Define custom retry behavior per error type
retry_policy = RetryPolicy(
    ContentPolicyViolationErrorRetries=3,  # Transient usually
    AuthenticationErrorRetries=0,  # Don't retry auth fails
    BadRequestErrorRetries=1,  # Likely input issue
    TimeoutErrorRetries=2,
    RateLimitErrorRetries=3,  # Exponential backoff applied
    APIConnectionErrorRetries=2
)

# Define when to cooldown a deployment
allowed_fails_policy = AllowedFailsPolicy(
    ContentPolicyViolationErrorAllowedFails=1000,
    RateLimitErrorAllowedFails=100,  # Cooldown after 100 fails/min
    AuthenticationErrorAllowedFails=1,  # Cooldown immediately
)

router = Router(
    model_list=[...],
    routing_strategy="simple-shuffle",
    retry_policy=retry_policy,
    allowed_fails_policy=allowed_fails_policy,
    cooldown_time=30  # Cooldown duration in seconds
)

# When deployment is rate-limited or fails, router:
# 1. Retries up to retry_policy limit
# 2. Cools down if hits allowed_fails threshold
# 3. Falls back to next deployment in order
```

**Retry Flow:**
1. Request sent to primary deployment (order=1)
2. If fails, retry per `retry_policy` (exponential backoff for rate limits)
3. If exceeds `allowed_fails`, cooldown for `cooldown_time`
4. Fallback to next deployment (order=2)
5. Repeat until success or all exhausted

### Strategy 3: Cost-Based Routing with Fallback

```python
from litellm import Router

# Route to cheapest provider first
router = Router(
    model_list=[
        {
            "model_name": "claude-3-haiku",
            "litellm_params": {
                "model": "anthropic/claude-3-haiku-20240307",
                "api_key": "...",
                "rpm": 4000,
                "tpm": 1000000
            },
            "order": 1  # Cheapest, try first
        },
        {
            "model_name": "claude-3-haiku",
            "litellm_params": {
                "model": "openai/gpt-3.5-turbo",
                "api_key": "...",
                "rpm": 3500,
                "tpm": 90000
            },
            "order": 2  # More expensive fallback
        }
    ],
    routing_strategy="simple-shuffle",
    fallback_multiplier=2.0  # If primary full, scale limits
)
```

### Strategy 4: Latency-Based Routing

```python
from litellm import Router

# Route to fastest responder
router = Router(
    model_list=[...],
    routing_strategy="latency-based",
    latency_threshold=1.0  # Buffer zone in seconds
)

# Routes to deployment with lowest latency
# Won't overload top performer due to threshold buffer
```

### Strategy 5: Context Window Pre-Validation

```python
from litellm import Router, get_max_tokens

# Pre-check context window before routing
def check_deployment_capacity(model: str, messages: list):
    max_ctx = get_max_tokens(model)
    token_count = estimate_tokens(messages)

    if token_count > max_ctx * 0.8:  # Safety margin
        print(f"Model {model} lacks context capacity")
        # Router will skip this in next request
```

### Known Issues & Workarounds

**Issue 1: usage-based-routing-v2 Broken Retry Logic**
```python
# PROBLEM: usage-based-routing-v2 ignores all retry settings
# and immediately retries rate-limit errors causing failures

# WORKAROUND: Use simple-shuffle instead
router = Router(
    model_list=[...],
    routing_strategy="simple-shuffle"  # Recommended, works properly
)
```

**Issue 2: Bedrock Multi-Message Format**
```python
# PROBLEM: When converting parallel tool results to Bedrock format,
# LiteLLM creates 2 messages with single content blocks
# instead of 1 message with array of content blocks

# WORKAROUND: Convert parallel to sequential for Bedrock
if "bedrock" in model:
    parallel_tool_calls = False
else:
    parallel_tool_calls = True
```

---

## Token Management

### Pattern 1: Token Counting Per Provider

```python
from litellm import token_counter, cost_per_token, completion_cost
import litellm

# Get token count for specific model
messages = [
    {"role": "user", "content": "Explain LiteLLM"}
]

# Count input tokens
input_tokens = token_counter(
    model="gpt-4o-mini",
    messages=messages
)

# Get per-token costs
prompt_cost, completion_cost_per_token = cost_per_token(model="gpt-4o-mini")

# Calculate total cost for completion
response = completion(
    model="gpt-4o-mini",
    messages=messages
)

total_cost = response.usage.prompt_tokens * prompt_cost + \
             response.usage.completion_tokens * completion_cost_per_token

print(f"Cost: ${total_cost:.4f}")
```

**Supported Tokenizers:**
- OpenAI: tiktoken
- Anthropic: Claude tokenizer
- Cohere: Cohere tokenizer
- Llama2/Llama3: HuggingFace tokenizers
- Others: Fallback to tiktoken (may be inaccurate)

### Pattern 2: Context Window Management

```python
from litellm import get_max_tokens, completion

def safe_completion_with_context_check(model: str, messages: list):
    # Get model's max context
    max_tokens = get_max_tokens(model)

    # Estimate current usage
    input_tokens = token_counter(model=model, messages=messages)

    # Reserve tokens for response
    max_response_tokens = 4000
    available_for_context = max_tokens - max_response_tokens

    if input_tokens > available_for_context:
        print(f"Input exceeds context: {input_tokens}/{available_for_context}")
        # Implement sliding window or summarization
        messages = summarize_old_messages(messages, available_for_context)

    response = completion(
        model=model,
        messages=messages,
        max_tokens=max_response_tokens
    )

    return response
```

**Context Window Strategy:**
- Check `get_max_tokens(model)` upfront
- Reserve tokens for response generation
- Implement sliding window for long conversations
- Truncate intelligently (preserve recent + critical context)

### Pattern 3: Streaming with Token Tracking

```python
from litellm import acompletion

async def stream_with_token_usage():
    response = await acompletion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Stream response"}],
        stream=True,
        stream_options={"include_usage": True}  # Enable token tracking
    )

    total_prompt_tokens = 0
    total_completion_tokens = 0

    async for chunk in response:
        # Regular content chunk
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")

        # Final chunk with usage
        if chunk.usage:
            total_prompt_tokens = chunk.usage.prompt_tokens
            total_completion_tokens = chunk.usage.completion_tokens

    print(f"\nTokens - Prompt: {total_prompt_tokens}, Completion: {total_completion_tokens}")
    return total_prompt_tokens, total_completion_tokens
```

**Streaming Token Tracking:**
- Set `stream_options={"include_usage": True}`
- Final chunk contains aggregate token counts
- Usage appears in last chunk's `chunk.usage`

### Pattern 4: Custom Model Registration

```python
from litellm import register_model

# Register custom model with pricing
register_model(
    model="local-llama-2",
    litellm_model="custom/llama-2",
    cost_per_token={
        "input": 0.0001,  # Cheap local model
        "output": 0.0002
    },
    max_tokens=4096,
    mode="completion"  # or "chat"
)

# Register from pricing JSON
register_model(
    model="azure-gpt4",
    litellm_model="azure/gpt-4",
    model_cost="https://example.com/pricing.json"
)
```

### Pattern 5: Cost Tracking in Agents

```python
from litellm import completion

class CostTrackingAgent:
    def __init__(self, budget_limit: float = 1.0):
        self.total_cost = 0
        self.budget_limit = budget_limit
        self.call_history = []

    def run(self, messages):
        if self.total_cost > self.budget_limit:
            raise Exception(f"Budget exceeded: ${self.total_cost:.2f}")

        response = completion(
            model="gpt-4o-mini",
            messages=messages
        )

        # Track cost
        cost = response.get("cost", 0)
        self.total_cost += cost
        self.call_history.append({
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "cost": cost
        })

        print(f"Total spent: ${self.total_cost:.4f} / ${self.budget_limit:.2f}")
        return response
```

### Known Issues

**Issue: Token Counting Inaccuracy with vLLM**
```python
# PROBLEM: LiteLLM /utils/token_counter with vLLM
# defaults to tiktoken which is inaccurate for Gemma2, Mistral

# WORKAROUND 1: Use model's native tokenizer
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("mistralai/Mistral-7B")
tokens = tokenizer.encode(text)

# WORKAROUND 2: Request vLLM directly
import requests
response = requests.post("http://vllm-server/v1/token/count", json={"prompt": text})
```

---

## Implementation Recommendations

### Architecture Pattern for AI Coding Agent

```python
import asyncio
from litellm import Router, acompletion
from litellm.router import RetryPolicy

class CodeAnalysisAgent:
    def __init__(self):
        # Setup router with fallbacks
        self.router = Router(
            model_list=[
                {
                    "model_name": "gpt-4o-mini",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "...",
                        "rpm": 3500,
                        "tpm": 90000
                    },
                    "order": 1
                },
                {
                    "model_name": "gpt-4o-mini",
                    "litellm_params": {
                        "model": "azure/gpt-4o-mini",
                        "api_key": "...",
                        "rpm": 2500,
                        "tpm": 60000
                    },
                    "order": 2
                }
            ],
            routing_strategy="simple-shuffle",
            num_retries=3,
            timeout=30
        )

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "Search codebase",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "file_pattern": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file contents",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        },
                        "required": ["path"]
                    }
                }
            }
        ]

        self.total_tokens = {"prompt": 0, "completion": 0}

    async def stream_analysis(self, query: str):
        """Stream code analysis with tool calls"""
        messages = [
            {"role": "user", "content": f"Analyze code: {query}"}
        ]

        try:
            # Streaming completion with tool support
            response = await acompletion(
                model="gpt-4o-mini",
                messages=messages,
                tools=self.tools,
                stream=True,
                stream_options={"include_usage": True},
                timeout=30
            )

            buffer = ""
            async for chunk in response:
                # Handle streamed content
                if chunk.choices[0].delta.content:
                    buffer += chunk.choices[0].delta.content
                    yield chunk.choices[0].delta.content

                # Handle tool calls
                if hasattr(chunk.choices[0].delta, 'tool_calls'):
                    for tool_call in chunk.choices[0].delta.tool_calls or []:
                        yield f"\n[Executing: {tool_call.function.name}]"

                # Track tokens
                if chunk.usage:
                    self.total_tokens["prompt"] = chunk.usage.prompt_tokens
                    self.total_tokens["completion"] = chunk.usage.completion_tokens

        except Exception as e:
            yield f"\nError: {type(e).__name__}: {e}"

    async def interactive_analysis_loop(self, query: str):
        """Multi-turn analysis with tool calling"""
        messages = [
            {"role": "user", "content": f"Analyze: {query}"}
        ]

        max_turns = 5
        turn = 0

        while turn < max_turns:
            turn += 1

            # Get response with tools
            response = self.router.completion(
                model="gpt-4o-mini",
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )

            # Check for tool calls
            if response.choices[0].message.tool_calls:
                # Execute tools
                tool_results = []
                for tool_call in response.choices[0].message.tool_calls:
                    result = await self.execute_tool(
                        tool_call.function.name,
                        json.loads(tool_call.function.arguments)
                    )
                    tool_results.append((tool_call, result))

                # Add assistant response
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": response.choices[0].message.tool_calls
                })

                # Add tool results
                for tool_call, result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })

            elif response.choices[0].finish_reason == "stop":
                # Final answer
                return response.choices[0].message.content

            else:
                break

        return "Max turns exceeded"

    async def execute_tool(self, name: str, args: dict):
        """Execute tool and return results"""
        if name == "search_code":
            return {"results": ["Found patterns..."]}
        elif name == "read_file":
            return {"content": "File contents..."}

# Usage
async def main():
    agent = CodeAnalysisAgent()

    # Stream analysis
    print("Streaming analysis:")
    async for chunk in agent.stream_analysis("Find async patterns"):
        print(chunk, end="")

    print(f"\nTokens used: {agent.total_tokens}")

asyncio.run(main())
```

### Best Practices Checklist

- [ ] Use `async for` with `acompletion()` for true streaming
- [ ] Enable `stream_options={"include_usage": True}` for token tracking
- [ ] Use `Router` with `simple-shuffle` strategy for production
- [ ] Configure `RetryPolicy` per error type
- [ ] Check `supports_parallel_function_calling()` before using parallel calls
- [ ] Pre-validate context window with `get_max_tokens()`
- [ ] Implement exponential backoff for rate limits
- [ ] Track costs with `completion_cost` per request
- [ ] Use `timeout` parameter to prevent hanging
- [ ] Set `REPEATED_STREAMING_CHUNK_LIMIT` appropriately

---

## Common Pitfalls

### Pitfall 1: Fake Streaming with Synchronous Iteration

**Problem:**
```python
# WRONG: Synchronous for loop waits for entire iterator
response = acompletion(...)  # Missing await!
for chunk in response:  # Blocking iteration
    print(chunk)
```

**Solution:**
```python
# CORRECT: Async iteration
response = await acompletion(...)
async for chunk in response:
    print(chunk)
```

### Pitfall 2: Not Awaiting acompletion()

**Problem:**
```python
# Creates coroutine but doesn't execute
response = acompletion(model="gpt-4", messages=[...])
async for chunk in response:  # Error: not awaited
    print(chunk)
```

**Solution:**
```python
# Must await before iteration
response = await acompletion(model="gpt-4", messages=[...])
async for chunk in response:
    print(chunk)
```

### Pitfall 3: Parallel Calls on Unsupported Models

**Problem:**
```python
response = completion(
    model="gemini-2-flash",
    messages=[...],
    parallel_tool_calls=True  # Raises UnsupportedParamsError
)
```

**Solution:**
```python
from litellm import supports_parallel_function_calling

if supports_parallel_function_calling(model="gemini-2-flash"):
    parallel_calls = True
else:
    parallel_calls = False

response = completion(
    model="gemini-2-flash",
    messages=[...],
    parallel_tool_calls=parallel_calls
)
```

### Pitfall 4: Not Setting Timeout in Streaming

**Problem:**
```python
# Can hang indefinitely if connection drops
response = await acompletion(...)
async for chunk in response:
    # No timeout = potential infinite wait
    print(chunk)
```

**Solution:**
```python
response = await acompletion(
    model="gpt-4",
    messages=[...],
    stream=True,
    timeout=30  # Prevent hanging
)
```

### Pitfall 5: Ignoring Provider Differences in Tool Results

**Problem:**
```python
# Assumes OpenAI format works everywhere
messages.append({
    "role": "tool",  # Not valid for Anthropic
    "tool_call_id": "...",
    "content": "..."
})
```

**Solution:**
```python
# LiteLLM handles conversion, but be aware:
# - OpenAI uses "tool" role
# - Anthropic/Gemini use content blocks
# - LiteLLM translates internally

# Just use OpenAI format - LiteLLM converts
messages.append({
    "role": "tool",
    "tool_call_id": "...",
    "content": "..."
})
```

### Pitfall 6: Not Implementing Backoff for Rate Limits

**Problem:**
```python
response = router.completion(model="gpt-4", messages=[...])
# If rate limited, fails immediately
```

**Solution:**
```python
from litellm.router import RetryPolicy

retry_policy = RetryPolicy(RateLimitErrorRetries=3)
router = Router(
    model_list=[...],
    retry_policy=retry_policy
    # Exponential backoff applied automatically
)
```

### Pitfall 7: Streaming Tool Calls Not Fully Streamed

**Problem:**
```python
# Tool arguments may not stream incrementally
async for chunk in response:
    if chunk.choices[0].delta.tool_calls:
        # Tool function name and ID stream, but arguments
        # may arrive in large batches
        print(chunk.choices[0].delta.tool_calls[0].function.arguments)
```

**Note:** Provider-dependent. Use `buffer` pattern for reliable collection.

---

## Resources

### Official Documentation

- [LiteLLM Streaming + Async](https://docs.litellm.ai/docs/completion/stream)
- [LiteLLM Router & Load Balancing](https://docs.litellm.ai/docs/routing)
- [LiteLLM Function Calling](https://docs.litellm.ai/docs/completion/function_call)
- [LiteLLM Token Usage & Cost](https://docs.litellm.ai/docs/completion/token_usage)
- [LiteLLM Providers Documentation](https://docs.litellm.ai/docs/providers)
- [LiteLLM Anthropic Integration](https://docs.litellm.ai/docs/providers/anthropic)
- [LiteLLM Vertex AI / Gemini](https://docs.litellm.ai/docs/providers/vertex)

### GitHub Resources

- [LiteLLM GitHub Repository](https://github.com/BerriAI/litellm)
- [OpenAI Responses API Integration](https://docs.litellm.ai/docs/anthropic_unified)
- [Structured Outputs / JSON Mode](https://docs.litellm.ai/docs/completion/json_mode)

### Known Issues Tracked

- Parallel tool calls unsupported on Gemini models (#9686)
- Bedrock multi-message format issue for tool results (#5277)
- usage-based-routing-v2 retry logic broken (#7669)
- Token counting inaccuracy with vLLM-hosted models (#8244)

### Community Resources

- LiteLLM GitHub Issues
- LiteLLM Discord Community
- Stack Overflow tag: litellm

---

## Appendices

### A. Glossary

**acompletion:** Asynchronous version of completion function for non-blocking I/O

**RPM:** Requests per minute (rate limit)

**TPM:** Tokens per minute (rate limit)

**Tool Call:** Function invocation requested by LLM

**Streaming:** Incremental response delivery (chunks)

**Router:** Load balancer managing multiple LLM deployments

**Fallback:** Alternative deployment when primary unavailable

**Cooldown:** Temporary isolation of failing deployment

**Context Window:** Maximum number of tokens in conversation

**Parallel Tool Calls:** Multiple functions executed simultaneously

### B. Version Compatibility Matrix

| Feature | OpenAI | Anthropic | Gemini | Azure | Bedrock |
|---------|--------|-----------|--------|-------|---------|
| Async Streaming | ✓ | ✓ | ✓ | ✓ | ✓ |
| Tool Calling | ✓ | ✓ | ✓ | ✓ | ✓ |
| Parallel Calls | ✓ | ✓ | ✗ | ✓ | ✗ |
| JSON Mode | ✓ | ✓ | ✓ | ✓ | ~ |
| Token Counting | ✓ | ✓ | ✓ | ✓ | ~ |

### C. Migration Guide: OpenAI → LiteLLM

Change model name from `gpt-4-turbo` to `openai/gpt-4-turbo`:

```python
# Before
response = openai.ChatCompletion.create(model="gpt-4-turbo", ...)

# After
from litellm import completion
response = completion(model="openai/gpt-4-turbo", ...)
```

All request/response structures remain OpenAI-compatible. No other changes needed.

---

## Unresolved Questions

1. **Gemini Parallel Tool Calls:** Will parallel tool call support be added to Gemini in 2025? Current status: open issue #9686 on GitHub.

2. **vLLM Token Accuracy:** Is there a roadmap for accurate tokenization with vLLM-hosted Gemma/Mistral models?

3. **usage-based-routing-v2:** When will retry logic and `retry-after` header support be fixed?

4. **Bedrock Format Conversion:** Will tool result format conversion be fixed to handle parallel calls properly?

5. **Custom Tokenizers:** Best practices for plugging custom tokenizers for specialized models not in default list?

---

**Document Generated:** 2025-12-25
**Research Scope:** LiteLLM 1.80+ for AI Coding Agents
**Next Review:** Q1 2026 (expect new provider integrations and improvements)
