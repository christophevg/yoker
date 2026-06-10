"""Pytest configuration and fixtures."""

import subprocess
import sys
from pathlib import Path


def pytest_configure(config):
  """Configure pytest before running tests.

  Install the demo plugin package for integration tests.
  """
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
