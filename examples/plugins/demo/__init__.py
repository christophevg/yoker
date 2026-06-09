"""Demo plugin for Yoker plugin system validation.

This plugin demonstrates the plugin infrastructure by providing:
  - EchoTool: A simple tool that echoes input messages
  - greeting skill: A skill for friendly greetings
  - demo agent: A demonstration agent definition

Usage:
    # Run yoker with demo plugin
    yoker --with demo

    # The agent can now use:
    # - demo:echo tool
    # - demo:greeting skill (via /greeting)
"""

from typing import Any

from yoker.plugins import PluginManifest

# Import tool for manifest
from yoker.tools import Tool

# Create a simple EchoTool inline for the manifest
class _EchoTool(Tool):
  """Simple echo tool that returns its input with a prefix."""

  @property
  def name(self) -> str:
    return "echo"

  @property
  def description(self) -> str:
    return "Echo back the input message with a prefix"

  def get_schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "message": {
              "type": "string",
              "description": "The message to echo back",
            }
          },
          "required": ["message"],
        },
      },
    }

  async def execute(self, **kwargs: Any) -> Any:
    from yoker.tools.base import ToolResult

    message = kwargs.get("message", "")
    if not isinstance(message, str):
      return ToolResult(success=False, result="", error="Message must be a string")
    return ToolResult(success=True, result=f"Echo: {message}")


__YOKER_MANIFEST__ = PluginManifest(
  tools=[_EchoTool()],
  skills_dir="skills",
  agents_dir="agents",
)

__all__ = ["__YOKER_MANIFEST__"]