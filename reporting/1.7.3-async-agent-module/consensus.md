# Consensus Report: Task 1.7.3 Create Async Agent Module

**Date:** 2026-05-23
**Task:** 1.7.3 Create Async Agent Module
**Phase:** Phase 1.7 - Async-First Agent Architecture

## Domain Agents Consulted

| Agent | Status | Document |
|-------|--------|----------|
| api-architect | ✅ Approved | `analysis/api-async-agent.md` |
| security-engineer | ✅ Approved | `analysis/security-async-agent.md` |

## Consensus Decisions

### 1. Architecture Pattern: Composition with AgentCore

**Decision:** AsyncAgent uses AgentCore via composition, identical to sync Agent.

**Rationale:**
- No code duplication between sync/async implementations
- Shared state (config, context, tools, guardrails) in AgentCore
- Only differs in: Client type, event emission, streaming logic

### 2. Public Interface Contract

**Shared Properties (delegated to AgentCore):**
- `config`, `model`, `thinking_mode`, `agent_definition`
- `tool_registry`, `context`, `command_registry`

**AsyncAgent-Specific:**
- `client` → `AsyncClient` (vs `Client` in sync Agent)
- All core methods return `Awaitable`

**Methods:**
```python
# Event handlers (sync registration, async emission)
def add_event_handler(handler: EventCallback) -> None
def remove_event_handler(handler: EventCallback) -> None

# Core methods (async)
async def process(message: str) -> str
async def begin_session() -> None
async def end_session(reason: str = "quit") -> None

# Internal
async def _emit(event: Event) -> None  # supports sync & async handlers
```

### 3. Async Event Emission Design

**Decision:** Support both sync and async handlers.

**Implementation:**
```python
async def _emit(self, event: Event) -> None:
    for handler in self._core._event_handlers:
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)  # Sync handlers run directly
```

**Security Note:** Sync handlers in async context can block the event loop. Document handler requirements.

### 4. Security Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| SEC-ASYNC-1 | Handler registration logging | High |
| SEC-ASYNC-2 | Async context manager protocol | High |
| SEC-ASYNC-3 | Stream size limits (10MB) | Medium |
| SEC-ASYNC-4 | Connection pool limits | Medium |
| SEC-ASYNC-5 | Guardrails remain synchronous | Critical |

**Key Insight:** Guardrails must stay synchronous to prevent timing attacks.

### 5. Files to Create/Modify

| File | Action |
|------|--------|
| `src/yoker/async_agent.py` | CREATE - AsyncAgent class |
| `src/yoker/__init__.py` | MODIFY - Export AsyncAgent |

### 6. Breaking Changes

**None.** AsyncAgent is a new feature with no impact on existing sync Agent.

## Acceptance Criteria

1. AsyncAgent class created with AgentCore composition
2. AsyncClient used for Ollama communication
3. All property delegations working
4. Async event emission supports both sync and async handlers
5. Async process() with streaming
6. Async session methods (begin_session, end_session)
7. Export AsyncAgent from `__init__.py`
8. Existing tests pass (sync Agent unchanged)
9. Security requirements documented

## Sign-off

- [x] API Architect: Approved
- [x] Security Engineer: Approved
- [x] Consensus reached: Yes