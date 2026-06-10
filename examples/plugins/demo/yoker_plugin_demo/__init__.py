"""Demo plugin manifest for Yoker.

Declares the tools, skills directory, and agents directory provided
by the demo plugin.
"""

from yoker.plugins import PluginManifest

from .tools import EchoTool

__YOKER_MANIFEST__ = PluginManifest(
  tools=[EchoTool()],
  skills_dir="skills",
  agents_dir="agents",
)

__all__ = ["__YOKER_MANIFEST__", "EchoTool"]