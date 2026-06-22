"""Built-in tools for Yoker.

These tools are registered by default when the yoker plugin is loaded.
"""

from yoker.builtin.existence import existence
from yoker.builtin.list import list
from yoker.builtin.mkdir import mkdir
from yoker.builtin.read import read
from yoker.builtin.search import search
from yoker.plugins.manifest import PluginManifest

__all__ = [
  "existence",
  "list",
  "mkdir",
  "read",
  "search",
]

# Built-in Yoker plugin manifest.
#
# The filesystem tools are registered directly by the Agent via
# `yoker.agent.tools.build_tool_registry`, so they are not duplicated here.
# AgentTool and GitTool are also registered separately by the Agent because they
# require runtime dependencies (parent_agent and config).
#
# The built-in manifest remains available for future built-in components that
# are not hardcoded into the Agent.

__YOKER_MANIFEST__ = PluginManifest(
  tools=[existence, list, mkdir, read, search],
  skills_dir="skills",
  agents_dir="agents",
)

__all__ = ["__YOKER_MANIFEST__"]