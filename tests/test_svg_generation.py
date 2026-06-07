"""Tests for SVG generation without spinner."""

import tempfile
from pathlib import Path

from rich.console import Console

from yoker.events.handlers import ConsoleEventHandler
from yoker.events.spinner import LiveDisplay
from yoker.events.types import (
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  TurnEndEvent,
  TurnStartEvent,
)


class TestSVGGeneration:
  """Test that SVG generation doesn't capture intermediate spinner states."""

  def test_spinner_disabled_when_recording(self) -> None:
    """Verify spinner is disabled in LiveDisplay when console.record is True."""
    # Create console with recording enabled
    console = Console(record=True, width=80)
    display = LiveDisplay(console=console)

    # Check that LiveDisplay detected recording mode
    assert display._is_recording is True

  def test_spinner_enabled_when_not_recording(self) -> None:
    """Verify spinner is enabled in LiveDisplay when console.record is False."""
    # Create console without recording
    console = Console(record=False, width=80)
    display = LiveDisplay(console=console)

    # Check that LiveDisplay detected non-recording mode
    assert display._is_recording is False

  def test_svg_without_intermediate_spinner_updates(self) -> None:
    """Verify SVG generation doesn't include intermediate spinner updates.

    This test simulates a typical streaming sequence and verifies that
    when console.record=True, the spinner is not started during content streaming.
    """
    # Create console with recording enabled
    console = Console(record=True, width=80)
    handler = ConsoleEventHandler(console=console, show_thinking=True)

    # Simulate turn start
    from yoker.events.types import EventType

    handler._handle_turn_start(TurnStartEvent(type=EventType.TURN_START, message="test"))

    # Simulate thinking stream
    handler._handle_thinking_start(ThinkingStartEvent(type=EventType.THINKING_START))
    handler._handle_thinking_chunk(
      ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text="Thinking...")
    )
    handler._handle_thinking_end(ThinkingEndEvent(type=EventType.THINKING_END, total_length=13))

    # Simulate content stream
    handler._handle_content_start(ContentStartEvent(type=EventType.CONTENT_START))
    handler._handle_content_chunk(ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Hello "))
    handler._handle_content_chunk(ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="world"))
    handler._handle_content_end(ContentEndEvent(type=EventType.CONTENT_END, total_length=11))

    # Turn end
    handler._handle_turn_end(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="",
        total_duration_ms=1000,
        prompt_eval_count=10,
        eval_count=5,
      )
    )

    # Save SVG
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False) as f:
      svg_path = f.name

    try:
      console.save_svg(svg_path)

      # Read SVG and verify no spinner text
      svg_content = Path(svg_path).read_text(encoding="utf-8")

      # The SVG should NOT contain "Processing..." spinner text
      assert "Processing..." not in svg_content

      # The SVG should contain the actual content
      assert "Thinking..." in svg_content
      # Content is split across chunks, with non-breaking spaces (&#160;) in SVG
      assert "Hello" in svg_content
      assert "world" in svg_content
    finally:
      Path(svg_path).unlink()
