"""Event serialization and recording for Yoker sessions.

Provides functions to serialize/deserialize events to/from JSON-serializable
dictionaries and an EventRecorder class for writing events to JSONL files.

This module is part of the Event System (domain layer), providing
session persistence for replay, debugging, and testing.
"""

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from yoker.events.types import (
  AgentFinishedEvent,
  AgentMessageEvent,
  AgentSpawnedEvent,
  CommandEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  Event,
  EventType,
  SessionEndEvent,
  SessionStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  ToolCallEvent,
  ToolContentEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)

# Mapping from EventType to its dataclass. Used by deserialize_event to
# reconstruct events without per-type isinstance dispatch.
EVENT_CLASS_MAP: dict[EventType, type[Event]] = {
  EventType.TURN_START: TurnStartEvent,
  EventType.TURN_END: TurnEndEvent,
  EventType.THINKING_START: ThinkingStartEvent,
  EventType.THINKING_CHUNK: ThinkingChunkEvent,
  EventType.THINKING_END: ThinkingEndEvent,
  EventType.CONTENT_START: ContentStartEvent,
  EventType.CONTENT_CHUNK: ContentChunkEvent,
  EventType.CONTENT_END: ContentEndEvent,
  EventType.TOOL_CALL: ToolCallEvent,
  EventType.TOOL_RESULT: ToolResultEvent,
  EventType.TOOL_CONTENT: ToolContentEvent,
  EventType.COMMAND: CommandEvent,
  EventType.SESSION_START: SessionStartEvent,
  EventType.SESSION_END: SessionEndEvent,
  EventType.AGENT_SPAWNED: AgentSpawnedEvent,
  EventType.AGENT_FINISHED: AgentFinishedEvent,
  EventType.AGENT_MESSAGE: AgentMessageEvent,
}


def serialize_event(event: Event) -> dict[str, Any]:
  """Serialize an event to a JSON-serializable dictionary.

  Uses :func:`dataclasses.asdict` to convert the event dataclass into a
  dict, then strips the ``type`` and ``timestamp`` envelope fields (which
  are returned separately as part of the wrapper). The remaining dict is
  the event's data payload.

  Args:
    event: The event to serialize.

  Returns:
    Dictionary with ``type``, ``timestamp``, and ``data`` keys.
  """
  full = dataclasses.asdict(event)
  # Extract and remove envelope fields; everything else is event data.
  full.pop("type", None)
  full.pop("timestamp", None)
  return {
    "type": event.type.name,
    "timestamp": event.timestamp.isoformat(),
    "data": full,
  }


def deserialize_event(entry: dict[str, Any]) -> Event:
  """Deserialize a dictionary back to an event object.

  Looks up the event class via :data:`EVENT_CLASS_MAP` and constructs it
  directly from the stored data plus the envelope fields, avoiding per-type
  dispatch.

  Args:
    entry: Dictionary with ``type``, ``timestamp``, and ``data`` keys.

  Returns:
    Reconstructed event object.

  Raises:
    KeyError: If required fields are missing.
    ValueError: If event type is unknown.
  """
  event_type = EventType[entry["type"]]
  event_class = EVENT_CLASS_MAP.get(event_type)
  if event_class is None:
    raise ValueError(f"Unknown event type: {event_type}")

  timestamp = datetime.fromisoformat(entry["timestamp"])
  data = entry.get("data", {})
  # Reconstruct with envelope + data fields in one shot.
  return event_class(type=event_type, timestamp=timestamp, **data)


class EventRecorder:
  """Records all events to a JSONL file for replay.

  This class is an event handler that can be registered with an Agent
  to capture all events to a JSONL file. The file can later be replayed
  using EventReplayAgent.

  Example:
    agent = Agent(config=config)
    recorder = EventRecorder(Path("session.jsonl"))
    agent.add_event_handler(recorder)
    # ... run session ...
    recorder.close()
  """

  def __init__(self, path: Path) -> None:
    """Initialize the event recorder.

    Args:
      path: Path to the JSONL file to write.
    """
    self.path = path
    self.file = open(path, "w")  # noqa: SIM115 - will be closed in close()

  def __call__(self, event: Event) -> None:
    """Handle an event by recording it to the file.

    Args:
      event: The event to record.
    """
    entry = serialize_event(event)
    self.file.write(json.dumps(entry) + "\n")
    self.file.flush()

  def close(self) -> None:
    """Close the recording file."""
    self.file.close()


__all__ = [
  "serialize_event",
  "deserialize_event",
  "EventRecorder",
  "EVENT_CLASS_MAP",
]
