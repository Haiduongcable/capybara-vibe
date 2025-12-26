# Mistral Vibe Agent Architecture (Junior-Friendly Guide)

This document explains how the agent works in simple terms. It covers:
- The system prompt and how it is built
- Tools and how the agent calls them
- The agent loop and middleware
- Context engineering (project context, compaction, safety)

---

## 1) High-Level Flow (What Happens When You Chat)

1. The agent builds a **system prompt** (rules + tool docs + project context).
2. It sends your message + the system prompt to the LLM.
3. The LLM may return tool calls (like `read_file`, `grep`, `bash`).
4. The agent validates and runs those tools.
5. Tool results are sent back to the LLM.
6. The loop repeats until the LLM replies with no more tool calls.

---

## 2) System Prompt (How the "Brain" Is Built)

The system prompt is **assembled** from multiple parts:

- Base prompt text (like CLI instructions)
- Tool descriptions
- User instructions (from config or `instructions.md`)
- Project context (directory tree + git status)
- Optional project docs (like `AGENTS.md`)

---

## 3) Project Context (Repo Snapshot)

The agent creates a **snapshot** of the repo:
- directory tree (limited depth and size)
- git status and recent commits

This is used to help the model understand the project layout.

Safety:
- If the current folder is "dangerous" (like your home folder), it does NOT scan.
- Instead, it inserts a warning prompt.

---

## 4) Tools (What the Agent Can Do)

Tools are **structured actions** the agent can call. Each tool has:
- A name and description (so the model knows when to use it)
- A strict input schema (so arguments are validated)
- A result format (so the model can read outputs safely)
- Permission rules (auto-allow, ask, or deny)

The agent only executes tools after validating their inputs and checking permissions.

### Built-in Tools (Purpose and How They Work)

1) `read_file`
- Purpose: Read file contents safely without loading huge files.
- How it works: Reads by line with an optional offset + limit. Enforces a max byte size and reports if the output is truncated.
- Why it matters: Prevents large files from overwhelming the model.

2) `write_file`
- Purpose: Create or overwrite files.
- How it works: Validates path is inside the project, enforces a size limit, and requires explicit `overwrite=true` to replace existing files.
- Why it matters: Prevents accidental data loss and writing outside the project.

3) `search_replace`
- Purpose: Make precise edits to existing files.
- How it works: Uses SEARCH/REPLACE blocks with exact matching. Can warn about fuzzy matches or repeated blocks.
- Why it matters: Safe, targeted edits without rewriting whole files.

4) `grep`
- Purpose: Search the codebase quickly.
- How it works: Runs a fast search (usually ripgrep), respects ignore files, and enforces output limits.
- Why it matters: Fast discovery without manual file scanning.

5) `bash`
- Purpose: Run one-off shell commands (git, environment checks, etc.).
- How it works: Executes in a non-interactive shell with timeouts, output caps, and allowlist/denylist rules.
- Why it matters: Allows the agent to check system state or run quick commands safely.

6) `todo`
- Purpose: Track tasks in multi-step work.
- How it works: Stores a structured list of tasks with status and priority.
- Why it matters: Keeps long tasks organized and visible.

### Permissions and Safety

Each tool checks:
- Allowlist/denylist patterns (example: block interactive editors)
- Explicit permissions (always/ask/never)
- Path safety rules (no writing outside the project)

### How Tool Calls Flow

1) The model suggests a tool + arguments.
2) The agent validates the arguments against the schema.
3) The agent checks permissions (auto-approve or ask).
4) The tool runs and returns a structured result.
5) The result is fed back into the conversation.

### Practical Examples: Which Tool to Use and How to Call It

Below are common tasks and the typical tool call pattern.
All examples show the **arguments shape** the agent uses.

#### Example A: Read a file before editing
Use `read_file` to get current content.

```json
{
  "tool": "read_file",
  "args": {
    "path": "src/module.py",
    "offset": 0,
    "limit": 200
  }
}
```

#### Example B: Update or delete code inside a file
Use `search_replace` for precise edits.

```text
<<<<<<< SEARCH
def old_function():
    return "old"
=======
def new_function():
    return "new"
>>>>>>> REPLACE
```

Tool call:
```json
{
  "tool": "search_replace",
  "args": {
    "file_path": "src/module.py",
    "content": "<<<<<<< SEARCH\n...exact text...\n=======\n...replacement...\n>>>>>>> REPLACE"
  }
}
```

To **delete** code, replace with an empty string:
```text
<<<<<<< SEARCH
def unused():
    pass
=======
>>>>>>> REPLACE
```

#### Example C: Overwrite a file completely
Use `write_file` only when a full rewrite is needed.

```json
{
  "tool": "write_file",
  "args": {
    "path": "src/module.py",
    "content": "def main():\n    print(\"hello\")\n",
    "overwrite": true
  }
}
```

#### Example D: Find where something is defined
Use `grep` to search.

```json
{
  "tool": "grep",
  "args": {
    "pattern": "class MyClass",
    "path": "src"
  }
}
```

#### Example E: Run git status or quick checks
Use `bash` for one-off commands.

```json
{
  "tool": "bash",
  "args": {
    "command": "git status"
  }
}
```

#### Example F: Track a multi-step task
Use `todo` to store and update tasks.

```json
{
  "tool": "todo",
  "args": {
    "action": "write",
    "todos": [
      {
        "id": "1",
        "content": "Update parsing logic",
        "status": "in_progress",
        "priority": "high"
      }
    ]
  }
}
```

Tool discovery order:
1) Built-in tools
2) User-specified tool paths
3) Local `.vibe/tools`
4) Global tools

---

## 5) MCP Tools (Remote Tools)

The agent can connect to MCP servers and expose their tools locally.

How it works:
- It calls MCP "list tools"
- It wraps each tool as a local proxy class

---

## 6) Agent Loop (Core Execution)

The loop is inside `Agent.act()`:

1) Add user message.
2) Run middleware checks.
3) Call the LLM backend.
4) Parse tool calls and execute them.
5) Store tool results as messages.
6) Repeat until no tools are requested.

Core file:
The agent core loop is implemented in the main agent class.

---

## 7) Middleware (Safety + Limits)

Middleware runs **before** and **after** each LLM turn.

Built-in middleware:
- Turn limit
- Price limit
- Auto-compaction
- Context warnings
- Plan mode reminder

Plan mode:
- Uses only read-only tools.
- Injects a warning if the agent tries to act.

---

## 8) LLM Backends (Mistral vs Generic)

The agent supports:
- Mistral SDK backend
- Generic OpenAI-style HTTP backend

Tool calling format and parsing:
- The agent uses function-call schemas and validates tool arguments before running tools.

---

## 9) Skills System (Optional)

Skills are "mini-guides" stored in `SKILL.md` files with YAML frontmatter.

Skills are listed in the system prompt when available.

---

## 10) Session Logging

The agent saves logs of conversations, tool usage, and metadata.

---

## 11) How to Build a Similar Agent (Simple Checklist)

1) Build a system prompt assembly pipeline:
   - Base prompt
   - Tool docs
   - Project context snapshot
   - User instructions

2) Implement tool calling:
   - Tool schema discovery
   - Tool validation
   - Tool execution
   - Tool results back to LLM

3) Add safety + middleware:
   - Tool permissions
   - Allowlist/denylist
   - Optional auto-compact

4) Add a backend layer:
   - One SDK (Mistral)
   - One generic HTTP adapter (OpenAI style)

5) Add context engineering:
   - Directory scan with limits
   - Git status snapshot
   - Dangerous directory guard

---

If you want, I can also generate a "minimal skeleton" project layout that follows this design.
