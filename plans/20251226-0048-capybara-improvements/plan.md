# Capybara CLI Improvement Plan
## Based on Mistral Vibe CLI Architecture Analysis

**Created:** 2025-12-26
**Reference:** Mistral Vibe CLI Architecture
**Target:** Capybara CLI Agent Enhancement

---

## Executive Summary

After analyzing Mistral Vibe CLI's architecture, tools, and prompts, this plan identifies key improvements for Capybara CLI to enhance agent reliability, tool safety, context management, and user experience. The plan focuses on adopting proven patterns from Mistral Vibe while maintaining Capybara's strengths in multi-provider support and async architecture.

**Key Improvement Areas:**
1. Tool System Enhancement (search_replace pattern, safety, permissions)
2. Context Engineering (project snapshot, dangerous directory guards)
3. Prompt Engineering (structured system prompts, compaction strategy)
4. Middleware & Safety (turn limits, context warnings, plan mode)
5. User Experience (TODO tracking, better error messages)

---

## 1. Tool System Improvements

### 1.1 Implement `search_replace` Tool Pattern

**Gap:** Capybara uses `edit_file` with simple string replacement. Mistral Vibe uses structured SEARCH/REPLACE blocks for safer, more precise edits.

**Improvement:**
```python
# NEW: src/capybara/tools/builtin/search_replace.py

async def search_replace(file_path: str, content: str) -> str:
    """
    Apply SEARCH/REPLACE blocks to make targeted file changes.

    Format:
    <<<<<<< SEARCH
    [exact text to find]
    =======
    [text to replace with]
    >>>>>>> REPLACE

    Benefits:
    - Exact matching prevents accidental edits
    - Multiple changes in one call
    - Clear visual format for LLM
    - Better error messages with context
    """
```

**Action Items:**
- Create `search_replace.py` tool alongside existing `edit_file`
- Add validation for SEARCH/REPLACE block format
- Implement exact-match verification with context display on error
- Support multiple blocks per call (sequential application)
- Add fuzzy matching warnings for near-misses

**Priority:** HIGH
**Effort:** Medium
**Impact:** Reduces file editing errors significantly

---

### 1.2 Enhanced Tool Permission System

**Gap:** Capybara has basic `allowed_paths` check. Mistral Vibe implements comprehensive permission model with allowlist/denylist patterns.

**Improvement:**
```python
# Enhanced: src/capybara/tools/base.py

class ToolPermission(Enum):
    ALWAYS = "always"   # Auto-approve
    ASK = "ask"         # Prompt user
    NEVER = "never"     # Block

class BaseToolConfig(BaseModel):
    permission: ToolPermission = ToolPermission.ASK
    allowlist: list[str] = []  # Auto-approve patterns
    denylist: list[str] = []   # Block patterns

    # Example:
    # bash:
    #   permission: ask
    #   allowlist: ["git status", "npm test"]
    #   denylist: ["rm -rf", "sudo", "vim", "nano"]
```

**Action Items:**
- Add `ToolPermission` enum to base tool class
- Implement pattern matching (regex) for allowlist/denylist
- Add per-tool permission configuration in YAML
- Create middleware to check permissions before execution
- Add user prompt UI for ASK permission

**Priority:** HIGH
**Effort:** Medium
**Impact:** Prevents accidental destructive operations

---

### 1.3 Tool Prompts Co-location

**Gap:** Capybara embeds tool descriptions in code. Mistral Vibe stores tool prompts in separate .md files next to tool implementation.

**Improvement:**
```
src/capybara/tools/builtin/
├── read_file.py
├── prompts/
│   ├── read_file.md        # Tool usage guide
│   ├── write_file.md
│   ├── search_replace.md
│   ├── bash.md
│   └── grep.md
```

**Benefits:**
- Easier to update tool documentation
- Better organization and maintainability
- Can include examples and best practices
- Separates concerns (code vs. LLM instructions)

**Action Items:**
- Create `prompts/` directory in builtin tools
- Extract tool descriptions to .md files
- Add `get_tool_prompt()` class method (like Mistral Vibe)
- Update tool registration to load from .md files
- Add rich examples to each tool prompt

**Priority:** MEDIUM
**Effort:** Low
**Impact:** Better LLM tool usage, easier maintenance

---

### 1.4 Improved `read_file` with Chunking

**Gap:** Capybara's `read_file` loads entire file or uses offset/limit. Mistral Vibe has better large file handling.

