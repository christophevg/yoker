"""``yoker chat`` subcommand handler — the interactive REPL.

Extracted from :mod:`yoker.__main__` (MBI-004 task 4.2). This is the default
subcommand when no subcommand is given (backward compatibility). The handler
runs the pre-flight bootstrap check when no config is provided, loads the
:class:`~yoker.cli.commands.ChatConfig` via Clevis, wires the UI handler to the
Session via the event bridge, and starts the REPL loop.
"""

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from clevis import SecurityError
from ollama import ResponseError
from structlog import get_logger

from yoker.bootstrap import BootstrapResult, BootstrapWizard, config_provided
from yoker.bootstrap.steps import DOCS_HOME_URL
from yoker.cli.commands import ChatConfig
from yoker.cli.shared import abort, check_enabled, load_subcommand_config
from yoker.config import Config
from yoker.context.session import _bare_session_id
from yoker.core import Agent
from yoker.exceptions import NetworkError, TurnAbortedError, YokerError
from yoker.logging import configure_logging
from yoker.session import Session
from yoker.ui import BatchUIHandler, InteractiveUIHandler, UIBridge, UIHandler
from yoker.ui.agent_display import AgentDisplay
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


# Sentinel for --resume: resume the most recently active session.
RESUME_LAST = "last"


def _last_session_id(config: Config) -> str | None:
  """Resolve the bare session id of the most recently active session.

  The session files live in one JSONL per agent
  (``{session_id}-{agent_id}.jsonl``); mtime equals last activity because
  every context mutation bulk-rewrites the file. Any file of the winning
  session yields the same bare id via the session_start record (see
  :func:`yoker.context.session._bare_session_id` for the legacy handling).
  Returns None when the storage has no readable session files.
  """
  storage_path = Path(config.context.storage_path).expanduser()
  if not storage_path.exists():
    return None

  newest: tuple[float, Path] | None = None
  for file_path in storage_path.glob("*.jsonl"):
    mtime = file_path.stat().st_mtime
    if newest is None or mtime > newest[0]:
      newest = (mtime, file_path)
  if newest is None:
    return None

  try:
    with open(newest[1]) as f:
      record = json.loads(f.readline())
    if record.get("type") != "session_start":
      return None
    return _bare_session_id(record.get("data", {}))
  except (OSError, json.JSONDecodeError):
    logger.warning("last_session_resolve_failed", path=str(newest[1]))
    return None


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
    if sid == RESUME_LAST:
      resolved = _last_session_id(config)
      if resolved is None:
        ui.output_info("No previous session found to resume. Start one with --session-id <name>.")
        await ui.shutdown("quit")
        return
      sid = resolved
      ui.output_info(f"Resuming last session: {sid}")
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

    # Wire agent resolver so the bridge can build AgentDisplay for UI tagging.
    def _resolve_agent(agent_id: str) -> AgentDisplay | None:
      agent = session._agents_map.get(agent_id)
      if agent is None:
        return None
      d = agent.definition
      return AgentDisplay(
        id=agent_id,
        name=d.simple_name or agent_id,
        color=d.color,
        model=getattr(agent, "model", None),
        description=d.description,
      )

    bridge.set_agent_resolver(_resolve_agent)

    _wire_approval_handler(session, ui)
    await _run_repl(session.agent, ui, commands, prompt=config.prompt, session=session)


class _TurnInterrupt(KeyboardInterrupt):
  """Ctrl+C was pressed during a turn and the abort has been requested.

  ``_process_turn`` raises this once the turn has unwound, so the REPL's
  existing ``except KeyboardInterrupt`` branches exit the process —
  preserving Ctrl+C's external behavior (process terminates) while the
  in-flight turn is torn down cleanly first (stream cancelled / current
  tool completed, context consistent, abort recorded). A second Ctrl+C
  during the same turn raises a plain ``KeyboardInterrupt`` from the
  signal handler for an immediate exit.
  """


