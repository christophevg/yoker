"""Configuration system for Yoker.

Uses Clevis for configuration management with:
  - Auto-generated CLI arguments from dataclass fields
  - Environment variable interpolation via TOML syntax (${VAR})
  - Config file discovery (~/.yoker.toml, ./yoker.toml)
  - Layered merging (env interpolation > CLI args > project config > user config)

Example:
    from yoker.config import Config, get_yoker_config

    # Load config with dev/test security bypass (auto-detected)
    config = get_yoker_config()

    # Load config with CLI argument support
    config = get_yoker_config(cli=True)

    # Access configuration values
    print(config.backend.ollama.model)
    print(config.tools.read.enabled)

Environment Variables:
    Environment variables can be used in TOML config files via interpolation:
        [backend.ollama]
        model = "${OLLAMA_MODEL}"
        base_url = "${OLLAMA_HOST:-http://localhost:11434}"

    Clevis processes these interpolations when loading the config.

Configuration Files:
    - User config: ~/.yoker.toml (lower priority)
    - Project config: ./yoker.toml (higher priority)

CLI Arguments:
    Clevis auto-generates CLI args from dataclass fields:
    --backend-ollama-model MODEL         Set model
    --context-session-id SESSION_ID      Set session ID
    --tools-read-enabled BOOL           Enable/disable read tool
"""

import os
from dataclasses import dataclass, field
from typing import Literal

from clevis import SecurityAction, SecurityConfig, get_config

from yoker.exceptions import ValidationError
from yoker.validators import (
  validate_choice,
  validate_directory_exists,
  validate_log_level,
  validate_non_empty_string,
  validate_non_negative_int,
  validate_positive_int,
  validate_regex_patterns,
  validate_url,
)


def get_yoker_config(cli: bool = False) -> "Config":
  """Get Yoker configuration with dev/test security bypass.

  This is the recommended way to load Yoker configuration. It automatically
  detects development/testing environments and relaxes security checks.

  Security bypass is enabled when:
    - YOKER_DEV_MODE=1 environment variable is set
    - PYTEST_CURRENT_TEST is set (running tests)

  In these environments, world-writable directories and files with relaxed
  permissions are allowed (logged but not blocked).

  Args:
    cli: Whether to parse CLI arguments (default: False for library mode).

  Returns:
    Config object with security settings appropriate for the environment.
  """
  security: SecurityConfig | None = None
  if os.environ.get("YOKER_DEV_MODE") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
    security = SecurityConfig(
      file_permissions=SecurityAction.LOG,
      directory_permissions=SecurityAction.LOG,
    )

  return get_config(Config, name="yoker", cli=cli, security=security)


@dataclass(frozen=True)
class HarnessConfig:
  """Harness metadata configuration.

  Attributes:
    name: Human-readable name for the harness.
    version: Version string for the configuration.
  """

  name: str | None = "yoker"
  version: str | None = "1.0"
  author: str | None = None

  def __post_init__(self) -> None:
    """Validate harness configuration."""
    validate_non_empty_string(self.name, "harness.name")
    validate_non_empty_string(self.version, "harness.version")


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
    validate_positive_int(self.top_k, "backend.ollama.parameters.top_k")
    validate_positive_int(self.num_ctx, "backend.ollama.parameters.num_ctx")


