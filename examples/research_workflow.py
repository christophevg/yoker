"""Research workflow example for Yoker.

This example demonstrates how to use Yoker as a library to run a
research-oriented agent. It loads the built-in researcher agent
definition, processes a research prompt, and prints the response.

Run with:
    python examples/research_workflow.py "What are the latest features in Python 3.12?"

The example requires a running Ollama instance. If Ollama is not
available, a NetworkError is reported without crashing.
"""

import asyncio
import sys

from yoker.agent import Agent
from yoker.config import get_yoker_config
from yoker.exceptions import NetworkError
from yoker.ui import BatchUIHandler, UIBridge


async def run_research(prompt: str) -> None:
  """Run a single research prompt through the researcher agent.

  Args:
    prompt: Research question or task for the agent.
  """
  config = get_yoker_config(cli=False)

  agent = Agent(
    config=config,
    agent_path="examples/agents/researcher.md",
  )

  ui = BatchUIHandler(
    show_thinking=True,
    show_tool_calls=True,
    show_stats=True,
  )
  bridge = UIBridge(ui)
  agent.add_event_handler(bridge)

  await ui.start(agent)

  try:
    _ = await agent.process(prompt)
  except NetworkError as e:
    ui.output_error(e)
  finally:
    await ui.shutdown("complete")


def main() -> None:
  """Entry point for the research workflow example."""
  prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Summarize the README.md file."
  try:
    asyncio.run(run_research(prompt))
  except KeyboardInterrupt:
    sys.exit(130)


if __name__ == "__main__":
  main()
