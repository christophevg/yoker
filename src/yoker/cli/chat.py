"""``yoker chat`` subcommand handler — the interactive REPL.

Extracted from :mod:`yoker.__main__` (MBI-004 task 4.2). This is the default
subcommand when no subcommand is given (backward compatibility). The handler
runs the pre-flight bootstrap check when no config is provided, loads the
:class:`~yoker.cli.commands.ChatConfig` via Clevis, wires the UI handler to the
Session via the event bridge, and starts the REPL loop.
"""

import asyncio
import os
import sys

from clevis import SecurityError
from ollama import ResponseError
from structlog import get_logger

from yoker.bootstrap import BootstrapResult, BootstrapWizard, config_provided
from yoker.bootstrap.steps import DOCS_HOME_URL
from yoker.cli.commands import ChatConfig
from yoker.cli.shared import abort, check_enabled, load_subcommand_config
from yoker.config import Config
from yoker.core import Agent
from yoker.exceptions import NetworkError, YokerError
from yoker.logging import configure_logging
from yoker.session import Session
from yoker.ui import BatchUIHandler, InteractiveUIHandler, UIBridge, UIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry

logger = get_logger(__name__)


def run_chat(plugin_packages: list[str]) -> None:
  """Run the chat subcommand (the default REPL behavior).

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
      abort(
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
    bootstrap_ui = InteractiveUIHandler(history_file="none", show_prompts=False)
    try:
      result = asyncio.run(BootstrapWizard(bootstrap_ui).run())
      if result != BootstrapResult.WRITTEN:
        # Manual setup or abort: no file was written. The wizard already
        # emitted the appropriate message; exit cleanly.
        sys.exit(0)
    except KeyboardInterrupt:
      # Ctrl+C that bypassed the wizard's inner handler (e.g. arrived at the
      # event-loop level): treat as a clean abort, no file written.
      abort("Aborted. No configuration written.\n", 0)

    # Config was written; fall through to normal Agent startup, which will
    # load the freshly-written ~/.yoker.toml.

  try:
    # Load ChatConfig via Clevis (TOML + env + CLI args), then construct the
    # Session and primary Agent within it. ChatConfig extends Config, so all
    # existing CLI flags work under `yoker chat`.
    config = load_subcommand_config(ChatConfig)
  except (ValueError, SecurityError) as e:
    abort(f"Error: {e}\n", 1)

  check_enabled(config)

  CONSOLE_LOGGING = os.environ.get("YOKER_CONSOLE_LOGGING", "NO") != "NO"
  configure_logging(config.logging, console=CONSOLE_LOGGING)

  logger.info("config loaded")

  if plugin_packages:
    logger.info("cli plugins specified", packages=plugin_packages)

  ui = create_ui(config)
  bridge = UIBridge(ui)
  commands = create_default_registry()

  try:
    asyncio.run(_run_with_session(config, plugin_packages, ui, commands, bridge))
  except (ValueError, SecurityError) as e:
    abort(f"Error: {e}\n", 1)


def create_ui(config: Config) -> UIHandler:
  """Select the UI handler based on config and TTY detection."""
  if config.ui.mode != "batch" and sys.stdin.isatty():
    return InteractiveUIHandler(
      show_thinking=config.ui.show_thinking,
      show_tool_calls=config.ui.show_tool_calls,
      show_stats=config.ui.show_stats,
      content_display=config.tools_shared.content_display,
    )
  return BatchUIHandler()


async def _run_with_session(
  config: ChatConfig,
  plugin_packages: list[str],
  ui: UIHandler,
  commands: CommandRegistry,
  bridge: UIBridge,
) -> None:
  # Determine session id and fresh/resume mode from CLI flags.
  if config.resume:
    sid: str | None = config.resume
    config.context.fresh = False
  elif config.session_id:
    sid = config.session_id
    config.context.fresh = True
  else:
    sid = None
    config.context.fresh = True

  async with Session(
    config=config,
    extra_plugins=tuple(plugin_packages),
    session_id=sid,
  ) as session:
    if config.resume:
      # Graceful abort: check that the session file exists before entering
      # the Session context manager (which would create an empty one).
      from yoker.context.factory import _session_file_path

      if sid is not None:
        session_file_path = _session_file_path(config, sid, session._id_of(session.agent))
        if not session_file_path.exists():
          ui.output_info(
            f"No session '{sid}' found at {session_file_path}. Use --session-id {sid} to start a new one."
          )
          await ui.shutdown("quit")
          return

    session.on_event(bridge)
    bridge._primary_agent_id = session._id_of(session.agent)
    bridge._current_agent_id = bridge._primary_agent_id
    _wire_approval_handler(session, ui)
    await _run_repl(session.agent, ui, commands)


def _wire_approval_handler(session: Session, ui: UIHandler) -> None:
  """Wire the approval handler on the session when the UI opts in.

  ``confirm_approval`` is an optional ``UIHandler`` method (see
  :mod:`yoker.ui.handler`). Handlers that do not provide it are not wired,
  and the :class:`yoker.tools.guardrails.path.PathGuardrail` handles
  protected writes (block without interactive prompt). When ``ui``
  provides ``confirm_approval``, the handler is stored on the session
  so it is propagated to every agent created via ``_create_agent`` —
  the primary agent and all spawned subagents get the same interactive
  approval flow. The git tool also uses this handler for non-auto-
  permissioned operations (with ``kind="git"``).
  """
  if not hasattr(ui, "confirm_approval"):
    return
  session._approval_handler = ui.confirm_approval
  # Also wire on the primary agent (already constructed in __init__).
  session.agent._approval_handler = ui.confirm_approval


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


__all__ = ["run_chat", "create_ui"]
