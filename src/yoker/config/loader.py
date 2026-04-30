"""TOML configuration loader for Yoker.

Loads configuration from yoker.toml files and parses into Config objects.
"""

import sys
from pathlib import Path

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

# Use tomli for Python < 3.11, tomllib for 3.11+
if sys.version_info >= (3, 11):
  import tomllib
else:
  import tomli as tomllib  # type: ignore[import-not-found]


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
  max_file_size_kb = int(max_file) if isinstance(max_file, (int, float)) else 500

  max_rec = perms.get("max_recursion_depth", 3)
  max_recursion_depth = int(max_rec) if isinstance(max_rec, (int, float)) else 3

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


__all__ = [
  "load_config",
  "load_config_with_defaults",
]
