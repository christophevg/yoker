"""Entry point for running Yoker as a module.

Usage: python -m yoker [OPTIONS]

Options:
  -c, --config PATH    Path to configuration file (default: yoker.toml)
  -m, --model MODEL    Model to use (overrides config)
  -h, --help           Show this message and exit
"""

import argparse
from pathlib import Path

from ollama import ResponseError
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import PromptSession

from yoker import __version__
from yoker.agent import Agent
from yoker.commands import (
  CommandRegistry,
  create_context_command,
  create_help_command,
  create_think_command,
)
from yoker.config import Config
from yoker.events import (
  ConsoleEventHandler,
  ErrorEvent,
  EventType,
)
from yoker.logging import configure_logging, get_logger

# Default configuration file name
DEFAULT_CONFIG = "yoker.toml"

# History file for prompt_toolkit
HISTORY_FILE = Path.home() / ".yoker_history"

# Logger for this module
log = get_logger(__name__)


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
    mouse_support=False,  # Disable to allow terminal text selection
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

  Disables console output for interactive CLI to avoid interfering with
  the chat interface. Logs are only written to file if configured.

  Args:
    config: Configuration object.
  """
  log_file = None
  if config.logging.file:
    log_file = Path(config.logging.file)

  configure_logging(
    level=config.logging.level,
    log_file=log_file,
    format=config.logging.format,
    console=False,  # Disable console output for interactive CLI
  )

  log.info("logging_configured", level=config.logging.level)


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
      get_thinking_mode=lambda: agent.thinking_mode,
      set_thinking_mode=lambda mode: setattr(agent, "thinking_mode", mode),
    )
  )
  registry.register(
    create_context_command(
      get_session_id=lambda: agent.context.get_session_id(),
      get_statistics=lambda: agent.context.get_statistics(),
      get_messages=lambda: agent.context.get_messages(),
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
  parser.add_argument(
    "-a",
    "--agent",
    type=Path,
    default=None,
    help="Path to agent definition file (Markdown with YAML frontmatter)",
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

  # Create prompt session for interactive input
  session = create_prompt_session()

  # Create agent with optional agent definition
  agent = Agent(
    model=args.model,
    config=config,
    agent_path=args.agent,
  )

  # Show agent info if loaded
  if agent.agent_definition:
    print(f"Loaded agent: {agent.agent_definition.name}")
    print(f"  Description: {agent.agent_definition.description}")
    print(f"  Tools: {', '.join(agent.agent_definition.tools)}")
    print()

  # Create command registry with agent access
  command_registry = create_command_registry(agent)

  # Create and attach console handler
  console_handler = ConsoleEventHandler(
    show_thinking=True,
    show_tool_calls=True,
    version=__version__,
  )
  agent.add_event_handler(console_handler)

  # Begin session
  agent.begin_session()

  try:
    while True:
      try:
        user_input = prompt_input("> ", session)
      except EOFError:
        agent.end_session(reason="quit")
        break
      except KeyboardInterrupt:
        print()  # Newline after ^C
        agent.end_session(reason="interrupt")
        break

      if not user_input.strip():
        continue

      # Handle commands
      if user_input.startswith("/"):
        result = command_registry.dispatch(user_input)
        if result:
          # Print command result directly (no events needed for commands)
          print(f"{result}\n")
        continue

      # Process message (output is streamed via events)
      try:
        # No blank line needed here - user's Enter key already provides separation

        agent.process(user_input)

        # Add blank line after agent response
        print()
      except ResponseError as e:
        # Handle Ollama API errors gracefully - allow retry
        if e.status_code == 503:
          print("\n[Error] Ollama server is overloaded. Please wait a moment and try again.")
        elif e.status_code == 404:
          print("\n[Error] Model not found. Check that the model is available.")
        elif e.status_code in (401, 403):
          print("\n[Error] Authentication failed. Check your Ollama configuration.")
        elif e.status_code == 500:
          print(f"\n[Error] Ollama internal error: {e}")
        else:
          print(f"\n[Error] Ollama error ({e.status_code}): {e}")
        continue

  except Exception as e:
    agent._emit(
      ErrorEvent(
        type=EventType.ERROR,
        error_type=type(e).__name__,
        message=str(e),
      )
    )
    raise


if __name__ == "__main__":
  main()
