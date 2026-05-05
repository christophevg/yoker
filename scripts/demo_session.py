#!/usr/bin/env python
"""Generate terminal screenshots of Yoker sessions from demo scripts.

Demo scripts are defined as Markdown files with YAML frontmatter.
Each script specifies a sequence of user messages and an output path.
Multiple scripts can be defined for different features/tools.

Usage:
    python scripts/demo_session.py                    # Run default script (demos/session.md)
    python scripts/demo_session.py --script demos/list-tool.md
    python scripts/demo_session.py --scripts-dir demos/
    python scripts/demo_session.py --script demos/session.md --log
    python scripts/demo_session.py --script demos/session.md --replay
    python scripts/demo_session.py --output media/custom.svg

Output:
    Per-script SVG files defined in each demo script's frontmatter.
    Default script generates media/session.svg (with timestamped backup).
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
from yoker.demo import DemoScript, load_demo_script, load_demo_scripts
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

# Default demo script path
DEFAULT_SCRIPT = Path("demos/session.md")

# Console width for SVG output (Rich handles word-aware wrapping automatically)
# Set to 120 for wider output that fits modern displays
CONSOLE_WIDTH = 120


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


def _cleanup_temp_files() -> None:
  """Clean up temp files and directories created by demo scripts."""
  import shutil

  # Temp directories created by demos
  temp_dirs = [
    Path("/tmp/yoker-demo"),
    Path("/tmp/yoker-search-demo"),
  ]
  for temp_dir in temp_dirs:
    if temp_dir.exists():
      shutil.rmtree(temp_dir)

  # Temp files created by demos
  temp_files = [
    Path("/tmp/yoker-update-demo.txt"),
    Path("/tmp/yoker-demo.txt"),
    Path("/tmp/yoker-search-demo.py"),
  ]
  for temp_file in temp_files:
    if temp_file.exists():
      temp_file.unlink()


def run_demo_session(
  script: DemoScript,
  config_path: str | None = None,
  log: bool = False,
  replay: Path | None = None,
  agent_path: Path | None = None,
  persist: bool = False,
  resume: str | None = None,
  output: Path | None = None,
) -> Path:
  """Run a demo session from a script and save as SVG.

  Args:
    script: DemoScript with messages and output path.
    config_path: Path to configuration file.
    log: Whether to log events to the script's events file.
    replay: Path to events.jsonl file to replay (overrides script.events).
    agent_path: Path to agent definition file (Markdown with frontmatter).
    persist: Whether to persist session for resumption.
    resume: Session ID to resume (if set, loads previous session).
    output: Output path for SVG (overrides script.output).

  Returns:
    Path to the generated SVG file.
  """
  # Clean up temp files/directories before starting (ensure clean state)
  _cleanup_temp_files()

  # Create console with recording enabled
  # Rich handles word-aware wrapping automatically at this width
  console = Console(record=True, width=CONSOLE_WIDTH)

  # Create media directory
  MEDIA_DIR.mkdir(parents=True, exist_ok=True)

  # Determine output path
  if output:
    svg_path = output
    svg_path.parent.mkdir(parents=True, exist_ok=True)
  elif script.output:
    svg_path = Path(script.output)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
  else:
    # Fallback: timestamped file + symlink (old behavior)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    svg_path = MEDIA_DIR / f"session-{timestamp}.svg"
    current_link = MEDIA_DIR / "session.svg"
    if current_link.exists() or current_link.is_symlink():
      current_link.unlink()
    current_link.symlink_to(svg_path.name)

  # Determine events path
  events_path = replay if replay else (Path(script.events) if script.events else None)

  # Event recorder for --log mode
  event_recorder: EventRecorder | None = None

  # Initialize context manager (used in real LLM mode)
  context_manager: BasicPersistenceContextManager | None = None

  # Check replay mode BEFORE any file creation from --log
  is_replay_mode = events_path and events_path.exists()

  if is_replay_mode:
    # Replay mode: use EventReplayAgent to replay events
    agent = EventReplayAgent(events_path)
    # Attach console event handler for output
    handler = ConsoleEventHandler(
      console=console,
      show_thinking=agent.thinking_enabled,
      show_tool_calls=True,
      # No wrap_width - use Rich's natural word-aware wrapping
    )
    agent.add_event_handler(handler)
    get_input = ReplayInput(events_path)
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
      # No wrap_width - use Rich's natural word-aware wrapping
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
    if log and script.events:
      events_file = Path(script.events)
      events_file.parent.mkdir(parents=True, exist_ok=True)
      event_recorder = EventRecorder(events_file)
      agent.add_event_handler(event_recorder)

    # Create input function from script messages
    messages = list(script.messages)
    get_input = PredefinedInput(messages)

  # Create command registry
  command_registry = CommandRegistry()
  command_registry.register(create_help_command(command_registry))
  command_registry.register(
    create_think_command(
      get_thinking_mode=lambda: agent.thinking_mode,
      set_thinking_mode=lambda mode: setattr(agent, "thinking_mode", mode),
    )
  )

  # Begin session (emits SESSION_START event for real LLM mode)
  if not is_replay_mode:
    agent.begin_session()

  # Print mode-specific info
  if is_replay_mode:
    console.print(f"[bold cyan]Yoker v0.1.0[/] - Using model: [green]{agent.model}[/]")
    console.print("[dim]Replay mode - using logged events[/]")
    console.print("")
  elif log:
    console.print(f"[dim]Logging events to {script.events}[/]")

  # Process each message
  for message in get_input.messages if hasattr(get_input, "messages") else []:
    # User input should be plain text in the SVG recording
    # Use console.print with all Rich features disabled
    console.print(f"> {message}", markup=False, highlight=False)

    # Check if this is a command
    if message.startswith("/"):
      if is_replay_mode:
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
  if not (events_path and events_path.exists()):
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

  # Save SVG
  console.save_svg(str(svg_path))
  console.print(f"\n[dim]Saved session to: {svg_path}[/]")

  # Clean up temp files and directories after demo
  _cleanup_temp_files()

  # Close event recorder if it was opened
  if event_recorder is not None:
    event_recorder.close()

  return svg_path


def _resolve_script(args: argparse.Namespace) -> DemoScript:
  """Resolve which demo script to run from CLI arguments.

  Args:
    args: Parsed CLI arguments.

  Returns:
    DemoScript to run.

  Raises:
    SystemExit: If script cannot be resolved.
  """
  if args.script:
    return load_demo_script(args.script)

  if DEFAULT_SCRIPT.exists():
    return load_demo_script(DEFAULT_SCRIPT)

  print(f"Error: No script specified and default {DEFAULT_SCRIPT} not found.")
  print("Use --script to specify a demo script.")
  raise SystemExit(1)


def main() -> None:
  """Run demo session(s) from script files."""
  parser = argparse.ArgumentParser(
    description="Generate terminal screenshots of Yoker sessions from demo scripts.",
  )
  parser.add_argument(
    "--script",
    "-s",
    type=Path,
    default=None,
    help="Path to demo script Markdown file",
  )
  parser.add_argument(
    "--scripts-dir",
    "-d",
    type=Path,
    default=None,
    help="Run all demo scripts in directory",
  )
  parser.add_argument(
    "--log",
    action="store_true",
    help="Log events to script's events file",
  )
  parser.add_argument(
    "--replay",
    type=Path,
    nargs="?",
    const=None,
    default=None,
    help="Replay events from JSONL file (default: script's events path)",
  )
  parser.add_argument(
    "--agent",
    "-a",
    type=Path,
    default=None,
    help="Path to agent definition file (Markdown with YAML frontmatter)",
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
    help="Output path for SVG (overrides script default)",
  )
  args = parser.parse_args()

  # Look for local config file
  config_path = Path("yoker.toml")
  if not config_path.exists():
    config_path = None

  if args.scripts_dir:
    # Run all scripts in directory
    scripts = load_demo_scripts(args.scripts_dir)
    for title, script in scripts.items():
      print(f"\n{'=' * 60}")
      print(f"Running demo: {title}")
      print(f"{'=' * 60}")
      run_demo_session(
        script=script,
        config_path=str(config_path) if config_path else None,
        log=args.log,
        replay=args.replay,
        agent_path=args.agent,
        persist=args.persist,
        resume=args.resume,
        output=args.output,
      )
  else:
    # Run single script
    script = _resolve_script(args)
    run_demo_session(
      script=script,
      config_path=str(config_path) if config_path else None,
      log=args.log,
      replay=args.replay,
      agent_path=args.agent,
      persist=args.persist,
      resume=args.resume,
      output=args.output,
    )


if __name__ == "__main__":
  main()
