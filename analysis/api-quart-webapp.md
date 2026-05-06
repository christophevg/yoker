# API Design: Quart Webapp Framework Setup

**Document Version**: 1.0
**Date**: 2026-05-06
**Status**: Implementation Plan

## Overview

This document defines the implementation plan for task 7.1: Quart Framework Setup. This is a foundational task for the Phase 7 webapp feature, providing a web-based chat interface for Yoker.

### Goals

1. Initialize Quart application with async support
2. Create modular webapp structure
3. Integrate WebSocket for real-time streaming
4. Connect to existing Agent event system
5. Configure CORS for frontend integration

### Dependencies

- **Phase 3**: Backend Integration (Ollama client, tool call processing)
- **Phase 4**: Agent Runner (event-driven architecture, context management)
- **Existing Components**: Agent class, event system, configuration system

---

## Architecture Integration

### Event System Integration

The existing Agent class uses an event-driven architecture:

```python
# From src/yoker/agent.py
class Agent:
    def add_event_handler(self, handler: EventCallback) -> None:
        """Register an event handler."""
        self._event_handlers.append(handler)

    def _emit(self, event: Event) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers:
            handler(event)
```

**Integration Strategy**: Create a `WebSocketEventHandler` that:
1. Implements the EventCallback interface
2. Serializes events to JSON
3. Sends events to connected WebSocket clients
4. Handles connection lifecycle (connect/disconnect/reconnect)

### Configuration Integration

The existing configuration system uses frozen dataclasses from TOML:

```python
# From src/yoker/config/schema.py
@dataclass(frozen=True)
class Config:
    harness: HarnessConfig
    backend: BackendConfig
    context: ContextConfig
    permissions: PermissionsConfig
    tools: ToolsConfig
    agents: AgentsConfig
    logging: LoggingConfig
```

**Integration Strategy**: Add a `WebappConfig` section:

```toml
[webapp]
host = "localhost"
port = 5000
debug = false
cors_origins = ["http://localhost:3000"]

[webapp.websocket]
ping_interval = 30  # seconds
ping_timeout = 10   # seconds
max_message_size = 1048576  # 1MB
```

### Context Isolation

Each user session needs an isolated context:

```python
# From src/yoker/context/interface.py
class ContextManager(Protocol):
    def add_message(self, role: str, content: str, ...) -> None: ...
    def get_context(self) -> list[dict]: ...
    def save(self) -> None: ...
```

**Integration Strategy**: Task 7.4 will implement per-user context isolation. For task 7.1, use a simple session-to-context mapping.

---

## File Structure

```
src/yoker/webapp/
├── __init__.py                 # Public API exports
├── __main__.py                 # Entry point: uv run python -m yoker.webapp
├── app.py                      # Quart application factory
├── config.py                   # Webapp configuration schema
├── routes/
│   ├── __init__.py
│   ├── health.py               # Health check endpoint
│   └── chat.py                 # Chat WebSocket endpoint
├── handlers/
│   ├── __init__.py
│   └── websocket.py            # WebSocket event handler
├── middleware/
│   ├── __init__.py
│   └── cors.py                 # CORS configuration
└── session/
    ├── __init__.py
    └── manager.py               # Session management (placeholder for 7.4)
```

---

## Component Design

### 1. Configuration Schema (`config.py`)

**Purpose**: Define webapp-specific configuration.

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class WebSocketConfig:
    """WebSocket configuration."""
    ping_interval: int = 30  # seconds
    ping_timeout: int = 10   # seconds
    max_message_size: int = 1048576  # 1MB

@dataclass(frozen=True)
class WebappConfig:
    """Webapp configuration."""
    host: str = "localhost"
    port: int = 5000
    debug: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
```

**Integration Point**: Add to main `Config` class:

```python
# In src/yoker/config/schema.py
@dataclass(frozen=True)
class Config:
    # ... existing fields ...
    webapp: WebappConfig = field(default_factory=WebappConfig)
