"""Trust boundary validation for backend configuration.

Validates that custom base_url endpoints are explicitly allowed before
routing API credentials and conversation content to them. This is a
security feature to prevent credential leakage through malicious configs.

Security rationale:
  - base_url routes all model traffic (including api_key and messages)
  - Project-level ./yoker.toml can override user-level config
  - Non-default base_url could redirect to attacker-controlled server

Validation modes:
  - Interactive mode: Show warning and ask for confirmation
  - Batch mode: Terminate unless YOKER_ALLOW_CUSTOM_BASE_URL=1 is set

Default base URLs (no validation required):
  - Ollama: http://localhost:11434, https://ollama.com
  - OpenAI: use provider SDK default (None in config)
  - Anthropic: use provider SDK default (None in config)
  - Gemini: use provider SDK default (None in config)
"""

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from yoker.config import BackendConfig

# Environment variable to allow custom base URLs in batch mode
ENV_ALLOW_CUSTOM_BASE_URL = "YOKER_ALLOW_CUSTOM_BASE_URL"


class TrustBoundaryError(Exception):
  """Raised when custom base_url is not allowed."""

  pass


def is_custom_base_url(backend_config: "BackendConfig") -> bool:
  """Check if backend is configured with a custom (non-default) base_url.

  Args:
    backend_config: Backend configuration to check.

  Returns:
    True if base_url differs from default, False otherwise.
  """
  # Get the active provider's config
  sub_config = backend_config.config
  if sub_config is None:
    return False

  base_url = sub_config.base_url
  if base_url is None:
    return False

  # Get default URLs from the provider config class
  default_urls = getattr(type(sub_config), "DEFAULT_BASE_URLS", None)

  # For providers with None default (OpenAI, Anthropic, Gemini), any non-None base_url is custom
  if default_urls is None:
    return True

  # For providers with known defaults (Ollama), check if it differs from any default
  return base_url not in default_urls


def validate_base_url_trust(backend_config: "BackendConfig", interactive: bool = True) -> None:
  """Validate that custom base_url is explicitly allowed.

  This is a security gate to prevent credential leakage through malicious configs.
  A project-level ./yoker.toml can set base_url to an attacker-controlled server,
  which would receive all API keys and conversation content.

  Args:
    backend_config: Backend configuration to validate.
    interactive: Whether to show interactive prompt (True) or fail (False).

  Raises:
    TrustBoundaryError: If custom base_url is not allowed in batch mode.
    SystemExit: If user declines confirmation in interactive mode.
  """
  # Only validate if base_url is custom
  if not is_custom_base_url(backend_config):
    return

  provider = backend_config.provider
  base_url = _get_base_url(backend_config)

  # Check environment variable for explicit override
  if os.environ.get(ENV_ALLOW_CUSTOM_BASE_URL) == "1":
    # Explicitly allowed via environment variable
    return

  # Batch mode: terminate with warning
  if not interactive:
    print(
      f"ERROR: Custom base_url configured for {provider}: {base_url}\n"
      f"This routes all API credentials and conversation content to this endpoint.\n"
      f"Set {ENV_ALLOW_CUSTOM_BASE_URL}=1 to allow custom endpoints.\n",
      file=sys.stderr,
    )
    raise TrustBoundaryError(f"Custom base_url not allowed in batch mode for provider {provider}")

  # Interactive mode: show warning and ask for confirmation
  print(
    f"\n⚠️  WARNING: Custom base_url configured for {provider}\n"
    f"   Endpoint: {base_url}\n"
    f"\n"
    f"   This will route ALL API credentials and conversation content\n"
    f"   to this endpoint. Only proceed if you trust this server.\n"
    f"\n"
    f"   To skip this warning, set {ENV_ALLOW_CUSTOM_BASE_URL}=1\n",
    file=sys.stderr,
  )

  try:
    response = input("Proceed with custom base_url? [y/N]: ").strip().lower()
    if response != "y":
      print("Aborted.", file=sys.stderr)
      sys.exit(1)
  except (EOFError, KeyboardInterrupt):
    print("\nAborted.", file=sys.stderr)
    sys.exit(1)


def _get_base_url(backend_config: "BackendConfig") -> str | None:
  """Get the configured base_url for a backend.

  Args:
    backend_config: Backend configuration.

  Returns:
    Configured base_url or None if using default.
  """
  sub_config = backend_config.config
  if sub_config is None:
    return None

  # All provider configs have base_url attribute
  return sub_config.base_url


__all__ = [
  "TrustBoundaryError",
  "validate_base_url_trust",
  "is_custom_base_url",
  "ENV_ALLOW_CUSTOM_BASE_URL",
]
