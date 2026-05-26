"""TOML configuration loader for Yoker.

Loads configuration from yoker.toml files and parses into Config objects.
"""

import os
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, Union, get_args, get_origin

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
  ToolsConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.exceptions import ConfigurationError, FileNotFoundError
from yoker.logging import get_logger

# Use tomli for Python < 3.11, tomllib for 3.11+
if sys.version_info >= (3, 11):
  import tomllib
else:
  import tomli as tomllib  # type: ignore[import-not-found]

log = get_logger(__name__)


def _get_nested(data: dict[str, object], *keys: str) -> dict[str, object] | None:
  """Get nested dictionary value.

  Args:
    data: Dictionary to search.
    *keys: Keys to traverse.

  Returns:
    Nested value or None if not found.
  """
  result: dict[str, object] | None = data
  for key in keys:
    if result is None or not isinstance(result, dict):
      return None
    result = result.get(key)  # type: ignore
  return result


def _parse_harness(data: dict[str, object]) -> HarnessConfig:
  """Parse harness configuration section."""
  harness = _get_nested(data, "harness")
  if harness is None:
    return HarnessConfig()

  return HarnessConfig(
    name=harness.get("name", "yoker"),  # type: ignore
    version=harness.get("version", "1.0"),  # type: ignore
    log_level=harness.get("log_level", "INFO"),  # type: ignore
  )


def _parse_ollama_parameters(
  data: dict[str, object] | None,
) -> OllamaParameters:
  """Parse Ollama parameters section."""
  if data is None:
    return OllamaParameters()

  return OllamaParameters(
    temperature=data.get("temperature", 0.7),  # type: ignore
    top_p=data.get("top_p", 0.9),  # type: ignore
    top_k=data.get("top_k", 40),  # type: ignore
    num_ctx=data.get("num_ctx", 4096),  # type: ignore
  )


def _parse_ollama_config(data: dict[str, object] | None) -> OllamaConfig:
  """Parse Ollama backend configuration."""
  if data is None:
    return OllamaConfig()

  return OllamaConfig(
    base_url=data.get("base_url", "http://localhost:11434"),  # type: ignore
    model=data.get("model", "llama3.2:latest"),  # type: ignore
    timeout_seconds=data.get("timeout_seconds", 60),  # type: ignore
    parameters=_parse_ollama_parameters(
      data.get("parameters")  # type: ignore
    ),
  )


def _parse_backend(data: dict[str, object]) -> BackendConfig:
  """Parse backend configuration section."""
  backend = _get_nested(data, "backend")
  if backend is None:
    return BackendConfig()

  provider_val = backend.get("provider", "ollama")
  provider = str(provider_val) if provider_val is not None else "ollama"
  ollama_data = _get_nested(data, "backend", "ollama")

  return BackendConfig(
    provider=provider,
    ollama=_parse_ollama_config(ollama_data),
  )


def _parse_context(data: dict[str, object]) -> ContextConfig:
  """Parse context configuration section."""
  context = _get_nested(data, "context")
  if context is None:
    return ContextConfig()

  return ContextConfig(
    manager=context.get("manager", "basic_persistence"),  # type: ignore
    storage_path=context.get("storage_path", "./context"),  # type: ignore
    session_id=context.get("session_id", "auto"),  # type: ignore
    persist_after_turn=context.get("persist_after_turn", True),  # type: ignore
  )


def _parse_handlers(data: dict[str, object] | None) -> dict[str, HandlerConfig]:
  """Parse permission handlers section."""
  if data is None:
    return {}

  handlers: dict[str, HandlerConfig] = {}
  for name, handler_data in data.items():
    if isinstance(handler_data, dict):
      mode_val = handler_data.get("mode", "block")
      msg_val = handler_data.get("message")
      handlers[name] = HandlerConfig(
        mode=str(mode_val) if mode_val is not None else "block",
        message=str(msg_val) if msg_val is not None else None,
      )
  return handlers


