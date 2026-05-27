"""Skill definition schema for Yoker.

Provides frozen dataclass for skill definitions loaded from Markdown files.
Skills are prompts that can be invoked via slash commands or natural language.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
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

  name: str
  description: str
  content: str
  triggers: tuple[str, ...] = ()
  tools: tuple[str, ...] = ()
  source_path: str = ""
  namespace: str | None = None

  @property
  def full_name(self) -> str:
    """Get the full skill name with namespace if present.

    Returns:
      'namespace:name' if namespace is set, otherwise 'name'.
    """
    if self.namespace:
      return f"{self.namespace}:{self.name}"
    return self.name


__all__ = ["Skill"]
