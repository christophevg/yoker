# TODO

## Backlog

### Phase 1.5: UI/UX Fixes (High Priority)

- [x] **1.5.1 Remove Thinking Headers**
  - Remove "[thinking]" and "[response]" text headers from console output
  - Use visual styling (gray/muted color) to distinguish thinking sections
  - Ensure thinking sections remain readable but visually distinct from content
  - Verify the change works in both interactive and demo modes

- [x] **1.5.2 Fix Mouse Selection in Interactive Mode**
  - Set `mouse_support=False` in `PromptSession` (recommended fix from UX analysis)
  - Verify text selection works in terminal output area (scrollback buffer)
  - Verify text can be copied correctly (Ctrl+Shift+C / Cmd+C)
  - Verify keyboard navigation still works (arrows, Home, End, Ctrl+A, Ctrl+E)
  - Verify no conflicts with existing keybindings (multiline, history, search)
  - Update README.md to document keyboard navigation
  - See `analysis/ux-mouse-selection.md` for full UX analysis
  - See `reporting/1.5.2-mouse-selection/summary.md` for implementation summary

- [x] **1.5.3 Update Demo Session Script**
  - Update tool display format: `[Tool Call] read(file_path=...)` → `Read tool: <filename>`
  - Use cyan color for tool name (matches session header style)
  - Display filename only (not full path) for better readability
  - Ensure tool display is visually distinct but harmonious with other output
  - Create new session log for replay with tool calls
  - Improve replay to include commands and thinking events
  - Test replay mode produces same visual output as live session
  - See `analysis/ux-demo-session.md` for full UX analysis
  - See `reporting/1.5.3-demo-session/functional-review.md` for review summary

- [x] **1.5.4 Event Logging System**
  - Create `EventLogger` class to log all event types to JSONL
  - Log SESSION_START, TURN_START, THINKING_*, TOOL_*, CONTENT_*, events
  - Enable full visual replay capability
  - Create `EventReplayAgent` that emits events from log
  - Extracted from demo_session.py into src/yoker/logging/ module
  - See `reporting/1.5.4-event-logging/summary.md` for implementation summary

### Phase 1.6: Documentation (Medium Priority)

- [x] **1.6.1 Update Documentation Folder**
  - Review all files in docs/ folder against current implementation
  - Update outdated content to reflect current architecture
  - Ensure consistency with README.md and CLAUDE.md
  - Update code examples where necessary
  - Add feature checkboxes (current vs planned)
  - Add "Why Yoker?" section with rationale links
  - Add `--output` option to demo_session.py for single-use screenshots
  - See `reporting/1.6.1-documentation/summary.md` for implementation summary

- [x] **1.6.2 Define Project Rationale**
  - Research existing coding agent solutions and their approaches
  - Interview user to understand goals and vision
  - Document unique selling factors of yoker
  - Create rationale document explaining why yoker should exist and what it offers
  - Identify gaps in existing solutions that yoker addresses
  - See `docs/rationale.md` for the rationale document
  - See `research/2026-04-22-coding-agent-rationale/` for research findings

### Phase 1: Core Infrastructure

- [x] **1.1 Project Setup**
  - Create Python package structure (src/yoker/)
  - Set up pyproject.toml with dependencies (following clitic template)
  - Configure development environment (ruff, mypy, pytest)
  - Create basic CLI entry point
  - Set up Sphinx documentation structure
  - Create .readthedocs.yaml

- [x] **1.2 Configuration System**
  - Implement TOML config loader
  - Define configuration schema (dataclasses or pydantic)
  - Implement config validator (schema + semantic checks)
  - Add error handling for invalid configs
  - Create example configuration files

- [x] **1.3 Agent Definition Loader**
  - Implement Markdown file parser
  - Parse YAML frontmatter
  - Validate agent definitions against schema
  - Handle missing or invalid frontmatter
  - Create example agent definitions
  - See `analysis/agent-definition-loader.md` for design
  - See `reporting/1.3-agent-definition-loader/summary.md` for implementation summary

- [x] **1.5 Logging System**
  - Integrate structlog for structured logging
  - Add file and console handlers
  - Log tool calls and guardrail decisions
  - Add timing information for performance tracking
  - See `analysis/api-logging-system.md` for API design
  - See `reporting/1.5-logging-system/summary.md` for implementation summary

### Research Tasks (Medium Priority)

- [ ] **R.1 Hermes Agent Comparison**
  - Research Hermes Agent architecture and capabilities
  - Compare Hermes to Yoker architecture
  - Compare Hermes to C3 Agentic Harness approach
  - Compare Hermes to Assistant pattern
  - Document findings in research folder
  - Identify features worth incorporating

### Future Features (Low Priority)

- [ ] **F.1 Multi-Agent Chat Room Demo**
  - Design multi-agent chat room architecture
  - Implement spawn command in TUI to spawn agent from folder
  - Create agent folder structure for spawned agents
  - Implement agent-to-agent communication protocol
  - Create demonstration scenario

### Phase 2: Tool Implementation

- [ ] **2.1 Tool Base Framework**
  - Define Tool abstract base class
  - Define ToolResult and ValidationResult types
  - Implement tool registry
  - Create guardrail enforcer interface

