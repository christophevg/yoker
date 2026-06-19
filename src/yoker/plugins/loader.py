"""Plugin loader for Yoker.

Discovers and loads plugins from Python packages that expose a
`__YOKER_MANIFEST__` object in their top-level `__init__.py`.
"""

import importlib
from dataclasses import dataclass
from typing import Any

from structlog import get_logger

from yoker.exceptions import PluginError
from yoker.plugins.agents import load_agents_from_package
from yoker.plugins.skills import load_skills_from_package

log = get_logger(__name__)


@dataclass
class PluginComponents:
  """Container for plugin-discovered components."""

  tools: list[Any]
  skills: list[Any]
  agents: list[Any]
  source: str


def load_plugin(package_name: str) -> PluginComponents | None:
  """Load plugin components from a package.

  Packages must expose a top-level `__YOKER_MANIFEST__` object.

  Args:
    package_name: Python package name.

  Returns:
    PluginComponents if plugin exists and exposes a manifest.
    Returns None if the package is not installed or is not a Yoker plugin.

  Raises:
    PluginError: If a plugin module exists but fails to load.
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
    log.debug("plugin_manifest_not_found", package=package_name)
    return None

  log.info("plugin_manifest_found_in_package", package=package_name)
  return _load_from_module(package, package_name)


def _load_from_module(module: Any, package_name: str) -> PluginComponents:
  """Load plugin components from a module manifest."""
  manifest = module.__YOKER_MANIFEST__
  tools = list(getattr(manifest, "tools", []))
  skills = _load_manifest_skills(manifest, package_name)
  agents = _load_manifest_agents(manifest, package_name)

  log.info(
    "plugin_components_extracted",
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


def load_plugins(package_names: list[str]) -> list[PluginComponents]:
  """Load multiple plugins.

  Args:
    package_names: List of package names to load.

  Returns:
    List of successfully loaded PluginComponents.

  Raises:
    PluginError: If any plugin fails critically.
  """
  plugins: list[PluginComponents] = []
  for package_name in package_names:
    try:
      plugin = load_plugin(package_name)
      if plugin:
        plugins.append(plugin)
    except PluginError as e:
      log.error("plugin_load_failed", package=e.package, error=str(e))
      raise
  return plugins


__all__ = [
  "PluginComponents",
  "load_plugin",
  "load_plugins",
]