def _parse_permissions(data: dict[str, object]) -> PermissionsConfig:
  """Parse permissions configuration section."""
  perms = _get_nested(data, "permissions")
  if perms is None:
    return PermissionsConfig()

  paths_raw = perms.get("filesystem_paths", [])
  if isinstance(paths_raw, list):
    paths = tuple(str(p) for p in paths_raw)
  else:
    paths = ()

  handlers_data = _get_nested(data, "permissions", "handlers")

  network_val = perms.get("network_access", "none")
  network_access = str(network_val) if network_val is not None else "none"

  max_file = perms.get("max_file_size_kb", 500)
  max_file_size_kb = int(max_file) if isinstance(max_file, int | float) else 500

  max_rec = perms.get("max_recursion_depth", 3)
  max_recursion_depth = int(max_rec) if isinstance(max_rec, int | float) else 3

  return PermissionsConfig(
    filesystem_paths=paths,
    network_access=network_access,
    max_file_size_kb=max_file_size_kb,
    max_recursion_depth=max_recursion_depth,
    handlers=_parse_handlers(handlers_data),
  )


def _parse_list_tool(data: dict[str, object] | None) -> ListToolConfig:
  """Parse list tool configuration."""
  if data is None:
    return ListToolConfig()

  return ListToolConfig(
    enabled=data.get("enabled", True),  # type: ignore
    max_depth=data.get("max_depth", 5),  # type: ignore
    max_entries=data.get("max_entries", 2000),  # type: ignore
  )


def _parse_read_tool(data: dict[str, object] | None) -> ReadToolConfig:
  """Parse read tool configuration."""
  if data is None:
    return ReadToolConfig()

  exts = data.get("allowed_extensions")
  if exts is None:
    exts = ReadToolConfig.allowed_extensions
  elif isinstance(exts, list):
    exts = tuple(exts)

  patterns = data.get("blocked_patterns")
  if patterns is None:
    patterns = ReadToolConfig.blocked_patterns
  elif isinstance(patterns, list):
    patterns = tuple(patterns)

  return ReadToolConfig(
    enabled=data.get("enabled", True),  # type: ignore
    allowed_extensions=exts,  # type: ignore
    blocked_patterns=patterns,  # type: ignore
  )


def _parse_write_tool(data: dict[str, object] | None) -> WriteToolConfig:
  """Parse write tool configuration."""
  if data is None:
    return WriteToolConfig()

  exts = data.get("blocked_extensions")
  if exts is None:
    exts = WriteToolConfig.blocked_extensions
  elif isinstance(exts, list):
    exts = tuple(exts)

  return WriteToolConfig(
    enabled=data.get("enabled", True),  # type: ignore
    allow_overwrite=data.get("allow_overwrite", False),  # type: ignore
    max_size_kb=data.get("max_size_kb", 1000),  # type: ignore
    blocked_extensions=exts,  # type: ignore
  )


def _parse_update_tool(data: dict[str, object] | None) -> UpdateToolConfig:
  """Parse update tool configuration."""
  if data is None:
    return UpdateToolConfig()

  return UpdateToolConfig(
    enabled=data.get("enabled", True),  # type: ignore
    require_exact_match=data.get("require_exact_match", True),  # type: ignore
    max_diff_size_kb=data.get("max_diff_size_kb", 100),  # type: ignore
  )


def _parse_search_tool(data: dict[str, object] | None) -> SearchToolConfig:
  """Parse search tool configuration."""
  if data is None:
    return SearchToolConfig()

  return SearchToolConfig(
    enabled=data.get("enabled", True),  # type: ignore
    max_regex_complexity=data.get("max_regex_complexity", "medium"),  # type: ignore
    max_results=data.get("max_results", 500),  # type: ignore
    timeout_ms=data.get("timeout_ms", 10000),  # type: ignore
  )


def _parse_agent_tool(data: dict[str, object] | None) -> AgentToolConfig:
  """Parse agent tool configuration."""
  if data is None:
    return AgentToolConfig()

  return AgentToolConfig(
    enabled=data.get("enabled", True),  # type: ignore
    max_recursion_depth=data.get("max_recursion_depth", 3),  # type: ignore
    timeout_seconds=data.get("timeout_seconds", 300),  # type: ignore
  )


