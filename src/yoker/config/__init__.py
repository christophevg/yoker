"""Configuration system for Yoker.

Provides TOML configuration loading, validation, and schema definitions.

Example:
    from yoker.config import load_config, Config

    # Load configuration from file
    config = load_config("yoker.toml")

    # Load with defaults (returns default config if file missing)
    config = load_config_with_defaults("yoker.toml")

    # Access configuration values
    print(config.backend.ollama.model)
    print(config.tools.read.enabled)
"""

from yoker.config.loader import load_config, load_config_with_defaults
from yoker.config.schema import (
  AgentsConfig,
  AgentToolConfig,
  BackendConfig,
  Config,
  ContextConfig,
  GitToolConfig,
  HandlerConfig,
  HarnessConfig,
  ListToolConfig,
  LoggingConfig,
  OllamaConfig,
  OllamaParameters,
  PermissionsConfig,
  ReadToolConfig,
  SearchToolConfig,
  ToolConfig,
  ToolsConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.config.validator import validate_config
from yoker.exceptions import ConfigurationError, ValidationError

__all__ = [
  # Loader functions
  "load_config",
  "load_config_with_defaults",
  # Validator functions
  "validate_config",
  # Configuration classes
  "Config",
  "HarnessConfig",
  "BackendConfig",
  "OllamaConfig",
  "OllamaParameters",
  "ContextConfig",
  "HandlerConfig",
  "PermissionsConfig",
  "ToolConfig",
  "ListToolConfig",
  "ReadToolConfig",
  "WriteToolConfig",
  "UpdateToolConfig",
  "SearchToolConfig",
  "AgentToolConfig",
  "GitToolConfig",
  "ToolsConfig",
  "AgentsConfig",
  "LoggingConfig",
  # Exceptions
  "ConfigurationError",
  "ValidationError",
]
