"""Configuration schema definitions for Yoker.

Provides frozen dataclasses for all configuration sections with validation.
Following clitic patterns for immutable configuration objects.
Uses Clevis for configuration management.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from yoker.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _validate_url(value: str, path: str) -> None:
  """Validate that a value is a valid URL.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is not a valid URL.
  """
  try:
    result = urlparse(value)
    if not result.scheme or not result.netloc:
      raise ValidationError(path, value, "must be a valid URL with scheme and host")
  except Exception as e:
    raise ValidationError(path, value, f"must be a valid URL: {e}") from None


def _validate_non_empty_string(value: str, path: str) -> None:
  """Validate that a value is a non-empty string.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is empty.
  """
  if not value or not value.strip():
    raise ValidationError(path, value, "must be a non-empty string")


def _validate_positive_int(value: int, path: str) -> None:
  """Validate that a value is a positive integer.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is not positive.
  """
  if value <= 0:
    raise ValidationError(path, value, "must be a positive integer")


def _validate_non_negative_int(value: int, path: str) -> None:
  """Validate that a value is a non-negative integer.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the value is negative.
  """
  if value < 0:
    raise ValidationError(path, value, "must be a non-negative integer")


def _validate_choice(
  value: str,
  path: str,
  choices: tuple[str, ...],
) -> None:
  """Validate that a value is one of the allowed choices.

  Args:
    value: The value to validate.
    path: Configuration path for error messages.
    choices: Allowed values.

  Raises:
    ValidationError: If the value is not in choices.
  """
  if value not in choices:
    raise ValidationError(path, value, f"must be one of {choices}")


def _validate_log_level(value: str, path: str) -> None:
  """Validate that a log level is valid.

  Args:
    value: The log level to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If the log level is invalid.
  """
  valid_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
  if value.upper() not in valid_levels:
    raise ValidationError(path, value, f"must be one of {valid_levels}")


def _validate_regex_patterns(
  patterns: tuple[str, ...],
  path: str,
) -> None:
  """Validate that regex patterns are valid.

  Args:
    patterns: The regex patterns to validate.
    path: Configuration path for error messages.

  Raises:
    ValidationError: If any pattern is invalid.
  """
  for pattern in patterns:
    try:
      re.compile(pattern)
    except re.error as e:
      raise ValidationError(path, pattern, f"invalid regex pattern: {e}") from None


def _validate_directory_exists(value: str, path: str) -> None:
  """Validate that a directory exists (warning only).

  Args:
    value: The directory path to validate.
    path: Configuration path for error messages.
  """
  dir_path = Path(value)
  if not dir_path.exists():
    logger.warning(f"Configuration warning at '{path}': Directory does not exist: {value}")


@dataclass(frozen=True)
class HarnessConfig:
  """Harness metadata configuration.

  Attributes:
    name: Human-readable name for the harness.
    version: Version string for the configuration.
    log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
  """

  name: str = "yoker"
  version: str = "1.0"
  log_level: str = "INFO"

  def __post_init__(self) -> None:
    """Validate harness configuration."""
    _validate_non_empty_string(self.name, "harness.name")
    _validate_log_level(self.log_level, "harness.log_level")


@dataclass(frozen=True)
class OllamaParameters:
  """Ollama model parameters.

  Attributes:
    temperature: Sampling temperature (0.0-2.0).
    top_p: Nucleus sampling probability (0.0-1.0).
    top_k: Top-k sampling parameter.
    num_ctx: Context window size.
  """

  temperature: float = 0.7
  top_p: float = 0.9
  top_k: int = 40
  num_ctx: int = 4096

  def __post_init__(self) -> None:
    """Validate Ollama parameters."""
    if not 0.0 <= self.temperature <= 2.0:
      raise ValidationError(
        "backend.ollama.parameters.temperature",
        self.temperature,
        "must be between 0.0 and 2.0",
      )
    if not 0.0 <= self.top_p <= 1.0:
      raise ValidationError(
        "backend.ollama.parameters.top_p",
        self.top_p,
        "must be between 0.0 and 1.0",
      )
    _validate_positive_int(self.top_k, "backend.ollama.parameters.top_k")
    _validate_positive_int(self.num_ctx, "backend.ollama.parameters.num_ctx")


@dataclass(frozen=True)
class OllamaConfig:
  """Ollama backend configuration.

  Attributes:
    base_url: URL of the Ollama API server.
    model: Default model to use.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  base_url: str = "http://localhost:11434"
  model: str = "llama3.2:latest"
  timeout_seconds: int = 60
  parameters: OllamaParameters = field(default_factory=OllamaParameters)

  def __post_init__(self) -> None:
    """Validate Ollama configuration."""
    _validate_url(self.base_url, "backend.ollama.base_url")
    _validate_non_empty_string(self.model, "backend.ollama.model")
    _validate_positive_int(self.timeout_seconds, "backend.ollama.timeout_seconds")


