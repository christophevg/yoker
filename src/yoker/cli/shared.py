"""Shared helpers for CLI subcommands.

Centralizes config loading, the dev/test security bypass, and source-handling
utilities (cleanup, agent registration, agent/prompt resolution, manifest-aware
config loading) so each subcommand handler stays thin and DRY.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from clevis import SecurityAction, SecurityConfig, get_config

from yoker.cli.sources import LoadedSource

if TYPE_CHECKING:
  from yoker.session import Session

T = TypeVar("T")

# Prompt length cap (H2 remediation) — 10 KB. Shared by run and loop.
MAX_PROMPT_BYTES = 10 * 1024


def get_security_config() -> SecurityConfig | None:
  """Build a SecurityConfig with dev/test bypass when appropriate.

  Mirrors the logic in :func:`yoker.config.get_yoker_config`: relax file/directory
  permission checks (log instead of reject) when ``YOKER_DEV_MODE=1`` is set or
  when running under pytest (``PYTEST_CURRENT_TEST`` present).
  """
  if os.environ.get("YOKER_DEV_MODE") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
    return SecurityConfig(
      file_permissions=SecurityAction.LOG,
      directory_permissions=SecurityAction.LOG,
    )
  return None


def load_subcommand_config(config_class: type[T]) -> T:
  """Load a subcommand config class via Clevis with yoker's security policy.

  Each config-backed subcommand calls this with its own ``@configclass(cmd=...)``
  config class. Clevis parses the subcommand's CLI args and merges TOML layers
  (user → project → subcommand section extraction → CLI) into the returned
  instance.
  """
  return get_config(config_class, name="yoker", cli=True, security=get_security_config())


def load_subcommand_config_with_manifest(
  config_class: type[T],
  manifest_overrides: dict[str, Any],
) -> T:
  """Load a subcommand config with manifest overrides applied BEFORE CLI parsing.

  Implements the correct cascade::

      dataclass defaults
        -> user TOML (~/.yoker.toml)
        -> project TOML (./yoker.toml)
        -> subcommand section extraction ([run]/[loop]/...)
        -> manifest overrides (<source>/agent.toml)
        -> CLI arguments (highest priority)

  This mirrors :func:`clevis.get_config` but inserts the manifest override
  layer between subcommand-section extraction and CLI arg parsing, so CLI
  always wins over the source's manifest. ``from_dict`` runs ``__post_init__``
  validation on the final merged dict (no ``setattr`` bypass).

  Args:
    config_class: The ``@configclass(cmd=...)`` subcommand config class.
    manifest_overrides: Config overrides from the source's ``agent.toml``
      (the ``config_overrides`` field of :class:`FileManifestResult`).

  Returns:
    A fully merged and validated config instance.
  """
  from clevis import (
    ConfigError,
    apply_to_dict,
    check_directory_permissions,
    check_file_permissions,
    deep_merge,
    get_factory,
    load_toml_from_fd,
  )
  from dacite import Config as DaciteConfig
  from dacite import from_dict

  security = get_security_config()
  if security is None:
    security = {
      "file_permissions": SecurityAction.REJECT,
      "directory_permissions": SecurityAction.REJECT,
    }
  file_action = security.get("file_permissions", SecurityAction.REJECT)
  dir_action = security.get("directory_permissions", SecurityAction.REJECT)

  # 1. Load base config dict from user + project TOML (mirrors clevis.get_config).
  cfg: dict[str, Any] = {}
  user_config = Path.home() / ".yoker.toml"
  project_config = Path.cwd() / "yoker.toml"
  check_directory_permissions(user_config, dir_action)
  check_directory_permissions(project_config, dir_action)
  _, user_fd = check_file_permissions(user_config, file_action)
  if user_fd is not None:
    cfg.update(load_toml_from_fd(user_fd))
  _, project_fd = check_file_permissions(project_config, file_action)
  if project_fd is not None:
    cfg.update(load_toml_from_fd(project_fd))

  # 2. Extract subcommand section (e.g. [run]) — same logic as clevis.get_config.
  factory = get_factory(config_class)
  toml_key = factory.config or factory.cmd
  if toml_key and toml_key in cfg:
    cmd_cfg = cfg.pop(toml_key)
    if isinstance(cmd_cfg, dict):
      cfg.clear()
      cfg.update(cmd_cfg)
    else:
      raise ConfigError(
        message=(
          f"Configuration section '{toml_key}' must be a table, got {type(cmd_cfg).__name__}"
        ),
        field_path=toml_key,
        config_name="yoker",
      )

  # 3. Deep-merge manifest overrides (between TOML and CLI — CLI wins).
  if manifest_overrides:
    cfg = deep_merge(cfg, manifest_overrides)

  # 4. Apply CLI args on top (highest priority).
  apply_to_dict(factory.get_args(), cfg)

  # 5. Convert merged dict to config (runs __post_init__ validation).
  return from_dict(data_class=config_class, data=cfg, config=DaciteConfig(cast=[tuple, set]))


def abort(msg: str, code: int) -> None:
  """Write ``msg`` to stderr and exit with ``code``.

  Shared by :mod:`yoker.__main__` (plugin arg parsing) and subcommand handlers
  (chat, init, config) for consistent error-exit behaviour.
  """
  sys.stderr.write(msg)
  sys.exit(code)


def safe_cleanup(obj: Any) -> None:
  """Run the cleanup hook if present (removes temp dirs for github/zip sources).

  Works for any object exposing an optional ``cleanup`` callable
  (:class:`ResolvedSource` or :class:`LoadedSource`). Failures are logged, not
  propagated — cleanup is best-effort during error shutdown.
  """
  cleanup = getattr(obj, "cleanup", None)
  if cleanup is not None:
    try:
      cleanup()
    except Exception:
      from structlog import get_logger

      get_logger(__name__).warning("source_cleanup_failed", error="cleanup raised")


def parse_run_overrides(
  argv: list[str],
) -> tuple[str | None, str | None, list[str]]:
  """Extract ``--agent`` and ``--prompt`` from argv (local argparse, not Clevis).

  Returns ``(agent, prompt, cleaned_argv)`` where ``cleaned_argv`` has the
  ``--agent``/``--prompt`` flags and their values removed, so Clevis doesn't
  choke on unknown args when parsing RunConfig/LoopConfig.
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


