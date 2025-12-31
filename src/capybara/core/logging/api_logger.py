"""API request/response logging for debugging."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class APILogger:
    """Logs LiteLLM API requests and responses to JSON files."""

    def __init__(self, session_id: str, log_dir: Path | None = None) -> None:
        """Initialize API logger.

        Args:
            session_id: Session ID for organizing logs
            log_dir: Directory to store logs (defaults to ~/.capybara/logs/api)
        """
        self.session_id = session_id
        self.log_dir = log_dir or (Path.home() / ".capybara" / "logs" / "api")
        self.session_log_dir = self.log_dir / session_id
        self.session_log_dir.mkdir(parents=True, exist_ok=True)
        self.request_count = 0

    def log_request(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Log an API request.

        Args:
            messages: Messages being sent to LLM
            model: Model name
            tools: Tool schemas
            metadata: Additional metadata

        Returns:
            Request ID (sequential counter)
        """
        self.request_count += 1
        request_id = self.request_count

        log_data = {
            "request_id": request_id,
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "message_count": len(messages),
            "messages": messages,
            "tools": tools,
            "metadata": metadata or {},
        }

        log_file = self.session_log_dir / f"request_{request_id:03d}.json"
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)

        return request_id

    def log_response(
        self,
        request_id: int,
        response: Any,
        error: Exception | None = None,
    ) -> None:
        """Log an API response or error.

        Args:
            request_id: Request ID from log_request
            response: Response from LLM
            error: Exception if request failed
        """
        log_data = {
            "request_id": request_id,
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if error:
            log_data["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        else:
            log_data["response"] = response

        log_file = self.session_log_dir / f"response_{request_id:03d}.json"
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)

    def log_memory_state(
        self,
        messages: list[dict[str, Any]],
        token_count: int,
        context: str = "",
    ) -> None:
        """Log current memory state for debugging.

        Args:
            messages: Current messages in memory
            token_count: Current token count
            context: Context about when this was logged
        """
        log_data = {
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context,
            "token_count": token_count,
            "message_count": len(messages),
            "messages": messages,
        }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_file = self.session_log_dir / f"memory_state_{timestamp}.json"
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)