def _wire_approval_handler(session: Session, ui: UIHandler) -> None:
  """Wire the approval handler on the session when the UI opts in.

  ``confirm_approval`` is an optional ``UIHandler`` method (see
  :mod:`yoker.ui.handler`). Handlers that do not provide it are not wired,
  and the :class:`yoker.tools.guardrails.path.WritePathGuardrail` handles
  write-protected files (block without interactive prompt). When ``ui``
  provides ``confirm_approval``, the raw handler is stored on the session
  so it is propagated to every agent created via ``_create_agent`` — the
  primary agent and all spawned subagents get the same interactive
  approval flow. The idle watchdog is scoped to the LLM streaming phase
  only, so approval prompts (which happen during tool execution) never
  trigger a timeout. The git tool also uses this handler for
  non-auto-permissioned operations (with ``kind="git"``).
  """
  if not hasattr(ui, "confirm_approval"):
    return

  handler = ui.confirm_approval

  async def _approval_with_paused_watcher(label: str, preview: str, kind: str = "file") -> bool:
    # The approval prompt reads via input(); the Esc-Esc watcher owns stdin
    # in cbreak mode during a turn, so it must yield the terminal for the
    # duration of the prompt or neither would see the keystrokes reliably.
    watcher = _active_watcher
    if watcher is not None:
      watcher.pause()
    try:
      return bool(await handler(label, preview, kind))
    finally:
      if watcher is not None:
        watcher.resume()

  session._approval_handler = _approval_with_paused_watcher
  # Also wire on the primary agent (already constructed in __init__).
  session.agent._approval_handler = _approval_with_paused_watcher


# The watcher for the in-flight turn, if any. Set by ``_process_turn`` and
# consumed by the approval wrapper in ``_wire_approval_handler`` so the
# watcher can yield stdin to the approval prompt while it runs.
_active_watcher: "_EscAbortWatcher | None" = None


def _esc_watcher_active(ui: UIHandler) -> bool:
  """Is it safe to poke at the raw terminal right now?

  The Esc-Esc abort watcher owns stdin in cbreak mode while a turn runs.
  It must not be active in batch mode (stdin may not be a TTY) nor while a
  handler owns the terminal itself (the interactive approval prompt reads
  via ``input()`` — stealing those keystrokes would corrupt it).
  """
  if not sys.stdin.isatty():
    return False
  is_tty = getattr(ui, "_is_tty", None)
  return True if is_tty is None else bool(is_tty)


class _EscAbortWatcher:
  """Reads stdin in cbreak mode during a turn and triggers abort on Esc Esc.

  The turn runs with stdin inherited from the REPL; prompt_toolkit is idle
  (the user is not at the prompt while the agent is working). This watcher
  flips the terminal into cbreak mode for the duration of the turn and
  watches for a double-Esc (within ``_DOUBLE_ESC_WINDOW`` seconds). A
  single Esc is inert; other keys are consumed and dropped (the user
  should not be typing mid-turn anyway).

  On POSIX this uses ``termios``/``tty`` + ``os.read`` on stdin driven by
  the event loop's reader callback. On Windows or when stdin is not a
  TTY the watcher is a no-op; Esc-Esc then has no effect (the turn can
  still be aborted programmatically via ``Agent.abort()``).

  Terminal state is always restored on exit (best-effort, ``finally``).
  """

  _DOUBLE_ESC_WINDOW = 0.6

  def __init__(self, session: Session | None, ui: UIHandler) -> None:
    self._session = session
    self._ui = ui
    self._fd: int | None = None
    self._saved: Any = None
    self._loop: asyncio.AbstractEventLoop | None = None
    self._last_esc: float | None = None
    self._active = False

  def start(self) -> None:
    if self._session is None or not _esc_watcher_active(self._ui):
      return
    try:
      import termios
      import tty
    except ImportError:  # non-POSIX platform
      logger.debug("esc_watcher_unavailable", reason="no termios")
      return
    try:
      self._fd = sys.stdin.fileno()
      self._saved = termios.tcgetattr(self._fd)
      tty.setcbreak(self._fd)
      self._loop = asyncio.get_running_loop()
      self._loop.add_reader(self._fd, self._on_readable)
      self._active = True
    except (OSError, termios.error, ValueError) as e:
      logger.debug("esc_watcher_unavailable", reason=str(e))
      self._restore()

  def pause(self) -> None:
    """Temporarily restore the terminal and detach the read callback.

    Used while another component (the approval prompt, which reads via
    ``input()``) owns stdin, so the watcher never races it for keystrokes.
    """
    if not self._active:
      return
    if self._loop is not None and self._fd is not None:
      try:
        self._loop.remove_reader(self._fd)
      except (OSError, ValueError):
        pass
    self._restore_terminal_only()

  def resume(self) -> None:
    """Re-attach after a :meth:`pause`. Best-effort; failure leaves the
    watcher inactive for the rest of the turn (abort simply unavailable)."""
    if self._fd is None or self._saved is None:
      return
    try:
      import tty

      tty.setcbreak(self._fd)
      if self._loop is not None:
        self._loop.add_reader(self._fd, self._on_readable)
    except Exception as e:
      logger.debug("esc_watcher_resume_failed", reason=str(e))
      self.stop()

  def stop(self) -> None:
    if not self._active and self._fd is None:
      return
    self._active = False
    if self._loop is not None and self._fd is not None:
      try:
        self._loop.remove_reader(self._fd)
      except (OSError, ValueError):
        pass
    self._restore()

  def _restore_terminal_only(self) -> None:
    if self._fd is not None and self._saved is not None:
      try:
        import termios

        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
      except Exception:
        logger.warning("esc_watcher_restore_failed")

  def _restore(self) -> None:
    if self._fd is not None and self._saved is not None:
      try:
        import termios

        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
      except Exception:
        logger.warning("esc_watcher_restore_failed")
    self._fd = None
    self._saved = None
    self._loop = None

  def _on_readable(self) -> None:
    try:
      data = os.read(self._fd, 64)  # type: ignore[arg-type]
    except OSError:
      self.stop()
      return
    if not data:
      return
    now = time.monotonic()
    for byte in data:
      if byte == 0x1B:  # ESC
        if self._last_esc is not None and (now - self._last_esc) <= self._DOUBLE_ESC_WINDOW:
          self._last_esc = None
          self._trigger()
          return
        self._last_esc = now
      else:
        # Any other byte breaks the double-Esc sequence.
        self._last_esc = None

  def _trigger(self) -> None:
    logger.info("esc_abort_requested")
    try:
      assert self._session is not None
      self._session.abort_foreground()
    except Exception:
      logger.exception("esc_abort_failed")


