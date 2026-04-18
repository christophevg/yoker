# TODO

## Backlog

### Phase 1: Core Infrastructure

- [x] **1.1 Project Setup**
  - Create Python package structure (src/yoker/)
  - Set up pyproject.toml with dependencies (following clitic template)
  - Configure development environment (ruff, mypy, pytest)
  - Create basic CLI entry point
  - Set up Sphinx documentation structure
  - Create .readthedocs.yaml

- [ ] **1.2 Configuration System**
  - Implement TOML config loader
  - Define configuration schema (dataclasses or pydantic)
  - Implement config validator (schema + semantic checks)
  - Add error handling for invalid configs
  - Create example configuration files

- [ ] **1.3 Agent Definition Loader**
  - Implement Markdown file parser
  - Parse YAML frontmatter
  - Validate agent definitions against schema
  - Handle missing or invalid frontmatter
  - Create example agent definitions

- [ ] **1.4 Context Manager**
  - Define context storage format (JSONL)
  - Implement Context class for conversation history
  - Implement context persistence (append to JSONL)
  - Add session ID management
  - Implement context isolation for subagents

- [ ] **1.5 Logging System**
  - Integrate structlog for structured logging
  - Add file and console handlers
  - Log tool calls and guardrail decisions
  - Add timing information for performance tracking

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

### Phase 1: Core Infrastructure

- [x] **1.1 Project Setup**
  - Create Python package structure (src/yoker/)
  - Set up pyproject.toml with dependencies (following clitic template)
  - Configure development environment (ruff, mypy, pytest)
  - Create basic CLI entry point
  - Set up Sphinx documentation structure
  - Create .readthedocs.yaml