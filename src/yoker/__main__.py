"""Entry point for running Yoker as a module.

Usage: python -m yoker [OPTIONS]

Configuration is loaded from TOML config files (~/.yoker.toml and ./yoker.toml).
CLI arguments are automatically generated from the Config data classes.
Examples:
  --backend-ollama-model MODEL         Model to use
  --context-session-id SESSION_ID      Session ID for context persistence
  --tools-read-enabled BOOL            Enable/disable read tool
  --ui-mode MODE                       UI mode (interactive or batch)
  --ui-show-thinking BOOL              Show thinking output
  --ui-show-tool-calls BOOL            Show tool call information
  --ui-show-stats BOOL                 Show turn statistics
"""

import asyncio
import os
import sys
import traceback

from structlog import get_logger

from yoker.agent import Agent
from yoker.config import Config
from yoker.exceptions import NetworkError, YokerError
from yoker.ui import BatchUIHandler, InteractiveUIHandler, UIBridge, UIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry

logger = get_logger(__name__)


def _parse_plugin_args(argv: list[str]) -> tuple[list[str], list[str]]:
  """Extract --with plugin arguments before Clevis parsing.

  Args:
    argv: Original command line arguments.

  Returns:
    Tuple of (plugin_packages, cleaned_argv).

  Raises:
    SystemExit: If --with is missing its value.
  """
  plugin_packages: list[str] = []
  args_to_remove: list[int] = []
  i = 1
  while i < len(argv):
    arg = argv[i]
    if arg == "--with":
      if i + 1 < len(argv):
        plugin_packages.append(argv[i + 1])
        args_to_remove.extend([i, i + 1])
        i += 2
      else:
        sys.stderr.write("Error: --with requires a package name\n")
        sys.exit(1)
    else:
      i += 1

  cleaned = list(argv)
  for idx in sorted(args_to_remove, reverse=True):
    cleaned.pop(idx)

  return plugin_packages, cleaned


def _create_ui(config: Config) -> UIHandler:
  """Create the appropriate UI handler based on configuration.

  Args:
    config: Loaded Yoker configuration.

  Returns:
    UIHandler implementation for interactive or batch mode.
  """
  if config.ui.mode != "batch" and sys.stdin.isatty():
    return InteractiveUIHandler(
      show_thinking=config.ui.show_thinking,
      show_tool_calls=config.ui.show_tool_calls,
      show_stats=config.ui.show_stats,
    )
  return BatchUIHandler()


async def run_session(agent: Agent, ui: UIHandler, commands: CommandRegistry) -> None:
  """Run the interactive or batch session loop.

  Handles user input, command dispatch, agent processing, and errors. All
  output is produced through the UI handler. The UI is always shut down.

  Args:
    agent: The initialized Agent instance.
    ui: UI handler for input/output.
    commands: Command registry for slash-commands.
  """
  from ollama import ResponseError

  await ui.start(agent)

  try:
    while True:
      try:
        user_input = await ui.get_input()
        if user_input is None:
          break

        if not user_input.strip():
          continue

        if user_input.startswith("/"):
          result = await commands.dispatch(user_input, agent, ui)
          if result:
            ui.output_command_result(result)
        else:
          await agent.process(user_input)

      except NetworkError as e:
        ui.output_error(e)
        if not e.recoverable:
          break
      except YokerError as e:
        ui.output_error(e)
        break
      except ResponseError as e:
        ui.output_error(e)
        continue
      except KeyboardInterrupt:
        break
      except Exception as e:
        ui.output_error(e)
        continue
  finally:
    await ui.shutdown("quit")


def main() -> None:
  """Run Yoker.

  Creates the Agent (which loads its own config and env files), wires the
  UI handler to it via the event bridge, and starts the session loop.
  """
  plugin_packages, argv = _parse_plugin_args(sys.argv)
  sys.argv = argv

  try:
    # Agent is autonomous: it loads .env/.env.local, discovers config, and
    # builds its own tool registry. Console logging is disabled by default so the UI
    # layer owns all terminal output, but can be controlled using the YOKER_CONSOLE_LOGGING environment variable.
    agent = Agent(
      plugins=plugin_packages if plugin_packages else None,
      console_logging=os.environ.get("YOKER_CONSOLE_LOGGING", "NO") != "NO",
      parse_cli_args=True,
    )
  except ValueError as e:
    sys.stderr.write(f"Error: {e}\n")
    sys.exit(1)

  logger.info("config loaded via agent", source="agent")

  if plugin_packages:
    logger.info("cli_plugins_specified", packages=plugin_packages)

  ui = _create_ui(agent.config)
  bridge = UIBridge(ui)
  agent.add_event_handler(bridge)

  commands = create_default_registry()

  asyncio.run(run_session(agent, ui, commands))


if __name__ == "__main__":
  main()
