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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from clevis import SecurityAction, SecurityConfig, get_config

from yoker.config.providers import (
  AnthropicConfig,
  AnthropicParameters,
  GeminiConfig,
  GeminiParameters,
  GenericConfig,
  GenericParameters,
  OllamaConfig,
  OllamaParameters,
  OpenAIConfig,
  OpenAIParameters,
  ProviderConfig,
)
from yoker.config.validators import (
  validate_choice,
  validate_directory_exists,
  validate_log_level,
  validate_non_empty_string,
  validate_positive_int,
  validate_regex_patterns,
)
from yoker.exceptions import ValidationError

if TYPE_CHECKING:
  # For the return-type annotation of get_yoker_config_with_manifest().
  # Imported lazily at runtime inside the function to avoid a config -> plugins
  # import dependency at module load time.
  from yoker.plugins.file_manifest import PluginConfig, RunConfig


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


@dataclass
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


# Known backend providers with specific config classes
KNOWN_PROVIDERS = ("ollama", "openai", "anthropic", "gemini")


@dataclass
class BackendConfig:
  """Backend provider configuration (tagged union by `provider`).

  Attributes:
    provider: Backend provider name. Can be:
      - 'ollama': Local inference server (native OllamaBackend)
      - 'openai': OpenAI GPT models (via LitellmBackend)
      - 'anthropic': Anthropic Claude models (via LitellmBackend)
      - 'gemini': Google Gemini models (via LitellmBackend)
      - Any other litellm-supported provider (e.g., 'groq', 'cohere', 'azure', 'mistral')
    ollama: Ollama-specific configuration (required when provider='ollama').
    openai: OpenAI-specific configuration (required when provider='openai').
    anthropic: Anthropic-specific configuration (required when provider='anthropic').
    gemini: Gemini-specific configuration (required when provider='gemini').

  Note:
    For known providers ('ollama', 'openai', 'anthropic', 'gemini'), the corresponding
    config attribute must be set. For unknown providers (any litellm-supported provider),
    a GenericConfig is created automatically. Litellm handles authentication and routing.
  """

  provider: str = "ollama"
  ollama: OllamaConfig = field(default_factory=OllamaConfig)
  openai: OpenAIConfig | None = None
  anthropic: AnthropicConfig | None = None
  gemini: GeminiConfig | None = None

  def __post_init__(self) -> None:
    self.validate()

  def validate(self) -> None:
    """Validate cross-field invariants.

    Known providers must have their corresponding config set; unknown
    providers (handled by litellm) use a GenericConfig at call time.
    """
    validate_non_empty_string(self.provider, "backend.provider")
    if self.provider in KNOWN_PROVIDERS:
      config = getattr(self, self.provider, None)
      if config is None:
        raise ValidationError(
          f"backend.{self.provider}", None, f"required when provider='{self.provider}'"
        )

  @property
  def config(self) -> ProviderConfig:
    """Get the active provider's config.

    Returns the config for the currently selected provider.
    For unknown providers, returns a GenericConfig with model from environment
    or defaults (model must be specified in agent definition or config).

    Returns:
      ProviderConfig for the active provider. Never None.
    """
    # Known providers have their config as an attribute
    if self.provider in KNOWN_PROVIDERS:
      # Type assertion: validation in __post_init__ guarantees non-None
      return cast(ProviderConfig, getattr(self, self.provider))

    # Unknown provider: return GenericConfig
    # Model should come from agent definition or fallback
    return GenericConfig(model="")


@dataclass
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
  filename: str = "{session_id}-{agent_id}"
  fresh: bool = False

  def __post_init__(self) -> None:
    """Validate context configuration."""
    validate_choice(
      self.manager,
      "context.manager",
      ("basic_persistence", "compaction", "multi_tier"),
    )


@dataclass
class HandlerConfig:
  """Permission handler configuration.

  Attributes:
    mode: Handler mode ('block', 'allow', 'ask_user').
    message: Custom message for ask_user mode.
  """

  mode: str = "block"
  message: str | None = None


@dataclass
class PermissionsConfig:
  """Permission boundaries configuration.

  Attributes:
    filesystem_paths: Allowed filesystem paths.
    network_access: Network access level ('none', 'local', 'all').
    max_file_size_kb: Maximum file size in KB.
    handlers: Permission handler configurations.
  """

  filesystem_paths: tuple[str, ...] = (".",)
  network_access: str = "none"
  max_file_size_kb: int = 500
  handlers: dict[str, HandlerConfig] = field(default_factory=dict)

  def __post_init__(self) -> None:
    """Validate permissions configuration."""
    validate_choice(self.network_access, "permissions.network_access", ("none", "local", "all"))
    validate_positive_int(self.max_file_size_kb, "permissions.max_file_size_kb")
    if not self.filesystem_paths:
      raise ValidationError(
        "permissions.filesystem_paths",
        self.filesystem_paths,
        "must not be empty for security",
      )


