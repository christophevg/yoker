"""Entry point for running Yoker webapp.

Usage:
    uv run python -m yoker.webapp
    uv run uvicorn yoker.webapp:app --reload

Options:
    --host: Host to bind to (default: from config)
    --port: Port to bind to (default: from config)
    --reload: Enable auto-reload for development
"""

import uvicorn

from yoker.config import load_config_with_defaults
from yoker.logging import get_logger

logger = get_logger(__name__)


def main() -> None:
  """Run Yoker webapp using uvicorn."""
  # Load configuration
  config = load_config_with_defaults()

  # Get server settings
  host = config.webapp.host
  port = config.webapp.port
  debug = config.webapp.debug

  # Production check
  if not debug and host == "localhost":
    logger.warning(
      "webapp_development_host",
      extra={"host": host},
    )

  # Log startup
  logger.info(
    "webapp_starting",
    extra={
      "host": host,
      "port": port,
      "debug": debug,
    },
  )

  print(f"Starting Yoker webapp on {host}:{port}")
  print(f"Debug mode: {debug}")
  print("Press Ctrl+C to stop")

  # Run with uvicorn
  # Import the app lazily to avoid circular imports
  from yoker.webapp import app

  uvicorn.run(
    app,
    host=host,
    port=port,
    log_level="debug" if debug else "info",
    access_log=debug,
  )


if __name__ == "__main__":
  main()