```

### 2. Quart Application Factory (`app.py`)

**Purpose**: Create Quart application with configuration.

**Design Pattern**: Application Factory (Flask/Quart standard pattern)

```python
from quart import Quart
from yoker.config import Config

def create_app(config: Config | None = None) -> Quart:
    """Create and configure Quart application.
    
    Args:
        config: Configuration object (loads default if not provided).
    
    Returns:
        Configured Quart application.
    """
    app = Quart(__name__)
    
    # Load configuration
    if config is None:
        from yoker.config import load_config_with_defaults
        config = load_config_with_defaults()
    
    # Store config in app context
    app.config["YOKER_CONFIG"] = config
    
    # Configure CORS
    from yoker.webapp.middleware.cors import configure_cors
    configure_cors(app, config.webapp)
    
    # Register routes
    from yoker.webapp.routes.health import health_bp
    from yoker.webapp.routes.chat import chat_bp
    
    app.register_blueprint(health_bp)
    app.register_blueprint(chat_bp)
    
    return app
```

**Benefits**:
- Testable: Can create multiple app instances with different configs
- Configurable: Config injected at creation time
- Extensible: Blueprints for modular route organization

### 3. WebSocket Handler (`handlers/websocket.py`)

**Purpose**: Bridge Agent events to WebSocket clients.

**Design**: Implement EventCallback interface, serialize events to JSON

```python
import json
from typing import TYPE_CHECKING
from quart import websocket
from yoker.events import Event, serialize_event

if TYPE_CHECKING:
    from yoker.agent import Agent

class WebSocketEventHandler:
    """Event handler that sends events to WebSocket clients.
    
    This handler bridges the Agent's event system to WebSocket clients,
    enabling real-time streaming of thinking, content, and tool events.
    """
    
    def __init__(self):
        """Initialize WebSocket event handler."""
        self._connected = False
    
    async def __call__(self, event: Event) -> None:
        """Handle event by sending to WebSocket client.
        
        Args:
            event: Event from Agent.
        """
        if not self._connected:
            return
        
        # Serialize event to JSON
        event_dict = serialize_event(event)
        event_json = json.dumps(event_dict)
        
        # Send to WebSocket client
        await websocket.send(event_json)
    
    def connect(self) -> None:
        """Mark handler as connected."""
        self._connected = True
    
    def disconnect(self) -> None:
        """Mark handler as disconnected."""
        self._connected = False
```

**Key Design Decisions**:

1. **Async Support**: All methods are async to work with Quart's async WebSocket
2. **Serialization**: Use existing `serialize_event()` from event system
3. **Connection State**: Track connected state to avoid sending to disconnected clients
4. **Error Handling**: Quart handles WebSocket errors automatically

### 4. Chat Route (`routes/chat.py`)

**Purpose**: WebSocket endpoint for chat messages.

```python
from quart import Blueprint, websocket
from yoker.agent import Agent
from yoker.webapp.handlers.websocket import WebSocketEventHandler

chat_bp = Blueprint("chat", __name__)

@chat_bp.websocket("/ws/chat")
async def chat_websocket():
    """WebSocket endpoint for real-time chat.
    
    Protocol:
    - Client sends: {"type": "message", "content": "..."}
    - Server sends: Event objects (thinking_start, content_chunk, etc.)
    """
    handler = WebSocketEventHandler()
    agent = None
    
    try:
        # Get configuration from app context
        config = websocket.config["YOKER_CONFIG"]
        
        # Create agent instance for this connection
        agent = Agent(config=config)
        agent.add_event_handler(handler)
        
        # Mark handler as connected
        handler.connect()
        
        # Begin agent session
        agent.begin_session()
        
        # Message loop
        while True:
            # Receive message from client
            data = await websocket.receive()
            message = json.loads(data)
            
            if message["type"] == "message":
                # Process message through agent
                response = agent.process(message["content"])
                
                # Response is already streamed via events
                # Send completion signal
                await websocket.send(json.dumps({
                    "type": "turn_complete",
                    "response": response
                }))
            
    except Exception as e:
        # Log error
        # Error handling
        pass
    
    finally:
        # Clean up
        handler.disconnect()
        if agent:
            agent.end_session()
