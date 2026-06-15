"""UI layer slash-commands for Yoker.

All slash-commands live in the UI layer and receive the current Agent and
UIHandler. They may query agent state, update agent state, or drive agent
processing. Output is always produced through the UIHandler.
"""

from yoker.agent import Agent
from yoker.logging import get_logger
from yoker.ui import UIHandler
from yoker.ui.commands import skill_invoke
from yoker.ui.commands.agents import create_command as create_agents_command
from yoker.ui.commands.base import Command, CommandHandler
from yoker.ui.commands.context import create_command as create_context_command
from yoker.ui.commands.help import create_command as create_help_command
from yoker.ui.commands.skills import create_command as create_skills_command
from yoker.ui.commands.think import create_command as create_think_command
from yoker.ui.commands.tools import create_command as create_tools_command

__all__ = [
  "Agent",
  "Command",
  "CommandHandler",
  "CommandRegistry",
  "UIHandler",
  "create_default_registry",
]

log = get_logger(__name__)


class CommandRegistry:
  """Registry for slash-commands in the UI layer.

  Commands are matched by name (without the leading /). Built-in commands are
  registered explicitly. Any unknown command is treated as a potential skill
  invocation and delegated to the skill invocation handler.
  """

  def __init__(self) -> None:
    """Initialize an empty command registry."""
    self._commands: dict[str, Command] = {}

  def register(self, command: Command) -> None:
    """Register a command.

    Args:
      command: The Command object to register.

    Raises:
      ValueError: If a command with the same name is already registered.
    """
    if command.name in self._commands:
      raise ValueError(f"Command '{command.name}' is already registered")
    self._commands[command.name] = command

  def get(self, name: str) -> Command | None:
    """Get a command by name.

    Args:
      name: Command name (without leading /).

    Returns:
      The Command object if found, None otherwise.
    """
    return self._commands.get(name)

  def list_commands(self) -> list[Command]:
    """Get all registered commands sorted by name.

    Returns:
      List of Command objects sorted alphabetically by name.
    """
    return sorted(self._commands.values(), key=lambda c: c.name)

  @property
  def names(self) -> list[str]:
    """Get all registered command names.

    Returns:
      List of command names sorted alphabetically.
    """
    return sorted(self._commands.keys())

  async def dispatch(self, command: str, agent: Agent, ui: UIHandler) -> str | None:
    """Parse and dispatch a slash-command.

    Args:
      command: Raw user input line starting with /.
      agent: The current agent instance.
      ui: The UI handler for output.

    Returns:
      Command output string if this was a command that produced text output,
      or None if the command handled its own output (e.g., skill invocation).
      Returns None if the input was not a slash-command.
    """
    if not command.startswith("/"):
      return None

    name, _, args = command.lstrip("/").partition(" ")
    if not name:
      return "Error: Empty command"

    log.debug(
      "command_dispatch",
      command_name=name,
      args=args,
      available_commands=self.names,
    )

    cmd = self.get(name)
    if cmd is not None:
      log.info("command_executing", command_name=name, args=args)
      return await cmd.handler(args, agent, ui)

    # Unknown command: try skill invocation.
    registry = agent.skill_registry
    if registry is not None and name in registry:
      log.info("skill_command_dispatch", skill_name=name, args=args)
      await skill_invoke.handle(name, args, agent, ui)
      return None

    log.warning(
      "command_not_found",
      command_name=name,
      available_commands=self.names,
    )
    return f"Error: Unknown command '/{name}'. Type /help for available commands."


def create_default_registry() -> CommandRegistry:
  """Create and populate the default UI command registry.

  Registers all built-in slash commands. The registry is created empty and
  then populated so the /help command can capture a reference to the fully
  populated registry without circular imports.

  Returns:
    A CommandRegistry with all default commands registered.
  """
  registry = CommandRegistry()

  registry.register(create_help_command(lambda: registry))
  registry.register(create_think_command())
  registry.register(create_skills_command())
  registry.register(create_context_command())
  registry.register(create_tools_command())
  registry.register(create_agents_command())

  return registry
