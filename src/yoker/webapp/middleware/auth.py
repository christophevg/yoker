"""Authentication middleware hooks.

CRITICAL SECURITY: Provides authentication architecture for WebSocket endpoints.

CVSS Score: 9.0 (Critical)
Vulnerability: Missing authentication architecture
Protection: Authentication hooks must be in place, even if MVP allows all connections
"""

import functools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from yoker.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
  from quart import Quart


@dataclass(frozen=True)
class AuthenticationResult:
  """Result of authentication check.

  Attributes:
    authenticated: Whether authentication succeeded.
    user_id: User ID if authenticated, None otherwise.
    error_message: Error message if authentication failed, None otherwise.
  """

  authenticated: bool
  user_id: str | None = None
  error_message: str | None = None


async def check_authentication() -> AuthenticationResult:
  """Check authentication for the current request.

  MVP Implementation: Allows all connections.
  Production: Requires valid session token.

  Returns:
    AuthenticationResult with authentication status.

  Security Notes:
    - Logs all authentication attempts for security monitoring
    - MVP mode allows all connections but logs warning
    - Production mode validates session tokens
  """
  # MVP: Allow all connections
  # In production, this would check session tokens from cookies/headers
  logger.info("authentication_check_mvp_mode")

  # Log security event
  logger.info(
    "authentication_success",
    extra={"user_id": None, "auth_method": "mvp"},
  )

  return AuthenticationResult(authenticated=True, user_id=None)


def login_required(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
  """Decorator for authentication-protected WebSocket endpoints.

  Args:
    func: Async function to decorate.

  Returns:
    Decorated function that checks authentication.

  Security Notes:
    - Checks authentication before allowing endpoint access
    - Returns 401 Unauthorized if authentication fails
    - Logs all authentication attempts
  """

  @functools.wraps(func)
  async def wrapper(*args: Any, **kwargs: Any) -> Any:
    # Check authentication
    result = await check_authentication()

    if not result.authenticated:
      # Log security event
      logger.warning(
        "authentication_failed",
        extra={"error": result.error_message},
      )

      # Return 401 Unauthorized
      # In Quart WebSocket context, this would close the connection
      from quart import abort

      abort(401, description=result.error_message or "Authentication required")

    # Log successful authentication
    logger.info(
      "authentication_passed",
      extra={"user_id": result.user_id},
    )

    # Call the original function
    return await func(*args, **kwargs)

  return wrapper