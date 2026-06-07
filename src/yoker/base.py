"""Shared state and utilities for the async Agent.

This module provides AgentCore, a composition class that holds shared state
and utilities for the async-only Agent implementation.

.. warning::
  This class is for internal use. Use Agent instead.
"""

import os
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from yoker.config import Config
from yoker.logging import get_logger
from yoker.thinking import ThinkingMode
from yoker.tools import Tool, ToolRegistry
from yoker.tools.existence import ExistenceTool
from yoker.tools.git import GitTool
from yoker.tools.list import ListTool
from yoker.tools.mkdir import MkdirTool
from yoker.tools.read import ReadTool
from yoker.tools.search import SearchTool
from yoker.tools.update import UpdateTool
from yoker.tools.web_backend import OllamaWebFetchBackend, OllamaWebSearchBackend
from yoker.tools.web_guardrail import WebGuardrail, WebGuardrailConfig
from yoker.tools.webfetch import WebFetchTool
from yoker.tools.websearch import WebSearchTool
from yoker.tools.write import WriteTool

if TYPE_CHECKING:
  from ollama import AsyncClient

  from yoker.agents import AgentDefinition
  from yoker.commands import CommandRegistry
  from yoker.context import ContextManager
  from yoker.events import Event
  from yoker.skills import SkillRegistry
  from yoker.tools.path_guardrail import PathGuardrail

log = get_logger(__name__)

# Type alias for event callbacks
# Supports both sync handlers: Callable[["Event"], None]
# and async handlers: Callable[["Event"], Coroutine[None, None, None]]
EventCallback = Callable[["Event"], None] | Callable[["Event"], Coroutine[None, None, None]]

# Default system prompt
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

# Tools that operate on filesystem paths (require guardrail injection)
_FILESYSTEM_TOOLS = frozenset(
  {"read", "list", "write", "update", "search", "existence", "mkdir", "git"}
)


