"""Shared state and utilities for the async Agent.

This module provides AgentCore, a composition class that holds shared state
and utilities for the async-only Agent implementation.

.. warning::
  This class is for internal use. Use Agent instead.
"""

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from yoker.agent.tools import build_tool_registry
from yoker.config import Config
from yoker.logging import get_logger
from yoker.thinking import ThinkingMode
from yoker.tools import Tool, ToolRegistry

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
    config: Config | None = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    command_registry: "CommandRegistry | None" = None,
    agent_definition: "AgentDefinition | None" = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    client: "AsyncClient | None" = None,
    _recursion_depth: int = 0,
  ) -> None:
    """Initialize shared agent state.

    Config Resolution:
        Configuration is loaded using Clevis which handles:
        - Environment variables (YOKER_* prefix)
        - User config (~/.yoker.toml)
        - Project config (./yoker.toml)
        - Default values from Config dataclass

    Agent Definition Resolution (in order of precedence):
        1. Explicit `agent_definition` parameter
        2. Explicit `agent_path` parameter
        3. Config's `agents.definition` (if set and file exists)
        4. None (default system prompt)

    Args:
      config: Configuration object (uses Clevis auto-discovery if not provided).
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

    # Load configuration using Clevis (handles env vars, user config, project config)
    # Clevis handles environment variable interpolation via envtoml/tomlev
    from yoker.config import get_yoker_config

    # Use cli=False for library mode (no CLI argument parsing)
    self._config = config if config is not None else get_yoker_config(cli=False)
    config_source = "explicit" if config is not None else "discovered"
    log.info("config_loaded", source=config_source)

    # Validation happens automatically in Config.__post_init__

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

    # Set model: agent definition overrides config
    if self._agent_definition is not None and self._agent_definition.model is not None:
      self._model = self._agent_definition.model
      log.info(
        "model_from_agent_definition",
        model=self._model,
        agent=self._agent_definition.name,
      )
    else:
      self._model = self._config.backend.ollama.model
      log.info("model_from_config", model=self._model)

    # Initialize path guardrail for filesystem tool validation
    from yoker.tools.path_guardrail import PathGuardrail

    self._guardrail: PathGuardrail = PathGuardrail(self._config)

    # Build tool registry filtered by agent definition
    self._tool_registry = build_tool_registry(
      self._config,
      self._guardrail,
      agent_definition=self._agent_definition,
      client=client,
    )

    # Initialize context manager
    if context_manager is not None:
      self._context = context_manager
    else:
      # Create default in-memory context manager
      from yoker.context import BasicContextManager

      self._context = BasicContextManager()

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

    # Plugin tools tracking (populated by Agent during plugin loading)
    self._plugin_tools: list[Tool] = []

    # Plugin agents tracking (populated by Agent during plugin loading)
    self._plugin_agents: list[AgentDefinition] = []

    # Verify guardrails are enforced (SEC-5)
    self._validate_guardrails_enforced()

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

  @property
  def plugin_tools(self) -> list[Tool]:
    """List of loaded plugin tools.

    Returns:
      List of Tool instances from loaded plugins.
    """
    return self._plugin_tools

  def add_plugin_tool(self, tool: Tool) -> None:
    """Add a plugin tool to the known tools list.

    Args:
      tool: Tool instance from a plugin.
    """
    self._plugin_tools.append(tool)

  @property
  def plugin_agents(self) -> list["AgentDefinition"]:
    """List of loaded plugin agents.

    Returns:
      List of AgentDefinition instances from loaded plugins.
    """
    return self._plugin_agents

  def add_plugin_agent(self, agent_def: "AgentDefinition") -> None:
    """Add a plugin agent to the known agents list.

    Args:
      agent_def: AgentDefinition instance from a plugin.
    """
    self._plugin_agents.append(agent_def)

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

  def get_known_tools(self) -> list[Tool]:
    """Get list of all known built-in tools.

    Returns list of tool instances for all built-in tools (without
    namespace prefixes). Plugin tools are tracked separately in Agent.

    Only includes tools that are enabled in config.

    Returns:
      List of Tool instances for built-in tools.
    """
    from yoker.tools import (
      ExistenceTool,
      ListTool,
      MkdirTool,
      ReadTool,
      SearchTool,
      SkillTool,
      UpdateTool,
      WriteTool,
    )

    tools: list[Tool] = []

    if self._config.tools.read.enabled:
      tools.append(ReadTool())

    if self._config.tools.list.enabled:
      tools.append(ListTool())

    if self._config.tools.write.enabled:
      tools.append(WriteTool())

    if self._config.tools.update.enabled:
      tools.append(UpdateTool())

    if self._config.tools.search.enabled:
      tools.append(SearchTool())

    if self._config.tools.existence.enabled:
      tools.append(ExistenceTool())

    if self._config.tools.mkdir.enabled:
      tools.append(MkdirTool())

    # Add SkillTool only if skill tool is enabled and registry exists
    if self._config.tools.skill.enabled and self._skill_registry is not None:
      tools.append(SkillTool(skill_registry=self._skill_registry))

    return tools

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
