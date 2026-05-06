# API Review: Quart Webapp Framework Setup (Task 7.1)

**Date**: 2026-05-06
**Reviewer**: API Architect Agent
**Task**: 7.1 - Quart Framework Setup
**Document Reviewed**: `analysis/api-quart-webapp.md`

## Summary

This review evaluates the API design for the Quart webapp framework setup, focusing on RESTful compliance, WebSocket integration, and alignment with existing Yoker architecture. The design document is comprehensive and well-structured, with strong integration points with the existing event-driven architecture. Several concerns are identified around WebSocket protocol specification, session lifecycle management, and route design clarity.

## Strengths

### 1. Solid Integration with Existing Event System

The design correctly identifies the integration point with Yoker's existing event-driven architecture:

- **WebSocketEventHandler implements EventCallback** - This is the right abstraction, matching the existing `EventCallback = Callable[[Event], None]` pattern
- **Event serialization reuse** - Uses existing `serialize_event()` function from `yoker.events.recorder`, ensuring consistency with CLI/JSONL output
- **Agent lifecycle integration** - Correctly calls `agent.begin_session()` and `agent.end_session()` in WebSocket lifecycle

### 2. Application Factory Pattern

The `create_app(config)` pattern follows Flask/Quart best practices:

- Testable (can create multiple instances with different configs)
- Configurable (config injected at creation time)
- Extensible (blueprints for modular route organization)

### 3. Configuration Integration

The `WebappConfig` properly extends the existing frozen dataclass configuration system:

```python
@dataclass(frozen=True)
class WebappConfig:
    host: str = "localhost"
    port: int = 5000
    debug: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
```

This matches the existing pattern in `src/yoker/config/schema.py`.

### 4. Security-First Approach

The design explicitly notes that task 7.1 is foundation work without authentication, but clearly documents future security considerations for tasks 7.2-7.11.

## Issues and Concerns

### Critical Issues

#### 1. WebSocket Protocol Not Fully Specified

**Severity**: High
**Location**: `routes/chat.py` design

The WebSocket protocol needs more detailed specification:

```python
# Current design shows:
@chat_bp.websocket("/ws/chat")
async def chat_websocket():
    # Client sends: {"type": "message", "content": "..."}
    # Server sends: Event objects
```

**Issues**:
- What is the exact JSON schema for events sent over WebSocket?
- How are errors communicated? (ErrorEvent vs WebSocket close frame)
- What about connection lifecycle messages? (ping/pong, reconnect state sync)
- How does the client know when a turn is complete?

**Recommendation**: Define a complete WebSocket protocol specification:

```yaml
# Outbound events (server → client)
SessionStartEvent:
  type: "SESSION_START"
  model: string
  thinking_enabled: boolean

TurnStartEvent:
  type: "TURN_START"
  message: string

ThinkingStartEvent:
  type: "THINKING_START"

ThinkingChunkEvent:
  type: "THINKING_CHUNK"
  text: string

# ... etc for all event types

# TurnEndEvent includes completion signal
TurnEndEvent:
  type: "TURN_END"
  response: string
  tool_calls_count: integer

# Inbound messages (client → server)
MessageRequest:
  type: "message"
  content: string

# Future: control messages
StopRequest:
  type: "stop"
```

#### 2. Session Lifecycle Not Clear

**Severity**: High
**Location**: `handlers/websocket.py` and `session/manager.py`

The relationship between WebSocket connections, Agent instances, and ContextManagers needs clarification:

```python
# Current design:
ws = await client.websocket("/ws/chat")
agent = Agent(config=config)  # New Agent per connection?
agent.add_event_handler(handler)
agent.begin_session()
```

**Questions**:
- **One Agent per WebSocket connection?** This appears to be the design, but needs explicit documentation.
- **Context persistence?** Does each WebSocket connection create a new context file? Or resume existing?
- **Reconnection handling?** If WebSocket reconnects, does it get a new Agent or resume the old one?
- **Concurrent connections from same user?** Should they share context or be isolated?

**Recommendation**: Clarify session model in the design:

```python
# Proposed session model (document this):
class SessionModel:
    """One WebSocket connection = One Agent instance = One Context"""
    
    # Connection lifecycle:
    # 1. WebSocket connects
    # 2. Create new Agent with new Context
    # 3. Agent.begin_session() called
    # 4. Messages processed via agent.process()
    # 5. WebSocket disconnects
    # 6. Agent.end_session() called
    # 7. Context persisted
    
    # Task 7.4 will add:
    # - User authentication
    # - User-to-sessions mapping (multiple sessions per user)
    # - Session resumption (reconnect to existing context)
```

