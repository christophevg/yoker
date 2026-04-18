"""Minimal Agent implementation for Yoker prototype."""

import logging
from pathlib import Path
from typing import Any

from ollama import Client

from yoker.config import Config
from yoker.tools import AVAILABLE_TOOLS

logger = logging.getLogger(__name__)


class Agent:
  """Minimal agent that chats with Ollama and uses tools.

  Attributes:
    client: Ollama client for API communication.
    model: Model to use for chat.
    config: Configuration object (or defaults if not provided).
  """

  def __init__(
    self,
    model: str | None = None,
    config: Config | None = None,
    config_path: Path | str | None = None,
  ) -> None:
    """Initialize the agent.

    Args:
      model: Model to use (overrides config if provided).
      config: Configuration object (takes precedence over config_path).
      config_path: Path to configuration file (loaded if config not provided).
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

  def start(self) -> None:
    """Start the interactive chat loop."""
    messages: list[dict[str, Any]] = [
      {"role": "system", "content": "You are a helpful assistant."},
    ]

    print(f"Yoker v0.1.0 - Using model: {self.model}")
    print("Type your message and press Enter. Press Ctrl+D (or Ctrl+Z on Windows) to quit.\n")

    while True:
      try:
        user_input = input("> ")
      except EOFError:
        print("\nGoodbye!")
        break

      if not user_input.strip():
        continue

      messages.append({"role": "user", "content": user_input})

      # Process with model, handling tool calls in a loop
      while True:
        response = self.client.chat(
          model=self.model,
          messages=messages,
          tools=list(self.tools.values()),
        )

        # Extract response content
        content = response.message.content or ""
        tool_calls = response.message.tool_calls or []

        # Show assistant response
        if content:
          print(f"\n{content}\n")

        # If no tool calls, we're done with this turn
        if not tool_calls:
          break

        # Add assistant message to history
        messages.append({
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
          messages.append({
            "role": "tool",
            "name": tool_name,
            "content": str(result),
          })
