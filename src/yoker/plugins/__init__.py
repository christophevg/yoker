"""Plugin system for Yoker.

Enables Python packages to provide tools, skills, and agents to yoker
via a standard plugin discovery and registration mechanism.

Key Components:
  - PluginManifest: Dataclass for declaring plugin components
  - PluginComponents: Container for loaded plugin components
  - load_plugin(): Load plugin from Python package
  - load_plugins(): Load multiple plugins
  - load_agents_from_package(): Load agents from package's agents/ directory
  - load_skills_from_package(): Load skills from package's skills/ directory
  - register_tools(): Register tools with namespace prefix
  - register_skills(): Register skills with namespace prefix
  - register_agents(): Register agents with namespace prefix

Example:
  # Load a plugin
  from yoker.plugins import load_plugin

  plugin = load_plugin("pkgq")
  if plugin:
      register_tools(plugin.tools, tool_registry, namespace=plugin.source)
      register_skills(plugin.skills, skill_registry, namespace=plugin.source)
"""

from yoker.plugins.loader import (
  PluginComponents,
  load_plugin,
  load_plugins,
)
from yoker.plugins.loading import load_configured_plugins
from yoker.plugins.manifest import PluginManifest
from yoker.plugins.registration import (
  register_agents,
  register_skills,
  register_tools,
)
from yoker.plugins.security import (
  check_plugin_allowed,
  check_plugins_enabled,
  confirm_plugin,
  is_trusted,
  reset_session_trusted,
)

__all__ = [
  # Manifest
  "PluginManifest",
  # Loader
  "PluginComponents",
  "load_plugin",
  "load_plugins",
  "load_configured_plugins",
  # Registration
  "register_tools",
  "register_skills",
  "register_agents",
  # Security
  "is_trusted",
  "confirm_plugin",
  "check_plugins_enabled",
  "check_plugin_allowed",
  "reset_session_trusted",
]
