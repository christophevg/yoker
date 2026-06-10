"""/skills command implementation."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from yoker.commands.base import Command
from yoker.skills import SkillRegistry

if TYPE_CHECKING:
  from yoker.config import Config


def create_skills_command(registry: SkillRegistry, config: "Config") -> Command:
  """Create the /skills command.

  The skills command lists all loaded skills with their descriptions
  and shows their source (config directories vs plugins).

  Args:
    registry: The skill registry to query for available skills.
    config: Configuration object for accessing skill directories.

  Returns:
    A Command object for the skills command.
  """
  return Command(
    name="skills",
    description="List all loaded skills with sources",
    handler=_create_skills_handler(registry, config),
  )


def _create_skills_handler(registry: SkillRegistry, config: "Config") -> Callable[[list[str]], str]:
  """Create the skills command handler.

  Args:
    registry: The skill registry to query.
    config: Configuration object for accessing skill directories.

  Returns:
    Handler function for the skills command.
  """

  def handler(args: list[str]) -> str:
    """List all loaded skills with source information.

    Shows:
      - Skills from config directories
      - Skills from plugins (namespaced)
      - All marked as available (✓)

    Args:
      args: Ignored (no arguments needed).

    Returns:
      Formatted text listing all skills with sources.
    """
    lines = ["Loaded skills:"]
    lines.append("")

    if registry.count == 0:
      lines.append("  No skills loaded.")
      lines.append("")
      if config.skills.directories:
        lines.append(f"  Configured directories: {', '.join(config.skills.directories)}")
      else:
        lines.append("  No skill directories configured.")
      return "\n".join(lines)

    # Separate skills by source
    config_skills = []
    plugin_skills = []
    builtin_skills = []

    for skill_name, skill in registry:
      if ":" in skill_name:
        # Namespaced skill (from plugin or builtin)
        if skill_name.startswith("yoker:"):
          builtin_skills.append((skill_name, skill.description))
        else:
          plugin_skills.append((skill_name, skill.description))
      else:
        # Non-namespaced (from config directory)
        config_skills.append((skill_name, skill.description))

    # Skills from config directories
    if config_skills:
      lines.append("From config:")
      for skill_name, description in sorted(config_skills, key=lambda x: x[0]):
        lines.append(f"  ✓ {skill_name:20} - {description}")
      lines.append("")

    # Skills from plugins
    if plugin_skills:
      lines.append("From plugins:")
      for skill_name, description in sorted(plugin_skills, key=lambda x: x[0]):
        # Extract package name from namespace
        package = skill_name.split(":")[0] if ":" in skill_name else "unknown"
        lines.append(f"  ✓ {skill_name:20} - {description} ({package})")
      lines.append("")

    # Built-in skills
    if builtin_skills:
      lines.append("Built-in:")
      for skill_name, description in sorted(builtin_skills, key=lambda x: x[0]):
        lines.append(f"  ✓ {skill_name:20} - {description}")
      lines.append("")

    # Context information
    lines.append("All loaded skills are available to the agent.")

    return "\n".join(lines)

  return handler
