"""Entry point for running Yoker as a module.

Usage: python -m yoker [OPTIONS]

Clevis automatically generates CLI arguments from the Config dataclass:
  --backend-ollama-model MODEL         Model to use
  --context-session-id SESSION_ID      Session ID for context persistence
  --tools-read-enabled BOOL           Enable/disable read tool
  ...

Environment variables (YOKER_*) and config files (~/.yoker.toml, ./yoker.toml)
are also supported via Clevis.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from clevis import get_config

from yoker import __version__
from yoker.agent import Agent
from yoker.config import Config
from yoker.events import ConsoleEventHandler
from yoker.exceptions import NetworkError
from yoker.logging import configure_logging, get_logger
from yoker.ui import BatchUIHandler, UIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry

if TYPE_CHECKING:
  from prompt_toolkit.shortcuts import PromptSession

# History file for prompt_toolkit
HISTORY_FILE = Path.home() / ".yoker_history"

# Logger for this module
log = get_logger(__name__)


def create_prompt_session() -> "PromptSession[str]":
  """Create a prompt session with multiline support.

  Returns:
    PromptSession configured for multiline input.
    - Enter submits the input
    - Meta+Enter (Esc+Enter) adds a newline

  Note: Shift+Enter is not distinguishable from Enter in most terminals,
  so we use Meta+Enter for multiline input instead.
  """
  from prompt_toolkit.history import FileHistory
  from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
  from prompt_toolkit.shortcuts import PromptSession

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


async def prompt_input_async(prompt: str, session: "PromptSession[str]") -> str:
  """Get user input with prompt_toolkit (async version).

  Args:
    prompt: The prompt string to display.
    session: PromptSession to use.

  Returns:
    User input string.
  """
  result: str = await session.prompt_async(prompt)
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


def create_command_registry(agent: Agent, config: Config) -> CommandRegistry:
  """Create and populate the UI command registry.

  Args:
    agent: The agent instance (for state access).
    config: Configuration object (kept for API compatibility).

  Returns:
    Populated CommandRegistry from the UI layer.
  """
  registry = create_default_registry()

  log.info(
    "command_registry_created",
    commands=registry.names,
    skill_count=agent.skill_registry.count if agent.skill_registry else 0,
  )

  return registry


async def run_interactive_session(
  agent: Agent,
  command_registry: CommandRegistry,
  session: "PromptSession[str]",
  ui: "UIHandler",
) -> None:
  """Run the interactive agent session asynchronously.

  Args:
    agent: The agent instance.
    command_registry: Command registry for slash-commands.
    session: PromptSession for user input.
    ui: UI handler for command output and errors.
  """
  from ollama import ResponseError

  try:
    while True:
      try:
        user_input = await prompt_input_async("> ", session)
      except EOFError:
        break
      except KeyboardInterrupt:
        print()  # Newline after ^C
        break

      if not user_input.strip():
        continue

      # Handle slash-commands through the UI-layer registry.
      if user_input.startswith("/"):
        try:
          result = await command_registry.dispatch(user_input, agent, ui)
          if result is not None:
            ui.output_command_result(result)
        except NetworkError as e:
          if e.recoverable:
            print(f"\n[Network Error] {e}")
            print("Your message was preserved. You can try again or type a new message.")
          else:
            print(f"\n[Fatal Network Error] {e}")
            print("Unable to recover. Please restart the session.")
            raise
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

      # Process message (output is streamed via events)
      try:
        # No blank line needed here - user's Enter key already provides separation

        await agent.process(user_input)

        # Add blank line after agent response
        print()
      except NetworkError as e:
        # Handle network errors gracefully - allow retry
        if e.recoverable:
          print(f"\n[Network Error] {e}")
          print("Your message was preserved. You can try again or type a new message.")
        else:
          print(f"\n[Fatal Network Error] {e}")
          print("Unable to recover. Please restart the session.")
          raise
        continue
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

  except Exception:
    # Let exceptions propagate to the main() function
    raise


def main() -> None:
  """Run the interactive agent.

  Uses Clevis to load configuration from:
    1. CLI arguments (highest priority, auto-generated from Config schema)
    2. Environment variables (YOKER_*)
    3. Project config (./yoker.toml)
    4. User config (~/.yoker.toml)
    5. Default values (lowest priority)

  CLI arguments are generated from Config fields:
    --backend-ollama-model MODEL         Set model
    --context-session-id SESSION_ID      Set session ID
    --tools-read-enabled BOOL           Enable/disable read tool
    ...

  Additional CLI arguments (pre-Clevis):
    --with PACKAGE                       Load plugin package (can be specified multiple times)
  """
  from clevis import SecurityAction, SecurityConfig

  # Pre-parse --with arguments before Clevis (temporary workaround)
  # This will be replaced by Clevis native --with support in future
  plugin_packages: list[str] = []
  args_to_remove = []

  # Parse sys.argv to extract --with arguments
  i = 1  # Skip script name
  while i < len(sys.argv):
    arg = sys.argv[i]
    if arg == "--with":
      if i + 1 < len(sys.argv):
        plugin_packages.append(sys.argv[i + 1])
        args_to_remove.extend([i, i + 1])
        i += 2
      else:
        print("Error: --with requires a package name")
        sys.exit(1)
    else:
      i += 1

  # Remove --with arguments from sys.argv before Clevis parsing
  for idx in sorted(args_to_remove, reverse=True):
    sys.argv.pop(idx)

  # Configure security checks based on environment
  # In development/testing, allow group/other readable config files
  # In production, use strict permissions (default)
  security_config: SecurityConfig | None = None
  if os.environ.get("YOKER_DEV_MODE") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
    security_config = SecurityConfig(
      file_permissions=SecurityAction.LOG,
      directory_permissions=SecurityAction.LOG,
    )

  # Load configuration with Clevis (handles env vars, config files, CLI args)
  # Note: cli=True generates CLI arguments from Config fields
  config = get_config(Config, name="yoker", cli=True, security=security_config)

  # Setup logging with config
  setup_logging(config)

  # Log config source
  log.info("config_loaded_via_clevis", source="clevis")

  # Log --with packages if specified
  if plugin_packages:
    log.info("cli_plugins_specified", packages=plugin_packages)

  # Create prompt session for interactive input
  session = create_prompt_session()

  # Create agent with config and optional plugin override
  try:
    agent = Agent(config=config, plugins=plugin_packages if plugin_packages else None)
  except ValueError as e:
    print(f"Error: {e}")
    sys.exit(1)

  # Show agent info if loaded
  if agent.agent_definition:
    print(f"Loaded agent: {agent.agent_definition.name}")
    print(f"  Description: {agent.agent_definition.description}")
    print(f"  Tools: {', '.join(agent.agent_definition.tools)}")
    print()

  # Create command registry with agent access
  command_registry = create_command_registry(agent, config)

  # Create a simple UI handler for slash-command output.
  # In Phase 6 this will be replaced by the full interactive/batch UI.
  ui: UIHandler = BatchUIHandler(stdout=sys.stdout, stderr=sys.stderr)

  # Create and attach console handler
  console_handler = ConsoleEventHandler(
    show_thinking=True,
    show_tool_calls=True,
    version=__version__,
  )
  agent.add_event_handler(console_handler)

  # Run interactive session
  asyncio.run(run_interactive_session(agent, command_registry, session, ui))


if __name__ == "__main__":
  main()