```

**Key Design Decisions**:

1. **One Agent Per Connection**: Each WebSocket connection gets its own Agent instance
2. **Event Streaming**: Agent processes messages, events stream to client automatically
3. **Session Lifecycle**: Begin session on connect, end session on disconnect
4. **Error Handling**: Clean up resources on disconnect

### 5. Health Route (`routes/health.py`)

**Purpose**: Health check endpoint for monitoring.

```python
from quart import Blueprint, jsonify

health_bp = Blueprint("health", __name__)

@health_bp.route("/health")
async def health_check():
    """Health check endpoint.
    
    Returns:
        JSON response with status.
    """
    return jsonify({
        "status": "healthy",
        "version": "0.1.0"
    })
```

### 6. CORS Middleware (`middleware/cors.py`)

**Purpose**: Configure CORS for frontend integration.

```python
from quart import Quart
from quart_cors import cors

def configure_cors(app: Quart, config: "WebappConfig") -> None:
    """Configure CORS for the Quart application.
    
    Args:
        app: Quart application instance.
        config: Webapp configuration.
    """
    # Apply CORS configuration
    app = cors(
        app,
        allow_origin=list(config.cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=True,
        max_age=3600,
    )
```

**Dependency**: Requires `quart-cors` package (add to pyproject.toml)

### 7. Session Manager (`session/manager.py`)

**Purpose**: Placeholder for task 7.4 (session management with authentication).

```python
class SessionManager:
    """Manage user sessions.
    
    This is a placeholder for task 7.4 (Authentication).
    Task 7.1 uses a simple connection-based approach without persistence.
    """
    
    def __init__(self):
        """Initialize session manager."""
        self._sessions: dict[str, "Agent"] = {}
    
    def create_session(self, session_id: str, agent: "Agent") -> None:
        """Create a new session.
        
        Args:
            session_id: Session identifier.
            agent: Agent instance for this session.
        """
        self._sessions[session_id] = agent
    
    def get_session(self, session_id: str) -> "Agent | None":
        """Get agent for a session.
        
        Args:
            session_id: Session identifier.
        
        Returns:
            Agent instance or None if not found.
        """
        return self._sessions.get(session_id)
    
    def remove_session(self, session_id: str) -> None:
        """Remove a session.
        
        Args:
            session_id: Session identifier.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
```

**Note**: This is a minimal implementation for task 7.1. Task 7.4 will replace it with proper session management including authentication tokens and Ollama API key storage.

---

## Entry Point

### `__main__.py`

**Purpose**: Enable running webapp with `python -m yoker.webapp`

```python
"""Entry point for running Yoker webapp.

Usage:
    uv run python -m yoker.webapp
    uv run python -m yoker.webapp --port 8080
    uv run python -m yoker.webapp --config yoker.toml
"""

import asyncio
import click
from pathlib import Path

from yoker.config import load_config_with_defaults
from yoker.webapp.app import create_app


@click.command()
@click.option("--config", "-c", type=Path, help="Path to configuration file")
@click.option("--host", "-h", default="localhost", help="Host to bind to")
@click.option("--port", "-p", default=5000, type=int, help="Port to bind to")
@click.option("--debug", "-d", is_flag=True, help="Enable debug mode")
def main(config: Path | None, host: str, port: int, debug: bool):
    """Run the Yoker webapp server."""
    # Load configuration
    if config:
        from yoker.config import load_config
        cfg = load_config(config)
    else:
        cfg = load_config_with_defaults()
    
    # Override host/port from CLI if provided
    if host != "localhost":
        # Note: Config is frozen, so we create a new one
        # In production, use config file for host/port
        pass
    
    # Create app
    app = create_app(cfg)
    
    # Run server
    app.run(host=host, port=port, debug=debug or cfg.webapp.debug)


if __name__ == "__main__":
    main()
```

---

## Dependencies

### Add to `pyproject.toml`

```toml
[project.dependencies]
# ... existing dependencies ...
quart = ">=0.19.0"
quart-cors = ">=0.7.0"
```

**Rationale**:
- **Quart**: Async Flask-compatible framework (required for WebSocket support)
- **quart-cors**: CORS middleware for Quart

---

## Testing Strategy

### Unit Tests

```
tests/test_webapp/
├── __init__.py
├── conftest.py                 # Test fixtures
├── test_app.py                 # Application factory tests
├── test_config.py              # Configuration tests
├── test_handlers_websocket.py  # WebSocket handler tests
├── test_routes_health.py       # Health endpoint tests
└── test_routes_chat.py         # Chat endpoint tests
```

### Test Cases

#### 1. Application Factory Tests

```python
def test_create_app_default_config():
    """Test creating app with default configuration."""
    app = create_app()
    assert app is not None
    assert "YOKER_CONFIG" in app.config

def test_create_app_custom_config():
    """Test creating app with custom configuration."""
    from yoker.config import Config
    config = Config(webapp=WebappConfig(port=8080))
    app = create_app(config)
    assert app.config["YOKER_CONFIG"].webapp.port == 8080
```

#### 2. WebSocket Handler Tests

```python
@pytest.mark.asyncio
async def test_websocket_handler_sends_events():
    """Test that handler sends events to WebSocket client."""
    handler = WebSocketEventHandler()
    handler.connect()
    
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Hello")
    
    # Mock websocket.send
    with patch("quart.websocket.send") as mock_send:
        await handler(event)
        
        # Verify event was serialized and sent
        assert mock_send.called
        call_args = mock_send.call_args[0][0]
        data = json.loads(call_args)
        assert data["type"] == "content_chunk"

@pytest.mark.asyncio
async def test_websocket_handler_disconnect():
    """Test that handler doesn't send when disconnected."""
    handler = WebSocketEventHandler()
    handler.disconnect()
    
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Hello")
    
    with patch("quart.websocket.send") as mock_send:
        await handler(event)
        
        # Should not send when disconnected
        assert not mock_send.called
```

#### 3. Health Endpoint Tests

```python
@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check endpoint returns correct response."""
    app = create_app()
    client = app.test_client()
    
    response = await client.get("/health")
    
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "healthy"
```

#### 4. Chat Endpoint Tests

```python
@pytest.mark.asyncio
async def test_chat_websocket_connection():
    """Test WebSocket connection to chat endpoint."""
    app = create_app()
    
    async with app.test_client() as client:
        ws = await client.websocket("/ws/chat")
        
        # Send test message
        await ws.send(json.dumps({
            "type": "message",
            "content": "Hello, agent!"
        }))
        
        # Receive events
        response = await ws.receive()
        data = json.loads(response)
        
        # Should receive some event type
        assert "type" in data
```

---

## Gaps and Questions

### Questions for Clarification

1. **Session Persistence**: Should task 7.1 persist sessions across restarts, or is in-memory session management acceptable for MVP?
   - **Recommendation**: In-memory only for task 7.1. Task 7.4 will add persistence.

2. **Multiple Connections**: Should the webapp support multiple concurrent WebSocket connections from the same user?
   - **Recommendation**: Yes, each connection gets its own Agent instance. Task 7.4 will manage user-to-sessions mapping.

3. **Context Storage Location**: Where should per-user contexts be stored?
   - **Recommendation**: Use existing `ContextConfig.storage_path` with user-specific subdirectories. Task 7.4 will implement this.

4. **Error Streaming**: Should errors be streamed to the client via WebSocket, or returned as HTTP errors?
   - **Recommendation**: Stream errors as `ErrorEvent` via WebSocket for consistency with event system.

5. **Keep-Alive**: Should the WebSocket send periodic keep-alive pings?
   - **Recommendation**: Yes, use Quart's built-in ping mechanism (configured in `WebSocketConfig.ping_interval`).

### Identified Gaps

1. **Event Serialization**: Need to verify `serialize_event()` handles all event types correctly for JSON serialization.
   - **Action**: Review `src/yoker/events/__init__.py` and add tests for event serialization.

2. **Agent State Management**: Agent has `begin_session()` and `end_session()` - need to ensure these are called correctly in WebSocket lifecycle.
   - **Action**: Add to WebSocket handler's try/finally block.

3. **Context Manager Integration**: Each WebSocket connection needs its own `ContextManager` instance.
   - **Action**: Create context manager in WebSocket handler, pass to Agent.

4. **Tool Guardrails**: Ensure tool guardrails work correctly in webapp context (no TUI-specific behavior).
   - **Action**: Verify `PathGuardrail` doesn't depend on TUI context.

---

## Acceptance Criteria

From TODO.md:

- [ ] Add Quart dependency to pyproject.toml
- [ ] Create src/yoker/webapp/ module structure
- [ ] Implement basic Quart application factory pattern
- [ ] Add WebSocket support for real-time streaming
- [ ] Create basic routing structure (/, /login, /chat, /health)
- [ ] Add CORS configuration for frontend integration
- [ ] Write unit tests for basic routing

**Verification**:

```bash
# Install dependencies
uv sync

# Run webapp
uv run python -m yoker.webapp

# Should see:
# * Running on http://localhost:5000

# Health check
curl http://localhost:5000/health
# {"status": "healthy", "version": "0.1.0"}

# Run tests
make test
# All tests pass

# Type check
make typecheck
# No errors
```

---

## Implementation Order

1. **Add Dependencies**: Add `quart` and `quart-cors` to pyproject.toml
2. **Create Module Structure**: Create `src/yoker/webapp/` directory with `__init__.py`
3. **Configuration**: Add `WebappConfig` to configuration schema
4. **Application Factory**: Implement `create_app()` in `app.py`
5. **Health Endpoint**: Implement `/health` route
6. **WebSocket Handler**: Implement `WebSocketEventHandler`
7. **Chat Endpoint**: Implement WebSocket `/ws/chat` route
8. **CORS Middleware**: Configure CORS for frontend integration
9. **Entry Point**: Implement `__main__.py`
10. **Unit Tests**: Write tests for all components
11. **Integration Test**: Verify webapp starts and handles WebSocket connections

---

## Dependencies on Future Tasks

### Task 7.2: SMTP Configuration and Validation

- Webapp configuration will need SMTP settings for magic link authentication
- No direct dependency on task 7.1 completion

### Task 7.3: Magic Link Email Authentication

- Will use session management from task 7.1
- Will add authentication middleware to routes

### Task 7.4: Session Management and API Key Storage

- Will extend `SessionManager` placeholder from task 7.1
- Will add persistent session storage

### Task 7.5: Frontend Chat Interface

- Will consume WebSocket API from task 7.1
- Depends on WebSocket event protocol being stable

### Task 7.6: Frontend WebSocket Integration

- Direct consumer of WebSocket events from task 7.1
- Event protocol must be finalized

### Task 7.7: Backend Yoker Agent Integration

- Extends WebSocket handler from task 7.1
- Adds per-user context isolation

---

## Security Considerations

### Task 7.1 Scope (No Authentication Yet)

- **No authentication required** - This is foundation work
- **No authorization checks** - All endpoints are public
- **CORS configured for development** - localhost:3000 allowed

### Future Security (Tasks 7.2-7.11)

- **Authentication**: Magic link flow (task 7.3)
- **Session Tokens**: JWT or server-side sessions (task 7.4)
- **API Key Management**: Ollama API key storage (task 7.4)
- **CSRF Protection**: For non-WebSocket endpoints (task 7.11)
- **Rate Limiting**: Prevent abuse (task 7.11)

---

## References

- **Quart Documentation**: https://quart.palletsprojects.com/
- **WebSocket Protocol**: https://websockets.spec.whatwg.org/
- **Flask Application Factory**: https://flask.palletsprojects.com/en/2.3.x/patterns/appfactories/
- **Yoker Event System**: `src/yoker/events/types.py`
- **Yoker Agent Class**: `src/yoker/agent.py`