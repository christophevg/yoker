"""Shared helpers for CLI subcommands.

Centralizes config loading and the dev/test security bypass so each subcommand
handler can load its config class with a single call, consistent with the
existing :func:`yoker.config.get_yoker_config` security policy.
"""

import os
import sys
from typing import TypeVar

from clevis import SecurityAction, SecurityConfig, get_config

T = TypeVar("T")


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


def abort(msg: str, code: int) -> None:
  """Write ``msg`` to stderr and exit with ``code``.

  Shared by :mod:`yoker.__main__` (plugin arg parsing) and subcommand handlers
  (chat, init, config) for consistent error-exit behaviour.
  """
  sys.stderr.write(msg)
  sys.exit(code)


__all__ = ["abort", "get_security_config", "load_subcommand_config"]
