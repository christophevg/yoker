"""Annotation-driven Config writer (MBI-002 task 2.5).

Renders a :class:`~yoker.config.Config` (or any config dataclass) as TOML with
inline comments sourced from each field's ``metadata["help"]`` annotation. The
writer is **generic**: it walks the dataclass tree via :func:`dataclasses.fields`
and never hardcodes field names. Adding a new annotated config field requires
no change here — instrument the config class instead.

The writer is reusable for both the bootstrap wizard and in-session config
augmentation (e.g. "add ``plugins enabled = true`` to your configuration?").

Security:
  - :func:`write_config` sets the file mode to ``0o600`` immediately after
    writing, before any API key is persisted on disk.
  - The writer never logs or echoes field values; it only serializes them.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

from yoker.config import Config


def _set_dotted(config: Any, dotted: str, value: Any) -> Any:
  """Return a copy of ``config`` with ``dotted`` path set to ``value``.

  Works on frozen dataclasses via :func:`dataclasses.replace`, rebuilding each
  ancestor along the path. ``dotted`` uses dots as section separators, e.g.
  ``"backend.ollama.model"``.
  """
  parts = dotted.split(".")

  def _rebuild(obj: Any, idx: int) -> Any:
    if idx == len(parts) - 1:
      return dataclasses.replace(obj, **{parts[idx]: value})
    child = getattr(obj, parts[idx])
    new_child = _rebuild(child, idx + 1)
    return dataclasses.replace(obj, **{parts[idx]: new_child})

  return _rebuild(config, 0)


def _format_scalar(value: Any) -> str | None:
  """Serialize a scalar/collection value as a TOML fragment.

  Returns ``None`` for values that should be omitted from output (``None``
  itself and empty collections), so the caller can skip the line entirely.
  """
  if value is None:
    return None
  if isinstance(value, bool):
    return "true" if value else "false"
  if isinstance(value, str):
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
  if isinstance(value, int):
    return str(value)
  if isinstance(value, float):
    return repr(value)
  if isinstance(value, tuple):
    if not value:
      return None
    return "[" + ", ".join(_format_scalar(v) or "" for v in value) + "]"
  if isinstance(value, dict):
    if not value:
      return None
    items = ", ".join(f"{_format_scalar(k)} = {_format_scalar(v) or ''}" for k, v in value.items())
    return "{" + items + "}"
  # Fallback: stringify defensively.
  escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
  return f'"{escaped}"'


def _is_dataclass_instance(value: Any) -> bool:
  """True when ``value`` is a dataclass instance (i.e. a nested config section)."""
  return dataclasses.is_dataclass(value) and not isinstance(value, type)


def _render_section(obj: Any, prefix: str, lines: list[str], *, is_root: bool) -> None:
  """Render a dataclass section into ``lines``.

  Root sections emit no table header; nested sections emit ``[prefix]``.
  Scalars are emitted before sub-tables (TOML ordering rule), each with an
  inline ``# help`` comment when the field carries a ``help`` annotation.
  """
  if not is_root:
    lines.append(f"[{prefix}]")

  scalar_fields: list[dataclasses.Field[Any]] = []
  section_fields: list[dataclasses.Field[Any]] = []
  for field_obj in dataclasses.fields(obj):
    value = getattr(obj, field_obj.name)
    if _is_dataclass_instance(value):
      section_fields.append(field_obj)
    else:
      scalar_fields.append(field_obj)

  for field_obj in scalar_fields:
    value = getattr(obj, field_obj.name)
    fragment = _format_scalar(value)
    if fragment is None:
      # None defaults and empty collections are omitted from output.
      continue
    help_text = field_obj.metadata.get("help") if field_obj.metadata else None
    line = f"{field_obj.name} = {fragment}"
    if help_text:
      line = f"{line}  # {help_text}"
    lines.append(line)

  for field_obj in section_fields:
    child = getattr(obj, field_obj.name)
    child_prefix = field_obj.name if is_root else f"{prefix}.{field_obj.name}"
    _render_section(child, child_prefix, lines, is_root=False)


def render_config_toml(config: Config, overrides: dict[str, Any] | None = None) -> str:
  """Render ``config`` as TOML with inline help comments.

  Args:
    config: The configuration to render. Typically ``Config()`` for the full
      default config.
    overrides: Optional mapping of dotted-path -> value applied to ``config``
      before rendering (e.g. ``{"backend.ollama.model": "x"}``). Only the
      paths listed are overridden; all other fields keep their ``config``
      values.

  Returns:
    A TOML string with inline ``# help`` comments sourced from each field's
    ``metadata["help"]`` annotation. ``None`` values and empty collections are
    omitted. The string always ends with a newline.
  """
  rendered = config
  if overrides:
    for dotted, value in overrides.items():
      rendered = _set_dotted(rendered, dotted, value)
  lines: list[str] = []
  _render_section(rendered, "", lines, is_root=True)
  return "\n".join(lines) + "\n"


def write_config(
  config: Config,
  path: Path,
  overrides: dict[str, Any] | None = None,
) -> None:
  """Render ``config`` and write it to ``path`` with mode ``0o600``.

  The file is written and then its permissions are set to ``0o600`` so that an
  API key (if present via ``overrides``) is only readable by the owner. The
  writer does not log or echo any field values.

  Args:
    config: The configuration to render.
    path: Destination file path. Parent directories are not created here; the
      caller ensures the directory exists (e.g. ``~`` always exists).
    overrides: Optional dotted-path overrides applied before rendering.
  """
  toml_text = render_config_toml(config, overrides=overrides)
  # Write with restrictive permissions: open with O_CREAT and mode 0o600.
  flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
  fd = os.open(str(path), flags, 0o600)
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
      handle.write(toml_text)
  finally:
    # Ensure the file mode is 0o600 even if it pre-existed with looser bits.
    os.chmod(str(path), 0o600)


__all__ = ["render_config_toml", "write_config"]
