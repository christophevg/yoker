"""Event replay agent for Yoker sessions.

Provides EventReplayAgent for replaying recorded sessions from JSONL files
without requiring LLM calls.

This module is part of the Event System (domain layer), enabling
session replay for demos, testing, and debugging.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING

from yoker.events.recorder import deserialize_event
from yoker.events.types import (
  CommandEvent,
  Event,
  SessionStartEvent,
  TurnEndEvent,
  TurnStartEvent,
)

if TYPE_CHECKING:
  from yoker.agent import EventCallback


class EventReplayAgent:
  """Agent that replays events from a JSONL file.

  This class provides the same interface as Agent but replays previously
  recorded events instead of calling the LLM. Useful for:

  - Generating screenshots without LLM costs
  - Testing event handlers
  - Debugging session flows

  Example:
    agent = EventReplayAgent(Path("session.jsonl"))
    agent.add_event_handler(ConsoleEventHandler(console))
    agent.process("Hello")  # Replays events for "Hello" turn
  """

  def __init__(self, events_path: Path) -> None:
    """Initialize the replay agent.

    Args:
      events_path: Path to the events.jsonl file.

    Raises:
      FileNotFoundError: If events file doesn't exist.
      ValueError: If events file is invalid.
    """
    self.events_path = events_path
    self.events: list[Event] = []
    self.index = 0
    self.thinking_enabled = True
    self._model = "replay"
    self._handlers: list[EventCallback] = []

    # Load events from JSONL
    with open(events_path) as f:
      for line in f:
        entry = json.loads(line)
        event = deserialize_event(entry)
        self.events.append(event)

    # Extract model from first SESSION_START event
    for event in self.events:
      if isinstance(event, SessionStartEvent):
        self._model = event.model
        self.thinking_enabled = event.thinking_enabled
        break

  @property
  def model(self) -> str:
    """Return the model name from the recorded session."""
    return self._model

  def add_event_handler(self, handler: "EventCallback") -> None:
    """Register an event handler for replay.

    Args:
      handler: Callable that receives Event objects.
    """
    self._handlers.append(handler)

  def begin_session(self) -> None:
    """No-op for replay agent - session already in event log."""
    pass

  def end_session(self, reason: str = "quit") -> None:
    """No-op for replay agent."""
    pass

  def process(self, message: str) -> str:
    """Replay events for one turn.

    Finds the matching TURN_START event and replays all events
    until TURN_END, emitting them to registered handlers.

    Args:
      message: The user message (used to find matching turn).

    Returns:
      The response text from the replayed turn.
    """
    # Find TURN_START with matching message
    while self.index < len(self.events):
      evt = self.events[self.index]
      self.index += 1

      if isinstance(evt, TurnStartEvent):
        # Check if this matches our message
        if evt.message == message:
          break
      elif self.index == 1:  # No TURN_START found yet, just start from current
        break

    # Replay events until TURN_END
    response = ""
    while self.index < len(self.events):
      evt = self.events[self.index]

      # Emit to handlers
      for handler in self._handlers:
        handler(evt)

      # Capture response from TURN_END
      if isinstance(evt, TurnEndEvent):
        response = evt.response
        self.index += 1  # Move past TURN_END
        break

      self.index += 1

    return response

  def replay_command(self, command: str) -> str:
    """Replay a command event.

    Finds the matching COMMAND event and emits it to handlers.

    Args:
      command: The command string (used to find matching event).

    Returns:
      The command result, or empty string if not found.
    """
    # Find COMMAND event with matching command
    while self.index < len(self.events):
      evt = self.events[self.index]
      self.index += 1

      if isinstance(evt, CommandEvent):
        # Check if this matches our command
        if evt.command == command:
          # Emit to handlers
          for handler in self._handlers:
            handler(evt)
          return evt.result

    return ""  # Command not found


__all__ = [
  "EventReplayAgent",
]
