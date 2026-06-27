"""UIHandler protocol definition.

This module defines the protocol that all UI handlers must implement.
The protocol ensures consistent interface across different UI implementations
(interactive, batch, API, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
  from yoker.agent import Agent


class UIHandler(Protocol):
  """Abstract interface for all UI operations.

  All methods receive raw, unformatted data.
  Implementations are responsible for formatting and output.

  Input methods return None for no input (end of session).
  Output methods should handle ANSI codes appropriately for their context.

  Streaming:
    Agent always streams by default.
    UI implementations can buffer if needed.
  """

  # === Lifecycle ===

  async def start(self, agent: Agent) -> None:
    """Start UI session. Called once at beginning.

    Args:
      agent: The Agent instance this UI session is serving.
    """
    ...

  async def shutdown(self, reason: str) -> None:
    """End UI session. Called once at end.

    Args:
      reason: Reason for ending ("quit", "error", "interrupt").
    """
    ...

  # === Input ===

  async def get_input(self, prompt: str = "> ") -> str | None:
    """Get user input.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input (EOF).
    """
    ...

  async def get_secret_input(self, prompt: str = "> ") -> str | None:
    """Get secret user input (masked, not echoed).

    Used for credentials such as API keys. Implementations should mask the
    typed characters (e.g. prompt_toolkit ``is_password=True``). The value
    must never be echoed or logged by the handler.

    Args:
      prompt: Prompt string to display.

    Returns:
      User input string, or None if end of input (EOF).
    """
    ...

  def output_info(self, text: str) -> None:
    """Output an informational text block.

    Used by the bootstrap wizard (and similar pre-session flows) to display
    multi-line informational text outside the streaming agent turn flow.
    Unlike :meth:`output_content`, this does not start a live/streaming
    display; it prints the text as a discrete block.

    Args:
      text: Informational text (may contain newlines).
    """
    ...

  async def output_step_title(self, step: int, total: int, title: str) -> None:
    """Output a wizard step title with a progress indicator.

    Used by the bootstrap wizard to render the "Step N of M: Title" line that
    precedes a step's body content. Interactive implementations may render it
    with visual emphasis (bold/underline); batch implementations render it as
    plain text. Implementations should emit a leading blank line before the
    title for steps after the first (``step > 1``) so consecutive steps are
    visually separated.

    Args:
      step: The 1-based step index.
      total: The total number of steps in the wizard flow.
      title: The human-readable step title.
    """
    ...

  # === Content Output (stdout in batch) ===

  def output_content(self, content: str, content_type: str = "text/plain") -> None:
    """Output content text.

    Args:
      content: Content text (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    ...

  def output_command_result(self, result: str) -> None:
    """Output command result.

    Args:
      result: Command output text.
    """
    ...

  # === Diagnostic Output (stderr in batch) ===

  def output_thinking(self, text: str) -> None:
    """Output thinking/trace text.

    Args:
      text: Thinking text (may contain ANSI from LLM).
    """
    ...

  def output_tool_call(self, tool_name: str, args: dict[str, object]) -> None:
    """Output tool call information.

    Args:
      tool_name: Name of tool being called.
      args: Tool arguments (may be truncated for display).
    """
    ...

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    """Output tool result status.

    Args:
      tool_name: Name of tool.
      success: Whether tool succeeded.
      result: Result text or error message.
    """
    ...

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
      operation: Operation type (read, write, update, etc.).
      path: File path.
      content: Content text (may be None for summary).
      content_type: MIME type of content.
      metadata: Additional metadata (lines, bytes, etc.).
    """
    ...

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    """Output turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
    """
    ...

  def output_error(self, error: Exception, include_traceback: bool = False) -> None:
    """Output error message.

    Args:
      error: Exception that occurred.
    """
    ...

  # === Streaming ===

  def start_content_stream(self) -> None:
    """Start streaming content."""
    ...

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream content chunk.

    Args:
      chunk: Content chunk (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    ...

  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    ...

  def start_thinking_stream(self) -> None:
    """Start streaming thinking."""
    ...

  def stream_thinking(self, chunk: str) -> None:
    """Stream thinking chunk.

    Args:
      chunk: Thinking chunk (may contain ANSI from LLM).
    """
    ...

  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    ...
