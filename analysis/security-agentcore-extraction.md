# Security Review: AgentCore Extraction (Task 1.7.1)

**Document Version**: 1.0
**Date**: 2026-05-22
**Reviewer**: Security Engineer (Automated Review)
**Status**: Complete

## Executive Summary

The AgentCore extraction introduces shared state between synchronous and asynchronous Agent implementations. This review identifies security risks related to guardrail enforcement, shared state management, and configuration validation. The current implementation has strong security controls that must be preserved during extraction. Three medium-severity findings and several recommendations are provided.

**Overall Risk Assessment**: Medium - The extraction itself doesn't introduce new vulnerabilities, but shared state management requires careful design to maintain security properties.

## Security Controls Inventory

### Currently Implemented Controls

| Control | Implementation | Location | OWASP Category |
|---------|----------------|----------|----------------|
| Path traversal prevention | `os.path.realpath()` + allowed roots validation | `PathGuardrail._resolve_path()`, `_is_within_allowed_paths()` | A05:2021 - Injection |
| Sensitive file blocking | Regex pattern matching | `PathGuardrail._check_blocked_patterns()` | A01:2021 - Broken Access Control |
| Extension filtering | Whitelist for read, blocklist for write | `PathGuardrail._check_read_extension()`, `_check_write_extension()` | A01:2021 - Broken Access Control |
| File size limits | KB limits for read/write/update | `PathGuardrail._check_file_size()`, `_check_write_content_size()` | A06:2021 - Vulnerable Components |
| Session ID validation | Length, character set, path traversal checks | `context/validator.py::validate_session_id()` | A05:2021 - Injection |
| Storage path validation | Forbidden system directory prefixes | `context/validator.py::validate_storage_path()` | A01:2021 - Broken Access Control |
| File permissions | 0o700 (dirs), 0o600 (files) | `context/basic.py::DIR_MODE`, `FILE_MODE` | A01:2021 - Broken Access Control |
| Atomic writes | File locking (fcntl on Unix) | `context/basic.py::_atomic_write_jsonl()` | A08:2021 - Software/Data Integrity |
| Configuration validation | Required fields, value ranges | `config/validator.py::validate_config()` | A06:2021 - Vulnerable Components |
| Agent tool filtering | Only registered tools available | `Agent._build_tool_registry()` | A01:2021 - Broken Access Control |

### Security Architecture Strengths

1. **Defense-in-depth**: Guardrails validate parameters at tool execution time, not just at configuration time
2. **Principle of least privilege**: Agent definitions limit available tools
3. **Secure defaults**: Empty filesystem_paths raises validation error
4. **Explicit allowlisting**: Extensions, paths, and domains use allowlists, not blocklists

## Security Findings

### Medium Severity

#### M1: Guardrail Injection Bypass Risk During Extraction

**Classification**: Related
**OWASP**: A01:2021 - Broken Access Control
**STRIDE**: Tampering

**Description**: The current Agent implementation injects the guardrail into tools at construction time (line 216-230 in `agent.py`). This defense-in-depth pattern ensures every tool instance has guardrail enforcement. During extraction to AgentCore, if the guardrail injection is moved or refactored, tools could be created without proper guardrails.

**Current Secure Pattern**:
```python
# agent.py:216-230
tools: list[Tool] = [
    ReadTool(guardrail=self._guardrail),  # Guardrail injected
    ListTool(guardrail=self._guardrail),
    WriteTool(guardrail=self._guardrail),
    # ...
]
```

**Risk**: If AgentCore delegates tool creation to Agent/AsyncAgent subclasses without enforcing guardrail injection, a misconfiguration could create tools without security validation.

**Impact**: Filesystem tools could operate without path validation, allowing arbitrary file access including:
- Path traversal (`../../../etc/passwd`)
- Access to blocked patterns (`.env`, credentials)
- Writing to blocked extensions (`.ssh/authorized_keys`)

**Remediation**:
1. AgentCore MUST be responsible for tool creation, not delegating to subclasses
2. Guardrail injection must happen in AgentCore's `_build_tool_registry()`
3. Add a post-initialization validation check that all filesystem tools have guardrails:

```python
# In AgentCore.__init__()
self.tool_registry = self._build_tool_registry()
self._validate_guardrails_enforced()

def _validate_guardrails_enforced(self) -> None:
    """Verify all filesystem tools have guardrails."""
    for tool_name in _FILESYSTEM_TOOLS:
        tool = self.tool_registry.get(tool_name)
        if tool and not hasattr(tool, '_guardrail'):
            raise SecurityError(f"Tool {tool_name} missing guardrail")
```

