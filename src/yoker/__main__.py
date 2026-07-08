"""Entry point for running Yoker as a module.

Usage: python -m yoker [SUBCOMMAND] [OPTIONS]

Subcommands (registered via Clevis ``@configclass(cmd=...)`` in
:mod:`yoker.cli.commands`):

  chat       Start the interactive REPL (default when no subcommand is given)
  run        Run an agentic package non-interactively
  loop       Run an agentic package at intervals
  inspect    Dump a report about a source without executing it
  init       Generate a default configuration file
  config     Display the effective configuration
  container  Generate container setup for an agentic package

Configuration is loaded from TOML config files (~/.yoker.toml and ./yoker.toml).
CLI arguments are automatically generated from the Config data classes by Clevis.
When no subcommand is given, ``chat`` is inserted as the default (backward
compatibility). Examples:

  python -m yoker                              # -> yoker chat
  python -m yoker chat --ui-mode batch          # explicit chat subcommand
  python -m yoker --backend-ollama-model MODEL  # -> yoker chat --backend-ollama-model MODEL
"""

import asyncio
import os
import sys

from clevis import SecurityError, get_cmd
from ollama import ResponseError
from structlog import get_logger

from yoker.bootstrap import BootstrapResult, BootstrapWizard, config_provided
from yoker.bootstrap.steps import DOCS_HOME_URL
from yoker.cli import commands as cli_commands  # noqa: F401 — registers @configclass(cmd=...)
from yoker.cli.commands import ChatConfig
from yoker.cli.shared import load_subcommand_config
from yoker.config import Config
from yoker.core import Agent
from yoker.exceptions import NetworkError, YokerError
from yoker.logging import configure_logging
from yoker.session import Session
from yoker.ui import BatchUIHandler, InteractiveUIHandler, UIBridge, UIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry

logger = get_logger(__name__)

# Subcommand names registered with Clevis. Used to detect whether the first
# positional argument is a known subcommand (don't insert the default) or an
# unknown one (let argparse error with the valid-choice list).
KNOWN_COMMANDS = frozenset(
  {
    "chat",
    "run",
    "loop",
    "inspect",
    "init",
    "config",
    "container",
  }
)

# Subcommands that are stubbed out (not yet implemented). chat is the only
# working end-to-end subcommand in this task; the rest print a notice and exit.
STUB_COMMANDS = frozenset({"run", "loop", "inspect", "init", "config", "container"})


def main() -> None:
  """Run Yoker.

  Strips ``--with`` plugin args, defaults to the ``chat`` subcommand when none
  is given (backward compatibility), then dispatches to the subcommand handler
  via Clevis's ``get_cmd()``. The ``chat`` handler runs the interactive REPL;
  all other subcommands are stubs until their dedicated tasks land.
  """
  plugin_packages, sys.argv = _parse_plugin_args()

  # Default to chat when no subcommand is given. We patch sys.argv to insert
  # "chat" as the first positional so existing `yoker --backend-ollama-model X`
  # invocations route to `yoker chat --backend-ollama-model X`.
  #
  # TODO: submit a feature request to Clevis for configurable subcommand
  # defaults (e.g. a `default_cmd` on the subparser manager) so we can stop
  # patching sys.argv manually.
  if _needs_default_chat(sys.argv):
    sys.argv.insert(1, "chat")

  cmd = get_cmd()

  if cmd == "chat":
    _run_chat(plugin_packages)
  elif cmd in STUB_COMMANDS:
    sys.stdout.write(f"yoker {cmd}: not yet implemented\n")
    sys.exit(0)
  else:
    # Should not happen: argparse rejects unknown subcommands with a
    # valid-choice list before get_cmd() returns. Guard anyway.
    _abort(f"Error: unknown subcommand: {cmd}\n", 1)


