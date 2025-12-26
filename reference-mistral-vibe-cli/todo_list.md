# Plan: Integrating Todo List Tools into Agent Coding

## Table of Contents

1. [Overview](#overview)
2. [Agent Behavior with Todo List](#agent-behavior-with-todo-list) - **← START HERE to understand how agents actually use todos**
3. [Understanding the Todo Tool](#understanding-the-todo-tool) - Technical architecture
4. [Integration Steps](#integration-steps) - How to add todos to your agent
5. [Best Practices](#best-practices) - Recommended patterns
6. [Advanced Use Cases](#advanced-use-cases) - Complex scenarios
7. [Real-World Examples](#real-world-examples) - Code examples from Mistral Vibe
8. [Implementation Checklist](#implementation-checklist) - Step-by-step guide
9. [Common Pitfalls](#common-pitfalls) - What to avoid
10. [Resources](#resources) - Source code references

## Overview

This document outlines the plan for integrating the Mistral Vibe todo list tool into your agent coding system. The todo tool provides a stateful task management system that allows AI agents to track their work, break down complex tasks, and maintain context across conversations.

### What You'll Learn

- **Agent Behavior**: How the Mistral Vibe agent actually uses todos in practice (with real code flows)
- **Context Management**: How todos integrate into conversation history and state
- **Implementation Patterns**: Proven patterns for task breakdown, status management, and progress tracking
- **Technical Details**: Tool architecture, permissions, validation, and lifecycle
- **Best Practices**: Guidelines from the Mistral Vibe codebase on effective todo usage
- **Real Examples**: Actual code examples and test cases from the repository

### Quick Facts

| Aspect | Detail |
|--------|--------|
| **Source File** | `vibe/core/tools/builtins/todo.py` |
| **Permission** | `ALWAYS` (never requires user approval) |
| **State Scope** | Session-only (not persisted across agent restarts) |
| **Max Todos** | 100 (configurable) |
| **Operations** | Read (get all todos) and Write (replace all todos) |
| **Plan Mode** | ✅ Allowed (great for planning without execution) |
| **Context** | All todo operations stored in message history |

## Agent Behavior with Todo List

### How the Agent Uses Todos in Practice

Based on the Mistral Vibe codebase analysis, here's exactly how the agent behaves when using the todo tool:

#### 1. **Initial Task Receipt**

When a user gives the agent a complex task:

```
User: "Refactor the authentication module to use OAuth2"
```

**Agent's Internal Process:**
1. **LLM Turn 1**: Agent receives the user message in `agent.act(msg)`
2. **System Prompt Context**: The agent sees the todo tool description from `prompts/todo.md`:
   - Instructions to use todos for complex multi-step tasks (3+ steps)
   - Task management best practices
   - Status management rules
3. **Decision Point**: Agent decides if this warrants todo tracking (it does - complex refactoring)
4. **Tool Call**: Agent calls `todo(action="write", todos=[...])` with initial task breakdown

**Message Flow:**
```python
# In agent.messages:
[
  LLMMessage(role="system", content="<system prompt with todo instructions>"),
  LLMMessage(role="user", content="Refactor the authentication module..."),
  LLMMessage(role="assistant", content="I'll break this down into tasks", tool_calls=[...]),
  LLMMessage(role="tool", tool_call_id="...", content="message: Updated 5 todos\ntodos: [...]\ntotal_count: 5")
]
```

#### 2. **Todo Creation Flow**

**Event Sequence:**
```python
# Events yielded by agent.act():
AssistantEvent(content="I'll break this down into manageable tasks...")
ToolCallEvent(tool_name="todo", args=TodoArgs(action="write", todos=[...]))
ToolResultEvent(tool_name="todo", result=TodoResult(message="Updated 5 todos", todos=[...], total_count=5))
```

**State Changes:**
```python
# Before tool execution:
tool_instance.state.todos = []

# After tool execution:
tool_instance.state.todos = [
    TodoItem(id="1", content="Read current auth implementation", status="pending", priority="high"),
    TodoItem(id="2", content="Research OAuth2 best practices", status="pending", priority="medium"),
    # ... more todos
]
```

**Context Update:**
- Tool result is added to `agent.messages` as a `role="tool"` message
- Next LLM turn has access to the todo result in context
- Agent can now reference specific tasks by ID

#### 3. **Executing Tasks from Todos**

**Before Starting Work:**

```python
# Agent marks task as in_progress BEFORE executing
AssistantEvent(content="I'll start with task 1: reading the current implementation")
ToolCallEvent(tool_name="todo", args=TodoArgs(action="write", todos=[
    TodoItem(id="1", status="in_progress", ...),  # Changed from pending
    TodoItem(id="2", status="pending", ...),
    # ... rest unchanged
]))
ToolResultEvent(tool_name="todo", result=TodoResult(...))

# Then executes the actual work
ToolCallEvent(tool_name="read_file", args=ReadFileArgs(path="src/auth.py"))
```

**Agent Context Awareness:**
- The agent maintains awareness through message history
- Each tool result stays in `agent.messages[]` 
- Context window includes all previous todo states
- Agent can "remember" what it planned even across multiple turns

#### 4. **Task Completion and Updates**

**After Completing Work:**

```python
# Agent reads file, understands the code
ToolResultEvent(tool_name="read_file", result=ReadFileResult(content="..."))

# Agent marks task complete and moves to next
ToolCallEvent(tool_name="todo", args=TodoArgs(action="write", todos=[
    TodoItem(id="1", status="completed", ...),    # Just finished
    TodoItem(id="2", status="in_progress", ...),  # Starting next
    TodoItem(id="3", status="pending", ...),
    # ...
]))
```

**Dynamic Task Discovery:**
```python
# If agent discovers new requirements while working:
ToolCallEvent(tool_name="todo", args=TodoArgs(action="write", todos=[
    TodoItem(id="1", status="completed", ...),
    TodoItem(id="2", status="in_progress", ...),
    TodoItem(id="3", status="pending", ...),
    TodoItem(id="4", status="pending", content="Fix TypeScript errors found", priority="high"),  # NEW
    TodoItem(id="5", status="pending", ...),
]))
```

#### 5. **Context Before and After Using Todos**

**Before Using Todos:**

```python
# Agent's message context:
agent.messages = [
    LLMMessage(role="system", content="<system prompt>"),
    LLMMessage(role="user", content="Complex task request"),
    LLMMessage(role="assistant", content="I'll help with that..."),
]

# Agent's mental state:
# - Has user request in recent context
# - No structured task tracking
# - May forget steps in long conversations
# - No progress tracking
```

**After Using Todos:**

```python
# Agent's message context (enriched):
agent.messages = [
    LLMMessage(role="system", content="<system prompt>"),
    LLMMessage(role="user", content="Complex task request"),
    LLMMessage(role="assistant", content="I'll break this down", tool_calls=[...]),
    LLMMessage(role="tool", content="message: Updated 5 todos\ntodos: [TodoItem(id='1',...), ...]"),  # ← STRUCTURED STATE
    LLMMessage(role="assistant", content="Starting task 1", tool_calls=[...]),
    LLMMessage(role="tool", content="message: Updated 5 todos\ntodos: [TodoItem(id='1', status='in_progress',...), ...]"),
    # ... work continues
]

# Agent's mental state:
# - Clear task breakdown visible in context
# - Current status of each task available
# - Can reference specific task IDs
# - Progress is trackable and reportable
# - Less likely to forget steps
```

#### 6. **Plan Mode Special Behavior**

When in PLAN mode (`AgentMode.PLAN`):

```python
# Configuration for Plan Mode (modes.py):
PLAN_MODE_TOOLS = ["grep", "read_file", "todo"]  # ← Todo is allowed!

# Plan mode middleware injects reminder:
PLAN_MODE_REMINDER = """Plan mode is active. You MUST NOT make any edits...
Instead, you should:
1. Answer the user's query comprehensively
2. When you're done researching, present your plan..."""
```

**Agent Behavior in Plan Mode:**
1. Can freely use `todo` to create task plans
2. Cannot execute destructive tools (write_file, bash, etc.)
3. Uses todos to outline the plan without executing
4. Provides user with structured breakdown before getting approval

**Example Plan Mode Flow:**
```python
# User switches to plan mode
agent = Agent(config, mode=AgentMode.PLAN)

# User: "Refactor the auth module"
# Agent can:
ToolCallEvent(tool_name="grep", args=...)      # ✓ Allowed (read-only)
ToolCallEvent(tool_name="read_file", args=...) # ✓ Allowed (read-only)  
ToolCallEvent(tool_name="todo", args=...)      # ✓ Allowed (planning)
ToolCallEvent(tool_name="write_file", args=...)# ✗ BLOCKED (not in PLAN_MODE_TOOLS)

# Plan mode auto-approves todos (auto_approve=True in plan mode)
```

#### 7. **State Persistence Within Session**

**During Agent Session:**
```python
# Tool instances are cached in ToolManager:
class ToolManager:
    def __init__(self, config):
        self._instances: dict[str, BaseTool] = {}  # Cached instances
    
    def get(self, tool_name: str) -> BaseTool:
        if tool_name in self._instances:
            return self._instances[tool_name]  # ← Returns SAME instance
        # ... create new instance if not cached

# This means:
tool1 = tool_manager.get("todo")  # Creates instance with empty state
tool1.state.todos = [TodoItem(...)]  # Modifies state

tool2 = tool_manager.get("todo")  # Returns SAME instance
# tool2.state.todos == tool1.state.todos  # ← Same state!
```

**State Lifecycle:**
```python
# Session starts:
agent = Agent(config)
agent.tool_manager.get("todo").state.todos = []  # Empty

# After todo write:
agent.tool_manager.get("todo").state.todos = [TodoItem(...), ...]  # Populated

# Multiple turns later:
agent.tool_manager.get("todo").state.todos  # ← Still has all todos

# Session ends (agent instance destroyed):
# State is lost - not persisted to disk by default
```

**Between Sessions:**
- State is NOT automatically persisted
- Each new `Agent()` instance gets fresh tool instances
- Must implement custom persistence (see persistence patterns below)

#### 8. **Conversation Loop Integration**

**The Full Flow:**

```python
async def _conversation_loop(self, user_msg: str):
    # 1. Add user message
    self.messages.append(LLMMessage(role="user", content=user_msg))
    
    while True:
        # 2. LLM generates response (may include tool calls)
        async for event in self._perform_llm_turn():
            # Events: AssistantEvent, ToolCallEvent, ToolResultEvent
            yield event
        
        # 3. Check if last message was from tools
        last_message = self.messages[-1]
        if last_message.role != Role.tool:
            break  # Done - no more tool calls
        
        # 4. If tool calls happened, loop continues
        # Next LLM turn sees tool results in context
```

**Example Multi-Turn with Todos:**

```python
# Turn 1: User request
User → "Refactor auth module"

# Turn 2: Agent creates todos
Agent → AssistantEvent("I'll break this down...")
Agent → ToolCallEvent(todo, action="write", todos=[...])
Agent → ToolResultEvent(result=TodoResult(total_count=5))
# last_message.role == "tool" → continue loop

# Turn 3: Agent sees todo result, starts work
Agent → AssistantEvent("Starting with task 1...")
Agent → ToolCallEvent(todo, action="write", todos=[id="1" → in_progress])
Agent → ToolResultEvent(...)
Agent → ToolCallEvent(read_file, path="src/auth.py")
Agent → ToolResultEvent(...)
# last_message.role == "tool" → continue loop

# Turn 4: Agent continues with analysis
Agent → AssistantEvent("I've read the code. Here's what I found...")
# last_message.role == "assistant" → break loop (no tool calls)
```

#### 9. **Auto-Approval Behavior**

**Default Mode (ASK):**
```python
agent = Agent(config, mode=AgentMode.DEFAULT)
# Todo tool has permission="always" by default
# → No user approval needed for todo operations
```

**Auto-Approve Mode:**
```python
agent = Agent(config, mode=AgentMode.AUTO_APPROVE)
# All tools auto-approved
# → Agent can freely manage todos and execute tasks
```

**Permission Check Flow:**
```python
async def _should_execute_tool(self, tool, args, tool_call_id):
    # Check 1: Auto-approve mode?
    if self.auto_approve:
        return ToolDecision(verdict=EXECUTE)
    
    # Check 2: Tool's permission setting
    if tool.config.permission == ToolPermission.ALWAYS:
        return ToolDecision(verdict=EXECUTE)  # ← Todo takes this path
    
    # Check 3: Allowlist/denylist
    result = tool.check_allowlist_denylist(args)
    if result == ToolPermission.ALWAYS:
        return ToolDecision(verdict=EXECUTE)
    
    # Check 4: Ask user
    if self.approval_callback:
        response = await self.approval_callback(...)
        # ... handle user response
```

**For Todo Tool:**
- Default `permission = ToolPermission.ALWAYS`
- Never asks user for approval
- Always executes immediately
- Rational: Safe, non-destructive operation

#### 10. **Statistics and Tracking**

**Agent tracks todo usage:**
```python
# When todo is called:
self.stats.tool_calls_agreed += 1  # Approved to run
# After successful execution:
self.stats.tool_calls_succeeded += 1
# If it fails:
self.stats.tool_calls_failed += 1

# Stats are available at any time:
print(f"Total tool calls: {agent.stats.tool_calls_agreed}")
print(f"Successful: {agent.stats.tool_calls_succeeded}")
```

**End of session logging:**
```python
# In _conversation_loop finally block:
finally:
    await self.interaction_logger.save_interaction(
        self.messages,  # Includes all todo tool calls and results
        self.stats,     # Includes todo usage statistics
        self.config,
        self.tool_manager
    )
```

#### 11. **Exact Prompts the Agent Sees**

**System Prompt Component (from `prompts/todo.md`):**

The agent receives these instructions as part of the system prompt when the todo tool is available:

```markdown
Use the `todo` tool to manage a simple task list. This tool helps you track tasks and their progress.

## When to Use This Tool

**Use proactively for:**
- Complex multi-step tasks (3+ distinct steps)
- Non-trivial tasks requiring careful planning
- Multiple tasks provided by the user (numbered or comma-separated)
- Tracking progress on ongoing work
- After receiving new instructions - immediately capture requirements
- When starting work - mark task as in_progress BEFORE beginning
- After completing work - mark as completed and add any follow-up tasks discovered

**Skip this tool for:**
- Single, straightforward tasks
- Trivial operations (< 3 simple steps)
- Purely conversational or informational requests

## Task Management Best Practices

1. **Status Management:**
   - Only ONE task should be `in_progress` at a time
   - Mark tasks `in_progress` BEFORE starting work on them
   - Mark tasks `completed` IMMEDIATELY after finishing
   - Keep tasks `in_progress` if blocked or encountering errors

2. **Task Completion Rules:**
   - ONLY mark as `completed` when FULLY accomplished
   - Never mark complete if tests are failing, implementation is partial, or errors are unresolved
```

**This guidance shapes agent behavior to:**
- Be proactive about using todos for complex tasks
- Follow strict status management (one in_progress at a time)
- Update status before and after work (not just at the end)
- Add newly discovered tasks dynamically

**Tool Schema Sent to LLM:**

```json
{
  "type": "function",
  "function": {
    "name": "todo",
    "description": "Manage todos. Use action='read' to view, action='write' with complete list to update.",
    "parameters": {
      "type": "object",
      "properties": {
        "action": {
          "type": "string",
          "description": "Either 'read' or 'write'"
        },
        "todos": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "id": {"type": "string"},
              "content": {"type": "string"},
              "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
              "priority": {"type": "string", "enum": ["low", "medium", "high"]}
            },
            "required": ["id", "content"]
          },
          "description": "Complete list of todos when writing."
        }
      },
      "required": ["action"]
    }
  }
}
```

**Plan Mode Reminder (injected every turn):**

When in plan mode, agent sees this injected into context:

```
<vibe_warning>Plan mode is active. The user indicated that they do not want you to execute yet -- 
you MUST NOT make any edits, run any non-readonly tools (including changing configs or making commits), 
or otherwise make any changes to the system. This supersedes any other instructions you have received. 
Instead, you should:
1. Answer the user's query comprehensively
2. When you're done researching, present your plan by giving the full plan and not doing further tool 
   calls to return input to the user. Do NOT make any file changes or run any tools that modify the 
   system state in any way until the user has confirmed the plan.</vibe_warning>
```

This keeps the agent from executing work, but allows todo planning.

#### 12. **Tool Result Format in Context**

**After todo tool execution, the agent sees:**

```
message: Updated 5 todos
todos: [TodoItem(id='1', content='Read current auth implementation', status='pending', priority='high'), TodoItem(id='2', content='Research OAuth2 best practices', status='pending', priority='medium'), TodoItem(id='3', content='Design new auth flow', status='pending', priority='high'), TodoItem(id='4', content='Implement OAuth2 provider integration', status='pending', priority='high'), TodoItem(id='5', content='Update tests', status='pending', priority='medium')]
total_count: 5
```

**This structured format allows the agent to:**
- See the exact current state of all todos
- Parse and reference specific task IDs
- Understand status and priority of each task
- Make informed decisions about what to do next

**Example of how agent uses this in next turn:**

```
LLM sees in context:
  [previous messages...]
  role="tool": "message: Updated 5 todos\ntodos: [TodoItem(id='1', status='pending',...), ...]"

LLM generates:
  "I can see 5 tasks planned. Let me start with task 1 (high priority): reading the current 
   auth implementation..."
  
  tool_call: todo(action="write", todos=[
    {"id": "1", "status": "in_progress", ...},  ← Changed
    {"id": "2", "status": "pending", ...},
    ...
  ])
```

### Key Takeaways

1. **Todos are part of conversation context** - Every todo read/write adds to message history
2. **State is session-scoped** - Persists within agent instance, lost between sessions
3. **Always auto-approved** - No user confirmation needed (permission=ALWAYS)
4. **Plan mode friendly** - Explicitly included in read-only planning tools
5. **Proactive usage encouraged** - System prompt instructs agent to use for complex tasks
6. **Dynamic and flexible** - Agent can add/modify tasks as work progresses
7. **Context-aware** - Agent sees previous todo states in message history
8. **Guided by detailed prompts** - Receives specific instructions on when/how to use todos
9. **Status-driven workflow** - Prompted to mark tasks in_progress before work, completed after
10. **Full state visibility** - Tool results show complete todo list in structured format

## Understanding the Todo Tool

### Architecture

The todo tool (`vibe/core/tools/builtins/todo.py`) is built on Mistral Vibe's tool framework:

1. **Tool Components**:
   - `TodoArgs`: Input model defining the action ('read' or 'write') and optional todos list
   - `TodoResult`: Output model containing message, todos list, and total count
   - `TodoConfig`: Configuration with permission level (default: ALWAYS) and max_todos limit (100)
   - `TodoState`: Persistent state that stores the current todos list
   - `Todo`: Main tool class implementing BaseTool

2. **Data Models**:
   - `TodoItem`: Each todo has:
     - `id`: Unique identifier (string)
     - `content`: Description of the task
     - `status`: PENDING, IN_PROGRESS, COMPLETED, or CANCELLED
     - `priority`: LOW, MEDIUM, or HIGH

3. **Operations**:
   - **Read**: Retrieves all current todos
   - **Write**: Replaces the entire todo list (validates uniqueness of IDs and max limit)

### Key Features

- **Stateful**: Todos persist within the agent session (stored in `TodoState`)
- **Always Allowed**: Default permission is `ALWAYS` (no user approval needed)
- **Validation**: Enforces unique IDs and maximum todo count
- **Simple API**: Only two actions - read and write

## Integration Steps

### 1. Tool Discovery & Registration

The tool is automatically discovered by the ToolManager through:

```python
# vibe/core/tools/manager.py
class ToolManager:
    def __init__(self, config: VibeConfig):
        # Discovers tools from search paths
        self._available: dict[str, type[BaseTool]] = {
            cls.get_name(): cls for cls in self._iter_tool_classes(self._search_paths)
        }
```

**Search Paths** (in order):
1. Built-in tools directory (`vibe/core/tools/builtins/`)
2. User-configured tool paths (`config.tool_paths`)
3. Local project tools directory (`.vibe/tools/`)
4. Global tools directory (`~/.vibe/tools/`)

### 2. Create Custom Todo Tool (If Needed)

If you need to customize the todo tool for your agent:

#### Option A: Extend the Existing Tool

```python
from vibe.core.tools.builtins.todo import (
    Todo, TodoArgs, TodoResult, TodoConfig, TodoState, TodoItem
)

class CustomTodoConfig(TodoConfig):
    max_todos: int = 200  # Increase limit
    auto_cleanup: bool = True  # Custom config option

class CustomTodo(Todo):
    async def run(self, args: TodoArgs) -> TodoResult:
        # Add custom logic
        result = await super().run(args)
        
        if self.config.auto_cleanup:
            # Clean up completed todos automatically
            self.state.todos = [
                t for t in self.state.todos 
                if t.status != TodoStatus.COMPLETED
            ]
        
        return result
```

#### Option B: Create a New Tool from Scratch

```python
from vibe.core.tools.base import BaseTool, BaseToolConfig, BaseToolState
from pydantic import BaseModel, Field

class MyTaskArgs(BaseModel):
    action: str
    task_data: dict | None = None

class MyTaskResult(BaseModel):
    success: bool
    tasks: list[dict]

class MyTaskConfig(BaseToolConfig):
    permission: ToolPermission = ToolPermission.ASK
    
class MyTaskState(BaseToolState):
    tasks: list[dict] = Field(default_factory=list)

class MyTaskTool(
    BaseTool[MyTaskArgs, MyTaskResult, MyTaskConfig, MyTaskState]
):
    description = "Custom task management tool"
    
    async def run(self, args: MyTaskArgs) -> MyTaskResult:
        # Implementation
        pass
```

### 3. Configure the Tool

Add configuration to your `config.toml`:

```toml
[tools.todo]
permission = "always"  # always, ask, or never
max_todos = 100

# If you created a custom tool
[tools.custom_todo]
permission = "ask"
max_todos = 200
auto_cleanup = true
```

### 4. Agent Integration Patterns

#### Pattern 1: Automatic Task Breakdown

Train/prompt your agent to automatically create todos for complex requests:

```python
# In your system prompt or agent instructions:
"""
When a user gives you a complex task:
1. Break it down into smaller subtasks
2. Use the todo tool to track your progress
3. Update todo status as you complete each step
4. Use IDs like: "task-1", "task-2", etc.
"""
```

Example agent flow:
```
User: "Refactor the authentication module to use OAuth2"

Agent: Let me break this down into manageable tasks.

> todo(action="write", todos=[
    {id: "task-1", content: "Read current auth implementation", priority: "high"},
    {id: "task-2", content: "Research OAuth2 best practices", priority: "medium"},
    {id: "task-3", content: "Design new auth flow", priority: "high"},
    {id: "task-4", content: "Implement OAuth2 provider integration", priority: "high"},
    {id: "task-5", content: "Update tests", priority: "medium"},
    {id: "task-6", content: "Update documentation", priority: "low"}
  ])

> read_file(path="src/auth/current_auth.py")
> todo(action="write", todos=[...updated with task-1 as completed...])
```

#### Pattern 2: Session Continuity

Use todos to maintain context across sessions:

```python
# At the start of a new session, check for existing todos
> todo(action="read")

# Agent can continue where it left off
"I see we have 3 pending tasks from our previous session..."
```

#### Pattern 3: Parallel Task Management

For multi-step operations:

```python
# Agent tracks multiple parallel workflows
todos = [
    {id: "backend-1", content: "Update API endpoint", status: "in_progress"},
    {id: "backend-2", content: "Add validation", status: "pending"},
    {id: "frontend-1", content: "Update UI component", status: "in_progress"},
    {id: "frontend-2", content: "Add error handling", status: "pending"},
    {id: "testing-1", content: "Write integration tests", status: "pending"}
]
```

### 5. Tool State Persistence

The todo state is stored in memory during the agent session. For persistence across sessions:

#### Option A: Manual Serialization

```python
# Save todos to file when session ends
async def save_session_state(self):
    todos = await self.tools.get("todo").invoke(action="read")
    with open(".vibe/session_state.json", "w") as f:
        json.dump(todos.model_dump(), f)

# Restore on session start
async def restore_session_state(self):
    if Path(".vibe/session_state.json").exists():
        with open(".vibe/session_state.json") as f:
            data = json.load(f)
            await self.tools.get("todo").invoke(
                action="write",
                todos=data["todos"]
            )
```

#### Option B: Custom State Backend

Create a tool with file-based or database persistence:

```python
class PersistentTodoState(TodoState):
    def __init__(self):
        super().__init__()
        self._load_from_disk()
    
    def _load_from_disk(self):
        if Path(".todos.json").exists():
            with open(".todos.json") as f:
                self.todos = [TodoItem(**t) for t in json.load(f)]
    
    def _save_to_disk(self):
        with open(".todos.json", "w") as f:
            json.dump([t.model_dump() for t in self.todos], f)
```

### 6. UI Integration

The tool includes display methods for rich terminal output:

```python
@classmethod
def get_call_display(cls, event: ToolCallEvent) -> ToolCallDisplay:
    # Shows "Reading todos" or "Writing N todos"
    
@classmethod
def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
    # Shows success message with count
```

Customize these for your UI:

```python
class CustomTodo(Todo):
    @classmethod
    def get_result_display(cls, event: ToolResultEvent) -> ToolResultDisplay:
        result = event.result
        
        # Create a formatted display
        message = f"📝 {result.message}\n"
        for todo in result.todos:
            status_icon = {
                "pending": "⏳",
                "in_progress": "🔄", 
                "completed": "✅",
                "cancelled": "❌"
            }[todo.status]
            
            message += f"{status_icon} [{todo.priority}] {todo.content}\n"
        
        return ToolResultDisplay(success=True, message=message)
```

### 7. Testing Strategy

Create tests for your todo integration:

```python
import pytest
from vibe.core.tools.builtins.todo import Todo, TodoArgs, TodoItem, TodoStatus

@pytest.mark.asyncio
async def test_todo_workflow():
    # Create tool instance
    tool = Todo.from_config(Todo._get_tool_config_class()())
    
    # Start with empty todos
    result = await tool.run(TodoArgs(action="read"))
    assert len(result.todos) == 0
    
    # Add todos
    todos = [
        TodoItem(id="1", content="Task 1", priority="high"),
        TodoItem(id="2", content="Task 2", priority="low")
    ]
    result = await tool.run(TodoArgs(action="write", todos=todos))
    assert result.total_count == 2
    
    # Update status
    todos[0].status = TodoStatus.COMPLETED
    result = await tool.run(TodoArgs(action="write", todos=todos))
    assert result.todos[0].status == TodoStatus.COMPLETED
    
    # Test validation
    with pytest.raises(ToolError):
        # Duplicate IDs should fail
        await tool.run(TodoArgs(action="write", todos=[
            TodoItem(id="1", content="A"),
            TodoItem(id="1", content="B")
        ]))
```

## Best Practices

### 1. ID Convention

Use consistent ID patterns:
- Sequential: `task-1`, `task-2`, `task-3`
- Hierarchical: `feature-auth-1`, `feature-auth-2`, `bugfix-ui-1`
- UUID-based: For distributed systems

### 2. Task Granularity

- Break complex tasks into 5-10 subtasks
- Each task should be completable in one tool execution cycle
- Use priority to guide execution order

### 3. Status Management

- Start all tasks as PENDING
- Mark IN_PROGRESS when actively working
- Update to COMPLETED immediately after finishing
- Use CANCELLED for abandoned or invalid tasks

### 4. Error Handling

Always validate before writing:

```python
# Check if we're at max capacity
current = await tool.invoke(action="read")
if len(current.todos) + len(new_todos) > config.max_todos:
    # Handle overflow - maybe archive completed ones
    pass
```

### 5. Prompt Engineering

Include todo management in your system prompt:

```markdown
## Task Management

You have access to a `todo` tool for tracking your work:

- **Before starting**: Break complex requests into subtasks
- **During execution**: Update task status as you progress
- **After completion**: Mark tasks as completed
- **Use priorities**: HIGH for critical path, MEDIUM for normal, LOW for nice-to-have

Format: Use clear, action-oriented task descriptions
- ✅ "Implement user authentication endpoint"
- ❌ "Work on auth stuff"
```

## Advanced Use Cases

### 1. Multi-Agent Coordination

Share todo state between multiple agents:

```python
# Agent A writes tasks
await agent_a.tools.get("todo").invoke(
    action="write",
    todos=[TodoItem(id="shared-1", content="Prepare data")]
)

# Agent B reads and updates
todos = await agent_b.tools.get("todo").invoke(action="read")
# Process and update status
```

### 2. Progress Reporting

Generate progress reports:

```python
result = await tool.invoke(action="read")
total = len(result.todos)
completed = sum(1 for t in result.todos if t.status == "completed")
in_progress = sum(1 for t in result.todos if t.status == "in_progress")

print(f"Progress: {completed}/{total} completed, {in_progress} in progress")
```

### 3. Dependency Tracking

Extend TodoItem to track dependencies:

```python
class ExtendedTodoItem(TodoItem):
    depends_on: list[str] = Field(default_factory=list)  # IDs of prerequisite tasks
    
    def is_ready(self, all_todos: list['ExtendedTodoItem']) -> bool:
        """Check if all dependencies are completed"""
        for dep_id in self.depends_on:
            dep = next((t for t in all_todos if t.id == dep_id), None)
            if not dep or dep.status != TodoStatus.COMPLETED:
                return False
        return True
```

## Implementation Checklist

- [ ] Understand the base todo tool implementation
- [ ] Decide if you need to extend or use as-is
- [ ] Configure tool permissions in config.toml
- [ ] Update agent system prompt with todo usage guidelines
- [ ] Implement session state persistence (if needed)
- [ ] Add UI customizations (if needed)
- [ ] Write integration tests
- [ ] Train/test agent on task breakdown scenarios
- [ ] Document expected behavior for your users
- [ ] Monitor and adjust max_todos based on usage

## Common Pitfalls

1. **Not validating IDs**: Always ensure unique IDs when writing
2. **Forgetting to update status**: Tasks stuck in IN_PROGRESS
3. **Too granular**: Breaking tasks too small reduces clarity
4. **Not using priorities**: Harder to determine execution order
5. **State loss**: Not implementing persistence for long sessions
6. **Overloading**: Hitting max_todos limit without cleanup strategy

## Resources

- **Source Code**: `vibe/core/tools/builtins/todo.py`
- **Base Tool Framework**: `vibe/core/tools/base.py`
- **Tool Manager**: `vibe/core/tools/manager.py`
- **Configuration**: `vibe/core/config.py`
- **Agent Integration**: `vibe/core/agent.py`

## Visual Summary: Agent Todo Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER GIVES COMPLEX TASK                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  AGENT RECEIVES MESSAGE (agent.act("Refactor auth module"))     │
│  • Added to agent.messages as role="user"                       │
│  • System prompt includes todo tool instructions                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              LLM TURN 1: ANALYZE & PLAN                         │
│  • LLM sees: system prompt + user message                       │
│  • Decides: This needs structured task tracking                 │
│  • Generates: Assistant message + todo tool call                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         TOOL EXECUTION: todo(action="write", todos=[...])       │
│  Events: ToolCallEvent → ToolResultEvent                        │
│  State: tool.state.todos = [] → [5 TodoItems]                  │
│  Message: Added role="tool" with result to agent.messages       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         LLM TURN 2: START WORK                                  │
│  • LLM sees: previous context + todo result                     │
│  • Generates: "Starting task 1" + multiple tool calls:          │
│    - todo(write, [id="1" status="in_progress"])                │
│    - read_file(path="src/auth.py")                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         TOOL EXECUTION: Update status + Read file               │
│  State: todos[0].status = "in_progress"                         │
│  Context: File contents added to messages                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│         LLM TURN 3: ANALYZE & REPORT                            │
│  • LLM sees: all previous context including:                    │
│    - Initial task breakdown (todos)                             │
│    - Current status (task 1 in_progress)                        │
│    - File contents read                                         │
│  • Can reference specific tasks: "Task 1 complete, found issue" │
│  • Updates todos: mark completed, add new tasks if needed       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                         [Continues...]

MESSAGE HISTORY AT ANY POINT:
┌─────────────────────────────────────────────────────────────────┐
│ agent.messages = [                                              │
│   LLMMessage(role="system", content="<system + todo prompt>"),  │
│   LLMMessage(role="user", content="Refactor auth module"),      │
│   LLMMessage(role="assistant", content="...", tool_calls=[...]),│
│   LLMMessage(role="tool", content="Updated 5 todos\n..."),      │
│   LLMMessage(role="assistant", content="...", tool_calls=[...]),│
│   LLMMessage(role="tool", content="Updated 5 todos\n..."),      │
│   LLMMessage(role="tool", content="<file contents>"),           │
│   LLMMessage(role="assistant", content="Analysis: ..."),        │
│   ...                                                            │
│ ]                                                               │
│                                                                 │
│ STATE PERSISTENCE:                                              │
│ tool_manager.get("todo").state.todos = [                        │
│   TodoItem(id="1", status="completed", ...),                    │
│   TodoItem(id="2", status="in_progress", ...),                  │
│   TodoItem(id="3", status="pending", ...),                      │
│   ...                                                            │
│ ]                                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Reference: Todo Tool Behavior

| Aspect | Behavior |
|--------|----------|
| **Permission** | `ALWAYS` - never asks for approval |
| **State Scope** | Session-only (lost when agent instance destroyed) |
| **Context** | All todo reads/writes added to message history |
| **Plan Mode** | Explicitly allowed (in `PLAN_MODE_TOOLS`) |
| **Auto-Approve** | Yes - executes immediately |
| **Max Todos** | 100 (configurable via `max_todos` config) |
| **Validation** | Enforces unique IDs, max count |
| **Write Behavior** | Replaces entire list (not incremental) |
| **Read Behavior** | Returns full current state |
| **Prompt Guidance** | Detailed instructions in `prompts/todo.md` |

## Real-World Examples from Codebase

### Example 1: Simple Todo Read (from tests)

```python
# User query
"What about my todos?"

# Agent flow:
AssistantEvent(content="Checking your todos.")
ToolCallEvent(
    tool_name="todo",
    args=TodoArgs(action="read")
)
ToolResultEvent(
    result=TodoResult(
        message="Retrieved 0 todos",
        todos=[],
        total_count=0
    )
)
AssistantEvent(content="Done reviewing todos.")

# Message history:
[
  LLMMessage(role="user", content="What about my todos?"),
  LLMMessage(role="assistant", content="Checking your todos.", tool_calls=[...]),
  LLMMessage(role="tool", content="message: Retrieved 0 todos\ntodos: []\ntotal_count: 0"),
  LLMMessage(role="assistant", content="Done reviewing todos.")
]
```

### Example 2: Multi-Step Task Breakdown (from prompts)

```python
# User request
"Add dark mode toggle to settings"

# Agent creates structured plan:
ToolCallEvent(
    tool_name="todo",
    args=TodoArgs(
        action="write",
        todos=[
            TodoItem(id="1", content="Add dark mode toggle to settings", status="pending", priority="high"),
            TodoItem(id="2", content="Implement theme context/state management", status="pending", priority="high"),
            TodoItem(id="3", content="Update components for theme switching", status="pending", priority="medium"),
            TodoItem(id="4", content="Run tests and verify build", status="pending", priority="medium")
        ]
    )
)

# Agent starts work:
ToolCallEvent(
    tool_name="todo",
    args=TodoArgs(
        action="write",
        todos=[
            TodoItem(id="1", content="...", status="in_progress", priority="high"),  # Started
            # ... rest unchanged
        ]
    )
)

# Agent encounters issue, adds new task:
ToolCallEvent(
    tool_name="todo",
    args=TodoArgs(
        action="write",
        todos=[
            TodoItem(id="1", content="...", status="completed", priority="high"),
            TodoItem(id="2", content="...", status="in_progress", priority="high"),
            TodoItem(id="3", content="...", status="pending", priority="medium"),
            TodoItem(id="4", content="Fix TypeScript errors in theme types", status="pending", priority="high"),  # NEW
            TodoItem(id="5", content="Run tests and verify build", status="pending", priority="medium")
        ]
    )
)
```

### Example 3: Plan Mode Workflow

```python
# User enables plan mode
agent = Agent(config, mode=AgentMode.PLAN)

# User: "Refactor authentication system"

# Agent can use these tools:
PLAN_MODE_TOOLS = ["grep", "read_file", "todo"]

# Agent behavior:
ToolCallEvent(tool_name="grep", args=...)        # ✓ Reads codebase
ToolCallEvent(tool_name="read_file", args=...)   # ✓ Examines files
ToolCallEvent(tool_name="todo", args=TodoArgs(   # ✓ Creates plan
    action="write",
    todos=[
        TodoItem(id="1", content="Analyze current auth flow", status="pending"),
        TodoItem(id="2", content="Design new OAuth2 integration", status="pending"),
        TodoItem(id="3", content="Update authentication middleware", status="pending"),
        # ... more planning tasks
    ]
))
AssistantEvent(content="""
I've analyzed the codebase and created a refactoring plan with 5 tasks:

1. Analyze current auth flow - Review existing JWT implementation
2. Design new OAuth2 integration - Plan provider setup
3. Update authentication middleware - Modify auth checks
4. Implement OAuth2 handlers - Add new endpoints
5. Update tests - Ensure coverage

Would you like me to proceed with this plan?
""")

# Agent DOES NOT execute write_file, bash, etc. (blocked by plan mode)
# User can review plan, then switch to execution mode
```

### Example 4: Streaming Mode with Todos

```python
# With enable_streaming=True
agent = Agent(config, enable_streaming=True)

# Events come in batches:
AssistantEvent(content="Checking your todos.")  # Streamed content batch
ToolCallEvent(tool_name="todo", args=...)       # Tool call parsed
ToolResultEvent(result=...)                     # Tool executed
AssistantEvent(content="Done reviewing todos.") # Next streamed batch

# Each AssistantEvent contains 5 chunks of content (BATCH_SIZE=5)
# Provides smooth real-time feedback to user
```

### Example 5: Session State Lifecycle

```python
# Session Start
agent = Agent(config)
todo_tool = agent.tool_manager.get("todo")
print(todo_tool.state.todos)  # []

# User interaction 1
async for event in agent.act("Create plan for feature X"):
    if isinstance(event, ToolResultEvent) and event.tool_name == "todo":
        print(event.result.todos)  
        # [TodoItem(id="1", ...), TodoItem(id="2", ...)]

# User interaction 2 (same session)
async for event in agent.act("What's my current plan?"):
    # Agent reads todos - state still there
    if isinstance(event, ToolResultEvent) and event.tool_name == "todo":
        print(event.result.todos)  
        # [TodoItem(id="1", status="completed", ...), TodoItem(id="2", status="in_progress", ...)]

# Session End
del agent  # or program exits

# New Session
agent2 = Agent(config)
todo_tool2 = agent2.tool_manager.get("todo")
print(todo_tool2.state.todos)  # [] - state lost!
```

### Example 6: Error Handling

```python
# Duplicate ID error:
try:
    await tool.invoke(
        action="write",
        todos=[
            TodoItem(id="1", content="Task A"),
            TodoItem(id="1", content="Task B")  # Same ID!
        ]
    )
except ToolError as e:
    print(e)  # "Todo IDs must be unique"

# Too many todos error:
try:
    todos = [TodoItem(id=str(i), content=f"Task {i}") for i in range(101)]
    await tool.invoke(action="write", todos=todos)
except ToolError as e:
    print(e)  # "Cannot store more than 100 todos"

# Agent sees these errors in ToolResultEvent:
ToolResultEvent(
    tool_name="todo",
    error="<vibe_tool_error>todo failed: Todo IDs must be unique</vibe_tool_error>",
    tool_call_id="..."
)

# Error message added to conversation context
LLMMessage(role="tool", content="<vibe_tool_error>todo failed: Todo IDs must be unique</vibe_tool_error>")

# Agent can recover:
AssistantEvent(content="I'll fix the duplicate IDs and try again...")
ToolCallEvent(tool_name="todo", args=...)  # Corrected call
```

## Common Agent Patterns Observed

1. **Proactive Planning**: Agent creates todos at start of complex tasks
2. **Status-Driven Workflow**: Marks tasks in_progress before work, completed after
3. **Dynamic Discovery**: Adds new tasks when encountering unexpected requirements
4. **Context Maintenance**: References task IDs in natural language ("Starting task 1")
5. **Progress Reporting**: Uses todo state to report progress to users
6. **Plan Mode Usage**: Creates detailed plans without execution in plan mode
7. **Error Recovery**: Handles validation errors and retries with corrections
8. **Streaming Compatibility**: Works seamlessly with streaming and non-streaming modes

## Next Steps

1. Review the todo tool source code thoroughly
2. Understand the agent behavior patterns described above
3. Design your task breakdown strategy based on observed patterns
4. Implement any custom extensions needed
5. Test with real agent scenarios, paying attention to:
   - How agent decides when to use todos
   - Status progression through tasks
   - Context management across turns
   - Dynamic task addition/modification
6. Iterate based on agent performance and user feedback
7. Consider implementing session persistence if needed
8. Monitor todo usage patterns in your specific use cases

## Appendix: Complete System Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         MISTRAL VIBE AGENT SYSTEM                         │
└───────────────────────────────────────────────────────────────────────────┘

USER INPUT
    ↓
┌──────────────────────────┐
│   Agent.act(message)     │
│  ┌────────────────────┐  │
│  │ Conversation Loop  │  │
│  └────────────────────┘  │
└──────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│                    MESSAGE HISTORY                           │
│  agent.messages = [                                          │
│    LLMMessage(role="system", content="<system_prompt>"),     │
│    LLMMessage(role="user", content="user request"),          │
│    LLMMessage(role="assistant", content="...", tool_calls),  │
│    LLMMessage(role="tool", content="todo results"),    ◄─────┼─── TODO STATE
│    ...                                                        │     VISIBLE HERE
│  ]                                                            │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│                  LLM BACKEND (Mistral AI)                    │
│  • Receives: messages + available tools                      │
│  • Returns: assistant message + tool calls                   │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│                TOOL CALL HANDLER                             │
│  format_handler.parse_message() → tool_calls                 │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│                  TOOL MANAGER                                │
│  tool_manager.get("todo") → Todo instance                    │
│                                                               │
│  Cached Instances:                                           │
│  ┌─────────────────────────────────────────────┐             │
│  │ "todo"     → Todo(config, state)            │             │
│  │ "read_file" → ReadFile(config, state)       │             │
│  │ "bash"     → Bash(config, state)            │             │
│  └─────────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│                   TODO TOOL INSTANCE                         │
│  ┌────────────────────────────────────────────┐              │
│  │ TodoConfig:                                │              │
│  │  - permission: ALWAYS                      │              │
│  │  - max_todos: 100                          │              │
│  │  - workdir: /project/path                  │              │
│  └────────────────────────────────────────────┘              │
│  ┌────────────────────────────────────────────┐              │
│  │ TodoState:                                 │ ◄────── SESSION STATE
│  │  - todos: [TodoItem(...), ...]             │         (in memory)
│  └────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│              TOOL EXECUTION FLOW                             │
│                                                               │
│  1. Validate args (TodoArgs)                                 │
│  2. Check permission (ALWAYS → skip approval)                │
│  3. Execute: tool.run(args)                                  │
│     ├─ action="read"  → return current state                 │
│     └─ action="write" → validate & update state              │
│  4. Return TodoResult                                        │
│  5. Add to messages as role="tool"                           │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│                  EVENTS YIELDED TO USER                      │
│  • AssistantEvent(content="...")                             │
│  • ToolCallEvent(tool_name="todo", args=...)                 │
│  • ToolResultEvent(result=TodoResult(...))                   │
└──────────────────────────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────────────────────────┐
│              CONVERSATION CONTINUES...                       │
│  • Loop continues if last message is role="tool"             │
│  • LLM sees updated context with todo results                │
│  • Can make informed decisions based on todo state           │
└──────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                    SPECIAL MODES                              │
├───────────────────────────────────────────────────────────────┤
│  PLAN MODE:                                                   │
│  • Only allows: grep, read_file, todo                        │
│  • Auto-approves all tools                                   │
│  • Injects reminder to not make changes                      │
│  • Perfect for creating plans without execution              │
│                                                               │
│  AUTO_APPROVE MODE:                                           │
│  • All tools auto-approved                                   │
│  • Todo still has permission=ALWAYS                          │
│  • No user confirmation for any tools                        │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  STATE LIFECYCLE                              │
├───────────────────────────────────────────────────────────────┤
│  Session Start:                                               │
│    agent = Agent(config)                                      │
│    tool_manager._instances = {}                               │
│                                                               │
│  First Todo Call:                                             │
│    tool = tool_manager.get("todo")  # Creates instance        │
│    tool.state.todos = []                                      │
│                                                               │
│  Todo Write:                                                  │
│    tool.state.todos = [TodoItem(...), ...]  # Updated         │
│                                                               │
│  Subsequent Calls:                                            │
│    tool = tool_manager.get("todo")  # Returns SAME instance   │
│    tool.state.todos  # Still has data from before            │
│                                                               │
│  Session End:                                                 │
│    del agent  # or process exits                             │
│    → All state lost (unless manually persisted)              │
└───────────────────────────────────────────────────────────────┘
```

## Document Change History

- **Initial Version**: Created comprehensive integration plan
- **Enhanced Version**: Added detailed agent behavior analysis including:
  - 12 subsections covering complete agent workflow
  - Message flow diagrams
  - State persistence explanations
  - Exact prompts the agent sees
  - Tool result formats
  - Real-world examples from test suite
  - Visual architecture diagrams
  - Complete lifecycle documentation

---

**Document Status**: ✅ Complete and Ready for Use

For questions or clarifications, refer to:
- Source code: `vibe/core/tools/builtins/todo.py`
- System prompt: `vibe/core/tools/builtins/prompts/todo.md`
- Agent implementation: `vibe/core/agent.py`
- Tool manager: `vibe/core/tools/manager.py`
