"""Dynamic skill invocation command in the UI layer.

Handles `/<skill-name>` slash commands by injecting the skill context into
the agent's conversation and then processing a follow-up prompt. Output is
produced through the agent's normal event stream, which the UIHandler
receives.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.ui import UIHandler


async def handle(skill_name: str, args: str, agent: "Agent", ui: "UIHandler") -> None:
  """Invoke a skill by slash command.

  Injects the skill context into the agent's conversation and then asks the
  agent to execute the skill. Any output is produced via the agent's event
  stream, so this function returns None.

  Args:
    skill_name: Name of the skill to invoke.
    args: Optional arguments passed to the skill.
    agent: The current agent instance.
    ui: The UI handler that receives agent output.

  Raises:
    SkillError: If the skill is not found in the agent's skill registry.
  """
  from yoker.exceptions import SkillError

  registry = agent.skill_registry
  if registry is None or skill_name not in registry:
    available = ", ".join(registry.names) if registry else ""
    if available:
      raise SkillError(skill_name, f"Unknown skill. Available skills: {available}")
    raise SkillError(skill_name, "Unknown skill")

  agent.inject_skill_context(skill_name, args)

  prompt = args if args.strip() else "Execute the skill as requested."
  await agent.process(prompt)
