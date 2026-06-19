"""Demo plugin manifest for Yoker.

Declares the tools, skills directory, and agents directory provided
by the demo plugin.
"""

from yoker.plugins import PluginManifest

from .tools import echo

__YOKER_MANIFEST__ = PluginManifest(
  tools=[echo],
  skills_dir="skills",
  agents_dir="agents",
)

__all__ = ["__YOKER_MANIFEST__", "echo"]
