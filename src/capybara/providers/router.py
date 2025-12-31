"""LiteLLM router for multi-provider support."""

from typing import Any, AsyncIterator, Optional

import litellm
from litellm import Router
from litellm.router import RetryPolicy, AllowedFailsPolicy

from capybara.core.config import ProviderConfig
from capybara.core.logging.api_logger import APILogger


class ProviderRouter:
    """LiteLLM-based provider router with fallback support."""

    def __init__(
        self,
        providers: list[ProviderConfig] | None = None,
        default_model: str = "gpt-4o",
        session_id: str | None = None,
    ) -> None:
        self.default_model = default_model
        self._router: Optional[Router] = None
        self._providers = providers or []
        self.api_logger: Optional[APILogger] = None

        # Initialize API logger if session_id provided
        if session_id:
            self.api_logger = APILogger(session_id)

        # Always init router to get retry/rate-limit handling (even with 1 provider)
        if providers:
            self._init_router(providers)

    def _init_router(self, providers: list[ProviderConfig]) -> None:
        """Initialize LiteLLM router with retry and rate-limit handling."""
        model_list = []
        for provider in providers:
            model_config: dict[str, Any] = {
                "model_name": provider.name,
                "litellm_params": {
                    "model": provider.model,
                    "rpm": provider.rpm,
                    "tpm": provider.tpm,
                },
            }
            if provider.api_key:
                model_config["litellm_params"]["api_key"] = provider.api_key
            if provider.api_base:
                api_base = provider.api_base
                # Auto-append /v1 for OpenAI-compatible, custom-base models (indicated by openai/ prefix)
                # to prevent 404s when user only provides the base URL.
                if provider.model.startswith("openai/") and not api_base.endswith("/v1"):
                     api_base = f"{api_base.rstrip('/')}/v1"
                
                model_config["litellm_params"]["api_base"] = api_base
            model_list.append(model_config)

        # Retry policy: 5 retries for rate limit errors with exponential backoff
        retry_policy = RetryPolicy(
            RateLimitErrorRetries=5,
            TimeoutErrorRetries=3,
            ServiceUnavailableErrorRetries=3,
        )

        # Allow more rate limit errors before cooling down deployment
        allowed_fails_policy = AllowedFailsPolicy(
            RateLimitErrorAllowedFails=100,
        )

        self._router = Router(
            model_list=model_list,
            routing_strategy="simple-shuffle",
            retry_after=7,  # Wait 7s before retry (based on API error message)
            num_retries=5,
            cooldown_time=10,  # Cooldown for 10s after failures
            retry_policy=retry_policy,
            allowed_fails_policy=allowed_fails_policy,
        )

    def _get_provider_config(self, model: str) -> Optional[ProviderConfig]:
        """Get provider config for a model."""
        for provider in self._providers:
            if provider.model == model:
                return provider
        return None

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = True,
        timeout: float = 120.0,
    ) -> AsyncIterator[Any]:
        """Get streaming completion from LLM.

        Args:
            messages: Conversation messages
            model: Model to use (defaults to default_model)
            tools: Tool schemas in OpenAI format
            stream: Whether to stream response
            timeout: Request timeout in seconds

        Yields:
            Streaming chunks from the model
        """
        model = model or self.default_model

        # Log request if logger available
        request_id = None
        if self.api_logger:
            request_id = self.api_logger.log_request(
                messages=messages,
                model=model,
                tools=tools,
                metadata={"stream": stream, "timeout": timeout},
            )

        # Get provider config for max_tokens
        provider_config = self._get_provider_config(model)
        max_tokens = provider_config.max_tokens if provider_config else 8000

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "timeout": timeout,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if stream:
            kwargs["stream_options"] = {"include_usage": True}

        try:
            if self._router:
                response = await self._router.acompletion(**kwargs)
            else:
                # Pass api_key and api_base directly when not using router
                if provider_config:
                    if provider_config.api_key:
                        kwargs["api_key"] = provider_config.api_key
                    if provider_config.api_base:
                        api_base = provider_config.api_base
                        if provider_config.model.startswith("openai/") and not api_base.endswith("/v1"):
                             api_base = f"{api_base.rstrip('/')}/v1"
                        kwargs["api_base"] = api_base
                response = await litellm.acompletion(**kwargs)

            # Collect chunks for logging
            collected_chunks = []
            if stream:
                async for chunk in response:
                    collected_chunks.append(chunk)
                    yield chunk
            else:
                collected_chunks.append(response)
                yield response

            # Log successful response
            if self.api_logger and request_id:
                self.api_logger.log_response(
                    request_id=request_id,
                    response={"chunks": len(collected_chunks), "streamed": stream},
                )

        except Exception as e:
            # Log error
            if self.api_logger and request_id:
                self.api_logger.log_response(request_id=request_id, response=None, error=e)
            raise

    async def complete_non_streaming(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        timeout: float = 120.0,
    ) -> Any:
        """Get non-streaming completion from LLM.

        Args:
            messages: Conversation messages
            model: Model to use
            tools: Tool schemas
            timeout: Request timeout

        Returns:
            Complete response from the model
        """
        model = model or self.default_model

        # Log request if logger available
        request_id = None
        if self.api_logger:
            request_id = self.api_logger.log_request(
                messages=messages,
                model=model,
                tools=tools,
                metadata={"stream": False, "timeout": timeout},
            )

        # Get provider config for max_tokens
        provider_config = self._get_provider_config(model)
        max_tokens = provider_config.max_tokens if provider_config else 8000

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "timeout": timeout,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            if self._router:
                response = await self._router.acompletion(**kwargs)
            else:
                # Pass api_key and api_base directly when not using router
                if provider_config:
                    if provider_config.api_key:
                        kwargs["api_key"] = provider_config.api_key
                    if provider_config.api_base:
                        api_base = provider_config.api_base
                        if provider_config.model.startswith("openai/") and not api_base.endswith("/v1"):
                             api_base = f"{api_base.rstrip('/')}/v1"
                        kwargs["api_base"] = api_base
                response = await litellm.acompletion(**kwargs)

            # Log successful response
            if self.api_logger and request_id:
                self.api_logger.log_response(request_id=request_id, response=response)

            return response

        except Exception as e:
            # Log error
            if self.api_logger and request_id:
                self.api_logger.log_response(request_id=request_id, response=None, error=e)
            raise
