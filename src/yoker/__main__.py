"""Entry point for running Yoker as a module.

Usage: python -m yoker [OPTIONS]

Options:
  -c, --config PATH    Path to configuration file (default: yoker.toml)
  -m, --model MODEL    Model to use (overrides config)
  -h, --help           Show this message and exit
"""

import argparse
import logging
import readline  # noqa: F401 - Enables arrow keys and history in input()
from pathlib import Path

from rich.logging import RichHandler

from yoker import __version__
from yoker.agent import Agent
from yoker.config import Config

# Default configuration file name
DEFAULT_CONFIG = "yoker.toml"


def setup_logging(config: Config) -> None:
  """Configure logging based on configuration.

  Args:
    config: Configuration object.
  """
  log_level = getattr(logging, config.harness.log_level.upper(), logging.INFO)

  logging.basicConfig(
    level=log_level,
    format="%(name)s - %(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
  )

  # Silence noisy modules
  for module in ["httpx", "httpcore", "ollama"]:
    logging.getLogger(module).setLevel(logging.WARNING)


def main() -> None:
  """Run the interactive agent."""
  parser = argparse.ArgumentParser(
    prog="yoker",
    description="Yoker - A Python agent harness with configurable tools and guardrails.",
  )
  parser.add_argument(
    "-c",
    "--config",
    type=Path,
    default=None,
    help=f"Path to configuration file (default: {DEFAULT_CONFIG})",
  )
  parser.add_argument(
    "-m",
    "--model",
    type=str,
    default=None,
    help="Model to use (overrides config)",
  )

  args = parser.parse_args()

  # Load configuration
  config_path = args.config
  if config_path is None:
    # Try default config file
    default_path = Path(DEFAULT_CONFIG)
    if default_path.exists():
      config_path = default_path

  # Create agent
  if config_path is not None:
    from yoker.config import load_config

    config = load_config(config_path)
    print(f"Loaded configuration from: {config_path}")
  else:
    config = Config()
    print("Using default configuration")

  # Setup logging with config
  setup_logging(config)

  # Create and start agent
  print(f"Yoker v{__version__}")
  print("=" * 40)

  agent = Agent(model=args.model, config=config)
  agent.start()


if __name__ == "__main__":
  main()
