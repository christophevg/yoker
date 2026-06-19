"""/config command implementation in the UI layer.

Shows the current config.
"""

import json
from dataclasses import asdict

from yoker.agent import Agent
from yoker.ui import UIHandler
from yoker.ui.commands.base import Command


def create_config_command() -> "Command":
  """Create the /config command.

  Returns:
    A Command object for /config.
  """

  async def handle(_: str, agent: "Agent", __: "UIHandler") -> str:
    """Show the configuration

    Args:
      agent: The current agent instance.
      ui: The UI handler for output.

    Returns:
      The current configuration
    """
    return json.dumps(asdict(agent.config), indent=2)

  return Command(name="config", description="Show configuration.", handler=handle)
