# Security Review: AsyncAgent Implementation

**Document Version**: 1.0
**Date**: 2026-05-23
**Status**: Security Analysis
**Reviewer**: Security Engineer

## Executive Summary

The AsyncAgent implementation introduces async-first architecture to yoker, enabling integration with async frameworks (Quart, FastAPI) and non-blocking I/O. This review identifies security considerations specific to the async architecture, including handler validation, resource management, and thread safety concerns.

**Overall Risk Assessment**: Medium - The async architecture introduces new complexity that requires careful attention to handler validation and resource cleanup. However, the security posture is generally sound due to existing guardrails and validation layers.

---

## Architecture Analysis

### Current State (Synchronous)

The existing `Agent` class uses:
- Synchronous `ollama.Client` for API communication
- Synchronous event emission to registered handlers
- Synchronous tool execution with guardrails
- Synchronous context persistence (JSONL files)

### Target State (Async)

The `AsyncAgent` class will use:
- Asynchronous `ollama.AsyncClient` for API communication
- Async event emission supporting both sync and async handlers
- Same synchronous tool execution (Phase 1)
- Same synchronous context persistence (Phase 1)

---

## Security Findings

### Critical Findings (CVSS 9.0-10.0)

None identified.

---

### High Findings (CVSS 7.0-8.9)

#### SEC-ASYNC-1: Mixed Sync/Async Handler Support (CVSS 7.5)

**Category**: A06:2021 - Insecure Design

**Description**: The architecture supports both sync and async event handlers for backward compatibility. This design decision introduces complexity that could lead to inconsistent security behavior.

```python
async def _emit(self, event: Event) -> None:
    """Emit event to all handlers asynchronously."""
    for handler in self._core._event_handlers:
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)  # Sync handler in async context
```

**Impact**:
- Sync handlers execute in async context, potentially blocking the event loop
- Handler exceptions may propagate differently based on handler type
- Resource cleanup may differ between sync and async handlers
- Security controls implemented in handlers may behave inconsistently

**Attack Vector**:
1. Malicious sync handler could block async event loop (denial of service)
2. Handler exception handling differs, potentially leaking sensitive data
3. Async handlers could race with sync handlers for shared state

**Remediation**:
1. Document handler requirements clearly in security documentation
2. Add handler validation at registration time:
   ```python
   def add_event_handler(self, handler: EventCallback) -> None:
       """Register an event handler with security validation."""
       # Validate handler signature
       import inspect
       sig = inspect.signature(handler)
       params = list(sig.parameters.values())
       if len(params) != 1:
           raise ValueError("Handler must accept exactly one parameter (Event)")
       
       # Log handler registration for audit
       log.info("handler_registered", handler=handler.__name__, 
                is_async=asyncio.iscoroutinefunction(handler))
       self._core._event_handlers.append(handler)
   ```
3. Implement timeout for sync handlers in async context
4. Add exception isolation per handler

**Reference**: OWASP ASVS v4.0.3 - V11.1.1 Business Logic Security

---

#### SEC-ASYNC-2: Async Resource Cleanup Gaps (CVSS 7.0)

**Category**: A07:2021 - Identification and Authentication Failures (Resource Management)

**Description**: The architecture document does not address async resource cleanup patterns. The current sync implementation uses context managers (`with` blocks) that may not work correctly in async contexts.

**Impact**:
- Network connections may leak in async context
- File handles may not be properly closed on exceptions
- Context persistence may fail intermittently
- Resource exhaustion attacks become possible

**Remediation**:
1. Implement async context manager protocol for AsyncAgent:
   ```python
   async def __aenter__(self) -> "AsyncAgent":
       await self.begin_session()
       return self
   
   async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
       await self.end_session(reason="context_exit")
   ```

2. Use `asyncio.CancelledError` handling for proper cleanup
3. Ensure context persistence uses async file I/O or runs in executor
4. Document resource cleanup requirements for async handlers

**Reference**: OWASP ASVS v4.0.3 - V11.2.1 Resource Management

---

### Medium Findings (CVSS 4.0-6.9)

#### SEC-ASYNC-3: Event Handler Security Validation (CVSS 5.5)

**Category**: A01:2021 - Broken Access Control

