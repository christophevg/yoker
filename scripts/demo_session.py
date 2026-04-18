#!/usr/bin/env python
"""Generate a terminal screenshot of a Yoker session.

This script runs a demo session with predefined messages and exports
the captured output as an SVG file showing the terminal interaction.

Usage:
    python scripts/demo_session.py              # Real LLM session
    python scripts/demo_session.py --log       # Real LLM + log conversation
    python scripts/demo_session.py --replay    # Replay from log (no LLM)

Output:
    media/session-YYYYMMDD-HHMMSS.svg - Timestamped screenshot
    media/session.svg -> latest       - Symlink to latest
    media/session.jsonl               - Conversation log (if --log used)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterator

from rich.console import Console

from yoker.agent import Agent
from yoker.commands import CommandRegistry, create_help_command, create_think_command
from yoker.config import load_config_with_defaults

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
  """Iterator that replays conversation from a JSONL file."""

  def __init__(self, jsonl_path: Path) -> None:
    self.messages: list[str] = []
    # Load user messages from JSONL
    with open(jsonl_path) as f:
      for line in f:
        entry = json.loads(line)
        if entry["role"] == "user":
          self.messages.append(entry["content"])
    self.index = 0

  def __call__(self, prompt: str) -> str:
    """Return next user message from the log."""
    if self.index >= len(self.messages):
      raise EOFError()
    message = self.messages[self.index]
    self.index += 1
    return message


class ConversationLogger:
  """Logs conversation to a JSONL file."""

  def __init__(self, path: Path) -> None:
    self.path = path
    self.file = open(path, "w")  # noqa: SIM115 - will be closed in close()

  def log(self, role: str, content: str) -> None:
    """Log a message to the JSONL file."""
    entry = {"role": role, "content": content}
    self.file.write(json.dumps(entry) + "\n")
    self.file.flush()

  def close(self) -> None:
    """Close the log file."""
    self.file.close()


class LoggingAgent:
  """Agent wrapper that logs conversation."""

  def __init__(self, agent: Agent, logger: ConversationLogger) -> None:
    self.agent = agent
    self.logger = logger

  @property
  def model(self) -> str:
    return self.agent.model

  @property
  def thinking_enabled(self) -> bool:
    return self.agent.thinking_enabled

  @thinking_enabled.setter
  def thinking_enabled(self, value: bool) -> None:
    self.agent.thinking_enabled = value

  def process(self, message: str) -> str:
    """Process message and log conversation."""
    self.logger.log("user", message)
    response = self.agent.process(message)
    self.logger.log("assistant", response)
    return response


class MockAgent:
  """Mock agent that returns responses from a JSONL file."""

  def __init__(self, jsonl_path: Path, console: Console) -> None:
    self.console = console
    self.responses: list[str] = []
    self.index = 0
    self.thinking_enabled = True

    # Load assistant responses from JSONL
    with open(jsonl_path) as f:
      for line in f:
        entry = json.loads(line)
        if entry["role"] == "assistant":
          self.responses.append(entry["content"])

  def process(self, message: str) -> str:
    """Return next response from the log."""
    if self.index >= len(self.responses):
      return ""
    response = self.responses[self.index]
    self.index += 1
    return response

  @property
  def model(self) -> str:
    return "mock (replay)"


def run_demo_session(
  messages: list[str] | None = None,
  config_path: str | None = None,
  log: bool = False,
  replay: Path | None = None,
) -> Path:
  """Run a demo session and save as SVG.

  Args:
    messages: List of user messages (ignored if replay is set).
    config_path: Path to configuration file.
    log: Whether to log conversation to session.jsonl.
    replay: Path to JSONL file to replay (if set, no LLM calls).

  Returns:
    Path to the generated SVG file.
  """
  # Create console with recording enabled
  # Use width=80 for consistent line wrapping in SVG output
  console = Console(record=True, width=WRAP_WIDTH)

  # Create media directory
  MEDIA_DIR.mkdir(parents=True, exist_ok=True)

  # Determine agent and messages
  if replay:
    # Replay mode: use mock agent
    agent = MockAgent(replay, console)
    get_input = ReplayInput(replay)
    messages = []  # Will be read from file
  else:
    # Real LLM mode
    config = load_config_with_defaults(config_path)
    # Pass wrap_width to enable line wrapping in streaming output
    agent = Agent(config=config, console=console, wrap_width=WRAP_WIDTH)

    # Wrap with logger if requested
    if log:
      logger = ConversationLogger(MEDIA_DIR / "session.jsonl")
      agent = LoggingAgent(agent, logger)  # type: ignore

    # Create input function from messages
    if messages is None:
      messages = [
        "/help",
        "Summarize the README.md file in one sentence.",
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

  # Print session header
  console.print(f"[bold cyan]Yoker v0.1.0[/] - Using model: [green]{agent.model}[/]")
  thinking_status = "enabled" if agent.thinking_enabled else "disabled"
  console.print(f"[dim]Thinking mode: {thinking_status} (use /think on|off to toggle)[/]")
  console.print("[dim]Type /help for available commands.[/]")
  if replay:
    console.print("[dim]Replay mode - using logged conversation[/]")
  elif log:
    console.print("[dim]Logging conversation to session.jsonl[/]")
  console.print("")

  # Process each message
  for message in get_input.messages if hasattr(get_input, "messages") else []:
    console.print(f"[bold blue]>[/] {message}")

    # Check if this is a command
    if message.startswith("/"):
      result = command_registry.dispatch(message)
      if result:
        console.print(f"{result}\n")
      continue

    response = agent.process(message)
    if response:
      console.print()

  # Print session footer
  console.print("\n[bold cyan]Session complete.[/]")

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

  # Close logger if it was opened
  if log and not replay:
    logger.close()

  return timestamped_file


def main() -> None:
  """Run the demo session with example messages."""
  parser = argparse.ArgumentParser(
    description="Generate a terminal screenshot of a Yoker session.",
  )
  parser.add_argument(
    "--log",
    action="store_true",
    help="Log conversation to media/session.jsonl",
  )
  parser.add_argument(
    "--replay",
    type=Path,
    nargs="?",
    const=MEDIA_DIR / "session.jsonl",
    default=None,
    help="Replay conversation from JSONL file (default: media/session.jsonl)",
  )
  args = parser.parse_args()

  # Look for local config file
  config_path = Path("yoker.toml")
  if not config_path.exists():
    config_path = None

  # Run the demo
  run_demo_session(
    config_path=str(config_path) if config_path else None,
    log=args.log,
    replay=args.replay,
  )


if __name__ == "__main__":
  main()