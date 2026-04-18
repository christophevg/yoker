"""Minimal Agent implementation for Yoker prototype."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ollama import Client
from rich.console import Console

from yoker.config import Config
from yoker.tools import AVAILABLE_TOOLS

logger = logging.getLogger(__name__)

# Default system prompt
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

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
  ) -> None:
    """Initialize the agent.

    Args:
      model: Model to use (overrides config if provided).
      config: Configuration object (takes precedence over config_path).
      config_path: Path to configuration file (loaded if config not provided).
      console: Rich console for output (default console if not provided).
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

    # Initialize conversation history
    self.messages: list[dict[str, Any]] = [
      {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
    ]

  def process(self, message: str) -> str:
    """Process a single message and return the response.

    Handles tool calls internally until a final response is ready.

    Args:
      message: User message to process.

    Returns:
      Assistant's response text.
    """
    self.messages.append({"role": "user", "content": message})

    # Process with model, handling tool calls in a loop
    while True:
      response = self.client.chat(
        model=self.model,
        messages=self.messages,
        tools=list(self.tools.values()),
      )

      # Extract response content
      content = response.message.content or ""
      tool_calls = response.message.tool_calls or []

      # If no tool calls, we're done with this turn
      if not tool_calls:
        # Add assistant message to history
        self.messages.append({"role": "assistant", "content": content})
        return content

      # Add assistant message with tool calls to history
      self.messages.append({
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
      })

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
        self.messages.append({
          "role": "tool",
          "name": tool_name,
          "content": str(result),
        })

  def start(self, get_input: Callable[[str], str] | None = None) -> None:
    """Start the interactive chat loop.

    Args:
      get_input: Optional function to get user input. Defaults to built-in
        input() which works with readline for arrow keys and history.
    """
    if get_input is None:
      get_input = default_prompt

    self.console.print(f"Yoker v0.1.0 - Using model: {self.model}")
    self.console.print("Type your message and press Enter. Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")

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

      response = self.process(user_input)
      if response:
        self.console.print(f"\n{response}\n")
