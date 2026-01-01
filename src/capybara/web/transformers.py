"""Transform between UI and YAML config formats."""

from capybara.core.config import ProviderConfig


def transform_provider_for_yaml(ui_provider: dict) -> ProviderConfig:
    """Transform UI provider to YAML ProviderConfig."""
    model = ui_provider["model"]
    provider_type = ui_provider.get("type", "custom")
    openai_compatible = ui_provider.get("openai_compatible", False)

    # Clean model name of prefixes for storage if we have explicit type
    # This keeps the config.yaml clean as requested by user
    if model.startswith("openai/"):
        model = model[7:]
    elif model.startswith("anthropic/"):
        model = model[10:]
    elif model.startswith("gemini/"):
        model = model[7:]

    # For custom/openai types, ensure we capture the intent via api_type
    # If it's a proxy or custom openai-compatible, we'll store it as 'openai'
    # but the router will need to handle the reconstruction.
    # Actually, let's allow 'api_type' to store the UI provider type directly.
    # map UI types to backend types if needed, or just 1:1

    return ProviderConfig(
        name=ui_provider["name"],
        api_type=provider_type,  # Store the UI type directly
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
    provider_type = provider.api_type  # Default "openai" from model definition
    openai_compatible = False

    # Logic to refine provider_type if it's the default "openai" but the model/config implies otherwise
    # (Backward compatibility for existing configs without explicit api_type)
    if provider_type == "openai" and not provider.api_base:
        if model.startswith("gemini/") or model.startswith("gemini-"):
            provider_type = "google"
        elif model.startswith("anthropic/") or model.startswith("claude-"):
            provider_type = "anthropic"
        elif "litellm" in (provider.name or "").lower():
            provider_type = "litellm"
        elif "proxy" in (provider.name or "").lower():
            provider_type = "proxy"

    # Cleaning model name for UI display happens automatically since we store it clean now.
    # But if reading old config with prefixes:
    if model.startswith("openai/"):
         model = model[7:]
    elif model.startswith("anthropic/"):
         model = model[10:]
    elif model.startswith("gemini/"):
         model = model[7:]

    # determine openai_compatible flag for UI
    if provider_type in ["proxy", "custom", "litellm"]:
        openai_compatible = True
    elif provider_type == "openai":
         # Standard OpenAI is technically compatible but UI toggle usually implies "Custom Endpoint"
         openai_compatible = False

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