**Reference**: OWASP ASVS v4.0.3, V1.5.1 - Input validation architecture

---

#### M2: Shared State Between Sync/Async Agents

**Classification**: Related
**OWASP**: A06:2021 - Vulnerable and Outdated Components
**STRIDE**: Tampering, Information Disclosure

**Description**: The architecture document specifies that both Agent and AsyncAgent will delegate to a shared AgentCore instance. While this reduces code duplication, it creates potential for shared mutable state if multiple agent instances access the same AgentCore.

**Current State Isolation**: Each Agent instance has its own:
- `self.context` - Conversation history
- `self._event_handlers` - Event callbacks
- `self._recursion_depth` - Subagent tracking

**Proposed Architecture**:
```python
# From async-first-architecture.md
class Agent:
    def __init__(self, **kwargs):
        self._core = AgentCore(**kwargs)  # Each Agent has its own AgentCore
```

**Risk Scenarios**:

1. **Race Condition in Context**: If context manager is shared between concurrent agents, writes could interleave:
   ```
   Agent A: self.context.add_message("user", "secret key: ABC123")
   Agent B: self.context.save()  # Could save partial state
   ```

2. **Event Handler Leakage**: Event handlers registered with one agent could receive events from another:
   ```python
   def handler(event):
       log.info(f"Sensitive: {event.data}")
   
   agent_a.add_event_handler(handler)
   # If agent_b shares AgentCore, handler receives agent_b events too
   ```

3. **Configuration Mutation**: If AgentCore allows config mutation after initialization:
   ```python
   agent_a._core.config.permissions.filesystem_paths = ("/etc",)
   # agent_b now has access to /etc if sharing AgentCore
   ```

**Impact**:
- Information disclosure between agent sessions
- Integrity violations if one agent modifies shared state
- Confidentiality violations if event handlers receive unintended data

**Remediation**:
1. **Mandatory**: Each Agent/AsyncAgent instance MUST have its own AgentCore instance (not shared)
2. **Recommended**: AgentCore should be immutable after initialization (frozen dataclass or properties-only)
3. **Recommended**: Add ownership tracking to AgentCore:

```python
class AgentCore:
    def __init__(self, owner_id: str | None = None, **kwargs):
        self._owner_id = owner_id or str(uuid.uuid4())
        # ...
    
    def _check_ownership(self, caller: str) -> None:
        if self._owner_id != caller:
            raise SecurityError("AgentCore accessed by wrong owner")
```

**Reference**: CWE-362: Concurrent Execution using Shared Resource with Improper Synchronization

---

#### M3: Context Manager Thread Safety Not Enforced

**Classification**: New (Backlog Item)
**OWASP**: A06:2021 - Vulnerable and Outdated Components
**STRIDE**: Tampering

**Description**: The ContextManager protocol documentation explicitly states "In-memory operations are not thread-safe" (`context/interface.py:64-65`). This limitation exists today, but the async architecture will introduce concurrent access patterns.

**Current Mitigation**: None - single-threaded synchronous Agent

**Future Risk**: AsyncAgent enables:
- Concurrent `process()` calls from multiple coroutines
- Async event handlers that access context
- Background tasks that persist context

**Attack Scenario**:
```python
async def malicious_handler(event):
    # Event handler runs concurrently with process()
    agent.context.clear()  # Clear while process() is using context

agent.add_event_handler(malicious_handler)
await agent.process("query")  # Race condition
```

**Impact**:
- Context corruption leading to inconsistent conversation history
- Tool result injection if race condition during `add_tool_result()`
- Session hijacking if `clear()` removes security context

**Remediation**:
1. **For Task 1.7.1**: Document that AgentCore is not thread-safe, single-threaded use only
2. **For Phase 2**: Add async-safe context manager implementation:

```python
class AsyncContextManager:
    def __init__(self, ...):
        self._lock = asyncio.Lock()
    
    async def add_message(self, role: str, content: str) -> None:
        async with self._lock:
            # Thread-safe message addition
```

3. **Verification**: Add thread-safety test:
```python
@pytest.mark.asyncio
async def test_concurrent_context_access():
    cm = AsyncContextManager()
    tasks = [cm.add_message("user", f"msg{i}") for i in range(100)]
    await asyncio.gather(*tasks)
    assert cm.get_statistics().message_count == 100
```

**Reference**: OWASP ASVS v4.0.3, V11.1.1 - Business logic concurrency

---

### Low Severity

#### L1: Event Handler Security Not Validated

