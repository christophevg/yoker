"""``yoker init`` subcommand handler — generate a default configuration file.

Non-interactive mode (``--no-interactive``) writes a default ``~/.yoker.toml``
using :func:`yoker.config.writer.write_config` with all values at defaults.
Interactive mode (default) runs the existing :class:`BootstrapWizard` for
guided first-run setup.

Security:
  - ``--path`` is validated against forbidden system prefixes (``/etc``,
    ``/usr``, etc.) via :func:`yoker.context.validator.validate_storage_path`.
  - ``--force`` overwrites an existing file; when stdin is a TTY the user must
    confirm interactively before the overwrite happens.
  - Written files always have ``chmod 0600`` (enforced by :func:`write_config`).
"""

import asyncio
import sys
from pathlib import Path

from yoker.cli.commands import InitConfig
from yoker.cli.shared import abort, load_subcommand_config
from yoker.config import Config
from yoker.config.writer import write_config
from yoker.context.validator import validate_storage_path
from yoker.exceptions import ValidationError
from yoker.ui import InteractiveUIHandler


def _default_config_path() -> Path:
  """Return the default config destination: ``~/.yoker.toml``."""
  return Path.home() / ".yoker.toml"


def run_init() -> None:
  """Run the ``yoker init`` subcommand.

  Loads :class:`InitConfig` via Clevis (parses ``--no-interactive``,
  ``--path``, ``--force``), then dispatches to the interactive wizard or the
  non-interactive default-config writer.
  """
  try:
    init_config = load_subcommand_config(InitConfig)
  except (ValueError, ValidationError) as e:
    abort(f"Error: {e}\n", 1)

  target_path = _resolve_path(init_config.path)

  if init_config.no_interactive:
    _write_default_config(target_path, force=init_config.force)
  else:
    _run_interactive(target_path, force=init_config.force)


def _resolve_path(path: str | None) -> Path:
  """Resolve and validate the target config path.

  When ``path`` is ``None``, defaults to ``~/.yoker.toml``. Validates the
  resolved path against forbidden system prefixes.
  """
  raw = Path(path).expanduser() if path else _default_config_path()
  try:
    # validate_storage_path resolves to absolute and rejects forbidden prefixes.
    validate_storage_path(raw, "init.path")
  except ValidationError as e:
    abort(f"Error: {e}\n", 1)
  return raw


def _write_default_config(path: Path, *, force: bool) -> None:
  """Write a default config to ``path`` with ``chmod 0600``.

  Refuses to overwrite an existing file unless ``force`` is True. When
  overwriting and stdin is a TTY, asks for interactive confirmation.
  """
  if path.exists() and not force:
    abort(
      f"Error: {path} already exists. Use --force to overwrite.\n",
      1,
    )

  if path.exists() and force and sys.stdin.isatty():
    if not _confirm_overwrite(path):
      abort("Aborted. No configuration written.\n", 0)

  try:
    write_config(Config(), path)
  except OSError as e:
    abort(f"Error: could not write {path}: {e}\n", 1)

  sys.stdout.write(f"Configuration written to {path} (chmod 600).\n")


def _run_interactive(path: Path, *, force: bool) -> None:
  """Run the BootstrapWizard for interactive guided setup.

  If the target config already exists and ``force`` is not set, refuse to
  overwrite (the wizard itself assumes no config exists). When ``force`` is
  set and stdin is a TTY, ask for confirmation before proceeding.
  """
  if path.exists() and not force:
    abort(
      f"Error: {path} already exists. Use --force to overwrite.\n",
      1,
    )

  if path.exists() and force and sys.stdin.isatty():
    if not _confirm_overwrite(path):
      abort("Aborted. No configuration written.\n", 0)

  if not sys.stdin.isatty():
    abort(
      "Error: interactive init requires a TTY. Use --no-interactive to write defaults.\n",
      1,
    )

  # history_file="none" prevents bootstrap prompts (including API keys) from
  # being persisted to ~/.yoker_history.
  ui = InteractiveUIHandler(history_file="none")
  from yoker.bootstrap import BootstrapResult, BootstrapWizard

  try:
    result = asyncio.run(BootstrapWizard(ui, config_path=path).run())
  except KeyboardInterrupt:
    abort("Aborted. No configuration written.\n", 0)

  if result != BootstrapResult.WRITTEN:
    # Manual setup or abort: no file was written. Exit cleanly.
    sys.exit(0)


def _confirm_overwrite(path: Path) -> bool:
  """Ask the user to confirm overwriting ``path``. Returns True on yes."""
  sys.stdout.write(f"Overwrite existing {path}? [y/N] ")
  sys.stdout.flush()
  try:
    answer = sys.stdin.readline().strip().lower()
  except (EOFError, KeyboardInterrupt):
    return False
  return answer in ("y", "yes")


__all__ = ["run_init"]
