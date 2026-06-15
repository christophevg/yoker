"""Entry point for running Yoker as a module.

Usage: python -m yoker [OPTIONS]

Clevis automatically generates CLI arguments from the Config dataclass:
  --backend-ollama-model MODEL         Model to use
  --context-session-id SESSION_ID      Session ID for context persistence
  --tools-read-enabled BOOL            Enable/disable read tool
  --ui-mode MODE                       UI mode (interactive or batch)
  --ui-show-thinking BOOL              Show thinking output
  --ui-show-tool-calls BOOL            Show tool call information
  --ui-show-stats BOOL                 Show turn statistics

Environment variables (YOKER_*) and config files (~/.yoker.toml, ./yoker.toml)
are also supported via Clevis.
"""

import asyncio
import sys
from pathlib import Path

from yoker.agent import Agent
from yoker.config import Config, get_yoker_config
from yoker.exceptions import NetworkError, YokerError
from yoker.logging import configure_logging, get_logger
from yoker.ui import BatchUIHandler, InteractiveUIHandler, UIBridge, UIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry

log = get_logger(__name__)

VERSION = "0.4.0"


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


def _setup_logging(config: Config) -> None:
  """Configure logging based on configuration.

  Disables console output so the UI layer owns all terminal output.

  Args:
    config: Configuration object.
  """
  log_file: Path | None = None
  if config.logging.file:
    log_file = Path(config.logging.file)

  configure_logging(
    level=config.logging.level,
    log_file=log_file,
    format=config.logging.format,
    console=False,
  )

  log.info("logging_configured", level=config.logging.level)


def _create_ui(config: Config) -> UIHandler:
  """Create the appropriate UI handler based on configuration.

  Args:
    config: Loaded Yoker configuration.

  Returns:
    UIHandler implementation for interactive or batch mode.
  """
  ui_config = config.ui

  if ui_config.mode == "batch":
    return BatchUIHandler(
      show_thinking=ui_config.show_thinking,
      show_tool_calls=ui_config.show_tool_calls,
      show_stats=ui_config.show_stats,
    )

  return InteractiveUIHandler(
    show_thinking=ui_config.show_thinking,
    show_tool_calls=ui_config.show_tool_calls,
    show_stats=ui_config.show_stats,
  )


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

  await ui.start(
    agent.model,
    VERSION,
    {
      "thinking_enabled": agent.thinking_mode.value == "on",
      "show_tool_calls": getattr(ui, "show_tool_calls", False),
    },
  )

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
        break
  finally:
    await ui.shutdown("quit")


def main() -> None:
  """Run Yoker.

  Loads configuration via Clevis, creates the Agent and UI handler, wires
  events through UIBridge, and starts the session loop.
  """
  plugin_packages, argv = _parse_plugin_args(sys.argv)
  sys.argv = argv

  config = get_yoker_config(cli=True)

  _setup_logging(config)

  log.info("config_loaded_via_clevis", source="clevis")

  if plugin_packages:
    log.info("cli_plugins_specified", packages=plugin_packages)

  try:
    agent = Agent(
      config=config,
      plugins=plugin_packages if plugin_packages else None,
    )
  except ValueError as e:
    sys.stderr.write(f"Error: {e}\n")
    sys.exit(1)

  ui = _create_ui(config)
  bridge = UIBridge(ui)
  agent.add_event_handler(bridge)

  commands = create_default_registry()

  asyncio.run(run_session(agent, ui, commands))


if __name__ == "__main__":
  main()
