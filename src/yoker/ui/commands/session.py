"""/session command implementation in the UI layer.

Shows the active agents in the current session: the primary agent and all
spawned sub-agents, with their status, model, message count, and tools.
The command queries the session's agent map (via ``agent._session``) and
outputs via the UIHandler.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "Show active agents in the current session"


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """Show all active agents in the current session.

  Args:
    args: Ignored (no arguments needed).
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Formatted text showing session info and all active agents.
  """
  session = getattr(agent, "_session", None)

  if session is None:
    return "No active session (standalone agent)."

  agents_map = session._agents_map
  max_agents = session.config.session.max_agents

  lines: list[str] = []
  lines.append("Session")
  lines.append("")
  lines.append(f"  Session ID: {session.id}")
  lines.append(f"  Active agents: {len(agents_map)} / {max_agents}")
  lines.append("")

  lines.append("Active agents:")
  lines.append("")

  for agent_id, agnt in agents_map.items():
    is_primary = agnt is session.agent
    marker = "★" if is_primary else "●"
    label = "primary" if is_primary else "spawned"

    lines.append(f"  {marker} {agent_id} ({label})")
    lines.append(f"      Definition: {agnt.definition.name}")

    if agnt.definition.model:
      lines.append(f"      Model: {agnt.definition.model}")
    elif hasattr(agnt, "model") and agnt.model:
      lines.append(f"      Model: {agnt.model}")

    # Context statistics (messages, turns)
    try:
      stats = agnt.context.get_statistics()
      lines.append(f"      Messages: {stats.message_count}")
      lines.append(f"      Turns: {stats.turn_count}")
    except Exception:
      pass

    # Tools count
    lines.append(f"      Tools: {len(agnt.tools)}")

    # Skills count (if any)
    if len(agnt.skills) > 0:
      lines.append(f"      Skills: {len(agnt.skills)}")

    # Allowed spawns
    if agnt.definition.agents and len(agnt.definition.agents) > 0:
      spawn_list = ", ".join(agnt.definition.agents)
      lines.append(f"      Can spawn: {spawn_list}")

    lines.append("")

  if len(agents_map) >= max_agents:
    lines.append("  ⚠ Session capacity reached — release agents before spawning new ones.")
    lines.append("")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /session command.

  Returns:
    A Command object for /session.
  """
  from yoker.ui.commands.base import Command

  return Command(name="session", description=DESCRIPTION, handler=handle)
