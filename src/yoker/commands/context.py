"""/context command implementation."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from yoker.commands.base import Command

if TYPE_CHECKING:
  from yoker.context import ContextStatistics


def create_context_command(
  get_session_id: Callable[[], str],
  get_statistics: Callable[[], "ContextStatistics"],
  get_messages: Callable[[], list[dict[str, Any]]],
) -> Command:
  """Create the /context command.

  The context command shows the current session context including
  session ID, message count, turn count, and recent messages.

  Args:
    get_session_id: Function that returns the current session ID.
    get_statistics: Function that returns ContextStatistics.
    get_messages: Function that returns the message list.

  Returns:
    A Command object for the context command.
  """

  def handler(args: list[str]) -> str:
    """Show current context information.

    Args:
      args: Ignored (no arguments needed).

    Returns:
      Formatted context information.
    """
    session_id = get_session_id()
    stats = get_statistics()
    messages = get_messages()

    lines = ["Current Context", ""]
    lines.append(f"  Session ID: {session_id}")
    lines.append(f"  Messages: {stats.message_count}")
    lines.append(f"  Turns: {stats.turn_count}")
    lines.append(f"  Tool calls: {stats.tool_call_count}")

    # Show last few messages if any
    if messages:
      lines.append("")
      lines.append("  Recent messages:")
      recent = messages[-5:]  # Last 5 messages
      for msg in recent:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        # Truncate long content
        if len(content) > 50:
          content = content[:47] + "..."
        # Escape brackets for Rich markup (otherwise [system] is interpreted as style)
        lines.append(f"    \\[{role}] {content}")

    return "\n".join(lines)

  return Command(
    name="context",
    description="Show current session context",
    handler=handler,
  )
