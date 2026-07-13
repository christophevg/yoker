"""``yoker run <source>`` subcommand handler — the flagship capability.

Loads an agentic package from one of four source types (module, GitHub URL,
folder, zip) and runs it non-interactively. The source's ``agent.toml``
manifest specifies which agent to use and what initial prompt to send; CLI
``--agent`` and ``--prompt`` override the manifest.

Security invariant (C1, M3, H2 remediation): the source MUST pass
:func:`yoker.plugins.security.check_source_allowed` before
:func:`yoker.cli.sources.load_source` is called. The trust gate fires on
the user's own config (not the source's manifest overrides) so a source
cannot influence its own trust decision.

Flow::

    resolve_source (phase 1 — metadata only)
      -> [dry-run: print + exit]
      -> trust gate (check_source_allowed)
      -> load_source (phase 2 — imports, AFTER trust)
      -> apply manifest config overrides
      -> resolve agent + prompt (CLI > manifest)
      -> [prompt length cap: 10 KB]
      -> Session + Agent + process prompt
      -> output response via UI handler
      -> cleanup temp files
"""

import asyncio
import dataclasses
import os
import sys
from typing import Any

from clevis import SecurityError
from structlog import get_logger

from yoker.cli.commands import RunConfig
from yoker.cli.shared import abort, load_subcommand_config
from yoker.cli.sources import LoadedSource, ResolvedSource, load_source, resolve_source
from yoker.config import Config
from yoker.exceptions import YokerError
from yoker.logging import configure_logging
from yoker.plugins.security import check_source_allowed
from yoker.session import Session
from yoker.ui import BatchUIHandler, UIBridge

logger = get_logger(__name__)

# Prompt length cap (H2 remediation) — 10 KB.
MAX_PROMPT_BYTES = 10 * 1024


def run_run(plugin_packages: list[str]) -> None:
  """Run the ``yoker run <source>`` subcommand.

  Args:
    plugin_packages: Plugin packages from ``--with`` flags (shared with chat).
  """
  # Parse --agent and --prompt via local argparse (not Clevis — these are not
  # Config fields). Strip them from sys.argv before Clevis parses RunConfig.
  cli_agent, cli_prompt, sys.argv = _parse_run_overrides(sys.argv)

  try:
    config = load_subcommand_config(RunConfig)
  except (ValueError, SecurityError) as e:
    abort(f"Error: {e}\n", 1)

  if not config.source:
    abort("Error: yoker run requires a source. Usage: yoker run <source>\n", 1)

  CONSOLE_LOGGING = os.environ.get("YOKER_CONSOLE_LOGGING", "NO") != "NO"
  configure_logging(config.logging, console=CONSOLE_LOGGING)

  # Phase 1: resolve source (metadata only — safe, no code execution).
  try:
    resolved = resolve_source(config.source)
  except YokerError as e:
    abort(f"Error: {e}\n", 1)

  # --dry-run: print resolved info and exit without executing.
  if config.dry_run:
    _print_dry_run(resolved)
    _safe_cleanup(resolved)
    return

  # Trust gate (SECURITY INVARIANT — before load_source).
  # Uses the user's config, NOT manifest-overridden, so the source cannot
  # influence its own trust decision.
  if not check_source_allowed(resolved.trust_key, config, resolved):
    abort(f"Error: source '{resolved.trust_key}' is not trusted.\n", 1)

  # Phase 2: load source (imports — AFTER trust gate).
  try:
    loaded = load_source(resolved)
  except YokerError as e:
    _safe_cleanup(resolved)
    abort(f"Error: {e}\n", 1)

  # Apply manifest config overrides (after trust — source is trusted).
  if resolved.manifest is not None and resolved.manifest.config_overrides:
    _apply_config_overrides(config, resolved.manifest.config_overrides)

  # Resolve agent name: CLI --agent > manifest [run].agent > error.
  agent_name = cli_agent
  if agent_name is None:
    agent_name = loaded.agent
  if not agent_name:
    _safe_cleanup(loaded)
    abort(
      "Error: no agent specified. Use --agent <name> or add [run] agent = "
      '"<name>" to the source\'s agent.toml.\n',
      1,
    )
  assert agent_name is not None  # abort exits, but mypy can't infer that

  # Resolve prompt: CLI --prompt > manifest [run].prompt > error.
  prompt = cli_prompt
  if prompt is None:
    prompt = loaded.prompt
  if not prompt:
    _safe_cleanup(loaded)
    abort(
      "Error: no prompt specified. Use --prompt <text> or add [run] prompt = "
      '"<text>" to the source\'s agent.toml.\n',
      1,
    )
  assert prompt is not None  # abort exits, but mypy can't infer that

  # Prompt length cap (H2).
  prompt_bytes = len(prompt.encode("utf-8"))
  if prompt_bytes > MAX_PROMPT_BYTES:
    _safe_cleanup(loaded)
    abort(
      f"Error: prompt exceeds {MAX_PROMPT_BYTES} bytes "
      f"({prompt_bytes} bytes). Reduce the prompt length.\n",
      1,
    )

  # Persistence: without --persist, the run is stateless.
  if not config.persist:
    config.context.persist_after_turn = False

  session_id = config.session_id if config.persist else None

  try:
    asyncio.run(
      _run_source(
        config,
        loaded,
        agent_name,
        prompt,
        plugin_packages,
        session_id,
      )
    )
  except (ValueError, SecurityError) as e:
    abort(f"Error: {e}\n", 1)
  finally:
    _safe_cleanup(loaded)