#### 3. Error Handling Not Specified

**Severity**: Medium
**Location**: `routes/chat.py` exception handling

The design shows a bare `except Exception` with a `pass`:

```python
try:
    # ... process message ...
except Exception as e:
    # Log error
    # Error handling
    pass
```

**Issues**:
- How are Agent exceptions communicated to the client?
- Should errors be sent as `ErrorEvent` via WebSocket or close the connection?
- What about tool execution errors?

**Recommendation**: Define error handling strategy:

```python
# Proposed error handling:
try:
    response = agent.process(message["content"])
    await websocket.send(json.dumps({
        "type": "turn_complete",
        "response": response
    }))
except AgentError as e:
    # Agent-level errors → send ErrorEvent via WebSocket
    await websocket.send(json.dumps({
        "type": "ERROR",
        "error_type": e.__class__.__name__,
        "message": str(e),
        "details": {}
    }))
except Exception as e:
    # Unexpected errors → log and close connection
    log.error("websocket_error", error=str(e))
    await websocket.close(code=1011, reason="Internal error")
```

### Medium Issues

#### 4. Route Structure Needs Clarification

**Severity**: Medium
**Location**: `routes/` design

The TODO.md acceptance criteria mentions:
> Create basic routing structure (/, /login, /chat, /health)

But the design only defines:
- `/health` - Health check
- `/ws/chat` - WebSocket endpoint

**Questions**:
- What should `/` serve? (Static frontend? API info? Redirect?)
- Is `/login` for task 7.3 (magic link authentication)?
- Is `/chat` for REST API fallback, or is everything WebSocket-based?

**Recommendation**: Clarify routing structure in TODO and design:

```yaml
# Proposed routing structure for task 7.1:
routes:
  /health:
    GET: Health check (no auth required)
    Returns: {"status": "healthy", "version": "0.1.0"}
  
  /ws/chat:
    WebSocket: Real-time chat (no auth in 7.1)
    Protocol: Event-based streaming
  
  /:
    (Optional) GET: API info or redirect to frontend
    Returns: {"name": "yoker-webapp", "version": "0.1.0", "endpoints": [...]}

# Task 7.3 will add:
  /auth/request:
    POST: Request magic link email
  
  /auth/verify/:token:
    GET: Verify magic link token

# Task 7.5 will add:
  /api/conversations:
    GET: List conversations (requires auth)
```

#### 5. Agent Instance Creation Per Message

**Severity**: Medium
**Location**: `routes/chat.py` design

The design shows Agent creation inside the WebSocket handler:

```python
async def chat_websocket():
    agent = Agent(config=config)
    agent.add_event_handler(handler)
    agent.begin_session()
    
    while True:
        data = await websocket.receive()
        message = json.loads(data)
        response = agent.process(message["content"])
```

**Issues**:
- Agent is created once per WebSocket connection (good)
- But `agent.process()` is called in a loop, which is correct
- However, the context needs clarification - is a new context created per connection or per message?

**Recommendation**: Clarify context lifecycle in design:

```python
# Clarify that Agent and Context are created ONCE per WebSocket connection:
async def chat_websocket():
    config = websocket.config["YOKER_CONFIG"]
    
    # Create context for this session
    from yoker.context import BasicPersistenceContextManager
    context = BasicPersistenceContextManager(
        storage_path=Path(config.context.storage_path),
        session_id="auto",  # Generates unique session ID
    )
    
    # Create agent with this context
    agent = Agent(config=config, context_manager=context)
    
    # Add WebSocket event handler
    handler = WebSocketEventHandler()
    agent.add_event_handler(handler)
    handler.connect()
    
    # Begin session
    agent.begin_session()
    
    try:
        while True:
            data = await websocket.receive()
            message = json.loads(data)
            
            if message["type"] == "message":
                response = agent.process(message["content"])
                # Response is already streamed via events
    finally:
        handler.disconnect()
        agent.end_session()
```

### Minor Issues

#### 6. Missing ToolContentEvent Handling

**Severity**: Low
**Location**: Event serialization

The design correctly uses `serialize_event()`, but needs to ensure it handles `ToolContentEvent` (added in task 1.5.5).

**Verification**: Checked `yoker/events/recorder.py` - `ToolContentEvent` is handled:

