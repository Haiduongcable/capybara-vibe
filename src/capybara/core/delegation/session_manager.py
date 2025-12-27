"""Session hierarchy and lifecycle management."""

from typing import Optional
from ulid import ULID

from capybara.memory.storage import ConversationStorage


class SessionManager:
    """Manages parent-child session relationships."""

    def __init__(self, storage: ConversationStorage):
        self.storage = storage

    async def create_child_session(
        self,
        parent_id: str,
        model: str,
        prompt: str,
        title: Optional[str] = None,
    ) -> str:
        """Create child session and return ID."""
        child_id = str(ULID())
        await self.storage.create_session(
            session_id=child_id,
            model=model,
            title=title or f"Subtask of {parent_id[:8]}",
            parent_id=parent_id,
            agent_mode="child",
        )
        return child_id

    async def get_hierarchy(self, session_id: str) -> dict:
        """Get full hierarchy info for a session."""
        return await self.storage.get_session_hierarchy(session_id)

    async def get_children(self, parent_id: str) -> list[str]:
        """Get list of child session IDs."""
        children = await self.storage.get_child_sessions(parent_id)
        return [c["id"] for c in children]

    async def is_child_session(self, session_id: str) -> bool:
        """Check if session is a child."""
        hierarchy = await self.get_hierarchy(session_id)
        return hierarchy.get("parent_id") is not None

    async def get_agent_mode(self, session_id: str) -> str:
        """Get agent mode (parent/child) for session."""
        hierarchy = await self.get_hierarchy(session_id)
        return hierarchy.get("agent_mode", "parent")
