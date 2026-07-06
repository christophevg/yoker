"""Thinking mode enumeration for Yoker agents."""

from enum import Enum


class ThinkingMode(Enum):
  """Thinking mode for agent reasoning.

  Attributes:
    ON: Request thinking from LLM and display it to user.
    OFF: Don't request thinking from LLM.
    SILENT: Request thinking from LLM but don't display it (background processing).
  """

  ON = "on"
  OFF = "off"
  SILENT = "silent"

  @property
  def is_enabled(self) -> bool:
    """Check if thinking is requested from LLM.

    Returns:
      True for ON and SILENT modes, False for OFF.
    """
    return self in (ThinkingMode.ON, ThinkingMode.SILENT)

  @property
  def is_visible(self) -> bool:
    """Check if thinking should be displayed to user.

    Returns:
      True for ON mode only, False for OFF and SILENT.
    """
    return self == ThinkingMode.ON


__all__ = [
  "ThinkingMode",
]
