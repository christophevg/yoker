"""Configuration system for Yoker.

Provides TOML configuration loading, validation, and schema definitions.
Uses Clevis for configuration management with environment variable support.

Example:
    from yoker.config import Config

    # Load configuration (auto-discover from ./yoker.toml or ~/.yoker.toml)
    config = Config.discover()

    # Load with explicit config file
    config = Config.discover("./myconfig.toml")

    # Access configuration values
    print(config.backend.ollama.model)
    print(config.tools.read.enabled)

Environment Variables:
    YOKER_* environment variables override config file values.
    Example: YOKER_BACKEND_OLLAMA_MODEL=llama3 overrides model setting.

Configuration Files:
    - User config: ~/.yoker.toml (lower priority)
    - Project config: ./yoker.toml (higher priority)

Environment Variable Interpolation:
    Config files support ${VAR} syntax when envtoml is installed:
        [backend.ollama]
        base_url = "${OLLAMA_HOST:http://localhost:11434}"
"""

import sys
from pathlib import Path
from typing import Any

from dacite import from_dict

from yoker.config.schema import (
  AgentsConfig,
  AgentToolConfig,
  BackendConfig,
  Config,
  ContentDisplayConfig,
  ContextConfig,
  GitToolConfig,
  HandlerConfig,
  HarnessConfig,
  ListToolConfig,
  LoggingConfig,
  MkdirToolConfig,
  OllamaConfig,
  OllamaParameters,
  PermissionsConfig,
  ReadToolConfig,
  SearchToolConfig,
  SkillsConfig,
  ToolConfig,
  ToolsConfig,
  UpdateToolConfig,
  WebFetchToolConfig,
  WebSearchToolConfig,
  WriteToolConfig,
)
from yoker.exceptions import ConfigurationError, FileNotFoundError, ValidationError

# Use tomli for Python < 3.11, tomllib for 3.11+
if sys.version_info >= (3, 11):
  import tomllib
else:
  import tomli as tomllib  # type: ignore[import-not-found]


def _convert_lists_to_tuples(data: dict[str, Any]) -> dict[str, Any]:
  """Recursively convert lists to tuples in a dict for frozen dataclass compatibility.

  TOML arrays are parsed as lists, but frozen dataclasses need tuples.

  Args:
    data: Dictionary loaded from TOML.

  Returns:
    Dictionary with lists converted to tuples.
  """
  result: dict[str, Any] = {}
  for key, value in data.items():
    if isinstance(value, dict):
      result[key] = _convert_lists_to_tuples(value)
    elif isinstance(value, list):
      result[key] = tuple(value)
    else:
      result[key] = value
  return result


def load_config(path: Path | str) -> Config:
  """Load configuration from a specific TOML file.

  Args:
    path: Path to the configuration file.

  Returns:
    Configuration object with all settings.

  Raises:
    FileNotFoundError: If the configuration file doesn't exist.
    ConfigurationError: If the configuration is invalid.

  Example:
      config = load_config("./yoker.toml")
  """
  config_path = Path(path)

  if not config_path.exists():
    raise FileNotFoundError(str(config_path), "configuration")

  try:
    with open(config_path, "rb") as f:
      data = tomllib.load(f)

    # Convert lists to tuples for frozen dataclass compatibility
    data = _convert_lists_to_tuples(data)

    # Convert dict to Config using dacite
    return from_dict(data_class=Config, data=data)
  except ValidationError:
    # Re-raise validation errors as-is (from __post_init__)
    raise
  except Exception as e:
    raise ConfigurationError(
      setting=str(config_path),
      message=f"Failed to parse TOML: {e}",
    ) from None


def load_config_with_defaults(path: Path | str | None = None) -> Config:
  """Load configuration with defaults.

  If no path is provided or the file doesn't exist, returns default config.

  Args:
    path: Optional path to configuration file.

  Returns:
    Configuration object.

  Example:
      config = load_config_with_defaults()  # Returns default config
      config = load_config_with_defaults("./yoker.toml")  # Load from file
  """
  if path is None:
    return Config()

  try:
    return load_config(path)
  except FileNotFoundError:
    return Config()


def discover_config() -> tuple[Config, Path | None]:
  """Auto-discover configuration file.

  Search order:
      1. ./yoker.toml (current directory)
      2. ~/.yoker.toml (user home directory)
      3. Config() defaults

  Returns:
      Tuple of (Config, Path | None). Path is the discovered config file,
      or None if using defaults.

  Raises:
      ConfigurationError: If config file exists but is invalid.

  Example:
      config, path = discover_config()
      if path:
          print(f"Loaded config from {path}")
  """
  # Try current directory
  cwd_config = Path.cwd() / "yoker.toml"
  if cwd_config.exists():
    return load_config(cwd_config), cwd_config

  # Try user home directory
  home_config = Path.home() / ".yoker.toml"
  if home_config.exists():
    return load_config(home_config), home_config

  # Fallback to defaults
  return Config(), None


def validate_config(config: Config) -> list[str]:
  """Validate a configuration object.

  Performs all validation checks and returns a list of warnings.

  Note: With Clevis integration, validation now happens automatically
  in dataclass __post_init__ methods. This function remains for
  backward compatibility and always returns an empty warnings list.

  Args:
    config: Configuration to validate.

  Returns:
    List of warning messages (always empty with Clevis).

  Raises:
    ValidationError: If any critical validation fails.
  """
  # Validation now happens in __post_init__ methods on dataclasses
  # This function remains for backward compatibility
  return []


__all__ = [
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
  "MkdirToolConfig",
  "WebSearchToolConfig",
  "WebFetchToolConfig",
  "ContentDisplayConfig",
  "ToolsConfig",
  "AgentsConfig",
  "LoggingConfig",
  "SkillsConfig",
  # Loader functions (backward compatibility)
  "load_config",
  "load_config_with_defaults",
  "discover_config",
  # Validator functions (backward compatibility)
  "validate_config",
  # Exceptions
  "ConfigurationError",
  "ValidationError",
]
