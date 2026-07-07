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
from yoker.plugins.security import check_plugin_allowed
from yoker.resources import find_package_subdirectory
from yoker.skills import load_skills
from yoker.tools.schema import ToolSpec, build_tool_spec

if TYPE_CHECKING:
  from yoker.config import Config

logger = get_logger(__name__)


@dataclass
class PluginComponents:
  """Container for plugin-discovered components."""

  tools: list[ToolSpec]
  skills: list[Any]
  agents: list[Any]
  source: str


def load_plugins(config: "Config", extra_plugins: tuple[str, ...] = ()):
  """Yield clean plugin components for configured and CLI-specified packages.

  Single plugin-loading entry point. Discovers plugins, applies the
  global-enabled gate (``config.plugins.enabled``) and the per-plugin
  security gate, then yields ``PluginComponents`` for registries to
  consume via their ``register_plugin_*`` methods.

  ``yoker`` is always loaded (trusted builtin); configured and CLI
  packages are added only when plugins are enabled.
  """
  packages = ["yoker"]  # always load yoker
  if config.plugins.enabled:
    packages.extend(config.plugins.packages)
    packages.extend(extra_plugins)

  for package_name in packages:
    try:
      plugin = load_plugin(package_name)
    except PluginError as e:
      logger.error("plugin_load_failed", package=e.package, error=str(e))
      raise

    # yoker builtin is always trusted; others require explicit allow
    if package_name == "yoker" or check_plugin_allowed(plugin, config):
      yield plugin


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
    return list(load_agent_definitions(path, namespace=package_name))
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
  "load_plugins",
  "load_skills_from_package",
  "load_agents_from_package",
]
