"""Batch UI handler implementation.

Uses stdin/stdout/stderr channels with no formatting. Preserves ANSI codes
from LLM output. Supports predefined input messages for scripted execution.
"""

from __future__ import annotations

import sys
from typing import Any, TextIO

from yoker.agent import Agent
from yoker.ui.handler import UIHandler


class BatchUIHandler(UIHandler):
  """Batch UI for non-interactive execution.

  Output channels:
    - Content -> stdout
    - Thinking, tool calls, tool results, tool content, errors, stats -> stderr

  Input:
    - From predefined messages (set_input_messages)
    - From stdin (one message per line)

  No formatting - preserves ANSI from LLM.
  """

  def __init__(
    self,
    show_thinking: bool = False,
    show_tool_calls: bool = False,
    show_stats: bool = False,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
  ) -> None:
    """Initialize the batch UI handler.

    Args:
      show_thinking: Whether to display thinking output on stderr.
      show_tool_calls: Whether to display tool call info on stderr.
      show_stats: Whether to display turn statistics on stderr.
      stdin: Input stream (default: sys.stdin).
      stdout: Output stream for content (default: sys.stdout).
      stderr: Output stream for diagnostics (default: sys.stderr).
    """
    self.show_thinking = show_thinking
    self.show_tool_calls = show_tool_calls
    self.show_stats = show_stats

    # Streams
    self._stdin = stdin if stdin is not None else sys.stdin
    self._stdout = stdout if stdout is not None else sys.stdout
    self._stderr = stderr if stderr is not None else sys.stderr

    # Predefined input source
    self._input_source: list[str] | None = None
    self._input_index = 0

  def set_input_messages(self, messages: list[str]) -> None:
    """Set predefined input messages.

    Args:
      messages: List of input messages to return sequentially from get_input.
    """
    self._input_source = messages
    self._input_index = 0

  # === Lifecycle ===

  async def start(self, agent: Agent) -> None:
    """Start batch UI session.

    Args:
      agent: The Agent instance this UI session is serving.
    """
    # Minimal output for batch mode - only if showing thinking
    if self.show_thinking:
      print(f"# Model: {agent.model}", file=self._stderr)

  async def shutdown(self, reason: str) -> None:
    """End batch UI session.

    Args:
      reason: Reason for ending ("quit", "error", "interrupt", "complete").
    """
    # No output for batch mode
    pass

  # === Input ===

  async def get_input(self, prompt: str = "> ") -> str | None:
    """Get user input from predefined source or stdin.

    Args:
      prompt: Prompt string (ignored in batch mode).

    Returns:
      User input string, or None if end of input (EOF).
    """
    if self._input_source is not None:
      # Predefined messages
      if self._input_index >= len(self._input_source):
        return None
      message = self._input_source[self._input_index]
      self._input_index += 1
      return message

    # Read from stdin
    try:
      line = self._stdin.readline()
      if not line:
        return None
      return line.rstrip("\n")
    except EOFError:
      return None

  # === Content Output (stdout) ===

  def start_content_stream(self) -> None:
    """Start streaming content."""
    # No setup needed for batch mode
    pass

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream a content chunk to stdout.

    Args:
      chunk: Content chunk (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    print(chunk, file=self._stdout, end="", flush=True)

  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    print(file=self._stdout)  # Final newline

  def output_content(self, content: str, content_type: str = "text/plain") -> None:
    """Output content text directly (non-streaming).

    Args:
      content: Content text (may contain ANSI from LLM).
      content_type: MIME type of content.
    """
    self.start_content_stream()
    self.stream_content(content, content_type)
    self.end_content_stream(len(content))

  def output_thinking(self, text: str) -> None:
    """Output thinking text directly (non-streaming).

    Args:
      text: Thinking text.
    """
    self.start_thinking_stream()
    self.stream_thinking(text)
    self.end_thinking_stream(len(text))

  # === Command Output (stdout) ===

  def output_command_result(self, result: str) -> None:
    """Output command result.

    Args:
      result: Command output text.
    """
    print(result, file=self._stdout)

  # === Thinking Output (stderr) ===

  def start_thinking_stream(self) -> None:
    """Start streaming thinking."""
    pass

  def stream_thinking(self, chunk: str) -> None:
    """Stream a thinking chunk to stderr.

    Args:
      chunk: Thinking chunk (may contain ANSI from LLM).
    """
    if self.show_thinking:
      print(chunk, file=self._stderr, end="", flush=True)

  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    if self.show_thinking:
      print(file=self._stderr)

  # === Tool Output (stderr) ===

  def output_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
    """Output tool call information.

    Args:
      tool_name: Name of tool being called.
      args: Tool arguments (may be truncated for display).
    """
    if not self.show_tool_calls:
      return
    args_str = " ".join(f"{k}={v}" for k, v in list(args.items())[:3])
    print(f"# Tool: {tool_name}({args_str})", file=self._stderr)

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    """Output tool result status.

    Args:
      tool_name: Name of tool.
      success: Whether tool succeeded.
      result: Result text or error message.
    """
    if not self.show_tool_calls:
      return
    status = "OK" if success else "FAIL"
    detail = result[:50] if result else ""
    if detail:
      print(f"# {status} {tool_name}: {detail}", file=self._stderr)
    else:
      print(f"# {status} {tool_name}", file=self._stderr)

  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict[str, Any],
  ) -> None:
    """Output tool content.

    Args:
      tool_name: Name of tool.
      operation: Operation type.
      path: File path.
      content: Content text (may be None for summary).
      content_type: MIME type of content.
      metadata: Additional metadata.
    """
    if not self.show_tool_calls:
      return
    print(f"# Tool content: {tool_name} {operation} {path} ({content_type})", file=self._stderr)
    if content is not None:
      print(content, file=self._stderr)

  # === Stats Output (stderr) ===

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    """Output turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
    """
    if not self.show_stats:
      return
    total = prompt_tokens + eval_tokens
    duration_s = duration_ms / 1000.0
    print(f"# Stats: {duration_s:.1f}s, {total} tokens", file=self._stderr)

  # === Error Output (stderr) ===

  def output_error(self, error: Exception, include_traceback: bool = False) -> None:
    """Output error message.

    Args:
      error: Exception that occurred.
      include_traceback: Whether to include traceback (ignored in batch mode).
    """
    error_type = type(error).__name__
    print(f"Error [{error_type}]: {error}", file=self._stderr)