@dataclass(frozen=True)
class BackendConfig:
  """Backend provider configuration.

  Attributes:
    provider: Backend provider name (currently only 'ollama').
    ollama: Ollama-specific configuration.
  """

  provider: str = "ollama"
  ollama: OllamaConfig = field(default_factory=OllamaConfig)

  def __post_init__(self) -> None:
    """Validate backend configuration."""
    _validate_choice(self.provider, "backend.provider", ("ollama",))


@dataclass(frozen=True)
class ContextConfig:
  """Context management configuration.

  Attributes:
    manager: Context manager type ('basic_persistence', 'compaction', 'multi_tier').
    storage_path: Path to store context files.
    session_id: Session identifier ('auto' for generated).
    persist_after_turn: Whether to persist after each turn.
  """

  manager: str = "basic_persistence"
  storage_path: str = "./context"
  session_id: str = "auto"
  persist_after_turn: bool = True

  def __post_init__(self) -> None:
    """Validate context configuration."""
    _validate_choice(
      self.manager,
      "context.manager",
      ("basic_persistence", "compaction", "multi_tier"),
    )


@dataclass(frozen=True)
class HandlerConfig:
  """Permission handler configuration.

  Attributes:
    mode: Handler mode ('block', 'allow', 'ask_user').
    message: Custom message for ask_user mode.
  """

  mode: str = "block"
  message: str | None = None


@dataclass(frozen=True)
class PermissionsConfig:
  """Permission boundaries configuration.

  Attributes:
    filesystem_paths: Allowed filesystem paths.
    network_access: Network access level ('none', 'local', 'all').
    max_file_size_kb: Maximum file size in KB.
    max_recursion_depth: Maximum subagent recursion depth.
    handlers: Permission handler configurations.
  """

  filesystem_paths: tuple[str, ...] = (".",)
  network_access: str = "none"
  max_file_size_kb: int = 500
  max_recursion_depth: int = 3
  handlers: dict[str, HandlerConfig] = field(default_factory=dict)

  def __post_init__(self) -> None:
    """Validate permissions configuration."""
    _validate_choice(self.network_access, "permissions.network_access", ("none", "local", "all"))
    _validate_positive_int(self.max_file_size_kb, "permissions.max_file_size_kb")
    _validate_non_negative_int(self.max_recursion_depth, "permissions.max_recursion_depth")
    if not self.filesystem_paths:
      raise ValidationError(
        "permissions.filesystem_paths",
        self.filesystem_paths,
        "must not be empty for security",
      )


@dataclass(frozen=True)
class ToolConfig:
  """Base tool configuration.

  Attributes:
    enabled: Whether the tool is enabled.
  """

  enabled: bool = True


@dataclass(frozen=True)
class ListToolConfig(ToolConfig):
  """List tool configuration.

  Attributes:
    max_depth: Maximum directory depth to traverse.
    max_entries: Maximum entries to return.
  """

  max_depth: int = 5
  max_entries: int = 2000

  def __post_init__(self) -> None:
    """Validate list tool configuration."""
    _validate_positive_int(self.max_depth, "tools.list.max_depth")
    _validate_positive_int(self.max_entries, "tools.list.max_entries")


@dataclass(frozen=True)
class ReadToolConfig(ToolConfig):
  """Read tool configuration.

  Attributes:
    allowed_extensions: Allowed file extensions.
    blocked_patterns: Blocked file patterns.
  """

  allowed_extensions: tuple[str, ...] = (
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
  )
  blocked_patterns: tuple[str, ...] = (
    r"\.env",  # Environment files
    r"\.git",  # Git directories
    r"\.ssh",  # SSH directories
    r"\.aws",  # AWS credentials
    r"\.gnupg",  # GPG keys
    "credentials",  # Credential files
    r"secrets?",  # Secret files (singular/plural)
    r"\.pem$",  # Certificate files
    r"\.key$",  # Key files
    "id_rsa",  # SSH private keys
    "id_ed25519",  # Ed25519 keys
    r"\.bak$",  # Backup files
    r"\.old$",  # Old files
  )

  def __post_init__(self) -> None:
    """Validate read tool configuration."""
    _validate_regex_patterns(self.blocked_patterns, "tools.read.blocked_patterns")


@dataclass(frozen=True)
class WriteToolConfig(ToolConfig):
  """Write tool configuration.

  Attributes:
    allow_overwrite: Whether to allow overwriting files.
    max_size_kb: Maximum file size to write in KB.
    blocked_extensions: Blocked file extensions.
  """

  allow_overwrite: bool = False
  max_size_kb: int = 1000
  blocked_extensions: tuple[str, ...] = (".exe", ".sh", ".bat")

  def __post_init__(self) -> None:
    """Validate write tool configuration."""
    _validate_positive_int(self.max_size_kb, "tools.write.max_size_kb")


