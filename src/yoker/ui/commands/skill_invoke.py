"""Dynamic skill invocation command in the UI layer.

Handles `/<skill-name>` slash commands by injecting the skill context into
the agent's conversation and then processing a follow-up prompt. Output is
produced through the agent's normal event stream, which the UIHandler
receives.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
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
  agent.inject_skill_context(skill_name, args)

  prompt = args if args.strip() else "Execute the skill as requested."
  await agent.process(prompt)