def _parse_git_tool(data: dict[str, object] | None) -> GitToolConfig:
  """Parse git tool configuration."""
  if data is None:
    return GitToolConfig()

  cmds = data.get("allowed_commands")
  if cmds is None:
    cmds = GitToolConfig.allowed_commands
  elif isinstance(cmds, list):
    cmds = tuple(cmds)

  perms = data.get("requires_permission")
  if perms is None:
    perms = GitToolConfig.requires_permission
  elif isinstance(perms, list):
    perms = tuple(perms)

  return GitToolConfig(
    enabled=data.get("enabled", True),  # type: ignore
    allowed_commands=cmds,  # type: ignore
    requires_permission=perms,  # type: ignore
  )


def _parse_tools(data: dict[str, object]) -> ToolsConfig:
  """Parse tools configuration section."""
  tools = _get_nested(data, "tools")
  if tools is None:
    return ToolsConfig()

  return ToolsConfig(
    list=_parse_list_tool(_get_nested(data, "tools", "list")),
    read=_parse_read_tool(_get_nested(data, "tools", "read")),
    write=_parse_write_tool(_get_nested(data, "tools", "write")),
    update=_parse_update_tool(_get_nested(data, "tools", "update")),
    search=_parse_search_tool(_get_nested(data, "tools", "search")),
    agent=_parse_agent_tool(_get_nested(data, "tools", "agent")),
    git=_parse_git_tool(_get_nested(data, "tools", "git")),
  )


def _parse_agents(data: dict[str, object]) -> AgentsConfig:
  """Parse agents configuration section."""
  agents = _get_nested(data, "agents")
  if agents is None:
    return AgentsConfig()

  return AgentsConfig(
    directory=agents.get("directory", "./agents"),  # type: ignore
    definition=agents.get("definition", ""),  # type: ignore
    default_type=agents.get("default_type", "main"),  # type: ignore
  )


def _parse_logging(data: dict[str, object]) -> LoggingConfig:
  """Parse logging configuration section."""
  logging = _get_nested(data, "logging")
  if logging is None:
    return LoggingConfig()

  return LoggingConfig(
    format=logging.get("format", "json"),  # type: ignore
    include_tool_calls=logging.get("include_tool_calls", True),  # type: ignore
    include_permission_checks=logging.get("include_permission_checks", True),  # type: ignore
  )


def load_config(path: Path | str) -> Config:
  """Load configuration from a TOML file.

  Args:
    path: Path to the configuration file.

  Returns:
    Configuration object with all settings.

  Raises:
    FileNotFoundError: If the configuration file doesn't exist.
    ConfigurationError: If the configuration is invalid.
  """
  config_path = Path(path)

  if not config_path.exists():
    raise FileNotFoundError(str(config_path), "configuration")

  try:
    with open(config_path, "rb") as f:
      data = tomllib.load(f)
  except Exception as e:
    raise ConfigurationError(
      setting=str(config_path),
      message=f"Failed to parse TOML: {e}",
    ) from None

  return Config(
    harness=_parse_harness(data),
    backend=_parse_backend(data),
    context=_parse_context(data),
    permissions=_parse_permissions(data),
    tools=_parse_tools(data),
    agents=_parse_agents(data),
    logging=_parse_logging(data),
  )


def load_config_with_defaults(path: Path | str | None = None) -> Config:
  """Load configuration with defaults.

  If no path is provided or the file doesn't exist, returns default config.

  Args:
    path: Optional path to configuration file.

  Returns:
    Configuration object.
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
  """
  # Try current directory
  cwd_config = Path.cwd() / "yoker.toml"
  if cwd_config.exists():
    log.info("config_discovered", path=str(cwd_config), location="cwd")
    return load_config(cwd_config), cwd_config

  # Try user home directory
  home_config = Path.home() / ".yoker.toml"
  if home_config.exists():
    log.info("config_discovered", path=str(home_config), location="home")
    return load_config(home_config), home_config

  # Fallback to defaults
  log.info("config_defaults")
  return Config(), None


# Environment variable support


