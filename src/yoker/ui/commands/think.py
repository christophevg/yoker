"""/think command implementation in the UI layer.

Toggles or displays the agent's thinking mode. The command updates agent
state directly and outputs the result via the UIHandler.
"""

from typing import TYPE_CHECKING

from yoker.agent.thinking import ThinkingMode

if TYPE_CHECKING:
  from yoker.agent import Agent
  from yoker.ui import UIHandler
  from yoker.ui.commands.base import Command

DESCRIPTION = "Set thinking mode: /think [on|off|silent]"


async def handle(args: str, agent: "Agent", ui: "UIHandler") -> str:
  """Set or display thinking mode.

  Args:
    args: Optional 'on', 'off', or 'silent' to set mode explicitly.
    agent: The current agent instance.
    ui: The UI handler for output.

  Returns:
    Status message about the thinking mode.
  """
  arg = args.strip().lower()

  if not arg:
    current = agent.thinking_mode
    return f"Thinking mode is currently {current.value}. Use /think on|off|silent to change."

  if arg == "on":
    agent.thinking_mode = ThinkingMode.ON
    return "Thinking mode enabled. The LLM will show its reasoning process."
  if arg == "off":
    agent.thinking_mode = ThinkingMode.OFF
    return "Thinking mode disabled. The LLM will not use reasoning."
  if arg == "silent":
    agent.thinking_mode = ThinkingMode.SILENT
    return "Thinking mode silent. The LLM will reason but not display it."

  return f"Error: Invalid argument '{arg}'. Use /think on, off, or silent."


def create_command() -> "Command":
  """Create the /think command.

  Returns:
    A Command object for /think.
  """
  from yoker.ui.commands.base import Command

  return Command(name="think", description=DESCRIPTION, handler=handle)
