# Requirements

## Functional Requirements

### Skill System

- [x] **FR-S1:** Skills are loaded from configured directories (yoker.toml `skills_dirs`)
- [x] **FR-S2:** Skills are loaded from `YOKER_SKILLS_PATH` environment variable
- [x] **FR-S3:** `/skill-name` command invokes skill via CLI
- [x] **FR-S4:** `/skill-name args` command passes arguments to skill
- [x] **FR-S5:** Skill discovery shows available skills to agent
- [x] **FR-S6:** Agent can invoke skills dynamically via SkillTool
- [x] **FR-S7:** Skills use user-level message injection for context
- [ ] **FR-S8:** Skills have namespace support (`pkg:skill` format)
- [x] **FR-S9:** Skill content size limited to 100KB (security)
- [x] **FR-S10:** Skill paths validated against allowed directories (security)
- [x] **FR-S11:** Skill schema with name, description, content, triggers, tools
- [x] **FR-S12:** SkillLoader parses Markdown + YAML frontmatter
- [x] **FR-S13:** SkillRegistry manages loaded skills with name lookup
- [x] **FR-S14:** format_discovery_block() shows skill list for LLM context
- [x] **FR-S15:** format_invocation_block() injects full skill content

### Package Plugin System

- [ ] **FR-PP1:** Packages provide tools/skills/agents via `yoker` module
- [ ] **FR-PP2:** `--with <package>` loads package components before agent starts
- [ ] **FR-PP3:** Namespaced components (`pkg:skill`, `pkg:tool`, `pkg:agent`)
- [ ] **FR-PP4:** Graceful failure when package lacks yoker support
- [ ] **FR-PP5:** Multiple packages can be loaded (`--with pkg1 --with pkg2`)

### Async-First Agent Architecture

- [x] **FR1:** `process()` method is async and handles all core logic
- [x] **FR2:** All Agent methods are async-native
- [x] **FR3:** `_emit()` supports both sync and async event handlers
- [x] **FR4:** Async Ollama streaming works correctly with AsyncClient
- [x] **FR5:** `begin_session()` and `end_session()` are async methods
- [x] **FR6:** All tools use `async def execute()`
- [x] **FR7:** All existing tests pass (1047 tests)
- [x] **FR8:** Documentation updated with async API examples
- [x] **FR9:** CLI uses async API internally with `asyncio.run()`
- [x] **FR10:** Tool base class has `execute()` as abstract async method

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

- [x] **NFR-ASYNC1:** Async-native implementation with no sync wrappers
- [x] **NFR-ASYNC2:** Async API properly handles concurrent operations
- [x] **NFR-ASYNC3:** Resource cleanup works correctly (no event loop leaks)
- [x] **NFR-ASYNC4:** Error handling preserves async stack traces
- [x] **NFR-ASYNC5:** Type hints updated for async methods

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