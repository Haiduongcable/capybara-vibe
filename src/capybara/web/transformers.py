"""Transform between UI and YAML config formats."""

from capybara.core.config import ProviderConfig


def transform_provider_for_yaml(ui_provider: dict) -> ProviderConfig:
    """Transform UI provider to YAML ProviderConfig."""
    model = ui_provider["model"]
    provider_type = ui_provider.get("type", "custom")

    # Apply prefix based on type
    if provider_type == "proxy":
        # Force OpenAI prefix for LiteLLM to recognize protocol
        if model.startswith("anthropic/"):
             model = model[10:]
        elif model.startswith("openai/"):
             model = model[7:]
        
        model = f"openai/{model}"
    elif provider_type == "custom" and ui_provider.get("openai_compatible", True):
        # LiteLLM treats no-prefix as OpenAI compatible usually, but 'openai/' is safer for strictness
        if not model.startswith("openai/"):
            model = f"openai/{model}"
    elif provider_type == "google":
        if not model.startswith("gemini/"):
            model = f"gemini/{model}"
    elif provider_type == "anthropic":
        if not model.startswith("anthropic/"):
            model = f"anthropic/{model}"
    # OpenAI and LiteLLM don't need prefix

    return ProviderConfig(
        name=ui_provider["name"],
        model=model,
        api_key=ui_provider.get("api_key") or None,
        api_base=ui_provider.get("api_base") or None,
        max_tokens=ui_provider.get("max_tokens", 8000),
        rpm=ui_provider.get("rpm", 100),
        tpm=ui_provider.get("tpm", 100000),
    )


def transform_provider_for_ui(provider: ProviderConfig) -> dict:
    """Transform YAML ProviderConfig to UI format."""
    model = provider.model
    provider_type = "custom"
    openai_compatible = False

    # Detect type from model prefix and api_base
    if model.startswith("openai/"):
        provider_type = "custom"
        openai_compatible = True
        model = model[7:]
    elif model.startswith("gemini/"):
        provider_type = "google"
        model = model[7:]
    elif model.startswith("anthropic/") and provider.api_base:
        # Anthropic with custom api_base = proxy
        provider_type = "proxy"
        model = model[10:]
        openai_compatible = True
    elif provider.api_base and ("proxypal" in (provider.name or "").lower() or "proxy" in (provider.name or "").lower()):
        provider_type = "proxy"
        openai_compatible = True
        # Remove prefixes if somehow present
        if model.startswith("openai/"): model = model[7:]
        elif model.startswith("anthropic/"): model = model[10:]
    elif model.startswith("anthropic/"):
        provider_type = "anthropic"
        model = model[10:]
    elif model.startswith("gpt-") or model in ["o1", "o1-mini", "o1-preview"]:
        provider_type = "openai"
    elif model.startswith("claude-") and provider.api_base:
        provider_type = "proxy"
        openai_compatible = True
    elif model.startswith("claude-"):
        provider_type = "anthropic"
    elif model.startswith("gemini"):
        provider_type = "google"
    elif provider.api_base:
        provider_type = "litellm" if "litellm" in (provider.api_base or "").lower() else "custom"
        openai_compatible = True  # Assume custom with api_base is openai-compatible

    return {
        "type": provider_type,
        "name": provider.name,
        "model": model,
        "api_key": provider.api_key or "",
        "api_base": provider.api_base or "",
        "org_id": "",
        "openai_compatible": openai_compatible,
        "max_tokens": provider.max_tokens,
        "rpm": provider.rpm,
        "tpm": provider.tpm,
    }
