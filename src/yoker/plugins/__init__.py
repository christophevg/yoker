"""Plugin system for Yoker.

Enables Python packages to provide tools, skills, and agents to yoker
via a standard plugin discovery and registration mechanism.

Key Components:
  - PluginManifest: Dataclass for declaring plugin components
  - PluginComponents: Container for loaded plugin components
  - load_plugin(): Load plugin from Python package
  - load_plugins(): Single entry point — yields clean PluginComponents
    after global-enabled and per-plugin security gating. Registries
    consume the output via their ``register_plugin_*`` methods.

Registries own registration:
  - ToolRegistry.register_plugin_tools(plugins, config)
  - SkillRegistry.register_plugin_skills(plugins)
  - AgentRegistry.register_plugin_agents(config, extra_plugins)
"""

from yoker.plugins.file_manifest import (
  FileManifestResult,
  PluginConfig,
  RunConfig,
  load_file_manifest,
)
from yoker.plugins.loader import (
  PluginComponents,
  load_agents_from_package,
  load_plugin,
  load_plugins,
  load_skills_from_package,
)
from yoker.plugins.manifest import PluginManifest
from yoker.plugins.security import (
  check_plugin_allowed,
  confirm_plugin,
  is_trusted,
  reset_session_trusted,
  warn_plugins_disabled,
)

__all__ = [
  # Manifest
  "PluginManifest",
  # File-based manifest (agent.toml)
  "FileManifestResult",
  "PluginConfig",
  "RunConfig",
  "load_file_manifest",
  # Loader
  "PluginComponents",
  "load_plugin",
  "load_plugins",
  "load_skills_from_package",
  "load_agents_from_package",
  # Security
  "is_trusted",
  "confirm_plugin",
  "check_plugin_allowed",
  "reset_session_trusted",
  "warn_plugins_disabled",
]
