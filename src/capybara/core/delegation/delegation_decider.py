"""
Delegation Decider for determining when to delegate tasks to child agents.

Evaluates todo items to decide if they should be delegated or executed
by the parent agent.
"""

from capybara.tools.builtin.todo_state import TodoItem


class DelegationDecider:
    """
    Decides whether todo items should be delegated to child agents.

    Uses simple heuristics to evaluate isolation, boundaries, and dependencies.
    No time estimation - agent decides based on task characteristics.
    """

    def should_delegate(self, todo: TodoItem, context: dict) -> bool:
        """
        Decide if todo should be delegated to child agent.

        Delegate when:
        - Isolated scope (no parent context needed)
        - Clear boundaries (well-defined inputs/outputs)
        - Parallelizable (no sequential dependency)

        Do-it-self when:
        - Requires parent context (conversation history)
        - Sequential dependency (depends on previous todo)
        - Unclear boundaries (vague task)

        Args:
            todo: TodoItem to evaluate
            context: Additional context

        Returns:
            True if should delegate
        """
        # Check isolation
        if self._requires_parent_context(todo):
            return False

        # Check boundaries
        if not self._has_clear_boundaries(todo):
            return False

        # Check dependencies
        if self._has_sequential_dependency(todo, context):
            return False

        # Check parallelizability
        if not self._is_parallelizable(todo, context):
            return False

        # Delegate if isolated, clear, and parallelizable
        return True

    def generate_context(self, todo: TodoItem, parent_context: dict) -> str:
        """
        Generate rich context message for child agent.

        Include:
        - Task description
        - Relevant file paths
        - Expected outcome
        - Constraints/requirements

        Args:
            todo: TodoItem being delegated
            parent_context: Context from parent agent

        Returns:
            Context string for child agent
        """
        context_parts = []

        # Task description
        context_parts.append(f"Task: {todo.content}")

        # Relevant files
        if "relevant_files" in parent_context:
            files = parent_context["relevant_files"]
            context_parts.append("\nRelevant files:\n" + "\n".join(f"- {f}" for f in files))

        # Expected outcome
        if "expected_outcome" in parent_context:
            context_parts.append(f"\nExpected outcome: {parent_context['expected_outcome']}")

        # Constraints
        if "constraints" in parent_context:
            context_parts.append(f"\nConstraints: {parent_context['constraints']}")

        return "\n\n".join(context_parts)

    def _requires_parent_context(self, todo: TodoItem) -> bool:
        """Check if task needs conversation history."""
        context_keywords = ["previous", "earlier", "above", "mentioned", "discussed"]
        return any(kw in todo.content.lower() for kw in context_keywords)

    def _has_clear_boundaries(self, todo: TodoItem) -> bool:
        """
        Check if inputs/outputs are well-defined.

        Well-defined: specific file paths, clear actions
        Ill-defined: vague terms like "improve", "optimize" without specifics
        """
        vague_keywords = ["improve", "optimize", "enhance", "better"]
        has_vague = any(kw in todo.content.lower() for kw in vague_keywords)
        has_specifics = any(char in todo.content for char in ["/", ".py", ".js", ".ts", ".md"])
        return has_specifics or not has_vague

    def _has_sequential_dependency(self, todo: TodoItem, context: dict) -> bool:
        """Check if depends on previous todo completion."""
        return bool(context.get("has_dependencies", False))

    def _is_parallelizable(self, todo: TodoItem, context: dict) -> bool:
        """
        Check if can run in parallel with other todos.

        Not parallelizable if modifies shared state.
        """
        return not context.get("modifies_shared_state", False)
