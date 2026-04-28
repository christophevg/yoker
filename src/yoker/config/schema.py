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
  blocked_patterns: tuple[str, ...] = (r"\.env", "credentials", "secret")


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
  """

  list: ListToolConfig = field(default_factory=ListToolConfig)
  read: ReadToolConfig = field(default_factory=ReadToolConfig)
  write: WriteToolConfig = field(default_factory=WriteToolConfig)
  update: UpdateToolConfig = field(default_factory=UpdateToolConfig)
  search: SearchToolConfig = field(default_factory=SearchToolConfig)
  agent: AgentToolConfig = field(default_factory=AgentToolConfig)
  git: GitToolConfig = field(default_factory=GitToolConfig)


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
  "ToolsConfig",
  "AgentsConfig",
  "LoggingConfig",
  "Config",
]
