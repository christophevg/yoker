"""CORS middleware and WebSocket origin validation.

CRITICAL SECURITY: Implements protection against Cross-Site WebSocket Hijacking (CSWSH).

CVSS Score: 9.1 (Critical)
Vulnerability: Cross-Site WebSocket Hijacking
Protection: Validate WebSocket Origin header against allowed origins
"""

from typing import TYPE_CHECKING, Sequence
from urllib.parse import urlparse

from yoker.logging import get_logger

if TYPE_CHECKING:
  from quart import Quart

logger = get_logger(__name__)


def validate_websocket_origin(origin: str | None, allowed_origins: Sequence[str]) -> bool:
  """Validate WebSocket origin to prevent CSWSH attacks.

  CRITICAL: This function must be called for every WebSocket connection
  to prevent Cross-Site WebSocket Hijacking attacks.

  Args:
    origin: Origin header from WebSocket request (can be None).
    allowed_origins: List of allowed origin URLs.

  Returns:
    True if origin is valid, False otherwise.

  Security Notes:
    - Rejects 'null' origin (file://, data://, sandboxed iframes)
    - Rejects origins with path components
    - Rejects origins with query strings
    - Performs exact scheme://host:port matching
    - Logs all validation attempts for security monitoring
  """
  # Log validation attempt
  logger.info(
    "websocket_origin_validation",
    extra={"origin": origin, "allowed_origins": list(allowed_origins)},
  )

  # Reject missing origin
  if origin is None:
    logger.warning("websocket_origin_missing")
    return False

  # Reject 'null' origin (file://, data://, sandboxed iframes)
  if origin == "null":
    logger.warning("websocket_origin_null")
    return False

  # Parse origin
  try:
    parsed = urlparse(origin)
  except Exception as e:
    logger.warning("websocket_origin_parse_error", extra={"origin": origin, "error": str(e)})
    return False

  # Reject origins with path components (bypass attempt)
  if parsed.path and parsed.path != "/":
    logger.warning("websocket_origin_path_rejected", extra={"origin": origin})
    return False

  # Reject origins with query strings (bypass attempt)
  if parsed.query:
    logger.warning("websocket_origin_query_rejected", extra={"origin": origin})
    return False

  # Normalize origin (remove trailing slash)
  normalized_origin = f"{parsed.scheme}://{parsed.netloc}"

  # Check against allowed origins
  for allowed in allowed_origins:
    # Normalize allowed origin
    allowed_parsed = urlparse(allowed)
    normalized_allowed = f"{allowed_parsed.scheme}://{allowed_parsed.netloc}"

    # Exact match required (no subdomain matching)
    if normalized_origin == normalized_allowed:
      logger.info("websocket_origin_valid", extra={"origin": origin})
      return True

  # Origin not in allowed list
  logger.warning(
    "websocket_origin_not_allowed",
    extra={"origin": origin, "allowed_origins": list(allowed_origins)},
  )
  return False


def configure_cors(app: "Quart", cors_origins: Sequence[str]) -> None:
  """Configure CORS for the Quart application.

  Args:
    app: Quart application instance.
    cors_origins: List of allowed CORS origins.

  Security Notes:
    - Wildcard (*) origins are NOT allowed
    - Origins are validated to prevent misconfiguration
  """
  from quart_cors import cors

  # Validate CORS configuration
  if "*" in cors_origins:
    logger.error("cors_wildcard_not_allowed")
    raise ValueError(
      "Wildcard (*) CORS origin is not allowed for security. "
      "Explicitly list allowed origins."
    )

  # Validate each origin
  for origin in cors_origins:
    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
      logger.error("cors_invalid_origin", extra={"origin": origin})
      raise ValueError(f"Invalid CORS origin: {origin}")

  # Apply CORS middleware
  app = cors(app, allow_origin=list(cors_origins), allow_methods=["GET", "POST", "OPTIONS"])

  logger.info("cors_configured", extra={"origins": list(cors_origins)})