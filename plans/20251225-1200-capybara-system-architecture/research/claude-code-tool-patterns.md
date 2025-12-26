# Claude Code Tool Patterns Analysis

> Extracted from Claude Code's internal design patterns for CapybaraVibeCoding architecture reference.

## 1. Tool Categories & Design Philosophy

### File Operations
| Tool | Purpose | Key Features |
|------|---------|--------------|
| **Read** | Read file contents | Line numbers, offset/limit for large files, image/PDF support |
| **Write** | Create/overwrite files | Requires prior Read, absolute paths only |
| **Edit** | String replacements | `old_string` → `new_string`, `replace_all` flag, uniqueness validation |
| **MultiEdit** | Batch edits | Multiple edits in single call, same file |
| **Glob** | Pattern matching | Returns paths sorted by modification time |
| **Grep** | Content search | ripgrep-based, multiple output modes |

**Key Pattern**: Specialized tools beat generic Bash commands for file ops.

### Execution Tools
| Tool | Purpose | Key Features |
|------|---------|--------------|
| **Bash** | Shell commands | Persistent session, timeout (up to 10min), background execution |
| **KillShell** | Terminate bg shells | By shell_id |

**Key Pattern**: Background execution + TaskOutput for long-running commands.

### Agent/Task System
| Tool | Purpose | Key Features |
|------|---------|--------------|
| **Task** | Launch subagents | `subagent_type` param, parallel launches, background mode |
| **TaskOutput** | Get results | `block` for sync/async, timeout |

**Subagent Types**:
- `general-purpose` - Complex multi-step tasks
- `Explore` - Fast codebase exploration
- `researcher` - Web research, documentation
- `debugger` - Issue investigation
- `tester` - Run tests, coverage
- `code-reviewer` - Quality assessment
- `planner` - Implementation planning

### User Interaction
| Tool | Purpose | Key Features |
|------|---------|--------------|
| **AskUserQuestion** | Get user input | Multi-question support, options with descriptions |
| **TodoWrite** | Task tracking | Status: pending/in_progress/completed |

### Planning Mode
| Tool | Purpose | Key Features |
|------|---------|--------------|
| **EnterPlanMode** | Start planning | User approval required |
| **ExitPlanMode** | Complete plan | Signals plan file ready |

---

## 2. Tool Schema Patterns (JSON Schema)

### Standard Structure
```json
{
  "name": "tool_name",
  "description": "Clear description with usage notes, examples",
  "parameters": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "required_param": {
        "type": "string",
        "description": "What this param does"
      },
      "optional_param": {
        "type": "number",
        "default": 100,
        "description": "Optional with default"
      }
    },
    "required": ["required_param"],
    "additionalProperties": false
  }
}
```

### Description Best Practices
1. **Start with core purpose** (1 sentence)
2. **Usage notes** section with bullets
3. **Examples** when behavior is complex
4. **Warnings** for dangerous operations
5. **When NOT to use** guidance

### Parameter Patterns
- `type`: string, number, boolean, array, object
- `enum`: Constrained values
- `default`: Sensible defaults for optional params
- `description`: Always include, even if obvious
- `additionalProperties: false`: Strict validation

---

## 3. Tool Execution Patterns

### Parallel Execution
```
When multiple independent tools needed:
- Launch ALL in single message
- No dependencies = parallel
- Dependencies = sequential with &&
```

### Background Execution
```python
# Bash with run_in_background=True
# Task with run_in_background=True

# Later retrieve with TaskOutput
TaskOutput(task_id="xxx", block=True/False)
```

### Streaming Output Handling
- Bash: Output truncated at 30000 chars
- Read: Line numbers added, 2000 line default limit
- Task: Returns summary when complete

### Timeout Management
- Bash: Default 120s, max 600s (10 min)
- Long operations: Use background mode

---

## 4. Safety & Permission Patterns

### Path Validation
- **Absolute paths required** for Write, Read
- **Working directory awareness**: Store and use cwd
- **Quotes for spaces**: `"path with spaces/file.txt"`

### Sandbox Mode
- Default: Sandboxed execution
- Override: `dangerouslyDisableSandbox: true`
- Only when explicitly needed

### Command Validation
- No destructive git commands without explicit request
- No force push to main/master
- No skipping hooks unless requested
- Secret file detection (.env, credentials)

---

## 5. Key Design Principles for CapybaraVibeCoding

### 1. Specialized Over Generic
- Read > cat
- Edit > sed
- Glob > find
- Grep > grep/rg

### 2. Async by Default
- All tools must be async
- Background mode for long operations
- Parallel execution when independent

### 3. Rich Descriptions
- Description is the "documentation"
- Include examples, warnings, edge cases

### 4. Fail Gracefully
- Return errors as strings
- Never crash the agent loop
- Actionable error messages

### 5. Minimal Surface Area
- Few required params
- Sensible defaults
- Avoid parameter explosion

---

*Analysis completed - 2024-12-25*
