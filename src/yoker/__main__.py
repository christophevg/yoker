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
from pathlib import Path
from typing import TYPE_CHECKING

from clevis import get_config

from yoker import __version__
from yoker.agent import Agent
from yoker.commands import (
  CommandRegistry,
  create_context_command,
  create_help_command,
  create_skill_commands,
  create_skills_command,
  create_think_command,
)
from yoker.config import Config
from yoker.events import (
  ConsoleEventHandler,
  ErrorEvent,
  EventType,
)
from yoker.exceptions import NetworkError
from yoker.logging import configure_logging, get_logger
from yoker.skills import SkillRegistry, load_skills, load_skills_from_env

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
  """Create and populate the command registry.

  Loads skills from configured directories and environment variables,
  then registers skill commands alongside built-in commands.

  Args:
    agent: The agent instance (for state access).
    config: Configuration object.

  Returns:
    Populated CommandRegistry.
  """
  registry = CommandRegistry()

  # Load skills from configuration and environment
  skill_registry = SkillRegistry()

  # Load from configured directories
  for directory in config.skills.directories:
    try:
      skills = load_skills(directory)
      for skill_name, skill in skills.items():
        skill_registry.register(skill)
        log.info("skill_loaded", name=skill_name, source=directory)
    except Exception as e:
      log.warning("skill_directory_load_failed", directory=directory, error=str(e))

  # Load from environment variable (YOKER_SKILLS_PATH)
  try:
    env_skills = load_skills_from_env()
    for skill_name, skill in env_skills.items():
      skill_registry.register(skill)
      log.info("skill_loaded_from_env", name=skill_name)
  except Exception as e:
    log.warning("skill_env_load_failed", error=str(e))

  # Set skill registry on agent
  agent._core.skill_registry = skill_registry

  # Add skill discovery block to context if skills are loaded
  if skill_registry.count > 0:
    from yoker.skills import format_discovery_block

    skill_list = skill_registry.list_skills()
    discovery_block = format_discovery_block(skill_list)
    # Add as system message so the agent knows about available skills
    agent.context.add_message("system", discovery_block)
    log.info("skill_discovery_added", skill_count=len(skill_list))

    # Register SkillTool so agent can invoke skills dynamically
    from yoker.tools import SkillTool

    agent._core.tool_registry.register(SkillTool(skill_registry=skill_registry))
    log.info("skill_tool_registered")

  # Register built-in commands
  registry.register(create_help_command(registry))
  registry.register(create_skills_command(skill_registry))
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

  # Register skill commands
  skill_commands = create_skill_commands(
    registry=skill_registry,
    get_skill_registry=lambda: skill_registry,
  )
  for command in skill_commands:
    try:
      registry.register(command)
      log.debug("skill_command_registered", name=command.name)
    except ValueError as e:
      # Command already exists (e.g., duplicate skill name)
      log.warning("skill_command_duplicate", name=command.name, error=str(e))

  log.info(
    "skills_registered",
    count=skill_registry.count,
    commands=[cmd.name for cmd in skill_commands],
  )

  return registry


async def run_interactive_session(
  agent: Agent, command_registry: CommandRegistry, session: "PromptSession[str]"
) -> None:
  """Run the interactive agent session asynchronously.

  Args:
    agent: The agent instance.
    command_registry: Command registry for slash-commands.
    session: PromptSession for user input.
  """
  from ollama import ResponseError

  # Begin session
  await agent.begin_session()

  try:
    while True:
      try:
        user_input = await prompt_input_async("> ", session)
      except EOFError:
        await agent.end_session(reason="quit")
        break
      except KeyboardInterrupt:
        print()  # Newline after ^C
        await agent.end_session(reason="interrupt")
        break

      if not user_input.strip():
        continue

      # Handle commands
      if user_input.startswith("/"):
        result = command_registry.dispatch(user_input)
        if result:
          # Check if this is a skill injection
          from yoker.commands.skill import extract_skill_content, is_skill_injection

          if is_skill_injection(result):
            # Inject skill content as system message (invisible to user)
            skill_content = extract_skill_content(result)
            agent.context.add_message("system", skill_content)

            # Extract skill name and args for logging
            parts = user_input[1:].split(maxsplit=1)
            skill_name = parts[0]
            skill_args = parts[1] if len(parts) > 1 else ""
            log.info("skill_injected", skill_name=skill_name, args=skill_args)

            # Process with agent - the skill content is now in context
            # Send appropriate prompt based on whether args were provided
            try:
              if skill_args:
                # If args provided, send them as the user message
                # The agent sees skill context + user's args
                await agent.process(skill_args)
              else:
                # If no args, send minimal prompt indicating skill invocation
                # The agent sees skill context + invocation request
                await agent.process("Execute the skill as requested.")
              print()  # Blank line after response
            except NetworkError as e:
              if e.recoverable:
                print(f"\n[Network Error] {e}")
                print("Your message was preserved. You can try again or type a new message.")
              else:
                print(f"\n[Fatal Network Error] {e}")
                print("Unable to recover. Please restart the session.")
                raise
            except Exception as e:
              await agent._emit(
                ErrorEvent(
                  type=EventType.ERROR,
                  error_type=type(e).__name__,
                  message=str(e),
                )
              )
              raise
          else:
            # Regular command - print result directly
            print(f"{result}\n")
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

  except Exception as e:
    await agent._emit(
      ErrorEvent(
        type=EventType.ERROR,
        error_type=type(e).__name__,
        message=str(e),
      )
    )
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
  """
  from clevis import SecurityAction, SecurityConfig

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

  # Create prompt session for interactive input
  session = create_prompt_session()

  # Create agent with config
  agent = Agent(config=config)

  # Show agent info if loaded
  if agent.agent_definition:
    print(f"Loaded agent: {agent.agent_definition.name}")
    print(f"  Description: {agent.agent_definition.description}")
    print(f"  Tools: {', '.join(agent.agent_definition.tools)}")
    print()

  # Create command registry with agent access
  command_registry = create_command_registry(agent, config)

  # Create and attach console handler
  console_handler = ConsoleEventHandler(
    show_thinking=True,
    show_tool_calls=True,
    version=__version__,
  )
  agent.add_event_handler(console_handler)

  # Run interactive session
  asyncio.run(run_interactive_session(agent, command_registry, session))


if __name__ == "__main__":
  main()
