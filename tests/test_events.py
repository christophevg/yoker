"""Tests for yoker events module."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture

from yoker.config import Config
from yoker.events import (
  CommandEvent,
  ContentChunkEvent,
  EventType,
  ThinkingChunkEvent,
  ToolCallEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)
from yoker.events.types import Event


class TestEventTypes:
  """Tests for event type definitions."""

  def test_event_type_values(self) -> None:
    """Test that all event types have unique values."""
    event_types = list(EventType)
    values = [et.value for et in event_types]
    assert len(values) == len(set(values))  # All unique

  def test_event_type_count(self) -> None:
    """Test that all expected event types exist."""
    expected = [
      "TURN_START",
      "TURN_END",
      "THINKING_START",
      "THINKING_CHUNK",
      "THINKING_END",
      "CONTENT_START",
      "CONTENT_CHUNK",
      "CONTENT_END",
      "TOOL_CALL",
      "TOOL_RESULT",
      "TOOL_CONTENT",
      "COMMAND",
    ]
    actual = [et.name for et in EventType]
    assert set(expected) == set(actual)


class TestEventClasses:
  """Tests for event dataclasses."""

  def test_turn_start_event(self) -> None:
    """Test TurnStartEvent creation."""
    event = TurnStartEvent(type=EventType.TURN_START, message="Hello")
    assert event.message == "Hello"
    assert event.type == EventType.TURN_START

  def test_turn_end_event(self) -> None:
    """Test TurnEndEvent creation."""
    event = TurnEndEvent(
      type=EventType.TURN_END,
      response="Hi there",
      tool_calls_count=2,
    )
    assert event.response == "Hi there"
    assert event.tool_calls_count == 2

  def test_thinking_chunk_event(self) -> None:
    """Test ThinkingChunkEvent creation."""
    event = ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text="thinking...")
    assert event.text == "thinking..."

  def test_content_chunk_event(self) -> None:
    """Test ContentChunkEvent creation."""
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Hello world")
    assert event.text == "Hello world"
    assert event.content_type == "text/plain"  # Default value

  def test_content_chunk_event_with_content_type(self) -> None:
    """Test ContentChunkEvent with custom content_type."""
    event = ContentChunkEvent(
      type=EventType.CONTENT_CHUNK,
      text="# Heading\n\nContent",
      content_type="text/markdown",
    )
    assert event.text == "# Heading\n\nContent"
    assert event.content_type == "text/markdown"

  def test_tool_call_event(self) -> None:
    """Test ToolCallEvent creation."""
    event = ToolCallEvent(
      type=EventType.TOOL_CALL,
      tool_name="read",
      arguments={"path": "/tmp/test.txt"},
    )
    assert event.tool_name == "read"
    assert event.arguments == {"path": "/tmp/test.txt"}

  def test_tool_result_event(self) -> None:
    """Test ToolResultEvent creation."""
    event = ToolResultEvent(
      type=EventType.TOOL_RESULT,
      tool_name="read",
      result="file contents",
      success=True,
    )
    assert event.tool_name == "read"
    assert event.result == "file contents"
    assert event.success is True

  def test_command_event(self) -> None:
    """Test CommandEvent creation."""
    event = CommandEvent(
      type=EventType.COMMAND,
      command="/help",
      result="Available commands:\n  /help - Show help",
    )
    assert event.command == "/help"
    assert event.result == "Available commands:\n  /help - Show help"
    assert event.type == EventType.COMMAND

  def test_events_are_frozen(self) -> None:
    """Test that events are immutable (frozen dataclasses)."""
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="test")
    with pytest.raises(AttributeError):
      event.text = "modified"  # type: ignore[misc]


class TestEventCollector:
  """Test helper to collect events."""

  def __init__(self) -> None:
    self.events: list[Event] = []

  def __call__(self, event: Event) -> None:
    self.events.append(event)


class TestAgentEventEmission:
  """Tests for Agent event emission."""

  def test_agent_emits_events_during_process(self, mocker: MockerFixture) -> None:
    """Test that Agent emits events during process()."""
    mock_client = mocker.MagicMock()

    class AsyncIter:
      """Helper class to create an async iterator from a list."""

      def __init__(self, items: list) -> None:
        self.items = items
        self.index = 0

      def __aiter__(self) -> "AsyncIter":
        return self

      async def __anext__(self) -> Any:
        if self.index >= len(self.items):
          raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item

    mock_chunk = mocker.MagicMock()
    mock_chunk.message.thinking = None
    mock_chunk.message.content = "Hello there"
    mock_chunk.message.tool_calls: list = []
    mock_chunk.done = True
    mock_chunk.prompt_eval_count = 10
    mock_chunk.eval_count = 20
    mock_chunk.total_duration = 100_000_000

    mock_client.chat = AsyncMock(return_value=AsyncIter([mock_chunk]))

    mocker.patch("yoker.agent.AsyncClient", return_value=mock_client)

    from yoker.agent import Agent

    agent = Agent(config=Config())
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Hi"))

    assert len(collector.events) > 0

    event_types = [e.type for e in collector.events]
    assert EventType.TURN_START in event_types
    assert EventType.TURN_END in event_types

  def test_agent_add_remove_handler(self) -> None:
    """Test adding and removing event handlers."""
    from yoker.agent import Agent

    agent = Agent(config=Config())

    def handler(event: Event) -> None:
      pass

    agent.add_event_handler(handler)
    assert handler in agent._event_handlers

    agent.remove_event_handler(handler)
    assert handler not in agent._event_handlers
