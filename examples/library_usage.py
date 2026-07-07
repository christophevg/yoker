"""Library usage example for Yoker.

This example shows how to embed Yoker in your own application without
using the CLI. It loads configuration programmatically, creates an
Agent, and processes a single message.

Run with:
    python examples/library_usage.py

Note: This example requires a running Ollama instance unless you swap
out the backend client in your own code.
"""

import asyncio

from yoker import Agent, __version__
from yoker.config import get_yoker_config
from yoker.events import Event, SessionEvent
from yoker.exceptions import NetworkError


def log_events(event: Event | SessionEvent) -> None:
  """Simple event handler that prints every event type.

  Args:
    event: Event emitted by the Agent (or a SessionEvent envelope when
      used inside a Session — MBI-007).
  """
  if isinstance(event, SessionEvent):
    print(f"[event] {event.event.type.name} (from {event.agent_id})")
  else:
    print(f"[event] {event.type.name}")


async def main() -> None:
  """Entry point for the library usage example."""
  # Load configuration from environment variables, ~/.yoker.toml,
  # ./yoker.toml, and built-in defaults (in that priority order).
  config = get_yoker_config(cli=False)

  # Create the agent. All heavy lifting (context, tools, guardrails) is
  # configured from the Config object.
  agent = Agent(config=config)

  print(f"Yoker v{__version__}")
  print(f"Model: {agent.model}")
  print(f"Thinking mode: {agent.thinking_mode.value}")
  print(f"Tools: {', '.join(sorted(agent.tools.names))}")

  # Register a custom event handler to observe the agent's activity.
  agent.on_event(log_events)

  # Process a single message. This will contact the configured backend.
  try:
    response = await agent.process("Hello, how can you help me?")
    print(f"\nResponse: {response}")
  except NetworkError as e:
    print(f"\nNote: This example requires a running Ollama instance.\nNetwork error: {e}")


if __name__ == "__main__":
  asyncio.run(main())