**Description**: Event handlers receive potentially sensitive data (tool results, file contents, thinking traces) but there is no validation that handlers are from trusted sources.

**Current Code** (from `base.py`):
```python
def add_event_handler(self, handler: EventCallback) -> None:
    """Register an event handler.
    
    Event handlers receive all events emitted during agent processing.
    Handlers can access potentially sensitive data (tool results, file contents).
    Only register handlers from trusted sources.
    """
    self._core._event_handlers.append(handler)
```

**Impact**:
- Handlers can exfiltrate sensitive data without restrictions
- No authentication/authorization for handler registration
- No validation of handler behavior
- Potential for data leakage through malicious handlers

**Remediation**:
1. Add handler validation with security metadata:
   ```python
   from dataclasses import dataclass
   
   @dataclass
   class HandlerMetadata:
       name: str
       module: str
       is_async: bool
       source: str  # 'stdlib', 'third_party', 'user'
       trusted: bool
   
   def add_event_handler(self, handler: EventCallback, metadata: HandlerMetadata | None = None) -> None:
       if metadata is None:
           metadata = self._infer_handler_metadata(handler)
       
       if not metadata.trusted:
           log.warning("untrusted_handler_registered", handler=metadata.name)
       
       # Store metadata with handler for auditing
       self._handler_metadata[handler] = metadata
       self._core._event_handlers.append(handler)
   ```

2. Implement handler capability model (what data can each handler access)
3. Add audit logging for handler registration and invocation
4. Consider sandboxing untrusted handlers

**Reference**: OWASP ASVS v4.0.3 - V1.2.1 Architecture Design

---

#### SEC-ASYNC-4: Async Streaming from Untrusted LLM (CVSS 5.0)

**Category**: A05:2021 - Injection

**Description**: The async streaming implementation processes chunks from untrusted LLM responses. Malformed or malicious streaming data could exploit async iteration vulnerabilities.

**Code Pattern** (from architecture):
```python
async for chunk in async_stream:
    # Process chunks
    await self._emit(event)
```

**Impact**:
- LLM could return maliciously crafted chunks
- Async iteration could be abused for DoS (infinite streams)
- Chunk processing errors could propagate to event handlers
- Resource exhaustion through large streaming responses

**Remediation**:
1. Implement streaming validation with size limits:
   ```python
   MAX_STREAM_SIZE = 10 * 1024 * 1024  # 10 MB
   
   async def process(self, message: str) -> str:
       total_size = 0
       async for chunk in async_stream:
           total_size += len(chunk.content) + len(chunk.thinking)
           if total_size > MAX_STREAM_SIZE:
               raise SecurityError("Stream size limit exceeded")
           await self._emit(event)
   ```

2. Add timeout for async iteration
3. Validate chunk structure before processing
4. Implement graceful degradation for malformed chunks

**Reference**: OWASP ASVS v4.0.3 - V5.3.6 Input Validation

---

#### SEC-ASYNC-5: Guardrail Enforcement in Async Context (CVSS 5.0)

**Category**: A01:2021 - Broken Access Control

**Description**: The current guardrail implementation is synchronous. In async contexts, guardrail validation runs in the sync event loop, potentially creating timing windows for TOCTOU attacks.

**Current Code** (from `agent.py`):
```python
# Validate tool parameters through guardrail
validation = self._guardrail.validate(tool_name, tool_args)
if not validation.valid:
    log.info("guardrail_blocked", tool=tool_name, reason=validation.reason)
    result = f"Error: {validation.reason}"
    success = False
else:
    # Execute tool
    tool_result = tool.execute(**tool_args)
```

**Impact**:
- Race conditions between validation and execution
- Guardrail bypass through async timing attacks
- State changes between validation and execution
- Potential for privilege escalation

**Remediation**:
1. Keep guardrail validation synchronous and blocking (current approach is correct)
2. Ensure no async operations between validation and execution
3. Document that guardrails must be synchronous for security
4. Add atomic validation+execution pattern for critical tools

**Recommendation**: The current sync guardrail is secure. Async guardrails would introduce security vulnerabilities. Keep guardrails synchronous.

**Reference**: OWASP ASVS v4.0.3 - V5.3.1 Input Validation

---

### Low Findings (CVSS 0.1-3.9)