@dataclass
class ToolConfig:
  """Base tool configuration.

  Attributes:
    enabled: Whether the tool is enabled.
  """

  enabled: bool = True


@dataclass
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


@dataclass
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


@dataclass
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


@dataclass
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


@dataclass
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


@dataclass
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


@dataclass
class AgentToolConfig(ToolConfig):
  """Agent tool configuration.

  Attributes:
    timeout_seconds: Subagent timeout in seconds.
  """

  timeout_seconds: int = 300

  def __post_init__(self) -> None:
    """Validate agent tool configuration."""
    validate_positive_int(self.timeout_seconds, "tools.agent.timeout_seconds")


# Matches valid Makefile target names per GNU make conventions.
_TARGET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+\-]*$")


@dataclass
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


@dataclass
class MakeToolConfig(ToolConfig):
  """Make tool configuration.

  Attributes:
    timeout_ms: Default timeout in milliseconds.
    max_output_kb: Maximum output size per stream (stdout/stderr) in KB.
    allowed_env_vars: Per-target allowlist of env var names. Keys are
      Makefile target names; values are the env var names that target is
      permitted to receive. Targets not in the dict deny all env vars
      (deny-by-default). Empty dict = all env vars denied for all targets.
    max_env_var_bytes: Maximum byte size per env var value.
  """

  timeout_ms: int = 300000
  max_output_kb: int = 100
  allowed_env_vars: dict[str, tuple[str, ...]] = field(default_factory=dict)
  max_env_var_bytes: int = 4096

  def __post_init__(self) -> None:
    """Validate make tool configuration."""
    validate_positive_int(self.timeout_ms, "tools.make.timeout_ms")
    validate_positive_int(self.max_output_kb, "tools.make.max_output_kb")
    validate_positive_int(self.max_env_var_bytes, "tools.make.max_env_var_bytes")
    for target in self.allowed_env_vars:
      if not _TARGET_NAME_RE.fullmatch(target):
        raise ValidationError(
          "tools.make.allowed_env_vars",
          target,
          f"invalid target name key: {target!r}",
        )


@dataclass
class MkdirToolConfig(ToolConfig):
  """Mkdir tool configuration.

  Attributes:
    max_depth: Maximum directory depth from allowed root.
  """

  max_depth: int = 20


@dataclass
class ExistenceToolConfig(ToolConfig):
  """Existence tool configuration.

  Attributes:
    enabled: Whether the existence tool is enabled.
  """

  pass  # Inherits enabled: bool = True from ToolConfig


@dataclass
class SkillToolConfig(ToolConfig):
  """Skill tool configuration.

  Attributes:
    enabled: Whether the skill tool is enabled.
  """

  pass  # Inherits enabled: bool = True from ToolConfig


@dataclass
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


@dataclass
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


@dataclass
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
    make: Make tool config.
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
  make: MakeToolConfig = field(default_factory=MakeToolConfig)

  def __getitem__(self, name: str) -> ToolConfig:
    return cast(ToolConfig, getattr(self, name))


@dataclass
class ToolsSharedConfig:
  """Shared tool configurations.

  Attributes:
    content_display: Content display configuration for write/update tools.
  """

  content_display: ContentDisplayConfig = field(default_factory=ContentDisplayConfig)


@dataclass
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


@dataclass
class SkillsConfig:
  """Skills configuration.

  Attributes:
    directories: Directories containing skill definition files.
    discovery: Whether to show skill discovery block on startup.
  """

  directories: tuple[str, ...] = ()
  discovery: bool = True


@dataclass
class PluginsConfig:
  """Plugin configuration.

  Attributes:
    enabled: Whether plugins are enabled globally. Default: False.
    packages: List of plugin packages to load (e.g., ["pkgq", "c3"]).
    trusted: Dictionary of trusted plugin names. Key is package name, value is True.
  """

  enabled: bool = field(default=False, metadata={"help": "Whether plugins are enabled globally"})
  packages: tuple[str, ...] = field(
    default=(), metadata={"help": "Plugin packages to load (e.g. pkgq, c3)"}
  )
  trusted: dict[str, bool] = field(default_factory=dict)


@dataclass
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


@dataclass
class UIConfig:
  """UI layer configuration.

  Attributes:
    mode: UI mode ('interactive' or 'batch').
    show_thinking: Whether to display thinking output.
    show_tool_calls: Whether to display tool call information.
    show_stats: Whether to display turn statistics.
  """

  mode: str = field(
    default="interactive",
    metadata={"help": "UI mode ('interactive' or 'batch')"},
  )
  show_thinking: bool = field(default=True, metadata={"help": "Display thinking output"})
  show_tool_calls: bool = field(default=True, metadata={"help": "Display tool call information"})
  show_stats: bool = field(default=True, metadata={"help": "Display turn statistics"})

  def __post_init__(self) -> None:
    """Validate UI configuration."""
    validate_choice(self.mode, "ui.mode", ("interactive", "batch"))


