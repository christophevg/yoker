"""Event replay agent for Yoker sessions.

Provides EventReplayAgent for replaying recorded sessions from JSONL files
without requiring LLM calls.

This module is part of the Event System (domain layer), enabling
session replay for demos, testing, and debugging.
"""

import inspect
import json
from pathlib import Path

from yoker.events.recorder import deserialize_event
from yoker.events.session_event import SessionEvent
from yoker.events.types import CommandEvent, Event, EventCallback, TurnEndEvent, TurnStartEvent


class EventReplayAgent:
  """Agent that replays events from a JSONL file.

  This class provides the same async interface as Agent but replays previously
  recorded events instead of calling the LLM. Useful for:

  - Generating screenshots without LLM costs
  - Testing event handlers
  - Debugging session flows

  Example:
    agent = EventReplayAgent(Path("session.jsonl"))
    agent.add_event_handler(lambda event: print(event))
    await agent.process("Hello")  # Replays events for "Hello" turn
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
    # A replay trace may contain bare events or SessionEvent envelopes
    # (MBI-007, PR #43 Clarification 9). The list holds either form.
    self.events: list[Event | SessionEvent] = []
    self.index = 0
    self.thinking_enabled = True
    self._model = "replay"
    self._handlers: list[EventCallback] = []

    with open(events_path) as f:
      for line in f:
        entry = json.loads(line)
        event = deserialize_event(entry)
        self.events.append(event)

  @property
  def model(self) -> str:
    """Return the model name from the recorded session."""
    return self._model

  @property
  def skill_registry(self) -> None:
    """Return None - replay agent doesn't have skills."""
    return None

  def add_event_handler(self, handler: "EventCallback") -> None:
    """Register an event handler for replay.

    Args:
      handler: Callable that receives Event objects.
    """
    self._handlers.append(handler)

  async def process(self, message: str) -> str:
    """Replay events for one turn.

    Finds the matching TURN_START event and replays all events
    until TURN_END, emitting them to registered handlers.

    Args:
      message: The user message (used to find matching turn).

    Returns:
      The response text from the replayed turn.
    """
    # Find the matching TURN_START event
    while self.index < len(self.events):
      evt = self.events[self.index]

      if isinstance(evt, TurnStartEvent) and evt.message == message:
        break

      self.index += 1
    else:
      # No matching turn found
      return ""

    response = ""
    while self.index < len(self.events):
      evt = self.events[self.index]

      await self._emit(evt)

      if isinstance(evt, TurnEndEvent):
        response = evt.response
        self.index += 1
        break

      self.index += 1

    return response

  async def replay_command(self, command: str) -> str:
    """Replay a command event.

    Finds the matching COMMAND event and emits it to handlers.

    Args:
      command: The command string (used to find matching event).

    Returns:
      The command result, or empty string if not found.
    """
    while self.index < len(self.events):
      evt = self.events[self.index]
      self.index += 1

      if isinstance(evt, CommandEvent):
        if evt.command == command:
          await self._emit(evt)
          return evt.result

    return ""

  async def _emit(self, event: Event | SessionEvent) -> None:
    """Emit an event to all registered handlers asynchronously.

    Supports both sync and async handlers for backward compatibility.
    Accepts either a bare :class:`Event` or a :class:`SessionEvent`
    envelope (MBI-007, PR #43 Clarification 9).

    Args:
      event: The event to emit (bare or envelope-wrapped).
    """
    for handler in self._handlers:
      try:
        call_fn = getattr(handler, "__call__", handler)  # noqa: B004
        if inspect.iscoroutinefunction(call_fn):
          await handler(event)  # type: ignore[misc]
        else:
          handler(event)
      except Exception:
        pass


__all__ = [
  "EventReplayAgent",
]
