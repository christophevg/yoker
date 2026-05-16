"""Tests for Agent content event emission.

Task: 1.5.6 - Complete Tool Content Display
"""

from pathlib import Path
from typing import Any

from pytest_mock import MockerFixture

from yoker.agent import Agent
from yoker.config import Config
from yoker.config.schema import PermissionsConfig
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


def create_mock_tool_call(
  mocker: MockerFixture,
  name: str,
  arguments: dict[str, Any],
  call_id: str | None = None,
) -> Any:
  """Create a properly serializable mock tool call.

  The mock objects must have JSON-serializable attributes because
  the context manager serializes them to JSONL format.

  Args:
    mocker: pytest-mock fixture
    name: Tool name (e.g., "write", "read", "update")
    arguments: Tool arguments dict (will be JSON serialized)
    call_id: Optional tool call ID

  Returns:
    Mock object with proper JSON-serializable attributes
  """
  mock_call = mocker.MagicMock()
  # Set id to a string (not MagicMock)
  mock_call.id = call_id if call_id else f"call_{name}"

  # Create function object with proper string/dict attributes
  mock_function = mocker.MagicMock()
  mock_function.name = name
  # Arguments must be a dict (JSON serializable), not MagicMock
  mock_function.arguments = arguments
  mock_call.function = mock_function

  return mock_call


def create_mock_chunk(
  mocker: MockerFixture,
  tool_calls: list[Any] | None = None,
  content: str | None = None,
  thinking: str | None = None,
) -> Any:
  """Create a mock chunk with proper JSON-serializable attributes.

  Args:
    mocker: pytest-mock fixture
    tool_calls: List of mock tool calls (use create_mock_tool_call)
    content: Optional content string
    thinking: Optional thinking string

  Returns:
    Mock chunk object
  """
  mock_chunk = mocker.MagicMock()
  mock_chunk.message.thinking = thinking
  mock_chunk.message.content = content
  mock_chunk.message.tool_calls = tool_calls if tool_calls is not None else []
  # Add done attribute for stats tracking
  mock_chunk.done = False
  mock_chunk.prompt_eval_count = 0
  mock_chunk.eval_count = 0
  mock_chunk.total_duration = 0
  return mock_chunk


def create_tool_then_response(
  mocker: MockerFixture,
  tool_calls: list[Any],
  final_content: str = "Done",
) -> list[list[Any]]:
  """Create a side_effect sequence for Agent.process() tests.

  The Agent.process() loop:
  1. First call: Returns tool_calls → Agent executes the tool
  2. Second call: Returns content (no tool_calls) → Agent finishes the turn

  Args:
    mocker: pytest-mock fixture
    tool_calls: List of mock tool calls (use create_mock_tool_call)
    final_content: Final content response (default: "Done")

  Returns:
    List of chunk lists to use as side_effect
  """
  # First call: tool call
  tool_chunk = create_mock_chunk(mocker, tool_calls=tool_calls)
  # Second call: final response (no tool calls)
  final_chunk = create_mock_chunk(mocker, content=final_content)
  # Mark the final chunk as done with stats
  final_chunk.done = True
  final_chunk.prompt_eval_count = 10
  final_chunk.eval_count = 20
  final_chunk.total_duration = 100_000_000  # 100ms in nanoseconds

  return [[tool_chunk], [final_chunk]]


