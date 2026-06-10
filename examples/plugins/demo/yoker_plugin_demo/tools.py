"""Echo tool implementation for demo plugin.

Provides a simple EchoTool that returns its input with a prefix.
"""

from typing import Any

from yoker.tools.base import Tool, ToolResult


class EchoTool(Tool):
  """Simple echo tool that returns its input with a prefix.

  This tool demonstrates the minimal implementation required for a Yoker tool:
    - name property
    - description property
    - get_schema() method
    - async execute() method

  Example:
      >>> tool = EchoTool()
      >>> result = await tool.execute(message="Hello")
      >>> print(result.result)
      "Echo: Hello"
  """

  @property
  def name(self) -> str:
    """Tool name used for registration and LLM tool calling."""
    return "echo"

  @property
  def description(self) -> str:
    """Tool description shown to the LLM."""
    return "Echo back the input message with a prefix"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible function schema.

    Returns:
      Dict in OpenAI function-calling format.
    """
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

  async def execute(self, **kwargs: Any) -> ToolResult:
    """Execute the echo tool.

    Args:
      **kwargs: Must contain 'message' key with the message to echo.

    Returns:
      ToolResult with the echoed message.
    """
    message = kwargs.get("message", "")

    # Validate message is a string
    if not isinstance(message, str):
      return ToolResult(
        success=False,
        result="",
        error="Message must be a string",
      )

    # Return the echoed message
    return ToolResult(
      success=True,
      result=f"Echo: {message}",
    )