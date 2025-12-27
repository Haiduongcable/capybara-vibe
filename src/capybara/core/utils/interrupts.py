"""Agent interruption handling."""


class AgentInterruptException(Exception):
    """Exception raised when user interrupts agent execution.

    Raised by Esc key binding in interactive mode.
    Agent loop should catch this and gracefully stop execution.
    """

    def __init__(self, message: str = "Agent execution interrupted by user") -> None:
        super().__init__(message)
        self.message = message
