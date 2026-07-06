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

from yoker.events.session_event import SessionEvent
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


def serialize_event(event: Event | SessionEvent) -> dict[str, Any]:
  """Serialize an event to a JSON-serializable dictionary.

  Uses :func:`dataclasses.asdict` to convert the event dataclass into a
  dict, then strips the ``type`` and ``timestamp`` envelope fields (which
  are returned separately as part of the wrapper). The remaining dict is
  the event's data payload.

  When the input is a :class:`SessionEvent` envelope, the wrapper is
  serialized alongside the inner event::

      {
        "session_event": True,
        "agent_id": "<source agent id>",
        "event": <serialize_event(inner)>,
      }

  Args:
    event: The event to serialize (bare ``Event`` or ``SessionEvent``).

  Returns:
    Dictionary with ``type``, ``timestamp``, and ``data`` keys (or the
    ``session_event`` envelope form for ``SessionEvent`` inputs).
  """
  if isinstance(event, SessionEvent):
    return {
      "session_event": True,
      "agent_id": event.agent_id,
      "event": serialize_event(event.event),
    }
  full = dataclasses.asdict(event)
  # Extract and remove envelope fields; everything else is event data.
  full.pop("type", None)
  full.pop("timestamp", None)
  return {
    "type": event.type.name,
    "timestamp": event.timestamp.isoformat(),
    "data": full,
  }


def deserialize_event(entry: dict[str, Any]) -> Event | SessionEvent:
  """Deserialize a dictionary back to an event object.

  Looks up the event class via :data:`EVENT_CLASS_MAP` and constructs it
  directly from the stored data plus the envelope fields, avoiding per-type
  dispatch.

  When the entry carries the ``session_event`` marker, the
  :class:`SessionEvent` envelope is reconstructed around the deserialized
  inner event.

  Args:
    entry: Dictionary with ``type``, ``timestamp``, and ``data`` keys, or
      the ``session_event`` envelope form.

  Returns:
    Reconstructed event object (bare ``Event`` or ``SessionEvent``).

  Raises:
    KeyError: If required fields are missing.
    ValueError: If event type is unknown.
  """
  if entry.get("session_event") is True:
    inner = deserialize_event(entry["event"])
    # Envelopes do not nest in practice (agents emit bare events; the
    # Session wraps them once). Narrow to Event for the dataclass field.
    assert not isinstance(inner, SessionEvent)
    return SessionEvent(agent_id=entry["agent_id"], event=inner)

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