**Classification**: New (Backlog Item)
**OWASP**: A08:2021 - Software and Data Integrity Failures
**STRIDE**: Tampering, Information Disclosure

**Description**: Event handlers are registered without validation. Handlers receive all event types including potentially sensitive data (tool results, thinking content, file contents via ToolContentEvent).

**Current Risk**: Low - handlers are developer-provided, not user-controlled

**Future Risk**: If handlers become user-configurable (e.g., from agent definitions), malicious handlers could:
- Exfiltrate sensitive conversation data
- Log thinking content that users expect to be private
- Access tool results containing file contents

**Remediation**:
1. Document security implications of event handlers
2. If handlers become configurable, add validation:
   ```python
   def add_event_handler(self, handler: EventCallback, allowed_events: set[EventType] | None = None):
       # Validate handler is callable
       # Optionally restrict which events handler receives
   ```

**Reference**: CWE-915: Improperly Controlled Modification of Dynamically-Determined Object Attributes

---

#### L2: Recursion Depth Not Validated at Construction

**Classification**: Related
**OWASP**: A06:2021 - Vulnerable and Outdated Components
**STRIDE**: Denial of Service

**Description**: `_recursion_depth` is passed directly to Agent.__init__ without validation. A malicious caller could bypass recursion limits:

```python
# Current code doesn't validate
def __init__(self, ..., _recursion_depth: int = 0):
    self._recursion_depth = _recursion_depth  # No validation
    self._max_recursion_depth = self.config.tools.agent.max_recursion_depth
```

**Attack**: 
```python
agent = Agent(_recursion_depth=1000000)  # Bypass limit
```

**Impact**: Stack overflow or resource exhaustion in recursive agent calls

**Remediation**: Validate at construction:
```python
def __init__(self, ..., _recursion_depth: int = 0):
    max_depth = self.config.tools.agent.max_recursion_depth
    if _recursion_depth < 0 or _recursion_depth > max_depth:
        raise ValidationError("_recursion_depth", _recursion_depth, f"must be 0-{max_depth}")
    self._recursion_depth = _recursion_depth
```

**Reference**: CWE-400: Uncontrolled Resource Consumption

---

## Positive Security Observations

The current implementation demonstrates security best practices:

1. **Guardrails Enforced at Execution Time**: Tool parameters are validated immediately before execution, not just at configuration time. This prevents LLM-generated malicious parameters from bypassing restrictions.

2. **Secure File Handling**: 
   - Atomic writes with `fsync()` ensure crash safety
   - File locking prevents concurrent write corruption
   - Restrictive permissions (0o700/0o600) prevent unauthorized access

3. **Defense-in-Depth Path Validation**:
   - `os.path.realpath()` resolves symlinks and `..` components
   - Allowed roots check prevents traversal
   - Blocked patterns catch sensitive files
   - Extension filtering adds another layer

4. **Configuration Validation**: `validate_config()` enforces security-relevant constraints:
   - `filesystem_paths` must not be empty (prevents accidental permissive defaults)
   - Regex patterns are validated at startup
   - Value ranges checked (temperature, file sizes)

5. **Agent Tool Filtering**: Agent definitions limit tool availability, reducing attack surface

## Security Requirements for AgentCore

Based on this review, the following security requirements MUST be enforced in the AgentCore extraction:

### Critical Requirements (Blocking)

| ID | Requirement | Verification |
|----|-------------|--------------|
| SEC-1 | Guardrails MUST be injected into all filesystem tools during AgentCore initialization | Unit test: verify all `_FILESYSTEM_TOOLS` have `_guardrail` attribute |
| SEC-2 | Each Agent/AsyncAgent instance MUST have its own AgentCore instance (no sharing) | Architecture review: verify AgentCore is created per-agent |
| SEC-3 | Configuration validation MUST run before AgentCore initialization | Unit test: verify `validate_config()` is called in `__init__` |
| SEC-4 | AgentCore MUST NOT allow mutation of security-critical configuration after initialization | Type check: verify `config` is frozen or accessed via read-only properties |

### High Priority Recommendations

| ID | Recommendation | Rationale |
|----|----------------|-----------|
| SEC-5 | Add guardrail enforcement validation in AgentCore `__init__` | Defense-in-depth: catch misconfiguration early |
| SEC-6 | Validate `_recursion_depth` parameter | Prevent DoS via stack overflow |
| SEC-7 | Document thread-safety limitations of AgentCore | Prevent misuse in async contexts |

### Documentation Requirements

