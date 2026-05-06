# Consensus Report: Quart Framework Setup (Task 7.1)

**Date**: 2026-05-06
**Task**: 7.1 Quart Framework Setup
**Status**: ✅ Approved with Critical Requirements

## Domain Reviews

### API Architect Review
- **Document**: `analysis/api-quart-webapp-review.md`
- **Verdict**: Needs Clarification
- **Key Findings**:
  - ✅ Excellent integration with existing event system
  - ✅ Sound application factory pattern
  - ✅ Proper configuration integration
  - ⚠️ WebSocket protocol specification incomplete
  - ⚠️ Session lifecycle documentation needed
  - ⚠️ Error handling strategy undefined

### Security Engineer Review
- **Document**: Provided inline (comprehensive security analysis)
- **Verdict**: Critical Security Issues (MUST Fix)
- **Key Findings**:
  - 🔴 **Critical (9.1 CVSS)**: Cross-Site WebSocket Hijacking (CSWSH)
  - 🔴 **Critical (9.0 CVSS)**: Missing authentication architecture
  - ⚠️ **High (8.1 CVSS)**: In-memory session management without limits
  - ⚠️ **High (7.5 CVSS)**: WebSocket message injection
  - ⚠️ **Medium (7.3 CVSS)**: CORS misconfiguration risk

## Critical Requirements (MUST Implement in Task 7.1)

### 1. WebSocket Origin Validation (CSWSH Prevention)
**Priority**: Blocking
**CVSS**: 9.1
**Agent Agreement**: Both agents identified this as critical

**Implementation**:
```python
# middleware/cors.py
def validate_websocket_origin(origin: str, allowed_origins: Sequence[str]) -> bool:
    """Validate WebSocket origin to prevent CSWSH."""
    # Full implementation provided by security engineer
```

**Usage**: Apply in WebSocket handshake before accepting connections.

### 2. Authentication Architecture Hooks
**Priority**: Blocking
**CVSS**: 9.0
**Agent Agreement**: Security engineer requires, API architect supports

**Implementation**:
```python
# middleware/auth.py
class AuthenticationResult:
    authenticated: bool
    error_message: str | None

async def check_authentication() -> AuthenticationResult:
    """MVP: Allows all connections. Production: Requires valid auth."""

def login_required(func: Callable[..., Awaitable]) -> Callable[..., Awaitable]:
    """Decorator for authentication-protected WebSocket endpoints."""
```

**Usage**: Apply `@login_required` decorator to WebSocket routes.

### 3. Session Management with Limits
**Priority**: High
**CVSS**: 8.1
**Agent Agreement**: Both agents identified session lifecycle issues

**Implementation**:
```python
# session/manager.py
class SessionManager:
    def __init__(self, max_sessions: int = 100, session_timeout_seconds: int = 1800):
        # DoS protection: limit concurrent sessions
        # Memory protection: expire inactive sessions
```

### 4. WebSocket Message Schema Validation
**Priority**: High
**CVSS**: 7.5
**Agent Agreement**: Security requires, API architect needs protocol spec

**Implementation**:
```python
# routes/chat.py
@dataclass
class WebSocketMessage:
    type: Literal["message"]
    content: str
    
    @classmethod
    def from_json(cls, data: str, max_content_length: int = 100_000) -> "WebSocketMessage":
        """Parse and validate WebSocket message with schema validation."""
```

### 5. Security Event Logging
**Priority**: Medium
**CVSS**: 4.7
**Agent Agreement**: Security engineer recommends for incident detection

**Implementation**:
```python
# logging/security.py
class SecurityEventType:
    WS_CONNECTION_OPENED = "ws_connection_opened"
    WS_ORIGIN_REJECTED = "ws_origin_rejected"
    # ... comprehensive security logging
```

## Architecture Decisions

### WebSocket Protocol (API Architect Requirement)
**Decision**: Use JSON messages with explicit type field
**Schema**:
```json
// Client → Server
{
  "type": "message",
  "content": "user message"
}

// Server → Client
{
  "type": "thinking_start" | "content_chunk" | "tool_call" | "turn_complete",
  "timestamp": "ISO-8601",
  // ... event-specific fields
}
```