def register_source_agents(session: Session, loaded: LoadedSource) -> None:
  """Register the source's agent definitions into the session registry.

  Source wins on conflict: if a name collides with a built-in or configured
  agent, the source's definition replaces it via
  :meth:`AgentRegistry.override` (owner-confirmed per task 4.7).
  """
  if not loaded.components.agents:
    return
  for agent_def in loaded.components.agents:
    session.agents.override(agent_def, namespace=loaded.components.source)


def resolve_agent_and_prompt(
  cli_agent: str | None,
  cli_prompt: str | None,
  loaded: LoadedSource,
) -> tuple[str, str]:
  """Resolve agent name and prompt: CLI > manifest > error.

  Aborts with a clear message if neither CLI nor the manifest provides a value.
  Returns ``(agent_name, prompt)`` as non-None strings.
  """
  agent_name = cli_agent
  if agent_name is None:
    agent_name = loaded.agent
  if not agent_name:
    safe_cleanup(loaded)
    abort(
      "Error: no agent specified. Use --agent <name> or add [run] agent = "
      '"<name>" to the source\'s agent.toml.\n',
      1,
    )
  assert agent_name is not None  # abort exits, but mypy can't infer that

  prompt = cli_prompt
  if prompt is None:
    prompt = loaded.prompt
  if not prompt:
    safe_cleanup(loaded)
    abort(
      "Error: no prompt specified. Use --prompt <text> or add [run] prompt = "
      '"<text>" to the source\'s agent.toml.\n',
      1,
    )
  assert prompt is not None  # abort exits, but mypy can't infer that
  return agent_name, prompt


__all__ = [
  "MAX_PROMPT_BYTES",
  "abort",
  "get_security_config",
  "load_subcommand_config",
  "load_subcommand_config_with_manifest",
  "parse_run_overrides",
  "register_source_agents",
  "resolve_agent_and_prompt",
  "safe_cleanup",
]
