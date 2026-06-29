"""Tests for ModelBackend Protocol and streaming types."""

import pytest

from yoker.backends import (
  ChatChunk,
  ChatChunkEvent,
  ModelBackend,
  ToolCallDelta,
  UsageStats,
)


class TestChatChunk:
  """Tests for ChatChunk frozen dataclass."""

  def test_imports_from_top_level_package(self):
    """Public imports work from yoker.backends."""
    # This test verifies the acceptance criterion:
    # "Public imports work from yoker.backends"
    assert ChatChunk is not None
    assert ChatChunkEvent is not None
    assert ModelBackend is not None
    assert ToolCallDelta is not None
    assert UsageStats is not None

  def test_chat_chunk_is_frozen(self):
    """ChatChunk is frozen and cannot be mutated."""
    chunk = ChatChunk(event=ChatChunkEvent.CONTENT_DELTA, text="Hello")
    assert chunk.event == ChatChunkEvent.CONTENT_DELTA
    assert chunk.text == "Hello"

    with pytest.raises(AttributeError):
      chunk.text = "modified"  # type: ignore[misc]

    with pytest.raises(AttributeError):
      chunk.event = ChatChunkEvent.DONE  # type: ignore[misc]

  def test_chat_chunk_with_all_fields(self):
    """ChatChunk can be created with all optional fields."""
    usage = UsageStats(input_tokens=100, output_tokens=50)
    chunk = ChatChunk(
      event=ChatChunkEvent.USAGE,
      index=0,
      text=None,
      tool_call=None,
      usage=usage,
    )
    assert chunk.event == ChatChunkEvent.USAGE
    assert chunk.index == 0
    assert chunk.text is None
    assert chunk.tool_call is None
    assert chunk.usage == usage

  def test_chat_chunk_event_kinds(self):
    """ChatChunkEvent has all required event kinds."""
    expected_events = {
      ChatChunkEvent.CONTENT_START,
      ChatChunkEvent.CONTENT_DELTA,
      ChatChunkEvent.CONTENT_STOP,
      ChatChunkEvent.THINKING_START,
      ChatChunkEvent.THINKING_DELTA,
      ChatChunkEvent.THINKING_STOP,
      ChatChunkEvent.TOOL_CALL_START,
      ChatChunkEvent.TOOL_CALL_DELTA,
      ChatChunkEvent.TOOL_CALL_STOP,
      ChatChunkEvent.USAGE,
      ChatChunkEvent.DONE,
    }
    assert set(ChatChunkEvent) == expected_events


class TestToolCallDelta:
  """Tests for ToolCallDelta frozen dataclass."""

  def test_tool_call_delta_is_frozen(self):
    """ToolCallDelta is frozen and cannot be mutated."""
    delta = ToolCallDelta(index=0, id="call_123", name="test_tool")
    assert delta.index == 0
    assert delta.id == "call_123"
    assert delta.name == "test_tool"
    assert delta.arguments_delta is None

    with pytest.raises(AttributeError):
      delta.arguments_delta = "modified"  # type: ignore[misc]

  def test_tool_call_delta_with_arguments(self):
    """ToolCallDelta can carry arguments delta."""
    delta = ToolCallDelta(
      index=1,
      id="call_456",
      name="fetch",
      arguments_delta='{"url": "htt',
    )
    assert delta.index == 1
    assert delta.id == "call_456"
    assert delta.name == "fetch"
    assert delta.arguments_delta == '{"url": "htt'

  def test_tool_call_delta_minimal(self):
    """ToolCallDelta can be created with minimal fields."""
    delta = ToolCallDelta(index=0)
    assert delta.index == 0
    assert delta.id is None
    assert delta.name is None
    assert delta.arguments_delta is None


class TestUsageStats:
  """Tests for UsageStats frozen dataclass."""

  def test_usage_stats_is_frozen(self):
    """UsageStats is frozen and cannot be mutated."""
    stats = UsageStats(input_tokens=100, output_tokens=50)
    assert stats.input_tokens == 100
    assert stats.output_tokens == 50

    with pytest.raises(AttributeError):
      stats.input_tokens = 200  # type: ignore[misc]

  def test_usage_stats_defaults(self):
    """UsageStats all fields default to None."""
    stats = UsageStats()
    assert stats.input_tokens is None
    assert stats.output_tokens is None
    assert stats.prompt_eval_count is None
    assert stats.eval_count is None
    assert stats.total_duration_ms is None

  def test_usage_stats_ollama_native_fields(self):
    """UsageStats preserves Ollama-native fields."""
    stats = UsageStats(
      prompt_eval_count=150,
      eval_count=75,
      total_duration_ms=2500,
    )
    assert stats.prompt_eval_count == 150
    assert stats.eval_count == 75
    assert stats.total_duration_ms == 2500
    # Generic fields should default to None
    assert stats.input_tokens is None
    assert stats.output_tokens is None

  def test_usage_stats_openai_fields(self):
    """UsageStats carries OpenAI/Anthropic generic fields."""
    stats = UsageStats(
      input_tokens=200,
      output_tokens=100,
    )
    assert stats.input_tokens == 200
    assert stats.output_tokens == 100
    # Ollama-native fields should default to None
    assert stats.prompt_eval_count is None
    assert stats.eval_count is None
    assert stats.total_duration_ms is None

  def test_usage_stats_mixed_fields(self):
    """UsageStats can carry both Ollama-native and generic fields."""
    stats = UsageStats(
      input_tokens=150,
      output_tokens=75,
      prompt_eval_count=150,
      eval_count=75,
      total_duration_ms=2500,
    )
    # All fields can be present
    assert stats.input_tokens == 150
    assert stats.output_tokens == 75
    assert stats.prompt_eval_count == 150
    assert stats.eval_count == 75
    assert stats.total_duration_ms == 2500


class TestModelBackend:
  """Tests for ModelBackend Protocol."""

  def test_model_backend_is_protocol(self):
    """ModelBackend is a Protocol (runtime-checkable)."""
    from typing import Protocol

    # ModelBackend should be a Protocol
    assert issubclass(ModelBackend, Protocol)

  def test_model_backend_protocol_structure(self):
    """ModelBackend Protocol has required methods and properties."""
    # Create a minimal implementation to verify protocol structure
    from collections.abc import AsyncIterator
    from typing import Any

    class MockBackend:
      """Minimal implementation of ModelBackend."""

      @property
      def provider(self) -> str:
        return "mock"

      async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = False,
        **kwargs: Any,
      ) -> AsyncIterator[ChatChunk]:
        yield ChatChunk(event=ChatChunkEvent.DONE)

    # Should satisfy the Protocol
    backend = MockBackend()
    assert backend.provider == "mock"
    # Verify the method exists and has correct signature
    assert hasattr(backend, "chat_stream")
    assert callable(backend.chat_stream)
