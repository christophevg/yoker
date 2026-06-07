"""Configuration system for Yoker.

Uses Clevis for configuration management with:
  - Auto-generated CLI arguments from dataclass fields
  - Environment variable support (YOKER_*)
  - Config file discovery (~/.yoker.toml, ./yoker.toml)
  - Layered merging (env vars > CLI args > project config > user config)

Example:
    from yoker.config import Config
    from clevis import get_config

    # Load config (auto-discovers from ./yoker.toml or ~/.yoker.toml)
    config = get_config(Config, name="yoker")

    # Load config with CLI argument support
    config = get_config(Config, name="yoker", cli=True)

    # Access configuration values
    print(config.backend.ollama.model)
    print(config.tools.read.enabled)

Environment Variables:
    YOKER_* environment variables override config file values.
    Example: YOKER_BACKEND_OLLAMA_MODEL=llama3.2:latest

Configuration Files:
    - User config: ~/.yoker.toml (lower priority)
    - Project config: ./yoker.toml (higher priority)

CLI Arguments:
    Clevis auto-generates CLI args from dataclass fields:
    --backend-ollama-model MODEL         Set model
    --context-session-id SESSION_ID      Set session ID
    --tools-read-enabled BOOL           Enable/disable read tool
"""

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
]
