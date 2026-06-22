"""Plugin loader for Yoker.

Discovers and loads plugins from Python packages that expose a
`__YOKER_MANIFEST__` object in their top-level `__init__.py`.
"""

import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from structlog import get_logger

from yoker.agents.loader import load_agent_definitions
from yoker.exceptions import PluginError
from yoker.plugins.registration import register_agents, register_skills, register_tools
from yoker.plugins.security import check_plugin_allowed, check_plugins_enabled
from yoker.resources import find_package_subdirectory
from yoker.skills import load_skills

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.agents import AgentDefinition
  from yoker.config import Config

logger = get_logger(__name__)


@dataclass
class PluginComponents:
  """Container for plugin-discovered components."""

  tools: list[Any]
  skills: list[Any]
  agents: list[Any]
  source: str


def load_plugin(package_name: str) -> PluginComponents:
  """Load plugin components from a package.

  Packages must expose a top-level `__YOKER_MANIFEST__` object.

  Args:
    package_name: Python package name.

  Returns:
    PluginComponents if plugin exists and exposes a manifest.

  Raises:
    PluginError: If a plugin module exists but fails to load, doesn't exist or doesn't have a manifest.
  """
  try:
    package = importlib.import_module(package_name)
  except ImportError as e:
    raise PluginError(
      package=package_name,
      message=f"Plugin package '{package_name}' not found. Install it with: pip install {package_name}",
    ) from e
  except Exception as e:
    raise PluginError(
      package=package_name,
      message=f"Failed to import plugin package '{package_name}': {e}",
    ) from e

  if not hasattr(package, "__YOKER_MANIFEST__"):
    raise PluginError(
      package=package_name,
      message=f"Plugin package '{package_name}' doesn't provide a manifest."
    )

  logger.info("plugin_manifest_found", package=package_name)
  manifest = package.__YOKER_MANIFEST__
  tools = list(getattr(manifest, "tools", []))
  skills = _load_manifest_skills(manifest, package_name)
  agents = _load_manifest_agents(manifest, package_name)

  logger.info(
    "plugin_loaded",
    package=package_name,
    tools=len(tools),
    skills=len(skills),
    agents=len(agents),
  )
  return PluginComponents(
    tools=tools,
    skills=skills,
    agents=agents,
    source=package_name,
  )


def load_configured_plugins(
  agent: "Agent",
  config: "Config",
  extra_plugins: tuple[str, ...] = (),
) -> None:
  """Load configured and CLI-specified plugins into the agent's registries.

  Plugin tools, skills and agents are registered into ``agent.tools``,
  ``agent.skills`` and ``agent.agents`` respectively, namespaced by the
  plugin's package name. ``yoker`` itself is always included as a plugin.

  Args:
    agent: The Agent instance whose registries to populate.
    config: Resolved configuration (supplies ``config.plugins.packages``).
    extra_plugins: Additional plugin packages from the CLI beyond those
      declared in config.
  """
  if not check_plugins_enabled(config):
    logger.warning("plugins_disabled")
    return

  packages = config.plugins.packages + tuple(extra_plugins) + ("yoker",)
  logger.info("loading_plugins", packages=packages, count=len(packages))

  for package_name in packages:
    try:
      plugin = load_plugin(package_name)
    except PluginError as e:
      logger.error("plugin_load_failed", package=e.package, error=str(e))
      raise

    if not check_plugin_allowed(plugin.source, config, plugin):
      logger.warning("plugin_not_allowed", package=plugin.source)
      continue

    source = plugin.source
    if plugin.tools:
      register_tools(plugin.tools, agent.tools, namespace=source)
      logger.info("tools_registered", package=source, count=len(plugin.tools))

    if plugin.skills:
      register_skills(plugin.skills, agent.skills, namespace=source)
      logger.info("skills_registered", package=source, count=len(plugin.skills))

    if plugin.agents:
      register_agents(plugin.agents, agent.agents, namespace=source)
      logger.info("agents_registered", package=source, count=len(plugin.agents))


def _load_manifest_skills(manifest: Any, package_name: str) -> list[Any]:
  """Load skills declared in the manifest."""
  skills = list(getattr(manifest, "skills", []))
  skills_dir = getattr(manifest, "skills_dir", None)
  if not skills_dir:
    return skills
  path = find_package_subdirectory(package_name, skills_dir)
  if path:
    discovered = list(load_skills(path, namespace=package_name).values())
    if discovered:
      return skills + discovered
  return skills


def _load_manifest_agents(manifest: Any, package_name: str) -> list[Any]:
  """Load agents declared in the manifest."""
  agents = list(getattr(manifest, "agents", []))
  agents_dir = getattr(manifest, "agents_dir", None)
  if not agents_dir:
    return agents
  path = find_package_subdirectory(package_name, agents_dir)
  if path:
    discovered = list(load_agent_definitions(path, namespace=package_name).values())
    if discovered:
      return agents + discovered
  return agents


__all__ = [
  "PluginComponents",
  "load_plugin",
  "load_configured_plugins",
]
