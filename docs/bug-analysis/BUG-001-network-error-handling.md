# BUG-001: Network Error Handling

## Summary

Network exceptions from httpx/Ollama SDK cause application crashes instead of graceful error handling with retry option.

## Symptoms

When network connection is unstable, the application crashes with:

```
httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)
```

Other potential network errors not currently handled:
- `httpx.ConnectError` - Connection refused
- `httpx.ReadError` - Read timeout
- `httpx.WriteError` - Write failure
- `httpx.ConnectTimeout` - Connection timeout
- `httpx.ReadTimeout` - Read timeout

## Expected Behavior

1. Catch network exceptions gracefully
2. Inform user of connection issue
3. Offer retry option (context state is preserved)
4. Allow graceful exit

## Actual Behavior

Uncaught exception crashes the application.

## Root Cause Analysis

### Current Error Handling

In `__main__.py` (line 264-276), only `ollama.ResponseError` is caught:

```python
except ResponseError as e:
    # Handle Ollama API errors gracefully - allow retry
    if e.status_code == 503:
        print("\n[Error] Ollama server is overloaded...")
    ...
```

### Missing Exception Handling

The `client.chat()` call in `agent.py` (line 335) uses httpx under the hood, which throws:
- `httpx.RemoteProtocolError` - Protocol violations
- `httpx.ConnectError` - Network connectivity issues
- `httpx.TimeoutException` - Request timeouts

These bubble up through the call chain uncaught.

### Location

- Primary: `src/yoker/agent.py` - `process()` method
- Secondary: `src/yoker/__main__.py` - main loop

## Proposed Fix

### Option 1: Catch at Agent Level (Recommended)

Wrap `client.chat()` in try-except in `agent.py`:

**Pros:**
- Centralized handling
- Agent can emit error events
- Context state preserved
- Retry logic available to all callers

**Cons:**
- Requires new exception type

### Option 2: Catch at CLI Level

Add httpx exception handling in `__main__.py`:

**Pros:**
- Simpler implementation

**Cons:**
- Only handles interactive use
- Agent library users don't benefit

### Recommended: Option 1

Add to exceptions.py:

```python
class NetworkError(YokerError):
    """Exception for network-related errors.
    
    Attributes:
        original_error: The underlying httpx/connection error.
        recoverable: Whether the error can be retried.
    """
    def __init__(self, message: str, original_error: Exception | None = None, recoverable: bool = True) -> None:
        self.original_error = original_error
        self.recoverable = recoverable
        super().__init__(message)
```

Then catch in `agent.py`:

```python
try:
    stream = self.client.chat(...)
except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException) as e:
    raise NetworkError(f"Network error: {e}", original_error=e, recoverable=True)
```

## Test Strategy

### Unit Tests

1. Test `NetworkError` exception class
2. Test agent raises `NetworkError` on httpx exceptions
3. Test recoverable flag based on error type

### Integration Tests

1. Mock httpx errors and verify graceful handling
2. Verify retry preserves context state

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing behavior | Low | Additive change only |
| Missing exception types | Medium | Start with common httpx exceptions |
| Context corruption on retry | Low | Context state is immutable during turn |

## Implementation Checklist

- [x] Add `NetworkError` to `exceptions.py`
- [x] Add httpx import to `agent.py`
- [x] Wrap `client.chat()` in try-except
- [x] Add unit tests for NetworkError
- [x] Add integration tests for agent error handling
- [x] Update CLI error handling in `__main__.py`
- [ ] Add documentation for error handling
- [ ] Update CHANGELOG

## Related Files

- `src/yoker/exceptions.py` - Exception definitions
- `src/yoker/agent.py` - Agent implementation
- `src/yoker/__main__.py` - CLI entry point
- `tests/test_agent.py` - Agent tests