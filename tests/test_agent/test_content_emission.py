"""Tests for Agent content event emission.

Task: 1.5.6 - Complete Tool Content Display
"""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from yoker.agent import Agent
from yoker.backends import ChatChunk, ChatChunkEvent, ToolCallDelta, UsageStats
from yoker.config import Config, ContentDisplayConfig, PermissionsConfig, ToolsSharedConfig
from yoker.events import EventType, ToolContentEvent
from yoker.events.types import Event


class TestEventCollector:
  """Test helper to collect events."""

  def __init__(self) -> None:
    self.events: list[Event] = []

  def __call__(self, event: Event) -> None:
    self.events.append(event)

  def events_of_type(self, event_type: EventType) -> list[Event]:
    """Get all events of a specific type."""
    return [e for e in self.events if e.type == event_type]


async def _aiter_chunks(chunks: list[ChatChunk]) -> Any:
  """Async generator that yields ChatChunk instances."""
  for chunk in chunks:
    yield chunk


def create_tool_call_chunks(
  tool_name: str,
  tool_args: dict[str, Any],
  call_id: str | None = None,
) -> list[ChatChunk]:
  """Create ChatChunk sequence for a tool call.

  Args:
    tool_name: Tool name (e.g., "yoker:write")
    tool_args: Tool arguments dict
    call_id: Optional tool call ID

  Returns:
    List of ChatChunk instances representing tool call
  """
  import json

  idx = 0
  cid = call_id or f"call_{tool_name}"
  args_json = json.dumps(tool_args)

  return [
    ChatChunk(
      event=ChatChunkEvent.TOOL_CALL_START,
      index=idx,
      tool_call=ToolCallDelta(
        index=idx,
        id=cid,
        name=tool_name,
        arguments_delta=None,
      ),
    ),
    ChatChunk(
      event=ChatChunkEvent.TOOL_CALL_DELTA,
      index=idx,
      tool_call=ToolCallDelta(
        index=idx,
        id=cid,
        name=tool_name,
        arguments_delta=args_json,
      ),
    ),
    ChatChunk(
      event=ChatChunkEvent.TOOL_CALL_STOP,
      index=idx,
      tool_call=ToolCallDelta(
        index=idx,
        id=cid,
        name=tool_name,
        arguments_delta=None,
      ),
    ),
  ]


def create_content_chunks(content: str) -> list[ChatChunk]:
  """Create ChatChunk sequence for content.

  Args:
    content: Content string

  Returns:
    List of ChatChunk instances representing content
  """
  return [
    ChatChunk(event=ChatChunkEvent.CONTENT_START, index=0),
    ChatChunk(event=ChatChunkEvent.CONTENT_DELTA, index=0, text=content),
    ChatChunk(event=ChatChunkEvent.CONTENT_STOP, index=0),
  ]


def create_final_chunks(
  prompt_eval_count: int = 10,
  eval_count: int = 20,
  total_duration_ms: int = 100,
) -> list[ChatChunk]:
  """Create final ChatChunk sequence with usage stats.

  Args:
    prompt_eval_count: Prompt evaluation count
    eval_count: Evaluation count
    total_duration_ms: Total duration in milliseconds

  Returns:
    List of ChatChunk instances with usage and done
  """
  return [
    ChatChunk(
      event=ChatChunkEvent.USAGE,
      usage=UsageStats(
        prompt_eval_count=prompt_eval_count,
        eval_count=eval_count,
        total_duration_ms=total_duration_ms,
      ),
    ),
    ChatChunk(event=ChatChunkEvent.DONE),
  ]


def create_tool_then_response_chunks(
  tool_name: str,
  tool_args: dict[str, Any],
  final_content: str = "Done",
) -> list[list[ChatChunk]]:
  """Create side_effect sequence for Agent.process() tests.

  The Agent.process() loop:
  1. First call: Returns tool_calls -> Agent executes the tool
  2. Second call: Returns content (no tool_calls) -> Agent finishes the turn

  Args:
    tool_name: Tool name
    tool_args: Tool arguments
    final_content: Final content response

  Returns:
    List of chunk lists to use as side_effect
  """
  # First call: tool call
  tool_chunks = create_tool_call_chunks(tool_name, tool_args)

  # Second call: final response
  content_chunks = create_content_chunks(final_content)
  final_chunks = create_final_chunks()

  return [tool_chunks, content_chunks + final_chunks]


