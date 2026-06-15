"""Asynchronous Agent implementation for Yoker.

This module provides Agent, an async-first agent that chats with Ollama
and uses tools. All I/O operations are async.
"""

import inspect
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ollama import AsyncClient

from yoker.agent.core import AgentCore, EventCallback
from yoker.agent.processing import ProcessingMixin
from yoker.config import Config
from yoker.logging import get_logger
from yoker.skills import SkillRegistry
from yoker.thinking import ThinkingMode
from yoker.tools import ToolRegistry
from yoker.tools.agent import AgentTool

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.commands import CommandRegistry
  from yoker.context import ContextManager
  from yoker.tools.path_guardrail import PathGuardrail

log = get_logger(__name__)


def _load_agent_from_namespace_format(namespace_agent: str) -> "AgentDefinition | None":
  """Load an agent definition from namespace:agent format.

  Namespace format: <package>:<agent_name>
  Example: "yoker_plugin_demo:demo"

  Args:
    namespace_agent: Agent identifier in namespace:agent format.

  Returns:
    AgentDefinition if found, None if not found in any loaded plugin.
  """
  if ":" not in namespace_agent:
    return None

  parts = namespace_agent.split(":", 1)
  if len(parts) != 2:
    return None

  package, agent_name = parts
  log.info("loading_agent_from_namespace", package=package, agent_name=agent_name)

  from yoker.plugins import load_agents_from_package

  agents = load_agents_from_package(package, agents_dir="agents")

  for agent_def in agents:
    if agent_def.name == agent_name or agent_def.name == f"{package}:{agent_name}":
      log.info(
        "agent_loaded_from_namespace",
        package=package,
        agent_name=agent_name,
        full_name=agent_def.name,
      )
      return agent_def

  log.debug(
    "agent_not_found_in_namespace",
    package=package,
    agent_name=agent_name,
    available_agents=[a.name for a in agents],
  )
  return None


def _load_agent_from_plugin_url(plugin_url: str) -> "AgentDefinition":
  """Load an agent definition from a plugin:// URL.

  Plugin URL format: plugin://<package>/agents/<agent_name>

  Args:
    plugin_url: Plugin URL (e.g., "plugin://plugins.demo/agents/demo").

  Returns:
    AgentDefinition loaded from the plugin.

  Raises:
    ValueError: If URL format is invalid, plugin not found, or agent not found.
  """
  if not plugin_url.startswith("plugin://"):
    raise ValueError(f"Invalid plugin URL: {plugin_url}")

  path = plugin_url[9:]
  parts = path.split("/")

  if len(parts) < 3 or parts[1] != "agents":
    raise ValueError(
      f"Invalid plugin URL format: {plugin_url}. Expected: plugin://<package>/agents/<agent_name>"
    )

  package = parts[0]
  agent_name = parts[2]

  log.info("loading_agent_from_plugin", package=package, agent_name=agent_name)

  try:
    import importlib

    importlib.import_module(package)
  except ImportError as e:
    raise ValueError(f"Plugin package not found: {package}") from e

  from yoker.plugins import load_agents_from_package

  agents = load_agents_from_package(package, agents_dir="agents")

  for agent_def in agents:
    if agent_def.name == agent_name or agent_def.name == f"{package}:{agent_name}":
      log.info(
        "agent_loaded_from_plugin",
        package=package,
        agent_name=agent_name,
        full_name=agent_def.name,
      )
      return agent_def

  available_agents = [a.name for a in agents]
  raise ValueError(
    f"Agent '{agent_name}' not found in plugin '{package}'. Available agents: {available_agents}"
  )


