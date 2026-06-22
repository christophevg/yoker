"""Built-in tools for Yoker.

These tools are registered by default when the yoker plugin is loaded.
"""

from yoker.builtin.agent import make_agent_tool
from yoker.builtin.existence import existence
from yoker.builtin.git import git
from yoker.builtin.list import list
from yoker.builtin.mkdir import mkdir
from yoker.builtin.read import read
from yoker.builtin.search import search
from yoker.builtin.skill import make_skill_tool
from yoker.builtin.update import update
from yoker.builtin.webfetch import webfetch
from yoker.builtin.websearch import websearch
from yoker.builtin.write import write
from yoker.plugins.manifest import PluginManifest

__all__ = [
  "existence",
  "git",
  "list",
  "mkdir",
  "read",
  "search",
  "update",
  "webfetch",
  "websearch",
  "write",
  "make_agent_tool",
  "make_skill_tool",
]

# Built-in Yoker plugin manifest.
# All built-in tools are registered here for discovery.
# Note: agent and skill tools use factory functions (make_agent_tool, make_skill_tool)
# because they need runtime dependencies (parent_agent, SkillRegistry).

__YOKER_MANIFEST__ = PluginManifest(
  tools=[existence, git, list, mkdir, read, search, update, webfetch, websearch, write],
  skills_dir="skills",
  agents_dir="agents",
)

__all__.append("__YOKER_MANIFEST__")