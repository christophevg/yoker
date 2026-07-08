"""``yoker config`` subcommand handler — display the effective configuration.

Loads the merged config (user TOML + project TOML + CLI args) and prints it as
TOML (default) or JSON (``--json``). The ``--show-path`` flag also prints the
config file path(s). API keys are masked by default; ``--reveal`` shows them
in full.

Security:
  - ``api_key`` values are masked (``***`` or last-4) unless ``--reveal`` is
    passed, preventing accidental secret exposure in terminal output or logs.
"""

import copy
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from clevis import SecurityError

from yoker.cli.commands import ConfigCmdConfig
from yoker.cli.shared import abort, load_subcommand_config
from yoker.config import Config
from yoker.config.writer import render_config_toml

# Provider config attributes that carry an ``api_key`` field.
_PROVIDER_CONFIGS = ("ollama", "openai", "anthropic", "gemini", "generic")


def run_config_cmd() -> None:
  """Run the ``yoker config`` subcommand.

  Loads :class:`ConfigCmdConfig` via Clevis (which extends :class:`Config` with
  ``json``, ``show_path``, ``reveal`` display flags), masks API keys unless
  ``--reveal`` is set, and prints the config as TOML or JSON.
  """
  try:
    config = load_subcommand_config(ConfigCmdConfig)
  except (ValueError, SecurityError) as e:
    abort(f"Error: {e}\n", 1)

  if config.show_path:
    _print_config_paths()

  display = _mask_api_keys(config) if not config.reveal else config
  # Drop the ConfigCmdConfig display flags (json, show_path, reveal) from the
  # rendered output by projecting to a base Config — those are CLI-only switches,
  # not persistent configuration fields.
  base = _to_base_config(display)

  if config.json:
    output = _render_json(base)
  else:
    output = render_config_toml(base)

  sys.stdout.write(output)


def _to_base_config(config: ConfigCmdConfig) -> Config:
  """Project a ConfigCmdConfig down to a base Config for rendering.

  Drops the display-only fields (``json``, ``show_path``, ``reveal``) so they
  don't appear in TOML/JSON output. Nested dataclass sections are shared by
  reference (safe — we don't mutate after this point).
  """
  config_fields = {f.name for f in dataclasses.fields(Config)}
  kwargs = {name: getattr(config, name) for name in config_fields}
  return Config(**kwargs)


def _print_config_paths() -> None:
  """Print the config file paths that were found on disk."""
  user_config = Path.home() / ".yoker.toml"
  project_config = Path.cwd() / "yoker.toml"
  found = False
  for label, path in (("user", user_config), ("project", project_config)):
    if path.exists():
      sys.stdout.write(f"{label}: {path}\n")
      found = True
  if not found:
    sys.stdout.write("No config files found (using defaults + CLI args).\n")


def _mask_api_keys(config: ConfigCmdConfig) -> ConfigCmdConfig:
  """Return a deep copy of ``config`` with all ``api_key`` values masked.

  Masks as ``***`` when the key is set, leaving ``None`` values as ``None``
  (so they are omitted from TOML output by the writer). The original config
  is not mutated.
  """
  masked = copy.deepcopy(config)
  backend = masked.backend
  for provider_name in _PROVIDER_CONFIGS:
    provider_config = getattr(backend, provider_name, None)
    if provider_config is not None and hasattr(provider_config, "api_key"):
      if provider_config.api_key is not None:
        provider_config.api_key = _mask_value(provider_config.api_key)
  return masked


def _mask_value(value: str) -> str:
  """Mask a secret string, showing only the last 4 characters."""
  if len(value) <= 4:
    return "***"
  return f"***...{value[-4:]}"


def _render_json(config: Config) -> str:
  """Render ``config`` as a JSON string with 2-space indentation."""
  return json.dumps(_dataclass_to_dict(config), indent=2, default=str) + "\n"


def _dataclass_to_dict(obj: Any) -> Any:
  """Convert a dataclass tree to a dict/list/scalar, omitting ``None`` values.

  Tuples are converted to lists (JSON has no tuple type). ``None`` values are
  omitted to keep output concise, matching the TOML writer's behavior.
  """
  if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
    result: dict[str, Any] = {}
    for field_obj in dataclasses.fields(obj):
      value = getattr(obj, field_obj.name)
      converted = _dataclass_to_dict(value)
      if converted is None:
        continue
      if isinstance(converted, dict) and not converted:
        continue
      result[field_obj.name] = converted
    return result
  if isinstance(obj, (tuple, list)):
    items = [_dataclass_to_dict(item) for item in obj]
    items = [item for item in items if item is not None]
    return items
  if isinstance(obj, dict):
    return {k: _dataclass_to_dict(v) for k, v in obj.items() if v is not None}
  return obj


__all__ = ["run_config_cmd"]
