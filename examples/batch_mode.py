"""Batch mode example for Yoker.

This example demonstrates how to use Yoker as a library in batch mode.
It sends a predefined list of messages to the agent and writes response
content to stdout. Diagnostics go to stderr.

Run with:
    python examples/batch_mode.py

Or pipe input from stdin:
    printf "Hello\nWhat is 2+2?\n" | python examples/batch_mode.py
"""

import asyncio
import sys

from yoker.agent import Agent
from yoker.config import get_yoker_config
from yoker.exceptions import NetworkError
from yoker.ui import BatchUIHandler, UIBridge


async def run_batch(messages: list[str] | None = None) -> None:
  """Run a batch session with predefined or stdin input.

  Args:
    messages: Optional predefined messages. When None, input is read from
      stdin one line at a time.
  """
  config = get_yoker_config(cli=False)
  agent = Agent(config=config)

  ui = BatchUIHandler(
    show_thinking=True,
    show_tool_calls=True,
    show_stats=True,
  )
  if messages is not None:
    ui.set_input_messages(messages)

  bridge = UIBridge(ui)
  agent.add_event_handler(bridge)

  await ui.start(agent)

  try:
    while True:
      user_input = await ui.get_input()
      if user_input is None:
        break
      if not user_input.strip():
        continue
      await agent.process(user_input)
  except NetworkError as e:
    ui.output_error(e)
  finally:
    await ui.shutdown("complete")


async def main() -> None:
  """Entry point for the batch mode example."""
  messages = ["Hello, how can you help me?"]
  try:
    await run_batch(messages)
  except KeyboardInterrupt:
    sys.exit(130)


if __name__ == "__main__":
  asyncio.run(main())
