"""Base types for the UI command system.

Slash-commands are intercepted before being sent to the LLM and trigger
Yoker functionality directly. All commands receive the current Agent and
UIHandler so they can query state, update state, and produce output.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.core import Agent
  from yoker.ui import UIHandler

CommandHandler = Callable[[str, "Agent", "UIHandler"], Awaitable[str | None]]


@dataclass(frozen=True)
class Command:
  """A slash-command that triggers Yoker functionality from the UI layer.

  Attributes:
    name: Command name (without the leading /).
    description: Short description for help output.
    handler: Async function that executes the command. Receives the raw
      argument string, the current Agent, and the UIHandler. Returns a
      string to display, or None if the command produced its own output.
  """

  name: str
  description: str
  handler: CommandHandler
