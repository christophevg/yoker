"""Built-in Yoker plugin providing standard tools and skills.

This module exports the standard tools and skills that come with yoker
as a plugin. All built-in components use the "yoker" namespace prefix.

Example:
    # Load built-in plugin in Agent initialization
    from yoker.plugins.builtin import load_builtin_plugin

    tools, skills = load_builtin_plugin(config)

    # Register with namespaces
    register_tools(tools, tool_registry, namespace="yoker")
    register_skills(skills, skill_registry, namespace="yoker")

The built-in plugin provides:
    - Tools: read, list, write, update, search, existence, mkdir, agent
    - Skills: (no built-in skills, loaded from configuration)
"""

from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger

if TYPE_CHECKING:
  from yoker.config import Config
  from yoker.skills import Skill
  from yoker.tools import Tool

log = get_logger(__name__)


def load_builtin_plugin(config: "Config | None" = None) -> tuple[list["Tool"], list["Skill"]]:
  """Load built-in yoker plugin (standard tools).

  This function creates instances of all built-in tools with the provided
  configuration. Built-in tools are registered with the "yoker" namespace.

  Note: AgentTool and GitTool are NOT included here because:
    - AgentTool needs parent_agent (set during Agent initialization)
    - GitTool needs config for allowed_operations (set during Agent initialization)

  Args:
    config: Configuration object (optional, uses defaults if not provided).

  Returns:
    Tuple of (tools, skills) lists.

  Example:
      tools, skills = load_builtin_plugin(config)
      register_tools(tools, registry, namespace="yoker")
  """
  # Import tools - only basic filesystem tools that don't need special setup
  from yoker.tools import (
    ExistenceTool,
    ListTool,
    MkdirTool,
    ReadTool,
    SearchTool,
    UpdateTool,
    WriteTool,
  )

  # Create tool instances
  tools: list[Tool] = [
    ReadTool(),
    ListTool(),
    WriteTool(),
    UpdateTool(),
    SearchTool(),
    ExistenceTool(),
    MkdirTool(),
    # Note: AgentTool and GitTool are added separately during Agent initialization
    # because they need configuration or parent_agent
  ]

  # Skills: Built-in skills loaded from configuration, not hardcoded
  # Skills are loaded from configured directories (yoker.toml) or
  # environment variable (YOKER_SKILLS_PATH)
  skills: list[Skill] = []

  log.info(
    "builtin_plugin_loaded",
    tools=len(tools),
    skills=len(skills),
  )

  return tools, skills


# Module-level exports for direct access
# These are used by the plugin loader to get components
TOOLS: list["Tool"] = []
SKILLS: list["Skill"] = []
# AGENTS: Future use - type would require forward reference to AgentDefinition
# which doesn't exist in TYPE_CHECKING block, so we use list[Any]
AGENTS: list[Any] = []  # Future: standard agents


def get_builtin_tools(config: "Config | None" = None) -> list["Tool"]:
  """Get built-in tool instances.

  This is a convenience function for getting built-in tools without
  the full plugin loading mechanism.

  Args:
    config: Configuration object (optional).

  Returns:
    List of Tool instances.
  """
  tools, _ = load_builtin_plugin(config)
  return tools


def get_builtin_skills() -> list["Skill"]:
  """Get built-in skill instances.

  Built-in skills are loaded from configuration directories,
  not hardcoded. This function returns an empty list and is
  provided for API consistency.

  Returns:
    Empty list (skills loaded from config directories).
  """
  return []


__all__ = [
  "load_builtin_plugin",
  "get_builtin_tools",
  "get_builtin_skills",
  "TOOLS",
  "SKILLS",
  "AGENTS",
]
