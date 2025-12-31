"""Tests for web config transformers."""

from capybara.core.config import ProviderConfig
from capybara.web.transformers import (
    transform_provider_for_ui,
    transform_provider_for_yaml,
)


class TestTransformProviderForYAML:
    """Tests for UI -> YAML transformation."""

    def test_custom_openai_compatible_adds_prefix(self):
        """Custom provider with openai_compatible=True adds openai/ prefix."""
        result = transform_provider_for_yaml(
            {
                "type": "custom",
                "name": "My Custom",
                "model": "my-model",
                "api_key": "sk-test",
                "api_base": "https://api.example.com",
                "openai_compatible": True,
            }
        )
        assert result.model == "openai/my-model"
        assert result.name == "My Custom"
        assert result.api_key == "sk-test"
        assert result.api_base == "https://api.example.com"

    def test_custom_not_compatible_no_prefix(self):
        """Custom provider with openai_compatible=False keeps model as-is."""
        result = transform_provider_for_yaml(
            {
                "type": "custom",
                "name": "test",
                "model": "my-model",
                "openai_compatible": False,
            }
        )
        assert result.model == "my-model"

    def test_custom_already_has_prefix(self):
        """Custom provider with existing prefix doesn't double-prefix."""
        result = transform_provider_for_yaml(
            {
                "type": "custom",
                "name": "test",
                "model": "openai/my-model",
                "openai_compatible": True,
            }
        )
        assert result.model == "openai/my-model"

    def test_google_adds_gemini_prefix(self):
        """Google provider adds gemini/ prefix."""
        result = transform_provider_for_yaml(
            {
                "type": "google",
                "name": "Google AI",
                "model": "2.0-flash",
                "api_key": "AIza-test",
            }
        )
        assert result.model == "gemini/2.0-flash"

    def test_google_already_has_prefix(self):
        """Google provider with existing prefix doesn't double-prefix."""
        result = transform_provider_for_yaml(
            {
                "type": "google",
                "name": "test",
                "model": "gemini/2.0-flash",
            }
        )
        assert result.model == "gemini/2.0-flash"

    def test_anthropic_adds_prefix(self):
        """Anthropic provider adds anthropic/ prefix."""
        result = transform_provider_for_yaml(
            {
                "type": "anthropic",
                "name": "Claude",
                "model": "claude-3-5-sonnet",
                "api_key": "sk-ant-test",
            }
        )
        assert result.model == "anthropic/claude-3-5-sonnet"

    def test_openai_no_prefix(self):
        """OpenAI provider keeps model as-is (no prefix)."""
        result = transform_provider_for_yaml(
            {
                "type": "openai",
                "name": "OpenAI",
                "model": "gpt-4o",
                "api_key": "sk-test",
            }
        )
        assert result.model == "gpt-4o"

    def test_litellm_no_prefix(self):
        """LiteLLM provider keeps model as-is."""
        result = transform_provider_for_yaml(
            {
                "type": "litellm",
                "name": "LiteLLM Proxy",
                "model": "gpt-4",
                "api_base": "http://localhost:4000",
            }
        )
        assert result.model == "gpt-4"

    def test_default_values(self):
        """Missing optional fields get defaults."""
        result = transform_provider_for_yaml(
            {
                "type": "openai",
                "name": "test",
                "model": "gpt-4o",
            }
        )
        assert result.max_tokens == 8000
        assert result.rpm == 100
        assert result.tpm == 100000
        assert result.api_key is None
        assert result.api_base is None

    def test_empty_strings_become_none(self):
        """Empty strings for api_key/api_base become None."""
        result = transform_provider_for_yaml(
            {
                "type": "openai",
                "name": "test",
                "model": "gpt-4o",
                "api_key": "",
                "api_base": "",
            }
        )
        assert result.api_key is None
        assert result.api_base is None


