"""``yoker loop <source>`` subcommand handler — interval execution.

Runs an agentic package at intervals, reusing the shared source resolution
and execution path. The source is resolved ONCE, the trust gate fires ONCE,
and the source is loaded ONCE; each iteration then sends the same prompt
(from the manifest or ``--prompt``) through the agent.

Security (M1 remediation):
  - ``--max-iterations`` defaults to a finite cap (100), not unlimited.
  - ``--max-duration`` provides a wall-clock timeout (optional).
  - The loop stops after 3 consecutive failures with exponential backoff.
  - Per-iteration timeout reuses ``config.tools.agent.timeout_seconds``.
  - API cost warning is included in the docstring/help.

Config cascade (corrected — same as run)::

    resolve_source (phase 1)
      -> trust gate (check_source_allowed — user's OWN config, no manifest)
      -> load_source (phase 2 — AFTER trust)
      -> reload config WITH manifest overrides (CLI still wins over manifest)
      -> resolve agent + prompt (CLI > manifest)
      -> [prompt length cap: 10 KB]
      -> loop:
           -> print iteration number + timestamp
           -> Session + Agent + process(prompt) [with per-iteration timeout]
           -> on success: reset failure counter, sleep interval
           -> on failure: increment failure counter, exponential backoff
           -> stop if max_iterations / max_duration / 3 failures / Ctrl+C
      -> cleanup temp files
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timezone

from clevis import SecurityError
from structlog import get_logger

from yoker.cli.commands import LoopConfig
from yoker.cli.shared import (
  MAX_PROMPT_BYTES,
  abort,
  load_subcommand_config,
  load_subcommand_config_with_manifest,
  parse_run_overrides,
  register_source_agents,
  resolve_agent_and_prompt,
  safe_cleanup,
)
from yoker.cli.sources import LoadedSource, load_source, resolve_source
from yoker.exceptions import YokerError
from yoker.logging import configure_logging
from yoker.plugins.security import check_source_allowed
from yoker.session import Session
from yoker.ui import BatchUIHandler, UIBridge

logger = get_logger(__name__)

# Stop after this many consecutive failures (M1 remediation).
MAX_CONSECUTIVE_FAILURES = 3
# Base backoff in seconds; actual backoff is 2 ** failures * base.
_BACKOFF_BASE = 2


def run_loop(plugin_packages: list[str]) -> None:
  """Run the ``yoker loop <source>`` subcommand.

  Args:
    plugin_packages: Plugin packages from ``--with`` flags (shared with chat).
  """
  cli_agent, cli_prompt, sys.argv = parse_run_overrides(sys.argv)

  try:
    config = load_subcommand_config(LoopConfig)
  except (ValueError, SecurityError) as e:
    abort(f"Error: {e}\n", 1)

  if not config.source:
    abort("Error: yoker loop requires a source. Usage: yoker loop <source>\n", 1)

  CONSOLE_LOGGING = os.environ.get("YOKER_CONSOLE_LOGGING", "NO") != "NO"
  configure_logging(config.logging, console=CONSOLE_LOGGING)

  # Phase 1: resolve source ONCE (metadata only — no code execution).
  try:
    resolved = resolve_source(config.source)
  except YokerError as e:
    abort(f"Error: {e}\n", 1)

  # Trust gate ONCE (before load_source — user's OWN config, no manifest).
  if not check_source_allowed(resolved.trust_key, config, resolved):
    safe_cleanup(resolved)
    abort(f"Error: source '{resolved.trust_key}' is not trusted.\n", 1)

  # Phase 2: load source ONCE (imports — AFTER trust gate).
  try:
    loaded = load_source(resolved)
  except YokerError as e:
    safe_cleanup(resolved)
    abort(f"Error: {e}\n", 1)

  # Apply manifest config overrides BEFORE CLI (CLI wins over manifest).
  if resolved.manifest is not None and resolved.manifest.config_overrides:
    try:
      config = load_subcommand_config_with_manifest(LoopConfig, resolved.manifest.config_overrides)
    except (ValueError, SecurityError) as e:
      safe_cleanup(loaded)
      abort(f"Error: {e}\n", 1)

  # Resolve agent name + prompt: CLI > manifest > error.
  agent_name, prompt = resolve_agent_and_prompt(cli_agent, cli_prompt, loaded)

  # Prompt length cap (H2).
  prompt_bytes = len(prompt.encode("utf-8"))
  if prompt_bytes > MAX_PROMPT_BYTES:
    safe_cleanup(loaded)
    abort(
      f"Error: prompt exceeds {MAX_PROMPT_BYTES} bytes "
      f"({prompt_bytes} bytes). Reduce the prompt length.\n",
      1,
    )

  # Persistence: without --persist, each iteration is stateless.
  if not config.persist:
    config.context.persist_after_turn = False

  session_id = config.session_id if config.persist else None

  # Per-iteration timeout from agent tool config.
  iteration_timeout = config.tools.agent.timeout_seconds

  try:
    asyncio.run(
      _run_loop(
        config,
        loaded,
        agent_name,
        prompt,
        plugin_packages,
        session_id,
        iteration_timeout,
      )
    )
  except (ValueError, SecurityError) as e:
    abort(f"Error: {e}\n", 1)
  finally:
    safe_cleanup(loaded)


async def _run_loop(
  config: LoopConfig,
  loaded: LoadedSource,
  agent_name: str,
  prompt: str,
  plugin_packages: list[str],
  session_id: str | None,
  iteration_timeout: int,
) -> None:
  """Run the iteration loop with max/max-duration/backoff/Ctrl+C handling.

  Prints iteration number and timestamp before each run. Stops on
  ``max_iterations``, ``max_duration``, 3 consecutive failures, or Ctrl+C.
  """
  max_iterations = config.max_iterations
  max_duration = config.max_duration
  interval = config.interval

  out = sys.stdout
  start_time = time.monotonic()
  consecutive_failures = 0
  completed = 0
  stopped_reason = "max iterations reached"

  # Install a SIGINT handler that sets a stop flag (graceful shutdown).
  stop_flag = asyncio.Event()

  def _sigint_handler() -> None:
    out.write("\nCtrl+C received — stopping loop gracefully...\n")
    out.flush()
    stop_flag.set()

  loop = asyncio.get_running_loop()
  try:
    loop.add_signal_handler(signal.SIGINT, _sigint_handler)
  except NotImplementedError:
    # add_signal_handler is not available on all platforms (e.g. Windows).
    # Fall back to KeyboardInterrupt catching in the loop below.
    pass

  try:
    for i in range(1, max_iterations + 1):
      if stop_flag.is_set():
        stopped_reason = "interrupted by user (Ctrl+C)"
        break

      if max_duration is not None:
        elapsed = time.monotonic() - start_time
        if elapsed >= max_duration:
          stopped_reason = "max duration reached"
          break

      ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
      out.write(f"\n--- Iteration {i}/{max_iterations} [{ts}] ---\n")
      out.flush()

      try:
        await asyncio.wait_for(
          _run_iteration(config, loaded, agent_name, prompt, plugin_packages, session_id),
          timeout=iteration_timeout,
        )
        completed += 1
        consecutive_failures = 0
      except asyncio.TimeoutError:
        consecutive_failures += 1
        out.write(f"Iteration {i} timed out after {iteration_timeout}s\n")
        logger.warning("loop_iteration_timeout", iteration=i)
      except Exception as e:
        consecutive_failures += 1
        out.write(f"Iteration {i} failed: {e}\n")
        logger.warning("loop_iteration_failed", iteration=i, error=str(e))

      if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        stopped_reason = f"{MAX_CONSECUTIVE_FAILURES} consecutive failures"
        break

      if consecutive_failures > 0:
        backoff = _BACKOFF_BASE**consecutive_failures
        out.write(f"Backing off for {backoff}s (failure {consecutive_failures})\n")
        await _interruptible_sleep(backoff, stop_flag)
        if stop_flag.is_set():
          stopped_reason = "interrupted by user (Ctrl+C)"
          break

      # Normal interval sleep (skip after the last iteration).
      if i < max_iterations and not stop_flag.is_set():
        await _interruptible_sleep(interval, stop_flag)
  finally:
    try:
      loop.remove_signal_handler(signal.SIGINT)
    except (NotImplementedError, RuntimeError):
      pass

  elapsed_total = time.monotonic() - start_time
  out.write(f"\nLoop finished: {completed} iterations completed in {elapsed_total:.1f}s\n")
  out.write(f"Reason: {stopped_reason}\n")


async def _run_iteration(
  config: LoopConfig,
  loaded: LoadedSource,
  agent_name: str,
  prompt: str,
  plugin_packages: list[str],
  session_id: str | None,
) -> None:
  """Run a single iteration: construct Session, register components, process prompt."""
  async with Session(
    config=config,
    extra_plugins=tuple(plugin_packages),
    session_id=session_id,
  ) as session:
    register_source_agents(session, loaded)

    if loaded.components.tools:
      session.agent.tools.register_plugin_tools([loaded.components], config)
    if loaded.components.skills:
      session.agent.skills.register_plugin_skills([loaded.components])

    ui = BatchUIHandler(
      show_thinking=config.ui.show_thinking,
      show_tool_calls=config.ui.show_tool_calls,
      show_stats=config.ui.show_stats,
    )
    bridge = UIBridge(ui)
    session.on_event(bridge)

    await ui.start(session.agent)
    try:
      await session.agent.process(prompt)
    except YokerError as e:
      ui.output_error(e)
      raise
    finally:
      await ui.shutdown("done")


async def _interruptible_sleep(seconds: int, stop_flag: asyncio.Event) -> None:
  """Sleep for ``seconds`` but wake early if ``stop_flag`` is set."""
  try:
    await asyncio.wait_for(stop_flag.wait(), timeout=seconds)
  except asyncio.TimeoutError:
    pass  # normal — the full interval elapsed


__all__ = ["run_loop"]