**Improvement:**
```python
# Enhanced: src/capybara/tools/builtin/filesystem.py

@dataclass
class ReadFileResult:
    content: str
    was_truncated: bool
    total_lines: Optional[int] = None
    offset: int = 0
    limit: Optional[int] = None

async def read_file(
    path: str,
    offset: int = 0,
    limit: Optional[int] = 1000
) -> ReadFileResult:
    """
    Read file with automatic truncation for large files.
    Returns metadata about truncation for informed next steps.
    """
```

**Action Items:**
- Return structured result with `was_truncated` flag
- Add file size checks and warnings
- Implement smart chunking strategy in tool prompt
- Guide LLM to read in chunks when `was_truncated=True`

**Priority:** LOW
**Effort:** Low
**Impact:** Better handling of large files

---

## 2. Context Engineering

### 2.1 Project Context Snapshot

**Gap:** Capybara doesn't provide project structure context. Mistral Vibe injects directory tree + git status at conversation start.

**Improvement:**
```python
# NEW: src/capybara/core/context.py

async def build_project_context() -> str:
    """
    Build project snapshot for system prompt.

    Includes:
    - Directory structure (limited depth, respects .gitignore)
    - Git status and recent commits
    - Project metadata (language, framework detection)
    """

    template = """
directoryStructure: {structure}

Absolute path: {abs_path}

gitStatus: {git_status}
"""
```

**Action Items:**
- Create `context.py` module for project scanning
- Implement directory tree builder (max depth 3-4, skip node_modules, .git, etc.)
- Add git status integration (`git status --short`, `git log -5 --oneline`)
- Inject into system prompt at agent initialization
- Add config option to enable/disable (default: enabled)

**Priority:** HIGH
**Effort:** Medium
**Impact:** LLM understands project layout without exploration

---

### 2.2 Dangerous Directory Guard

**Gap:** Capybara allows scanning any directory. Mistral Vibe blocks dangerous directories (home folder, root).

**Improvement:**
```python
# NEW: src/capybara/core/safety.py

DANGEROUS_PATHS = [
    Path.home(),           # User home directory
    Path("/"),             # Root
    Path("/usr"),
    Path("/etc"),
]

def is_dangerous_directory(path: Path) -> bool:
    """Check if directory is unsafe for project scanning."""
    resolved = path.resolve()
    return any(
        resolved == dangerous or
        resolved.is_relative_to(dangerous)
        for dangerous in DANGEROUS_PATHS
    )

DANGEROUS_DIRECTORY_WARNING = """
⚠️ WARNING: This directory may contain sensitive files.
The agent will NOT scan the directory structure automatically.
Please specify exact file paths when requesting file operations.
"""
```

**Action Items:**
- Add dangerous directory detection
- Skip project context snapshot when in dangerous path
- Inject warning into system prompt instead
- Add user confirmation for dangerous directory operations

**Priority:** MEDIUM
**Effort:** Low
**Impact:** Prevents accidental exposure of sensitive files

---

### 2.3 Context Compaction Strategy

**Gap:** Capybara uses simple FIFO trimming. Mistral Vibe has structured compaction prompt for conversation summarization.

**Improvement:**
```python
# NEW: src/capybara/core/compaction.py

COMPACTION_PROMPT = """
Create comprehensive summary of our conversation for continuing work.

Required sections:
1. User's Primary Goals and Intent
2. Conversation Timeline and Progress
3. Technical Context and Decisions
4. Files and Code Changes (with paths, purpose, changes)
5. Active Work and Last Actions
6. Unresolved Issues and Pending Tasks
7. Immediate Next Step

Focus on actionable information for seamless continuation.
"""

async def compact_conversation(messages: list[dict]) -> str:
    """Trigger LLM to summarize conversation when token limit approaching."""
    # Call LLM with compaction prompt
    # Replace old messages with summary message
```

**Action Items:**
- Create compaction prompt template (from Mistral Vibe)
- Add middleware to detect when compaction needed (e.g., 80% of token limit)
- Implement LLM-based summarization
- Replace message history with summary + system prompt + recent messages
- Add config for compaction threshold

**Priority:** MEDIUM
**Effort:** High
**Impact:** Better context retention in long conversations

---

## 3. Prompt Engineering

### 3.1 Structured System Prompt Assembly

**Gap:** Capybara has monolithic system prompt. Mistral Vibe assembles from multiple components.

