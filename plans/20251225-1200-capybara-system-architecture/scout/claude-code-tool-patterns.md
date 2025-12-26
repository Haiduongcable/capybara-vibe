# Claude Code Tool Design Patterns

## 1. Tool Categories & Purposes

### File Operations (Composition over Abstraction)
- **Read**: Load file contents with line-aware pagination (line offset + limit)
  - Pattern: Stream-friendly, supports image/PDF/notebook formats
  - Safety: Explicit path validation, no shell expansion
  - Semantics: Pure read, immutable operation

- **Write**: Overwrite entire files (atomic, no append)
  - Pattern: Requires prior Read to avoid accidental overwrites
  - Safety: Explicit file path, no relative paths
  - Constraint: New files only if explicitly required

- **Edit**: Targeted string replacement with context
  - Pattern: Exact match required (uniqueness or replace_all flag)
  - Safety: old_string/new_string both specified, prevents blind edits
  - Use case: Surgical changes to existing code

- **Glob**: Fast pattern matching for file discovery
  - Pattern: Returns paths sorted by modification time
  - Use: Supplement to grep for file filtering
  - Design: Works with any codebase size efficiently

- **NotebookEdit**: Jupyter notebook cell-level operations
  - Pattern: Cell-based granularity (code/markdown types)
  - Modes: replace, insert (after cell ID), delete
  - Semantics: Preserves notebook structure, JSON-friendly

### Search (Specialized for Code Context)
- **Grep**: Ripgrep-based search with rich filtering
  - Patterns: Full regex syntax, multiline support (multiline: true flag)
  - Output modes: content (with -A/-B/-C context), files_with_matches, count
  - Filtering: glob patterns, file types (type: "js"), case-insensitive (-i)
  - Design philosophy: Never use bash grep/rg; use dedicated tool for ACL/permissions

### Execution (Persistent Sessions with Lifecycle)
- **Bash**: Long-running shell with timeout/background support
  - Pattern: Persistent session (cwd resets between calls, always use absolute paths)
  - Timeouts: Configurable up to 600s (default 120s)
  - Background: run_in_background: true for long operations
  - Output: Truncates >30k chars, captures exit codes
  - Safety: Quoting required for paths with spaces, no force commands to main/master

- **KillShell**: Terminate background processes
  - Pattern: Paired with run_in_background operations
  - Semantics: Clean shutdown signal

### Web Tools (External Data Retrieval)
- **WebFetch**: URL content → markdown conversion + AI processing
  - Pattern: Includes 15-min cache, auto-upgrades HTTP→HTTPS
  - Input: URL + prompt for extraction
  - Output: Summarized/processed results
  - Safety: Handles redirects, reports redirect URLs

- **WebSearch**: Query-based search across indexed web
  - Pattern: Supports domain filtering (allowed_domains, blocked_domains)
  - Availability: US-only
  - CRITICAL: Must include Sources section in response with markdown links

### Task Management (Asynchronous Coordination)
- **Task**: Subagent dispatch with streaming output
  - Pattern: Name-based subagent identification
  - Communication: Persistent state (pending/in_progress/completed)
  - Design: Single subagent active at a time, queue-like semantics

- **TaskOutput**: Read streaming results from Task
  - Pattern: Non-blocking poll, returns available output
  - Use: Monitor long-running subagent work without blocking

- **TodoWrite**: Human-visible task tracking
  - Pattern: Dual-form tasks (content + activeForm)
  - States: pending/in_progress/completed
  - Rule: Exactly ONE in_progress at a time, mark complete immediately
  - NOT for automation; for user visibility

### User Interaction
- **AskUserQuestion**: Prompt for user input during execution
  - Pattern: Blocking until user responds
  - Use: When agent needs clarification/approval before proceeding
  - Safety: User explicitly gates decisions

