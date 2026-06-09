"""Demo plugin manifest for Yoker.

Declares the tools, skills directory, and agents directory provided
by the demo plugin.
"""

from typing import Any

from yoker.plugins import PluginManifest

from .tools import EchoTool

# Manifest for future use (when loader supports it)
__YOKER_MANIFEST__ = PluginManifest(
  tools=[EchoTool()],
  skills_dir="skills",
  agents_dir="agents",
)

# Module-level exports for current plugin loader
TOOLS: list[Any] = [EchoTool()]
SKILLS: list[Any] = []  # Skills loaded from skills/ directory
AGENTS: list[Any] = []  # Agents loaded from agents/ directory

__all__ = ["__YOKER_MANIFEST__", "EchoTool", "TOOLS", "SKILLS", "AGENTS"]