def _get_env_var_name(config_path: tuple[str, ...], prefix: str = "") -> str:
  """Convert config path to environment variable name.

  Args:
    config_path: Tuple of path components (e.g., ('backend', 'ollama', 'model'))
    prefix: Optional prefix (e.g., 'MYAPP')

  Returns:
    Environment variable name (e.g., 'MYAPP_YOKER_BACKEND_OLLAMA_MODEL' or
    'YOKER_BACKEND_OLLAMA_MODEL')

  Example:
    _get_env_var_name(('backend', 'ollama', 'model')) -> 'YOKER_BACKEND_OLLAMA_MODEL'
    _get_env_var_name(('backend', 'ollama', 'model'), 'MYAPP') -> 'MYAPP_YOKER_BACKEND_OLLAMA_MODEL'
  """
  parts = [prefix, "YOKER"] if prefix else ["YOKER"]
  parts.extend(part.upper() for part in config_path)
  return "_".join(parts)


# Mapping of config paths to their types for coercion
# Format: (section, subsection, field) -> type
_CONFIG_FIELD_TYPES: dict[tuple[str, ...], type] = {}


def _build_config_field_types() -> dict[tuple[str, ...], type]:
  """Build mapping of config paths to their types.

  This is built once at module load time for efficient env var lookups.
  """
  types_map: dict[tuple[str, ...], type] = {}

  # Helper to extract field types from a dataclass
  def extract_types(
    prefix: tuple[str, ...],
    dataclass_type: type,
    types_map: dict[tuple[str, ...], type],
  ) -> None:
    for f in fields(dataclass_type):
      field_path = prefix + (f.name,)
      field_type = f.type

      # Handle string annotations (forward references)
      if isinstance(field_type, str):
        # Skip string annotations, we can't resolve them
        continue

      # Handle optional types (str | None)
      origin = get_origin(field_type)
      if origin is Union:
        # Extract non-None type from Union
        for arg in get_args(field_type):
          if arg is not type(None):
            field_type = arg
            break
        # Re-get origin after unwrapping Union
        origin = get_origin(field_type)

      # Check if this is a nested dataclass
      if hasattr(field_type, "__dataclass_fields__"):
        # Recurse into nested dataclass
        extract_types(field_path, field_type, types_map)
      else:
        # Store the type for this field
        # Handle both simple types (str, int, bool) and generic types (tuple[str, ...])
        if isinstance(field_type, type) or origin is not None:
          types_map[field_path] = field_type
        # Skip complex type annotations that aren't simple types

  # Build from root Config
  extract_types((), Config, types_map)

  return types_map


# Initialize field types at module load
_CONFIG_FIELD_TYPES = _build_config_field_types()

# Build reverse mapping from env var name to config path (for default prefix)
# Note: For custom prefixes, we need to strip the prefix when looking up
_DEFAULT_ENV_VAR_TO_PATH: dict[str, tuple[str, ...]] = {
  _get_env_var_name(path): path for path in _CONFIG_FIELD_TYPES
}


def _coerce_value(value: str, target_type: type) -> Any:
  """Coerce string value to target type.

  Args:
    value: String value from environment variable
    target_type: Target Python type

  Returns:
    Coerced value

  Raises:
    ValueError: If value cannot be coerced to target type
  """
  if target_type is str:
    return value
  elif target_type is int:
    return int(value)
  elif target_type is float:
    return float(value)
  elif target_type is bool:
    lower = value.lower()
    if lower in ("true", "1", "yes", "on"):
      return True
    elif lower in ("false", "0", "no", "off"):
      return False
    else:
      raise ValueError(f"Cannot convert '{value}' to bool")
  else:
    # Check if this is a tuple type (tuple[str, ...]) or raw tuple class
    origin = get_origin(target_type)
    if origin is tuple or target_type is tuple:
      # Handle tuple[str, ...] or tuple
      # Split by comma and strip whitespace
      return tuple(v.strip() for v in value.split(",") if v.strip())
    else:
      # Default to string
      return value


def _set_nested_value(
  data: dict[str, Any],
  path: tuple[str, ...],
  value: Any,
) -> None:
  """Set a nested value in a dictionary.

  Args:
    data: Dictionary to modify
    path: Path to the nested key
    value: Value to set

  Example:
    data = {}
    _set_nested_value(data, ('backend', 'ollama', 'model'), 'llama3')
    # data = {'backend': {'ollama': {'model': 'llama3'}}}
  """
  for key in path[:-1]:
    if key not in data:
      data[key] = {}
    data = data[key]
  data[path[-1]] = value


