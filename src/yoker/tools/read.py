"""Read tool implementation for Yoker.

Provides the ReadTool for reading file contents with basic error handling.
This is the concrete implementation of the read functionality that was
previously in src/yoker/tools.py.
"""

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ReadTool(Tool):
  """Tool for reading file contents.

  Reads the entire contents of a file as text. Returns error messages
  for common failure cases (file not found, permission denied).
  """

  @property
  def name(self) -> str:
    return "read"

  @property
  def description(self) -> str:
    return "Read the contents of a file"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the read tool.

    Returns:
      Dict with 'type': 'function' and function metadata.
    """
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Path to the file to read",
            }
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Read a file and return its contents.

    Args:
      **kwargs: Must contain 'path' key with file path.

    Returns:
      ToolResult with file content or error message.
    """
    path_str = kwargs.get("path", "")
    try:
      content = Path(path_str).read_text()
      return ToolResult(success=True, result=content)
    except FileNotFoundError:
      return ToolResult(
        success=False,
        result="",
        error=f"File not found: {path_str}",
      )
    except PermissionError:
      return ToolResult(
        success=False,
        result="",
        error=f"Permission denied: {path_str}",
      )
    except Exception as e:
      return ToolResult(
        success=False,
        result="",
        error=f"Error reading file: {e}",
      )
