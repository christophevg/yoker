"""/skill command implementation.

Provides slash command support for invoking skills by name.

Skill commands inject the skill content into the agent's context as a system
message and signal that the agent should process with the skill context.
The user does NOT see the raw skill content.
"""

from collections.abc import Callable

from yoker.commands.base import Command
from yoker.skills import Skill, SkillRegistry, format_invocation_block

# Special marker to indicate skill content should be injected
SKILL_INJECTION_MARKER = "__SKILL_INJECTION__"


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

  Returns a special marker string that signals the main loop to inject
  the skill content into the agent's context as a system message.

  Args:
    skill: The skill being invoked.
    args: Arguments passed to the skill command.

  Returns:
    Special marker string that contains the skill content to inject.
    The format is: __SKILL_INJECTION__<skill_content>
  """
  # Join arguments into a single string
  args_str = " ".join(args) if args else ""

  # Format the invocation block
  invocation_block = format_invocation_block(skill, args_str)

  # Return special marker with the content
  # The main loop will detect this and inject it as a system message
  return f"{SKILL_INJECTION_MARKER}{invocation_block}"


def is_skill_injection(result: str) -> bool:
  """Check if a command result is a skill injection marker.

  Args:
    result: The result string from a command.

  Returns:
    True if this is a skill injection marker.
  """
  return result.startswith(SKILL_INJECTION_MARKER)


def extract_skill_content(result: str) -> str:
  """Extract skill content from an injection marker.

  Args:
    result: The result string containing the injection marker.

  Returns:
    The skill content to inject as a system message.
  """
  return result[len(SKILL_INJECTION_MARKER):]


__all__ = ["create_skill_commands", "is_skill_injection", "extract_skill_content"]
