"""Multi-agent delegation components."""

from capybara.core.delegation.child_errors import ChildFailure, FailureCategory
from capybara.core.delegation.event_bus import Event, EventBus, EventType, get_event_bus
from capybara.core.delegation.session_manager import SessionManager

__all__ = [
    "SessionManager",
    "EventBus",
    "Event",
    "EventType",
    "get_event_bus",
    "ChildFailure",
    "FailureCategory",
]