```python
elif isinstance(event, ToolContentEvent):
    data = {
        "tool_name": event.tool_name,
        "operation": event.operation,
        "path": event.path,
        "content_type": event.content_type,
        "content": event.content,
        "metadata": event.metadata,
    }
```

However, `deserialize_event()` doesn't have a case for `TOOL_CONTENT`. This should be added.

#### 7. WebSocketConfig Missing Fields

**Severity**: Low
**Location**: Configuration schema

The `WebSocketConfig` could use additional fields:

```python
@dataclass(frozen=True)
class WebSocketConfig:
    ping_interval: int = 30  # seconds
    ping_timeout: int = 10   # seconds
    max_message_size: int = 1048576  # 1MB
    # Missing:
    # reconnect_timeout: int = 60  # seconds before session cleanup
    # message_queue_size: int = 100  # max pending messages
```

## RESTful Compliance

### Routing Analysis

| Endpoint | HTTP Method | Pattern | RESTful? | Notes |
|----------|-------------|---------|----------|-------|
| `/health` | GET | Resource | ✅ Yes | Health check resource |
| `/ws/chat` | WebSocket | Action-based | ⚠️ Mixed | WebSocket is stateful, not REST |

**Recommendation**: WebSocket endpoint naming is acceptable (not violating REST principles since WebSocket is inherently stateful). However, consider naming it `/chat/stream` or similar to distinguish from future REST endpoints:

```yaml
# Alternative naming:
/chat:
  POST: Create chat message (future REST API for testing/CLI)
  Returns: {"response": "..."} (non-streaming)

/ws/chat:
  WebSocket: Real-time chat stream
  Protocol: Event-based streaming
```

### Future REST Endpoints (Task 7.9)

The design should plan for REST endpoints alongside WebSocket:

```yaml
# Task 7.9 will add:
/api/conversations:
  GET: List conversations (paginated)
  POST: Create new conversation

/api/conversations/{id}:
  GET: Get conversation history
  DELETE: Delete conversation

# All follow RESTful resource naming
```

## Integration with Existing Architecture

### Event System Integration

**Excellent** - The design properly integrates with the existing event system:

- Uses `EventCallback` interface
- Uses `serialize_event()` for JSON serialization
- Handles all event types (thinking, content, tool, error)
- Session lifecycle matches Agent's `begin_session()` / `end_session()`

### Context Manager Integration

**Needs Clarification** - The design mentions context isolation but doesn't specify:

- Where contexts are stored (same `storage_path` as CLI?)
- How to handle concurrent sessions (one context per WebSocket?)
- Session ID generation (auto? user-provided? authenticated user ID?)

**Recommendation**: Add context integration details:

```python
# In WebSocket handler:
from pathlib import Path
from yoker.context import BasicPersistenceContextManager

# Create session-specific context
session_id = str(uuid.uuid4())  # Or use authenticated user ID in task 7.4
context_path = Path(config.context.storage_path) / "webapp" / session_id
context_path.mkdir(parents=True, exist_ok=True)

context = BasicPersistenceContextManager(
    storage_path=context_path,
    session_id="session",  # Single file for this session
)
```

### Configuration Integration

**Good** - The design correctly extends the existing configuration system:

```python
# Add to src/yoker/config/schema.py
@dataclass(frozen=True)
class Config:
    # ... existing fields ...
    webapp: WebappConfig = field(default_factory=WebappConfig)
```

## Dependencies and Version Management

### Quart Version

The design specifies `quart = ">=0.19.0"`. This is appropriate:

- Quart 0.19.0+ supports Python 3.8+ (Yoker requires 3.10+)
- Includes WebSocket support
- Async/await compatible

### quart-cors Version

The design specifies `quart-cors = ">=0.7.0"`. This is appropriate:

- Compatible with Quart 0.19+
- Provides CORS middleware

**Recommendation**: Add dependency justification to design:

```toml
[project.dependencies]
# ... existing dependencies ...
quart = ">=0.19.0"  # Async Flask-compatible framework with WebSocket support
quart-cors = ">=0.7.0"  # CORS middleware for Quart
```

## Security Considerations

### Task 7.1 Scope (No Authentication)

The design correctly identifies that task 7.1 is foundation work without authentication:

- **No authentication required** - This is acceptable for MVP/foundation
- **CORS configured for development** - `localhost:3000` is appropriate for development

### Future Security (Tasks 7.2-7.11)

The design correctly defers security to later tasks:

- Task 7.2: SMTP configuration
- Task 7.3: Magic link authentication
- Task 7.4: Session management with API keys
- Task 7.11: Production hardening

