#!/usr/bin/env python
"""Generate a terminal screenshot of a Yoker session.

This script runs a demo session with predefined messages and exports
the captured output as an SVG file showing the terminal interaction.

Usage:
    python scripts/demo_session.py

Output:
    media/session.svg - Terminal screenshot of the session
"""

from pathlib import Path

from rich.console import Console

from yoker.agent import Agent
from yoker.config import load_config_with_defaults

# Media directory for session screenshots
MEDIA_DIR = Path("media")
OUTPUT_FILE = MEDIA_DIR / "session.svg"


def run_demo_session(
  messages: list[str],
  config_path: str | None = None,
) -> Path:
  """Run a demo session and save as SVG.

  Args:
    messages: List of user messages to send to the agent.
    config_path: Path to configuration file (default: yoker.toml).

  Returns:
    Path to the generated SVG file.
  """
  # Load configuration
  config = load_config_with_defaults(config_path)

  # Create console with recording enabled
  console = Console(record=True)

  # Initialize agent with the recording console
  agent = Agent(config=config, console=console)

  # Print session header
  console.print(f"[bold cyan]Yoker v0.1.0[/] - Using model: [green]{agent.model}[/]")
  console.print("[dim]Demo session with predefined messages[/]\n")

  # Process each message
  for message in messages:
    console.print(f"[bold blue]>[/] {message}")
    response = agent.process(message)
    if response:
      console.print(f"\n{response}\n")

  # Print session footer
  console.print("\n[bold cyan]Session complete.[/]")

  # Create media directory
  MEDIA_DIR.mkdir(parents=True, exist_ok=True)

  # Save SVG
  console.save_svg(str(OUTPUT_FILE))

  console.print(f"\n[dim]Saved session to: {OUTPUT_FILE}[/]")

  return OUTPUT_FILE


def main() -> None:
  """Run the demo session with example messages."""
  # Look for local config file
  config_path = Path("yoker.toml")
  if not config_path.exists():
    config_path = None

  # Example messages for the demo
  messages = [
    "What files are in this directory?",
    "Read the README.md file",
  ]

  # Run the demo
  run_demo_session(
    messages=messages,
    config_path=str(config_path) if config_path else None,
  )


if __name__ == "__main__":
  main()