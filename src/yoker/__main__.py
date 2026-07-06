"""Entry point for running Yoker as a module.

Usage: python -m yoker [OPTIONS]

Configuration is loaded from TOML config files (~/.yoker.toml and ./yoker.toml).
CLI arguments are automatically generated from the Config data classes.
Examples:
  --backend-ollama-model MODEL         Model to use when using Ollama as a backend
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
from ollama import ResponseError
from structlog import get_logger

from yoker.agent import Agent
from yoker.bootstrap import BootstrapResult, BootstrapWizard, config_provided
from yoker.bootstrap.steps import DOCS_HOME_URL
from yoker.config import Config, get_yoker_config
from yoker.exceptions import NetworkError, YokerError
from yoker.session import Session
from yoker.ui import BatchUIHandler, InteractiveUIHandler, UIBridge, UIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry

logger = get_logger(__name__)


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
  plugin_packages, sys.argv = _parse_plugin_args()

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
    # Load config via Clevis (TOML + env + CLI args), then construct the
    # Session and primary Agent within it. The Session owns the AgentRegistry
    # and backend factory; the Agent resolves its definition via
    # session.agents and shares the session's backend.
    config = get_yoker_config(cli=True)
  except (ValueError, SecurityError) as e:
    _abort(f"Error: {e}\n", 1)

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


async def _run_with_session(
  config: Config,
  plugin_packages: list[str],
  ui: UIHandler,
  commands: CommandRegistry,
  bridge: UIBridge,
) -> None:
  async with Session(config=config) as session:
    agent = Agent(
      config=config,
      plugins=plugin_packages if plugin_packages else None,
      session=session,
      console_logging=os.environ.get("YOKER_CONSOLE_LOGGING", "NO") != "NO",
    )
    # Register the primary agent with the session so it gets a runtime id,
    # is added to the active map (for send_message addressing), and receives
    # the Session-injected tools (agent, send_message).
    session.register_primary_agent(agent)
    # UIBridge is registered on Session so aggregated sub-agent events
    # (SessionEvent envelopes) reach the UI.
    session.add_event_handler(bridge)
    await _run_repl(agent, ui, commands)


async def _run_repl(agent: Agent, ui: UIHandler, commands: CommandRegistry) -> None:
  """Run the interactive or batch REPL loop.

  Handles user input, command dispatch, agent processing, and errors. All
  output is produced through the UI handler. The UI is always shut down
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