#### SEC-ASYNC-6: Context Manager Thread Safety (CVSS 3.5)

**Category**: A02:2021 - Cryptographic Failures (Data Integrity)

**Description**: The `BasicPersistenceContextManager` uses file locking (`fcntl.LOCK_EX`) on Unix but falls back to no locking on Windows. In async contexts, concurrent access patterns differ from sync contexts.

**Code** (from `context/basic.py`):
```python
if fcntl is not None:
    # Acquire exclusive lock (Unix only)
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
        json.dump(record, f)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
else:
    # Windows: write without locking
    json.dump(record, f)
    f.write("\n")
    f.flush()
    os.fsync(f.fileno())
```

**Impact**:
- File corruption on Windows in concurrent async scenarios
- Session data inconsistency between async tasks
- Log integrity issues
- Limited impact due to single-agent-per-context design

**Remediation**:
1. Use `aiofiles` for async file I/O (Phase 2)
2. Implement async-safe file locking abstraction:
   ```python
   # Future: async context persistence
   async def _atomic_write_jsonl_async(self, record: dict[str, Any]) -> None:
       import aiofiles
       import asyncio
       
       # Use asyncio.Lock for async-safe file access
       async with self._file_lock:
           async with aiofiles.open(self._file_path, mode='a') as f:
               await f.write(json.dumps(record) + '\n')
   ```

3. Document Windows limitations clearly
4. Consider in-memory context for async sessions with batch persistence

**Reference**: OWASP ASVS v4.0.3 - V8.1.1 Data Protection

---

#### SEC-ASYNC-7: AsyncClient Connection Handling (CVSS 3.0)

**Category**: A02:2021 - Cryptographic Failures

**Description**: The AsyncClient configuration mirrors the sync Client but does not address async-specific connection pooling, timeout handling, and retry logic.

**Current Sync Client** (from `agent.py`):
```python
api_key = os.environ.get("OLLAMA_API_KEY")
if api_key:
    self._client = Client(
        host="https://ollama.com", 
        headers={"Authorization": f"Bearer {api_key}"}
    )
else:
    base_url = loaded_config.backend.ollama.base_url
    self._client = Client(host=base_url)
```

**Impact**:
- Connection leaks in async contexts if not properly closed
- Timeout handling differs between sync and async clients
- API key handling must be consistent
- Connection pool exhaustion under load

**Remediation**:
1. Implement async context manager for AsyncClient
2. Configure connection timeouts explicitly:
   ```python
   self._client = AsyncClient(
       host=base_url,
       timeout=httpx.Timeout(60.0, connect=5.0),
       limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
   )
   ```

3. Ensure API key handling is identical to sync client
4. Add connection pool monitoring

**Reference**: OWASP ASVS v4.0.3 - V9.1.1 Communications Security

---

#### SEC-ASYNC-8: Recursion Depth Enforcement (CVSS 2.0)

**Category**: A06:2021 - Vulnerable and Outdated Components

**Description**: Recursion depth tracking exists for subagent spawning but does not account for async concurrency. Multiple concurrent async agents could bypass depth limits.

**Current Validation** (from `base.py`):
```python
max_depth = self._config.tools.agent.max_recursion_depth
if _recursion_depth < 0:
    raise ValueError(f"_recursion_depth must be non-negative, got {_recursion_depth}")
if _recursion_depth > max_depth:
    raise ValueError(
        f"_recursion_depth ({_recursion_depth}) exceeds max_recursion_depth ({max_depth})"
    )
self._recursion_depth = _recursion_depth
self._max_recursion_depth = max_depth
```

**Impact**:
- Concurrent async agents could spawn many subagents
- Depth tracking is per-agent, not global
- Resource exhaustion through parallel recursion
- Limited impact due to configuration limits

**Remediation**:
1. Document that depth tracking is per-agent instance
2. Add global concurrency limit for subagents
3. Consider global recursion counter for async contexts
4. Log recursion depth warnings

**Recommendation**: Current per-agent depth tracking is sufficient for MVP. Add global limits in Phase 2.

**Reference**: OWASP ASVS v4.0.3 - V5.3.4 Input Validation

---

## Threat Model Analysis (STRIDE)

### Spoofing

