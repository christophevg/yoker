# Requirements

## Functional Requirements

### Async-First Agent Architecture

- [ ] **FR1:** `process_async()` method exists and handles all core logic
- [ ] **FR2:** `process()` method exists as thin sync wrapper using `asyncio.run()`
- [ ] **FR3:** `_emit()` supports both sync and async event handlers
- [ ] **FR4:** Async Ollama streaming works correctly
- [ ] **FR5:** `begin_session_async()` and `end_session_async()` methods exist
- [ ] **FR6:** Session sync wrappers work correctly
- [ ] **FR7:** All existing tests pass (backward compatibility)
- [ ] **FR8:** New async tests cover async functionality
- [ ] **FR9:** Documentation updated with async API examples
- [ ] **FR10:** CLI uses async API internally

### Core Agent Features

- [x] **FR-A1:** Agent processes messages and returns responses
- [x] **FR-A2:** Agent uses tools to perform operations
- [x] **FR-A3:** Agent emits events during processing
- [x] **FR-A4:** Agent manages conversation context
- [x] **FR-A5:** Agent loads definitions from Markdown files
- [x] **FR-A6:** Agent filters tools based on definition
- [x] **FR-A7:** Agent supports hierarchical spawning

### Tool System

- [x] **FR-T1:** Tools have structured schemas
- [x] **FR-T2:** Tools have guardrails for safety
- [x] **FR-T3:** Tools return structured results
- [x] **FR-T4:** Tools can be registered dynamically
- [x] **FR-T5:** Path-based guardrails enforce filesystem permissions

### Configuration System

- [x] **FR-C1:** Configuration loaded from TOML files
- [x] **FR-C2:** Configuration validated for schema and semantics
- [x] **FR-C3:** Agent definitions loaded from Markdown
- [x] **FR-C4:** Tool guardrails configured globally
- [x] **FR-C5:** Tool availability configured per-agent

### Context Management

- [x] **FR-CM1:** Context persisted to JSONL files
- [x] **FR-CM2:** Context loaded on resume
- [x] **FR-CM3:** Context isolated for subagents
- [x] **FR-CM4:** Context tracks conversation and state

### Event System

- [x] **FR-E1:** Events emitted for all operations
- [x] **FR-E2:** Event handlers registered dynamically
- [x] **FR-E3:** Events support session, turn, thinking, content, tool types
- [x] **FR-E4:** Console handler provides default visualization

### Backend Integration

- [x] **FR-B1:** Ollama client integration
- [x] **FR-B2:** Streaming response support
- [x] **FR-B3:** Tool call parsing and execution
- [x] **FR-B4:** Configurable model parameters
- [x] **FR-B5:** API key authentication for ollama.com

## Non-Functional Requirements

### Async-First Architecture

- [ ] **NFR-ASYNC1:** No performance regression (sync wrapper acceptable overhead)
- [ ] **NFR-ASYNC2:** Async API properly handles concurrent operations
- [ ] **NFR-ASYNC3:** Resource cleanup works correctly (no event loop leaks)
- [ ] **NFR-ASYNC4:** Error handling preserves async stack traces
- [ ] **NFR-ASYNC5:** Type hints updated for async methods

### Performance

- [x] **NFR-P1:** Streaming responses for perceived performance
- [x] **NFR-P2:** Lazy tool loading (Phase 2)
- [x] **NFR-P3:** Context window management (Phase 2)

### Security

- [x] **NFR-S1:** Guardrails enforce filesystem permissions
- [x] **NFR-S2:** Path validation prevents traversal attacks
- [x] **NFR-S3:** Blocked patterns prevent sensitive file access
- [x] **NFR-S4:** Subprocess execution secured (future tools)
- [x] **NFR-S5:** Recursion depth limits prevent runaway spawning

### Quality

- [x] **NFR-Q1:** Test coverage >80%
- [x] **NFR-Q2:** Full type hints (mypy strict mode)
- [x] **NFR-Q3:** Code formatted with ruff
- [x] **NFR-Q4:** Documentation via Sphinx

### Maintainability

- [x] **NFR-M1:** Pluggable architecture
- [x] **NFR-M2:** Clear separation of concerns
- [x] **NFR-M3:** Comprehensive logging
- [x] **NFR-M4:** Structured error handling

## Completed Requirements

- [x] FR-A1 through FR-A7: Core Agent Features
- [x] FR-T1 through FR-T5: Tool System
- [x] FR-C1 through FR-C5: Configuration System
- [x] FR-CM1 through FR-CM4: Context Management
- [x] FR-E1 through FR-E4: Event System
- [x] FR-B1 through FR-B5: Backend Integration
- [x] NFR-P1: Streaming responses
- [x] NFR-S1 through NFR-S5: Security requirements
- [x] NFR-Q1 through NFR-Q4: Quality requirements
- [x] NFR-M1 through NFR-M4: Maintainability requirements