**Improvement:**
```python
# Enhanced: src/capybara/core/prompts.py

def build_system_prompt(
    tools: list[ToolInfo],
    project_context: str,
    user_instructions: Optional[str] = None,
    mode: str = "default"
) -> str:
    """
    Assemble system prompt from components:
    1. Base CLI instructions
    2. Tool descriptions (with prompts from .md files)
    3. Project context (directory tree + git)
    4. User custom instructions
    5. Mode-specific additions (plan mode, test mode, etc.)
    """

    parts = [
        load_prompt("cli.md"),           # Base behavior
        format_tool_docs(tools),         # Available tools
        project_context,                 # Project snapshot
        user_instructions or "",         # Custom rules
        MODE_PROMPTS.get(mode, "")      # Mode-specific
    ]

    return "\n\n".join(filter(None, parts))
```

**Action Items:**
- Split system prompt into modular .md files in `prompts/`
- Create `prompts/cli.md` for base agent instructions
- Create `prompts/project_context.md` template
- Create `prompts/dangerous_directory.md` warning
- Add mode system (default, plan, test)
- Support user custom instructions from config

**Priority:** HIGH
**Effort:** Medium
**Impact:** Cleaner prompt management, easier customization

---

### 3.2 Todo Tool Integration

**Gap:** Capybara doesn't have task tracking. Mistral Vibe has built-in TODO tool for multi-step work.

**Improvement:**
```python
# NEW: src/capybara/tools/builtin/todo.py

@dataclass
class TodoItem:
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    priority: Literal["high", "medium", "low"]

async def todo_read() -> list[TodoItem]:
    """Read current TODO list."""

async def todo_write(todos: list[TodoItem]) -> str:
    """Write complete TODO list (replaces all)."""

# System prompt addition:
"""
Use the `todo` tool to manage multi-step tasks:
- Create todos at task start
- Mark ONE task in_progress before working
- Mark completed IMMEDIATELY after finishing
- Never mark complete if tests fail or errors occur
"""
```

**Action Items:**
- Implement TODO tool with read/write actions
- Store in-memory or in session storage
- Add TODO prompt guidance (from Mistral Vibe)
- Display TODO list in CLI interface
- Update system prompt with TODO best practices

**Priority:** MEDIUM
**Effort:** Medium
**Impact:** Better task organization, visible progress

---

## 4. Middleware & Safety

### 4.1 Middleware System

**Gap:** Capybara hardcodes limits in agent loop. Mistral Vibe has pluggable middleware.

**Improvement:**
```python
# NEW: src/capybara/core/middleware.py

class Middleware(ABC):
    @abstractmethod
    async def before_turn(self, messages: list[dict]) -> None:
        """Run before LLM call."""

    @abstractmethod
    async def after_turn(self, response: dict) -> None:
        """Run after LLM responds."""

class TurnLimitMiddleware(Middleware):
    """Enforce maximum turns per conversation."""

class TokenLimitMiddleware(Middleware):
    """Warn when approaching token limit."""

class CompactionMiddleware(Middleware):
    """Auto-compact when token threshold reached."""

class PlanModeMiddleware(Middleware):
    """Restrict to read-only tools in plan mode."""
```

**Action Items:**
- Create middleware base class
- Implement turn limit middleware (already exists, refactor)
- Add token warning middleware
- Add auto-compaction middleware
- Add plan mode enforcement middleware
- Register middleware in agent initialization

**Priority:** LOW
**Effort:** Medium
**Impact:** Cleaner separation of concerns

---

### 4.2 Plan Mode

**Gap:** Capybara doesn't have planning mode. Mistral Vibe has read-only plan mode for design phase.

**Improvement:**
```python
# Enhanced: src/capybara/core/agent.py

class AgentMode(Enum):
    DEFAULT = "default"
    PLAN = "plan"      # Read-only tools only
    TEST = "test"      # Focus on testing

class Agent:
    def __init__(self, ..., mode: AgentMode = AgentMode.DEFAULT):
        self.mode = mode

    async def run(self, user_input: str) -> str:
        if self.mode == AgentMode.PLAN:
            # Filter to read-only tools
            allowed_tools = [
                t for t in tools
                if t.name in ["read_file", "grep", "list_directory", "bash"]
            ]
            # Inject plan mode warning to system prompt
```

**Action Items:**
- Add `AgentMode` enum
- Filter tools based on mode
- Add plan mode system prompt addition
- Add CLI flag `capybara chat --mode plan`
- Document plan mode usage

**Priority:** LOW
**Effort:** Low
**Impact:** Supports design-before-implement workflow

---

## 5. User Experience

### 5.1 Better Error Messages

**Gap:** Generic error messages. Mistral Vibe provides detailed context on tool failures.

**Improvement:**
```python
# Enhanced: Tool error handling

try:
    # Execute search_replace
    match_index = content.find(search_text)
    if match_index == -1:
        # Show context around expected location
        return f"""
Error: SEARCH block not found in {file_path}

Expected to find:
{search_text}

Showing file context (lines {start}-{end}):
{context_lines}

Suggestions:
- Check for whitespace differences
- Verify line endings match
- Ensure indentation is exact
"""
```

