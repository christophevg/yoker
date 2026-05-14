"""Configuration schema definitions for Yoker.

Provides frozen dataclasses for all configuration sections.
Following clitic patterns for immutable configuration objects.
"""

from dataclasses import dataclass, field
from typing import Literal


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


@dataclass(frozen=True)
class BackendConfig:
  """Backend provider configuration.

  Attributes:
    provider: Backend provider name (currently only 'ollama').
    ollama: Ollama-specific configuration.
  """

  provider: str = "ollama"
  ollama: OllamaConfig = field(default_factory=OllamaConfig)


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


@dataclass(frozen=True)
class UpdateToolConfig(ToolConfig):
  """Update tool configuration.

  Attributes:
    require_exact_match: Whether to require exact match for updates.
    max_diff_size_kb: Maximum diff size in KB.
  """

  require_exact_match: bool = True
  max_diff_size_kb: int = 100


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


@dataclass(frozen=True)
class AgentToolConfig(ToolConfig):
  """Agent tool configuration.

  Attributes:
    max_recursion_depth: Maximum subagent recursion depth.
    timeout_seconds: Subagent timeout in seconds.
  """

  max_recursion_depth: int = 3
  timeout_seconds: int = 300


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
    default_type: Default agent type.
  """

  directory: str = ""
  default_type: str = "main"


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
    logging: Logging configuration.
  """

  harness: HarnessConfig = field(default_factory=HarnessConfig)
  backend: BackendConfig = field(default_factory=BackendConfig)
  context: ContextConfig = field(default_factory=ContextConfig)
  permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
  tools: ToolsConfig = field(default_factory=ToolsConfig)
  agents: AgentsConfig = field(default_factory=AgentsConfig)
  logging: LoggingConfig = field(default_factory=LoggingConfig)


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
  "LoggingConfig",
  "Config",
]
