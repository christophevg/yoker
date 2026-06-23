"""Tests for UIHandler protocol and public API."""

from yoker.ui import (
  BatchUIHandler,
  InteractiveUIHandler,
  LiveDisplay,
  UIBridge,
  UIHandler,
  live_display,
)


class TestUIHandlerPublicAPI:
  """Tests for UI module public API exports."""

  def test_all_classes_exported(self):
    """All expected classes should be importable from yoker.ui."""
    assert UIHandler is not None
    assert UIBridge is not None
    assert InteractiveUIHandler is not None
    assert BatchUIHandler is not None
    assert LiveDisplay is not None
    assert live_display is not None


class TestUIHandlerProtocol:
  """Tests for UIHandler protocol compliance."""

  def test_uohandler_is_protocol(self):
    """UIHandler should be a Protocol."""
    from typing import Protocol

    assert issubclass(UIHandler, Protocol)

  def test_uohandler_has_lifecycle_methods(self):
    """UIHandler should have lifecycle methods."""
    # Check that the protocol defines the required methods
    assert hasattr(UIHandler, "start")
    assert hasattr(UIHandler, "shutdown")

  def test_uohandler_has_input_methods(self):
    """UIHandler should have input methods."""
    assert hasattr(UIHandler, "get_input")

  def test_uohandler_has_output_methods(self):
    """UIHandler should have output methods."""
    assert hasattr(UIHandler, "output_content")
    assert hasattr(UIHandler, "output_command_result")
    assert hasattr(UIHandler, "output_thinking")
    assert hasattr(UIHandler, "output_tool_call")
    assert hasattr(UIHandler, "output_tool_result")
    assert hasattr(UIHandler, "output_tool_content")
    assert hasattr(UIHandler, "output_stats")
    assert hasattr(UIHandler, "output_error")

  def test_uohandler_has_streaming_methods(self):
    """UIHandler should have streaming methods."""
    assert hasattr(UIHandler, "start_content_stream")
    assert hasattr(UIHandler, "stream_content")
    assert hasattr(UIHandler, "end_content_stream")
    assert hasattr(UIHandler, "start_thinking_stream")
    assert hasattr(UIHandler, "stream_thinking")
    assert hasattr(UIHandler, "end_thinking_stream")
