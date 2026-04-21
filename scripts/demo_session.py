#!/usr/bin/env python
"""Generate a terminal screenshot of a Yoker session.

This script runs a demo session with predefined messages and exports
the captured output as an SVG file showing the terminal interaction.

Usage:
    python scripts/demo_session.py              # Real LLM session
    python scripts/demo_session.py --log       # Real LLM + log conversation
    python scripts/demo_session.py --replay    # Replay from events (no LLM)
    python scripts/demo_session.py --persist  # Save session for resumption
    python scripts/demo_session.py --resume <session_id>  # Resume session

Output:
    media/session-YYYYMMDD-HHMMSS.svg - Timestamped screenshot
    media/session.svg -> latest       - Symlink to latest
    media/events.jsonl                - Event log (if --log used)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from yoker.agent import Agent, EventCallback
from yoker.commands import CommandRegistry, create_help_command, create_think_command
from yoker.config import load_config_with_defaults
from yoker.context import BasicPersistenceContextManager
from yoker.events import ConsoleEventHandler
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
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)

# Media directory for session screenshots
MEDIA_DIR = Path("media")

# Wrap width for SVG output
WRAP_WIDTH = 80


def _serialize_event(event: Event) -> dict[str, Any]:
  """Serialize an event to a JSON-serializable dictionary.

  Args:
    event: The event to serialize.

  Returns:
    Dictionary with type, timestamp, and event data.
  """
  data: dict[str, Any] = {}
  timestamp = event.timestamp.isoformat()

  match event.type:
    case EventType.SESSION_START:
      event = event  # type: ignore
      data = {
        "model": event.model,
        "thinking_enabled": event.thinking_enabled,
        "config_summary": event.config_summary,
      }
    case EventType.SESSION_END:
      event = event  # type: ignore
      data = {"reason": event.reason}
    case EventType.TURN_START:
      event = event  # type: ignore
      data = {"message": event.message}
    case EventType.TURN_END:
      event = event  # type: ignore
      data = {"response": event.response, "tool_calls_count": event.tool_calls_count}
    case EventType.THINKING_START:
      pass  # No data
    case EventType.THINKING_CHUNK:
      event = event  # type: ignore
      data = {"text": event.text}
    case EventType.THINKING_END:
      event = event  # type: ignore
      data = {"total_length": event.total_length}
    case EventType.CONTENT_START:
      pass  # No data
    case EventType.CONTENT_CHUNK:
      event = event  # type: ignore
      data = {"text": event.text}
    case EventType.CONTENT_END:
      event = event  # type: ignore
      data = {"total_length": event.total_length}
    case EventType.TOOL_CALL:
      event = event  # type: ignore
      data = {"tool_name": event.tool_name, "arguments": event.arguments}
    case EventType.TOOL_RESULT:
      event = event  # type: ignore
      data = {"tool_name": event.tool_name, "result": event.result, "success": event.success}
    case EventType.ERROR:
      event = event  # type: ignore
      data = {"error_type": event.error_type, "message": event.message, "details": event.details}
    case EventType.COMMAND:
      event = event  # type: ignore
      data = {"command": event.command, "result": event.result}

  return {"type": event.type.name, "timestamp": timestamp, "data": data}


def _deserialize_event(entry: dict[str, Any]) -> Event:
  """Deserialize a dictionary back to an event object.

  Args:
    entry: Dictionary with type, timestamp, and event data.

  Returns:
    Reconstructed event object.
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


class EventLogger:
  """Logs all events to a JSONL file for replay."""

  def __init__(self, path: Path) -> None:
    """Initialize the event logger.

    Args:
      path: Path to the JSONL file to write.
    """
    self.path = path
    self.file = open(path, "w")  # noqa: SIM115 - will be closed in close()

  def __call__(self, event: Event) -> None:
    """Handle an event by logging it to the file.

    Args:
      event: The event to log.
    """
    entry = _serialize_event(event)
    self.file.write(json.dumps(entry) + "\n")
    self.file.flush()

  def close(self) -> None:
    """Close the log file."""
    self.file.close()