async def _run_source(
  config: RunConfig,
  loaded: LoadedSource,
  agent_name: str,
  prompt: str,
  plugin_packages: list[str],
  session_id: str | None,
) -> None:
  """Construct the Session, register source components, and run the prompt."""
  async with Session(
    config=config,
    extra_plugins=tuple(plugin_packages),
    session_id=session_id,
  ) as session:
    # Register source agent definitions (source wins on conflict — owner-confirmed).
    _register_source_agents(session, loaded)

    # Register source tools and skills onto the primary agent.
    if loaded.components.tools:
      session.agent.tools.register_plugin_tools([loaded.components], config)
    if loaded.components.skills:
      session.agent.skills.register_plugin_skills([loaded.components])

    # Wire the UI bridge (batch mode — non-interactive output to stdout/stderr).
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


def _register_source_agents(session: Session, loaded: LoadedSource) -> None:
  """Register the source's agent definitions into the session registry.

  Source wins on conflict: if a name collides with a built-in or configured
  agent, the source's definition replaces it (owner-confirmed per task 4.7).
  """
  if not loaded.components.agents:
    return
  for agent_def in loaded.components.agents:
    name = agent_def.name
    if name in session.agents.data:
      logger.info("source_agent_overrides_builtin", name=name)
      del session.agents.data[name]
    session.agents.register(agent_def, namespace=loaded.components.source)


def _parse_run_overrides(
  argv: list[str],
) -> tuple[str | None, str | None, list[str]]:
  """Extract ``--agent`` and ``--prompt`` from argv (local argparse, not Clevis).

  Returns ``(agent, prompt, cleaned_argv)`` where ``cleaned_argv`` has the
  ``--agent``/``--prompt`` flags and their values removed, so Clevis doesn't
  choke on unknown args when parsing RunConfig.
  """
  agent: str | None = None
  prompt: str | None = None
  args_to_remove: list[int] = []
  i = 1
  while i < len(argv):
    arg = argv[i]
    if arg == "--agent" and i + 1 < len(argv):
      agent = argv[i + 1]
      args_to_remove.extend([i, i + 1])
      i += 2
    elif arg == "--prompt" and i + 1 < len(argv):
      prompt = argv[i + 1]
      args_to_remove.extend([i, i + 1])
      i += 2
    else:
      i += 1

  cleaned = list(argv)
  for idx in sorted(args_to_remove, reverse=True):
    cleaned.pop(idx)
  return agent, prompt, cleaned


def _print_dry_run(resolved: ResolvedSource) -> None:
  """Print resolved source info for ``--dry-run`` without executing."""
  out = sys.stdout
  out.write(f"Source:      {resolved.source_string}\n")
  out.write(f"Kind:        {resolved.kind}\n")
  out.write(f"Trust key:   {resolved.trust_key}\n")
  out.write(f"Path:        {resolved.path}\n")
  if resolved.manifest is not None:
    out.write("\n[run] section:\n")
    out.write(f"  agent:  {resolved.manifest.run_config.agent!r}\n")
    out.write(f"  prompt: {resolved.manifest.run_config.prompt!r}\n")
    out.write("\n[plugin] section:\n")
    pc = resolved.manifest.plugin_config
    out.write(f"  skills_dir:   {pc.skills_dir}\n")
    out.write(f"  agents_dir:   {pc.agents_dir}\n")
    out.write(f"  tools_module: {pc.tools_module!r}\n")
    if resolved.manifest.config_overrides:
      out.write("\nConfig overrides:\n")
      for key, value in resolved.manifest.config_overrides.items():
        out.write(f"  {key}: {value}\n")
  else:
    out.write("\nNo agent.toml manifest found.\n")
  out.write("\n(dry-run — no code executed)\n")


def _apply_config_overrides(config: Config, overrides: dict[str, Any]) -> None:
  """Deep-merge manifest config overrides into the config dataclass.

  The source is already trusted (trust gate passed), so its overrides are
  from a trusted source. Nested dicts recurse into dataclass attributes;
  non-dict values replace the field directly. Lists/tuples replace (matching
  TOML array semantics for tuple-typed fields).
  """
  for key, value in overrides.items():
    if not hasattr(config, key):
      logger.warning("manifest_override_unknown_field", field=key)
      continue
    current = getattr(config, key)
    if (
      isinstance(value, dict)
      and dataclasses.is_dataclass(current)
      and not isinstance(current, type)
    ):
      _apply_config_overrides(current, value)  # type: ignore[arg-type]
    else:
      setattr(config, key, value)


def _safe_cleanup(obj: ResolvedSource | LoadedSource) -> None:
  """Run the cleanup hook if present (removes temp dirs for github/zip)."""
  cleanup = getattr(obj, "cleanup", None)
  if cleanup is not None:
    try:
      cleanup()
    except Exception:
      logger.warning("source_cleanup_failed", error="cleanup raised")


__all__ = ["run_run"]