| Threat | Mitigation | Status |
|--------|------------|--------|
| Async handlers impersonating sync handlers | Handler type checking with `asyncio.iscoroutinefunction()` | Implemented |
| Malicious handler registration | None - document trust requirement | **Gap** |

**Recommendation**: Add handler registration logging and optional handler verification.

### Tampering

| Threat | Mitigation | Status |
|--------|------------|--------|
| Event data modification in handlers | Events are frozen dataclasses | Implemented |
| Guardrail bypass via async timing | Guardrails are synchronous | Implemented |
| Context file tampering | File permissions (0o600), path validation | Implemented |

**Status**: No gaps identified.

### Repudiation

| Threat | Mitigation | Status |
|--------|------------|--------|
| Handler invocation not logged | No logging of handler calls | **Gap** |
| Event emission not logged | No audit trail for events | **Gap** |
| Subagent actions not attributed | Subagent sessions have unique IDs | Implemented |

**Recommendation**: Add audit logging for handler registration and event emission.

### Information Disclosure

| Threat | Mitigation | Status |
|--------|------------|--------|
| Sensitive data in event handlers | Documented in handler docstring | Implemented |
| LLM response leakage through streaming | Stream size limits needed | **Gap** |
| File content exposure through events | Events can contain file contents | By Design |

**Recommendation**: Implement stream size limits.

### Denial of Service

| Threat | Mitigation | Status |
|--------|------------|--------|
| Blocking sync handler in async context | No timeout enforcement | **Gap** |
| Infinite streaming from LLM | No stream size limits | **Gap** |
| Connection pool exhaustion | No pool limits configured | **Gap** |

**Recommendation**: Add timeouts for sync handlers, stream size limits, and connection pool configuration.

### Elevation of Privilege

| Threat | Mitigation | Status |
|--------|------------|--------|
| Guardrail bypass through async race | Guardrails are synchronous | Implemented |
| Path traversal in async context | PathGuardrail is synchronous | Implemented |
| Recursion depth bypass | Per-agent depth tracking | Implemented |

**Status**: No gaps identified.

---

## Security Requirements for Async Implementation

### Required for MVP (Phase 1)

| ID | Requirement | Priority | Reference |
|----|-------------|----------|-----------|
| SEC-ASYNC-001 | Handler registration logging | High | SEC-ASYNC-1, SEC-ASYNC-3 |
| SEC-ASYNC-002 | Async context manager implementation | High | SEC-ASYNC-2 |
| SEC-ASYNC-003 | Stream size limits | Medium | SEC-ASYNC-4 |
| SEC-ASYNC-004 | Connection pool configuration | Medium | SEC-ASYNC-7 |
| SEC-ASYNC-005 | Document sync guardrail requirement | High | SEC-ASYNC-5 |

### Recommended for Phase 2

| ID | Requirement | Priority | Reference |
|----|-------------|----------|-----------|
| SEC-ASYNC-006 | Handler timeout enforcement | Medium | SEC-ASYNC-1 |
| SEC-ASYNC-007 | Async context persistence | Low | SEC-ASYNC-6 |
| SEC-ASYNC-008 | Global subagent concurrency limit | Low | SEC-ASYNC-8 |
| SEC-ASYNC-009 | Handler capability model | Low | SEC-ASYNC-3 |
| SEC-ASYNC-010 | Event audit trail | Medium | Repudiation |

---

## Secure Implementation Patterns

### 1. Async Event Emission Pattern

```python
async def _emit(self, event: Event) -> None:
    """Emit event to all handlers with security controls."""
    for handler in self._core.get_event_handlers():
        try:
            # Set per-handler timeout for sync handlers
            if asyncio.iscoroutinefunction(handler):
                # Async handler - await directly
                await handler(event)
            else:
                # Sync handler - run in executor with timeout
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, handler, event),
                    timeout=self._config.events.handler_timeout_seconds
                )
        except asyncio.TimeoutError:
            log.warning("handler_timeout", handler=handler.__name__)
        except Exception as e:
            # Isolate handler exceptions
            log.error("handler_error", handler=handler.__name__, error=str(e))
```

### 2. Async Context Manager Pattern

