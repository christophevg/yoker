"""Demo plugin manifest for Yoker.

Declares the tools, skills directory, and agents directory provided
by the demo plugin, plus the plugin's typed tool configuration class
(TODO 7.2): Yoker augments its config schema with one
``[tools.yoker_plugin_demo.<tool>]`` table per tool declared here.
"""

from yoker.plugins import PluginManifest

from .tools import DemoPluginConfig, EchoToolConfig, echo

__YOKER_MANIFEST__ = PluginManifest(
  tools=[echo],
  config_class=DemoPluginConfig,
  skills_dir="skills",
  agents_dir="agents",
)

__all__ = ["__YOKER_MANIFEST__", "DemoPluginConfig", "EchoToolConfig", "echo"]