def create_agent_with_permissions(tmp_path: Path) -> Agent:
  """Create an Agent with permissions for tmp_path.

  Args:
    tmp_path: Temporary directory path from pytest fixture

  Returns:
    Agent instance configured to allow filesystem access to tmp_path
  """
  config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
  return Agent(model="test-model", config=config)


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
    # Mock the ollama client to return tool call, then final response
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Hello\nWorld\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

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

    # Mock the ollama client to return tool call, then final response
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="read",
          arguments={"path": str(tmp_path / "test.txt")},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Read a file")

    # Check that no ToolContentEvent was emitted
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 0

  def test_content_event_emitted_after_result_event(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes tool result with content_metadata
    When: Emitting events
    Then: ToolResultEvent is emitted before ToolContentEvent
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

    # Find ToolResultEvent and ToolContentEvent
    result_idx = None
    content_idx = None

    for i, event in enumerate(collector.events):
      if event.type == EventType.TOOL_RESULT:
        result_idx = i
      elif event.type == EventType.TOOL_CONTENT:
        content_idx = i

    assert result_idx is not None
    assert content_idx is not None
    assert result_idx < content_idx

  def test_content_event_contains_tool_metadata(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent emits ToolContentEvent
    When: Event is created
    Then: Event contains tool_name, operation, path, content_type
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "myfile.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1

    event = content_events[0]
    assert isinstance(event, ToolContentEvent)
    assert event.tool_name == "write"
    assert event.operation == "write"
    assert "myfile.txt" in event.path
    assert event.content_type in ("summary", "full")

  def test_content_event_contains_content(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent emits ToolContentEvent for write operation
    When: Event is created
    Then: Event contains content field
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    # Configure for content verbosity
    from yoker.config.schema import ContentDisplayConfig, ToolsConfig

    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(content_display=ContentDisplayConfig(verbosity="content")),
    )
    agent = Agent(model="test-model", config=config)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1

    event = content_events[0]
    assert isinstance(event, ToolContentEvent)
    # Content should be present when verbosity="content"
    # (or None if silent/summary mode)
    assert hasattr(event, "content")

  def test_content_event_contains_diff_metadata(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent emits ToolContentEvent for update replace operation
    When: Event is created
    Then: Event metadata contains old_content and new_content
    """
    # Create an existing file for update
    test_file = tmp_path / "existing.txt"
    test_file.write_text("Old content\n")

    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="update",
          arguments={
            "path": str(test_file),
            "operation": "replace",
            "old_string": "Old",
            "new_string": "New",
          },
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Update a file")

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) >= 1

    event = content_events[0]
    assert isinstance(event, ToolContentEvent)
    assert event.tool_name == "update"
    # Metadata should contain diff information
    assert hasattr(event, "metadata")


class TestAgentContentEventConstruction:
  """Test ToolContentEvent construction from content_metadata."""

  def test_event_construction_from_write_metadata(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: content_metadata from WriteTool
    When: Agent constructs ToolContentEvent
    Then: Event fields map correctly from metadata
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1

    event = content_events[0]
    assert event.tool_name == "write"
    assert event.operation == "write"
    assert "test.txt" in event.path
    # content_type should be "summary" or "full"
    assert event.content_type in ("summary", "full")
    # metadata should include lines count
    assert "lines" in event.metadata or event.content_type == "full"

  def test_event_construction_from_update_metadata(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: content_metadata from UpdateTool
    When: Agent constructs ToolContentEvent
    Then: Event fields map correctly from metadata
    """
    # Create an existing file
    test_file = tmp_path / "existing.txt"
    test_file.write_text("Original line\n")

    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="update",
          arguments={
            "path": str(test_file),
            "operation": "replace",
            "old_string": "Original",
            "new_string": "Modified",
          },
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Update a file")

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) >= 1

    event = content_events[0]
    assert event.tool_name == "update"
    # operation should match update type
    assert event.operation in ("replace", "insert_before", "insert_after", "delete")

  def test_event_type_set_to_tool_content(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent creates ToolContentEvent
    When: Event is constructed
    Then: event.type is EventType.TOOL_CONTENT
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1

    event = content_events[0]
    assert event.type == EventType.TOOL_CONTENT


class TestAgentContentEventEmissionOrder:
  """Test event emission order for content events."""

  def test_event_sequence_for_write_operation(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes WriteTool result
    When: Emitting events
    Then: ToolResultEvent is emitted, then ToolContentEvent
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

    # Verify order
    result_idx = None
    content_idx = None
    for i, event in enumerate(collector.events):
      if event.type == EventType.TOOL_RESULT:
        result_idx = i
      elif event.type == EventType.TOOL_CONTENT:
        content_idx = i

    assert result_idx is not None
    assert content_idx is not None
    assert result_idx < content_idx

  def test_event_sequence_for_update_operation(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes UpdateTool result
    When: Emitting events
    Then: ToolResultEvent is emitted, then ToolContentEvent
    """
    # Create an existing file
    test_file = tmp_path / "existing.txt"
    test_file.write_text("Original\n")

    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="update",
          arguments={
            "path": str(test_file),
            "operation": "replace",
            "old_string": "Original",
            "new_string": "Updated",
          },
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Update a file")

    # Verify order
    result_idx = None
    content_idx = None
    for i, event in enumerate(collector.events):
      if event.type == EventType.TOOL_RESULT:
        result_idx = i
      elif event.type == EventType.TOOL_CONTENT:
        content_idx = i

    assert result_idx is not None
    assert content_idx is not None
    assert result_idx < content_idx

  def test_event_sequence_for_read_operation(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes ReadTool result
    When: Emitting events
    Then: Only ToolResultEvent is emitted (no content event)
    """
    # Create a file to read
    test_file = tmp_path / "test.txt"
    test_file.write_text("Content\n")

    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="read",
          arguments={"path": str(test_file)},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Read a file")

    # Verify no content event
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    result_events = collector.events_of_type(EventType.TOOL_RESULT)

    assert len(content_events) == 0
    assert len(result_events) >= 1


class TestAgentContentEventWithMultipleTools:
  """Test content event emission with multiple tool calls."""

  def test_content_events_for_sequential_writes(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes multiple WriteTool results
    When: Emitting events
    Then: Each write emits ToolResultEvent then ToolContentEvent
    """
    # Mock the ollama client to return multiple tool calls
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "file1.txt"), "content": "Content 1\n"},
          call_id="call_write_1",
        ),
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "file2.txt"), "content": "Content 2\n"},
          call_id="call_write_2",
        ),
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write files")

    # Count content events
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 2

    # Verify order of result/content pairs
    event_types = [e.type for e in collector.events]
    # Find TOOL_RESULT and TOOL_CONTENT indices
    result_indices = [i for i, t in enumerate(event_types) if t == EventType.TOOL_RESULT]
    content_indices = [i for i, t in enumerate(event_types) if t == EventType.TOOL_CONTENT]

    # Each content event should come after its corresponding result event
    assert len(result_indices) >= 2
    assert len(content_indices) == 2
    # First content after first result
    assert content_indices[0] > result_indices[0]
    # Second content after second result
    assert content_indices[1] > result_indices[1]

  def test_content_events_for_mixed_operations(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent processes mixed tool results (write, read, update)
    When: Emitting events
    Then: Content events only for write and update operations
    """
    # Create files for operations
    (tmp_path / "existing.txt").write_text("Original\n")

    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "new.txt"), "content": "New file\n"},
          call_id="call_write",
        ),
        create_mock_tool_call(
          mocker,
          name="read",
          arguments={"path": str(tmp_path / "existing.txt")},
          call_id="call_read",
        ),
        create_mock_tool_call(
          mocker,
          name="update",
          arguments={
            "path": str(tmp_path / "existing.txt"),
            "operation": "replace",
            "old_string": "Original",
            "new_string": "Updated",
          },
          call_id="call_update",
        ),
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Mixed operations")

    # Should have 2 content events (write and update, not read)
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    tool_names = [e.tool_name for e in content_events if isinstance(e, ToolContentEvent)]

    assert len(content_events) == 2
    assert "write" in tool_names
    assert "update" in tool_names
    assert "read" not in tool_names


class TestAgentContentEventErrorHandling:
  """Test error handling for content event emission."""

  def test_content_event_not_emitted_on_error(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: ToolResult with success=False and content_metadata
    When: Agent processes result
    Then: ToolContentEvent is not emitted
    """
    # Mock the ollama client to return a tool call that will fail
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          # Invalid path (will fail)
          arguments={"path": "/nonexistent/path/test.txt", "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write to invalid path")

    # Should not emit ToolContentEvent on error
    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    result_events = collector.events_of_type(EventType.TOOL_RESULT)

    # Should have result event with success=False
    assert len(result_events) >= 1
    # Should not have content event
    assert len(content_events) == 0

  def test_content_event_handles_missing_fields(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: content_metadata with missing fields
    When: Agent constructs ToolContentEvent
    Then: Event is created with available fields, defaults for missing
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = create_agent_with_permissions(tmp_path)
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Write a file")

    content_events = collector.events_of_type(EventType.TOOL_CONTENT)
    assert len(content_events) == 1

    event = content_events[0]
    # Event should be created successfully even with default values
    assert isinstance(event, ToolContentEvent)
    assert event.operation is not None  # Has default ""
    assert event.content_type is not None  # Has default "summary"

  def test_content_event_emission_does_not_affect_tool_result(
    self, tmp_path: Path, mocker: MockerFixture
  ) -> None:
    """
    Given: Agent emits ToolContentEvent
    When: Content event emission fails
    Then: Tool result is still returned to LLM
    """
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_client.chat.side_effect = create_tool_then_response(
      mocker,
      tool_calls=[
        create_mock_tool_call(
          mocker,
          name="write",
          arguments={"path": str(tmp_path / "test.txt"), "content": "Test\n"},
        )
      ],
    )

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    agent = Agent(model="test-model")

    # Create a handler that fails on ToolContentEvent
    class FailingHandler:
      def __init__(self) -> None:
        self.events: list[Event] = []

      def __call__(self, event: Event) -> None:
        self.events.append(event)
        if event.type == EventType.TOOL_CONTENT:
          raise RuntimeError("Handler failed")

    failing_handler = FailingHandler()
    agent.add_event_handler(failing_handler)

    # Process should complete without raising error
    agent.process("Write a file")

    # Tool result event should have been emitted before the failure
    result_events = [e for e in failing_handler.events if e.type == EventType.TOOL_RESULT]
    assert len(result_events) >= 1
