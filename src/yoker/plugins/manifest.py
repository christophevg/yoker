"""Plugin manifest for Yoker plugin integration.

Defines the PluginManifest dataclass for declaring plugin components
(tools, skills, agents) that a Python package provides.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from yoker.agents import AgentDefinition
  from yoker.skills import Skill


@dataclass
class PluginManifest:
  """Plugin manifest for declaring plugin components.

  Packages provide this manifest in their yoker submodule to declare
  the tools, skills, and agents they provide.

  Example:
    # In package/yoker/__init__.py

    from typing import Annotated
    from yoker.annotations import Text
    from yoker.plugins import PluginManifest

    def echo(message: Annotated[str, Text("Message to echo")]) -> str:
      return f"Echo: {message}"

    manifest = PluginManifest(
      tools=[echo],
      skills=[...],
      agents=[...],
    )

  Attributes:
    tools: List of functions or callable class instances provided by this plugin.
    skills: List of Skill instances provided by this plugin.
    agents: List of AgentDefinition instances provided by this plugin.
    config_class: Optional configuration class for plugin tools.
      If provided, yoker will pass configuration from yoker.toml to tools.
    skills_dir: Optional directory name for skill files (default: "skills").
    agents_dir: Optional directory name for agent files (default: "agents").
  """

  tools: list[Callable[..., Any]] = field(default_factory=list)
  skills: list["Skill"] = field(default_factory=list)
  agents: list["AgentDefinition"] = field(default_factory=list)
  config_class: type | None = None
  skills_dir: str = "skills"
  agents_dir: str = "agents"


__all__ = ["PluginManifest"]
