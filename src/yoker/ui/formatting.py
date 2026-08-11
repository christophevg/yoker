"""Tool output formatting helpers shared across UI handlers.

Provides unified argument rendering and content preview (middle-collapse)
truncation.  Both :class:`yoker.ui.interactive.InteractiveUIHandler` and
:class:`yoker.ui.batch.BatchUIHandler` delegate to these helpers so that
tool-call argument display and tool-content preview are consistent.

The formatting parameters come from :class:`yoker.config.ContentDisplayConfig`
(extended with new fields for argument rendering and preview head/tail
lines).  When no config is available, module-level defaults are used.
"""

from __future__ import annotations

import json
from typing import Any

from yoker.config import ContentDisplayConfig

# Module-level fallback defaults (used when no ContentDisplayConfig is passed).
_DEFAULTS = ContentDisplayConfig()


def format_tool_args(
  tool_name: str,
  args: dict[str, Any],
  config: ContentDisplayConfig | None = None,
) -> str:
  """Format tool arguments for display.

  Produces either an inline ``key=value`` string (when the argument set is
  small and all values are short scalars) or a multi-line indented JSON-like
  block (when there are many keys or long/multi-line string values).

  Long string values are rendered as ``"head...tail" (N chars)`` where
  ``head`` and ``tail`` are taken from ``config.arg_preview_head`` and
  ``config.arg_preview_tail``.

  For ``write``/``update`` tools, ``content``/``old_string``/``new_string``
  are rendered as previews rather than fully suppressed — the diff/content
  is still shown separately via ``output_tool_content``, but a short preview
  in the call line gives immediate context.

  Args:
    tool_name: Name of the tool (used for special-case formatting).
    args: Tool arguments dictionary.
    config: Optional display config. Falls back to defaults when None.

  Returns:
    Formatted string for display.
  """
  cfg = config if config is not None else _DEFAULTS

  # Special-case: git tool — show operation, path, args compactly.
  if tool_name == "git":
    return _format_git_args(args, cfg)

  # Special-case: websearch — show the query prominently.
  if tool_name == "websearch":
    query = args.get("query", "")
    if query:
      return _format_scalar("query", str(query), cfg)
    return _format_inline(args, cfg)

  # Decide inline vs. multi-line.
  if _should_inline(args, cfg):
    return _format_inline(args, cfg)
  return _format_multiline(args, cfg)


def truncate_content_preview(
  content: str,
  max_lines: int,
  head_lines: int,
  tail_lines: int,
) -> tuple[str, bool, int]:
  """Truncate content using middle-collapse: show head + tail, skip middle.

  When the content has fewer lines than ``max_lines``, it is returned
  unchanged.  Otherwise the first ``head_lines`` and last ``tail_lines``
  are kept, with a ``... N lines hidden (start–end) ...`` marker between
  them.

  Args:
    content: Full content string.
    max_lines: Maximum lines before truncation kicks in.
    head_lines: Lines to show from the top when truncating.
    tail_lines: Lines to show from the bottom when truncating.

  Returns:
    Tuple of (truncated_content, was_truncated, total_line_count).
  """
  lines = content.splitlines(keepends=True)
  total = len(lines)

  if total <= max_lines:
    return content, False, total

  head = lines[:head_lines]
  tail = lines[total - tail_lines :]

  # Ensure head lines end with newline for clean joining.
  head = [line if line.endswith("\n") else line + "\n" for line in head]
  tail = [line if line.endswith("\n") else line + "\n" for line in tail]

  hidden_start = head_lines + 1
  hidden_end = total - tail_lines
  hidden_count = hidden_end - hidden_start

  marker = f"... {hidden_count} lines hidden ({hidden_start}\u2013{hidden_end}) ...\n"

  return "".join(head) + marker + "".join(tail), True, total


# === Internal helpers ===


def _should_inline(args: dict[str, Any], cfg: ContentDisplayConfig) -> bool:
  """Decide whether arguments can be rendered inline.

  Inline when: few keys AND all values are short scalars (no newlines,
  not longer than ``max_arg_inline_chars``) AND the combined inline
  representation fits within ``max_inline_args_width``.
  """
  if len(args) > cfg.multiline_arg_threshold:
    return False
  # Estimate the total inline width: sum of key=value pairs with separators.
  total_width = 0
  for k, v in args.items():
    if isinstance(v, str):
      if "\n" in v or len(v) > cfg.max_arg_inline_chars:
        return False
      total_width += len(k) + 2 + len(v) + 2  # key="value",
    elif isinstance(v, (dict, list)):
      return False
    else:
      s = str(v)
      if len(s) > cfg.max_arg_inline_chars:
        return False
      total_width += len(k) + 1 + len(s) + 2  # key=value,
  if total_width > cfg.max_inline_args_width:
    return False
  return True


