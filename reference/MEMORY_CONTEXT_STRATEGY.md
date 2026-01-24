# Memory Context Strategy

This document explains how Mistral Vibe manages the LLM context window to prevent overloading while maintaining conversation coherence.

## Table of Contents

- [Overview](#overview)
- [Token Tracking System](#token-tracking-system)
- [Middleware Pipeline](#middleware-pipeline)
- [Auto-Compaction Strategy](#auto-compaction-strategy)
- [Compaction Prompt Design](#compaction-prompt-design)
- [Context Warning System](#context-warning-system)
- [Configuration Options](#configuration-options)
- [Best Practices](#best-practices)

---

## Overview

LLM context windows have finite capacity. As conversations grow with messages, tool calls, and tool results, the context can exceed model limits. Mistral Vibe implements a **multi-layered defense strategy** to manage this:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CONTEXT MANAGEMENT LAYERS                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Layer 1: TRACKING                                                 │
│   ├── Monitor token usage per turn                                  │
│   └── Track cumulative context size                                 │
│                                                                     │
│   Layer 2: WARNING                                                  │
│   ├── Alert at 50% of threshold                                    │
│   └── Inject message to inform LLM                                  │
│                                                                     │
│   Layer 3: AUTO-COMPACTION                                          │
│   ├── Trigger at threshold                                          │
│   └── Summarize history, preserve intent                            │
│                                                                     │
│   Layer 4: HARD LIMITS                                              │
│   ├── Turn limits                                                   │
│   └── Cost limits                                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Token Tracking System

### AgentStats Model

The agent maintains detailed token statistics in `AgentStats` (`core/types.py`):

```python
class AgentStats(BaseModel):
    # Session-level cumulative counts
    session_prompt_tokens: int = 0
    session_completion_tokens: int = 0

    # Current context size (prompt + completion of last turn)
    context_tokens: int = 0

    # Last turn breakdown
    last_turn_prompt_tokens: int = 0
    last_turn_completion_tokens: int = 0
    last_turn_duration: float = 0.0
    tokens_per_second: float = 0.0
```

### How Tokens Are Updated

After each LLM call, the agent updates statistics:

```python
def _update_stats(self, usage: LLMUsage, time_seconds: float) -> None:
    self.stats.last_turn_prompt_tokens = usage.prompt_tokens
    self.stats.last_turn_completion_tokens = usage.completion_tokens
    self.stats.session_prompt_tokens += usage.prompt_tokens
    self.stats.session_completion_tokens += usage.completion_tokens
    self.stats.context_tokens = usage.prompt_tokens + usage.completion_tokens
```

> **Note**: `context_tokens` represents the current context size, not the cumulative total. After compaction, this value decreases significantly.

---

## Middleware Pipeline

Mistral Vibe uses a **middleware pipeline pattern** for extensible context management. Each middleware can inspect the conversation context and return actions.

### Middleware Protocol

```python
class ConversationMiddleware(Protocol):
    async def before_turn(self, context: ConversationContext) -> MiddlewareResult
    async def after_turn(self, context: ConversationContext) -> MiddlewareResult
    def reset(self, reset_reason: ResetReason) -> None
```

### Available Middleware Actions

| Action | Effect |
|--------|--------|
| `CONTINUE` | Proceed normally |
| `STOP` | Halt the conversation loop |
| `COMPACT` | Trigger context compaction |
| `INJECT_MESSAGE` | Add a system message to the context |

### Context Management Middleware

```python
# Configured in Agent._setup_middleware()

if config.auto_compact_threshold > 0:
    # Trigger compaction when threshold exceeded
    pipeline.add(AutoCompactMiddleware(config.auto_compact_threshold))

    if config.context_warnings:
        # Warn at 50% of threshold
        pipeline.add(ContextWarningMiddleware(0.5, config.auto_compact_threshold))
```

---

## Auto-Compaction Strategy

When context tokens exceed the threshold, the `AutoCompactMiddleware` triggers compaction.

### Compaction Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      COMPACTION PROCESS                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   1. SAVE CURRENT STATE                                             │
│      └── Persist full history to session log                        │
│                                                                     │
│   2. EXTRACT LAST USER INTENT                                       │
│      └── Find most recent user message                              │
│                                                                     │
│   3. REQUEST LLM SUMMARY                                            │
│      ├── Append compact prompt to messages                          │
│      └── LLM generates structured summary                           │
│                                                                     │
│   4. REPLACE HISTORY                                                │
│      ├── Keep: [system_prompt]                                      │
│      ├── Add:  [summary_message]                                    │
│      └── Append: "Last request from user was: ..."                  │
│                                                                     │
│   5. RECALCULATE TOKENS                                             │
│      └── Count actual tokens in new context                         │
│                                                                     │
│   6. RESET STATE                                                    │
│      ├── Reset middleware (warning flags, etc.)                     │
│      └── Start new session ID                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Implementation

```python
async def compact(self) -> str:
    # Save current state for recovery
    await self.interaction_logger.save_interaction(...)

    # Find user's last request
    last_user_message = None
    for msg in reversed(self.messages):
        if msg.role == Role.user:
            last_user_message = msg.content
            break

    # Ask LLM for summary
    summary_request = UtilityPrompt.COMPACT.read()
    self.messages.append(LLMMessage(role=Role.user, content=summary_request))
    summary_result = await self._chat()

    # Preserve user's last intent
    summary_content = summary_result.message.content
    if last_user_message:
        summary_content += f"\n\nLast request from user was: {last_user_message}"

    # Replace history with compact version
    system_message = self.messages[0]
    summary_message = LLMMessage(role=Role.user, content=summary_content)
    self.messages = [system_message, summary_message]

    # Recalculate actual token count
    self.stats.context_tokens = await backend.count_tokens(...)

    # Reset for fresh state
    self.middleware_pipeline.reset(reset_reason=ResetReason.COMPACT)

    return summary_content
```

---

## Compaction Prompt Design

The compaction prompt (`prompts/compact.md`) is carefully designed to preserve maximum context in minimal tokens:

### Prompt Structure

```markdown
Create a comprehensive summary of our entire conversation that will serve
as complete context for continuing this work.

Your summary must include these sections in order:

## 1. User's Primary Goals and Intent
Capture ALL explicit requests and objectives...

## 2. Conversation Timeline and Progress
Chronologically document the key phases...

## 3. Technical Context and Decisions
Technologies, frameworks, patterns, constraints...

## 4. Files and Code Changes
Full file paths, changes made, current state...

## 5. Active Work and Last Actions
CRITICAL: Detail EXACTLY what was being worked on...

## 6. Unresolved Issues and Pending Tasks
Errors, pending tasks, awaiting decisions...

## 7. Immediate Next Step
State the SPECIFIC next action to take...
```

### Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Structured sections** | Ensures no category of information is lost |
| **Chronological timeline** | Preserves cause-and-effect relationships |
| **Explicit file paths** | Enables continuing file edits accurately |
| **Last action emphasis** | Prevents context loss at critical moments |
| **Next step specification** | Maintains momentum after compaction |

---

## Context Warning System

The `ContextWarningMiddleware` provides early warning before hitting limits.

### Warning Injection

```python
class ContextWarningMiddleware:
    def __init__(self, threshold_percent: float = 0.5, max_context: int | None = None):
        self.threshold_percent = threshold_percent
        self.max_context = max_context
        self.has_warned = False

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        if self.has_warned:
            return MiddlewareResult()

        if context.stats.context_tokens >= max_context * self.threshold_percent:
            self.has_warned = True

            percentage_used = (context.stats.context_tokens / max_context) * 100
            warning_msg = f"<vibe_warning>You have used {percentage_used:.0f}% of your total context ({context.stats.context_tokens:,}/{max_context:,} tokens)</vibe_warning>"

            return MiddlewareResult(
                action=MiddlewareAction.INJECT_MESSAGE,
                message=warning_msg
            )
```

### Warning Effects

When the warning is injected:
1. The LLM becomes aware of context constraints
2. It may naturally be more concise
3. It may suggest running `/compact` command
4. User can manually trigger compaction via `/compact`

---

## Configuration Options

### config.toml Settings

```toml
# Token threshold for auto-compaction (0 = disabled)
auto_compact_threshold = 200000

# Enable warning at 50% of threshold
context_warnings = false
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `/compact` | Manually trigger compaction |
| `/clear` | Clear all history (fresh start) |
| `/status` | View current token usage |

### Environment Variables

```bash
# Override via environment
export VIBE_AUTO_COMPACT_THRESHOLD=150000
export VIBE_CONTEXT_WARNINGS=true
```

---

## Best Practices

### 1. Choosing the Right Threshold

| Model Context Size | Recommended Threshold | Rationale |
|-------------------|----------------------|-----------|
| 8K tokens | 4,000 - 6,000 | Leave room for response |
| 32K tokens | 20,000 - 25,000 | Balance between history and headroom |
| 128K tokens | 80,000 - 100,000 | Generous history, safe margin |
| 200K+ tokens | 150,000 - 200,000 | Default setting |

### 2. When to Manually Compact

- Before starting a completely new task (clean context)
- When conversation has drifted significantly from original goal
- When LLM seems confused by conflicting earlier instructions

### 3. When to Clear Instead

- Starting work on a different project
- After completing a major milestone
- When the summary might carry over irrelevant context

### 4. Monitoring Token Usage

Use `/status` command to check:
```
## Agent Statistics

- **Steps**: 15
- **Session Prompt Tokens**: 45,000
- **Session Completion Tokens**: 12,000
- **Session Total LLM Tokens**: 57,000
- **Last Turn Tokens**: 3,500
- **Cost**: $0.0234
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONTEXT LIFECYCLE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    User Message ────────────────────────────────────────────────────────►   │
│         │                                                                   │
│         ▼                                                                   │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │ Middleware Pipeline: before_turn()                              │     │
│    │  ├─ TurnLimitMiddleware: check turn count                       │     │
│    │  ├─ PriceLimitMiddleware: check cost                            │     │
│    │  ├─ AutoCompactMiddleware: check context_tokens >= threshold    │     │
│    │  │      └─► Returns COMPACT action if exceeded                  │     │
│    │  └─ ContextWarningMiddleware: warn at 50%                       │     │
│    └─────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ▼                                                                   │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │ If COMPACT action:                                              │     │
│    │  1. Yield CompactStartEvent                                     │     │
│    │  2. await self.compact()                                        │     │
│    │  3. Yield CompactEndEvent                                       │     │
│    │  4. Continue with reduced context                               │     │
│    └─────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ▼                                                                   │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │ LLM Call: _chat() or _chat_streaming()                          │     │
│    │  └─ _update_stats() updates context_tokens                      │     │
│    └─────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ▼                                                                   │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │ Tool Execution (if any)                                         │     │
│    │  └─ Tool results added to messages                              │     │
│    └─────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ▼                                                                   │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │ Middleware Pipeline: after_turn()                               │     │
│    │  └─ Check if should continue loop                               │     │
│    └─────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ▼                                                                   │
│    Continue or Stop ────────────────────────────────────────────────────►   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Related Documentation

- [PERSISTENCE_STATE.md](./PERSISTENCE_STATE.md) - Session persistence and resume
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