class AgentCore:
  """Shared state and utilities for the async Agent.

  This class holds configuration, tool registry, context manager,
  and other state needed by the Agent.

  Not intended for direct use by consumers. Use Agent instead.

  Note:
    This class is not thread-safe. Each Agent instance must have
    its own AgentCore instance. Do not share AgentCore between agents.

  Attributes:
    config: Configuration object.
    model: Model name to use for chat.
    thinking_mode: Current thinking mode state.
    agent_definition: Loaded agent definition, if any.
    tool_registry: Registry of available tools.
    context: Context manager for conversation history.
    command_registry: Command registry for slash-commands, if any.
  """

  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    config_path: Path | str | None = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    command_registry: "CommandRegistry | None" = None,
    agent_definition: "AgentDefinition | None" = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    client: "AsyncClient | None" = None,
    _recursion_depth: int = 0,
  ) -> None:
    """Initialize shared agent state.

    Config Resolution (in order of precedence):
        1. Environment variables (YOKER_* or {PREFIX}_YOKER_*)
        2. Explicit `config` parameter
        3. Explicit `config_path` parameter
        4. Auto-discovered config (./yoker.toml, ~/.yoker.toml)
        5. Config() defaults

    Agent Definition Resolution (in order of precedence):
        1. Explicit `agent_definition` parameter
        2. Explicit `agent_path` parameter
        3. Config's `agents.definition` (if set and file exists)
        4. None (default system prompt)

    Args:
      model: Model to use (overrides config if provided).
      config: Configuration object (takes precedence over config_path).
      config_path: Path to configuration file (loaded if config not provided).
      thinking_mode: Thinking mode (on/off/silent, default: ON).
      command_registry: Optional command registry for slash-commands.
      agent_definition: Pre-loaded AgentDefinition to use for system prompt.
      agent_path: Path to agent definition file (Markdown with frontmatter).
      context_manager: Optional ContextManager for conversation persistence.
      client: Optional AsyncClient for tools that need it (e.g., WebSearch).
      _recursion_depth: Internal parameter for subagent recursion tracking.
    """
    # Load environment variables from .env and .env.local
    # .env.local takes precedence over .env
    load_dotenv(Path(".env"))
    load_dotenv(Path(".env.local"))

    # Load environment variable configuration
    # Env vars have HIGHEST priority (even over explicit config parameter)
    from yoker.config import load_env_config, merge_configs

    env_overrides = load_env_config()

    # Load configuration (with auto-discovery)
    config_source: str
    discovered_path: Path | None = None

    if config is not None:
      # Merge env vars ON TOP of explicit config
      self._config = merge_configs(config, env_overrides) if env_overrides else config
      if env_overrides:
        log.info(
          "config_loaded",
          source="explicit_with_env",
          env_vars_count=len(env_overrides),
        )
      # Skip logging - caller (Agent) already logged config resolution
    elif config_path is not None:
      from yoker.config import load_config

      base_config = load_config(config_path)
      self._config = merge_configs(base_config, env_overrides) if env_overrides else base_config
      discovered_path = Path(config_path)
      log.info(
        "config_loaded",
        source="explicit_path_with_env" if env_overrides else "explicit_path",
        path=str(discovered_path),
        env_vars_count=len(env_overrides) if env_overrides else 0,
      )
    else:
      from yoker.config import discover_config

      base_config, discovered_path = discover_config()
      self._config = merge_configs(base_config, env_overrides) if env_overrides else base_config
      config_source = (
        "discovered_with_env" if env_overrides else "discovered" if discovered_path else "defaults"
      )
      log.info(
        "config_loaded",
        source=config_source,
        path=str(discovered_path) if discovered_path else None,
        env_vars_count=len(env_overrides) if env_overrides else 0,
      )

    # Validate configuration
    from yoker.config.validator import validate_config

    warnings = validate_config(self._config)
    for warning in warnings:
      log.warning("config_validation_warning", warning=warning)

    # Use provided model or config model
    self._model = model if model is not None else self._config.backend.ollama.model

    # Thinking mode state
    self._thinking_mode = thinking_mode

    # Command registry for slash-commands
    self._command_registry = command_registry

    # Resolve agent definition from config if not explicitly provided
    resolved_agent_path: Path | str | None = agent_path
    if agent_definition is None and agent_path is None:
      # Check if config has agents.definition
      if self._config.agents.definition:
        definition_path = Path(self._config.agents.definition).expanduser()
        if definition_path.exists():
          resolved_agent_path = definition_path
          log.info(
            "agent_definition_loaded",
            path=str(definition_path),
            source="config",
          )
        else:
          log.warning(
            "agent_definition_not_found",
            path=str(definition_path),
            fallback="default_prompt",
          )

    # Load agent definition if path provided
    self._agent_definition: AgentDefinition | None = None
    system_prompt = DEFAULT_SYSTEM_PROMPT

    if agent_definition is not None:
      self._agent_definition = agent_definition
      system_prompt = agent_definition.system_prompt or DEFAULT_SYSTEM_PROMPT
    elif resolved_agent_path is not None:
      from yoker.agents import load_agent_definition

      self._agent_definition = load_agent_definition(resolved_agent_path)
      system_prompt = self._agent_definition.system_prompt or DEFAULT_SYSTEM_PROMPT

    # Initialize path guardrail for filesystem tool validation
    from yoker.tools.path_guardrail import PathGuardrail

    self._guardrail: PathGuardrail = PathGuardrail(self._config)

    # Build tool registry filtered by agent definition
    self._tool_registry = self._build_tool_registry(client)

    # Initialize context manager
    if context_manager is not None:
      self._context = context_manager
    else:
      # Create default in-memory context manager
      from yoker.context import BasicPersistenceContextManager

      self._context = BasicPersistenceContextManager(
        storage_path=Path(self._config.context.storage_path),
        session_id=self._config.context.session_id,
      )

    # Add system prompt to context (skip if already exists, e.g., on resume)
    messages = self._context.get_messages()
    has_system = any(m.get("role") == "system" for m in messages)
    if not has_system:
      self._context.add_message("system", system_prompt)

    # Track recursion depth (internal, not exposed to LLM)
    # Validate recursion depth (SEC-6)
    max_depth = self._config.tools.agent.max_recursion_depth
    if _recursion_depth < 0:
      raise ValueError(f"_recursion_depth must be non-negative, got {_recursion_depth}")
    if _recursion_depth > max_depth:
      raise ValueError(
        f"_recursion_depth ({_recursion_depth}) exceeds max_recursion_depth ({max_depth})"
      )
    self._recursion_depth = _recursion_depth
    self._max_recursion_depth = max_depth

    # Event handlers storage
    self._event_handlers: list[EventCallback] = []

    # Skill registry (initially empty, populated by Agent)
    self._skill_registry: SkillRegistry | None = None

    # Verify guardrails are enforced (SEC-5)
    self._validate_guardrails_enforced()

    # Note: Logging happens in Agent after AgentTool is registered
    # This ensures the tool list is complete in the log

  @property
  def config(self) -> Config:
    """Configuration object."""
    return self._config

  @property
  def model(self) -> str:
    """Model name to use for chat."""
    return self._model

  @property
  def thinking_mode(self) -> ThinkingMode:
    """Current thinking mode state."""
    return self._thinking_mode

  @thinking_mode.setter
  def thinking_mode(self, value: ThinkingMode) -> None:
    """Set thinking mode state."""
    self._thinking_mode = value

  @property
  def agent_definition(self) -> "AgentDefinition | None":
    """Loaded agent definition, if any."""
    return self._agent_definition

  @property
  def tool_registry(self) -> ToolRegistry:
    """Registry of available tools."""
    return self._tool_registry

  @property
  def context(self) -> "ContextManager":
    """Context manager for conversation history."""
    return self._context

  @property
  def command_registry(self) -> "CommandRegistry | None":
    """Command registry for slash-commands."""
    return self._command_registry

  @property
  def skill_registry(self) -> "SkillRegistry | None":
    """Skill registry for skill definitions."""
    return self._skill_registry

  @skill_registry.setter
  def skill_registry(self, value: "SkillRegistry | None") -> None:
    """Set skill registry."""
    self._skill_registry = value

  @property
  def recursion_depth(self) -> int:
    """Current recursion depth (internal)."""
    return self._recursion_depth

  @property
  def max_recursion_depth(self) -> int:
    """Maximum allowed recursion depth."""
    return self._max_recursion_depth

  @property
  def guardrail(self) -> "PathGuardrail":
    """Path guardrail for filesystem tool validation."""
    return self._guardrail

  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler.

    Event handlers receive all events emitted during agent processing.
    Handlers can access potentially sensitive data (tool results, file contents).
    Only register handlers from trusted sources.

    Supports both sync and async handlers:
      - Sync handlers: def handler(event: Event) -> None
      - Async handlers: async def handler(event: Event) -> None

    Args:
      handler: Callable that receives Event objects.

    Example:
      def my_handler(event: Event):
          if isinstance(event, ContentChunkEvent):
              print(event.text, end='', flush=True)

      agent.add_event_handler(my_handler)

    Security Note:
      Handler registration is logged for audit purposes.
      Handlers should complete quickly (<100ms) to avoid blocking the event loop.
    """
    self._event_handlers.append(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler.

    Args:
      handler: The handler to remove.

    Raises:
      ValueError: If the handler is not registered.
    """
    self._event_handlers.remove(handler)

  def get_event_handlers(self) -> list[EventCallback]:
    """Get list of registered event handlers.

    Returns:
      Copy of the event handlers list.
    """
    return self._event_handlers.copy()

  def _build_tool_registry(self, client: "AsyncClient | None" = None) -> ToolRegistry:
    """Build a tool registry filtered by agent definition.

    If an agent definition is loaded, only registers tools listed in
    the agent's tools field. Otherwise, registers all default tools.

    All filesystem tools are created with the agent's guardrail injected
    for defense-in-depth validation.

    Args:
      client: Optional AsyncClient for tools that need it (e.g., WebSearch).

    Returns:
      ToolRegistry with available tools for this agent.
    """
    registry = ToolRegistry()

    # Create tools with guardrail injected for defense-in-depth
    tools: list[Tool] = [
      ReadTool(guardrail=self._guardrail),
      ListTool(guardrail=self._guardrail),
      WriteTool(guardrail=self._guardrail),
      UpdateTool(guardrail=self._guardrail),
      SearchTool(guardrail=self._guardrail),
      ExistenceTool(guardrail=self._guardrail),
      MkdirTool(guardrail=self._guardrail),
      GitTool(
        config=self._config.tools.git,
        guardrail=self._guardrail,
        permission_handlers=self._config.permissions.handlers,
      ),
      # AgentTool is added separately below (needs parent_agent reference)
    ]

    # Add WebSearchTool only if API key is available and client is provided
    if os.environ.get("OLLAMA_API_KEY") and client is not None:
      # Create guardrails with configuration from tool configs
      websearch_config = WebGuardrailConfig(
        max_query_length=self._config.tools.websearch.max_query_length,
        domain_allowlist=self._config.tools.websearch.domain_allowlist,
        domain_blocklist=self._config.tools.websearch.domain_blocklist,
        requests_per_minute=self._config.tools.websearch.requests_per_minute,
        requests_per_hour=self._config.tools.websearch.requests_per_hour,
        block_private_cidrs=self._config.tools.websearch.block_private_cidrs,
        timeout_seconds=self._config.tools.websearch.timeout_seconds,
      )
      tools.append(
        WebSearchTool(
          backend=OllamaWebSearchBackend(async_client=client),
          guardrail=WebGuardrail(config=websearch_config),
        )
      )
      webfetch_config = WebGuardrailConfig(
        domain_allowlist=self._config.tools.webfetch.domain_allowlist,
        domain_blocklist=self._config.tools.webfetch.domain_blocklist,
        block_private_cidrs=self._config.tools.webfetch.block_private_cidrs,
        require_https=self._config.tools.webfetch.require_https,
        timeout_seconds=self._config.tools.webfetch.timeout_seconds,
      )
      tools.append(
        WebFetchTool(
          backend=OllamaWebFetchBackend(async_client=client),
          guardrail=WebGuardrail(config=webfetch_config),
        )
      )
    else:
      log.warning("web_search_unavailable", reason="OLLAMA_API_KEY not set")
      log.warning("web_fetch_unavailable", reason="OLLAMA_API_KEY not set")

    # Filter by agent definition if present
    if self._agent_definition is not None:
      allowed_tools = {t.lower() for t in self._agent_definition.tools}
      for tool in tools:
        if tool.name.lower() in allowed_tools:
          registry.register(tool)
    else:
      for tool in tools:
        registry.register(tool)

    return registry

  def _validate_guardrails_enforced(self) -> None:
    """Verify all filesystem tools have guardrails.

    This is a defense-in-depth check to ensure security controls are in place.
    Raises an error if a filesystem tool is missing its guardrail.
    """
    for tool_name in _FILESYSTEM_TOOLS:
      tool = self._tool_registry.get(tool_name)
      if tool is not None:
        if not hasattr(tool, "_guardrail"):
          raise RuntimeError(
            f"Security error: Tool '{tool_name}' is missing guardrail. "
            "All filesystem tools must have guardrails injected."
          )


__all__ = ["AgentCore", "EventCallback", "DEFAULT_SYSTEM_PROMPT"]

