"""/context command implementation in the UI layer.

Shows the current session context including session ID, message count,
turn count, tool calls, and recent messages. The command queries the
agent's context manager and outputs via the UIHandler.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "Show current session context"


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """Show current context information.

  Args:
    args: Ignored (no arguments needed).
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Formatted context information.
  """
  session_id = agent.context.get_session_id()
  stats = agent.context.get_statistics()
  messages = agent.context.get_messages()

  lines = ["Current Context", ""]
  lines.append(f"  Session ID: {session_id}")
  lines.append(f"  Messages: {stats.message_count}")
  lines.append(f"  Turns: {stats.turn_count}")
  lines.append(f"  Tool calls: {stats.tool_call_count}")

  if messages:
    lines.append("")
    lines.append("  Recent messages:")
    recent = messages[-5:]
    for msg in recent:
      role = msg.get("role", "unknown")
      content = msg.get("content", "")
      if len(content) > 50:
        content = content[:47] + "..."
      lines.append(f"    \\[{role}] {content}")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /context command.

  Returns:
    A Command object for /context.
  """
  from yoker.ui.commands.base import Command

  return Command(name="context", description=DESCRIPTION, handler=handle)
