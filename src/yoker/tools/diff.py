"""Shared unified-diff helper for filesystem tools and approval flow.

``generate_diff`` produces a unified diff string from two text contents.
It is reused by:

- :mod:`yoker.builtin.update` — content_metadata diff rendering.
- :mod:`yoker.core._processing` — interactive approval-on-diff for writes
  to protected files (MBI-009 T12).

Keeping the helper here avoids a circular ``core`` → ``builtin`` import and
gives both call sites a single, tested code path.
"""

from __future__ import annotations

import difflib

__all__ = ["generate_diff"]


def generate_diff(old_content: str, new_content: str, filename: str) -> str:
  """Return a unified diff string between ``old_content`` and ``new_content``.

  Args:
    old_content: The original file content. May be empty (e.g. for a new-file
      write approval — the diff then shows every line as an addition).
    new_content: The proposed content.
    filename: Label used in the diff header (basename or relative path).

  Returns:
    A unified diff string (possibly empty when contents are identical).
  """
  old_lines = old_content.splitlines(keepends=True)
  new_lines = new_content.splitlines(keepends=True)
  diff_lines = difflib.unified_diff(
    old_lines,
    new_lines,
    fromfile=f"{filename} (before)",
    tofile=f"{filename} (after)",
  )
  return "".join(line if line.endswith("\n") else line + "\n" for line in diff_lines)
