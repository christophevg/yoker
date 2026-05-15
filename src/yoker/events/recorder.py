"""Event serialization and recording for Yoker sessions.

Provides functions to serialize/deserialize events to/from JSON-serializable
dictionaries and an EventRecorder class for writing events to JSONL files.

This module is part of the Event System (domain layer), providing
session persistence for replay, debugging, and testing.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from yoker.events.types import (
  CommandEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  ErrorEvent,
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


def serialize_event(event: Event) -> dict[str, Any]:
  """Serialize an event to a JSON-serializable dictionary.

  Args:
    event: The event to serialize.

  Returns:
    Dictionary with type, timestamp, and event data.
  """
  data: dict[str, Any] = {}
  timestamp = event.timestamp.isoformat()

  if isinstance(event, SessionStartEvent):
    data = {
      "model": event.model,
      "thinking_enabled": event.thinking_enabled,
      "config_summary": event.config_summary,
    }
  elif isinstance(event, SessionEndEvent):
    data = {"reason": event.reason}
  elif isinstance(event, TurnStartEvent):
    data = {"message": event.message}
  elif isinstance(event, TurnEndEvent):
    data = {"response": event.response, "tool_calls_count": event.tool_calls_count}
  elif isinstance(event, ThinkingChunkEvent):
    data = {"text": event.text}
  elif isinstance(event, ThinkingEndEvent):
    data = {"total_length": event.total_length}
  elif isinstance(event, ContentChunkEvent):
    data = {"text": event.text}
  elif isinstance(event, ContentEndEvent):
    data = {"total_length": event.total_length}
  elif isinstance(event, ToolCallEvent):
    data = {"tool_name": event.tool_name, "arguments": event.arguments}
  elif isinstance(event, ToolResultEvent):
    data = {
      "tool_name": event.tool_name,
      "result": event.result,
      "success": event.success,
    }
  elif isinstance(event, ErrorEvent):
    data = {
      "error_type": event.error_type,
      "message": event.message,
      "details": event.details,
    }
  elif isinstance(event, CommandEvent):
    data = {"command": event.command, "result": event.result}
  # ThinkingStartEvent, ContentStartEvent have no data fields

  return {"type": event.type.name, "timestamp": timestamp, "data": data}


def deserialize_event(entry: dict[str, Any]) -> Event:
  """Deserialize a dictionary back to an event object.

  Args:
    entry: Dictionary with type, timestamp, and event data.

  Returns:
    Reconstructed event object.

  Raises:
    KeyError: If required fields are missing.
    ValueError: If event type is unknown.
  """
  event_type = EventType[entry["type"]]
  timestamp = datetime.fromisoformat(entry["timestamp"])
  data = entry.get("data", {})

  match event_type:
    case EventType.SESSION_START:
      return SessionStartEvent(
        type=event_type,
        timestamp=timestamp,
        model=data["model"],
        thinking_enabled=data["thinking_enabled"],
        config_summary=data.get("config_summary", {}),
      )
    case EventType.SESSION_END:
      return SessionEndEvent(
        type=event_type,
        timestamp=timestamp,
        reason=data["reason"],
      )
    case EventType.TURN_START:
      return TurnStartEvent(
        type=event_type,
        timestamp=timestamp,
        message=data["message"],
      )
    case EventType.TURN_END:
      return TurnEndEvent(
        type=event_type,
        timestamp=timestamp,
        response=data["response"],
        tool_calls_count=data.get("tool_calls_count", 0),
      )
    case EventType.THINKING_START:
      return ThinkingStartEvent(type=event_type, timestamp=timestamp)
    case EventType.THINKING_CHUNK:
      return ThinkingChunkEvent(
        type=event_type,
        timestamp=timestamp,
        text=data["text"],
      )
    case EventType.THINKING_END:
      return ThinkingEndEvent(
        type=event_type,
        timestamp=timestamp,
        total_length=data["total_length"],
      )
    case EventType.CONTENT_START:
      return ContentStartEvent(type=event_type, timestamp=timestamp)
    case EventType.CONTENT_CHUNK:
      return ContentChunkEvent(
        type=event_type,
        timestamp=timestamp,
        text=data["text"],
      )
    case EventType.CONTENT_END:
      return ContentEndEvent(
        type=event_type,
        timestamp=timestamp,
        total_length=data["total_length"],
      )
    case EventType.TOOL_CALL:
      return ToolCallEvent(
        type=event_type,
        timestamp=timestamp,
        tool_name=data["tool_name"],
        arguments=data["arguments"],
      )
    case EventType.TOOL_RESULT:
      return ToolResultEvent(
        type=event_type,
        timestamp=timestamp,
        tool_name=data["tool_name"],
        result=data["result"],
        success=data.get("success", True),
      )
    case EventType.ERROR:
      return ErrorEvent(
        type=event_type,
        timestamp=timestamp,
        error_type=data["error_type"],
        message=data["message"],
        details=data.get("details", {}),
      )
    case EventType.COMMAND:
      return CommandEvent(
        type=event_type,
        timestamp=timestamp,
        command=data["command"],
        result=data["result"],
      )
    case EventType.TOOL_CONTENT:
      return ToolContentEvent(
        type=event_type,
        timestamp=timestamp,
        tool_name=data["tool_name"],
        operation=data["operation"],
        path=data["path"],
        content_type=data.get("content_type", "summary"),
        content=data.get("content"),
        metadata=data.get("metadata", {}),
      )
    case _:
      raise ValueError(f"Unknown event type: {event_type}")


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
]
