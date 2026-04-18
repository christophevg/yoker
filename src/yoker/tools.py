"""Minimal tools for Yoker prototype."""

from pathlib import Path


def read(path: str) -> str:
  """Read the content of a file.

  Args:
    path: The path to the file to read.

  Returns:
    The content of the file.
  """
  try:
    return Path(path).read_text()
  except FileNotFoundError:
    return f"Error: File not found: {path}"
  except Exception as e:
    return f"Error reading file: {e}"


# Tool registry - maps tool names to functions
AVAILABLE_TOOLS = {
  "read": read,
}