class EventReplayAgent:
  """Agent that replays events from a JSONL file."""

  def __init__(self, events_path: Path) -> None:
    """Initialize the replay agent.

    Args:
      events_path: Path to the events.jsonl file.
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
        event = _deserialize_event(entry)
        self.events.append(event)

    # Extract model from first SESSION_START event
    for event in self.events:
      if event.type == EventType.SESSION_START:
        self._model = event.model  # type: ignore
        self.thinking_enabled = event.thinking_enabled  # type: ignore
        break

  @property
  def model(self) -> str:
    """Return the model name from the recorded session."""
    return self._model

  def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler (stored for later replay)."""
    self._handlers.append(handler)

  def begin_session(self) -> None:
    """No-op for replay agent - session already in event log."""
    pass

  def end_session(self, reason: str = "quit") -> None:
    """No-op for replay agent."""
    pass

  def process(self, message: str) -> str:
    """Replay events for one turn.

    Args:
      message: The user message (used to find matching turn).

    Returns:
      The response text from the replayed turn.
    """
    # Find TURN_START with matching message
    while self.index < len(self.events):
      event = self.events[self.index]
      self.index += 1

      if event.type == EventType.TURN_START:
        # Check if this matches our message
        if event.message == message:  # type: ignore
          break
      elif self.index == 1:  # No TURN_START found yet, just start from current
        break

    # Replay events until TURN_END
    response = ""
    while self.index < len(self.events):
      event = self.events[self.index]

      # Emit to handlers
      for handler in self._handlers:
        handler(event)

      # Capture response from TURN_END
      if event.type == EventType.TURN_END:
        response = event.response  # type: ignore
        self.index += 1  # Move past TURN_END
        break

      self.index += 1

    return response

  def replay_command(self, command: str) -> str:
    """Replay a command event.

    Args:
      command: The command string (used to find matching event).

    Returns:
      The command result.
    """
    # Find COMMAND event with matching command
    while self.index < len(self.events):
      event = self.events[self.index]
      self.index += 1

      if event.type == EventType.COMMAND:
        # Check if this matches our command
        if event.command == command:  # type: ignore
          # Emit to handlers
          for handler in self._handlers:
            handler(event)
          return event.result  # type: ignore

    return ""  # Command not found


class PredefinedInput:
  """Iterator that yields predefined messages and raises EOFError when done."""

  def __init__(self, messages: list[str]) -> None:
    self.messages = messages
    self.index = 0

  def __call__(self, prompt: str) -> str:
    """Return next message from the list."""
    if self.index >= len(self.messages):
      raise EOFError()
    message = self.messages[self.index]
    self.index += 1
    return message


class ReplayInput:
  """Iterator that extracts user messages from events.jsonl."""

  def __init__(self, events_path: Path) -> None:
    self.messages: list[str] = []
    # Load user messages from TURN_START events and CommandEvent events
    with open(events_path) as f:
      for line in f:
        entry = json.loads(line)
        if entry["type"] == "TURN_START":
          self.messages.append(entry["data"]["message"])
        elif entry["type"] == "COMMAND":
          self.messages.append(entry["data"]["command"])
    self.index = 0

  def __call__(self, prompt: str) -> str:
    """Return next user message from the log."""
    if self.index >= len(self.messages):
      raise EOFError()
    message = self.messages[self.index]
    self.index += 1
    return message


