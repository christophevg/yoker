"""Pytest configuration and fixtures."""

import os
import subprocess
import sys
from pathlib import Path


def pytest_configure(config):
  """Configure pytest before running tests.

  Install the demo plugin package for integration tests.
  Set environment variables for trust boundary checks.
  """
  # Set YOKER_ALLOW_CUSTOM_BASE_URL to allow custom base URLs during tests
  # This prevents TrustBoundaryError when tests run in batch mode
  os.environ["YOKER_ALLOW_CUSTOM_BASE_URL"] = "1"

  plugin_path = Path(__file__).parent.parent / "examples" / "plugins" / "demo"

  if plugin_path.exists():
    # Install demo plugin in development mode using uv
    try:
      result = subprocess.run(
        ["uv", "pip", "install", "-e", str(plugin_path)],
        capture_output=True,
        check=False,  # Don't raise on error
      )
      # If uv fails, try with regular pip
      if result.returncode != 0:
        subprocess.run(
          [sys.executable, "-m", "pip", "install", "-e", str(plugin_path)],
          capture_output=True,
          check=False,  # Don't raise on error
        )
    except Exception:
      # Ignore installation errors - some tests may not need the plugin
      pass
