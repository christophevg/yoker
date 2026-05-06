"""Pytest fixtures for Quart webapp tests.

Provides test fixtures for:
- Quart test client
- Configuration objects
- Mock WebSocket connections
- Security test helpers
"""

import pytest
from pathlib import Path
from typing import Generator

from yoker.config import Config
from yoker.config.schema import (
  WebappConfig,
  WebSocketConfig,
  HarnessConfig,
  BackendConfig,
  ContextConfig,
  PermissionsConfig,
  ToolsConfig,
  AgentsConfig,
  LoggingConfig,
)


@pytest.fixture
def default_config() -> Config:
  """Create default configuration for testing.

  Returns:
    Configuration object with default webapp settings.
  """
  return Config(
    harness=HarnessConfig(),
    backend=BackendConfig(),
    context=ContextConfig(storage_path="/tmp/yoker-test"),
    permissions=PermissionsConfig(),
    tools=ToolsConfig(),
    agents=AgentsConfig(),
    logging=LoggingConfig(),
    webapp=WebappConfig(
      host="localhost",
      port=5000,
      debug=False,
      cors_origins=("http://localhost:3000",),
      websocket=WebSocketConfig(
        ping_interval=30,
        ping_timeout=10,
        max_message_size=1048576,
      ),
    ),
  )


@pytest.fixture
def custom_config() -> Config:
  """Create custom configuration with specific settings.

  Returns:
    Configuration object with custom webapp settings.
  """
  return Config(
    harness=HarnessConfig(),
    backend=BackendConfig(),
    context=ContextConfig(storage_path="/tmp/yoker-test-custom"),
    permissions=PermissionsConfig(),
    tools=ToolsConfig(),
    agents=AgentsConfig(),
    logging=LoggingConfig(),
    webapp=WebappConfig(
      host="0.0.0.0",
      port=8080,
      debug=True,
      cors_origins=(
        "http://localhost:3000",
        "http://localhost:8080",
        "https://example.com",
      ),
      websocket=WebSocketConfig(
        ping_interval=60,
        ping_timeout=15,
        max_message_size=2097152,
      ),
    ),
  )


@pytest.fixture
def temp_storage(tmp_path: Path) -> Generator[Path, None, None]:
  """Create temporary storage directory for tests.

  Args:
    tmp_path: Pytest temporary path fixture.

  Yields:
    Path to temporary storage directory.
  """
  storage = tmp_path / "yoker-test-storage"
  storage.mkdir(parents=True, exist_ok=True)
  yield storage
  # Cleanup is automatic via pytest tmp_path


@pytest.fixture
def valid_origins() -> tuple[str, ...]:
  """Provide valid origins for CORS testing.

  Returns:
    Tuple of valid origin URLs.
  """
  return (
    "http://localhost:3000",
    "http://localhost:8080",
    "https://example.com",
  )


@pytest.fixture
def invalid_origins() -> tuple[str, ...]:
  """Provide invalid origins for security testing.

  Returns:
    Tuple of invalid origin URLs.
  """
  return (
    "http://evil.com",
    "https://attacker.example",
    "http://localhost:9999",
    "http://192.168.1.100:3000",
    "file:///etc/passwd",
    "null",
    "",
  )


@pytest.fixture
def malicious_messages() -> list[dict]:
  """Provide malicious WebSocket messages for security testing.

  Returns:
    List of malicious message payloads.
  """
  return [
    # Missing required fields
    {"type": "message"},
    {"content": "test"},
    {},
    # Oversized content (DoS attempt)
    {"type": "message", "content": "x" * 10_000_000},
    # Invalid types
    {"type": "invalid", "content": "test"},
    {"type": "<script>alert(1)</script>", "content": "test"},
    # Injection attempts
    {"type": "message", "content": "<script>document.location='http://evil.com'</script>"},
    {"type": "message", "content": "'; DROP TABLE users; --"},
    {"type": "message", "content": "../../../etc/passwd"},
    # Malformed JSON will be tested separately
  ]