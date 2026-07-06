"""/help command implementation in the UI layer.

Lists all registered commands with their descriptions. Output is produced
via the UIHandler so implementations can format it appropriately.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands import CommandRegistry
  from yoker.ui.commands.base import Command

DESCRIPTION = "Show available commands"


def create_command(registry_getter: Callable[[], "CommandRegistry"]) -> "Command":
  """Create the /help command.

  Args:
    registry_getter: Callable that returns the command registry. Used to
      avoid a circular import while still allowing the help command to list
      all registered commands dynamically.

  Returns:
    A Command object for /help.
  """
  from yoker.ui.commands.base import Command

  async def handler(args: str, agent: "Agent", ui: "UIHandler") -> str:
    """Show available commands.

    Args:
      args: Ignored (no arguments needed).
      agent: The current agent instance.
      ui: The UI handler for output.

    Returns:
      Formatted help text listing all commands.
    """
    registry = registry_getter()
    lines = ["Available commands:", ""]

    for cmd in registry.list_commands():
      lines.append(f"  /{cmd.name} - {cmd.description}")

    lines.append("")
    lines.append("Type a message without / prefix to chat with the LLM.")

    return "\n".join(lines)

  return Command(name="help", description=DESCRIPTION, handler=handler)
