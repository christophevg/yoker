"""Agent definition schema for Yoker.

Provides frozen dataclasses for agent definitions loaded from Markdown files.
"""

from dataclasses import dataclass

from yoker.schema import NameSpaced


@dataclass
class AgentDefinition(NameSpaced):
  """Agent definition loaded from a Markdown file.

  Attributes:
    name: Agent identifier (unique within a configuration).
    description: Short description for LLM tool definition.
    system_prompt: The Markdown body content (agent's system prompt).
    source_path: Path to the source Markdown file.
    tools: Optional Tuple of tool names available to this agent.
    color: Optional display color for UI integrations.
    model: Optional model override for this agent.
  """

  description: str = "The default/minimal Yoker agent."
  system_prompt: str = "You are a helpful assistant."
  source_path: str = ""
  tools: tuple[str, ...] = ()
  color: str | None = None
  model: str | None = None

  @property
  def default_simple_name(self) -> str | None:
    return "default"

__all__ = [
  "AgentDefinition",
]
