"""/skills command implementation in the UI layer.

Lists all loaded skills with their descriptions and sources. The command
queries the agent's skill registry and outputs via the UIHandler.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "List all loaded skills with sources"


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """List all loaded skills with source information.

  Args:
    args: Ignored (no arguments needed).
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Formatted text listing all skills with sources.
  """
  registry = agent.skills

  lines = ["Loaded skills:", ""]

  if registry is None or len(registry) == 0:
    lines.append("  No skills loaded.")
    lines.append("")
    if agent.config.skills.directories:
      lines.append(f"  Configured directories: {', '.join(agent.config.skills.directories)}")
    else:
      lines.append("  No skill directories configured.")
    return "\n".join(lines)

  config_skills: list[tuple[str, str]] = []
  plugin_skills: list[tuple[str, str]] = []
  builtin_skills: list[tuple[str, str]] = []

  for skill_name, skill in registry.items():
    if ":" in skill_name:
      if skill_name.startswith("yoker:"):
        builtin_skills.append((skill_name, skill.description))
      else:
        plugin_skills.append((skill_name, skill.description))
    else:
      config_skills.append((skill_name, skill.description))

  if config_skills:
    lines.append("From config:")
    for skill_name, description in sorted(config_skills, key=lambda x: x[0]):
      lines.append(f"  ✓ {skill_name:20} - {description}")
    lines.append("")

  if plugin_skills:
    lines.append("From plugins:")
    for skill_name, description in sorted(plugin_skills, key=lambda x: x[0]):
      package = skill_name.split(":")[0] if ":" in skill_name else "unknown"
      lines.append(f"  ✓ {skill_name:20} - {description} ({package})")
    lines.append("")

  if builtin_skills:
    lines.append("Built-in:")
    for skill_name, description in sorted(builtin_skills, key=lambda x: x[0]):
      lines.append(f"  ✓ {skill_name:20} - {description}")
    lines.append("")

  lines.append("All loaded skills are available to the agent.")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /skills command.

  Returns:
    A Command object for /skills.
  """
  from yoker.ui.commands.base import Command

  return Command(name="skills", description=DESCRIPTION, handler=handle)
