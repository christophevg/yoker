"""Agent definition schema for Yoker.

Provides frozen dataclasses for agent definitions loaded from Markdown files.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
  """Agent definition loaded from a Markdown file.

  Attributes:
    name: Agent identifier (unique within a configuration).
    description: Short description for LLM tool definition.
    tools: Tuple of tool names available to this agent.
    color: Optional display color for UI integrations.
    system_prompt: The Markdown body content (agent's system prompt).
    source_path: Path to the source Markdown file.
  """

  name: str
  description: str
  tools: tuple[str, ...]
  color: str | None = None
  system_prompt: str = ""
  source_path: str = ""


__all__ = [
  "AgentDefinition",
]
