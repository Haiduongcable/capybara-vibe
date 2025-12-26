"""LiteLLM router for multi-provider support."""

from typing import Any, AsyncIterator, Optional

import litellm
from litellm import Router

from capybara.core.config import ProviderConfig


class ProviderRouter:
    """LiteLLM-based provider router with fallback support."""

    def __init__(
        self,
        providers: list[ProviderConfig] | None = None,
        default_model: str = "gpt-4o",
    ) -> None:
        self.default_model = default_model
        self._router: Optional[Router] = None
        self._providers = providers or []

        if providers and len(providers) > 1:
            self._init_router(providers)

    def _init_router(self, providers: list[ProviderConfig]) -> None:
        """Initialize LiteLLM router with multiple providers."""
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
                model_config["litellm_params"]["api_base"] = provider.api_base
            model_list.append(model_config)

        self._router = Router(
            model_list=model_list,
            routing_strategy="simple-shuffle",
            retry_after=5,
            num_retries=5,
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

        if stream:
            kwargs["stream_options"] = {"include_usage": True}

        if self._router:
            response = await self._router.acompletion(**kwargs)
        else:
            # Pass api_key and api_base directly when not using router
            if provider_config:
                if provider_config.api_key:
                    kwargs["api_key"] = provider_config.api_key
                if provider_config.api_base:
                    kwargs["api_base"] = provider_config.api_base
            response = await litellm.acompletion(**kwargs)

        if stream:
            async for chunk in response:
                yield chunk
        else:
            yield response

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

        if self._router:
            return await self._router.acompletion(**kwargs)
        else:
            # Pass api_key and api_base directly when not using router
            if provider_config:
                if provider_config.api_key:
                    kwargs["api_key"] = provider_config.api_key
                if provider_config.api_base:
                    kwargs["api_base"] = provider_config.api_base
            return await litellm.acompletion(**kwargs)
