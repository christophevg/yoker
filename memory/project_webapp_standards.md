# Project: Webapp Standards

**Date**: 2026-05-06
**Session**: Task 7.1 Quart Webapp Implementation

## Python Webapps (Quart/Uvicorn)

### Standard Stack
- **ASGI Server**: Uvicorn
- **Web Framework**: Quart (async Flask-compatible)
- **CORS**: quart-cors
- **WebSocket**: Native Quart support

### Port Selection
- **Development**: 8000 (avoid 5000 on macOS - AirPlay conflict)
- **Production**: 80 (HTTP) or 443 (HTTPS)

### Entry Points
```bash
# Recommended: Uvicorn (ASGI)
uv run uvicorn <project>.webapp:app --reload

# Module entry point
uv run python -m <project>.webapp
```

### Configuration
```python
@dataclass(frozen=True)
class WebappConfig:
    host: str = "localhost"
    port: int = 8000  # Not 5000 (AirPlay conflict)
    debug: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://localhost:8000")
```

### CORS Configuration
- **Public endpoints**: Use `@cors_exempt` (health, index)
- **API endpoints**: Explicit origin list
- **No wildcard (*)**: Security requirement
- **Origin validation**: Required for WebSocket (CSWSH prevention)

### WebSocket Security
- Always validate `Origin` header
- Reject 'null' origin (file://, data://)
- Normalize URLs for comparison
- Exact match required (no subdomain matching)

## Vue/Vuetify Projects

### Rapid Prototyping Workflow
1. **Start with Baseweb** for quick iteration
2. Baseweb provides:
   - Quick page creation
   - Python API backend endpoints
   - Component library
3. **Iterate rapidly** on functionality
4. **Prove worth** before committing to architecture
5. **Deconstruct** to classic Vue/Vuetify after validation

### Deconstruction Pattern
Only deconstruct Baseweb → Vue/Vuetify when:
- App has proven its worth
- Architecture requirements are clear
- Performance/scaling needs are understood
- Team is ready for maintenance

### Benefits
- Fast iteration during exploration
- Minimal investment before validation
- Flexible architecture evolution
- Risk reduction through prototyping

## Security Standards

### WebSocket Endpoints
- Origin validation (CSWSH prevention)
- Message schema validation
- Session limits (DoS protection)
- JSON serialization (no f-strings)

### CORS
- Explicit origin allowlist
- No wildcard in production
- Public endpoints exempted
- Preflight handling

### Session Management
- Thread-safe operations
- Session limits enforced
- Timeout and expiration
- Activity tracking

## Testing Standards

### WebSocket Testing
- Python test script with `websockets` library
- Browser test UI at `/` route
- curl for health endpoints
- Automated test stubs

### Test Coverage
- Security tests for all CVSS 7.0+ vulnerabilities
- Origin validation tests
- Message validation tests
- Session limit tests

## Common Patterns

### Application Factory
```python
def create_app(config: Config | None = None) -> Quart:
    app = Quart(__name__)
    # ... configuration
    return app

# For uvicorn
app = create_app()
```

### Health Check
```python
@health_bp.route("/health")
@cors_exempt
async def health_check() -> str:
    return jsonify({"status": "healthy", "version": __version__})
```

### WebSocket Handler
```python
@chat_bp.websocket("/ws/chat")
async def chat_websocket():
    while True:
        data = await websocket.receive()
        message = json.loads(data)
        # ... process message
        await websocket.send(json.dumps(response))
```

## Dependencies

```toml
[project.dependencies]
quart = ">=0.19.0,<0.21.0"
quart-cors = ">=0.7.0,<0.9.0"
uvicorn = ">=0.30.0,<0.35.0"
```

## Related Skills

- `c3:quart-webapp` - Quart/Uvicorn patterns
- `c3:baseweb` - Rapid prototyping (in Baseweb project)
- `c3:commit` - Pre-commit verification with functional completeness