@dataclass
class SessionConfig:
  """Session configuration.

  A :class:`Session` manages a team of agents: lifecycle, registry,
  recursion depth, event aggregation, and inter-agent messaging.

  Attributes:
    max_agents: Hard cap on concurrent agents in a session.
    default_isolation_policy: Default context isolation for spawned agents
      (``"fresh"`` or ``"fork"``).
    event_aggregation: Whether sub-agent events are aggregated to session
      handlers.
  """

  max_agents: int = 10
  default_isolation_policy: str = "fresh"
  event_aggregation: bool = True

  def __post_init__(self) -> None:
    """Validate session configuration."""
    validate_positive_int(self.max_agents, "session.max_agents")
    validate_choice(
      self.default_isolation_policy,
      "session.default_isolation_policy",
      ("fresh", "fork"),
    )


@dataclass
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
    session: Session configuration.
  """

  agent: str | None = None

  harness: HarnessConfig = field(default_factory=HarnessConfig)
  backend: BackendConfig = field(default_factory=BackendConfig)
  context: ContextConfig = field(default_factory=ContextConfig)
  permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
  tools: ToolsConfig = field(default_factory=ToolsConfig)
  tools_shared: ToolsSharedConfig = field(default_factory=ToolsSharedConfig)
  agents: AgentsConfig = field(default_factory=AgentsConfig)
  skills: SkillsConfig = field(default_factory=SkillsConfig)
  plugins: PluginsConfig = field(default_factory=PluginsConfig)
  logging: LoggingConfig = field(default_factory=LoggingConfig)
  ui: UIConfig = field(default_factory=UIConfig)
  session: SessionConfig = field(default_factory=SessionConfig)


def get_yoker_config_with_manifest(
  manifest_path: Path | None,
  cli: bool = False,
) -> tuple["Config", "RunConfig", "PluginConfig"]:
  """Load Yoker configuration with a manifest override layer applied.

  Implements the configuration cascade::

      dataclass defaults
        -> user TOML (~/.yoker.toml)
        -> project TOML (./yoker.toml)
        -> manifest overrides (<source>/agent.toml)
        -> CLI arguments (highest priority)

  The manifest is a generic config-override layer: any :class:`Config` field
  can be overridden from ``agent.toml``. ``[run]`` and ``[plugin]`` sections
  are extracted separately and returned alongside the merged config.

  Args:
    manifest_path: Path to the ``agent.toml`` file. If ``None`` or the file
      does not exist, falls back to :func:`get_yoker_config` (no manifest
      layer) and returns empty run/plugin configs.
    cli: Whether to parse CLI arguments (highest-priority override layer).

  Returns:
    A ``(config, run_config, plugin_config)`` tuple where ``config`` is the
    merged :class:`Config`, ``run_config`` is the ``[run]`` section, and
    ``plugin_config`` is the ``[plugin]`` section.

  Raises:
    PluginError: If the manifest exists but is malformed.
  """
  from clevis import build_default_cascade, get_config

  from yoker.plugins.file_manifest import (
    PluginConfig,
    RunConfig,
    load_file_manifest,
  )

  # Security: mirror get_yoker_config's dev/test bypass.
  security: SecurityConfig | None = None
  if os.environ.get("YOKER_DEV_MODE") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
    security = SecurityConfig(
      file_permissions=SecurityAction.LOG,
      directory_permissions=SecurityAction.LOG,
    )

  # Build the cascade: user TOML → project TOML → manifest overrides.
  # CLI args are applied by get_config on top (highest priority).
  cascade = build_default_cascade("yoker", security)

  run_config = RunConfig()
  plugin_config = PluginConfig()
  if manifest_path is not None:
    manifest = load_file_manifest(manifest_path)
    if manifest is not None:
      run_config = manifest.run_config
      plugin_config = manifest.plugin_config
      overrides = manifest.config_overrides
      cascade = cascade + [lambda: overrides]

  config = get_config(Config, name="yoker", cascade=cascade, cli=cli)
  return config, run_config, plugin_config


__all__ = [
  # Configuration classes
  "Config",
  "HarnessConfig",
  "BackendConfig",
  # Provider configuration classes (from providers.py)
  "OllamaConfig",
  "OllamaParameters",
  "OpenAIConfig",
  "OpenAIParameters",
  "AnthropicConfig",
  "AnthropicParameters",
  "GeminiConfig",
  "GeminiParameters",
  "GenericConfig",
  "GenericParameters",
  "ProviderConfig",
  # Other configuration classes
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
  "MakeToolConfig",
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
  "SessionConfig",
  # Constants
  "KNOWN_PROVIDERS",
  # Helper function
  "get_yoker_config",
  "get_yoker_config_with_manifest",
]
