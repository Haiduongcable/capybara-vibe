"""API routes for configuration management."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from capybara.core.config import load_config, save_config
from capybara.web.transformers import (
    transform_provider_for_ui,
    transform_provider_for_yaml,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Shutdown callback - will be set by server
_shutdown_callback = None


def set_shutdown_callback(callback):
    """Set the shutdown callback function."""
    global _shutdown_callback
    _shutdown_callback = callback


class ProviderUI(BaseModel):
    """Provider config as displayed in UI."""

    type: str  # openai, google, anthropic, litellm, custom
    name: str
    model: str
    api_key: str = ""
    api_base: str = ""
    org_id: str = ""
    openai_compatible: bool = True
    max_tokens: int = 8000
    rpm: int = 100
    tpm: int = 100000


class ConfigResponse(BaseModel):
    """Config response for UI."""

    providers: list[ProviderUI]


class SaveConfigRequest(BaseModel):
    """Save config request."""

    providers: list[ProviderUI]


class TestConnectionRequest(BaseModel):
    """Test connection request."""

    provider: ProviderUI


class TestConnectionResponse(BaseModel):
    """Test connection response."""

    success: bool
    message: str


class FetchModelsRequest(BaseModel):
    """Request to fetch models from provider."""

    provider: ProviderUI


class FetchModelsResponse(BaseModel):
    """Fetch models response."""

    success: bool
    models: list[str] = []
    message: str = ""


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """Get current configuration for UI."""
    config = load_config()
    providers = [ProviderUI(**transform_provider_for_ui(p)) for p in config.providers]
    return ConfigResponse(providers=providers)


@router.post("/config")
async def save_config_endpoint(request: SaveConfigRequest):
    """Save configuration from UI."""
    # Validate at least one provider with required fields
    for i, p in enumerate(request.providers):
        if not p.name.strip():
            raise HTTPException(status_code=400, detail=f"Provider {i + 1}: Name is required")
        if not p.model.strip():
            raise HTTPException(status_code=400, detail=f"Provider {i + 1}: Model is required")

    config = load_config()

    # Transform UI providers to YAML format
    config.providers = [transform_provider_for_yaml(p.model_dump()) for p in request.providers]

    save_config(config)
    return {"status": "ok"}


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest):
    """Test provider connection."""
    # Validate required fields
    if not request.provider.model.strip():
        return TestConnectionResponse(success=False, message="Model is required")

    # API key not required for proxy type (may use x-api-key header differently)
    if request.provider.type != "proxy" and not request.provider.api_key.strip():
        return TestConnectionResponse(success=False, message="API key is required")

    try:
        provider = transform_provider_for_yaml(request.provider.model_dump())

        import litellm

        # Ensure we are using the model name exactly as stored in config (which now enforces openai/ prefix)
        # But if the UI passed it without prefix (because we stripped it for display), we re-add it here for the test
        model_to_test = provider.model

        # Logic mirroring ProviderRouter._resolve_litellm_model
        if provider.api_type == "google":
            if not model_to_test.startswith("gemini/"):
                model_to_test = f"gemini/{model_to_test}"
        elif request.provider.openai_compatible and not model_to_test.startswith("openai/"):
            model_to_test = f"openai/{model_to_test}"

        # LiteLLM needs the api_base to usually end in /v1 for "openai" provider logic if using standard client
        api_base_to_use = provider.api_base
        if (
            model_to_test.startswith("openai/")
            and api_base_to_use
            and not api_base_to_use.endswith("/v1")
        ):
            api_base_to_use = f"{api_base_to_use.rstrip('/')}/v1"

        response = await litellm.acompletion(
            model=model_to_test,
            messages=[{"role": "user", "content": "Hi"}],
            api_key=provider.api_key or "placeholder",
            api_base=api_base_to_use,
            max_tokens=5,
            timeout=10,
        )

        return TestConnectionResponse(success=True, message=f"Connected! Model: {response.model}")
    except Exception as e:
        error_msg = str(e)
        # Check for common error patterns
        if "auth" in error_msg.lower() or "api key" in error_msg.lower():
            return TestConnectionResponse(
                success=False, message="Authentication failed - check API key"
            )
        if "timeout" in error_msg.lower():
            return TestConnectionResponse(success=False, message="Connection timed out")
        logger.warning(f"Test connection failed for {request.provider.name}: {e}")
        return TestConnectionResponse(success=False, message=error_msg[:150])


@router.post("/fetch-models", response_model=FetchModelsResponse)
async def fetch_models(request: FetchModelsRequest):
    """Fetch available models from provider."""
    import httpx

    provider = request.provider
    if not provider.api_base:
        return FetchModelsResponse(success=False, message="API Base URL is required")

    api_base = provider.api_base.rstrip("/")
    url = f"{api_base}/v1/models"
    headers = {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Parse OpenAI format {"data": [{"id": "..."}, ...]}
            models = []
            if "data" in data and isinstance(data["data"], list):
                models = [m["id"] for m in data["data"] if "id" in m]

            return FetchModelsResponse(success=True, models=sorted(models))

    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        return FetchModelsResponse(success=False, message=str(e))


@router.post("/shutdown")
async def shutdown():
    """Shutdown server."""
    if _shutdown_callback:
        _shutdown_callback()
    return {"status": "shutting_down"}
