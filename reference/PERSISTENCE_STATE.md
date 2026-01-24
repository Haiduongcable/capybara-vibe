# Persistence & State Management

This document explains how Mistral Vibe persists agent state and enables session resumption across CLI invocations.

## Table of Contents

- [Overview](#overview)
- [Session Logging System](#session-logging-system)
- [Session File Structure](#session-file-structure)
- [Resume Mechanisms](#resume-mechanisms)
- [State Restoration Process](#state-restoration-process)
- [What Is Persisted](#what-is-persisted)
- [What Is NOT Persisted](#what-is-not-persisted)
- [Configuration Options](#configuration-options)
- [Use Cases](#use-cases)
- [Troubleshooting](#troubleshooting)

---

## Overview

Mistral Vibe automatically saves conversation state to disk, enabling users to:

- **Continue** the most recent session
- **Resume** any specific session by ID
- **Audit** past conversations
- **Recover** from interruptions

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PERSISTENCE OVERVIEW                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ACTIVE SESSION                           DISK STORAGE             │
│   ┌─────────────────┐                      ┌─────────────────┐     │
│   │ Agent           │    Auto-save at      │ ~/.vibe/logs/   │     │
│   │ ├── messages[]  │ ─────────────────►   │ session_*.json  │     │
│   │ ├── stats       │    key moments       │                 │     │
│   │ └── config      │                      └─────────────────┘     │
│   └─────────────────┘                              │               │
│                                                    │               │
│   NEW SESSION                                      │               │
│   ┌─────────────────┐                              │               │
│   │ vibe --continue │ ◄────────────────────────────┘               │
│   │ vibe --resume X │    Load & restore                            │
│   └─────────────────┘                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Session Logging System

### InteractionLogger Class

The `InteractionLogger` (`core/interaction_logger.py`) handles all persistence operations:

```python
class InteractionLogger:
    def __init__(
        self,
        session_config: SessionLoggingConfig,
        session_id: str,
        auto_approve: bool = False,
        workdir: Path | None = None,
    ) -> None:
        self.enabled = session_config.enabled
        self.save_dir = Path(session_config.save_dir)
        self.session_id = session_id
        self.session_start_time = datetime.now().isoformat()
        self.filepath = self._get_save_filepath()
        self.session_metadata = self._initialize_session_metadata()
```

### Auto-Save Trigger Points

Sessions are automatically saved at these moments:

| Trigger | Location | Purpose |
|---------|----------|---------|
| After each conversation turn | `_conversation_loop()` finally block | Ensure no data loss on interruption |
| Before compaction | `compact()` | Preserve full history before summarizing |
| After compaction | `compact()` | Save the reduced state |
| On clear history | `clear_history()` | Archive before clearing |
| On config reload | `reload_with_initial_messages()` | Preserve state across reloads |
| On app exit | App teardown | Final state capture |

### Session File Naming

```
session_{timestamp}_{session_id[:8]}.json
         │              │
         │              └── First 8 chars of UUID
         └── Format: YYYYMMDD_HHMMSS
```

Example: `session_20260106_160230_7dcdccef.json`

---

## Session File Structure

Each session is stored as a comprehensive JSON file:

```json
{
  "metadata": {
    "session_id": "7dcdccef-c0fb-4a57-ad44-0e438d4c157d",
    "start_time": "2026-01-06T16:02:30.123456",
    "end_time": "2026-01-06T16:45:12.654321",
    "git_commit": "abc123def456789...",
    "git_branch": "feature/new-feature",
    "auto_approve": false,
    "username": "developer",
    "environment": {
      "working_directory": "/Users/developer/project"
    },
    "stats": {
      "steps": 15,
      "session_prompt_tokens": 45000,
      "session_completion_tokens": 12000,
      "context_tokens": 8500,
      "tool_calls_agreed": 8,
      "tool_calls_rejected": 2,
      "tool_calls_failed": 1,
      "tool_calls_succeeded": 7,
      "last_turn_prompt_tokens": 3000,
      "last_turn_completion_tokens": 500,
      "last_turn_duration": 2.34,
      "tokens_per_second": 213.67,
      "input_price_per_million": 0.4,
      "output_price_per_million": 2.0
    },
    "total_messages": 24,
    "tools_available": [
      {
        "type": "function",
        "function": {
          "name": "read_file",
          "description": "Read contents of a file...",
          "parameters": { ... }
        }
      }
    ],
    "agent_config": {
      "active_model": "devstral-2",
      "auto_compact_threshold": 200000,
      ...
    }
  },
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful coding assistant..."
    },
    {
      "role": "user",
      "content": "Help me fix the bug in main.py"
    },
    {
      "role": "assistant",
      "content": "I'll help you fix the bug...",
      "tool_calls": [
        {
          "id": "call_abc123",
          "function": {
            "name": "read_file",
            "arguments": "{\"path\": \"main.py\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "name": "read_file",
      "content": "# File contents here..."
    }
  ]
}
```

### Metadata Fields

| Field | Description |
|-------|-------------|
| `session_id` | Unique UUID for this session |
| `start_time` | ISO timestamp when session began |
| `end_time` | ISO timestamp of last save |
| `git_commit` | Current git HEAD hash |
| `git_branch` | Current git branch name |
| `auto_approve` | Whether auto-approve mode was active |
| `username` | System username |
| `environment` | Working directory and environment info |
| `stats` | Complete token and call statistics |
| `tools_available` | Snapshot of available tools |
| `agent_config` | Full agent configuration |

---

## Resume Mechanisms

### CLI Flags

Mistral Vibe provides two ways to resume sessions:

```bash
# Resume the most recent session
vibe --continue
vibe -c

# Resume a specific session by ID
vibe --resume 7dcdccef
vibe --resume 7dcd          # Partial ID works
vibe --resume 7dcdccef-c0fb-4a57-ad44-0e438d4c157d  # Full UUID works
```

### Session Discovery

```python
# Find most recent session (for --continue)
@staticmethod
def find_latest_session(config: SessionLoggingConfig) -> Path | None:
    save_dir = Path(config.save_dir)
    pattern = f"{config.session_prefix}_*.json"
    session_files = list(save_dir.glob(pattern))

    if not session_files:
        return None

    return max(session_files, key=lambda p: p.stat().st_mtime)

# Find session by ID (for --resume)
@staticmethod
def find_session_by_id(session_id: str, config: SessionLoggingConfig) -> Path | None:
    # Extract short form if full UUID provided
    short_id = session_id.split("-")[0] if "-" in session_id else session_id

    # Try exact match first, then partial
    patterns = [
        f"{prefix}_*_{short_id}.json",      # Exact short UUID
        f"{prefix}_*_{short_id}*.json",     # Partial UUID
    ]

    for pattern in patterns:
        matches = list(save_dir.glob(pattern))
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)

    return None
```

### Session Loading

```python
@staticmethod
def load_session(filepath: Path) -> tuple[list[LLMMessage], dict[str, Any]]:
    with filepath.open("r", encoding="utf-8") as f:
        content = f.read()

    data = json.loads(content)
    messages = [LLMMessage.model_validate(msg) for msg in data.get("messages", [])]
    metadata = data.get("metadata", {})

    return messages, metadata
```

---

## State Restoration Process

### Full Resume Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SESSION RESUME FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. CLI ENTRY                                                              │
│      └── parse_arguments() → args.continue_session or args.resume           │
│                                                                             │
│   2. VALIDATION                                                             │
│      └── Check session_logging.enabled in config                            │
│          └── Exit with error if disabled                                    │
│                                                                             │
│   3. SESSION DISCOVERY                                                      │
│      ├── --continue → find_latest_session()                                 │
│      └── --resume X → find_session_by_id(X)                                │
│          └── Exit with error if not found                                   │
│                                                                             │
│   4. SESSION LOADING                                                        │
│      └── load_session(filepath) → (messages[], metadata)                    │
│                                                                             │
│   5. AGENT INITIALIZATION                                                   │
│      ├── Create new Agent with current config                               │
│      ├── Generate FRESH system prompt (not from session)                    │
│      ├── Filter out system messages from loaded session                     │
│      └── Extend agent.messages with remaining messages                      │
│                                                                             │
│   6. UI RECONSTRUCTION (Interactive mode)                                   │
│      └── _rebuild_history_from_messages()                                   │
│          ├── Mount UserMessage for each user message                        │
│          ├── Mount AssistantMessage for each assistant message              │
│          ├── Mount ToolCallMessage for each tool call                       │
│          └── Mount ToolResultMessage for each tool result                   │
│                                                                             │
│   7. READY TO CONTINUE                                                      │
│      └── User can send new messages in the restored context                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why System Prompt Is Regenerated

The system prompt is **not restored from the session file**. Instead, it's regenerated fresh:

```python
# In Agent.__init__
system_prompt = get_universal_system_prompt(self.tool_manager, config, self.skill_manager)
self.messages = [LLMMessage(role=Role.system, content=system_prompt)]

# When loading session
if self._loaded_messages:
    non_system_messages = [
        msg for msg in self._loaded_messages
        if not (msg.role == Role.system)  # FILTER OUT system prompts
    ]
    agent.messages.extend(non_system_messages)
```

**Rationale**:
- System prompt may contain updated instructions
- Tool definitions may have changed
- Project context (file tree, git status) needs updating
- Skills configuration may differ

---

## What Is Persisted

| State | Persisted | Notes |
|-------|-----------|-------|
| User messages | ✅ | Full content |
| Assistant messages | ✅ | Content and tool calls |
| Tool call requests | ✅ | Name, arguments, call ID |
| Tool results | ✅ | Full output |
| Git context | ✅ | Commit hash, branch at save time |
| Token statistics | ✅ | Cumulative and per-turn |
| Tool call counts | ✅ | Agreed, rejected, failed, succeeded |
| Configuration snapshot | ✅ | Full config at save time |
| Available tools | ✅ | Tool schemas |
| Working directory | ✅ | Path where session ran |

---

## What Is NOT Persisted

| State | Persisted | Reason |
|-------|-----------|--------|
| System prompt | ❌ | Regenerated for current context |
| Live tool state | ❌ | Bash terminals, file handles are ephemeral |
| Approval decisions | ❌ | Security - user must re-approve tools |
| Mode (--plan, etc.) | ❌ | User must specify again |
| Mid-turn state | ❌ | Only complete turns are saved |
| Streaming buffers | ❌ | Transient data |

---

## Configuration Options

### config.toml

```toml
[session_logging]
# Enable or disable session logging entirely
enabled = true

# Directory where session files are stored
save_dir = "~/.vibe/logs"

# Prefix for session file names
session_prefix = "session"
```

### SessionLoggingConfig Model

```python
class SessionLoggingConfig(BaseSettings):
    save_dir: str = ""           # Default: ~/.vibe/logs
    session_prefix: str = "session"
    enabled: bool = True
```

### Default Save Location

```python
# From core/paths/global_paths.py
SESSION_LOG_DIR = GlobalPath("logs")  # ~/.vibe/logs
```

---

## Use Cases

### 1. Recovering from Interruption

```bash
# Terminal crashed or closed accidentally
vibe --continue
```

The session resumes exactly where you left off.

### 2. Picking Up Work After a Break

```bash
# Yesterday's work session
vibe --resume 7dcdccef
```

### 3. Context Switching Between Projects

```bash
# List recent sessions (manual inspection)
ls -la ~/.vibe/logs/

# Resume specific project work
vibe --resume abc12345
```

### 4. Continuing Long Tasks

```bash
# First session: started a complex refactor
vibe "Refactor the authentication module"
# ... work happens, then exit

# Next day: continue the refactor
vibe --continue "Now let's add the tests"
```

### 5. Debugging Past Sessions

```bash
# View session contents
cat ~/.vibe/logs/session_20260106_160230_7dcdccef.json | jq .
```

---

## Troubleshooting

### Session Not Found

```
[red]No previous sessions found in ~/.vibe/logs[/]
```

**Solutions**:
1. Check if session logging is enabled: `enabled = true` in config
2. Verify save directory exists and is writable
3. Check if any sessions exist: `ls ~/.vibe/logs/`

### Cannot Resume - Logging Disabled

```
[red]Session logging is disabled. Enable it in config to use --continue or --resume[/]
```

**Solution**: Add to `~/.vibe/config.toml`:
```toml
[session_logging]
enabled = true
```

### Session File Corrupted

If JSON parsing fails during load:

1. Try a different session: `vibe --resume <other-id>`
2. Check file integrity: `jq . ~/.vibe/logs/session_*.json`
3. Delete corrupted file and start fresh

### Large Session Files

Very long sessions can create large files. Consider:

1. Using `/compact` periodically to reduce conversation size
2. Using `/clear` to start fresh when appropriate
3. Archiving old session files

---

## Exit Message

When exiting the CLI, you'll see resume instructions:

```
To continue this session, run: vibe --continue
Or: vibe --resume 7dcdccef
```

This makes it easy to pick up exactly where you left off.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STATE PERSISTENCE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ~/.vibe/logs/                                                            │
│    ├── session_20260105_143022_abc12345.json   ← Older session              │
│    ├── session_20260106_090145_def67890.json   ← Yesterday's work           │
│    └── session_20260106_160230_7dcdccef.json   ← Current/latest session     │
│         │                                                                   │
│         │  ┌────────────────────────────────────────────────────────────┐  │
│         │  │ JSON Structure                                             │  │
│         │  │ ├── metadata                                               │  │
│         │  │ │   ├── session_id, timestamps                             │  │
│         │  │ │   ├── git_commit, git_branch                             │  │
│         │  │ │   ├── stats (tokens, tool calls, cost)                   │  │
│         │  │ │   ├── tools_available[]                                  │  │
│         │  │ │   └── agent_config                                       │  │
│         │  │ └── messages[]                                             │  │
│         │  │     ├── {role: system, content: ...}                       │  │
│         │  │     ├── {role: user, content: ...}                         │  │
│         │  │     ├── {role: assistant, content: ..., tool_calls: [...]} │  │
│         │  │     └── {role: tool, tool_call_id: ..., content: ...}      │  │
│         │  └────────────────────────────────────────────────────────────┘  │
│         │                                                                   │
│         │ vibe --continue / vibe --resume <id>                             │
│         ▼                                                                   │
│    ┌─────────────────────────────────────────────────────────────────────┐ │
│    │  Session Restoration                                                 │ │
│    │  ├── Load JSON → messages[], metadata                               │ │
│    │  ├── Create new Agent                                               │ │
│    │  ├── Generate FRESH system prompt                                   │ │
│    │  ├── Filter out old system messages                                 │ │
│    │  ├── Extend agent.messages with conversation history                │ │
│    │  └── Rebuild UI (if interactive)                                    │ │
│    └─────────────────────────────────────────────────────────────────────┘ │
│              │                                                              │
│              ▼                                                              │
│    ┌─────────────────────────────────────────────────────────────────────┐ │
│    │  Continued Conversation                                             │ │
│    │  └── User sends new message → Agent has full context               │ │
│    └─────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Related Documentation

- [MEMORY_CONTEXT_STRATEGY.md](./MEMORY_CONTEXT_STRATEGY.md) - Context window management
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
