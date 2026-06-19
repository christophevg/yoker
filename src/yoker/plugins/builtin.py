"""Built-in Yoker plugin manifest.

The filesystem tools are registered directly by the Agent via
`yoker.agent.tools.build_tool_registry`, so they are not duplicated here.
AgentTool and GitTool are also registered separately by the Agent because they
require runtime dependencies (parent_agent and config).

The built-in manifest remains available for future built-in components that
are not hardcoded into the Agent.
"""

from yoker.plugins.manifest import PluginManifest

__YOKER_MANIFEST__ = PluginManifest()

__all__ = ["__YOKER_MANIFEST__"]
