"""Main async agent with streaming and tool calling."""

from dataclasses import dataclass
from typing import Any

from rich.console import Console

from capybara.core.agent.state_manager import AgentStateManager
from capybara.core.agent.status import AgentState, AgentStatus
from capybara.core.agent.ui_renderer import AgentUIRenderer
from capybara.core.config.settings import ToolsConfig
from capybara.core.delegation.event_bus import Event, EventType, get_event_bus
from capybara.core.execution.execution_log import ExecutionLog
from capybara.core.logging import (
    SessionLoggerAdapter,
    get_logger,
    get_session_log_manager,
    log_error,
)
from capybara.core.execution.streaming import non_streaming_completion, stream_completion
from capybara.core.execution.tool_executor import ToolExecutor
from capybara.memory.window import ConversationMemory
from capybara.providers.router import ProviderRouter
from capybara.tools.base import AgentMode
from capybara.tools.registry import ToolRegistry
from capybara.ui.flow_renderer import CommunicationFlowRenderer

logger = get_logger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    model: str = "capybara-gpt-5.2"
    max_turns: int = 70
    timeout: float = 300.0  # 5 minutes for complex tasks
    stream: bool = True
    mode: AgentMode = AgentMode.PARENT


class Agent:
    """Async agent with streaming and tool calling.

    Core orchestration class that delegates to specialized modules:
    - AgentStateManager: State transitions and events
    - AgentUIRenderer: UI rendering
    - ToolExecutor: Tool execution with permissions
    """

    def __init__(
        self,
        config: AgentConfig,
        memory: ConversationMemory,
        tools: ToolRegistry,
        console: Console | None = None,
        provider: ProviderRouter | None = None,
        tools_config: ToolsConfig | None = None,
        session_id: str | None = None,
        parent_session_id: str | None = None,
    ) -> None:
        self.config = config
        self.memory = memory
        # Filter tools by agent mode
        self.tools = tools.filter_by_mode(config.mode)
        self.console = console or Console()
        self.provider = provider or ProviderRouter(default_model=config.model)
        self.tools_config = tools_config or ToolsConfig()
        self.session_id = session_id
        self.event_bus = get_event_bus()

        # Create session-specific logger
        self.session_logger: SessionLoggerAdapter | None
        if session_id:
            log_manager = get_session_log_manager()
            self.session_logger = log_manager.create_session_logger(
                session_id=session_id,
                agent_mode=config.mode.value,
                log_level="INFO",
                parent_session_id=parent_session_id,  # Child agents write to parent's log
            )
        else:
            # Fallback to default logger if no session ID
            self.session_logger = None

        # Enable execution logging for child agents only
        self.execution_log: ExecutionLog | None = None
        if config.mode == AgentMode.CHILD:
            self.execution_log = ExecutionLog()

        # Initialize status tracking
        self.status = AgentStatus(
            session_id=session_id or "unknown",
            mode=config.mode.value,
            state=AgentState.IDLE,
        )

        # Parent agents get flow renderer
        self.flow_renderer: CommunicationFlowRenderer | None = None
        if config.mode == AgentMode.PARENT:
            self.flow_renderer = CommunicationFlowRenderer(self.console)

        # Initialize specialized modules
        self.state_manager = AgentStateManager(
            status=self.status,
            session_id=session_id,
            session_logger=self.session_logger,
            event_bus=self.event_bus,
            flow_renderer=self.flow_renderer,
        )

        self.ui_renderer = AgentUIRenderer(
            console=self.console,
            agent_mode=config.mode,
            flow_renderer=self.flow_renderer,
        )

        self.tool_executor = ToolExecutor(
            tools=self.tools,
            console=self.console,
            tools_config=self.tools_config,
            agent_mode=config.mode,
            session_id=session_id,
            session_logger=self.session_logger,
            execution_log=self.execution_log,
            event_bus=self.event_bus,
        )

    async def run(self, user_input: str) -> str:
        """Main agent loop with tool use.

        Args:
            user_input: User's message

        Returns:
            Final response from the agent
        """
        # Log to session logger if available
        if self.session_logger:
            self.session_logger.info(f"Agent run started with model: {self.config.model}")
            self.session_logger.info(f"User input: {user_input[:200]}...")
        else:
            logger.info(f"Agent run started with model: {self.config.model}")
            logger.info(f"User input: {user_input}")

        # Update state to thinking
        self.state_manager.update_state(AgentState.THINKING, "Processing user input")

        # Publish agent start event
        if self.session_id:
            await self.event_bus.publish(
                Event(
                    session_id=self.session_id,
                    event_type=EventType.AGENT_START,
                    metadata={"prompt": user_input[:100]},
                )
            )

        self.memory.add({"role": "user", "content": user_input})

        # Track current turn for logging
        self._current_turn = 0

        try:
            for turn in range(self.config.max_turns):
                self._current_turn = turn + 1  # Store for logging

                if self.session_logger:
                    self.session_logger.info(f"Turn {turn + 1}/{self.config.max_turns}")
                else:
                    logger.info(f"Turn {turn + 1}/{self.config.max_turns}")

                # State: Getting LLM completion
                self.state_manager.update_state(AgentState.THINKING, f"Turn {turn + 1}")

                response = await self._get_completion()
                self.memory.add(response)

                # Log assistant response
                if response.get("content"):
                    if self.session_logger:
                        self.session_logger.info(f"Agent response: {response['content'][:200]}...")
                    else:
                        logger.info(f"Agent response: {response['content'][:200]}...")

                tool_calls = response.get("tool_calls")
                if not tool_calls:
                    final_response = str(response.get("content", ""))
                    if self.session_logger:
                        self.session_logger.info("Agent completed successfully (no more tool calls)")
                    else:
                        logger.info("Agent completed successfully (no more tool calls)")

                    # Update state to completed
                    self.state_manager.update_state(AgentState.COMPLETED)

                    # Publish agent done event
                    if self.session_id:
                        await self.event_bus.publish(
                            Event(
                                session_id=self.session_id,
                                event_type=EventType.AGENT_DONE,
                                metadata={"turns": turn + 1, "status": "completed"},
                            )
                        )

                    return final_response

                # State: Executing tools
                self.state_manager.update_state(
                    AgentState.EXECUTING_TOOLS, f"{len(tool_calls)} tools"
                )

                # Execute tools using ToolExecutor
                results = await self.tool_executor.execute_tools(
                    tool_calls=tool_calls,
                    ui_renderer=self.ui_renderer,
                )

                for result in results:
                    self.memory.add(result)

            if self.session_logger:
                self.session_logger.warning("Max turns exceeded")
            else:
                logger.warning("Max turns exceeded")

            # Update state to failed
            self.state_manager.update_state(AgentState.FAILED, "Max turns exceeded")

            # Publish agent done event for max turns
            if self.session_id:
                await self.event_bus.publish(
                    Event(
                        session_id=self.session_id,
                        event_type=EventType.AGENT_DONE,
                        metadata={"turns": self.config.max_turns, "status": "max_turns"},
                    )
                )

            return "Max turns exceeded"
        except Exception as e:
            # Log error
            log_error(
                error=e,
                context="agent_run",
                session_id=self.session_id,
                agent_mode=self.config.mode.value,
            )

            # Publish agent done event on error
            if self.session_id:
                await self.event_bus.publish(
                    Event(
                        session_id=self.session_id,
                        event_type=EventType.AGENT_DONE,
                        metadata={"status": "error", "error": str(e)},
                    )
                )
            raise

    async def _get_completion(self) -> dict[str, Any]:
        """Get completion from LLM (streaming or non-streaming)."""
        tool_schemas = self.tools.schemas if self.tools.schemas else None
        messages = self.memory.get_messages()

        # Log memory state before API call if provider has logger
        if hasattr(self.provider, 'api_logger') and self.provider.api_logger:
            self.provider.api_logger.log_memory_state(
                messages=messages,
                token_count=self.memory.get_token_count(),
                context=f"before_completion_turn_{self._current_turn}",
            )

        if self.config.stream:
            return await stream_completion(
                provider=self.provider,
                messages=messages,
                model=self.config.model,
                tools=tool_schemas,
                timeout=self.config.timeout,
                console=self.console,
            )
        else:
            return await non_streaming_completion(
                provider=self.provider,
                messages=messages,
                model=self.config.model,
                tools=tool_schemas,
                timeout=self.config.timeout,
                console=self.console,
            )

    # Backward compatibility methods for internal access
    def _update_state(self, state: AgentState, action: str | None = None):
        """Update agent state (delegated to state manager)."""
        self.state_manager.update_state(state, action)