def _format_inline(args: dict[str, Any], cfg: ContentDisplayConfig) -> str:
  """Format arguments as a single inline ``key=value`` string."""
  parts = []
  for k, v in args.items():
    parts.append(k + "=" + _format_value(v, cfg))
  return ", ".join(parts)


def _format_multiline(args: dict[str, Any], cfg: ContentDisplayConfig) -> str:
  """Format arguments as a multi-line indented block.

  Output looks like::

      key: value,
      key: "preview..." (N chars)

  The outer braces are omitted -- the ``(`` and ``)`` from the tool
  call line already delimit the block.
  """
  lines: list[str] = []
  for k, v in args.items():
    formatted = _format_value(v, cfg)
    lines.append(f"{k}: {formatted},")
  return "\n".join(lines)


def _format_value(value: Any, cfg: ContentDisplayConfig) -> str:
  """Format a single argument value for display.

  - Strings shorter than the threshold are shown raw (quoted).
  - Long or multi-line strings show a head/tail preview with char count.
  - Dicts and lists are rendered recursively (with the same preview logic
    applied to nested strings).
  - Other types are str()'d.
  """
  if isinstance(value, str):
    return _format_string(value, cfg)
  if isinstance(value, dict):
    return _format_dict(value, cfg)
  if isinstance(value, list):
    return _format_list(value, cfg)
  return _format_scalar(None, str(value), cfg)


def _format_string(s: str, cfg: ContentDisplayConfig) -> str:
  """Format a string value: raw if short, preview if long or multi-line."""
  if "\n" not in s and len(s) <= cfg.max_arg_inline_chars:
    return f'"{s}"'
  return _format_string_preview(s, cfg)


def _format_string_preview(s: str, cfg: ContentDisplayConfig) -> str:
  """Render a long string as ``"head...tail" (N chars)``."""
  total = len(s)
  head = s[: cfg.arg_preview_head]
  tail = s[total - cfg.arg_preview_tail :] if total > cfg.arg_preview_tail else ""
  # Collapse newlines in the preview fragments for inline display.
  head = head.replace("\n", "\\n")
  tail = tail.replace("\n", "\\n")
  return f'"{head}...{tail}" ({total} chars)'


def _format_dict(d: dict[str, Any], cfg: ContentDisplayConfig) -> str:
  """Format a dict value (recursive, inline for small dicts)."""
  if not d:
    return "{}"
  if len(d) <= cfg.multiline_arg_threshold and all(
    not isinstance(v, (dict, list)) for v in d.values()
  ):
    parts = []
    for k, v in d.items():
      parts.append(f"{k}: {_format_value(v, cfg)}")
    return "{" + ", ".join(parts) + "}"
  # Larger dict: JSON-ish multiline (but kept inline for arg display)
  try:
    return json.dumps(d, default=str, ensure_ascii=False)[: cfg.max_arg_inline_chars * 2]
  except (TypeError, ValueError):
    return str(d)[: cfg.max_arg_inline_chars * 2]


def _format_list(lst: list[Any], cfg: ContentDisplayConfig) -> str:
  """Format a list value (recursive)."""
  if not lst:
    return "[]"
  if len(lst) <= cfg.multiline_arg_threshold and all(not isinstance(v, (dict, list)) for v in lst):
    parts = [_format_value(v, cfg) for v in lst]
    return "[" + ", ".join(parts) + "]"
  return f"[{len(lst)} items]"


def _format_scalar(_key: str | None, s: str, cfg: ContentDisplayConfig) -> str:
  """Format a scalar string for inline display."""
  if "\n" in s or len(s) > cfg.max_arg_inline_chars:
    return _format_string_preview(s, cfg)
  return s


def _format_git_args(args: dict[str, Any], cfg: ContentDisplayConfig) -> str:
  """Special-case formatting for the git tool."""
  operation = args.get("operation", "")
  path = args.get("path", "")
  sub_args = args.get("args", {})

  parts = [str(operation)] if operation else []
  if path:
    parts.append(f"on {path}")
  if isinstance(sub_args, dict) and sub_args:
    items = list(sub_args.items())[:3]
    args_str = ", ".join(f"{k}={v}" for k, v in items)
    if len(sub_args) > 3:
      args_str += ", ..."
    parts.append(f"({args_str})")

  return " ".join(parts) if parts else _format_inline(args, cfg)


__all__ = [
  "format_tool_args",
  "truncate_content_preview",
]
