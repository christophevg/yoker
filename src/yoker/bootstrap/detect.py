"""Boolean detection of whether the user has provided Yoker configuration.

Per ``analysis/bootstrap-config-detection.md`` (revised), detection is
intentionally minimal: a single boolean function, :func:`config_provided`,
that returns ``True`` when the user has induced any configuration source and
``False`` otherwise. There is no ``ConfigStatus`` dataclass, no state machine,
and no field-presence check.
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path


def _default_config_paths() -> tuple[Path, Path]:
  """Return ``(user_config_path, project_config_path)`` using Clevis conventions.

  User: ``~/.yoker.toml`` (``Path.home() / ".yoker.toml"``).
  Project: ``./yoker.toml`` (``Path.cwd() / "yoker.toml"``).
  """
  return Path.home() / ".yoker.toml", Path.cwd() / "yoker.toml"


def _yoker_cli_prefixes() -> frozenset[str]:
  """Return the set of CLI flag prefixes generated from the Config dataclass.

  Clevis auto-generates CLI args from dataclass fields. A top-level field
  named ``backend`` produces ``--backend`` and ``--backend-*`` flags. We
  derive the prefixes from the Config fields so the set stays in sync with
  the schema without hardcoding field names here.
  """
  # Imported lazily to avoid an import cycle at module load time.
  from yoker.config import Config

  prefixes: set[str] = set()
  for field_obj in dataclasses.fields(Config):
    dashed = field_obj.name.replace("_", "-")
    prefixes.add(f"--{dashed}")
    prefixes.add(f"--{dashed}-")
  return frozenset(prefixes)


def _cli_overrides_present(cli_args: Sequence[str]) -> bool:
  """Return ``True`` if any yoker-related CLI flag is present in ``cli_args``.

  ``--help`` / ``-h`` and the plugin-only ``--with`` flag are not configuration
  overrides and do not count. Returns ``False`` for an empty or help-only
  argv.
  """
  if not cli_args:
    return False
  prefixes = _yoker_cli_prefixes()
  for arg in cli_args:
    if arg in ("--help", "-h") or arg == "--with" or arg.startswith("--with="):
      continue
    for prefix in prefixes:
      if arg == prefix or arg.startswith(prefix):
        return True
  return False


def config_provided(
  *,
  user_config_path: Path | None = None,
  project_config_path: Path | None = None,
  cli_args: Sequence[str] | None = None,
) -> bool:
  """Return ``True`` if the user has supplied any Yoker configuration.

  "Provided" means the user has induced configuration via at least one of:

  - a user-level ``~/.yoker.toml`` file,
  - a project-level ``./yoker.toml`` file,
  - CLI arguments overriding defaults.

  Returns ``False`` only when none of these are present — i.e. the first-run,
  no-config case that should trigger the bootstrap wizard.

  This function inspects the **file system** (does the TOML file exist?) and
  the **CLI parse** (were any yoker-related flags supplied?), not the loaded
  ``Config`` object. It does not parse file contents, so a malformed file is
  treated as "provided" (the user consciously created it); surfacing parse
  errors is left to the normal config-loading path.

  Args:
    user_config_path: Override the user config path (default ``~/.yoker.toml``).
      Used for testing.
    project_config_path: Override the project config path (default
      ``./yoker.toml``). Used for testing.
    cli_args: Override the CLI argument list (default ``sys.argv[1:]``).
      Used for testing.

  Returns:
    ``True`` if any user-induced configuration source is present; ``False``
    otherwise.
  """
  default_user, default_project = _default_config_paths()
  user_path = user_config_path if user_config_path is not None else default_user
  project_path = project_config_path if project_config_path is not None else default_project
  user_path = Path(user_path).expanduser()
  project_path = Path(project_path).expanduser()

  if user_path.exists() or project_path.exists():
    return True

  args = sys.argv[1:] if cli_args is None else cli_args
  return _cli_overrides_present(args)
