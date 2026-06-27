"""Custom UIHandler example for Yoker.

This example shows how to implement the UIHandler protocol and wire it
into Yoker through UIBridge. It generates events manually so it does not
require a running Ollama instance.

Run with:
    python examples/custom_handler.py
"""

import asyncio
from typing import Any

from yoker import __version__
from yoker.agent import Agent
from yoker.events import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventType,
  ToolCallEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)
from yoker.ui import UIBridge


class PrintUIHandler:
  """Minimal UIHandler that prints every event to stdout.

  This is useful for logging, testing, or building non-terminal interfaces
  (web dashboards, log collectors, etc.).

  Implements the UIHandler protocol without inheritance.
  """

  async def start(self, agent: Agent) -> None:
    """Print session start information.

    Args:
      agent: the agent in action
    """
    print(f"[start] model={agent.model} version={__version__} config={agent.config}")

  async def shutdown(self, reason: str) -> None:
    """Print session end information.

    Args:
      reason: Reason for ending the session.
    """
    print(f"[shutdown] reason={reason}")

  async def get_input(self, prompt: str = "> ") -> str | None:
    """Return no input; this example drives events manually.

    Args:
      prompt: Prompt string (ignored here).

    Returns:
      None to signal end of input.
    """
    return None

  async def get_secret_input(self, prompt: str = "> ") -> str | None:
    """Return no input; this example drives events manually.

    Args:
      prompt: Prompt string (ignored here).

    Returns:
      None to signal end of input.
    """
    return None

  def output_info(self, text: str) -> None:
    """Print an informational text block.

    Args:
      text: Informational text (may contain newlines).
    """
    print(f"[info] {text}")

  def output_command_result(self, result: str) -> None:
    """Print a slash-command result.

    Args:
      result: Command output text.
    """
    print(f"[command] {result}")

  def output_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
    """Print a tool call.

    Args:
      tool_name: Name of the tool being called.
      args: Tool arguments.
    """
    print(f"[tool call] {tool_name}({args})")

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    """Print a tool result.

    Args:
      tool_name: Name of the tool.
      success: Whether the tool succeeded.
      result: Result text or error message.
    """
    print(f"[tool result] {tool_name} success={success}: {result}")

  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict[str, Any],
  ) -> None:
    """Print tool content metadata.

    Args:
      tool_name: Name of the tool.
      operation: Operation type.
      path: File path.
      content: Content text (may be None).
      content_type: MIME type of the content.
      metadata: Additional metadata.
    """
    print(f"[tool content] {tool_name} {operation} {path} ({content_type}) metadata={metadata}")

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    """Print turn statistics.

    Args:
      duration_ms: Duration in milliseconds.
      prompt_tokens: Number of prompt tokens.
      eval_tokens: Number of evaluation tokens.
    """
    print(f"[stats] {duration_ms}ms, prompt_tokens={prompt_tokens}, eval_tokens={eval_tokens}")

  def output_error(self, error: Exception, include_traceback: bool = False) -> None:
    """Print an error.

    Args:
      error: Exception that occurred.
      include_traceback: Whether to include traceback.
    """
    print(f"[error] {type(error).__name__}: {error}")

  def output_content(self, content: str, content_type: str = "text/plain") -> None:
    """Output content text directly (non-streaming).

    Args:
      content: Content text.
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

  def start_content_stream(self) -> None:
    """Start streaming content."""
    print("[content start]", end="")

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    """Stream a content chunk.

    Args:
      chunk: Content chunk.
      content_type: MIME type of content.
    """
    print(chunk, end="")

  def end_content_stream(self, total_length: int) -> None:
    """End streaming content.

    Args:
      total_length: Total content length.
    """
    print(f"\n[content end length={total_length}]")

  def start_thinking_stream(self) -> None:
    """Start streaming thinking."""
    print("[thinking start]", end="")

  def stream_thinking(self, chunk: str) -> None:
    """Stream a thinking chunk.

    Args:
      chunk: Thinking chunk.
    """
    print(chunk, end="")

  def end_thinking_stream(self, total_length: int) -> None:
    """End streaming thinking.

    Args:
      total_length: Total thinking length.
    """
    print(f"\n[thinking end length={total_length}]")


async def main() -> None:
  """Entry point for the custom handler example."""
  from unittest.mock import MagicMock

  ui = PrintUIHandler()
  bridge = UIBridge(ui)

  # Create a mock Agent for the example
  agent = MagicMock()
  agent.model = "llama3.2:latest"

  # Manually emit a realistic sequence of events. In a real application,
  # these would come from Agent.process().
  events: list[Event] = [
    TurnStartEvent(type=EventType.TURN_START, message="List the files."),
    ToolCallEvent(
      type=EventType.TOOL_CALL,
      tool_name="list",
      arguments={"path": ".", "recursive": False},
    ),
    ToolResultEvent(
      type=EventType.TOOL_RESULT,
      tool_name="list",
      result="README.md\nexamples/\n",
      success=True,
    ),
    ContentStartEvent(type=EventType.CONTENT_START),
    ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Here are the files:"),
    ContentEndEvent(type=EventType.CONTENT_END, total_length=17),
    TurnEndEvent(
      type=EventType.TURN_END,
      response="Here are the files:",
      prompt_eval_count=120,
      eval_count=8,
      total_duration_ms=450,
    ),
  ]

  await ui.start(agent)
  for event in events:
    await bridge(event)
  await ui.shutdown("complete")


if __name__ == "__main__":
  asyncio.run(main())
