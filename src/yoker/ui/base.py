"""Base UI handler implementation.

This module provides a base implementation with state management,
allowing subclasses to focus on platform-specific formatting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.agent import Agent


class BaseUIHandler(ABC):
  """Base implementation with state management.

  Provides:
    - State tracking (turn count, streaming state)
    - Default implementations for convenience

  Does NOT provide:
    - Formatting (implementation-specific)
    - Buffering (implementation choice)

  Subclasses implement:
    - Platform-specific output methods
    - Input handling
    - Error formatting
  """

  def __init__(self) -> None:
    """Initialize base handler with default state."""
    self._turn_count = 0
    self._streaming_content = False
    self._streaming_thinking = False

  # === State Management ===

  def _start_turn(self) -> None:
    """Start a new turn."""
    self._turn_count += 1
    self._streaming_content = False
    self._streaming_thinking = False

  def _end_turn(self) -> None:
    """End current turn."""
    self._streaming_content = False
    self._streaming_thinking = False

  # === Default Implementations ===

  def output_content(self, content: str, content_type: str = "text/plain") -> None:
    """Default: output via streaming.

    This method provides a default implementation that uses streaming
    to output content. Subclasses can override if they prefer direct output.

    Args:
      content: Content text.
      content_type: MIME type of content.
    """
    self.start_content_stream()
    self.stream_content(content, content_type)
    self.end_content_stream(len(content))

  def output_thinking(self, text: str) -> None:
    """Default: output via streaming.

    This method provides a default implementation that uses streaming
    to output thinking. Subclasses can override if they prefer direct output.

    Args:
      text: Thinking text.
    """
    self.start_thinking_stream()
    self.stream_thinking(text)
    self.end_thinking_stream(len(text))

  # === Abstract Methods ===

  @abstractmethod
  async def start(self, agent: Agent) -> None:
    """Start UI session.

    Args:
      agent: The Agent instance this UI session is serving.
    """
    ...

  @abstractmethod
  async def shutdown(self, reason: str) -> None:
    """End UI session.

    Args:
      reason: Reason for ending.
    """
    ...

  @abstractmethod
  async def get_input(self, prompt: str = "> ") -> str | None:
    """Get user input.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input.
    """
    ...

  @abstractmethod
  def output_command_result(self, result: str) -> None:
    """Output command result.

    Args:
      result: Command output text.
    """
    ...

  @abstractmethod
  def output_tool_call(self, tool_name: str, args: dict[str, object]) -> None:
    """Output tool call information.

    Args:
      tool_name: Name of tool being called.
      args: Tool arguments.
    """
    ...

  @abstractmethod
  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    """Output tool result status.

    Args:
      tool_name: Name of tool.
      success: Whether tool succeeded.
      result: Result text or error message.
    """
    ...

  @abstractmethod
  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict[str, object],
  ) -> None:
    """Output tool content (file contents, diff, etc.).

    Args:
      tool_name: Name of tool.
      operation: Operation type.
      path: File path.
      content: Content text.
      content_type: MIME type of content.
      metadata: Additional metadata.
    """
    ...

  @abstractmethod
  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    """Output turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
    """
    ...

  @abstractmethod
  def output_error(self, error: Exception) -> None:
    """Output error message.

    Args:
      error: Exception that occurred.
    """
    ...

  # === Abstract Streaming Methods ===

  @abstractmethod
  def start_content_stream(self) -> None:
    """Start streaming content."""
    ...

  @abstractmethod
  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream content chunk.

    Args:
      chunk: Content chunk.
      content_type: MIME type of content.
    """
    ...

  @abstractmethod
  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    ...

  @abstractmethod
  def start_thinking_stream(self) -> None:
    """Start streaming thinking."""
    ...

  @abstractmethod
  def stream_thinking(self, chunk: str) -> None:
    """Stream thinking chunk.

    Args:
      chunk: Thinking chunk.
    """
    ...

  @abstractmethod
  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    ...
