"""Echo tool implementation for demo plugin.

Provides a simple echo tool that returns its input with a prefix.
"""

from typing import Annotated

from yoker.tools.annotations import Text


def echo(message: Annotated[str, Text("The message to echo back")]) -> str:
  """Echo back the input message with a prefix."""
  return f"Echo: {message}"


__all__ = ["echo"]