class Agent(ProcessingMixin):
  """Asynchronous agent that chats with Ollama and uses tools.

  This implementation uses composition with AgentCore for shared state.
  All I/O operations are async.

  Attributes:
    client: AsyncClient for Ollama API communication.
    model: Model to use for chat.
    config: Configuration object.
    context: ContextManager for conversation history.
    thinking_mode: Current thinking mode (on/off/silent).
    agent_definition: Loaded agent definition (if provided).
    _recursion_depth: Current recursion depth (internal, for subagent tracking).
    _max_recursion_depth: Maximum allowed recursion depth (internal).
  """

  def __init__(
    self,
    config: "Config | None" = None,
    thinking_mode: ThinkingMode = ThinkingMode.ON,
    command_registry: "CommandRegistry | None" = None,
    agent_definition: "AgentDefinition | None" = None,
    agent_path: Path | str | None = None,
    context_manager: "ContextManager | None" = None,
    plugins: list[str] | None = None,
    _recursion_depth: int = 0,
  ) -> None:
    """Initialize the async agent.

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

    Plugin Loading:
        1. Built-in plugin (yoker) is always loaded first
        2. Config-specified plugins from config.plugins.packages
        3. Override plugins from `plugins` parameter (if provided)

    Args:
      config: Configuration object (uses Clevis auto-discovery if not provided).
      thinking_mode: Thinking mode (on/off/silent, default: ON).
      command_registry: Optional command registry for slash-commands.
      agent_definition: Pre-loaded AgentDefinition to use for system prompt.
      agent_path: Path to agent definition file (Markdown with frontmatter).
      context_manager: Optional ContextManager for conversation persistence.
      plugins: Optional list of plugin packages to load (overrides config).
      _recursion_depth: Internal parameter for subagent recursion tracking.
    """
    from yoker.config import get_yoker_config

    loaded_config = config if config is not None else get_yoker_config(cli=False)

    config_source = "explicit" if config is not None else "discovered"
    log.info("config_loaded", source=config_source)

    resolved_agent_path: Path | str | None = agent_path
    resolved_agent_definition: AgentDefinition | None = agent_definition

    if agent_definition is not None:
      resolved_agent_path = None
      log.info(
        "agent_definition_provided",
        name=agent_definition.name,
      )
    elif agent_path is not None:
      if not str(agent_path).startswith("plugin://"):
        path = Path(agent_path)
        if not path.exists():
          raise ValueError(f"Agent definition file not found: {agent_path}")

      if str(agent_path).startswith("plugin://"):
        plugin_url = str(agent_path)
        resolved_agent_definition = _load_agent_from_plugin_url(plugin_url)
        resolved_agent_path = None
        log.info(
          "agent_definition_loaded_from_plugin",
          url=plugin_url,
          name=resolved_agent_definition.name,
        )
      else:
        from yoker.agents import load_agent_definition

        resolved_agent_definition = load_agent_definition(agent_path)
        log.info(
          "agent_definition_loaded_from_file",
          path=str(agent_path),
          name=resolved_agent_definition.name,
        )
    else:
      if loaded_config.agents.definition:
        definition_value = loaded_config.agents.definition

        if definition_value.startswith("plugin://"):
          resolved_agent_definition = _load_agent_from_plugin_url(definition_value)
          log.info(
            "agent_definition_loaded_from_plugin_url",
            url=definition_value,
            name=resolved_agent_definition.name,
          )
        elif ":" in definition_value and not Path(definition_value).exists():
          resolved_agent_definition = _load_agent_from_namespace_format(definition_value)
          if resolved_agent_definition:
            log.info(
              "agent_definition_loaded_from_namespace",
              definition=definition_value,
              name=resolved_agent_definition.name,
            )
          else:
            raise ValueError(f"Agent definition file not found: {definition_value}")
        else:
          definition_path = Path(definition_value).expanduser()
          if definition_path.exists():
            from yoker.agents import load_agent_definition

            resolved_agent_definition = load_agent_definition(definition_path)
            log.info(
              "agent_definition_loaded_from_config",
              path=str(definition_path),
              name=resolved_agent_definition.name,
            )
          else:
            raise ValueError(f"Agent definition file not found: {definition_value}")

    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key:
      self._client = AsyncClient(
        host="https://ollama.com", headers={"Authorization": f"Bearer {api_key}"}
      )
      log.info("async_ollama_client_initialized", host="ollama.com", auth="api_key")
    else:
      base_url = loaded_config.backend.ollama.base_url
      self._client = AsyncClient(host=base_url)
      log.info("async_ollama_client_initialized", host=base_url, auth="none")

    self._core = AgentCore(
      config=loaded_config,
      thinking_mode=thinking_mode,
      command_registry=command_registry,
      agent_definition=resolved_agent_definition,
      agent_path=resolved_agent_path,
      context_manager=context_manager,
      client=self._client,
      _recursion_depth=_recursion_depth,
    )

    if self._core.agent_definition is not None:
      allowed_tools = {t.lower() for t in self._core.agent_definition.tools}
      if "agent" in allowed_tools:
        self._core.tool_registry.register(
          AgentTool(guardrail=self._core.guardrail, parent_agent=self)
        )
    else:
      self._core.tool_registry.register(
        AgentTool(guardrail=self._core.guardrail, parent_agent=self)
      )

    self._load_plugins(loaded_config, plugins)

    from yoker.skills import SkillRegistry, load_skills

    if self._core.skill_registry is None:
      self._core.skill_registry = SkillRegistry()

    for directory in loaded_config.skills.directories:
      try:
        skills = load_skills(directory)
        for _skill_name, skill in skills.items():
          self._core.skill_registry.register(skill)
        log.info("skills_loaded", count=len(skills), source=directory)
      except Exception as e:
        log.warning("skills_directory_load_failed", directory=directory, error=str(e))

    if self._core.skill_registry.count > 0 and loaded_config.skills.discovery:
      from yoker.skills import format_discovery_block

      skill_list = self._core.skill_registry.list_skills()
      discovery_block = format_discovery_block(skill_list)
      self.context.add_message("system", discovery_block)
      log.info("skill_discovery_added", skill_count=len(skill_list))

    if loaded_config.tools.skill.enabled:
      from yoker.tools import SkillTool

      self._core.tool_registry.register(SkillTool(skill_registry=self._core.skill_registry))
      log.info("skill_tool_registered")

    log.info(
      "async_agent_initialized",
      model=self.model,
      thinking_mode=self.thinking_mode.value,
      has_agent_definition=self.agent_definition is not None,
      available_tools=self.tool_registry.names,
    )

  @property
  def config(self) -> "Config":
    """Configuration object."""
    return self._core.config

  @property
  def model(self) -> str:
    """Model name to use for chat."""
    return self._core.model

  @property
  def thinking_mode(self) -> ThinkingMode:
    """Current thinking mode state."""
    return self._core.thinking_mode

  @thinking_mode.setter
  def thinking_mode(self, value: ThinkingMode) -> None:
    """Set thinking mode state."""
    self._core.thinking_mode = value

  @property
  def agent_definition(self) -> "AgentDefinition | None":
    """Loaded agent definition, if any."""
    return self._core.agent_definition

  @property
  def tool_registry(self) -> ToolRegistry:
    """Registry of available tools."""
    return self._core.tool_registry

  @property
  def context(self) -> "ContextManager":
    """Context manager for conversation history."""
    return self._core.context

  @property
  def command_registry(self) -> "CommandRegistry | None":
    """Command registry for slash-commands."""
    return self._core.command_registry

  @property
  def skill_registry(self) -> "SkillRegistry | None":
    """Skill registry for skill definitions."""
    return self._core.skill_registry

  @property
  def _recursion_depth(self) -> int:
    """Current recursion depth (internal)."""
    return self._core.recursion_depth

  @property
  def _max_recursion_depth(self) -> int:
    """Maximum allowed recursion depth."""
    return self._core.max_recursion_depth

  @property
  def _event_handlers(self) -> list[EventCallback]:
    """Event handlers storage (internal)."""
    return self._core._event_handlers

  @property
  def client(self) -> AsyncClient:
    """AsyncClient for Ollama API communication."""
    return self._client

  @property
  def _guardrail(self) -> "PathGuardrail":
    """Path guardrail for filesystem tool validation."""
    return self._core.guardrail

  def _load_plugins(
    self,
    config: "Config",
    plugins_override: list[str] | None = None,
  ) -> None:
    """Load built-in and configured plugins.

    Args:
      config: Configuration object.
      plugins_override: Optional list of plugins to load (overrides config).
    """
    from yoker.plugins import (
      BUILTIN_AGENTS,
      BUILTIN_SKILLS,
      BUILTIN_TOOLS,
      check_plugin_allowed,
      check_plugins_enabled,
      load_plugins,
      register_agents,
      register_skills,
      register_tools,
    )

    plugin_packages = plugins_override if plugins_override is not None else config.plugins.packages

    log.info(
      "plugin_loading_started",
      has_override=plugins_override is not None,
      packages=plugin_packages if plugin_packages else [],
    )

    log.info("loading_builtin_plugin")
    print("Loading built-in plugin: yoker")

    for tool in BUILTIN_TOOLS:
      namespaced_name = f"yoker:{tool.name}"
      from yoker.plugins.registration import _clone_tool_with_name

      namespaced_tool = _clone_tool_with_name(tool, namespaced_name)
      self.tool_registry.register(namespaced_tool)

    log.info(
      "builtin_tools_registered",
      count=len(BUILTIN_TOOLS),
      tools=[f"yoker:{t.name}" for t in BUILTIN_TOOLS],
    )

    for skill in BUILTIN_SKILLS:
      from dataclasses import fields as dataclass_fields

      from yoker.skills import Skill

      field_values = {f.name: getattr(skill, f.name) for f in dataclass_fields(skill)}
      field_values["namespace"] = "yoker"
      namespaced_skill = Skill(**field_values)

      if self._core.skill_registry is None:
        self._core.skill_registry = SkillRegistry()

      self._core.skill_registry.register(namespaced_skill)

    log.info(
      "builtin_skills_registered",
      count=len(BUILTIN_SKILLS),
      skills=[f"yoker:{s.name}" for s in BUILTIN_SKILLS],
    )

    for _agent_def in BUILTIN_AGENTS:
      pass

    log.info(
      "builtin_agents_registered",
      count=len(BUILTIN_AGENTS),
      agents=[f"yoker:{a.name}" for a in BUILTIN_AGENTS] if BUILTIN_AGENTS else [],
    )

    if not plugin_packages:
      log.info("no_plugins_configured")
      return

    if not check_plugins_enabled(config):
      log.warning("plugins_disabled_aborting")
      return

    log.info("loading_plugins", packages=list(plugin_packages), count=len(plugin_packages))

    try:
      loaded_plugins = load_plugins(list(plugin_packages))
    except ImportError as e:
      print(f"  Error: Failed to load plugins: {e}")
      log.error("plugin_import_error", error=str(e))
      return
    except Exception as e:
      print(f"  Error: Failed to load plugins: {e}")
      log.error("plugin_load_error", error=str(e))
      return

    for plugin in loaded_plugins:
      print(f"Loading plugin: {plugin.source}")

      if not check_plugin_allowed(plugin.source, config, plugin):
        print(f"  Plugin '{plugin.source}' not loaded.")
        log.warning("plugin_not_allowed", package=plugin.source)
        continue

      if plugin.tools:
        registered_tools = register_tools(
          plugin.tools,
          self.tool_registry,
          namespace=plugin.source,
        )
        from yoker.plugins.registration import _clone_tool_with_name

        for tool, namespaced_name in zip(plugin.tools, registered_tools, strict=True):
          namespaced_tool = _clone_tool_with_name(tool, namespaced_name)
          self._core.add_plugin_tool(namespaced_tool)
        log.info(
          "plugin_tools_registered",
          package=plugin.source,
          tools=registered_tools,
        )

      if plugin.skills:
        if self._core.skill_registry is None:
          self._core.skill_registry = SkillRegistry()

        registered_skills = register_skills(
          plugin.skills,
          self._core.skill_registry,
          namespace=plugin.source,
        )
        log.info(
          "plugin_skills_registered",
          package=plugin.source,
          skills=registered_skills,
        )

      if plugin.agents:
        registered_agents = register_agents(
          plugin.agents,
          namespace=plugin.source,
        )
        for agent_def in plugin.agents:
          self._core.add_plugin_agent(agent_def)
        log.info(
          "plugin_agents_registered",
          package=plugin.source,
          agents=registered_agents,
        )

      print(
        f"  Loaded plugin {plugin.source}: {len(plugin.tools)} tools, {len(plugin.skills)} skills, {len(plugin.agents)} agents"
      )

      log.info(
        "plugin_loaded",
        package=plugin.source,
        tools=len(plugin.tools),
        skills=len(plugin.skills),
        agents=len(plugin.agents),
      )

  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler.

    Args:
      handler: Callable that receives Event objects.
    """
    handler_name = getattr(handler, "__name__", str(handler))
    call_fn = getattr(handler, "__call__", handler)  # noqa: B004
    log.info(
      "handler_registered",
      handler=handler_name,
      is_async=inspect.iscoroutinefunction(call_fn),
    )
    self._core.add_event_handler(handler)

  def remove_event_handler(self, handler: EventCallback) -> None:
    """Remove a registered event handler.

    Args:
      handler: The handler to remove.

    Raises:
      ValueError: If the handler is not registered.
    """
    self._core.remove_event_handler(handler)


__all__ = ["Agent"]
