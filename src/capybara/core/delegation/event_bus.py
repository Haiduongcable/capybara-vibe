"""Async event bus for parent-child progress communication."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator, Optional

from capybara.core.logging import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    """Event types for progress tracking."""
    TOOL_START = "tool_start"
    TOOL_DONE = "tool_done"
    TOOL_ERROR = "tool_error"
    AGENT_START = "agent_start"
    AGENT_DONE = "agent_done"

    # Status transitions
    AGENT_STATE_CHANGE = "agent_state_change"
    DELEGATION_START = "delegation_start"
    DELEGATION_COMPLETE = "delegation_complete"
    CHILD_RESPONSE = "child_response"


@dataclass
class Event:
    """Progress event from child agent."""
    session_id: str
    event_type: EventType
    tool_name: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # For status events
    agent_state: Optional[str] = None
    message: Optional[str] = None


class EventBus:
    """In-memory async event bus for session events."""

    def __init__(self):
        # session_id -> Queue of subscribers
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # session_id -> recent events (for late subscribers)
        self._history: dict[str, list[Event]] = {}
        self._max_history = 100

    async def publish(self, event: Event) -> None:
        """Publish event to all subscribers of this session."""
        session_id = event.session_id

        # Store in history
        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append(event)

        # Trim history
        if len(self._history[session_id]) > self._max_history:
            self._history[session_id] = self._history[session_id][-self._max_history:]

        # Send to subscribers
        if session_id in self._subscribers:
            for queue in self._subscribers[session_id]:
                try:
                    await queue.put(event)
                except Exception as e:
                    logger.error(f"Error publishing event: {e}")

    async def subscribe(self, session_id: str) -> AsyncIterator[Event]:
        """Subscribe to events from a session. Yields events as they arrive."""
        queue: asyncio.Queue = asyncio.Queue()

        # Register subscriber
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        self._subscribers[session_id].append(queue)

        # Replay recent history to catch up
        if session_id in self._history:
            for event in self._history[session_id]:
                await queue.put(event)

        try:
            while True:
                event = await queue.get()
                yield event

                # Stop after agent done
                if event.event_type == EventType.AGENT_DONE:
                    break
        finally:
            # Cleanup
            if session_id in self._subscribers:
                self._subscribers[session_id].remove(queue)
                if not self._subscribers[session_id]:
                    del self._subscribers[session_id]

    def get_recent(self, session_id: str, limit: int = 50) -> list[Event]:
        """Get recent events for a session (non-blocking)."""
        return self._history.get(session_id, [])[-limit:]

    def cleanup_session(self, session_id: str) -> None:
        """Remove all data for a session."""
        self._subscribers.pop(session_id, None)
        self._history.pop(session_id, None)


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create global event bus."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