def run_demo_session(
  messages: list[str] | None = None,
  config_path: str | None = None,
  log: bool = False,
  replay: Path | None = None,
  agent_path: Path | None = None,
  persist: bool = False,
  resume: str | None = None,
) -> Path:
  """Run a demo session and save as SVG.

  Args:
    messages: List of user messages (ignored if replay is set).
    config_path: Path to configuration file.
    log: Whether to log events to events.jsonl.
    replay: Path to events.jsonl file to replay (if set, no LLM calls).
    agent_path: Path to agent definition file (Markdown with frontmatter).
    persist: Whether to persist session for resumption.
    resume: Session ID to resume (if set, loads previous session).

  Returns:
    Path to the generated SVG file.
  """
  # Create console with recording enabled
  # Use width=80 for consistent line wrapping in SVG output
  console = Console(record=True, width=WRAP_WIDTH)

  # Create media directory
  MEDIA_DIR.mkdir(parents=True, exist_ok=True)

  # Event logger for --log mode
  event_logger: EventLogger | None = None

  # Determine agent and messages
  if replay:
    # Replay mode: use EventReplayAgent to replay events
    agent = EventReplayAgent(replay)
    # Attach console event handler for output
    handler = ConsoleEventHandler(
      console=console,
      show_thinking=agent.thinking_enabled,
      show_tool_calls=True,
      wrap_width=WRAP_WIDTH,
    )
    agent.add_event_handler(handler)
    get_input = ReplayInput(replay)
    messages = []  # Will be read from file
  else:
    # Real LLM mode
    config = load_config_with_defaults(config_path)

    # Create context manager for persistence or resumption
    context_manager: BasicPersistenceContextManager | None = None
    if persist or resume:
      session_id = resume if resume else "auto"
      context_manager = BasicPersistenceContextManager(
        storage_path=Path(config.context.storage_path),
        session_id=session_id,
      )
      if resume:
        loaded = context_manager.load()
        if not loaded:
          console.print(f"[yellow]Warning: Session {resume} not found. Starting fresh.[/]\n")

    # Create agent with event-driven architecture
    agent = Agent(
      config=config,
      agent_path=agent_path,
      context_manager=context_manager,
    )
    # Attach console event handler for output
    handler = ConsoleEventHandler(
      console=console,
      show_thinking=True,
      show_tool_calls=True,
      wrap_width=WRAP_WIDTH,
    )
    agent.add_event_handler(handler)

    # Show agent info if loaded
    if agent.agent_definition:
      print(f"Loaded agent: {agent.agent_definition.name}")
      print(f"  Description: {agent.agent_definition.description}")
      print()

    # Show session info
    if context_manager:
      stats = context_manager.get_statistics()
      console.print(f"[dim]Session ID: {context_manager.get_session_id()}[/]")
      if resume and stats.turn_count > 0:
        console.print(
          f"[dim]Resumed: {stats.turn_count} turns, {stats.tool_call_count} tool calls[/]"
        )
      console.print("")

    # Add event logger if requested
    if log:
      event_logger = EventLogger(MEDIA_DIR / "events.jsonl")
      agent.add_event_handler(event_logger)

    # Create input function from messages
    if messages is None:
      messages = [
        "/help",
        "Summarize the README.md file in less than 10 lines.",
      ]
    get_input = PredefinedInput(messages)

  # Create command registry
  command_registry = CommandRegistry()
  command_registry.register(create_help_command(command_registry))
  command_registry.register(
    create_think_command(
      get_thinking_state=lambda: agent.thinking_enabled,
      set_thinking_state=lambda enabled: setattr(agent, "thinking_enabled", enabled),
    )
  )

  # Begin session (emits SESSION_START event for real LLM mode)
  if not replay:
    agent.begin_session()

  # Print mode-specific info (for replay mode, or additional info for log mode)
  if replay:
    console.print(f"[bold cyan]Yoker v0.1.0[/] - Using model: [green]{agent.model}[/]")
    console.print("[dim]Replay mode - using logged events[/]")
    console.print("")
  elif log:
    console.print("[dim]Logging events to events.jsonl[/]")

  # Process each message
  for message in get_input.messages if hasattr(get_input, "messages") else []:
    console.print(f"[bold blue]>[/] {message}")

    # Check if this is a command
    if message.startswith("/"):
      if replay:
        # Replay mode: emit CommandEvent from event log
        agent.replay_command(message)  # type: ignore
      else:
        # Real LLM mode: execute command and log it
        result = command_registry.dispatch(message)
        if result:
          console.print(f"{result}\n")
        # Log command event if logging is enabled
        if event_logger is not None:
          command_event = CommandEvent(
            type=EventType.COMMAND,
            command=message,
            result=result or "",
          )
          event_logger(command_event)
      continue

    response = agent.process(message)
    # In replay mode, events are emitted by EventReplayAgent
    # In real LLM mode, events are emitted by Agent
    # ConsoleEventHandler prints the output in both cases

  # End session (emits SESSION_END event for real LLM mode)
  if not replay:
    agent.end_session()

  # Print session footer
  console.print("\n[bold cyan]Session complete.[/]")

  # Show statistics if context manager was used
  if context_manager is not None:
    stats = context_manager.get_statistics()
    console.print(f"[dim]Session: {context_manager.get_session_id()}[/]")
    console.print(
      f"[dim]Statistics: {stats.turn_count} turns, "
      f"{stats.message_count} messages, {stats.tool_call_count} tool calls[/]"
    )

  # Generate timestamped filename
  timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
  timestamped_file = MEDIA_DIR / f"session-{timestamp}.svg"
  current_link = MEDIA_DIR / "session.svg"

  # Save timestamped SVG
  console.save_svg(str(timestamped_file))

  # Update symlink to latest
  if current_link.exists():
    current_link.unlink()
  current_link.symlink_to(timestamped_file.name)

  console.print(f"\n[dim]Saved session to: {timestamped_file}[/]")
  console.print(f"[dim]Latest: {current_link}[/]")

  # Close event logger if it was opened
  if event_logger is not None:
    event_logger.close()

  return timestamped_file


def main() -> None:
  """Run the demo session with example messages."""
  parser = argparse.ArgumentParser(
    description="Generate a terminal screenshot of a Yoker session.",
  )
  parser.add_argument(
    "--log",
    action="store_true",
    help="Log events to media/events.jsonl",
  )
  parser.add_argument(
    "--replay",
    type=Path,
    nargs="?",
    const=MEDIA_DIR / "events.jsonl",
    default=None,
    help="Replay events from JSONL file (default: media/events.jsonl)",
  )
  parser.add_argument(
    "--agent",
    "-a",
    type=Path,
    default=None,
    help="Path to agent definition file (Markdown with YAML frontmatter)",
  )
  parser.add_argument(
    "--message",
    "-m",
    type=str,
    action="append",
    default=None,
    help="Add a message to send (can be used multiple times)",
  )
  parser.add_argument(
    "--persist",
    action="store_true",
    help="Persist session for later resumption",
  )
  parser.add_argument(
    "--resume",
    type=str,
    default=None,
    help="Resume a previous session by ID",
  )
  args = parser.parse_args()

  # Look for local config file
  config_path = Path("yoker.toml")
  if not config_path.exists():
    config_path = None

  # Build messages if provided
  messages = args.message if args.message else None

  # Run the demo
  run_demo_session(
    config_path=str(config_path) if config_path else None,
    log=args.log,
    replay=args.replay,
    agent_path=args.agent,
    messages=messages,
    persist=args.persist,
    resume=args.resume,
  )


if __name__ == "__main__":
  main()
