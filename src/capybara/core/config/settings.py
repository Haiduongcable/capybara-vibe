from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from capybara.tools.base import ToolSecurityConfig, ToolPermission

class ToolsConfig(BaseModel):
    """Tools configuration."""

    bash_enabled: bool = True
    bash_timeout: int = 120
    filesystem_enabled: bool = True
    allowed_paths: list[str] = Field(default_factory=lambda: ["."])
    
    # Permission settings
    security: dict[str, ToolSecurityConfig] = Field(default_factory=dict)


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    name: str = "default"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    rpm: int = 3500  # Requests per minute
    tpm: int = 90000  # Tokens per minute
    max_tokens: int = 8000  # Maximum tokens per response


class MemoryConfig(BaseModel):
    """Memory management configuration."""

    max_messages: Optional[int] = None
    max_tokens: int = 100_000
    persist: bool = True




class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class MCPConfig(BaseModel):
    """MCP integration configuration."""

    enabled: bool = False
    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class FeaturesConfig(BaseModel):
    """Feature flags for experimental/new features."""

    auto_complexity_detection: bool = False
    auto_todo_creation: bool = False
    auto_delegation: bool = False
    unified_ui: bool = False
    enhanced_summaries: bool = False
    structured_logging: bool = False

    # Complexity threshold (0.0-1.0)
    complexity_threshold: float = 0.6


class CapybaraConfig(BaseSettings):
    """Main configuration for CapybaraVibeCoding."""

    model_config = SettingsConfigDict(
        env_prefix="CAPYBARA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    providers: list[ProviderConfig] = Field(default_factory=lambda: [ProviderConfig()])
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)

    @property
    def default_model(self) -> str:
        """Get the default model from the first provider."""
        if self.providers:
            return self.providers[0].model
        return "gpt-4o"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return Path.home() / ".capybara" / "config.yaml"


def load_config() -> CapybaraConfig:
    """Load configuration from file and environment."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
            return CapybaraConfig(**data)
    return CapybaraConfig()


def save_config(config: CapybaraConfig) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(exclude_none=True)
    with open(config_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def init_config() -> Path:
    """Initialize configuration directory and file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        default_config = CapybaraConfig()
        save_config(default_config)

    # Create history file directory
    history_path = config_path.parent / "history"
    history_path.touch(exist_ok=True)

    return config_path
