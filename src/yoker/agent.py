"""Minimal Agent implementation for Yoker prototype."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ollama import Client
from rich.console import Console
from rich.style import Style

from yoker.config import Config
from yoker.tools import AVAILABLE_TOOLS

if TYPE_CHECKING:
  from yoker.commands import CommandRegistry

logger = logging.getLogger(__name__)

# Default system prompt
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

# Style for thinking output
THINKING_STYLE = Style(color="bright_black", dim=True)


# Default input prompt function
def default_prompt(prompt: str) -> str:
  """Default input prompt using built-in input().

  This works with readline for arrow keys and history.

  Args:
    prompt: The prompt string to display.

  Returns:
    User input string.
  """
  return input(prompt)


class Agent:
  """Minimal agent that chats with Ollama and uses tools.

  Attributes:
    client: Ollama client for API communication.
    model: Model to use for chat.
    config: Configuration object (or defaults if not provided).
    console: Rich console for output.
    messages: Conversation history.
  """

  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    config_path: Path | str | None = None,
    console: Console | None = None,
    thinking_enabled: bool = True,
    command_registry: "CommandRegistry | None" = None,
    wrap_width: int | None = None,
  ) -> None:
    """Initialize the agent.

    Args:
      model: Model to use (overrides config if provided).
      config: Configuration object (takes precedence over config_path).
      config_path: Path to configuration file (loaded if config not provided).
      console: Rich console for output (default console if not provided).
      thinking_enabled: Whether to enable thinking mode (default: True).
      command_registry: Optional command registry for slash-commands.
      wrap_width: Optional width for wrapping streaming output (default: None = no wrapping).
    """
    # Load configuration
    if config is not None:
      self.config = config
    elif config_path is not None:
      from yoker.config import load_config

      self.config = load_config(config_path)
    else:
      self.config = Config()

    # Initialize client
    self.client = Client(host=self.config.backend.ollama.base_url)

    # Use provided model or config model
    self.model = model if model is not None else self.config.backend.ollama.model

    # Use available tools (TODO: filter by config.tools)
    self.tools = AVAILABLE_TOOLS

    # Use provided console or default
    self.console = console if console is not None else Console()

    # Thinking mode state
    self.thinking_enabled = thinking_enabled

    # Command registry for slash-commands
    self.command_registry = command_registry

    # Wrap width for streaming output
    self.wrap_width = wrap_width

    # Initialize conversation history
    self.messages: list[dict[str, Any]] = [
      {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
    ]

    # Column tracking for wrap_width
    self._column = 0

  def _print_wrapped(self, text: str, style: Style | None = None, end: str = "") -> None:
    """Print text with optional wrapping at wrap_width.

    Args:
      text: Text to print.
      style: Optional Rich style.
      end: String to append at the end (default: "").
    """
    if self.wrap_width is None:
      # No wrapping, use standard print
      self.console.print(text, style=style, end=end)
      return

    # Wrap at width boundary
    for char in text:
      if char == "\n":
        self._column = 0
      elif char == "\r":
        self._column = 0
      elif self._column >= self.wrap_width:
        self.console.print()
        self._column = 0

      self.console.print(char, style=style, end="")
      self._column += 1

    if end:
      self.console.print(end, style=style, end="")

  def process(self, message: str) -> str:
    """Process a single message and return the response.

    Handles tool calls internally until a final response is ready.
    Uses streaming when thinking is enabled.

    Args:
      message: User message to process.

    Returns:
      Assistant's response text.
    """
    self.messages.append({"role": "user", "content": message})

    # Process with model, handling tool calls in a loop
    while True:
      # Use streaming for better UX
      stream = self.client.chat(
        model=self.model,
        messages=self.messages,
        tools=list(self.tools.values()),
        think=self.thinking_enabled,
        stream=True,
      )

      # Accumulate partial fields
      content = ""
      thinking = ""
      tool_calls: list[Any] = []
      in_thinking = False

      for chunk in stream:
        # Handle thinking output
        if chunk.message.thinking:
          if not in_thinking and self.thinking_enabled:
            in_thinking = True
            self._print_wrapped("\n[Thinking]\n", style=THINKING_STYLE)
          thinking += chunk.message.thinking
          if self.thinking_enabled:
            self._print_wrapped(chunk.message.thinking, style=THINKING_STYLE)

        # Handle content output
        if chunk.message.content:
          if in_thinking and self.thinking_enabled:
            in_thinking = False
            self._print_wrapped("\n\n[Response]\n")
          content += chunk.message.content
          self._print_wrapped(chunk.message.content)

        # Handle tool calls
        if chunk.message.tool_calls:
          tool_calls.extend(chunk.message.tool_calls)

      # End output with newline
      if content or thinking:
        self.console.print()  # Final newline

      # Build assistant message for history
      assistant_message: dict[str, Any] = {"role": "assistant"}
      if thinking:
        assistant_message["thinking"] = thinking
      if content:
        assistant_message["content"] = content
      if tool_calls:
        assistant_message["tool_calls"] = tool_calls

      self.messages.append(assistant_message)

      # If no tool calls, we're done with this turn
      if not tool_calls:
        return content

      # Process tool calls
      for call in tool_calls:
        tool_name = call.function.name
        tool_args = call.function.arguments

        logger.info(f"Tool call: {tool_name}({tool_args})")

        try:
          result = self.tools[tool_name](**tool_args)
        except KeyError:
          result = f"Error: Unknown tool '{tool_name}'"
        except Exception as e:
          result = f"Error executing tool: {e}"

        logger.info(f"Tool result: {result[:100]}...")

        # Add tool result to messages
        self.messages.append(
          {
            "role": "tool",
            "name": tool_name,
            "content": str(result),
          }
        )

  def start(self, get_input: Callable[[str], str] | None = None) -> None:
    """Start the interactive chat loop.

    Args:
      get_input: Optional function to get user input. Defaults to built-in
        input() which works with readline for arrow keys and history.
    """
    if get_input is None:
      get_input = default_prompt

    self.console.print(f"Yoker v0.1.0 - Using model: {self.model}")
    thinking_status = "enabled" if self.thinking_enabled else "disabled"
    self.console.print(f"Thinking mode: {thinking_status} (use /think on|off to toggle)")
    self.console.print("Type /help for available commands.")
    self.console.print("Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")

    while True:
      try:
        user_input = get_input("> ")
      except EOFError:
        self.console.print("\nGoodbye!")
        break
      except KeyboardInterrupt:
        self.console.print("\nGoodbye!")
        break

      if not user_input.strip():
        continue

      # Check if this is a command
      if self.command_registry and user_input.startswith("/"):
        result = self.command_registry.dispatch(user_input)
        if result:
          self.console.print(f"{result}\n")
        continue

      # Process message (output is streamed during processing)
      self.process(user_input)
      # Add blank line after response for readability
      self.console.print()