@dataclass(frozen=True)
class OllamaConfig:
  """Ollama backend configuration.

  Attributes:
    base_url: URL of the Ollama API server.
    api_key: Optional API key for Ollama authorization.
    model: Default model to use.
    timeout_seconds: Request timeout in seconds.
    parameters: Model generation parameters.
  """

  base_url: str = "http://localhost:11434"
  api_key: str | None = None
  model: str = "llama3.2:latest"
  timeout_seconds: int = 60
  parameters: OllamaParameters = field(default_factory=OllamaParameters)

  def __post_init__(self) -> None:
    """Validate Ollama configuration."""
    validate_url(self.base_url, "backend.ollama.base_url")
    validate_non_empty_string(self.model, "backend.ollama.model")
    validate_positive_int(self.timeout_seconds, "backend.ollama.timeout_seconds")


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
    validate_choice(self.provider, "backend.provider", ("ollama",))


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
    validate_choice(
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
    validate_choice(self.network_access, "permissions.network_access", ("none", "local", "all"))
    validate_positive_int(self.max_file_size_kb, "permissions.max_file_size_kb")
    validate_non_negative_int(self.max_recursion_depth, "permissions.max_recursion_depth")
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
    validate_positive_int(self.max_depth, "tools.list.max_depth")
    validate_positive_int(self.max_entries, "tools.list.max_entries")


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
    validate_regex_patterns(self.blocked_patterns, "tools.read.blocked_patterns")


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
    validate_positive_int(self.max_size_kb, "tools.write.max_size_kb")


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
    validate_positive_int(self.max_diff_size_kb, "tools.update.max_diff_size_kb")


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
    validate_positive_int(self.max_results, "tools.search.max_results")
    validate_positive_int(self.timeout_ms, "tools.search.timeout_ms")


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
    validate_positive_int(self.max_recursion_depth, "tools.agent.max_recursion_depth")
    validate_positive_int(self.timeout_seconds, "tools.agent.timeout_seconds")


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
class ExistenceToolConfig(ToolConfig):
  """Existence tool configuration.

  Attributes:
    enabled: Whether the existence tool is enabled.
  """

  pass  # Inherits enabled: bool = True from ToolConfig


@dataclass(frozen=True)
class SkillToolConfig(ToolConfig):
  """Skill tool configuration.

  Attributes:
    enabled: Whether the skill tool is enabled.
  """

  pass  # Inherits enabled: bool = True from ToolConfig


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
    existence: Existence tool config.
    websearch: Web search tool config.
    webfetch: Web fetch tool config.
    skill: Skill tool config.
  """

  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  write: WriteToolConfig = field(default_factory=WriteToolConfig)
  update: UpdateToolConfig = field(default_factory=UpdateToolConfig)
  search: SearchToolConfig = field(default_factory=SearchToolConfig)
  agent: AgentToolConfig = field(default_factory=AgentToolConfig)
  git: GitToolConfig = field(default_factory=GitToolConfig)
  mkdir: MkdirToolConfig = field(default_factory=MkdirToolConfig)
  existence: ExistenceToolConfig = field(default_factory=ExistenceToolConfig)
  websearch: WebSearchToolConfig = field(default_factory=WebSearchToolConfig)
  webfetch: WebFetchToolConfig = field(default_factory=WebFetchToolConfig)
  skill: SkillToolConfig = field(default_factory=SkillToolConfig)

  def __getitem__(self, name: str) -> ToolConfig:
    return getattr(self, name)

@dataclass(frozen=True)
class ToolsSharedConfig:
  """Shared tool configurations.

  Attributes:
    content_display: Content display configuration for write/update tools.
  """

  content_display: ContentDisplayConfig = field(default_factory=ContentDisplayConfig)

@dataclass(frozen=True)
class AgentsConfig:
  """Agent definition settings.

  Attributes:
    directories: Directories containing agent definition files.
    definition: Path to a specific agent definition file.
  """

  directories: tuple[str, ...] = ()
  definition: str = ""

  def __post_init__(self) -> None:
    """Validate agents configuration."""
    for directory in self.directories:
      validate_directory_exists(directory, "agents.directories")


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
class PluginsConfig:
  """Plugin configuration.

  Attributes:
    enabled: Whether plugins are enabled globally. Default: False.
    packages: List of plugin packages to load (e.g., ["pkgq", "c3"]).
    trusted: Dictionary of trusted plugin names. Key is package name, value is True.
  """

  enabled: bool = False
  packages: tuple[str, ...] = ()
  trusted: dict[str, bool] = field(default_factory=dict)


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

  level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "WARNING"
  format: Literal["json", "text"] = "text"
  file: str | None = None
  include_tool_calls: bool = True
  include_permission_checks: bool = True
  timestamp_format_string: str = "iso"

  def __post_init__(self) -> None:
    """Validate logging configuration."""
    validate_log_level(self.level, "logging.level")
    validate_choice(self.format, "logging.format", ("json", "text"))


@dataclass(frozen=True)
class UIConfig:
  """UI layer configuration.

  Attributes:
    mode: UI mode ('interactive' or 'batch').
    show_thinking: Whether to display thinking output.
    show_tool_calls: Whether to display tool call information.
    show_stats: Whether to display turn statistics.
  """

  mode: str = "interactive"
  show_thinking: bool = True
  show_tool_calls: bool = True
  show_stats: bool = True

  def __post_init__(self) -> None:
    """Validate UI configuration."""
    validate_choice(self.mode, "ui.mode", ("interactive", "batch"))


@dataclass(frozen=True)
class Config:
  """Root configuration container.

  Attributes:
    agent : the agent to use.
    harness: Harness metadata.
    backend: Backend provider configuration.
    context: Context management configuration.
    permissions: Permission boundaries.
    tools: Tool configurations.
    agents: Agent definition settings.
    skills: Skills configuration.
    plugins: Plugin configuration.
    logging: Logging configuration.
    ui: UI layer configuration.
  """

  agent: str | None = None

  harness: HarnessConfig = field(default_factory=HarnessConfig)
  backend: BackendConfig = field(default_factory=BackendConfig)
  context: ContextConfig = field(default_factory=ContextConfig)
  permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
  tools: ToolsConfig = field(default_factory=ToolsConfig)
  tools_shared : ToolsSharedConfig = field(default_factory=ToolsSharedConfig)
  agents: AgentsConfig = field(default_factory=AgentsConfig)
  skills: SkillsConfig = field(default_factory=SkillsConfig)
  plugins: PluginsConfig = field(default_factory=PluginsConfig)
  logging: LoggingConfig = field(default_factory=LoggingConfig)
  ui: UIConfig = field(default_factory=UIConfig)


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
  "ExistenceToolConfig",
  "WebSearchToolConfig",
  "WebFetchToolConfig",
  "ContentDisplayConfig",
  "SkillToolConfig",
  "ToolsConfig",
  "AgentsConfig",
  "SkillsConfig",
  "PluginsConfig",
  "LoggingConfig",
  "UIConfig",
  # Helper function
  "get_yoker_config",
]