### Session Lifecycle (API Architect Requirement)
**Decision**: Document Agent/Context/WebSocket relationship
```
WebSocket Connection Opened
  ↓
SessionManager.create_session(session_id, agent)
  ↓
Agent created with fresh ContextManager
  ↓
Events → WebSocketEventHandler → WebSocket.send()
  ↓
WebSocket Connection Closed
  ↓
SessionManager.remove_session(session_id)
```

### Error Handling (API Architect Requirement)
**Decision**: Sanitize errors before sending to client
```python
# Security engineer recommendation
except ValidationError:
    # Safe to send details
    await ws.send({"type": "error", "message": str(e)})
except YokerError:
    # Log details, send generic message
    logger.error(f"Application error: {e}")
    await ws.send({"type": "error", "message": "An error occurred"})
except Exception:
    # Never send stack trace
    await ws.send({"type": "error", "message": "Unexpected error"})
```

## Test Requirements

### Security Tests (MUST Pass)
```python
# Test CSWSH prevention
async def test_origin_validation_rejects_unauthorized():
    # Valid origin: accepted
    # Invalid origin: 403 Forbidden

# Test session limits
def test_session_limit_enforced():
    # max_sessions reached: SessionLimitError

# Test message injection prevention
def test_rejects_missing_content_field():
    # Invalid schema: ValidationError
```

### Integration Tests
```python
# Test WebSocket lifecycle
async def test_websocket_lifecycle():
    # Connect → Send message → Receive events → Disconnect

# Test event streaming
async def test_events_stream_to_websocket():
    # Thinking, content, tool_call events → WebSocket messages
```

## File Structure (Agreed)

```
src/yoker/webapp/
├── __init__.py
├── __main__.py                 # Entry point
├── app.py                      # Application factory
├── config.py                   # WebappConfig
├── routes/
│   ├── __init__.py
│   ├── health.py               # /health endpoint
│   └── chat.py                 # /ws/chat WebSocket
├── handlers/
│   ├── __init__.py
│   └── websocket.py            # WebSocketEventHandler
├── middleware/
│   ├── __init__.py
│   ├── cors.py                 # Origin validation (CRITICAL)
│   └── auth.py                 # Authentication hooks (CRITICAL)
└── session/
    ├── __init__.py
    └── manager.py              # Session limits (HIGH)
```

## Implementation Order

1. **Dependencies**: Add quart, quart-cors to pyproject.toml
2. **Configuration**: Add WebappConfig to schema
3. **Security Foundation** (CRITICAL):
   - middleware/cors.py with origin validation
   - middleware/auth.py with authentication hooks
   - logging/security.py with event logging
4. **Session Management** (HIGH):
   - session/manager.py with limits and expiration
5. **Application Factory**:
   - app.py with Quart factory pattern
   - CORS configuration
6. **WebSocket Handler**:
   - handlers/websocket.py implementing EventCallback
   - Message schema validation
7. **Routes**:
   - routes/health.py for /health
   - routes/chat.py for /ws/chat with @login_required
8. **Entry Point**:
   - __main__.py with production validation
9. **Tests**: Security tests, integration tests

## Acceptance Criteria (Updated)

✅ `uv run python -m yoker.webapp` starts on localhost:5000
✅ GET /health returns {"status": "healthy"}
✅ WebSocket /ws/chat accepts valid origins, rejects invalid (403)
✅ Session limits enforced (max_sessions)
✅ Message schema validation rejects malformed JSON
✅ Security events logged
✅ `make test` passes all tests
✅ `make typecheck` passes

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| CSWSH vulnerability | Critical (9.1) | ✅ Origin validation in task 7.1 |
| Missing auth architecture | Critical (9.0) | ✅ Auth hooks in task 7.1 |
| Session DoS | High (8.1) | ✅ Limits in task 7.1 |
| Message injection | High (7.5) | ✅ Schema validation in task 7.1 |
| CORS misconfiguration | Medium (7.3) | ✅ Production validation in task 7.1 |

## Consensus

**Both domain agents APPROVE proceeding with implementation**, provided that:

1. ✅ Critical security features (CSWSH prevention, auth hooks) are implemented in task 7.1
2. ✅ Session management includes limits and expiration
3. ✅ WebSocket protocol is fully specified before implementation
4. ✅ Error handling sanitizes sensitive information
5. ✅ Security tests validate all critical fixes

**Next Step**: Create test stubs (TDD approach), then invoke python-developer.