def _run_chat(plugin_packages: list[str]) -> None:
  """Run the chat subcommand (the current default REPL behavior).

  Runs the pre-flight bootstrap check when no config is provided, loads the
  ChatConfig via Clevis, wires the UI handler to the Session via the event
  bridge, and starts the REPL loop.
  """
  # Pre-flight: detect missing configuration and bootstrap when needed.
  # When config_provided() is False there are no yoker CLI overrides (any
  # --ui-mode batch flag would have made it True), so the UI mode is the
  # default "interactive". The interactive/non-interactive gate therefore
  # reduces to TTY detection here, mirroring _create_ui's selection.
  if not config_provided():
    if not sys.stdin.isatty():
      _abort(
        f"""No yoker configuration found at ~/.yoker.toml or ./yoker.toml.
        Run `yoker` interactively to configure, or see {DOCS_HOME_URL}
        Aborting (non-interactive mode).
        """,
        1,
      )
    # Interactive: drive the wizard through an interactive UI handler.
    # IMPORTANT: Use history_file="none" to prevent bootstrap prompts (including
    # API keys) from being persisted to ~/.yoker_history. Bootstrap is for
    # one-time configuration, not conversation, and should never log secrets.
    bootstrap_ui = InteractiveUIHandler(history_file="none")
    try:
      result = asyncio.run(BootstrapWizard(bootstrap_ui).run())
      if result != BootstrapResult.WRITTEN:
        # Manual setup or abort: no file was written. The wizard already
        # emitted the appropriate message; exit cleanly.
        sys.exit(0)
    except KeyboardInterrupt:
      # Ctrl+C that bypassed the wizard's inner handler (e.g. arrived at the
      # event-loop level): treat as a clean abort, no file written.
      _abort("Aborted. No configuration written.\n", 0)

    # Config was written; fall through to normal Agent startup, which will
    # load the freshly-written ~/.yoker.toml.

  try:
    # Load ChatConfig via Clevis (TOML + env + CLI args), then construct the
    # Session and primary Agent within it. ChatConfig extends Config, so all
    # existing CLI flags work under `yoker chat`.
    config = load_subcommand_config(ChatConfig)
  except (ValueError, SecurityError) as e:
    _abort(f"Error: {e}\n", 1)

  CONSOLE_LOGGING = os.environ.get("YOKER_CONSOLE_LOGGING", "NO") != "NO"
  configure_logging(config.logging, console=CONSOLE_LOGGING)

  logger.info("config loaded")

  if plugin_packages:
    logger.info("cli plugins specified", packages=plugin_packages)

  ui = _create_ui(config)
  bridge = UIBridge(ui)
  commands = create_default_registry()

  try:
    asyncio.run(_run_with_session(config, plugin_packages, ui, commands, bridge))
  except (ValueError, SecurityError) as e:
    _abort(f"Error: {e}\n", 1)


def _needs_default_chat(argv: list[str]) -> bool:
  """Return True if we should insert "chat" as the default subcommand.

  We insert "chat" when:
  - No args follow the program name (bare ``yoker``), or
  - The first arg is a flag (e.g. ``yoker --backend-ollama-model X``), meaning
    the user expects the default command with config overrides.

  We leave argv untouched when:
  - The first arg is ``--help`` / ``-h`` (let the top-level parser show the
    subcommand list), or
  - The first arg is a known subcommand (let it route), or
  - The first arg is an unknown positional (let argparse reject it with the
    valid-choice list — this is how ``yoker <unknown>`` reports valid
    subcommands).
  """
  if len(argv) <= 1:
    return True
  first = argv[1]
  if first in ("--help", "-h"):
    return False
  if first.startswith("-"):
    return True
  # First positional: only default when it is not a known subcommand name.
  # For unknown positionals, let argparse error with the choice list.
  return False


async def _run_with_session(
  config: Config,
  plugin_packages: list[str],
  ui: UIHandler,
  commands: CommandRegistry,
  bridge: UIBridge,
) -> None:
  async with Session(config=config, extra_plugins=tuple(plugin_packages)) as session:
    session.on_event(bridge)
    await _run_repl(session.agent, ui, commands)


async def _run_repl(agent: Agent, ui: UIHandler, commands: CommandRegistry) -> None:
  """Run the interactive or batch REPL loop.

  Handles user input, command dispatch, agent processing, and errors. All
  output is produced through the UI handler. The UI is always shut down.
  """
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
      except ResponseError as e:
        ui.output_error(e)
        continue
      except YokerError as e:
        ui.output_error(e)
        break
      except Exception as e:
        ui.output_error(e)
        break
      except KeyboardInterrupt:
        break
  finally:
    await ui.shutdown("quit")


def _parse_plugin_args(argv: list[str] | None = None) -> tuple[list[str], list[str]]:
  """Extract --with plugin arguments before standard parsing."""
  plugin_packages: list[str] = []
  args_to_remove: list[int] = []
  i = 1
  if argv is None:
    argv = sys.argv
  while i < len(argv):
    arg = argv[i]
    if arg == "--with":
      if i + 1 < len(argv):
        plugin_packages.append(argv[i + 1])
        args_to_remove.extend([i, i + 1])
        i += 2
      else:
        _abort("Error: --with requires a package name\n", 1)
    else:
      i += 1

  cleaned = list(argv)
  for idx in sorted(args_to_remove, reverse=True):
    cleaned.pop(idx)

  return plugin_packages, cleaned


def _create_ui(config: Config) -> UIHandler:
  if config.ui.mode != "batch" and sys.stdin.isatty():
    return InteractiveUIHandler(
      show_thinking=config.ui.show_thinking,
      show_tool_calls=config.ui.show_tool_calls,
      show_stats=config.ui.show_stats,
    )
  return BatchUIHandler()


def _abort(msg: str, code: int) -> None:
  sys.stderr.write(msg)
  sys.exit(code)


if __name__ == "__main__":
  main()
