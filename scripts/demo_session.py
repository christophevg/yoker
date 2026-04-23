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

from rich.console import Console

from yoker.agent import Agent, EventCallback
from yoker.commands import CommandRegistry, create_help_command, create_think_command
from yoker.config import load_config_with_defaults
from yoker.context import BasicPersistenceContextManager
from yoker.events import (
  CommandEvent,
  ConsoleEventHandler,
  Event,
  EventRecorder,
  EventReplayAgent,
  EventType,
)

# Media directory for session screenshots
MEDIA_DIR = Path("media")

# Wrap width for SVG output
WRAP_WIDTH = 80


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
  output: Path | None = None,
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
    output: Output path for SVG (if set, no timestamp or symlink).

  Returns:
    Path to the generated SVG file.
  """
  # Create console with recording enabled
  # Use width=80 for consistent line wrapping in SVG output
  console = Console(record=True, width=WRAP_WIDTH)

  # Create media directory
  MEDIA_DIR.mkdir(parents=True, exist_ok=True)

  # Event recorder for --log mode
  event_recorder: EventRecorder | None = None

  # Determine agent and messages
  # Initialize context manager (used in real LLM mode)
  context_manager: BasicPersistenceContextManager | None = None

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

    # Add event recorder if requested
    if log:
      event_recorder = EventRecorder(MEDIA_DIR / "events.jsonl")
      agent.add_event_handler(event_recorder)

    # Create input function from messages
    if messages is None:
      messages = [
        "/help",
        "/think off",
        "Show files in the current folder whose name starts with an 'R'.",
        "/think on",
        "Summarize the README.md file in less than 5 lines.",
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
        if event_recorder is not None:
          command_event = CommandEvent(
            type=EventType.COMMAND,
            command=message,
            result=result or "",
          )
          event_recorder(command_event)
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

  # Determine output path
  if output:
    # Use specified output path directly
    svg_path = output
    # Ensure parent directory exists
    svg_path.parent.mkdir(parents=True, exist_ok=True)
  else:
    # Generate timestamped filename and symlink
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    timestamped_file = MEDIA_DIR / f"session-{timestamp}.svg"
    current_link = MEDIA_DIR / "session.svg"

    # Save timestamped SVG
    svg_path = timestamped_file

    # Update symlink to latest (handles broken symlinks)
    if current_link.exists() or current_link.is_symlink():
      current_link.unlink()
    current_link.symlink_to(timestamped_file.name)

    console.print(f"\n[dim]Saved session to: {timestamped_file}[/]")
    console.print(f"[dim]Latest: {current_link}[/]")

  # Save SVG
  console.save_svg(str(svg_path))

  if output:
    console.print(f"\n[dim]Saved session to: {svg_path}[/]")

  # Close event recorder if it was opened
  if event_recorder is not None:
    event_recorder.close()

  return svg_path


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
  parser.add_argument(
    "--output",
    "-o",
    type=Path,
    default=None,
    help="Output path for SVG (default: media/session-TIMESTAMP.svg)",
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
    output=args.output,
  )


if __name__ == "__main__":
  main()
