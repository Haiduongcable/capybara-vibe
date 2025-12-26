# Agent delegation, sessions, and todo lists

This note distills how OpenCode actually runs multi‑agent work, manages session context/memory, and persists todo lists so another developer can extend or reimplement the feature without bouncing through the codebase.

## Sessions, messages, and context handling
- Session records are keyed by project and a ULID‑style session ID. Creating a session writes the record to storage, sets timestamps, and optionally a `parentID` for child sessions. Default titles are timestamped; the loop later renames them when real user text arrives.
- Messages are immutable containers of ordered parts. Part types include text, reasoning, tool calls (with call IDs, status, input/output, timestamps), files, compaction markers, subtasks, retries, and step markers. Every part is addressable by `sessionID` + `messageID` + `part.id` for streaming updates.
- The prompt loop continuously:
  - Loads message history (dropping compacted parts) and finds the latest user/assistant turns.
  - If a pending `subtask` or `compaction` part exists, handles it before any new model call.
  - Enforces the active agent’s `maxSteps` and injects reminder snippets from the agent prompt (e.g., plan/todo nudges).
  - Resolves prompt parts (inline text, attached files, agent mentions, resource links) and calls the chosen model.
  - Intercepts slash commands like `/compact` to run command handlers instead of the model.
- Context protection:
  - Overflow detection sums the last assistant turn’s `input + cache.read + output` tokens and compares against `context_limit - min(output_limit, OUTPUT_TOKEN_MAX)`. If overflow is likely, a compaction job is queued.
  - Compaction emits a summarized assistant message and, when auto‑triggered, injects a synthetic “continue” user prompt so the loop resumes on the trimmed transcript.
  - Pruning walks backward through completed tool calls; once recent tool output exceeds a threshold, older tool outputs are marked compacted and dropped from future prompts (certain tools like `skill` are exempt).

## Agents and how delegation works
- Built‑ins:
  - Primary: `build` (default; full tool access), `plan` (edits denied, bash asks).
  - Subagents: `general`, `explore` (read‑heavy, faster), both with todo and write/edit tools disabled by default.
- Permissions merge global defaults with per‑agent overrides. Tool availability is filtered by permission and each agent’s tool flags; the registry also disables tools when permissions say “deny.”
- Delegation path (subtasks):
  1) A slash command marked `subtask`, or selecting a subagent, produces a `subtask` part instead of an immediate model call.
  2) The loop consumes that part by running the `task` tool.
  3) The `task` tool creates or reuses a child session (parent = caller), subscribes to bus events from that child, and mirrors child tool-part updates back to the parent message metadata so the user sees live progress.
  4) It runs the subagent with its own or inherited model, while forcing a restricted tool set (todo tools and the `task` tool itself are off unless explicitly enabled).
  5) When the subagent finishes, the parent gets the subagent’s text plus `<task_metadata>` containing the child session ID, enabling follow‑up or navigation.
- ACP bridge: Tool lifecycle events are mirrored to Agent Client Protocol clients. For todo writes, the bridge parses the JSON output, turns todos into ACP plan entries (treating `cancelled` as `completed`), and sends plan updates alongside tool status.

## Todo system internals

### Schema and storage
- Todo entries validate four fields: `id` (string ULID), `content` (task label), `status` (`pending`, `in_progress`, `completed`, `cancelled`), and `priority` (`high`, `medium`, `low`). The shared schema backs both tool inputs and API typing.
- `update(sessionID, todos)` overwrites the stored array for that session and publishes a `todo.updated` bus event carrying the full list. `get(sessionID)` returns the stored list or `[]` on cache miss or read error. Consumers always treat the emitted list as canonical.

### Tool behavior
- `todowrite`
  - Input: full todo array (validated).
  - Behavior: persists the array, emits `todo.updated`, and returns a payload with `metadata.todos`, JSON `output`, and a title showing the remaining (non‑completed) count.
  - Side effect: because the bus event carries the entire list, clients simply replace their local state.
- `todoread`
  - Input: none.
  - Behavior: reads the stored array and returns the same metadata/output shape as `todowrite` without mutating storage.
- Usage rules encoded in prompts: create todos for multi‑step/complex requests or explicit user asks; keep only one `in_progress` when possible; mark `completed` immediately; use `cancelled` for dropped tasks; skip the tool for trivial single‑step work.
- Subagents: todo tools are disabled by default for subagents and for delegated `task` runs; enable explicitly in agent config if you want subagent‑owned plans.

### Propagation to clients and API
- HTTP: `GET /session/:id/todo` returns the stored list for a session. SDKs expose `session.todo()` with the same shape as the internal schema.
- Event flow: `todo.updated` bus events are consumed by:
  - Desktop/app state sync: hydrates todos during initial sync (alongside messages/diffs) and updates them on events.
  - TUI: session sidebar collapses/expands todos; uses event updates for live refresh.
  - Web/share UI: todo tool parts render checklists directly from tool metadata; session-level lists can be fetched via the SDK.
  - ACP: plan updates mirror todo changes so external IDEs display the same state.

### Typical lifecycle
1) Agent decides to plan and calls `todowrite` with initial items.
2) Storage is overwritten and `todo.updated` fires; all clients refresh.
3) Agent marks items `in_progress`/`completed` via repeated `todowrite` calls (ideally one `in_progress` at a time).
4) Subagents usually do not touch todos unless explicitly permitted; the parent session remains the source of truth.
5) External viewers (TUI/web/ACP) render from tool metadata or the session todo API.

## How parent and subagents share context
- Session isolation: each subagent runs in its own child session with its own message history and storage (including its own todos if enabled). The child session retains the parent’s `parentID` but does not automatically inherit or mutate the parent’s messages.
- Prompt handoff: when a `subtask` is executed, the `task` tool sends the subagent the prompt text that triggered the delegation (resolved from the original command/template). That is the only automatic context passed; if richer context is needed (files, summaries), the parent must include it in that prompt text.
- Live progress mirroring: as the subagent runs tools, bus events from the child session are mirrored back into the parent message metadata so the user can see tool statuses and titles. This is a UI/status bridge only—it does not inject child outputs into the parent’s prompt context unless the parent agent chooses to read or summarize them.
- Rejoining: the subagent’s final message returns to the parent as text plus `<task_metadata>` containing the child `session_id`. The parent can then explicitly pull or summarize that child session (e.g., via a follow-up command or manual read) to incorporate results into its own context.
- Compaction independence: compaction/pruning are applied per session. Parent context shrinking does not affect child transcripts, and vice versa.
- Todo ownership: by default, only the parent session’s todo list is manipulated. Child sessions have todo tools disabled unless turned on, keeping planning state separate unless deliberately linked.

## Implementation guidance
- Extending the model: add optional fields to the todo schema, update both tools, storage readers, SDK typing, and the `/session/:id/todo` handler; keep JSON output backward compatible when possible.
- Delegated planning: if a subagent should own a todo list, turn the todo tools on for that agent and decide whether the parent should mirror or aggregate child todos (current behavior keeps them isolated).
- Client work: subscribe to `todo.updated` rather than polling; hydrate with `session.todo` on load to avoid drift between tabs/clients.
- Context safety: keep todo `content` concise; rely on `priority` and `status` instead of stuffing state into the description so token usage stays small during prompt construction.