**Action Items:**
- Enhance error messages with context
- Show file snippets around error location
- Provide actionable suggestions
- Add line numbers to error context

**Priority:** MEDIUM
**Effort:** Low
**Impact:** Faster debugging, better LLM self-correction

---

### 5.2 Rich CLI Output

**Gap:** Basic Rich usage. Could enhance with panels, progress bars, status indicators.

**Improvement:**
```python
# Enhanced: src/capybara/cli/interactive.py

from rich.panel import Panel
from rich.progress import Progress
from rich.status import Status

# Welcome screen
console.print(Panel(
    f"[bold]Capybara CLI v{VERSION}[/bold]\n"
    f"Model: {config.model}\n"
    f"Tools: {len(tools)} available\n"
    f"Mode: {mode}",
    title="🦫 Welcome",
    border_style="blue"
))

# Tool execution status
with console.status("[bold blue]Executing tools...") as status:
    results = await execute_tools(tool_calls)
```

**Action Items:**
- Add welcome panel to chat mode
- Show tool execution status with spinner
- Display TODO list in sidebar (if implemented)
- Add token usage footer
- Color-code different message types

**Priority:** LOW
**Effort:** Low
**Impact:** More professional, informative interface

---

## 6. Implementation Phases

### Phase 1: Core Safety & Tools (Week 1)
**Priority: HIGH**

1. Implement `search_replace` tool with SEARCH/REPLACE blocks
2. Add tool permission system (ALWAYS/ASK/NEVER)
3. Add allowlist/denylist pattern matching
4. Implement dangerous directory guard
5. Add project context snapshot to system prompt

**Deliverables:**
- `src/capybara/tools/builtin/search_replace.py`
- `src/capybara/tools/base.py` (enhanced permissions)
- `src/capybara/core/safety.py`
- `src/capybara/core/context.py`
- Updated system prompt assembly

**Testing:**
- Test SEARCH/REPLACE exact matching
- Test permission checks block destructive commands
- Verify dangerous directory detection
- Validate project context generation

---

### Phase 2: Prompt Engineering (Week 2)
**Priority: HIGH**

1. Split system prompt into modular .md files
2. Create tool prompt files (prompts/ directory)
3. Implement prompt assembly pipeline
4. Add user custom instructions support
5. Enhance tool descriptions with examples

**Deliverables:**
- `src/capybara/prompts/cli.md`
- `src/capybara/prompts/project_context.md`
- `src/capybara/prompts/dangerous_directory.md`
- `src/capybara/tools/builtin/prompts/*.md`
- Updated `build_system_prompt()` function

**Testing:**
- Verify prompt assembly works correctly
- Test each mode (default, plan, test)
- Validate tool prompt loading

---

### Phase 3: Context Management (Week 3)
**Priority: MEDIUM**

1. Implement TODO tool for task tracking
2. Add context compaction middleware
3. Create LLM-based conversation summarization
4. Add token warning system
5. Implement middleware architecture

**Deliverables:**
- `src/capybara/tools/builtin/todo.py`
- `src/capybara/core/compaction.py`
- `src/capybara/core/middleware.py`
- Middleware implementations

**Testing:**
- Test TODO tool persistence
- Verify compaction triggers at threshold
- Validate summarization quality
- Test middleware chain execution

---

### Phase 4: UX Enhancements (Week 4)
**Priority: LOW**

1. Improve error messages with context
2. Add Rich CLI panels and status indicators
3. Implement plan mode
4. Enhanced file reading with chunking metadata
5. Documentation updates

**Deliverables:**
- Better error formatting across all tools
- Enhanced CLI interface with panels
- Plan mode implementation
- Updated README and documentation

**Testing:**
- Manual testing of CLI interface
- Error message clarity validation
- Plan mode workflow testing

---

## 7. Configuration Changes

### Enhanced config.yaml

```yaml
# ~/.capybara/config.yaml

providers:
  - name: default
    model: gpt-4o
    api_key: ${OPENAI_API_KEY}

memory:
  max_tokens: 100000
  persist: true
  compaction_threshold: 0.8  # NEW: Trigger compaction at 80%

tools:
  bash_enabled: true
  bash_timeout: 120
  bash_permission: ask       # NEW: ALWAYS/ASK/NEVER
  bash_allowlist:           # NEW: Auto-approve patterns
    - "git status"
    - "git log"
    - "npm test"
  bash_denylist:            # NEW: Block patterns
    - "rm -rf"
    - "sudo"
    - "^(vim|nano|emacs)"   # Interactive editors

  filesystem_enabled: true
  allowed_paths:
    - "."

  search_replace_enabled: true  # NEW tool

context:
  project_snapshot: true     # NEW: Include dir tree + git
  dangerous_directory_check: true  # NEW: Safety guard

mode: default  # NEW: default/plan/test

user_instructions: |   # NEW: Custom prompt additions
  Additional instructions here...
```

