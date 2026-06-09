"""Plugin system for Yoker.

Enables Python packages to provide tools, skills, and agents to yoker
via a standard plugin discovery and registration mechanism.

Key Components:
  - PluginManifest: Dataclass for declaring plugin components
  - PluginComponents: Container for loaded plugin components
  - load_plugin(): Load plugin from Python package
  - load_plugins(): Load multiple plugins
  - load_skills_from_package(): Load skills from package's skills/ directory
  - load_agents_from_package(): Load agents from package's agents/ directory
  - register_tools(): Register tools with namespace prefix
  - register_skills(): Register skills with namespace prefix
  - register_agents(): Register agents with namespace prefix

Built-in Plugin:
  The yoker package provides its own tools and skills as a built-in plugin
  with namespace "yoker". All built-in tools are registered as "yoker:read",
  "yoker:write", etc.

Example:
  # Load a plugin
  from yoker.plugins import load_plugin

  plugin = load_plugin("pkgq")
  if plugin:
      register_tools(plugin.tools, tool_registry, namespace=plugin.source)
      register_skills(plugin.skills, skill_registry, namespace=plugin.source)
"""

from yoker.plugins.builtin import AGENTS as BUILTIN_AGENTS
from yoker.plugins.builtin import SKILLS as BUILTIN_SKILLS
from yoker.plugins.builtin import TOOLS as BUILTIN_TOOLS
from yoker.plugins.builtin import load_builtin_plugin
from yoker.plugins.loader import (
  PluginComponents,
  load_agents_from_package,
  load_plugin,
  load_plugins,
  load_skills_from_package,
)
from yoker.plugins.manifest import PluginManifest
from yoker.plugins.registration import (
  register_agents,
  register_skills,
  register_tools,
)

__all__ = [
  # Manifest
  "PluginManifest",
  # Loader
  "PluginComponents",
  "load_plugin",
  "load_plugins",
  "load_skills_from_package",
  "load_agents_from_package",
  # Registration
  "register_tools",
  "register_skills",
  "register_agents",
  # Built-in
  "BUILTIN_TOOLS",
  "BUILTIN_SKILLS",
  "BUILTIN_AGENTS",
  "load_builtin_plugin",
]

