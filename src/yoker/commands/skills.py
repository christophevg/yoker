"""/skills command implementation."""

from collections.abc import Callable

from yoker.commands.base import Command
from yoker.skills import SkillRegistry


def create_skills_command(registry: SkillRegistry) -> Command:
  """Create the /skills command.

  The skills command lists all loaded skills with their descriptions.

  Args:
    registry: The skill registry to query for available skills.

  Returns:
    A Command object for the skills command.
  """
  return Command(
    name="skills",
    description="List all loaded skills",
    handler=_create_skills_handler(registry),
  )


def _create_skills_handler(registry: SkillRegistry) -> Callable[[list[str]], str]:
  """Create the skills command handler.

  Args:
    registry: The skill registry to query.

  Returns:
    Handler function for the skills command.
  """

  def handler(args: list[str]) -> str:
    """List all loaded skills.

    Args:
      args: Ignored (no arguments needed).

    Returns:
      Formatted text listing all skills.
    """
    lines = ["Available skills:"]
    lines.append("")

    if registry.count == 0:
      lines.append("  No skills loaded.")
    else:
      for skill_name, skill in registry:
        lines.append(f"  - {skill_name}: {skill.description}")

    return "\n".join(lines)

  return handler