def load_env_config(prefix: str | None = None) -> dict[str, Any]:
  """Load configuration from environment variables.

  Environment variables take the form:
    YOKER_BACKEND_OLLAMA_MODEL=value
    YOKER_PERMISSIONS_FILESYSTEM_PATHS=/path1,/path2
    YOKER_CONTEXT_PERSIST_AFTER_TURN=true

  With prefix:
    MYAPP_YOKER_BACKEND_OLLAMA_MODEL=value

  Args:
    prefix: Optional prefix for env vars (from YOKER_PREFIX env var or explicit)

  Returns:
    Dictionary with config structure from environment variables.
  """
  # Get prefix from env var if not explicitly provided
  if prefix is None:
    prefix = os.environ.get("YOKER_PREFIX", "")

  result: dict[str, Any] = {}

  # Determine the env var prefix to look for
  env_prefix = f"{prefix}_YOKER_" if prefix else "YOKER_"

  # Scan environment variables
  for env_key, env_value in os.environ.items():
    # Check if this env var matches our pattern
    if not env_key.startswith(env_prefix):
      continue

    # Strip the prefix to get the default env var name
    default_env_key = env_key[len(prefix) + 1 :] if prefix else env_key

    # Look up the config path using the default reverse mapping
    if default_env_key not in _DEFAULT_ENV_VAR_TO_PATH:
      # Unknown env var, skip
      continue

    # Get the config path and target type
    config_path = _DEFAULT_ENV_VAR_TO_PATH[default_env_key]
    target_type = _CONFIG_FIELD_TYPES[config_path]

    try:
      # Coerce the value to the correct type
      coerced_value = _coerce_value(env_value, target_type)
      _set_nested_value(result, config_path, coerced_value)
      log.debug(
        "env_var_loaded",
        env_var=env_key,
        path=".".join(config_path),
        value_type=type(coerced_value).__name__,
      )
    except ValueError as e:
      log.warning(
        "env_var_coercion_failed",
        env_var=env_key,
        value=env_value,
        target_type=target_type.__name__,
        error=str(e),
      )

  return result


def merge_configs(base: Config, overrides: dict[str, Any]) -> Config:
  """Merge environment overrides into a base configuration.

  Creates a new Config with values from overrides merged on top of base.
  Overrides take precedence over base values.

  Args:
    base: Base configuration
    overrides: Dictionary with override values (from load_env_config)

  Returns:
    New Config with merged values
  """
  if not overrides:
    return base

  # Convert base to dict for merging
  # Since Config is frozen, we need to build new instances

  def merge_section(
    base_obj: Any,
    overrides_dict: dict[str, Any] | None,
  ) -> Any:
    """Recursively merge a section."""
    if overrides_dict is None:
      return base_obj

    if not hasattr(base_obj, "__dataclass_fields__"):
      return base_obj

    # Build kwargs for new instance
    kwargs: dict[str, Any] = {}
    for f in fields(base_obj):
      field_name = f.name
      base_value = getattr(base_obj, field_name)

      if field_name in overrides_dict:
        override_value = overrides_dict[field_name]
        if hasattr(base_value, "__dataclass_fields__"):
          # Nested dataclass - recurse
          kwargs[field_name] = merge_section(base_value, override_value)
        else:
          # Leaf value - use override
          kwargs[field_name] = override_value
      else:
        # No override - use base value
        kwargs[field_name] = base_value

    # Create new instance
    return type(base_obj)(**kwargs)

  # Merge each top-level section
  result_kwargs: dict[str, Any] = {}
  for f in fields(base):
    section_name = f.name
    base_section = getattr(base, section_name)
    override_section = overrides.get(section_name)
    result_kwargs[section_name] = merge_section(base_section, override_section)

  return Config(**result_kwargs)


__all__ = [
  "load_config",
  "load_config_with_defaults",
  "discover_config",
  "load_env_config",
  "merge_configs",
]