---

## 8. Testing Strategy

### Unit Tests
- Tool permission system
- SEARCH/REPLACE block parsing
- Dangerous directory detection
- Project context generation
- Middleware execution order

### Integration Tests
- End-to-end agent runs with new tools
- Permission prompts workflow
- Compaction trigger and execution
- Mode switching (default/plan)

### Manual Tests
- CLI interface usability
- Error message clarity
- TODO tool workflow
- Permission system UX

---

## 9. Documentation Updates

### User Documentation
- Update README with new tools (search_replace, todo)
- Document permission system configuration
- Add plan mode usage guide
- Configuration reference update

### Developer Documentation
- Update ARCHITECTURE.md with new components
- Document middleware system
- Tool development guide (including prompts/)
- Compaction strategy explanation

---

## 10. Migration Guide

### For Existing Users

**Breaking Changes:**
- `edit_file` behavior unchanged, but `search_replace` recommended
- New permission system requires config update for auto-approve patterns

**Recommended Actions:**
1. Update config.yaml with permission settings
2. Review bash allowlist/denylist for your workflow
3. Enable project_snapshot for better context
4. Try plan mode for design work

**Backward Compatibility:**
- All existing tools continue working
- Default permissions = ASK (current behavior)
- Project snapshot can be disabled in config

---

## 11. Success Metrics

### Quantitative
- **Reduced edit errors:** Track failed edit_file vs. search_replace
- **Permission blocks:** Count destructive operations prevented
- **Context efficiency:** Tokens saved via compaction
- **Tool usage:** Adoption of new tools (search_replace, todo)

### Qualitative
- **User feedback:** Survey on safety improvements
- **LLM performance:** Better task completion rates
- **Developer experience:** Easier customization via prompts/

---

## 12. Risks & Mitigation

### Risk 1: Permission System Too Strict
**Mitigation:** Start with ASK default, provide good allowlist examples in docs

### Risk 2: Compaction Loses Context
**Mitigation:** Extensive testing of summarization quality, user control over threshold

### Risk 3: SEARCH/REPLACE Complexity
**Mitigation:** Keep edit_file as alternative, provide clear examples in tool prompt

### Risk 4: Performance Impact
**Mitigation:** Make project snapshot optional, cache results, limit tree depth

---

## 13. Future Enhancements (Post-Plan)

### Beyond This Plan
1. **Skills System:** Adopt Mistral Vibe's SKILL.md mini-guides
2. **Session Logging:** Structured logs of tool usage, tokens, timing
3. **MCP Tool Wrapping:** Better integration with MCP servers
4. **Multi-Provider Routing:** Enhance LiteLLM integration
5. **Web UI:** Optional web interface for conversations

---

## 14. Key Learnings from Mistral Vibe

### What to Adopt
✅ SEARCH/REPLACE block pattern - Proven safer than simple string replace
✅ Tool permission system - Essential safety layer
✅ Project context snapshot - Huge time saver for LLM
✅ Modular prompt assembly - Much easier to maintain
✅ TODO tool - Critical for multi-step tasks
✅ Dangerous directory guard - Prevents accidents

### What to Adapt
🔄 Middleware system - Good pattern, implement gradually
🔄 Compaction strategy - Useful but complex, start simple
🔄 Plan mode - Nice-to-have, lower priority

### What to Skip (For Now)
❌ Skills system - Too complex, defer to later
❌ Full middleware pipeline - Overengineering risk
❌ Extensive session logging - Use existing logging

---

## 15. Conclusion

This plan brings battle-tested patterns from Mistral Vibe CLI to enhance Capybara's safety, reliability, and user experience while preserving its strengths in async architecture and multi-provider support.

**Critical Path:**
1. Safety first: Permissions + dangerous directory guard
2. Better tools: search_replace for reliable edits
3. Context: Project snapshot for better LLM awareness
4. Polish: Prompts, errors, UX improvements

**Estimated Timeline:** 4 weeks for full implementation
**Effort Distribution:** 60% safety/tools, 25% prompts/context, 15% UX

**Next Step:** Review and approve this plan, then begin Phase 1 implementation.
