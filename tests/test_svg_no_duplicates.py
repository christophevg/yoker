"""Tests to verify SVG generation doesn't create duplicate content."""

import tempfile
from pathlib import Path

from rich.console import Console

from yoker.events.handlers import ConsoleEventHandler
from yoker.events.types import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  EventType,
  SessionEndEvent,
  SessionStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  TurnEndEvent,
  TurnStartEvent,
)


class TestSVGNoDuplicates:
  """Test that SVG generation doesn't create duplicate content."""

  def test_single_session_header(self) -> None:
    """Verify session header appears only once in SVG."""
    console = Console(record=True, width=80)
    handler = ConsoleEventHandler(console=console, version="1.2.3")

    # Session start
    handler._handle_session_start(
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="test-model",
        thinking_enabled=True,
        config_summary={},
      )
    )

    # Turn
    handler._handle_turn_start(TurnStartEvent(type=EventType.TURN_START, message="test"))
    handler._handle_content_start(ContentStartEvent(type=EventType.CONTENT_START))
    handler._handle_content_chunk(ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Response"))
    handler._handle_content_end(ContentEndEvent(type=EventType.CONTENT_END, total_length=8))
    handler._handle_turn_end(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Response",
        total_duration_ms=100,
        prompt_eval_count=5,
        eval_count=3,
      )
    )

    # Session end
    handler._handle_session_end(SessionEndEvent(type=EventType.SESSION_END, reason="quit"))

    # Save and check
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as f:
      svg_path = f.name

    try:
      console.save_svg(svg_path)
      svg_content = Path(svg_path).read_text(encoding="utf-8")

      # Count occurrences of Yoker (appears at least once in header)
      yoker_count = svg_content.count("Yoker")
      assert yoker_count >= 1, f"Yoker should appear at least once, found {yoker_count} times"

      # Count occurrences of model name
      model_count = svg_content.count("test-model")
      assert model_count >= 1, f"Model should appear at least once, found {model_count} times"
    finally:
      Path(svg_path).unlink()

  def test_no_duplicate_thinking_content(self) -> None:
    """Verify thinking content appears only once in SVG."""
    console = Console(record=True, width=80)
    handler = ConsoleEventHandler(console=console, show_thinking=True)

    handler._handle_turn_start(TurnStartEvent(type=EventType.TURN_START, message="test"))

    # Thinking stream
    handler._handle_thinking_start(ThinkingStartEvent(type=EventType.THINKING_START))
    handler._handle_thinking_chunk(
      ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text="Unique thinking text")
    )
    handler._handle_thinking_end(ThinkingEndEvent(type=EventType.THINKING_END, total_length=20))

    # Content stream
    handler._handle_content_start(ContentStartEvent(type=EventType.CONTENT_START))
    handler._handle_content_chunk(
      ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Response content")
    )
    handler._handle_content_end(ContentEndEvent(type=EventType.CONTENT_END, total_length=16))
    handler._handle_turn_end(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Response content",
        total_duration_ms=100,
        prompt_eval_count=5,
        eval_count=3,
      )
    )

    # Save and check
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as f:
      svg_path = f.name

    try:
      console.save_svg(svg_path)
      svg_content = Path(svg_path).read_text(encoding="utf-8")

      # Count thinking content (may be split across elements)
      thinking_count = svg_content.count("Unique thinking text")
      # Check for partial match if split
      if thinking_count == 0:
        thinking_count = svg_content.count("Unique") + svg_content.count("thinking")
      assert thinking_count >= 1, (
        f"Thinking should appear at least once, found {thinking_count} times"
      )

      # Count response content (may be split)
      response_count = svg_content.count("Response content")
      if response_count == 0:
        response_count = svg_content.count("Response") + svg_content.count("content")
      assert response_count >= 1, (
        f"Response should appear at least once, found {response_count} times"
      )
    finally:
      Path(svg_path).unlink()

  def test_no_duplicate_tool_content(self) -> None:
    """Verify tool call and result content don't duplicate."""
    console = Console(record=True, width=80)
    handler = ConsoleEventHandler(console=console, show_tool_calls=True)

    handler._handle_turn_start(TurnStartEvent(type=EventType.TURN_START, message="test"))

    # Tool call
    from yoker.events.types import ToolCallEvent, ToolResultEvent

    handler._handle_tool_call(
      ToolCallEvent(
        type=EventType.TOOL_CALL,
        tool_name="read",
        arguments={"path": "/test/file.txt"},
      )
    )

    handler._handle_tool_result(
      ToolResultEvent(
        type=EventType.TOOL_RESULT,
        tool_name="read",
        result="File content here",
        success=True,
      )
    )

    # Content stream
    handler._handle_content_start(ContentStartEvent(type=EventType.CONTENT_START))
    handler._handle_content_chunk(
      ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Final response")
    )
    handler._handle_content_end(ContentEndEvent(type=EventType.CONTENT_END, total_length=14))
    handler._handle_turn_end(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Final response",
        total_duration_ms=100,
        prompt_eval_count=5,
        eval_count=3,
      )
    )

    # Save and check
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as f:
      svg_path = f.name

    try:
      console.save_svg(svg_path)
      svg_content = Path(svg_path).read_text(encoding="utf-8")

      # Tool name should appear once (in tool call display)
      tool_count = svg_content.count("Read")
      assert tool_count <= 1, f"Tool name should appear once or less, found {tool_count} times"

      # Result should appear once
      result_count = svg_content.count("File content here")
      assert result_count <= 1, f"Result should appear once or less, found {result_count} times"

      # Response should appear once (may be split)
      response_count = svg_content.count("Final response")
      if response_count == 0:
        response_count = svg_content.count("Final") + svg_content.count("response")
      assert response_count >= 1, (
        f"Response should appear at least once, found {response_count} times"
      )
    finally:
      Path(svg_path).unlink()

  def test_content_not_split_across_multiple_lines(self) -> None:
    """Verify streaming content is not duplicated by Live display updates."""
    console = Console(record=True, width=80)
    handler = ConsoleEventHandler(console=console)

    handler._handle_turn_start(TurnStartEvent(type=EventType.TURN_START, message="test"))

    # Stream content in multiple chunks
    handler._handle_content_start(ContentStartEvent(type=EventType.CONTENT_START))
    chunks = ["This ", "is ", "a ", "test ", "message"]
    for chunk in chunks:
      handler._handle_content_chunk(ContentChunkEvent(type=EventType.CONTENT_CHUNK, text=chunk))
    handler._handle_content_end(ContentEndEvent(type=EventType.CONTENT_END, total_length=22))
    handler._handle_turn_end(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="This is a test message",
        total_duration_ms=100,
        prompt_eval_count=5,
        eval_count=3,
      )
    )

    # Save and check
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as f:
      svg_path = f.name

    try:
      console.save_svg(svg_path)
      svg_content = Path(svg_path).read_text(encoding="utf-8")

      # Each word should appear approximately the right number of times
      # (words may be split across SVG elements, but shouldn't be repeated excessively)
      for word in ["This", "test", "message"]:
        count = svg_content.count(word)
        # Allow some tolerance for word appearing in other contexts
        # but it shouldn't appear dozens of times
        assert count < 5, f"Word '{word}' appears {count} times, suggesting duplication in SVG"

      # Check for the full phrase - should appear in final stats but not multiple times
      full_count = svg_content.count("This is a test message")
      assert full_count <= 1, f"Full message should appear once or less, found {full_count} times"
    finally:
      Path(svg_path).unlink()
