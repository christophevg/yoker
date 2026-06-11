"""Tests for BaseUIHandler abstract class."""

import pytest

from yoker.ui import BaseUIHandler


class ConcreteUIHandler(BaseUIHandler):
  """Concrete implementation for testing."""

  def __init__(self) -> None:
    super().__init__()
    self.started = False
    self.shutdown_reason = None
    self.inputs = []
    self.content_output = []
    self.command_results = []
    self.thinking_output = []
    self.tool_calls = []
    self.tool_results = []
    self.tool_content = []
    self.stats = []
    self.errors = []
    self.content_streams = []
    self.thinking_streams = []

  async def start(self, model: str, version: str, config: dict) -> None:
    self.started = True

  async def shutdown(self, reason: str) -> None:
    self.shutdown_reason = reason

  async def get_input(self, prompt: str = "> ") -> str | None:
    if self.inputs:
      return self.inputs.pop(0)
    return None

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)

  def output_tool_call(self, tool_name: str, args: dict) -> None:
    self.tool_calls.append((tool_name, args))

  def output_tool_result(self, tool_name: str, success: bool, result: str) -> None:
    self.tool_results.append((tool_name, success, result))

  def output_tool_content(
    self,
    tool_name: str,
    operation: str,
    path: str,
    content: str | None,
    content_type: str,
    metadata: dict,
  ) -> None:
    self.tool_content.append((tool_name, operation, path, content, content_type, metadata))

  def output_stats(self, duration_ms: int, prompt_tokens: int, eval_tokens: int) -> None:
    self.stats.append((duration_ms, prompt_tokens, eval_tokens))

  def output_error(self, error: Exception) -> None:
    self.errors.append(error)

  def start_content_stream(self) -> None:
    self.content_streams.append("start")

  def stream_content(self, chunk: str, content_type: str = "text/plain") -> None:
    self.content_streams.append(("chunk", chunk, content_type))

  def end_content_stream(self, total_length: int) -> None:
    self.content_streams.append(("end", total_length))

  def start_thinking_stream(self) -> None:
    self.thinking_streams.append("start")

  def stream_thinking(self, chunk: str) -> None:
    self.thinking_streams.append(("chunk", chunk))

  def end_thinking_stream(self, total_length: int) -> None:
    self.thinking_streams.append(("end", total_length))


class TestBaseUIHandler:
  """Tests for BaseUIHandler."""

  def test_initial_state(self):
    """BaseUIHandler should initialize with default state."""
    handler = ConcreteUIHandler()
    assert handler._turn_count == 0
    assert handler._streaming_content is False
    assert handler._streaming_thinking is False

  def test_start_turn(self):
    """_start_turn should increment turn count."""
    handler = ConcreteUIHandler()
    handler._start_turn()
    assert handler._turn_count == 1
    assert handler._streaming_content is False
    assert handler._streaming_thinking is False

    handler._start_turn()
    assert handler._turn_count == 2

  def test_end_turn(self):
    """_end_turn should reset streaming state."""
    handler = ConcreteUIHandler()
    handler._streaming_content = True
    handler._streaming_thinking = True

    handler._end_turn()
    assert handler._streaming_content is False
    assert handler._streaming_thinking is False

  def test_output_content_uses_streaming(self):
    """output_content should use streaming by default."""
    handler = ConcreteUIHandler()
    handler.output_content("Hello, world!", "text/plain")

    assert "start" in handler.content_streams
    assert ("chunk", "Hello, world!", "text/plain") in handler.content_streams
    assert ("end", 13) in handler.content_streams

  def test_output_thinking_uses_streaming(self):
    """output_thinking should use streaming by default."""
    handler = ConcreteUIHandler()
    handler.output_thinking("Thinking...")

    assert "start" in handler.thinking_streams
    assert ("chunk", "Thinking...") in handler.thinking_streams
    assert ("end", 11) in handler.thinking_streams

  @pytest.mark.asyncio
  async def test_lifecycle_methods(self):
    """start and shutdown should work correctly."""
    handler = ConcreteUIHandler()

    assert handler.started is False
    await handler.start("model", "1.0.0", {"thinking_enabled": True})
    assert handler.started is True

    assert handler.shutdown_reason is None
    await handler.shutdown("quit")
    assert handler.shutdown_reason == "quit"

  @pytest.mark.asyncio
  async def test_get_input(self):
    """get_input should return inputs in order."""
    handler = ConcreteUIHandler()
    handler.inputs = ["first", "second"]

    result1 = await handler.get_input()
    assert result1 == "first"

    result2 = await handler.get_input()
    assert result2 == "second"

    result3 = await handler.get_input()
    assert result3 is None

  def test_tool_methods(self):
    """Tool output methods should store data correctly."""
    handler = ConcreteUIHandler()

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})
    assert ("read", {"path": "/tmp/file.txt"}) in handler.tool_calls

    handler.output_tool_result("read", True, "File contents...")
    assert ("read", True, "File contents...") in handler.tool_results

    handler.output_tool_content(
      "write", "write", "/tmp/file.txt", "content", "text/plain", {"lines": 10}
    )
    assert (
      "write",
      "write",
      "/tmp/file.txt",
      "content",
      "text/plain",
      {"lines": 10},
    ) in handler.tool_content

  def test_stats_and_error(self):
    """Stats and error methods should store data correctly."""
    handler = ConcreteUIHandler()

    handler.output_stats(1000, 50, 100)
    assert (1000, 50, 100) in handler.stats

    error = ValueError("Test error")
    handler.output_error(error)
    assert error in handler.errors
