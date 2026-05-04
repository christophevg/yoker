# Consensus Report: WebFetchTool Implementation

**Task:** 2.12 WebFetch Tool
**Date:** 2026-05-04
**Participants:** c3:api-architect, c3:security-engineer

---

## Summary

Both domain agents agree on the implementation approach for WebFetchTool. The design follows the pluggable backend pattern established by WebSearchTool, with comprehensive SSRF protection extending the existing WebGuardrail.

---

## Agreed Architecture

### Components

| Component | Purpose | Owner |
|-----------|---------|-------|
| `WebFetchBackend` | Protocol interface for fetch implementations | API |
| `OllamaWebFetchBackend` | Ollama native web_fetch implementation | API |
| `WebFetchTool` | Tool class with guardrail integration | API |
| `FetchedContent` | Result dataclass | API |
| `WebFetchError` | Exception class with error_type | API |
| `WebFetchToolConfig` | Configuration dataclass | API |
| `WebGuardrail.validate_url()` | URL-specific validation extension | Security |

### Security Measures

| Measure | Priority | Implementation |
|---------|----------|----------------|
| SSRF via URL parsing | Critical | Extend WebGuardrail with `_extract_url_host()` |
| DNS rebinding defense | Critical | IP pinning in backend (for local implementation) |
| Redirect validation | High | Validate each redirect target |
| Content size limits | High | Stream tracking in backend |
| Scheme enforcement | Medium | HTTPS only (configurable) |
| Timeout enforcement | Medium | Configuration parameter |

---

## Design Decisions

### 1. Pluggable Backend (Unanimous)

**Decision:** Use the same pluggable backend pattern as WebSearchTool.

**Rationale:**
- Consistent architecture across web tools
- Allows future LocalWebFetchBackend implementation
- Configuration-driven backend selection

**Implementation:**
```python
class WebFetchBackend(Protocol):
    async def fetch(self, url: str, **kwargs) -> FetchedContent: ...
```

### 2. WebGuardrail Extension (Unanimous)

**Decision:** Extend existing WebGuardrail with URL-specific validation rather than create separate guardrail.

**Rationale:**
- Reuses domain allowlist/blocklist configuration
- Maintains consistent security model
- Reduces code duplication

**Implementation:**
```python
# Add to WebGuardrail
def validate_url(self, url: str) -> ValidationResult:
    # URL parsing, scheme validation, domain check
    # IP resolution for DNS rebinding protection
```

### 3. Ollama Backend First (Unanimous)

**Decision:** Implement OllamaWebFetchBackend first, defer LocalWebFetchBackend to Task 2.13.2.

**Rationale:**
- Ollama backend handles SSRF protection server-side
- Faster implementation with fewer security concerns
- Local backend requires full SSRF implementation

**Implementation:**
```python
class OllamaWebFetchBackend:
    """Uses Ollama's native web_fetch tool with built-in summarization."""
    
    async def fetch(self, url: str, **kwargs) -> FetchedContent:
        # Delegate to Ollama's web_fetch tool
        # Ollama handles content extraction and summarization
```

### 4. Guardrail on Client Side (Unanimous)

**Decision:** Apply WebGuardrail validation before calling backend, regardless of backend choice.

**Rationale:**
- Consistent security enforcement
- Guardrails apply before any network request
- Defense in depth for local backend

---

## File Changes

### New Files

| File | Purpose |
|------|---------|
| `src/yoker/tools/webfetch.py` | WebFetchTool implementation |
| `tests/test_tools/test_webfetch.py` | Unit tests |

### Modified Files

| File | Change |
|------|--------|
| `src/yoker/tools/web_backend.py` | Add WebFetchBackend protocol |
| `src/yoker/tools/web_types.py` | Add FetchedContent, WebFetchError |
| `src/yoker/tools/web_guardrail.py` | Add validate_url() method |
| `src/yoker/config/schema.py` | Add WebFetchToolConfig |
| `src/yoker/tools/__init__.py` | Register WebFetchTool |
| `src/yoker/agent.py` | Add WebFetchTool to default registry |

---

## Implementation Order

1. **Extend WebGuardrail** - Add `validate_url()` method with URL parsing and validation
2. **Add WebFetchBackend protocol** - Define interface in web_backend.py
3. **Implement FetchedContent dataclass** - Result type in web_types.py
4. **Implement OllamaWebFetchBackend** - Use Ollama's native web_fetch
5. **Implement WebFetchTool** - Tool class with guardrail integration
6. **Add configuration** - WebFetchToolConfig in schema.py
7. **Register tool** - Add to __init__.py and agent.py
8. **Write tests** - Security tests and functional tests

---

## Consensus Verification

- [x] API Architect: Design approved, follows existing patterns
- [x] Security Engineer: Security requirements documented, attack vectors covered
- [x] No conflicting requirements identified
- [x] Implementation order agreed

---

## Next Steps

Proceed to **Phase 2.5: Test Setup** - Create test stubs for TDD workflow.