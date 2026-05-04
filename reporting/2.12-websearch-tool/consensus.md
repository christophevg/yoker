# Consensus Report: WebSearchTool (Task 2.12)

## Domain Agents

| Agent | Document | Status |
|-------|----------|--------|
| API Architect | `analysis/api-websearch-tool.md` | ✓ Approved |
| Security Engineer | `analysis/security-websearch-tool.md` | ✓ Approved |
| Testing Engineer | 108 test stubs | ✓ Approved |

---

## Key Decisions

### 1. Architecture: Pluggable Backend

**Decision**: Use Protocol-based backend abstraction
**Rationale**: Enables Ollama backend now, local DDGS backend later without interface changes

```python
class WebSearchBackend(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...
```

**Agents**: API Architect, Security Engineer
**Consensus**: Unanimous

### 2. Security: Defense-in-Depth

**Decision**: Implement comprehensive guardrails before production use
**Rationale**: SSRF and prompt injection are actively exploited (2026 threat landscape)

**Critical Controls**:
| Control | Priority | Justification |
|---------|----------|---------------|
| SSRF CIDR blocking | P0 | Cloud metadata attack vector |
| DNS resolution validation | P0 | Prevents DNS rebinding |
| Domain whitelisting | P0 | Prevents search result poisoning |
| Query sanitization | P1 | Prevents credential leaks |
| Rate limiting | P1 | Prevents DoS/quota exhaustion |

**Agents**: Security Engineer (lead), API Architect (implementation)
**Consensus**: Unanimous

### 3. Configuration Schema

**Decision**: Add WebSearchToolConfig to config schema
**Rationale**: Centralizes backend selection and guardrail settings

```toml
[tools.websearch]
backend = "ollama"
max_results = 10
timeout_seconds = 30

[permissions.web_domains]
allow = ["*.github.com", "docs.python.org"]
block = ["*.internal", "*.local"]
block_private_cidrs = true
```

**Agents**: API Architect, Security Engineer
**Consensus**: Unanimous

### 4. Test Coverage

**Decision**: 108 test stubs covering security and functionality
**Rationale**: Every security finding must have verification

**Categories**:
- SSRF protection: 12 tests
- Domain filtering: 13 tests
- Query sanitization: 11 tests
- Rate limiting: 5 tests
- Tool functionality: 16 tests
- Backend integration: 22 tests
- Type definitions: 14 tests

**Agents**: Testing Engineer (lead), Security Engineer (security tests)
**Consensus**: Unanimous

---

## Implementation Plan

### Files to Create

| File | Purpose | Priority |
|------|---------|----------|
| `src/yoker/tools/web_types.py` | SearchResult, WebSearchError | P0 |
| `src/yoker/tools/web_backend.py` | Backend protocol + Ollama impl | P0 |
| `src/yoker/tools/web_guardrail.py` | WebGuardrail | P0 |
| `src/yoker/tools/websearch.py` | WebSearchTool | P0 |

### Files to Modify

| File | Change | Priority |
|------|--------|----------|
| `src/yoker/config/schema.py` | Add WebSearchToolConfig | P0 |
| `src/yoker/tools/__init__.py` | Export new components | P0 |
| `src/yoker/agent.py` | Register tool | P1 |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| SSRF bypass via DNS rebinding | Medium | Critical | DNS pinning + CIDR validation |
| Prompt injection via results | High | Critical | Domain whitelisting + content filtering |
| Rate limit bypass | Medium | High | Multi-dimensional limits |
| Query data leakage | Medium | High | Query sanitization + DLP |

---

## Approval

All domain agents approve the implementation plan. Proceed to Phase 4: Implementation.