**Recommendation**: Add security notes to design:

```yaml
# Security Scope for Task 7.1:
- No authentication (all endpoints public)
- CORS allows localhost:3000 (development only)
- No input validation beyond JSON parsing
- No rate limiting
- No session persistence

# Task 7.11 will add:
- HTTPS enforcement
- Secure cookies
- CSRF protection
- Rate limiting
- Input sanitization
- Security headers
```

## Performance Considerations

### WebSocket Connection Pooling

**Concern**: One Agent instance per WebSocket connection could be memory-intensive:

```python
# Current design:
# Each WebSocket = One Agent = One Context = One Ollama connection
```

**Recommendation**: This is acceptable for task 7.1 (MVP), but document future optimization:

```yaml
# Phase 2 Optimization (future):
- Agent pooling for connection reuse
- Context caching for faster resume
- Connection pooling for Ollama client
```

### Event Batching

**Concern**: Streaming every event immediately could cause overhead:

```python
# Current: Immediate send
await websocket.send(json.dumps(event_dict))
```

**Recommendation**: This is correct for real-time streaming. No batching needed for task 7.1.

## Testing Strategy

### Unit Tests

The design proposes good test coverage:

```python
# Application factory tests
test_create_app_default_config()
test_create_app_custom_config()

# WebSocket handler tests
test_websocket_handler_sends_events()
test_websocket_handler_disconnect()

# Health endpoint tests
test_health_endpoint()

# Chat endpoint tests
test_chat_websocket_connection()
```

**Additional Test Recommendations**:

```python
# Context lifecycle tests
test_context_created_per_connection()
test_context_persisted_on_disconnect()
test_context_not_shared_between_connections()

# Event serialization tests
test_all_event_types_serialize()
test_tool_content_event_serializes()

# Error handling tests
test_agent_error_sends_error_event()
test_unexpected_error_closes_connection()

# Integration tests
test_full_turn_lifecycle()
test_tool_call_streaming()
test_thinking_mode_toggle()
```

## Recommendations

### High Priority

1. **Define complete WebSocket protocol specification** - Create a separate document detailing all message types and schemas
2. **Clarify session lifecycle model** - Document the relationship between WebSocket, Agent, and Context
3. **Define error handling strategy** - Specify how errors are communicated to clients

### Medium Priority

4. **Clarify routing structure** - Update TODO and design to specify what `/` and `/login` endpoints should do
5. **Add context integration details** - Specify where contexts are stored and how session IDs are generated
6. **Add missing ToolContentEvent deserialization** - Update `deserialize_event()` to handle all event types

### Low Priority

7. **Expand WebSocketConfig fields** - Add reconnect timeout and message queue size
8. **Add dependency justifications** - Document why specific Quart versions are required

## Action Items

### Implementation Tasks (Update TODO.md)

Add the following to task 7.1 acceptance criteria:

- [ ] Define WebSocket protocol specification (message types, schemas)
- [ ] Document session lifecycle model (one Agent per connection)
- [ ] Implement error handling strategy (ErrorEvent vs connection close)
- [ ] Add context integration (session-specific storage path)
- [ ] Add ToolContentEvent deserialization support
- [ ] Write integration tests for full turn lifecycle

### Documentation Tasks

- [ ] Create `docs/websocket-protocol.md` with complete protocol specification
- [ ] Update `analysis/api-quart-webapp.md` with session lifecycle clarification
- [ ] Add routing structure section to design document

### Future Considerations (Task 7.4+)

- [ ] Design session persistence for reconnection
- [ ] Design user authentication integration
- [ ] Design API key management per user
- [ ] Design conversation history REST API (task 7.9)

## Conclusion

**Status**: Needs Clarification

The API design is **well-structured and properly integrates with the existing Yoker architecture**. The use of the event system, configuration integration, and application factory pattern are all correct. However, several critical aspects need clarification before implementation:

1. WebSocket protocol specification needs complete documentation
2. Session lifecycle model needs explicit definition
3. Error handling strategy needs specification

**Recommendation**: Proceed with implementation after addressing high-priority recommendations. The foundational design is sound, but the identified gaps could cause integration issues during implementation.

## Next Steps

1. Address high-priority recommendations (WebSocket protocol, session lifecycle, error handling)
2. Update `analysis/api-quart-webapp.md` with clarifications
3. Create `docs/websocket-protocol.md` with complete protocol specification
4. Update TODO.md with additional acceptance criteria
5. Begin implementation of task 7.1