class TestTransformProviderForUI:
    """Tests for YAML -> UI transformation."""

    def test_strips_openai_prefix(self):
        """Strips openai/ prefix and sets type=custom, openai_compatible=True."""
        provider = ProviderConfig(
            name="test", model="openai/my-model", api_base="https://api.example.com"
        )
        result = transform_provider_for_ui(provider)
        assert result["model"] == "my-model"
        assert result["type"] == "custom"
        assert result["openai_compatible"] is True

    def test_strips_gemini_prefix(self):
        """Strips gemini/ prefix and sets type=google."""
        provider = ProviderConfig(name="test", model="gemini/2.0-flash", api_key="AIza-test")
        result = transform_provider_for_ui(provider)
        assert result["model"] == "2.0-flash"
        assert result["type"] == "google"

    def test_strips_anthropic_prefix(self):
        """Strips anthropic/ prefix and sets type=anthropic."""
        provider = ProviderConfig(name="test", model="anthropic/claude-3-5-sonnet")
        result = transform_provider_for_ui(provider)
        assert result["model"] == "claude-3-5-sonnet"
        assert result["type"] == "anthropic"

    def test_detects_openai_from_model_name(self):
        """Detects OpenAI from gpt- prefix in model name."""
        provider = ProviderConfig(name="test", model="gpt-4o")
        result = transform_provider_for_ui(provider)
        assert result["type"] == "openai"
        assert result["model"] == "gpt-4o"

    def test_detects_openai_o1_models(self):
        """Detects OpenAI from o1 model names."""
        for model in ["o1", "o1-mini", "o1-preview"]:
            provider = ProviderConfig(name="test", model=model)
            result = transform_provider_for_ui(provider)
            assert result["type"] == "openai"

    def test_detects_anthropic_from_model_name(self):
        """Detects Anthropic from claude- prefix in model name."""
        provider = ProviderConfig(name="test", model="claude-3-5-sonnet-20241022")
        result = transform_provider_for_ui(provider)
        assert result["type"] == "anthropic"

    def test_detects_google_from_model_name(self):
        """Detects Google from gemini prefix in model name."""
        provider = ProviderConfig(name="test", model="gemini-2.0-flash")
        result = transform_provider_for_ui(provider)
        assert result["type"] == "google"

    def test_custom_with_api_base(self):
        """Unknown model with api_base becomes custom type."""
        provider = ProviderConfig(name="test", model="my-model", api_base="https://api.example.com")
        result = transform_provider_for_ui(provider)
        assert result["type"] == "custom"
        assert result["openai_compatible"] is True

    def test_litellm_detected_from_api_base(self):
        """Detects LiteLLM from api_base containing 'litellm'."""
        provider = ProviderConfig(
            name="test", model="my-custom-model", api_base="http://localhost:4000/litellm"
        )
        result = transform_provider_for_ui(provider)
        assert result["type"] == "litellm"

    def test_preserves_all_fields(self):
        """All fields are preserved in transformation."""
        provider = ProviderConfig(
            name="My Provider",
            model="gpt-4o",
            api_key="sk-test",
            api_base="https://api.openai.com",
            max_tokens=16000,
            rpm=5000,
            tpm=150000,
        )
        result = transform_provider_for_ui(provider)
        assert result["name"] == "My Provider"
        assert result["api_key"] == "sk-test"
        assert result["api_base"] == "https://api.openai.com"
        assert result["max_tokens"] == 16000
        assert result["rpm"] == 5000
        assert result["tpm"] == 150000

    def test_none_values_become_empty_strings(self):
        """None values for api_key/api_base become empty strings."""
        provider = ProviderConfig(name="test", model="gpt-4o", api_key=None, api_base=None)
        result = transform_provider_for_ui(provider)
        assert result["api_key"] == ""
        assert result["api_base"] == ""


class TestRoundTrip:
    """Tests for UI -> YAML -> UI round-trip transformations."""

    def test_openai_roundtrip(self):
        """OpenAI provider survives round-trip."""
        original = {
            "type": "openai",
            "name": "OpenAI",
            "model": "gpt-4o",
            "api_key": "sk-test",
            "api_base": "",
            "openai_compatible": False,
            "max_tokens": 8000,
            "rpm": 3500,
            "tpm": 90000,
        }
        yaml_config = transform_provider_for_yaml(original)
        result = transform_provider_for_ui(yaml_config)

        assert result["type"] == "openai"
        assert result["model"] == "gpt-4o"
        assert result["name"] == "OpenAI"

    def test_custom_openai_compatible_roundtrip(self):
        """Custom OpenAI-compatible provider survives round-trip."""
        original = {
            "type": "custom",
            "name": "My API",
            "model": "my-model",
            "api_key": "sk-test",
            "api_base": "https://api.example.com",
            "openai_compatible": True,
            "max_tokens": 8000,
            "rpm": 100,
            "tpm": 100000,
        }
        yaml_config = transform_provider_for_yaml(original)
        assert yaml_config.model == "openai/my-model"

        result = transform_provider_for_ui(yaml_config)
        assert result["type"] == "custom"
        assert result["model"] == "my-model"
        assert result["openai_compatible"] is True

    def test_google_roundtrip(self):
        """Google provider survives round-trip."""
        original = {
            "type": "google",
            "name": "Gemini",
            "model": "2.0-flash",
            "api_key": "AIza-test",
        }
        yaml_config = transform_provider_for_yaml(original)
        assert yaml_config.model == "gemini/2.0-flash"

        result = transform_provider_for_ui(yaml_config)
        assert result["type"] == "google"
        assert result["model"] == "2.0-flash"
