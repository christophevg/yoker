"""Security event logging for Yoker webapp.

Provides structured logging for security events to enable monitoring,
alerting, and forensic analysis of security incidents.

Security events are logged using structlog for structured output with:
- Event type classification
- Contextual information
- Timestamps
- Severity levels
"""

from yoker.logging import get_logger

logger = get_logger(__name__)


class SecurityEventType:
  """Security event types for structured logging.

  These event types are used in security event logging to classify
  security-relevant actions and incidents. Each type corresponds to
  a specific security event that should be monitored.

  Event Types:
    WebSocket Security Events:
      - WS_CONNECTION_OPENED: WebSocket connection established
      - WS_CONNECTION_CLOSED: WebSocket connection closed
      - WS_ORIGIN_REJECTED: WebSocket origin validation failed (CSWSH)
      - WS_MESSAGE_INVALID: WebSocket message validation failed

    Authentication Events:
      - AUTH_SUCCESS: Authentication succeeded
      - AUTH_FAILURE: Authentication failed
      - AUTH_SESSION_CREATED: Session created after authentication
      - AUTH_SESSION_EXPIRED: Session expired

    Rate Limiting Events:
      - RATE_LIMIT_EXCEEDED: Rate limit exceeded (potential DoS)
      - SESSION_LIMIT_REACHED: Session limit reached (DoS protection)

  Usage:
    logger.info(
      SecurityEventType.WS_ORIGIN_REJECTED,
      extra={"origin": "http://evil.com", "reason": "not_in_allowed_list"}
    )
  """

  # WebSocket security events
  WS_CONNECTION_OPENED = "ws_connection_opened"
  WS_CONNECTION_CLOSED = "ws_connection_closed"
  WS_ORIGIN_REJECTED = "ws_origin_rejected"
  WS_MESSAGE_INVALID = "ws_message_invalid"

  # Authentication events
  AUTH_SUCCESS = "authentication_success"
  AUTH_FAILURE = "authentication_failure"
  AUTH_SESSION_CREATED = "auth_session_created"
  AUTH_SESSION_EXPIRED = "auth_session_expired"

  # Rate limiting events
  RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
  SESSION_LIMIT_REACHED = "session_limit_reached"


__all__ = ["SecurityEventType"]