@dataclass(frozen=True)
class UpdateToolConfig(ToolConfig):
  """Update tool configuration.

  Attributes:
    require_exact_match: Whether to require exact match for updates.
    max_diff_size_kb: Maximum diff size in KB.
  """

  require_exact_match: bool = True
  max_diff_size_kb: int = 100

  def __post_init__(self) -> None:
    """Validate update tool configuration."""
    _validate_positive_int(self.max_diff_size_kb, "tools.update.max_diff_size_kb")


@dataclass(frozen=True)
class ContentDisplayConfig:
  """Configuration for displaying file content in tool operations.

  Attributes:
    verbosity: Verbosity level: 'silent' (no content), 'summary' (line counts),
      'content' (full content with truncation).
    max_content_lines: Maximum lines to show before truncation.
    max_content_bytes: Maximum bytes to show before truncation.
    show_diff_for_updates: Whether to show before/after for update operations.
    max_diff_lines: Maximum lines in diff display.
  """

  verbosity: str = "summary"  # "silent", "summary", "content"
  max_content_lines: int = 50
  max_content_bytes: int = 4096
  show_diff_for_updates: bool = True
  max_diff_lines: int = 30


@dataclass(frozen=True)
class SearchToolConfig(ToolConfig):
  """Search tool configuration.

  Attributes:
    max_regex_complexity: Maximum regex complexity level.
    max_results: Maximum search results to return.
    timeout_ms: Search timeout in milliseconds.
  """

  max_regex_complexity: str = "medium"
  max_results: int = 500
  timeout_ms: int = 10000

  def __post_init__(self) -> None:
    """Validate search tool configuration."""
    _validate_positive_int(self.max_results, "tools.search.max_results")
    _validate_positive_int(self.timeout_ms, "tools.search.timeout_ms")


@dataclass(frozen=True)
class AgentToolConfig(ToolConfig):
  """Agent tool configuration.

  Attributes:
    max_recursion_depth: Maximum subagent recursion depth.
    timeout_seconds: Subagent timeout in seconds.
  """

  max_recursion_depth: int = 3
  timeout_seconds: int = 300

  def __post_init__(self) -> None:
    """Validate agent tool configuration."""
    _validate_positive_int(self.max_recursion_depth, "tools.agent.max_recursion_depth")
    _validate_positive_int(self.timeout_seconds, "tools.agent.timeout_seconds")


@dataclass(frozen=True)
class GitToolConfig(ToolConfig):
  """Git tool configuration.

  Attributes:
    allowed_commands: Allowed git commands.
    requires_permission: Commands that require user permission.
  """

  allowed_commands: tuple[str, ...] = (
    "status",
    "log",
    "diff",
    "branch",
    "show",
  )
  requires_permission: tuple[str, ...] = ("commit", "push")


@dataclass(frozen=True)
class MkdirToolConfig(ToolConfig):
  """Mkdir tool configuration.

  Attributes:
    max_depth: Maximum directory depth from allowed root.
  """

  max_depth: int = 20


@dataclass(frozen=True)
class WebSearchToolConfig(ToolConfig):
  """Web search tool configuration.

  Attributes:
    backend: Backend to use ("ollama" or "local").
    max_results: Maximum results per search.
    max_query_length: Maximum query string length.
    timeout_seconds: Search timeout in seconds.
    requests_per_minute: Rate limit per minute (0 = unlimited).
    requests_per_hour: Rate limit per hour (0 = unlimited).
    domain_allowlist: Domains to allow (empty = all allowed).
    domain_blocklist: Domains to block (empty = none blocked).
    block_private_cidrs: Whether to block private IP ranges.
  """

  backend: str = "ollama"
  max_results: int = 10
  max_query_length: int = 500
  timeout_seconds: int = 30
  requests_per_minute: int = 60
  requests_per_hour: int = 1000
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
  block_private_cidrs: bool = True


@dataclass(frozen=True)
class WebFetchToolConfig(ToolConfig):
  """Web fetch tool configuration.

  Attributes:
    backend: Backend to use ("ollama" or "local").
    timeout_seconds: Fetch timeout in seconds.
    max_size_kb: Maximum content size in KB.
    max_redirects: Maximum redirect hops to follow.
    content_type: Default output format ("markdown", "text", "html").
    domain_allowlist: Domains to allow (empty = all allowed).
    domain_blocklist: Domains to block (empty = none blocked).
    block_private_cidrs: Whether to block private IP ranges.
    block_metadata_endpoints: Whether to block cloud metadata IPs.
    require_https: Whether to require HTTPS (block HTTP).
    follow_redirects: Whether to follow redirects.
    validate_redirects: Whether to revalidate each redirect URL.
  """

  backend: str = "ollama"
  timeout_seconds: int = 30
  max_size_kb: int = 2048
  max_redirects: int = 5
  content_type: str = "markdown"
  domain_allowlist: tuple[str, ...] = ()
  domain_blocklist: tuple[str, ...] = ()
  block_private_cidrs: bool = True
  block_metadata_endpoints: bool = True
  require_https: bool = True
  follow_redirects: bool = True
  validate_redirects: bool = True


