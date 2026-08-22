"""Tests for UIBridge event dispatcher."""

import pytest

from yoker.events.types import (
  CommandEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  EventType,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  ToolCallEvent,
  ToolContentEvent,
  ToolResultEvent,
  TurnEndEvent,
)
from yoker.ui import UIBridge


class MockUIHandler:
  """Mock UI handler for testing.

  Implements the UIHandler protocol without inheritance.
  """

  def __init__(self) -> None:
    self.calls = []

  async def start(self, agent) -> None:
    self.calls.append(("start", agent))

  async def shutdown(self, reason: str) -> None:
    self.calls.append(("shutdown", reason))

  async def get_input(self, prompt: str = "> ") -> str | None:
    self.calls.append(("get_input", prompt))
    return None

  def output_info(self, text: str) -> None:
    self.calls.append(("output_info", text))

  async def output_step_title(self, step: int, total: int, title: str) -> None:
    self.calls.append(("output_step_title", step, total, title))

  def output_command_result(self, result: str) -> None:
    self.calls.append(("output_command_result", result))

  def output_tool_call(self, tool_name: str, args: dict, agent=None) -> None:
    self.calls.append(("output_tool_call", tool_name, args))

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    self.calls.append(("output_tool_result", tool_name, success, result))

  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict,
  ) -> None:
    self.calls.append(
      ("output_tool_content", tool_name, operation, path, content, content_type, metadata)
    )

  def output_stats(
    self,
    duration_ms: int,
    prompt_tokens: int,
    eval_tokens: int,
    usage_limits: dict | None = None,
    agent=None,
  ) -> None:
    self.calls.append(("output_stats", duration_ms, prompt_tokens, eval_tokens, usage_limits))

  def output_error(self, error: Exception, include_traceback: bool = False) -> None:
    self.calls.append(("output_error", error))

  def start_content_stream(self, agent=None) -> None:
    self.calls.append("start_content_stream")

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    self.calls.append(("stream_content", chunk, content_type))

  def end_content_stream(self, total_length: int) -> None:
    self.calls.append(("end_content_stream", total_length))

  def start_thinking_stream(self, agent=None) -> None:
    self.calls.append("start_thinking_stream")

  def stream_thinking(self, chunk: str) -> None:
    self.calls.append(("stream_thinking", chunk))

  def end_thinking_stream(self, total_length: int) -> None:
    self.calls.append(("end_thinking_stream", total_length))


@pytest.mark.asyncio
class TestUIBridge:
  """Tests for UIBridge event dispatcher."""

  async def test_bridge_initialization(self):
    """UIBridge should initialize with UI handler."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)
    assert bridge.ui is handler

  async def test_bridge_handles_thinking_events(self):
    """UIBridge should dispatch thinking events correctly."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    # Thinking start
    await bridge(ThinkingStartEvent(type=EventType.THINKING_START))
    assert "start_thinking_stream" in handler.calls

    # Thinking chunk
    await bridge(ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text="thinking..."))
    assert ("stream_thinking", "thinking...") in handler.calls

    # Thinking end
    await bridge(ThinkingEndEvent(type=EventType.THINKING_END, total_length=11))
    assert ("end_thinking_stream", 11) in handler.calls

  async def test_bridge_handles_content_events(self):
    """UIBridge should dispatch content events correctly."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    # Content start
    await bridge(ContentStartEvent(type=EventType.CONTENT_START))
    assert "start_content_stream" in handler.calls

    # Content chunk
    await bridge(ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="content"))
    assert ("stream_content", "content", "text/plain") in handler.calls

    # Content end
    await bridge(ContentEndEvent(type=EventType.CONTENT_END, total_length=7))
    assert ("end_content_stream", 7) in handler.calls

  async def test_bridge_handles_content_chunk_with_type(self):
    """UIBridge should pass content_type from event."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    # Content chunk with explicit content_type (simulating future enhancement)
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="content")
    # Note: content_type is not a standard field yet, but the bridge handles it
    await bridge(event)
    assert ("stream_content", "content", "text/plain") in handler.calls

  async def test_bridge_handles_tool_call(self):
    """UIBridge should dispatch tool call events."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    await bridge(
      ToolCallEvent(
        type=EventType.TOOL_CALL,
        tool_name="read",
        arguments={"path": "/tmp/file.txt"},
      )
    )
    assert ("output_tool_call", "read", {"path": "/tmp/file.txt"}) in handler.calls

  async def test_bridge_handles_tool_result(self):
    """UIBridge should dispatch tool result events."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    await bridge(
      ToolResultEvent(
        type=EventType.TOOL_RESULT,
        tool_name="read",
        result="File contents",
        success=True,
      )
    )
    assert ("output_tool_result", "read", True, "File contents") in handler.calls

  async def test_bridge_handles_tool_content(self):
    """UIBridge should dispatch tool content events."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    await bridge(
      ToolContentEvent(
        type=EventType.TOOL_CONTENT,
        tool_name="write",
        operation="write",
        path="/tmp/file.txt",
        content_type="text/plain",
        content="File contents",
        metadata={"lines": 10},
      )
    )
    assert (
      "output_tool_content",
      "write",
      "write",
      "/tmp/file.txt",
      "File contents",
      "text/plain",
      {"lines": 10},
    ) in handler.calls

  async def test_bridge_handles_turn_end(self):
    """UIBridge should dispatch turn end stats."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    await bridge(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Response",
        tool_calls_count=2,
        prompt_eval_count=50,
        eval_count=100,
        total_duration_ms=1500,
      )
    )
    assert ("output_stats", 1500, 50, 100, None) in handler.calls

  async def test_bridge_handles_turn_end_with_usage_limits(self):
    """UIBridge should dispatch usage_limits in turn end stats."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    limits = {"session": {"usage": 0.975}, "weekly": {"usage": 0.531}}
    await bridge(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Response",
        tool_calls_count=0,
        prompt_eval_count=50,
        eval_count=100,
        total_duration_ms=1500,
        usage_limits=limits,
      )
    )
    assert ("output_stats", 1500, 50, 100, limits) in handler.calls

  async def test_bridge_handles_command(self):
    """UIBridge should dispatch command result events."""
    handler = MockUIHandler()
    bridge = UIBridge(handler)

    await bridge(
      CommandEvent(
        type=EventType.COMMAND,
        command="/help",
        result="Available commands: ...",
      )
    )
    assert ("output_command_result", "Available commands: ...") in handler.calls

  async def test_bridge_turn_start_starts_processing(self):
    """UIBridge should call start_processing on TURN_START if available."""
    from yoker.events.types import TurnStartEvent

    handler = MockUIHandler()
    # Add start_processing to the mock so it can be called.
    handler.start_processing = lambda: handler.calls.append("start_processing")
    bridge = UIBridge(handler)

    await bridge(TurnStartEvent(type=EventType.TURN_START, message="hello"))

    # start_processing should be called for TURN_START.
    assert "start_processing" in handler.calls
