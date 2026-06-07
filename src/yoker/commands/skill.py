"""/skill command implementation.

Provides slash command support for invoking skills by name.
"""

from collections.abc import Callable

from yoker.commands.base import Command
from yoker.skills import Skill, SkillRegistry, format_invocation_block


def create_skill_commands(
  registry: SkillRegistry,
  get_skill_registry: Callable[[], SkillRegistry],
) -> list[Command]:
  """Create skill commands from the skill registry.

  Each registered skill becomes a slash command that can be invoked
  as `/skill-name` with optional arguments.

  Args:
    registry: SkillRegistry with pre-loaded skills.
    get_skill_registry: Function that returns current skill registry
      (for dynamic registry access).

  Returns:
    List of Command objects for all registered skills.
  """
  commands: list[Command] = []

  for skill_name, skill in registry:
    # Create a command for each skill
    # Note: skill_name is captured in closure, so each command gets its own name
    # Use explicit function to avoid mypy lambda type inference issues
    def make_handler(s: Skill) -> Callable[[list[str]], str]:
      """Create a handler function for a skill."""

      def handler(args: list[str]) -> str:
        return _skill_handler(s, args)

      return handler

    commands.append(
      Command(
        name=skill_name,
        description=skill.description,
        handler=make_handler(skill),
      )
    )

  return commands


def _skill_handler(skill: Skill, args: list[str]) -> str:
  """Handle skill command invocation.

  Args:
    skill: The skill being invoked.
    args: Arguments passed to the skill command.

  Returns:
    Formatted invocation block with skill content.
  """
  # Join arguments into a single string
  args_str = " ".join(args) if args else ""

  # Format and return the invocation block
  return format_invocation_block(skill, args_str)


__all__ = ["create_skill_commands"]