### Planning Mode
- **EnterPlanMode**: Suspend execution for deliberate planning
  - Pattern: Switches to analysis-only, no tool execution
  - Use: Complex decisions, research phases

- **ExitPlanMode**: Resume execution from plan
  - Pattern: Exits analysis mode, resumes tool-driven work

### IDE Integration (Direct Language Support)
- **mcp__ide__getDiagnostics**: Language diagnostics (LSP integration)
  - Pattern: Per-file or whole-workspace diagnostics
  - Output: Type errors, linting issues, warnings
  - Use: Pre-build validation, error detection

- **mcp__ide__executeCode**: Jupyter kernel execution
  - Pattern: Persistent kernel state across calls
  - Language: Python (or configured kernel)
  - Semantics: Modify state intentionally, not speculatively

### Skills (Specialized Knowledge Domains)
- **Skill**: Invoke domain-specific expertise
  - Pattern: Tool invocation with optional args
  - Activation: Intelligence-driven (analyze task, activate needed skills)
  - Design: Each skill encapsulates expertise + workflows

---

## 2. Tool Schema Patterns

### Parameter Design Principles

#### Required vs Optional
- **Required**: Parameters essential to tool semantics
  - Example: `Read(file_path)`, `Bash(command)`, `Grep(pattern)`
  - Design: No defaults for ambiguous operations

- **Optional**: Configuration/tuning parameters
  - Example: `Bash(timeout, run_in_background)`, `Read(limit, offset)`, `Grep(-A, -B, -C)`
  - Pattern: Sensible defaults (timeout=120s, limit=2000, run_in_background=false)

#### Parameter Types & Validation
- **String**: Quoted for paths with spaces, exact values from user
- **Number**: Timeout in milliseconds (max 600000), line limits
- **Boolean**: Feature flags (run_in_background, multiline, -i)
- **Enums**: Output modes ("content"/"files_with_matches"/"count"), edit modes
- **Arrays**: Domain filtering (allowed_domains: ["github.com"], blocked_domains: ["ads.com"])

### Schema Quality Standards

#### Descriptions: Actionable & Concise
- **File tools**: Specify behavior (overwrites, atomic, requires prior Read)
- **Search tools**: Explain syntax rules (ripgrep, not grep; literal braces need escaping)
- **Execution tools**: Document guarantees (persistent session, absolute paths required)
- **Web tools**: Note side effects (caching, header requirements)

#### Error Handling Approaches
- **Read**: Returns error if file doesn't exist; graceful for empty files
- **Edit**: Fails if old_string not unique; use replace_all to force
- **Write**: Fails if file not pre-read (prevents accidental overwrites)
- **Bash**: Captures exit codes, truncates output, doesn't raise on non-zero exit
- **Grep**: Returns empty if no matches (not an error)

---

## 3. Tool Execution Patterns

### Parallel Execution (Non-Blocking)
- **Mechanism**: Multiple tool calls in single function_calls block (no dependencies)
- **When to use**: Independent Read/Grep/Bash operations
- **Example**:
  ```
  [Bash(git status), Bash(git log), Bash(npm test)]
  // All execute in parallel
  ```
- **Design philosophy**: Minimize latency by exploiting independent operations

### Sequential Execution (Blocking Dependencies)
- **Mechanism**: Wait for tool result, then call dependent tool
- **When to use**: Tool B depends on output of Tool A
- **Example**:
  ```
  1. Bash(git status) → identifies untracked files
  2. Read(file_path) → read identified file
  3. Edit(file_path, old_string, new_string) → modify based on content
  ```
- **Error handling**: Don't cascade; stop and ask user if intermediate step fails

### Background Execution (Fire & Forget)
- **Mechanism**: run_in_background: true on Bash tool
- **When to use**: Long-running operations (tests, builds, server startup)
- **Monitoring**: TaskOutput to poll results without blocking
- **Cleanup**: KillShell to terminate if needed