```python
class AsyncAgent:
    async def __aenter__(self) -> "AsyncAgent":
        """Initialize async context."""
        await self.begin_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup async context."""
        reason = "error" if exc_type else "normal_exit"
        await self.end_session(reason=reason)
    
    async def process(self, message: str) -> str:
        """Process with resource management."""
        async with self:
            return await self._process_internal(message)
```

### 3. Secure Streaming Pattern

```python
async def process(self, message: str) -> str:
    """Process with streaming validation."""
    MAX_STREAM_SIZE = 10 * 1024 * 1024  # 10 MB
    STREAM_TIMEOUT = 300  # 5 minutes
    
    try:
        async with asyncio.timeout(STREAM_TIMEOUT):
            total_size = 0
            async for chunk in async_stream:
                # Size validation
                chunk_size = len(chunk.content or "") + len(chunk.thinking or "")
                total_size += chunk_size
                if total_size > MAX_STREAM_SIZE:
                    raise SecurityError(f"Stream size limit exceeded: {total_size} bytes")
                
                await self._emit(event)
    except asyncio.TimeoutError:
        raise NetworkError("Stream timeout", recoverable=True)
```

---

## Positive Security Observations

The async architecture maintains several strong security practices from the sync implementation:

1. **Guardrails are Synchronous**: PathGuardrail and other validation runs synchronously, preventing async timing attacks.

2. **Context Isolation**: Each agent instance has its own AgentCore, preventing state sharing between async agents.

3. **Recursion Depth Tracking**: Subagent depth limits prevent uncontrolled recursion.

4. **Event Isolation**: Events are frozen dataclasses, preventing modification after creation.

5. **File Permissions**: Context files use secure permissions (0o600 for files, 0o700 for directories).

6. **Path Validation**: PathGuardrail resolves symlinks and checks against allowed roots.

7. **API Key Handling**: API keys read from environment variables, not hardcoded.

8. **Timeout Enforcement**: Subagent execution uses signal-based timeout on Unix.

---

## Recommendations

### Immediate (Before Async Implementation)

1. **SEC-ASYNC-001**: Add handler registration logging to AgentCore
2. **SEC-ASYNC-002**: Implement async context manager for AsyncAgent
3. **SEC-ASYNC-005**: Document that guardrails must remain synchronous

### Short-term (Phase 1)

4. **SEC-ASYNC-003**: Add stream size limits to AsyncAgent.process()
5. **SEC-ASYNC-004**: Configure AsyncClient connection pool limits
6. Add unit tests for async security scenarios

### Long-term (Phase 2)

7. **SEC-ASYNC-006**: Implement handler timeout enforcement
8. **SEC-ASYNC-007**: Add async context persistence with aiofiles
9. **SEC-ASYNC-010**: Create event audit trail for security monitoring

---

## Security Testing Checklist

### For AsyncAgent Implementation

- [ ] Test sync handler timeout in async context
- [ ] Test async handler exception isolation
- [ ] Test stream size limit enforcement
- [ ] Test connection pool exhaustion scenarios
- [ ] Test async context cleanup on exception
- [ ] Test concurrent agent depth enforcement
- [ ] Test handler registration logging
- [ ] Test guardrail enforcement in async context
- [ ] Test context file locking on Windows vs Unix
- [ ] Test API key handling consistency between sync and async

---

## Conclusion

The async-first architecture for AsyncAgent is well-designed with security in mind. The key security decision to keep guardrails synchronous prevents timing attacks. The main areas requiring attention are:

1. **Handler validation and logging** - Currently handlers can be registered without validation
2. **Async resource cleanup** - Context managers and timeouts need async-aware implementation
3. **Stream size limits** - Large LLM responses could exhaust resources
4. **Connection pool management** - AsyncClient needs explicit pool configuration

The existing security controls (guardrails, path validation, recursion limits) transfer correctly to the async context because they remain synchronous. This is the correct approach - security validation should not be async to prevent timing attacks.

**Security Approval Status**: Approved for implementation with required changes documented above.

---

## References

- OWASP Top 10:2021: https://owasp.org/Top10/
- OWASP ASVS v4.0.3: https://owasp.org/www-project-application-security-verification-standard/
- OWASP Cheat Sheet Series: https://cheatsheetseries.owasp.org/
- Python asyncio Security: https://docs.python.org/3/library/asyncio.html#security
- httpx Async Security: https://www.python-httpx.org/async/