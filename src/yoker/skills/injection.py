"""Skill context injection for Yoker.

Provides functions to build skill discovery blocks (system reminders)
and invocation blocks (command messages with full skill content).
"""

from yoker.skills.schema import Skill


def format_discovery_block(skills: list[Skill]) -> str:
  """Format the system-reminder block showing available skills.

  This is the discovery phase - skills are listed but full content is not loaded.
  The block shows skill names and descriptions, allowing the LLM to reference them.

  Args:
    skills: List of skill definitions.

  Returns:
    Formatted system-reminder block for injection into LLM context.

  Example:
    >>> skills = [Skill(name="commit", description="Guide git commits")]
    >>> block = format_discovery_block(skills)
    >>> print(block)
    <system-reminder>
    The following skills are available for use:
    - commit: Guide git commits
    ...
    </system-reminder>
  """
  if not skills:
    return ""

  lines = ["<system-reminder>", "The following skills are available for use:"]

  for skill in sorted(skills, key=lambda s: s.full_name):
    # Format: "- name: description"
    # Include usage hint if there are triggers
    line = f"- {skill.full_name}: {skill.description}"
    lines.append(line)

  lines.append("</system-reminder>")
  return "\n".join(lines)


def format_invocation_block(skill: Skill, args: str = "") -> str:
  """Format the invocation block with full skill content injection.

  This is the invocation phase - the full skill content is loaded.
  The block includes the skill content as a command message.

  Args:
    skill: The skill being invoked.
    args: Optional arguments passed to the skill.

  Returns:
    Formatted invocation block with skill content.

  Example:
    >>> skill = Skill(name="commit", description="Guide commits", content="...")
    >>> block = format_invocation_block(skill, "fix authentication bug")
    >>> print(block)
    <command-message>
    <command-name>commit</command-name>
    <command-args>fix authentication bug</command-args>
    </command-message>

    Base directory for this skill:
    ...
  """
  # Command message shows the user's slash command
  command_part = f"/{skill.full_name}"
  if args:
    command_part += f" {args}"

  lines = [
    "<command-message>",
    f"<command-name>{skill.full_name}</command-name>",
    f"<command-args>{args}</command-args>" if args else "<command-args></command-args>",
    "</command-message>",
    "",
    "Base directory for this skill:",
    "",
  ]

  # The full skill content is injected here
  lines.append(skill.content)

  return "\n".join(lines)


def build_skill_context_message(skills: list[Skill], is_discovery: bool = True) -> str:
  """Build context message for skill injection.

  For discovery phase, returns a system-reminder block with skill list.
  For invocation phase, returns the full skill content.

  Args:
    skills: List of skill definitions (typically single skill for invocation).
    is_discovery: True for discovery (list skills), False for invocation (full content).

  Returns:
    Formatted context message for LLM.
  """
  if is_discovery:
    return format_discovery_block(skills)
  elif skills:
    return format_invocation_block(skills[0])
  return ""


def match_skill_by_trigger(message: str, skills: list[Skill]) -> tuple[Skill | None, str]:
  """Match a message against skill triggers for natural language invocation.

  Looks for trigger phrases in the message that might invoke a skill.

  Args:
    message: User message to check.
    skills: List of available skills.

  Returns:
    Tuple of (matched skill, remaining message after trigger removal).
    If no match, returns (None, original message).
  """
  message_lower = message.lower()

  for skill in skills:
    for trigger in skill.triggers:
      trigger_lower = trigger.lower()
      if trigger_lower in message_lower:
        # Remove the trigger from the message
        idx = message_lower.find(trigger_lower)
        remaining = message[:idx] + message[idx + len(trigger) :]
        remaining = remaining.strip()
        return skill, remaining

  return None, message


__all__ = [
  "format_discovery_block",
  "format_invocation_block",
  "build_skill_context_message",
  "match_skill_by_trigger",
]