async def _process_turn(
  agent: Agent,
  message: str,
  ui: UIHandler,
  session: Session | None,
) -> None:
  """Run one turn with the Esc-Esc abort watcher active.

  The watcher is a no-op outside interactive TTY sessions; the abort
  itself is delivered via :meth:`Session.abort_foreground`, which resolves
  the deepest (spawned) agent before falling back to the primary.
  """
  global _active_watcher
  watcher = _EscAbortWatcher(session, ui)
  _active_watcher = watcher
  watcher.start()

  interrupted = {"count": 0}

  def _sigint_abort(_signum, _frame):  # type: ignore[no-untyped-def]
    # Ctrl+C during a turn: first press requests the same clean abort as
    # Esc-Esc and the process exits once the turn unwinds (see below).
    # A second press force-exits immediately.
    interrupted["count"] += 1
    if interrupted["count"] > 1:
      signal.signal(signal.SIGINT, signal.default_int_handler)
      raise KeyboardInterrupt
    target = (session.foreground_agent if session is not None else None) or agent
    target.abort()

  try:
    previous_sigint = signal.signal(signal.SIGINT, _sigint_abort)
  except ValueError:
    # Not in the main thread — leave the default KeyboardInterrupt behavior.
    previous_sigint = None
  try:
    try:
      await agent.process(message)
    except TurnAbortedError:
      if interrupted["count"]:
        # Ctrl+C triggered this abort — unwind out of the REPL like a
        # normal Ctrl+C, but only after the turn tore down cleanly.
        raise _TurnInterrupt() from None
      # Esc-Esc: stay in the session.
      raise
  finally:
    if previous_sigint is not None:
      signal.signal(signal.SIGINT, previous_sigint)
    watcher.stop()
    _active_watcher = None


async def _run_repl(
  agent: Agent,
  ui: UIHandler,
  commands: CommandRegistry,
  prompt: str = "",
  session: Session | None = None,
) -> None:
  """Run the interactive or batch REPL loop.

  Handles user input, command dispatch, agent processing, and errors. All
  output is produced through the UI handler. The UI is always shut down.

  When ``prompt`` is non-empty, it is sent to the agent as the first message
  before entering the REPL loop. The response is shown, then the user can
  continue the conversation interactively.

  When ``session`` is provided (interactive CLI), an Esc-Esc keypress during
  a turn requests a clean abort of the foreground agent's turn via
  :meth:`Session.abort_foreground`; the REPL then returns to the prompt.
  """
  await ui.start(agent)

  try:
    if prompt.strip():
      try:
        await _process_turn(agent, prompt, ui, session)
      except NetworkError as e:
        ui.output_error(e)
        if not e.recoverable:
          return
      except TimeoutError as e:
        ui.output_error(e)
      except ResponseError as e:
        ui.output_error(e)
      except TurnAbortedError:
        # The TURN_ABORTED event already surfaced the notice via the UI
        # handler; just return to the prompt.
        pass
      except YokerError as e:
        ui.output_error(e)
        return
      except Exception as e:
        ui.output_error(e)
        return
      except KeyboardInterrupt:
        return

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
          await _process_turn(agent, user_input, ui, session)

      except NetworkError as e:
        ui.output_error(e)
        if not e.recoverable:
          break
      except TimeoutError as e:
        ui.output_error(e)
        continue
      except ResponseError as e:
        ui.output_error(e)
        continue
      except TurnAbortedError:
        # The TURN_ABORTED event already surfaced the notice via the UI
        # handler; just return to the prompt.
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
