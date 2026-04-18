"""Base classes for the command system."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Command:
  """A slash-command that triggers Yoker functionality.

  Attributes:
    name: Command name (without the leading /).
    description: Short description for help output.
    handler: Function that executes the command. Takes a list of string
      arguments and returns the output string.
  """

  name: str
  description: str
  handler: Callable[[list[str]], str]