- [ ] **2.2 List Tool**
  - Implement directory listing functionality
  - Add path restriction guardrails
  - Add max_depth and max_entries limits
  - Add pattern filtering support
  - Write unit tests

- [ ] **2.3 Read Tool**
  - Implement file reading functionality
  - Add path restriction guardrails
  - Add file extension filtering
  - Add size limit enforcement
  - Add blocked pattern matching (e.g., .env files)
  - Write unit tests

- [ ] **2.4 Write Tool**
  - Implement file writing functionality
  - Add path restriction guardrails
  - Implement overwrite protection
  - Add size limit enforcement
  - Add blocked extension filtering
  - Write unit tests

- [ ] **2.5 Update Tool**
  - Implement file editing operations (replace, insert, delete)
  - Add exact match validation
  - Add diff size limits
  - Implement line-based operations
  - Write unit tests

- [ ] **2.6 Search Tool**
  - Implement content search (grep-like)
  - Implement filename search (glob-like)
  - Add regex complexity limits
  - Add result count limits
  - Add timeout enforcement
  - Write unit tests

- [ ] **2.7 Agent Tool**
  - Implement subagent spawning
  - Implement recursion depth tracking (internal)
  - Return error when max depth exceeded
  - Add subagent timeout handling
  - Implement clean context creation for subagents
  - Write unit tests

### Phase 3: Backend Integration

- [ ] **3.1 Ollama Client**
  - Implement HTTP client for Ollama API
  - Support all configurable parameters
  - Implement streaming response handling
  - Add connection error handling and retries
  - Parse tool calls from responses
  - Write unit tests (with mocking)

- [ ] **3.2 Tool Call Processing**
  - Parse tool call requests from LLM responses
  - Route to appropriate tool implementation
  - Format tool results for LLM
  - Handle tool errors gracefully
  - Implement tool call loop

### Phase 4: Agent Runner

- [ ] **4.1 Agent Lifecycle**
  - Implement Agent class with state management
  - Load agent definition from Markdown file
  - Implement tool availability filtering
  - Add system prompt handling
  - Write unit tests

- [ ] **4.2 Main Execution Loop**
  - Implement message exchange loop
  - Integrate context manager
  - Integrate tool dispatcher
  - Add turn-by-turn persistence
  - Implement graceful shutdown

- [ ] **4.3 Hierarchical Spawning**
  - Implement internal depth tracking
  - Create fresh context for subagents
  - Pass initial prompt to subagent
  - Collect result from subagent
  - Add hierarchical logging
  - Write integration tests

### Phase 5: Polish and Documentation

- [ ] **5.1 Error Handling**
  - Define error codes and messages
  - Implement graceful error recovery
  - Add user-friendly error messages
  - Ensure all exceptions are handled

- [ ] **5.2 Documentation**
  - Write README with quick start guide
  - Document all configuration options
  - Write API documentation (Sphinx autodoc)
  - Create usage examples
  - Publish to ReadTheDocs

- [ ] **5.3 Testing**
  - Achieve high test coverage (>80%)
  - Add integration tests for full flows
  - Add guardrail enforcement tests
  - Add edge case tests

### Phase 6: Release Preparation

- [ ] **6.1 PyPI Package**
  - Finalize pyproject.toml metadata
  - Create release notes
  - Test installation from source distribution
  - Upload to TestPyPI
  - Upload to PyPI

- [ ] **6.2 Examples and Tutorials**
  - Create basic example
  - Create research workflow example
  - Write tutorial documentation

## Done

- [x] **1.4.1 Context Manager Integration**
  - Add ContextManager parameter to Agent.__init__
  - Replace self.messages with self.context
  - Update process() to use context methods
  - Add session persistence to CLI
  - Context now persists after each turn
  - Added --persist and --resume flags to demo_session.py
  - Fixed duplicate message bug (user and assistant added twice)
  - Fixed system message re-added on resume

- [x] **1.4 Context Manager**
  - Define context storage format (JSONL)
  - Implement Context class for conversation history
  - Implement context persistence (append to JSONL)
  - Add session ID management
  - Implement context isolation for subagents (clear method)
  - Fix atomic write implementation (file locking with fcntl)
  - Fix get_context() ordering (single sequence list)
  - See `reporting/1.4-context-manager/summary.md` for implementation summary

- [x] **1.3 Agent Definition Loader**
  - Implement Markdown file parser
  - Parse YAML frontmatter
  - Validate agent definitions against schema
  - Handle missing or invalid frontmatter
  - Create example agent definitions
  - See `analysis/agent-definition-loader.md` for design
  - See `reporting/1.3-agent-definition-loader/summary.md` for implementation summary

- [x] **1.2.5 Event-Driven Architecture Refactor**
  - Refactor Agent class to emit events instead of console output
  - Define event types (thinking_start, thinking_chunk, content_chunk, tool_call, etc.)
  - Create event emitter/callback system in library
  - Move all Rich console logic to __main__.py (application layer)
  - Ensure library is headless and reusable in different contexts
  - Write unit tests for event emission