### Streaming Output Handling
- **Timeout protection**: Prevent infinite hangs; default 120s, max 600s
- **Output truncation**: >30k chars truncated; use TaskOutput for continuation
- **Line-aware pagination**: Read(limit, offset) for large files
- **Lazy evaluation**: Glob returns sorted paths; Grep uses head_limit to limit results

### Timeout Management
- **Default**: 120 seconds (2 minutes)
- **Maximum**: 600 seconds (10 minutes)
- **Unit**: Milliseconds in parameter
- **Use case**: Tests (300s), long builds (600s), quick operations (120s default)

---

## 4. Permission & Safety Patterns

### Sandboxing (Default: Enabled)
- **Pattern**: dangerouslyDisableSandbox: true ONLY when explicitly needed
- **Use cases**: Low-risk, specific tool invocations
- **Default behavior**: All Bash commands execute in sandbox
- **Principle**: Assume untrusted input; sandbox by default

### Path Validation
- **Absolute paths only**: No relative paths (cwd resets between calls)
- **Space handling**: Quote paths with spaces: `cd "/Users/name/My Documents"`
- **No shell expansion**: Paths treated literally, no ~ or $VAR expansion
- **Read prerequisite**: Write/Edit require prior Read to prevent overwrites

### Command Validation
- **Git safety**: No force push to main/master (requires explicit user request + warning)
- **Destructive operations**: hard reset, force push gated behind explicit approval
- **Amend rules**: Only on HEAD commit created in session, not pushed, and pre-commit hook auto-modified files
- **Hooks**: Never skip (--no-verify, --no-gpg-sign) unless explicit user request

### Output Sanitization
- **Truncation**: >30k chars truncated (prevents token explosion)
- **No secrets**: Tool descriptions warn about .env, credentials.json
- **User-supplied values**: ALWAYS use exact values from user (in quotes if specified)

---

## 5. Design Philosophy Synthesis

### Core Principles

1. **Composition over Abstraction**
   - File tools are specialized (Read ≠ Write ≠ Edit) rather than generic "FileOp"
   - Each tool has single responsibility with clear semantics
   - Tools combine in declarative pipelines (Read → Grep → Edit)

2. **Safety as Default**
   - Sandboxing on, paths absolute, previews required (Read before Write)
   - Commands explicit (no inference), ambiguity = error
   - User gates destructive operations (git force push, amend)

3. **Efficiency & Latency**
   - Parallel execution for independent operations
   - Timeout protection prevents hangs
   - Lazy evaluation (head_limit, line offsets) for large datasets
   - Background execution for long tasks

4. **Semantics Over Convenience**
   - Bash execution is persistent (session state matters)
   - Edit requires exact old_string match (prevents accidental changes)
   - Write is atomic overwrite, not append (predictable)
   - Grep outputs modes are explicit (content vs file list vs count)

5. **Error Transparency**
   - Tools fail clearly (not silently)
   - Output always captured (exit codes, stderr included)
   - Truncation indicates more data available (TaskOutput for continuation)
   - Git operations warn before destructive actions

### Tool Interaction Patterns

#### Read-Plan-Execute
- Read(file) → Analyze content → Edit(file, change)
- Safety: Preview before modification guaranteed
- Use: Code refactoring, configuration updates

#### Search-Modify-Verify
- Grep(pattern) → Read(results) → Edit(files) → Bash(validate)
- Safety: Search results reviewed before modification
- Use: Bulk code changes, migration tasks

#### Explore-Execute-Monitor
- Glob(pattern) → Bash(command) → TaskOutput(monitor) → KillShell(cleanup)
- Safety: Background task monitored/cancellable
- Use: Long-running tests, deployments

---

## 6. Tool Invocation Decision Tree

### When to Use Each Tool

