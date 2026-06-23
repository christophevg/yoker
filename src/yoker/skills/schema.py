"""Skill definition schema for Yoker.

Provides dataclass for skill definitions loaded from Markdown files.
Skills are prompts that can be invoked via slash commands or natural language.
"""

from dataclasses import dataclass

from yoker.schema import NameSpaced


@dataclass
class Skill(NameSpaced):
  """Skill definition loaded from a Markdown file.

  Skills are reusable prompts that guide agent behavior for specific tasks.
  They can be invoked via slash commands (e.g., /commit) or natural language.

  Attributes:
    name: Skill identifier (unique, used in slash commands).
    description: Short description for system reminder discovery block.
    content: Full skill content (body after frontmatter).
    triggers: Optional list of trigger phrases for natural language invocation.
    tools: Optional list of tool names this skill uses.
    source_path: Path to the source Markdown file.
    namespace: Optional namespace prefix (e.g., 'pkg' for 'pkg:skill').
  """

  description: str = ""
  content: str = ""
  triggers: tuple[str, ...] = ()
  tools: tuple[str, ...] = ()
  source_path: str = ""

  def __post_init__(self) -> None:
    if not self.description:
      raise ValueError("A skill needs a description.")
    if not self.content:
      raise ValueError("A skill needs content")


__all__ = ["Skill"]
