"""Configuration TOML writer for Yoker.

Renders Config dataclasses to TOML format with support for tagged unions
(BackendConfig with provider-specific sub-configs).
"""

from dataclasses import fields, is_dataclass
from typing import Any


def render_config_toml(config: Any, overrides: dict[str, Any] | None = None) -> str:
  """Render a Config dataclass to TOML format.

  This function converts a Config dataclass to a TOML string. It handles
  the tagged-union structure of BackendConfig by omitting None sub-configs.

  Args:
    config: A Config dataclass instance to render.
    overrides: Optional dictionary of field overrides (reserved for future use).

  Returns:
    TOML string representation of the config.

  Example:
      >>> from yoker.config import Config, BackendConfig
      >>> config = Config(backend=BackendConfig(provider="ollama"))
      >>> toml_str = render_config_toml(config)
      >>> print(toml_str)
      [harness]
      name = "yoker"
      version = "1.0"

      [backend]
      provider = "ollama"

      [backend.ollama]
      base_url = "http://localhost:11434"
      model = "llama3.2:latest"
      ...
  """
  lines: list[str] = []
  _render_dataclass_section(config, lines, is_root=True)
  return "\n".join(lines)


def _render_dataclass_section(
  obj: Any, lines: list[str], section_path: str = "", is_root: bool = False
) -> None:
  """Render a dataclass as a TOML section.

  Args:
    obj: The dataclass instance to render.
    lines: List of TOML lines to append to.
    section_path: Current section path (e.g., "backend.ollama").
    is_root: Whether this is the root Config dataclass.
  """
  if not is_dataclass(obj):
    return

  # Separate fields into simple values and nested dataclasses
  simple_fields: list[tuple[str, Any]] = []
  nested_dataclasses: list[tuple[str, Any]] = []
  nested_dicts: list[tuple[str, Any]] = []

  for field in fields(obj):
    value = getattr(obj, field.name)

    # Skip None values (including None sub-configs for tagged unions)
    if value is None:
      continue

    if is_dataclass(value):
      nested_dataclasses.append((field.name, value))
    elif isinstance(value, dict) and len(value) > 0:
      nested_dicts.append((field.name, value))
    elif isinstance(value, (list, tuple)) and len(value) > 0:
      # Lists/tuples are simple fields rendered inline
      simple_fields.append((field.name, value))
    elif not isinstance(value, (list, tuple, dict)):
      # Simple scalar value
      simple_fields.append((field.name, value))

  # Write section header (if not root and has content)
  if not is_root and (simple_fields or nested_dataclasses or nested_dicts):
    lines.append(f"\n[{section_path}]")

  # Write simple fields
  for field_name, value in simple_fields:
    formatted_value = _format_value(value)
    lines.append(f"{field_name} = {formatted_value}")

  # Write nested dicts as inline tables or subsections
  for field_name, dict_value in nested_dicts:
    dict_path = f"{section_path}.{field_name}" if section_path else field_name
    lines.append(f"\n[{dict_path}]")
    for key, val in dict_value.items():
      formatted_value = _format_value(val)
      lines.append(f"{key} = {formatted_value}")

  # Recursively render nested dataclasses
  for field_name, nested_obj in nested_dataclasses:
    nested_path = f"{section_path}.{field_name}" if section_path else field_name
    _render_dataclass_section(nested_obj, lines, section_path=nested_path)


def _format_value(value: Any) -> str:
  """Format a Python value as TOML literal.

  Args:
    value: The value to format.

  Returns:
    TOML-formatted string representation.
  """
  if isinstance(value, bool):
    return "true" if value else "false"
  elif isinstance(value, str):
    # Escape special characters in strings
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
  elif isinstance(value, (int, float)):
    return str(value)
  elif isinstance(value, (list, tuple)):
    # Format as TOML array
    items = [_format_value(item) for item in value]
    return "[" + ", ".join(items) + "]"
  else:
    # Fallback: convert to string
    return f'"{str(value)}"'