**File Discovery**: Glob (fast pattern match) → Grep (content search)
**File Reading**: Read (with line pagination for large files)
**File modification**: Edit (surgical), Write (wholesale), NotebookEdit (Jupyter)
**Code execution**: Bash (general), mcp__ide__executeCode (Python/Jupyter context)
**External data**: Grep (local), WebFetch (URL content), WebSearch (indexed web)
**Long operations**: Bash + run_in_background, monitor with TaskOutput
**User coordination**: AskUserQuestion (input needed), TodoWrite (visibility)
**Planning**: EnterPlanMode (analysis), ExitPlanMode (resume execution)
**Specialized domains**: Skill (activate relevant expertise)

---

## 7. Anti-Patterns & Pitfalls

### Avoid
- **Relative paths**: Always absolute (cwd resets between calls)
- **Grep via Bash**: Use Grep tool directly (permissions, ACL)
- **Blind Write**: Always Read file first to verify content
- **Force git commands**: Require explicit approval, warn before main/master force
- **Silent failures**: All operations should have visible output/error
- **Parallel + dependencies**: Don't mix parallel calls with dependencies
- **Token hoarding**: Truncate large outputs; use TaskOutput for continuation
- **Tool reimplementation**: Use specialized tools (not bash-based grep, file read, etc.)

---

## 8. Implementation Recommendations for Claude Code CLI

### For Tool Developers
1. **Follow composition pattern**: Single-purpose tools combine into workflows
2. **Explicit error states**: Fail clearly, provide actionable messages
3. **Parameter validation**: Type-check, range-check, path validation at entry
4. **Timeout protection**: Always include configurable timeout
5. **Output limits**: Truncate intelligently; enable continuation patterns

### For Tool Users (Agents)
1. **Parallel first**: Check for independent operations; batch them
2. **Pipeline thinking**: Chain tool results into next tool inputs
3. **Safety gates**: Read before Write, ask before destructive ops
4. **Monitoring**: Use TaskOutput for background work, don't fire & forget
5. **Token consciousness**: Limit output scope with head_limit, offset, line ranges

### For System Design
1. **Tool discovery**: Maintain registry of available tools + patterns
2. **Skill integration**: Activate skills based on task analysis
3. **Session management**: Preserve state (Bash session, kernel state)
4. **Rate limiting**: Protect against tool abuse
5. **Logging/audit**: Track tool invocations for debugging + transparency

---

## 9. Unresolved Questions

1. **KillShell mechanism**: Does it only work with run_in_background: true? Implicit requirement?
2. **Bash persistence**: How long does session persist? Timeout? Auto-cleanup?
3. **Grep multiline semantics**: Does multiline: true affect performance significantly?
4. **WebFetch caching**: 15-min cache—is it per-URL or global? Invalidation rules?
5. **Task vs TaskOutput**: Can TaskOutput be polled for different subagents simultaneously?
6. **Skill activation**: Is there a skill discovery API, or must agents know skill names?
7. **mcp__ide__ tools**: LSP server requirements? Language support beyond Python?
8. **Edit string matching**: How are escape sequences handled in old_string?
9. **Glob sorting**: Why modification time sorting specifically? Use case?
10. **dangerouslyDisableSandbox**: Security implications—what attacks does sandboxing prevent?

---

## 10. Related Patterns in Ecosystem

### Similar to Unix Philosophy
- Single tool, single responsibility (grep, cat, sed)
- Composability via pipelines (stdin/stdout)
- Explicit over implicit (flags, options)

### Analogues in Other Systems
- **Language feature parity**: Read/Write (Python file I/O), Bash (shell scripting)
- **Testing frameworks**: Timeout patterns (pytest timeout), output capture
- **CI/CD systems**: Background task management, parallel job execution
- **Cloud CLIs**: Path validation (AWS S3 paths), safety gates (CloudFormation diffs)

---

**Document Version**: 1.0
**Analyzed**: 2025-12-25
**Scope**: Claude Code tool design based on documented parameters, descriptions, and usage patterns
**Author**: System Research
