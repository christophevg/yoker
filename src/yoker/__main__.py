"""Entry point for running Yoker as a module.

Usage: python -m yoker
"""

import logging

from rich.logging import RichHandler

from yoker import __version__
from yoker.agent import Agent

# Configure logging
logging.basicConfig(
  level=logging.INFO,
  format="%(name)s - %(message)s",
  datefmt="[%X]",
  handlers=[RichHandler()],
)

# Silence noisy modules
for module in ["httpx", "httpcore", "ollama"]:
  logging.getLogger(module).setLevel(logging.WARNING)


def main() -> None:
  """Run the interactive agent."""
  print(f"Yoker v{__version__}")
  print("=" * 40)
  Agent().start()


if __name__ == "__main__":
  main()