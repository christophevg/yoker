"""/think command implementation."""

from collections.abc import Callable

from yoker.commands.base import Command


def create_think_command(
  get_thinking_state: Callable[[], bool],
  set_thinking_state: Callable[[bool], None],
) -> Command:
  """Create the /think command.

  The think command toggles or displays the thinking mode state.

  Args:
    get_thinking_state: Function that returns current thinking state.
    set_thinking_state: Function that sets thinking state (takes bool).

  Returns:
    A Command object for the think command.
  """

  def handler(args: list[str]) -> str:
    """Toggle or display thinking mode.

    Args:
      args: Optional 'on' or 'off' to set state explicitly.

    Returns:
      Status message about the thinking state.
    """
    if not args:
      # No args: show current state
      current = get_thinking_state()
      state = "on" if current else "off"
      return f"Thinking mode is currently {state}. Use /think on|off to change."

    arg = args[0].lower()

    if arg == "on":
      set_thinking_state(True)
      return "Thinking mode enabled. The LLM will show its reasoning process."
    elif arg == "off":
      set_thinking_state(False)
      return "Thinking mode disabled. The LLM will not show reasoning."
    else:
      return f"Error: Invalid argument '{arg}'. Use /think on or /think off."

  return Command(
    name="think",
    description="Enable/disable thinking mode: /think [on|off]",
    handler=handler,
  )
