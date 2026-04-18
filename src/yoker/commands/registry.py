"""Command registry for managing slash-commands."""

from yoker.commands.base import Command


class CommandRegistry:
  """Registry for slash-commands.

  Manages command registration and dispatch. Commands are matched by name
  (without the leading /).

  Attributes:
    commands: Dictionary mapping command names to Command objects.
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

  def dispatch(self, input_line: str) -> str | None:
    """Parse and dispatch a command if it matches.

    Args:
      input_line: Raw user input line.

    Returns:
      Command output string if this was a command, None if not a command.

    Example:
      >>> registry.dispatch("/help")
      "Available commands:\\n/help - Show this help message"
      >>> registry.dispatch("hello world")
      None
    """
    if not input_line.startswith("/"):
      return None

    # Parse command and arguments
    parts = input_line[1:].split(maxsplit=1)
    if not parts:
      return "Error: Empty command"

    command_name = parts[0].lower()
    args: list[str] = parts[1].split() if len(parts) > 1 else []

    # Look up command
    command = self.get(command_name)
    if command is None:
      return f"Error: Unknown command '/{command_name}'. Type /help for available commands."

    # Execute command
    return command.handler(args)

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
