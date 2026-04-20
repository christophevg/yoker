"""Entry point for running Yoker as a module.

Usage: python -m yoker [OPTIONS]

Options:
  -c, --config PATH    Path to configuration file (default: yoker.toml)
  -m, --model MODEL    Model to use (overrides config)
  -h, --help           Show this message and exit
"""

import argparse
import logging
from pathlib import Path

from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import PromptSession
from rich.logging import RichHandler

from yoker import __version__
from yoker.agent import Agent
from yoker.commands import CommandRegistry, create_help_command, create_think_command
from yoker.config import Config
from yoker.events import ConsoleEventHandler

# Default configuration file name
DEFAULT_CONFIG = "yoker.toml"

# History file for prompt_toolkit
HISTORY_FILE = Path.home() / ".yoker_history"


def create_prompt_session() -> PromptSession[str]:
  """Create a prompt session with multiline support.

  Returns:
    PromptSession configured for multiline input.
    - Enter submits the input
    - Meta+Enter (Esc+Enter) adds a newline

  Note: Shift+Enter is not distinguishable from Enter in most terminals,
  so we use Meta+Enter for multiline input instead.
  """
  from prompt_toolkit.key_binding import KeyPressEvent

  # Key bindings for multiline input
  kb = KeyBindings()

  @kb.add("enter")
  def _handle_enter(event: KeyPressEvent) -> None:
    """Enter submits the input."""
    event.current_buffer.validate_and_handle()

  @kb.add("escape", "enter")
  def _handle_meta_enter(event: KeyPressEvent) -> None:
    """Meta+Enter (Esc+Enter) adds a newline."""
    event.current_buffer.insert_text("\n")

  # Ensure history directory exists
  HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

  session: PromptSession[str] = PromptSession(
    history=FileHistory(str(HISTORY_FILE)),
    multiline=True,
    mouse_support=True,
    key_bindings=kb,
  )

  return session


def prompt_input(prompt: str, session: PromptSession[str]) -> str:
  """Get user input with prompt_toolkit.

  Args:
    prompt: The prompt string to display.
    session: PromptSession to use.

  Returns:
    User input string.
  """
  result: str = session.prompt(prompt)
  return result


def setup_logging(config: Config) -> None:
  """Configure logging based on configuration.

  Args:
    config: Configuration object.
  """
  log_level = getattr(logging, config.harness.log_level.upper(), logging.INFO)

  logging.basicConfig(
    level=log_level,
    format="%(name)s - %(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
  )

  # Silence noisy modules
  for module in ["httpx", "httpcore", "ollama"]:
    logging.getLogger(module).setLevel(logging.WARNING)


def create_command_registry(agent: Agent) -> CommandRegistry:
  """Create and populate the command registry.

  Args:
    agent: The agent instance (for state access).

  Returns:
    Populated CommandRegistry.
  """
  registry = CommandRegistry()

  # Register built-in commands
  registry.register(create_help_command(registry))
  registry.register(
    create_think_command(
      get_thinking_state=lambda: agent.thinking_enabled,
      set_thinking_state=lambda enabled: setattr(agent, "thinking_enabled", enabled),
    )
  )

  return registry


def main() -> None:
  """Run the interactive agent."""
  parser = argparse.ArgumentParser(
    prog="yoker",
    description="Yoker - A Python agent harness with configurable tools and guardrails.",
  )
  parser.add_argument(
    "-c",
    "--config",
    type=Path,
    default=None,
    help=f"Path to configuration file (default: {DEFAULT_CONFIG})",
  )
  parser.add_argument(
    "-m",
    "--model",
    type=str,
    default=None,
    help="Model to use (overrides config)",
  )

  args = parser.parse_args()

  # Load configuration
  config_path = args.config
  if config_path is None:
    # Try default config file
    default_path = Path(DEFAULT_CONFIG)
    if default_path.exists():
      config_path = default_path

  # Create agent
  if config_path is not None:
    from yoker.config import load_config

    config = load_config(config_path)
    print(f"Loaded configuration from: {config_path}")
  else:
    config = Config()
    print("Using default configuration")

  # Setup logging with config
  setup_logging(config)

  # Print startup info
  print(f"Yoker v{__version__}")
  print("=" * 40)

  # Create prompt session for interactive input
  session = create_prompt_session()

  # Create input function using prompt_toolkit
  def get_input(prompt_text: str) -> str:
    try:
      return prompt_input(prompt_text, session)
    except KeyboardInterrupt:
      raise EOFError from None

  # Create agent
  agent = Agent(model=args.model, config=config)

  # Create command registry with agent access
  command_registry = create_command_registry(agent)

  # Pass command registry to agent
  agent.command_registry = command_registry

  # Create and attach console handler
  console_handler = ConsoleEventHandler(
    show_thinking=True,
    show_tool_calls=True,
    version=__version__,
  )
  agent.add_event_handler(console_handler)

  # Start agent
  agent.start(get_input=get_input)


if __name__ == "__main__":
  main()