def create_agent_with_permissions(tmp_path: Path) -> Agent:
  """Create an Agent with permissions for tmp_path.

  Args:
    tmp_path: Temporary directory path from pytest fixture

  Returns:
    Agent instance configured to allow filesystem access to tmp_path
  """
  config = Config(
    permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
    tools_shared=ToolsSharedConfig(content_display=ContentDisplayConfig(verbosity="content")),
  )
  return Agent(config=config)


class TestAgentContentEventEmission:
  """Test Agent emission of ToolContentEvent when metadata present."""

  def test_agent_emits_content_event_when_metadata_present(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes tool result with content_metadata
    When: ToolResult contains content_metadata
    Then: Agent emits ToolContentEvent
    """
    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:write",
      tool_args={"path": str(tmp_path / "test.txt"), "content": "Hello\nWorld\n"},
    )

    # chat_stream returns an async generator
    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write a file"))

    # Check that ToolContentEvent was emitted
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1
    assert isinstance(content_events[0], ToolContentEvent)

  def test_agent_skips_content_event_when_metadata_absent(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes tool result without content_metadata
    When: ToolResult.content_metadata is None
    Then: Agent does not emit ToolContentEvent
    """
    # Create the file so read succeeds
    (tmp_path / "test.txt").write_text("content")

    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:read",
      tool_args={"path": str(tmp_path / "test.txt")},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Read a file"))

    # Check that no ToolContentEvent was emitted
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 0

  def test_content_event_emitted_after_result_event(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes tool with content_metadata
    When: Tool execution completes
    Then: ToolResultEvent is emitted before ToolContentEvent
    """
    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:write",
      tool_args={"path": str(tmp_path / "test.txt"), "content": "Hello\nWorld\n"},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write a file"))

    # Find positions of events
    result_indices = [i for i, e in enumerate(collector.events) if e.type == EventType.TOOL_RESULT]
    content_indices = [
      i for i, e in enumerate(collector.events) if e.type == EventType.TOOL_CONTENT
    ]

    # ToolResult should come before ToolContent
    assert len(result_indices) == 1
    assert len(content_indices) == 1
    assert result_indices[0] < content_indices[0]

  def test_content_event_contains_tool_metadata(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Tool execution produces content_metadata
    When: ToolContentEvent is emitted
    Then: Event contains operation, path, content_type from metadata
    """
    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:write",
      tool_args={"path": str(tmp_path / "test.txt"), "content": "Hello\nWorld\n"},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write a file"))

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1
    event = content_events[0]
    assert isinstance(event, ToolContentEvent)
    assert event.tool_name == "yoker:write"
    assert event.operation == "write"
    assert "test.txt" in event.path

  def test_content_event_contains_content(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: Tool execution produces content_metadata with content field
    When: ToolContentEvent is emitted
    Then: Event contains the content
    """
    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:write",
      tool_args={"path": str(tmp_path / "test.txt"), "content": "Hello\nWorld\n"},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write a file"))

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1
    event = content_events[0]
    # The content field contains the written content (truncated if needed)
    assert event.content is not None

  def test_content_event_contains_diff_metadata(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Tool execution produces content_metadata with diff info
    When: ToolContentEvent is emitted
    Then: Event contains lines/bytes metadata
    """
    # Create an existing file for update
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("Original content\n")

    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:update",
      tool_args={
        "path": str(existing_file),
        "operation": "replace",
        "old_string": "Original",
        "new_string": "Updated",
      },
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Update the file"))

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1
    event = content_events[0]
    assert event.operation == "replace"
    # Check for diff metadata (lines_modified is present in diff output)
    assert "lines_modified" in event.metadata


class TestAgentContentEventConstruction:
  """Tests for ToolContentEvent construction."""

  def test_event_construction_from_write_metadata(self) -> None:
    """
    Given: write tool produces metadata
    When: ToolContentEvent is created
    Then: Event fields are populated correctly
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="yoker:write",
      operation="write",
      path="/test/file.txt",
      content_type="text/plain",
      content="Hello World",
      metadata={"lines": 1, "bytes": 11, "is_new_file": True},
    )

    assert event.tool_name == "yoker:write"
    assert event.operation == "write"
    assert event.path == "/test/file.txt"
    assert event.content_type == "text/plain"
    assert event.content == "Hello World"
    assert event.metadata["lines"] == 1
    assert event.metadata["is_new_file"] is True

  def test_event_construction_from_update_metadata(self) -> None:
    """
    Given: update tool produces metadata
    When: ToolContentEvent is created
    Then: Event fields are populated correctly
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="yoker:update",
      operation="replace",
      path="/test/file.txt",
      content_type="text/x-diff",
      content="--- a/file.txt\n+++ b/file.txt\n-original\n+updated\n",
      metadata={"lines_added": 1, "lines_removed": 1, "is_overwrite": False},
    )

    assert event.tool_name == "yoker:update"
    assert event.operation == "replace"
    assert event.content_type == "text/x-diff"

  def test_event_type_set_to_tool_content(self) -> None:
    """
    Given: Any tool content event
    When: Event is created
    Then: type field is TOOL_CONTENT
    """
    event = ToolContentEvent(
      type=EventType.TOOL_CONTENT,
      tool_name="yoker:write",
      operation="write",
      path="/test/file.txt",
      content_type="text/plain",
    )

    assert event.type == EventType.TOOL_CONTENT


class TestAgentContentEventEmissionOrder:
  """Tests for event emission ordering."""

  def test_event_sequence_for_write_operation(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: Agent processes a write operation
    When: Events are emitted
    Then: Events follow correct sequence: ToolCall -> ToolResult -> ToolContent -> TurnEnd
    """
    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:write",
      tool_args={"path": str(tmp_path / "test.txt"), "content": "Hello\n"},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write a file"))

    # Verify event order
    event_types = [e.type for e in collector.events]

    # TurnStart should be first, TurnEnd last
    assert event_types[0] == EventType.TURN_START
    assert event_types[-1] == EventType.TURN_END

    # ToolCall should come before ToolResult
    call_idx = event_types.index(EventType.TOOL_CALL)
    result_idx = event_types.index(EventType.TOOL_RESULT)
    assert call_idx < result_idx

    # ToolContent should come after ToolResult
    content_idx = event_types.index(EventType.TOOL_CONTENT)
    assert result_idx < content_idx

  def test_event_sequence_for_update_operation(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: Agent processes an update operation
    When: Events are emitted
    Then: Events follow correct sequence
    """
    # Create an existing file
    (tmp_path / "existing.txt").write_text("Original content\n")

    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:update",
      tool_args={
        "path": str(tmp_path / "existing.txt"),
        "operation": "replace",
        "old_string": "Original",
        "new_string": "Updated",
      },
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Update the file"))

    # Verify event sequence
    event_types = [e.type for e in collector.events]
    call_idx = event_types.index(EventType.TOOL_CALL)
    result_idx = event_types.index(EventType.TOOL_RESULT)
    content_idx = event_types.index(EventType.TOOL_CONTENT)

    assert call_idx < result_idx < content_idx

  def test_event_sequence_for_read_operation(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: Agent processes a read operation (no content_metadata)
    When: Events are emitted
    Then: No ToolContent event is emitted
    """
    # Create the file to read
    (tmp_path / "test.txt").write_text("Hello World")

    # Create mock backend that returns tool call, then final response
    mock_backend = MagicMock()

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:read",
      tool_args={"path": str(tmp_path / "test.txt")},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Read the file"))

    # Verify no ToolContent event
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 0


class TestAgentContentEventWithMultipleTools:
  """Tests for ToolContentEvent with multiple tool executions."""

  def test_content_events_for_sequential_writes(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent executes multiple write operations
    When: Each write completes
    Then: Each produces a ToolContentEvent
    """
    # Create mock backend that returns first tool call, then second, then final
    mock_backend = MagicMock()
    mock_backend.provider = "ollama"

    first_chunks = create_tool_call_chunks(
      "yoker:write",
      {"path": str(tmp_path / "first.txt"), "content": "First file"},
    )
    second_chunks = create_tool_call_chunks(
      "yoker:write",
      {"path": str(tmp_path / "second.txt"), "content": "Second file"},
    )
    final_chunks = create_content_chunks("All done") + create_final_chunks()

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(first_chunks),
        _aiter_chunks(second_chunks),
        _aiter_chunks(final_chunks),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write two files"))

    # Two ToolContentEvents should be emitted
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 2

  def test_content_events_for_mixed_operations(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: Agent executes write then read operations
    When: Operations complete
    Then: Only write produces ToolContentEvent
    """
    # Create the file for reading
    (tmp_path / "readme.txt").write_text("Content to read")

    # Create mock backend that returns write, then read, then final
    mock_backend = MagicMock()
    mock_backend.provider = "ollama"

    write_chunks = create_tool_call_chunks(
      "yoker:write",
      {"path": str(tmp_path / "output.txt"), "content": "Written content"},
    )
    read_chunks = create_tool_call_chunks(
      "yoker:read",
      {"path": str(tmp_path / "readme.txt")},
    )
    final_chunks = create_content_chunks("Done") + create_final_chunks()

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(write_chunks),
        _aiter_chunks(read_chunks),
        _aiter_chunks(final_chunks),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write then read"))

    # Only one ToolContentEvent from write
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1
    assert content_events[0].operation == "write"


class TestAgentContentEventErrorHandling:
  """Tests for error handling during content event emission."""

  def test_content_event_not_emitted_on_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
    """
    Given: Tool execution fails with error
    When: ToolResult.success is False
    Then: ToolContentEvent is not emitted
    """
    # Point to a non-existent path
    nonexistent = tmp_path / "nonexistent" / "file.txt"

    # Create mock backend that returns tool call, then final
    mock_backend = MagicMock()
    mock_backend.provider = "ollama"

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:read",
      tool_args={"path": str(nonexistent)},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Read nonexistent file"))

    # No ToolContentEvent should be emitted for failed tool
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 0

  def test_content_event_handles_missing_fields(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Tool execution succeeds with minimal metadata
    When: ToolContentEvent is emitted
    Then: Event is created with default values
    """
    # Create mock backend that returns tool call, then final
    mock_backend = MagicMock()
    mock_backend.provider = "ollama"

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:write",
      tool_args={"path": str(tmp_path / "test.txt"), "content": "Hello"},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    asyncio.run(agent.process("Write a file"))

    # Event should have required fields even if metadata is sparse
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1
    event = content_events[0]
    assert event.tool_name == "yoker:write"
    assert event.operation == "write"
    assert event.path  # path should be present

  def test_content_event_emission_does_not_affect_tool_result(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Tool execution with content_metadata
    When: Content event emission fails
    Then: ToolResult event is still emitted correctly
    """
    # Create mock backend that returns tool call, then final
    mock_backend = MagicMock()
    mock_backend.provider = "ollama"

    chunks_sequence = create_tool_then_response_chunks(
      tool_name="yoker:write",
      tool_args={"path": str(tmp_path / "test.txt"), "content": "Hello"},
    )

    mock_backend.chat_stream = mocker.Mock(
      side_effect=[
        _aiter_chunks(chunks_sequence[0]),
        _aiter_chunks(chunks_sequence[1]),
      ]
    )

    mocker.patch("yoker.agent.create_backend", return_value=mock_backend)

    agent = create_agent_with_permissions(tmp_path)

    # Add a handler that might fail
    class FailingHandler:
      def __init__(self):
        self.events: list[Event] = []

      def __call__(self, event: Event) -> None:
        # Only fail on ToolContent events
        if event.type == EventType.TOOL_CONTENT:
          raise RuntimeError("Handler error")
        self.events.append(event)

    handler = FailingHandler()
    agent.add_event_handler(handler)

    # Should not raise - errors are caught in emit()
    asyncio.run(agent.process("Write a file"))

    # ToolResult should still be in the events
    result_events = [e for e in handler.events if e.type == EventType.TOOL_RESULT]
    assert len(result_events) == 1
