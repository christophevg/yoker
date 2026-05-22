# Consensus Report: Task 1.7.1 Extract AgentCore Class

**Date:** 2026-05-22
**Task:** 1.7.1 Extract AgentCore Class
**Phase:** Phase 1.7 - Async-First Agent Architecture

## Domain Agents Consulted

| Agent | Status | Document |
|-------|--------|----------|
| api-architect | ✅ Approved | `analysis/api-agentcore-extraction.md` |
| security-engineer | ✅ Approved | `analysis/security-agentcore-extraction.md` |

## Consensus Decisions

### 1. Architecture Pattern: Composition Over Inheritance

**Decision:** AgentCore will be a separate class used via composition by both `Agent` and `AsyncAgent`.

**Rationale:**
- Cleaner separation of concerns
- No diamond inheritance problems
- Allows different client types (sync `Client` vs async `AsyncClient`)
- Easier to test in isolation

### 2. AgentCore Responsibilities

**Shared State (in AgentCore):**
- Configuration object
- Model name
- Thinking mode state
- Agent definition
- Tool registry
- Guardrail
- Context manager
- Recursion depth tracking
- Event handlers list
- Command registry

**NOT in AgentCore (stays in Agent/AsyncAgent):**
- Ollama client (different types)
- Event emission `_emit()` (sync vs async execution)
- Streaming logic (different iteration patterns)
- Session methods (sync vs async)

### 3. Security Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| SEC-1 | Guardrails MUST be injected into all filesystem tools during AgentCore initialization | Critical |
| SEC-2 | Each Agent/AsyncAgent instance MUST have its own AgentCore instance | Critical |
| SEC-3 | Configuration validation MUST run before AgentCore initialization | Critical |
| SEC-4 | AgentCore MUST NOT allow mutation of security-critical config after initialization | High |

### 4. Interface Design

**Public Properties (read-only via Agent):**
```python
@property
def model(self) -> str:
    return self._core.model
```

**AgentCore Public Methods:**
- `add_event_handler(handler)`
- `remove_event_handler(handler)`
- `get_event_handlers()`

### 5. Backward Compatibility

**Requirement:** All existing tests must pass without modification.

**Strategy:**
- Property delegations from Agent to AgentCore
- No changes to public Agent interface
- Internal refactoring only

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/yoker/agent_base.py` | CREATE - AgentCore class |
| `src/yoker/agent.py` | MODIFY - Use AgentCore composition |
| `src/yoker/__init__.py` | MODIFY - Export AgentCore (internal use) |
| `tests/test_agent_core.py` | CREATE - Unit tests for AgentCore |
| `tests/test_agent.py` | NO CHANGES - Backward compatibility |

## Identified Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Guardrail bypass during extraction | Medium | Preserve injection pattern in AgentCore init |
| Shared state between agents | Medium | Document: each Agent needs own AgentCore |
| Context thread safety | Medium | Defer to Task H13 (Phase 2 prerequisite) |

## Deferred Items

| Item | Reason | Target |
|------|--------|--------|
| Thread-safe ContextManager | AsyncAgent needs it | Task H13 (Phase 2) |
| Event handler validation | Low priority | Task L5 |

## Acceptance Criteria

1. AgentCore class created with shared state and utilities
2. Agent refactored to use AgentCore via composition
3. All property delegations working
4. All existing tests pass without modification
5. New unit tests for AgentCore with >80% coverage
6. Security requirements SEC-1 through SEC-4 verified

## Sign-off

- [x] API Architect: Approved
- [x] Security Engineer: Approved
- [x] Consensus reached: Yes