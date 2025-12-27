"""Agent state management and transitions."""

import asyncio
from typing import TYPE_CHECKING

from capybara.core.agent.status import AgentState, AgentStatus
from capybara.core.delegation.event_bus import Event, EventType, EventBus
from capybara.core.logging import SessionLoggerAdapter, log_state_change

if TYPE_CHECKING:
    from capybara.ui.flow_renderer import CommunicationFlowRenderer


class AgentStateManager:
    """Manages agent state transitions and notifications.

    Responsible for:
    - Tracking agent state (idle, thinking, executing, etc.)
    - Publishing state change events
    - Logging state transitions
    - Updating flow renderer (for parent agents)
    """

    def __init__(
        self,
        status: AgentStatus,
        session_id: str | None = None,
        session_logger: SessionLoggerAdapter | None = None,
        event_bus: EventBus | None = None,
        flow_renderer: "CommunicationFlowRenderer | None" = None,
    ):
        """Initialize state manager.

        Args:
            status: Agent status object to manage
            session_id: Optional session ID for events
            session_logger: Optional session logger
            event_bus: Optional event bus for publishing
            flow_renderer: Optional flow renderer for parent agents
        """
        self.status = status
        self.session_id = session_id
        self.session_logger = session_logger
        self.event_bus = event_bus
        self.flow_renderer = flow_renderer

    def update_state(self, state: AgentState, action: str | None = None) -> None:
        """Update agent state and publish event.

        Args:
            state: New agent state
            action: Optional description of current action
        """
        old_state = self.status.state
        self.status.state = state
        self.status.current_action = action

        # Log state change
        if self.session_logger and old_state != state:
            log_state_change(
                self.session_logger,
                from_state=old_state.value,
                to_state=state.value,
                reason=action,
            )

        # Publish state change event
        if self.session_id and self.event_bus:
            asyncio.create_task(
                self.event_bus.publish(
                    Event(
                        session_id=self.session_id,
                        event_type=EventType.AGENT_STATE_CHANGE,
                        agent_state=state.value,
                        message=action,
                    )
                )
            )

        # Update flow renderer if parent
        if self.flow_renderer:
            self.flow_renderer.update_parent(self.status)
