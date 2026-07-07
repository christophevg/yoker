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

import copy
import dataclasses
import os
from pathlib import Path
from typing import Any

from yoker.config import KNOWN_PROVIDERS, Config


def _set_dotted(config: Any, dotted: str, value: Any) -> Any:
  """Set ``dotted`` path on ``config`` to ``value`` in place.

  Walks the dataclass tree via attribute access and sets the leaf via
  ``setattr``. ``dotted`` uses dots as section separators, e.g.
  ``"backend.ollama.model"``.
  """
  parts = dotted.split(".")
  obj = config
  for part in parts[:-1]:
    obj = getattr(obj, part)
  setattr(obj, parts[-1], value)
  return config


def _apply_backend_provider_overrides(
  config: Config,
  overrides: dict[str, Any],
) -> tuple[Config, set[str]]:
  """Apply backend.provider override together with provider config.

  When setting ``backend.provider`` to a known provider, we must also set the
  corresponding ``backend.<provider>`` config in the same operation to avoid
  validation errors in BackendConfig.__post_init__.

  This function extracts backend-related overrides and applies them atomically.

  Returns:
    A tuple of (modified config, set of applied override keys).
  """
  # Check if we're setting backend.provider
  applied_keys: set[str] = set()

  if "backend.provider" not in overrides:
    return config, applied_keys

  provider = overrides["backend.provider"]
  applied_keys.add("backend.provider")

  provider_config_key = f"backend.{provider}"

  # Unknown providers (handled by litellm) need no config initialization.
  if provider not in KNOWN_PROVIDERS:
    return config, applied_keys

  # Track that we're applying the provider config key
  if provider_config_key in overrides:
    applied_keys.add(provider_config_key)

  # Apply provider + provider config together, then validate the cross-field
  # invariant (known provider ⇒ corresponding config set).
  config.backend.provider = provider
  if provider_config_key in overrides:
    setattr(config.backend, provider, overrides[provider_config_key])
  config.backend.validate()

  return config, applied_keys


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
    # Escape special characters for TOML basic strings
    # TOML spec: https://toml.io/en/v1.0.0#string
    # Must escape: \ " (and control characters below U+0020)
    # We also escape newlines and tabs for readability
    escaped = (
      value.replace("\\", "\\\\")
      .replace('"', '\\"')
      .replace("\n", "\\n")
      .replace("\t", "\\t")
      .replace("\r", "\\r")
    )
    # Escape control characters (ASCII 0x00-0x1F except for already handled \n, \t, \r)
    # and U+007F (DEL)
    result_chars = []
    for char in escaped:
      code = ord(char)
      if code < 0x20 or code == 0x7F:
        # Escape as \uXXXX
        result_chars.append(f"\\u{code:04x}")
      else:
        result_chars.append(char)
    escaped = "".join(result_chars)
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
  escaped = (
    str(value)
    .replace("\\", "\\\\")
    .replace('"', '\\"')
    .replace("\n", "\\n")
    .replace("\t", "\\t")
    .replace("\r", "\\r")
  )
  result_chars = []
  for char in escaped:
    code = ord(char)
    if code < 0x20 or code == 0x7F:
      result_chars.append(f"\\u{code:04x}")
    else:
      result_chars.append(char)
  escaped = "".join(result_chars)
  return f'"{escaped}"'


def _is_dataclass_instance(value: Any) -> bool:
  """True when ``value`` is a dataclass instance (i.e. a nested config section)."""
  return dataclasses.is_dataclass(value) and not isinstance(value, type)


def _render_section(
  obj: Any,
  prefix: str,
  lines: list[str],
  *,
  is_root: bool,
  _emitted_header: list[bool] | None = None,
) -> None:
  """Render a dataclass section into ``lines``.

  Root sections emit no table header; nested sections emit ``[prefix]``.
  Scalars are emitted before sub-tables (TOML ordering rule), each with an
  inline ``# help`` comment when the field carries a ``help`` annotation.

  A blank line is inserted before each table header except the first one, so
  rendered TOML has whitespace between sections/tables (see MBI-002 PR #34
  feedback). The ``_emitted_header`` flag tracks whether any header has been
  emitted yet across the recursive walk.
  """
  if _emitted_header is None:
    _emitted_header = [False]
  if not is_root:
    # Whitespace between sections/tables: blank line before every header
    # except the very first one in the document.
    if _emitted_header[0]:
      lines.append("")
    lines.append(f"[{prefix}]")
    _emitted_header[0] = True

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
    _render_section(child, child_prefix, lines, is_root=False, _emitted_header=_emitted_header)


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
  # Deep-copy so override application via _set_dotted does not mutate the
  # caller's Config. The no-override path also copies for a stable contract;
  # callers can rely on their input never being modified by rendering.
  rendered = copy.deepcopy(config)
  if overrides:
    # Apply backend.provider and backend.<provider> together atomically
    # to avoid validation errors in BackendConfig.__post_init__
    rendered, applied_keys = _apply_backend_provider_overrides(rendered, overrides)

    # Apply remaining overrides (excluding the ones already applied)
    for dotted, value in overrides.items():
      if dotted not in applied_keys:
        rendered = _set_dotted(rendered, dotted, value)

  lines: list[str] = []
  _render_section(rendered, "", lines, is_root=True, _emitted_header=[False])
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

  This is a **full replace**, not a merge: any existing file at ``path`` is
  overwritten with the rendered config plus ``overrides``. Callers that need
  to preserve existing keys must load-merge-render themselves. The bootstrap
  wizard relies on this clobber behavior because it only runs when no config
  file exists.

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
