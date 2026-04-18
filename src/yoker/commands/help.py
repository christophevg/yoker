"""/help command implementation."""

from collections.abc import Callable

from yoker.commands.base import Command
from yoker.commands.registry import CommandRegistry


def create_help_command(registry: CommandRegistry) -> Command:
  """Create the /help command.

  The help command lists all registered commands with their descriptions.

  Args:
    registry: The command registry to query for available commands.

  Returns:
    A Command object for the help command.
  """
  return Command(
    name="help",
    description="Show available commands",
    handler=_create_help_handler(registry),
  )


def _create_help_handler(registry: CommandRegistry) -> Callable[[list[str]], str]:
  """Create the help command handler.

  Args:
    registry: The command registry to query.

  Returns:
    Handler function for the help command.
  """

  def handler(args: list[str]) -> str:
    """Show available commands.

    Args:
      args: Ignored (no arguments needed).

    Returns:
      Formatted help text listing all commands.
    """
    lines = ["Available commands:"]
    lines.append("")

    for cmd in registry.list_commands():
      lines.append(f"  /{cmd.name} - {cmd.description}")

    lines.append("")
    lines.append("Type a message without / prefix to chat with the LLM.")

    return "\n".join(lines)

  return handler
