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

from clevis import SecurityError
from structlog import get_logger

from yoker.agent import Agent
from yoker.bootstrap import BootstrapResult, BootstrapWizard, config_provided
from yoker.bootstrap.steps import DOCS_HOME_URL
from yoker.config import Config
from yoker.exceptions import NetworkError, YokerError
from yoker.ui import BatchUIHandler, InteractiveUIHandler, UIBridge, UIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry

logger = get_logger(__name__)


def _abort_non_interactive() -> None:
  """Print the approved no-config warning to stderr and exit non-zero.

  Used when ``config_provided()`` is False in non-interactive mode. The
  wizard is not instantiated (it requires a TTY).
  """
  sys.stderr.write(
    "No yoker configuration found at ~/.yoker.toml.\n"
    "Run `yoker` interactively to configure, or see "
    f"{DOCS_HOME_URL}\n"
    "Aborting (non-interactive mode).\n"
  )
  sys.exit(1)


async def _run_bootstrap(ui: UIHandler) -> bool:
  """Run the bootstrap wizard when no config is provided.

  Args:
    ui: The interactive UI handler to drive the wizard.

  Returns:
    True when the wizard wrote a config (caller should continue into the
    normal Agent session); False when the user chose manual setup or aborted
    (caller should exit cleanly with no file written).
  """
  result = await BootstrapWizard(ui).run()
  # WRITTEN -> continue into the session. MANUAL and ABORTED -> exit cleanly.
  # The wizard emits the abort/manual message itself; __main__ just exits.
  return result == BootstrapResult.WRITTEN


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

  Before constructing the Agent, a pre-flight check runs: when no user
  configuration is provided, the interactive bootstrap wizard is invoked
  (interactive mode only). In non-interactive mode a warning is printed to
  stderr and the process exits non-zero. After the wizard writes
  ``~/.yoker.toml`` it returns, and the normal Agent startup proceeds using
  the freshly-written config (the wizard does not exit the process).
  """
  plugin_packages, argv = _parse_plugin_args(sys.argv)
  sys.argv = argv

  # Pre-flight: detect missing configuration and bootstrap when needed.
  # When config_provided() is False there are no yoker CLI overrides (any
  # --ui-mode batch flag would have made it True), so the UI mode is the
  # default "interactive". The interactive/non-interactive gate therefore
  # reduces to TTY detection here, mirroring _create_ui's selection.
  if not config_provided():
    if not sys.stdin.isatty():
      _abort_non_interactive()
    # Interactive: drive the wizard through an interactive UI handler.
    # IMPORTANT: Use history_file="none" to prevent bootstrap prompts (including
    # API keys) from being persisted to ~/.yoker_history. Bootstrap is for
    # one-time configuration, not conversation, and should never log secrets.
    bootstrap_ui = InteractiveUIHandler(history_file="none")
    try:
      written = asyncio.run(_run_bootstrap(bootstrap_ui))
    except KeyboardInterrupt:
      # Ctrl+C that bypassed the wizard's inner handler (e.g. arrived at the
      # event-loop level): treat as a clean abort, no file written.
      sys.stderr.write("Aborted. No configuration written.\n")
      sys.exit(0)
    if not written:
      # Manual setup or abort: no file was written. The wizard already
      # emitted the appropriate message; exit cleanly.
      sys.exit(0)
    # Config was written; fall through to normal Agent startup, which will
    # load the freshly-written ~/.yoker.toml.

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
  except SecurityError as e:
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
