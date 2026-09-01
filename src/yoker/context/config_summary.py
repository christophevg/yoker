"""Render a curated, redacted summary of the effective configuration.

The summary is embedded in the agent's environment reminder so agents see
the *effective* (merged) configuration — dataclass defaults -> user TOML ->
project TOML -> manifest -> CLI — without reading source or hitting
surprising tool rejections (e.g. a per-target env-var allowlist from a
user-level config the agent cannot read).

Security model: redaction is structural. The renderer only touches an
explicit allowlist of fields — credential fields (``api_key`` etc.) are
never read, so they cannot leak by omission of a filter rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.config import Config

# Caps to keep the block within context budget (~15 lines typical).
_MAX_OPERATIONS = 8
_MAX_ENV_TARGETS = 4
_MAX_PATHS = 6
_MAX_PLUGINS = 6


def _truncate_list(items: list[str], cap: int) -> tuple[list[str], int]:
  """Cap a rendered list, returning (items, overflow_count)."""
  if len(items) <= cap:
    return items, 0
  return items[:cap], len(items) - cap


def _fmt_list(items: list[str], cap: int) -> str:
  """Format a list with an overflow notice when capped."""
  shown, overflow = _truncate_list(items, cap)
  if overflow:
    return ", ".join(shown) + f", … (+{overflow} more)"
  return ", ".join(shown) if shown else ""


def render_config_summary(config: Config) -> str:
  """Render the curated configuration summary block.

  Returns an empty string when there is nothing to show (config sections
  empty and defaults in place), so the environment reminder stays clean.
  """
  lines: list[str] = []

  # --- Tools: positive allowlists the agent must respect ---
  tools = config.tools

  gh = tools.github
  write_ops = [op for op in gh.allowed_operations if op in _WRITE_OPS]
  read_ops = [op for op in gh.allowed_operations if op not in _WRITE_OPS]
  if write_ops:
    lines.append(
      f"* github allowed_operations: {len(read_ops)} read ops + write ops explicitly granted: [{_fmt_list(write_ops, _MAX_OPERATIONS)}]"
    )
  else:
    lines.append(
      "* github allowed_operations: read-only set (write ops like pr_create, issue_comment NOT enabled)"
    )

  make = tools.make
  if make.allowed_env_vars:
    target_parts = [
      f"{target}: [{', '.join(names)}]"
      for target, names in list(make.allowed_env_vars.items())[:_MAX_ENV_TARGETS]
    ]
    lines.append(f"* make allowed_env_vars: {'; '.join(target_parts)}")
  else:
    lines.append("* make allowed_env_vars: none configured (deny-by-default)")

  git = tools.git
  approval_required = [c for c in git.allowed_commands if c not in git.auto_permission]
  if approval_required:
    lines.append(
      f"* git permissions: auto-approved: [{_fmt_list(list(git.auto_permission), _MAX_OPERATIONS)}]; approval required: [{_fmt_list(approval_required, _MAX_OPERATIONS)}]"
    )
  else:
    lines.append("* git permissions: all configured commands auto-approved")

  # --- Permissions ---
  perms = config.permissions
  lines.append(f"* filesystem_paths: {_fmt_list(list(perms.filesystem_paths), _MAX_PATHS)}")
  lines.append(f"* network_access: {perms.network_access}")
  blocked_count = len(perms.blocked_write_paths)
  if blocked_count:
    lines.append(
      f"* write-protection active: {blocked_count} protected paths (Makefile, pyproject.toml, …)"
    )

  # --- Backend (names only, never credentials) ---
  model = getattr(config.backend.ollama, "model", None)
  lines.append(f"* backend: {config.backend.provider} (model: {model})")

  # --- Plugins ---
  trusted = list(config.plugins.trusted.keys())
  if trusted:
    lines.append(f"* trusted plugins: {_fmt_list(trusted, _MAX_PLUGINS)}")

  if not lines:
    return ""

  body = "\n".join(lines)
  return f"""
# Effective Configuration (snapshot at session start)
{body}
"""


# Write-op set imported lazily to avoid a circular import at module load
# (builtin/github.py imports config). Mirrors _WRITE_OPS there.
def _write_ops() -> frozenset[str]:
  from yoker.builtin.github import _WRITE_OPS

  return _WRITE_OPS


_WRITE_OPS = _write_ops()