@dataclass(frozen=True)
class ToolsConfig:
  """All tool configurations.

  Attributes:
    list: List tool config.
    read: Read tool config.
    write: Write tool config.
    update: Update tool config.
    search: Search tool config.
    agent: Agent tool config.
    git: Git tool config.
    mkdir: Mkdir tool config.
    websearch: Web search tool config.
    webfetch: Web fetch tool config.
    content_display: Content display configuration for write/update tools.
  """

  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  write: WriteToolConfig = field(default_factory=WriteToolConfig)
  update: UpdateToolConfig = field(default_factory=UpdateToolConfig)
  search: SearchToolConfig = field(default_factory=SearchToolConfig)
  agent: AgentToolConfig = field(default_factory=AgentToolConfig)
  git: GitToolConfig = field(default_factory=GitToolConfig)
  mkdir: MkdirToolConfig = field(default_factory=MkdirToolConfig)
  websearch: WebSearchToolConfig = field(default_factory=WebSearchToolConfig)
  webfetch: WebFetchToolConfig = field(default_factory=WebFetchToolConfig)
  content_display: ContentDisplayConfig = field(default_factory=ContentDisplayConfig)


@dataclass(frozen=True)
class AgentsConfig:
  """Agent definition settings.

  Attributes:
    directory: Directory containing agent definition files (empty = no directory).
    definition: Path to a specific agent definition file (overrides default_type).
    default_type: Default agent type.
  """

  directory: str = ""
  definition: str = ""
  default_type: str = "main"

  def __post_init__(self) -> None:
    """Validate agents configuration."""
    if self.directory:
      _validate_directory_exists(self.directory, "agents.directory")


@dataclass(frozen=True)
class SkillsConfig:
  """Skills configuration.

  Attributes:
    directories: Directories containing skill definition files.
    discovery: Whether to show skill discovery block on startup.
  """

  directories: tuple[str, ...] = ()
  discovery: bool = True


@dataclass(frozen=True)
class LoggingConfig:
  """Logging configuration.

  Attributes:
    level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    format: Log format ('json' or 'text').
    file: Optional file path for log output.
    include_tool_calls: Whether to include tool calls in logs.
    include_permission_checks: Whether to include permission checks in logs.
  """

  level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
  format: Literal["json", "text"] = "text"
  file: str | None = None
  include_tool_calls: bool = True
  include_permission_checks: bool = True

  def __post_init__(self) -> None:
    """Validate logging configuration."""
    _validate_choice(self.format, "logging.format", ("json", "text"))


@dataclass(frozen=True)
class Config:
  """Root configuration container.

  Attributes:
    harness: Harness metadata.
    backend: Backend provider configuration.
    context: Context management configuration.
    permissions: Permission boundaries.
    tools: Tool configurations.
    agents: Agent definition settings.
    skills: Skills configuration.
    logging: Logging configuration.
  """

  harness: HarnessConfig = field(default_factory=HarnessConfig)
  backend: BackendConfig = field(default_factory=BackendConfig)
  context: ContextConfig = field(default_factory=ContextConfig)
  permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
  tools: ToolsConfig = field(default_factory=ToolsConfig)
  agents: AgentsConfig = field(default_factory=AgentsConfig)
  skills: SkillsConfig = field(default_factory=SkillsConfig)
  logging: LoggingConfig = field(default_factory=LoggingConfig)

  @classmethod
  def discover(cls, config_path: Path | str | None = None) -> "Config":
    """Auto-discover configuration from environment and files.

    Resolution order (highest to lowest priority):
      1. Environment variables (YOKER_* or {PREFIX}_YOKER_*)
      2. Explicit config_path parameter
      3. ./yoker.toml (project config)
      4. ~/.yoker.toml (user config)
      5. Default Config()

    Args:
      config_path: Optional explicit path to config file.

    Returns:
      Config with resolved values from all sources.

    Example:
      >>> config = Config.discover()  # Auto-discover
      >>> config = Config.discover("./custom.toml")  # Explicit path
    """
    # Use discover_config from __init__.py which handles list-to-tuple conversion
    from yoker.config import discover_config

    config, _ = discover_config()
    return config


__all__ = [
  "HarnessConfig",
  "OllamaParameters",
  "OllamaConfig",
  "BackendConfig",
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
  "SkillsConfig",
  "LoggingConfig",
  "Config",
]
