"""Plugin loading helpers for the Agent."""

from typing import TYPE_CHECKING, Any

from structlog import get_logger

from yoker.plugins import (
  check_plugin_allowed,
  check_plugins_enabled,
  register_agents,
  register_skills,
  register_tools,
)
from yoker.plugins import (
  load_plugins as load_configured_plugins,
)

if TYPE_CHECKING:
  from yoker.config import Config
  from yoker.plugins import PluginComponents

logger = get_logger(__name__)


def load_plugins(
  agent: Any,
  config: "Config",
  extra_plugins: tuple[str, ...] = (),
) -> None:
  """Load configured plugins into the agent's registries.

  Plugin tools, skills and agents are registered into ``agent.tools``,
  ``agent.skills`` and ``agent.agents`` respectively, namespaced by the
  plugin's package name. ``yoker`` itself is always included as a plugin
  (its manifest is currently empty; built-in tools are populated in a later
  step). Additional packages from the CLI (``--with``) are passed via
  ``extra_plugins`` since ``Config`` is frozen.

  Args:
    agent: The Agent instance whose registries to populate.
    config: Resolved configuration (supplies ``config.plugins.packages``).
    extra_plugins: Additional plugin packages from the CLI beyond those
      declared in config.
  """
  if not check_plugins_enabled(config):
    logger.warning("plugins disabled aborting")
    return

  packages = config.plugins.packages + tuple(extra_plugins) + ("yoker",)

  logger.info("loading_plugins", packages=packages, count=len(packages))
  loaded_plugins = _load_configured(packages)
  if loaded_plugins is None:
    return

  for plugin in loaded_plugins:
    if not check_plugin_allowed(plugin.source, config, plugin):
      logger.warning("plugin_not_allowed", package=plugin.source)
      continue
    _register_plugin_components(agent, plugin)


def _load_configured(plugin_packages: list[str]) -> list["PluginComponents"] | None:
  """Load configured plugins, logging errors without aborting."""
  try:
    return load_configured_plugins(plugin_packages)
  except ImportError as e:
    logger.error("plugin_import_error", error=str(e))
    return None
  except Exception as e:
    logger.error("plugin_load_error", error=str(e))
    return None


def _register_plugin_components(agent: Any, plugin: "PluginComponents") -> None:
  """Register tools, skills, and agents from a loaded plugin into the agent's registries."""
  source = plugin.source
  if plugin.tools:
    registered_tools = register_tools(plugin.tools, agent.tools, namespace=source)
    logger.info("plugin_tools_registered", package=source, tools=registered_tools)

  if plugin.skills:
    registered_skills = register_skills(plugin.skills, agent.skills, namespace=source)
    logger.info("plugin_skills_registered", package=source, skills=registered_skills)

  if plugin.agents:
    registered_agents = register_agents(plugin.agents, agent.agents, namespace=source)
    logger.info("plugin_agents_registered", package=source, agents=registered_agents)

  logger.info(
    "plugin_loaded",
    package=source,
    tools=len(plugin.tools),
    skills=len(plugin.skills),
    agents=len(plugin.agents),
  )
