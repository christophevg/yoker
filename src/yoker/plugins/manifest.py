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
    from yoker.tools.annotations import Text
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
    agent: Optional agent definition name to use for `yoker run`. Convenience
      fallback for Python packages without an `agent.toml` (NOT a config override;
      the manifest config-override layer is handled in
      :mod:`yoker.plugins.file_manifest`).
    prompt: Optional initial prompt for `yoker run`. Same convenience fallback
      role as `agent`.
  """

  tools: list[Callable[..., Any]] = field(default_factory=list)
  skills: list["Skill"] = field(default_factory=list)
  agents: list["AgentDefinition"] = field(default_factory=list)
  config_class: type | None = None
  skills_dir: str = "skills"
  agents_dir: str = "agents"
  # Convenience fallbacks for `yoker run` when no agent.toml is present.
  agent: str | None = None
  prompt: str | None = None


__all__ = ["PluginManifest"]
