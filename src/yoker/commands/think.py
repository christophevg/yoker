"""/think command implementation."""

from collections.abc import Callable

from yoker.commands.base import Command
from yoker.thinking import ThinkingMode


def create_think_command(
  get_thinking_mode: Callable[[], ThinkingMode],
  set_thinking_mode: Callable[[ThinkingMode], None],
) -> Command:
  """Create the /think command.

  The think command sets or displays the thinking mode state.

  Args:
    get_thinking_mode: Function that returns current thinking mode.
    set_thinking_mode: Function that sets thinking mode (takes ThinkingMode).

  Returns:
    A Command object for the think command.
  """

  def handler(args: list[str]) -> str:
    """Set or display thinking mode.

    Args:
      args: Optional 'on', 'off', or 'silent' to set mode explicitly.

    Returns:
      Status message about the thinking mode.
    """
    if not args:
      # No args: show current state
      current = get_thinking_mode()
      return f"Thinking mode is currently {current.value}. Use /think on|off|silent to change."

    arg = args[0].lower()

    if arg == "on":
      set_thinking_mode(ThinkingMode.ON)
      return "Thinking mode enabled. The LLM will show its reasoning process."
    elif arg == "off":
      set_thinking_mode(ThinkingMode.OFF)
      return "Thinking mode disabled. The LLM will not use reasoning."
    elif arg == "silent":
      set_thinking_mode(ThinkingMode.SILENT)
      return "Thinking mode silent. The LLM will reason but not display it."
    else:
      return f"Error: Invalid argument '{arg}'. Use /think on, off, or silent."

  return Command(
    name="think",
    description="Set thinking mode: /think [on|off|silent]",
    handler=handler,
  )
