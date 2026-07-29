"""/context command implementation in the UI layer.

Shows the current session context including session ID, message count,
turn count, tool calls, and recent messages. The command queries the
agent's context manager and outputs via the UIHandler.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
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
    lines.append("  Messages:")
    for index, msg in enumerate(messages, start=1):
      role = msg.get("role", "unknown")
      content = msg.get("content", "")
      thinking = msg.get("thinking")
      tool_calls = msg.get("tool_calls")
      lines.append(f"    #{index} ({role})")
      if thinking:
        lines.append("      --- thinking ---")
        for line in str(thinking).splitlines():
          lines.append(f"      {line}")
        lines.append("      --- content ---")
      if content:
        for line in content.splitlines():
          lines.append(f"      {line}")
      if tool_calls:
        if content:
          lines.append("      --- tool calls ---")
        for tc in tool_calls:
          name = tc.get("name") or tc.get("function", {}).get("name", "unknown")
          lines.append(f"      [tool: {name}]")
      if not content and not tool_calls and not thinking:
        lines.append("      (empty)")
      lines.append("")

  return "\n".join(lines)


def create_command() -> "Command":
  """Create the /context command.

  Returns:
    A Command object for /context.
  """
  from yoker.ui.commands.base import Command

  return Command(name="context", description=DESCRIPTION, handler=handle)
