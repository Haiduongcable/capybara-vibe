"""Tests for DelegationDecider."""

import pytest
from capybara.core.delegation.delegation_decider import DelegationDecider
from capybara.tools.builtin.todo import TodoItem, TodoStatus


class TestDelegationDecider:
    """Test DelegationDecider logic."""

    def test_should_delegate_isolated_task(self):
        """Test isolated tasks are delegated."""
        decider = DelegationDecider()

        todo = TodoItem(
            id="1",
            content="Add unit tests for auth.py",
            status=TodoStatus.PENDING
        )
        context = {
            'has_dependencies': False,
            'modifies_shared_state': False
        }

        assert decider.should_delegate(todo, context) is True

    def test_no_delegate_requires_context(self):
        """Test tasks requiring parent context aren't delegated."""
        decider = DelegationDecider()

        todo = TodoItem(
            id="1",
            content="Update the file we discussed earlier",
            status=TodoStatus.PENDING
        )
        context = {}

        assert decider.should_delegate(todo, context) is False

    def test_no_delegate_sequential_dependency(self):
        """Test sequential dependencies prevent delegation."""
        decider = DelegationDecider()

        todo = TodoItem(
            id="1",
            content="Run tests after migration completes",
            status=TodoStatus.PENDING
        )
        context = {'has_dependencies': True}

        assert decider.should_delegate(todo, context) is False

    def test_no_delegate_modifies_shared_state(self):
        """Test tasks modifying shared state aren't delegated."""
        decider = DelegationDecider()

        todo = TodoItem(
            id="1",
            content="Update global configuration",
            status=TodoStatus.PENDING
        )
        context = {'modifies_shared_state': True}

        assert decider.should_delegate(todo, context) is False

    def test_context_generation(self):
        """Test context generation for delegated tasks."""
        decider = DelegationDecider()

        todo = TodoItem(
            id="1",
            content="Implement login endpoint",
            status=TodoStatus.PENDING
        )
        parent_context = {
            'relevant_files': ['src/auth.py', 'tests/test_auth.py'],
            'expected_outcome': 'POST /login endpoint with JWT response',
            'constraints': 'Use bcrypt for passwords'
        }

        context_msg = decider.generate_context(todo, parent_context)

        assert "Implement login endpoint" in context_msg
        assert "src/auth.py" in context_msg
        assert "JWT response" in context_msg
        assert "bcrypt" in context_msg

    def test_clear_boundaries_detection(self):
        """Test detection of clear vs unclear task boundaries."""
        decider = DelegationDecider()

        clear_tasks = [
            "Edit src/auth.py to add login function",
            "Add tests to tests/test_auth.py",
        ]

        unclear_tasks = [
            "Improve the code quality",
            "Optimize performance",
        ]

        for content in clear_tasks:
            todo = TodoItem(id="1", content=content, status=TodoStatus.PENDING)
            assert decider._has_clear_boundaries(todo) is True

        for content in unclear_tasks:
            todo = TodoItem(id="1", content=content, status=TodoStatus.PENDING)
            assert decider._has_clear_boundaries(todo) is False
