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
from yoker.tools.schema import ToolSpec, build_tool_spec

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.config import Config

logger = get_logger(__name__)


@dataclass
class PluginComponents:
  """Container for plugin-discovered components."""

  tools: list[ToolSpec]
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
      package=package_name, message=f"Plugin package '{package_name}' doesn't provide a manifest."
    )

  logger.info("plugin_manifest_found", package=package_name)
  manifest = package.__YOKER_MANIFEST__
  tools_raw = list(getattr(manifest, "tools", []))
  skills = _load_manifest_skills(manifest, package_name)
  agents = _load_manifest_agents(manifest, package_name)

  # Parse tools into ToolSpec objects during load (consistent with skills/agents)
  tools = [build_tool_spec(tool, namespace=package_name) for tool in tools_raw]

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
  plugins_enabled = check_plugins_enabled(config)
  if not plugins_enabled:
    logger.warning("plugins_disabled")

  # Always load yoker builtin plugin (essential for agent operation)
  # even when external plugins are disabled
  packages = ["yoker"]

  # Add configured and CLI plugins only if plugins are enabled
  if plugins_enabled:
    packages.extend(config.plugins.packages)
    packages.extend(extra_plugins)

  logger.info("loading_plugins", packages=packages, count=len(packages))

  for package_name in packages:
    try:
      plugin = load_plugin(package_name)
    except PluginError as e:
      logger.error("plugin_load_failed", package=e.package, error=str(e))
      raise

    # Skip security check for yoker builtin (always trusted)
    if package_name != "yoker" and not check_plugin_allowed(plugin.source, config, plugin):
      logger.warning("plugin_not_allowed", package=plugin.source)
      continue

    source = plugin.source
    if plugin.tools:
      # Filter tools based on enabled flag in config
      enabled_tools = _filter_enabled_tools(plugin.tools, config, source)
      register_tools(enabled_tools, agent.tools, namespace=source)
      logger.info("tools_registered", package=source, count=len(enabled_tools))

    if plugin.skills:
      register_skills(plugin.skills, agent.skills, namespace=source)
      logger.info("skills_registered", package=source, count=len(plugin.skills))

    if plugin.agents:
      register_agents(plugin.agents, agent.agents, namespace=source)
      logger.info("agents_registered", package=source, count=len(plugin.agents))


def load_skills_from_package(package_name: str, skills_dir: str) -> list[Any]:
  """Load skills from a package's skills directory.

  Args:
    package_name: Python package name.
    skills_dir: Directory name within the package (e.g., "skills").

  Returns:
    List of loaded skills.
  """
  path = find_package_subdirectory(package_name, skills_dir)
  if path:
    return list(load_skills(path, namespace=package_name).values())
  # Warn if skills_dir was specified but directory doesn't exist
  logger.warning(
    "plugin_skills_dir_not_found",
    package=package_name,
    skills_dir=skills_dir,
  )
  return []


def load_agents_from_package(package_name: str, agents_dir: str) -> list[Any]:
  """Load agents from a package's agents directory.

  Args:
    package_name: Python package name.
    agents_dir: Directory name within the package (e.g., "agents").

  Returns:
    List of loaded agents.
  """
  path = find_package_subdirectory(package_name, agents_dir)
  if path:
    return list(load_agent_definitions(path, namespace=package_name).values())
  return []


def _load_manifest_skills(manifest: Any, package_name: str) -> list[Any]:
  """Load skills declared in the manifest."""
  skills = list(getattr(manifest, "skills", []))
  skills_dir = getattr(manifest, "skills_dir", None)
  if not skills_dir:
    return skills
  discovered = load_skills_from_package(package_name, skills_dir)
  if discovered:
    return skills + discovered
  return skills


def _filter_enabled_tools(
  tools: list[ToolSpec],
  config: "Config",
  namespace: str,
) -> list[ToolSpec]:
  """Filter tools based on their enabled flag in config.

  For built-in yoker tools, check config.tools.<name>.enabled.
  Plugin tools are always enabled (no config control).

  WebSearch and WebFetch tools require an API key to be configured
  (config.backend.ollama.api_key) in addition to being enabled.

  Args:
    tools: List of ToolSpec objects.
    config: Configuration to check enabled flags.
    namespace: Tool namespace (e.g., "yoker" for built-in tools).

  Returns:
    List of enabled ToolSpec objects.
  """
  # Only filter built-in yoker tools
  if namespace != "yoker":
    return tools

  # Map tool simple names to config attribute names
  tool_config_map = {
    "list": "list",
    "read": "read",
    "write": "write",
    "update": "update",
    "search": "search",
    "agent": "agent",
    "git": "git",
    "mkdir": "mkdir",
    "existence": "existence",
    "websearch": "websearch",
    "webfetch": "webfetch",
    "skill": "skill",
  }

  # Tools that require API key for functionality
  api_key_required_tools = {"websearch", "webfetch"}

  enabled_tools = []
  for tool_spec in tools:
    tool_name = tool_spec.simple_name
    # simple_name should never be None for ToolSpec (set during build_tool_spec)
    # but we check for type safety
    if tool_name is None:
      # Skip tools without a name (shouldn't happen in practice)
      continue

    config_attr = tool_config_map.get(tool_name)

    if config_attr is None:
      # Tool not in config map, include by default (e.g., agent, skill tools)
      enabled_tools.append(tool_spec)
      continue

    # Type narrowing: config_attr is str after None check
    assert config_attr is not None  # For mypy
    tool_config = getattr(config.tools, config_attr, None)
    if tool_config is None:
      # No config for this tool, include by default
      enabled_tools.append(tool_spec)
      continue

    if not tool_config.enabled:
      logger.info("tool_disabled_by_config", tool=tool_name, namespace=namespace)
      continue

    # WebSearch and WebFetch require API key
    if tool_name in api_key_required_tools:
      if not config.backend.ollama.api_key:
        logger.info(
          "tool_disabled_no_api_key",
          tool=tool_name,
          namespace=namespace,
        )
        continue

    enabled_tools.append(tool_spec)

  return enabled_tools


def _load_manifest_agents(manifest: Any, package_name: str) -> list[Any]:
  """Load agents declared in the manifest."""
  agents = list(getattr(manifest, "agents", []))
  agents_dir = getattr(manifest, "agents_dir", None)
  if not agents_dir:
    return agents
  discovered = load_agents_from_package(package_name, agents_dir)
  if discovered:
    return agents + discovered
  return agents


__all__ = [
  "PluginComponents",
  "load_plugin",
  "load_configured_plugins",
  "load_skills_from_package",
  "load_agents_from_package",
]
