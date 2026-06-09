"""Plugin manifest for Yoker plugin integration.

Defines the PluginManifest dataclass for declaring plugin components
(tools, skills, agents) that a Python package provides.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.skills import Skill
  from yoker.tools import Tool


@dataclass
class PluginManifest:
  """Plugin manifest for declaring plugin components.

  Packages provide this manifest in their yoker submodule to declare
  the tools, skills, and agents they provide.

  Example:
    # In package/yoker/__init__.py

    from yoker.plugins import PluginManifest
    from yoker.tools import Tool, ToolResult

    class MyTool(Tool):
      name = "my_tool"
      description = "Does something useful"

      async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, result="Done")

    manifest = PluginManifest(
      tools=[MyTool()],
      skills=[...],
      agents=[...],
    )

  Attributes:
    tools: List of Tool instances provided by this plugin.
    skills: List of Skill instances provided by this plugin.
    agents: List of AgentDefinition instances provided by this plugin.
    config_class: Optional configuration class for plugin tools.
      If provided, yoker will pass configuration from yoker.toml to tools.
    skills_dir: Optional directory name for skill files (default: "skills").
    agents_dir: Optional directory name for agent files (default: "agents").
  """

  tools: list["Tool"] = field(default_factory=list)
  skills: list["Skill"] = field(default_factory=list)
  agents: list["AgentDefinition"] = field(default_factory=list)
  config_class: type | None = None
  skills_dir: str = "skills"
  agents_dir: str = "agents"


__all__ = ["PluginManifest"]