| ID | Requirement | Location |
|----|-------------|----------|
| SEC-8 | Document that AgentCore is single-threaded, not thread-safe | `agent_base.py` docstring |
| SEC-9 | Document security implications of event handlers | `add_event_handler()` docstring |
| SEC-10 | Document that context persistence is session-local, not multi-tenant safe | `context/interface.py` |

## Security Test Coverage Gaps

Current security tests cover:
- Path traversal blocking
- Blocked pattern matching
- Extension filtering
- Path validation

Missing security tests:
1. Guardrail injection verification (all tools have guardrails)
2. Configuration mutation blocking
3. Event handler data isolation
4. Recursion depth validation
5. Thread-safety failure modes (for future async)

**Recommendation**: Add security-specific test file: `tests/test_security.py`

## Scope Classification

| Finding | Classification | Action |
|---------|---------------|--------|
| M1: Guardrail bypass risk | Related | Add to Task 1.7.1 scope - verify guardrails preserved |
| M2: Shared state risks | Related | Add to Task 1.7.1 scope - document per-instance requirement |
| M3: Context thread safety | New | Add to backlog as H13 (Phase 2 prerequisite) |
| L1: Event handler security | New | Add to backlog as L5 (low priority) |
| L2: Recursion depth validation | Related | Add to Task 1.7.1 scope - add validation |

### New Backlog Items

- **H13**: Async-safe context manager for concurrent access - High priority (Phase 2 prerequisite)
- **L5**: Event handler security validation and documentation - Low priority

## Threat Model Summary

### Trust Boundaries

```
+------------------+     +-------------------+     +------------------+
|   LLM Backend    |     |    AgentCore      |     |   Filesystem     |
|  (Untrusted)     |---->|  (Trusted)        |---->|  (Protected)     |
|  - Ollama API    |     |  - Guardrails     |     |  - Allowed paths |
|  - Tool schemas  |     |  - Validation     |     |  - Blocked files |
+------------------+     +-------------------+     +------------------+
                                |
                                v
                         +-------------+
                         |   Context   |
                         |  (Sensitive)|
                         |  - History  |
                         |  - Session  |
                         +-------------+
```

### STRIDE Analysis

| Threat | Risk | Current Mitigation | Extraction Concern |
|--------|------|-------------------|-------------------|
| **Spoofing** | Low | Session IDs use `secrets.token_urlsafe()` | No change |
| **Tampering** | Medium | Guardrails validate all tool params | Guardrail injection must be preserved |
| **Repudiation** | Low | Context logging with timestamps | No change |
| **Information Disclosure** | Medium | File permissions, path restrictions | Shared state could leak data |
| **Denial of Service** | Low | Recursion limits, file size limits | Recursion validation needed |
| **Elevation of Privilege** | Low | Agent tool filtering | No change |

## Recommendations Summary

### For Task 1.7.1 Implementation

1. **MUST**: Guardrails injected in AgentCore._build_tool_registry()
2. **MUST**: Configuration validation called in AgentCore.__init__()
3. **MUST**: Each Agent instance creates its own AgentCore
4. **SHOULD**: Add post-initialization guardrail verification
5. **SHOULD**: Validate recursion depth parameter
6. **MUST**: Document thread-safety limitations

### For Future Phases

1. **Phase 2**: Implement async-safe context manager with locking
2. **Phase 2**: Add security test coverage for guardrail injection
3. **Backlog**: Event handler security documentation and validation

## References

- OWASP Top 10:2021: https://owasp.org/Top10/
- OWASP ASVS v4.0.3: https://owasp.org/www-project-application-security-verification-standard/
- CWE-362: Concurrent Execution using Shared Resource: https://cwe.mitre.org/data/definitions/362.html
- CWE-400: Uncontrolled Resource Consumption: https://cwe.mitre.org/data/definitions/400.html
- CWE-915: Improperly Controlled Modification: https://cwe.mitre.org/data/definitions/915.html

## Appendix: Code Review Checklist

For Task 1.7.1 implementation verification:

- [ ] AgentCore._build_tool_registry() injects guardrails into all filesystem tools
- [ ] AgentCore.__init__() calls validate_config()
- [ ] AgentCore stores config as frozen/read-only
- [ ] Agent.__init__() creates new AgentCore instance (not shared)
- [ ] AsyncAgent.__init__() creates new AgentCore instance (not shared)
- [ ] AgentCore docstring documents single-threaded limitation
- [ ] Recursion depth validated against max_recursion_depth
- [ ] Security tests verify guardrail injection

---

**Review Completed**: 2026-05-22
**Next Review**: After Task 1.7.1 implementation, before PR merge