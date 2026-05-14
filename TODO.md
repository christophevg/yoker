# TODO

## Backlog

### Standard Project Setup

- [x] **migrate-to-hatchling** (2026-04-29)
  - Migrate from setuptools.build_meta to hatchling
  - Update pyproject.toml: change build-backend to "hatchling.build"
  - Replace `[tool.setuptools.*]` sections with `[tool.hatch.build.*]`
  - Update packages config: `[tool.hatch.build.targets.wheel] packages = ["src/yoker"]`
  - Verify all tool configs remain in pyproject.toml
  - Acceptance: `pip install -e ".[dev]"` works, `make test` passes, `python -m build` succeeds
  - See: c3 skill `python-project` for hatchling configuration
  - See: `reporting/migrate-to-hatchling/summary.md` for implementation summary

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

- [x] **1.5.5 Show Write/Update Tool Content in CLI** (2026-05-05)
  - Add ToolContentEvent to event types
  - Add ContentDisplayConfig to configuration schema (verbosity, max_content_lines, show_diff_for_updates)
  - Add content_metadata field to ToolResult
  - Update WriteTool to populate content_metadata (new file, overwrite, binary detection)
  - Update UpdateTool to populate content_metadata (diff generation for replace, context for insert/delete)
  - Agent emits ToolContentEvent when metadata present
  - ConsoleEventHandler displays content based on verbosity (silent/summary/content)
  - Visual consistency with Read tool (cyan color, filename only)
  - Write unit tests (46 tests)
  - Stub tests for agent/handler (47 tests - need implementation)
  - See `analysis/api-write-update-display.md` for API design
  - See `analysis/ux-write-update-display.md` for UX design
  - See `reporting/1.5.5-write-update-display/consensus.md` for consensus

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

### Future Features (Low Priority)

- [ ] **2.13.1 Local WebSearch Backend** (Deferred: Ollama backend working)
  - Implement LocalWebSearchBackend using DDGS library
  - Support multiple search backends (bing, brave, ddg, google)
  - Add rate limiting and error handling
  - Integrate with WebSearchTool via plugin system
  - Write unit tests
  - Note: OllamaWebSearchBackend is working, this is for offline-first operation

- [ ] **2.13.2 Local WebFetch Backend** (Deferred: Ollama backend working)
  - Implement LocalWebFetchBackend using httpx + Trafilatura
  - Implement content extraction with Trafilatura
  - Add SSRF protection and DNS rebinding defense
  - Integrate with WebFetchTool via plugin system
  - Write unit tests
  - Note: OllamaWebFetchBackend is working, this is for full control over SSRF/redirects

- [ ] **R.1 Hermes Agent Comparison**
  - Research Hermes Agent architecture and capabilities
  - Compare Hermes to Yoker architecture
  - Compare Hermes to C3 Agentic Harness approach
  - Compare Hermes to Assistant pattern
  - Document findings in research folder
  - Identify features worth incorporating

- [ ] **F.1 Multi-Agent Chat Room Demo**
  - Design multi-agent chat room architecture
  - Implement spawn command in TUI to spawn agent from folder
  - Create agent folder structure for spawned agents
  - Implement agent-to-agent communication protocol
  - Create demonstration scenario

### Phase 2: Tool Implementation

- [x] **2.1 Tool Base Framework**
  - Define Tool abstract base class
  - Define ToolResult and ValidationResult types
  - Implement tool registry
  - Create guardrail enforcer interface

- [x] **2.1.5 Shared PathGuardrail Implementation**
  - Implement PathGuardrail concrete class using config permissions
  - Resolve paths with os.path.realpath() to prevent traversal
  - Validate paths against config.permissions.filesystem_paths
  - Add blocked pattern matching (regex)
  - Add file size limit enforcement
  - Add extension filtering for read tool
  - Wire guardrail validation into Agent.process() before tool.execute()
  - Add structured logging for allow/block decisions
  - Harden ReadTool to use the guardrail
  - Write unit tests for traversal, symlinks, blocked patterns
  - See analysis/security-list-tool.md for threat model
  - See analysis/api-list-tool.md for API design

- [x] **2.2 List Tool**
  - Implement directory listing functionality
  - Add path restriction guardrails
  - Add max_depth and max_entries limits
  - Add pattern filtering support
  - Write unit tests
  - API design: `analysis/api-list-tool.md`
    - Tool name: `list`, schema follows ReadTool patterns
    - Parameters: `path` (required), `max_depth` (default 1), `max_entries` (default 1000), `pattern` (optional glob)
    - Returns tree-formatted text with directory/file counts
    - Limits are self-enforced (clamped); guardrails focus on path security
    - PathGuardrail should be shared with ReadTool (task 2.3) and other filesystem tools
    - Update `src/yoker/tools/__init__.py` to register ListTool in default registry
  - **Security**: Must use shared `PathGuardrail` (see `analysis/security-list-tool.md`)
  - **Security**: Do not follow symlinks during recursion (`followlinks=False`)
  - **Security**: Resolve and validate path against `config.permissions.filesystem_paths`
  - **Security**: Enforce `max_depth` and `max_entries` with early termination
  - **Security**: Add tests for path traversal (`../../../etc`), symlink bypass, and blocked patterns

- [x] **2.3 Read Tool**
  - Implement file reading functionality
  - Add path restriction guardrails
  - Add file extension filtering
  - Add size limit enforcement
  - Add blocked pattern matching (e.g., .env files)
  - Write unit tests
  - **Security**: Must use shared `PathGuardrail` (see `analysis/security-list-tool.md`)
  - **Security**: Current `ReadTool` is critically vulnerable (zero validation); harden via guardrail
  - See `reporting/2.3-read-tool/summary.md` for implementation summary

- [x] **2.4 Write Tool**
  - Implement file writing functionality
  - Add path restriction guardrails
  - Implement overwrite protection
  - Add size limit enforcement
  - Add blocked extension filtering
  - Write unit tests
  - See `reporting/2.4-write-tool/summary.md` for implementation summary

- [x] **2.5 Update Tool**
  - Implement file editing operations (replace, insert, delete)
  - Add exact match validation
  - Add diff size limits
  - Implement line-based operations
  - Write unit tests
  - See `reporting/2.5-update-tool/summary.md` for implementation summary

- [x] **2.6 Search Tool**
  - Implement content search (grep-like)
  - Implement filename search (glob-like)
  - Add regex complexity limits
  - Add result count limits
  - Add timeout enforcement
  - Write unit tests
  - See `analysis/api-search-tool.md` for API design
  - See `analysis/security-search-tool.md` for security analysis
  - See `reporting/2.6-search-tool/summary.md` for implementation summary

- [x] **2.7 Agent Tool**
  - Implement subagent spawning
  - Implement recursion depth tracking (internal)
  - Return error when max depth exceeded
  - Add subagent timeout handling
  - Implement clean context creation for subagents
  - Write unit tests
  - See `analysis/api-agent-tool.md` for API design
  - See `analysis/security-agent-tool.md` for security analysis
  - See `reporting/2.7-agent-tool/consensus.md` for consensus report

- [x] **2.8 File Existence Tool**
  - Implement file existence check functionality
  - Implement folder existence check functionality
  - Add path restriction guardrails (use shared PathGuardrail)
  - Return structured result with exists, type, and path
  - Symlink rejection for security
  - Generic error messages (security hardening)
  - Write unit tests (28 test cases)
  - See `analysis/api-existence-tool.md` for API design
  - See `analysis/security-existence-tool.md` for security analysis
  - See `reporting/2.8-existence-tool/summary.md` for implementation summary

- [ ] **2.15 Python Tool**
  - Depends on: 2.14 Python Tool Research
  - Implement Python script execution functionality
  - Support virtual environment activation (uv, pyenv, venv)
  - Implement code validation guardrails based on research
  - Define allowed operations and permissions
  - Add timeout and resource limits
  - Write unit tests
  - See `analysis/api-python-tool.md` for API design (to be created)

- [ ] **2.16 Pytest Tool**
  - Implement test execution functionality via pytest
  - Support running all tests, a single test file, or a selection of tests
  - Add optional `activate_venv` parameter to activate pyenv virtual environment before running
  - Add optional `filter` parameter for simple grep pattern filtering of results
  - Add optional `max_lines` parameter to return only the top N lines of output
  - Apply concise output format (summary-focused, not verbose)
  - Add path restriction guardrails (use shared PathGuardrail for test file paths)
  - Add timeout enforcement for long-running test suites
  - Write unit tests
  - See `analysis/api-pytest-tool.md` for API design (to be created)

- [ ] **2.17 AskUserQuestion Tool**
  - Implement interactive question asking capability
  - Support choice-based questions with predefined options
  - Support open-ended questions
  - Add timeout and default value handling
  - Integrate with TUI for interactive sessions
  - Write unit tests
  - See `analysis/api-askuserquestion-tool.md` for API design (to be created)

- [ ] **2.18 Development Workflow Tools**
  - Implement RuffTool for linting/formatting operations
  - Implement MyPyTool for type checking
  - Implement ToxTool for multi-version testing
  - Implement MakeTool for Makefile target execution
  - Implement PyPiTool for package publishing
  - All tools should use PathGuardrail for path validation
  - All tools should have timeout enforcement
  - Write unit tests for each tool
  - See `analysis/api-dev-tools.md` for API design (to be created)

- [ ] **2.19 GitHub Tool**
  - Implement GitHub CLI wrapper tool for repository operations
  - Support read-only operations: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view
  - Use `gh` CLI with `--json` output for structured responses
  - Add operation allowlist guardrail (config.controls allowed_operations)
  - Add timeout enforcement (default 30 seconds)
  - Add result count limits (max 100 for lists)
  - Handle authentication errors (gh not installed, not authenticated)
  - Handle rate limit errors gracefully
  - Subprocess execution with list args (no shell=True for security)
  - Write unit tests (mock subprocess, test injection attempts)
  - See `analysis/api-github-tool.md` for API design
  - See `analysis/security-github-tool.md` for security analysis
  - **Security**: MVP excludes destructive operations (pr_merge, branch_delete, issue_create)
  - **Security**: Phase 2 will add write operations with explicit configuration

- [ ] **2.20 Add [start:stop] Arguments to Output-Heavy Tools**
  - Extend offset/limit pattern to tools that return large outputs
  - Add `offset` and `limit` parameters to SearchTool results
  - Add `offset` and `limit` parameters to ListTool (for deep directory trees)
  - Add `offset` and `limit` to any tool with paginated results
  - Use consistent parameter naming across tools (offset/limit, not start/stop)
  - Add result count metadata (total_matches, shown_matches, has_more)
  - Update tool descriptions to document pagination parameters
  - Write unit tests for pagination edge cases
  - See existing ReadTool implementation as reference

- [ ] **2.21 Skill Tool**
  - Research C3 skill system integration and invocation patterns
  - Implement SkillTool for invoking configured skills from agents
  - Support skill discovery from skill directories
  - Pass context and parameters to skill execution
  - Handle skill errors gracefully with meaningful messages
  - Add skill availability guardrails (configurable allowed skills per agent)
  - Write unit tests
  - See `analysis/api-skill-tool.md` for API design (to be created)
  - See `analysis/skill-system-integration.md` for integration design (to be created)

- [ ] **2.22 uv Tool**
  - Implement uv CLI wrapper tool for Python package management
  - Support common operations: install, sync, add, remove, run, venv
  - Add operation allowlist guardrail (config.controls allowed_operations)
  - Add timeout enforcement (default 60 seconds for operations)
  - Use PathGuardrail for virtual environment paths
  - Handle virtual environment activation within tool execution
  - Add result parsing for structured output (dependencies installed, errors)
  - Handle common errors (uv not installed, lock file conflicts)
  - Subprocess execution with list args (no shell=True for security)
  - Write unit tests
  - See `analysis/api-uv-tool.md` for API design (to be created)

### Phase 3: Backend Integration

- [x] **3.1 Ollama Client** (2026-05-06)
  - Implement HTTP client for Ollama API
  - Support all configurable parameters
  - Implement streaming response handling
  - Add connection error handling and retries
  - Parse tool calls from responses
  - Write unit tests (with mocking)
  - **Note**: Implemented directly in Agent class (not separate backend module)
  - Supports both local Ollama and ollama.com with API key authentication

- [x] **3.2 Tool Call Processing** (2026-05-06)
  - Parse tool call requests from LLM responses
  - Route to appropriate tool implementation
  - Format tool results for LLM
  - Handle tool errors gracefully
  - Implement tool call loop
  - **Note**: Implemented in Agent.process() method with deduplication and error handling

- [x] **3.3 Context Management Research** (2026-05-14)
  - Analyze logged sessions to identify context patterns
  - Reverse engineer context content from JSONL event logs
  - Identify system prompt construction requirements
  - Document prompt construction patterns for sub-agents
  - Research skill context injection requirements
  - Define context inheritance vs. isolation rules
  - Create analysis document with findings
  - Prerequisite for: Phase 4 (Agent Runner)
  - **Findings**: Sub-agents get fresh context (no history), filtered tools (28 vs 37), specialized system prompts (3KB vs 27KB). Skills are loaded on-demand via Skill tool.
  - See `analysis/context-management-research.md` for full analysis

- [ ] **3.4 Configurable Components Infrastructure**
  - Create base classes for component sets (SetMetadata, ComponentSet, ComponentLoader)
  - Implement resolution strategy (additional_dirs override set)
  - Create directory structure (prompts/sets/, skills/sets/, agents/sets/)
  - Implement metadata.toml parsing
  - Add configuration support to Config schema
  - Write unit tests for loader classes
  - See `analysis/configurable-components-design.md` for design
  - See `analysis/component-resolution-strategy.md` for resolution strategy

- [ ] **3.5 Prompt Sets Implementation**
  - Create prompts/sets/default/ with main.md, general-purpose.md, explore.md, plan.md
  - Create prompts/sets/minimal/ with shortened prompts
  - Create prompts/sets/detailed/ with verbose prompts
  - Implement PromptTemplate with variable rendering
  - Implement PromptLoader with set support
  - Integrate with Agent class (get_system_prompt)
  - Add prompt variants support (concise, verbose)
  - Write unit tests for prompt loading
  - See `analysis/prompt-sets-design.md` for design

- [ ] **3.6 Skills Sets Implementation**
  - Create skills/sets/default/ with core skills (git-commit, project-status, bug-fixing)
  - Create skills/sets/minimal/ with essential skills only
  - Implement Skill class with frontmatter parsing
  - Implement SkillLoader with set support
  - Integrate with SkillTool (on-demand loading)
  - Add skill discovery (list available skills)
  - Add skill invocation from agent
  - Write unit tests for skill loading
  - See `analysis/configurable-components-design.md` for design

- [ ] **3.7 Agent Sets Implementation**
  - Create agents/sets/default/ with main.md, researcher.md, developer.md, reviewer.md
  - Create agents/sets/research/ with research-focused agents
  - Create agents/sets/development/ with development-focused agents
  - Implement AgentDefinition class with frontmatter parsing
  - Implement AgentLoader with set support
  - Integrate with existing agent.py
  - Add tool filtering per agent definition
  - Add model configuration per agent
  - Write unit tests for agent loading
  - See `analysis/configurable-components-design.md` for design

- [ ] **3.8 Context Reminders Implementation**
  - Implement ContextReminder protocol
  - Implement SkillsReminder (list available skills)
  - Implement ClaudeMdReminder (global + project CLAUDE.md)
  - Implement CurrentDateReminder
  - Implement WorkingDirectoryReminder
  - Implement GitContextReminder (branch, status)
  - Create ReminderComposer class
  - Integrate with Agent message building
  - Write unit tests for reminders
  - See `analysis/context-implementation-plan.md` for design

- [ ] **3.9 Lazy Loading Implementation**
  - Implement LazyToolRegistry (load tools on first use)
  - Implement LazySkillLoader (load skills on demand)
  - Create core tools set (Read, List, Search, Existence)
  - Add tool caching after first load
  - Add skill discovery without loading
  - Implement get_tools_for_request() (core + loaded)
  - Add configuration for lazy vs eager loading
  - Write unit tests for lazy loading
  - See `analysis/context-implementation-plan.md` for design

### Phase 4: Agent Runner

- [x] **4.1 Agent Lifecycle** (2026-05-06)
  - Implement Agent class with state management
  - Load agent definition from Markdown file
  - Implement tool availability filtering
  - Add system prompt handling
  - Write unit tests
  - **Note**: Implemented in agent.py with full state management, definition loading, and tool filtering

- [x] **4.2 Main Execution Loop** (2026-05-06)
  - Implement message exchange loop
  - Integrate context manager
  - Integrate tool dispatcher
  - Add turn-by-turn persistence
  - Implement graceful shutdown
  - **Note**: Implemented in Agent.process() with streaming, context management, and tool call loop

- [x] **4.3 Hierarchical Spawning** (2026-05-06)
  - Implement internal depth tracking
  - Create fresh context for subagents
  - Pass initial prompt to subagent
  - Collect result from subagent
  - Add hierarchical logging
  - Write integration tests
  - **Note**: Implemented in AgentTool with depth tracking, timeout handling, and context isolation

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

- [x] **2.14 Python Tool Research** (2026-05-05)
  - Research safe Python code execution approaches (subprocess, sandbox, AST validation)
  - Investigate uv integration for virtual environment management
  - Define security model for code execution (what operations are allowed)
  - Document guardrails and permissions approach
  - Research pyenv environment activation integration
  - Recommend implementation strategy with justification
  - **Recommendation**: Subprocess isolation + AST validation + Resource limits (6-layer defense)
  - **Key insight**: RestrictedPython is NOT a sandbox; defense-in-depth is required
  - See `research/2026-05-05-python-execution-safety/README.md` for research findings
  - See `analysis/api-python-tool.md` for API design

- [x] **1.5.5 Show Write/Update Tool Content in CLI** (2026-05-05)
  - Add ToolContentEvent to event types
  - Add ContentDisplayConfig to configuration schema (verbosity, max_content_lines, show_diff_for_updates)
  - Add content_metadata field to ToolResult
  - Update WriteTool to populate content_metadata (new file, overwrite, binary detection)
  - Update UpdateTool to populate content_metadata (diff generation for replace, context for insert/delete)
  - Agent emits ToolContentEvent when metadata present
  - ConsoleEventHandler displays content based on verbosity (silent/summary/content)
  - Visual consistency with Read tool (cyan color, filename only)
  - Write unit tests (46 tests)
  - Stub tests for agent/handler (47 tests - need implementation)
  - See `analysis/api-write-update-display.md` for API design
  - See `analysis/ux-write-update-display.md` for UX design
  - See `reporting/1.5.5-write-update-display/consensus.md` for consensus

- [x] **2.12 WebFetch Tool** (2026-05-04)
  - Design pluggable backend architecture for fetch implementations
  - Create WebFetchBackend abstract interface (Protocol-based)
  - Implement OllamaWebFetchBackend (uses Ollama's native web_fetch tool)
  - Create WebFetchTool with backend selection via configuration
  - Extend WebGuardrail with validate_url() for SSRF protection
  - Add domain whitelist/blacklist with wildcard matching
  - Add HTTPS enforcement and private IP blocking
  - Write unit tests (83 tests)
  - All acceptance criteria verified:
    - `make test` (828 tests) ✓
    - `make lint` ✓
    - `make typecheck` ✓
  - See `analysis/api-webfetch-tool.md` for API design
  - See `analysis/security-webfetch-tool.md` for security analysis
  - See `reporting/2.12-webfetch-tool/summary.md` for implementation summary

- [x] **2.12 WebSearch Tool** (2026-05-04)
  - Design pluggable backend architecture for search implementations
  - Create WebSearchBackend abstract interface (Protocol-based)
  - Implement OllamaWebSearchBackend (uses Ollama's native web_search tool)
  - Create WebSearchTool with backend selection via configuration
  - Implement WebGuardrail with comprehensive SSRF protection
  - Add domain whitelist/blacklist with wildcard matching
  - Add query sanitization for sensitive patterns
  - Add rate limiting (requests/min, requests/hour)
  - Write unit tests (110 tests)
  - All acceptance criteria verified:
    - `make test` (746 tests) ✓
    - `make lint` ✓
    - `make typecheck` ✓
  - See `analysis/api-websearch-tool.md` for API design
  - See `analysis/security-websearch-tool.md` for security analysis
  - See `reporting/2.12-websearch-tool/summary.md` for implementation summary

- [x] **2.11 WebSearch and WebFetch Tools Research** (2026-05-04)
  - Research Ollama's WebSearch/WebFetch implementation capabilities
  - Compare Ollama approach with own HTTP client implementation
  - Document trade-offs: control vs. dependency, feature parity, maintenance
  - Evaluate guardrail implementation options for each approach
  - Recommend implementation strategy with justification
  - **Recommendation**: Custom implementation (DDGS for search, httpx+Trafilatura for fetch)
  - **Key Guardrails**: SSRF protection, domain whitelist, content limits, timeout
  - See `analysis/websearch-webfetch-research.md` for analysis summary
  - See `research/2026-05-04-websearch-webfetch-tools/` for full research

- [x] **2.10 Git Tool** (2026-05-04)
  - Implement Git operations (status, log, diff, branch, show) - read-only
  - Implement permission-required operations (commit, push)
  - Add permission handlers (allow, block, ask_user modes)
  - Implement command sanitization to prevent injection
  - Add dangerous option blocking (--exec, --upload-pack, etc.)
  - Add credential redaction in output
  - Integrate with PathGuardrail for repository path validation
  - Write unit tests
  - All acceptance criteria verified:
    - `make test` passes
    - `make lint` passes
    - `make typecheck` passes
  - See `analysis/api-git-tool.md` for API design
  - See `analysis/security-git-tool.md` for security analysis
  - See `reporting/2.10-git-tool/summary.md` for implementation summary

- [x] **2.9 Folder Creation Tool** (2026-04-30)
  - Implement folder creation functionality (mkdir -p equivalent)
  - Add path restriction guardrails (use shared PathGuardrail)
  - Support recursive parent creation
  - Handle existing folder gracefully (no error if already exists)
  - Depth limit enforcement (max 20 levels from allowed root)
  - Generic error messages for security
  - Write unit tests (56 tests)
  - All acceptance criteria verified:
    - `make test` (572 tests) ✓
    - `make lint` ✓
    - `make typecheck` ✓
  - See `analysis/api-folder-creation-tool.md` for API design
  - See `analysis/security-folder-creation-tool.md` for security analysis
  - See `reporting/2.9-mkdir-tool/summary.md` for implementation summary

- [x] **migrate-to-uv** (2026-04-30)
  - Migrated from pyenv virtualenv to uv for unified dependency management
  - Updated `.python-version` to contain version number only (3.11)
  - Refactored Makefile to use `uv run` for all commands
  - Updated CI workflow to use `astral-sh/setup-uv@v5`
  - Updated documentation (README.md, CLAUDE.md)
  - All acceptance criteria verified:
    - `make test` (516 tests) ✓
    - `make lint` ✓
    - `make build` ✓
    - Interactive mode works ✓
  - See `analysis/uv-migration-checklist.md` for migration checklist
  - Commit: 5c05f71

- [x] **2.8 File Existence Tool** (2026-04-29)
  - Implement file existence check functionality
  - Implement folder existence check functionality
  - Add path restriction guardrails (use shared PathGuardrail)
  - Return structured result with exists, type, and path
  - Symlink rejection for security
  - Generic error messages (security hardening)
  - Expanded default blocked patterns in config
  - Write unit tests (28 test cases, including error handling)
  - All acceptance criteria verified:
    - `make lint` ✓
    - `make typecheck` ✓
    - `make test` (516 tests) ✓
  - See `analysis/api-existence-tool.md` for API design
  - See `analysis/security-existence-tool.md` for security analysis
  - See `reporting/2.8-existence-tool/summary.md` for implementation summary

- [x] **migrate-to-hatchling** (2026-04-29)
  - Migrate from setuptools.build_meta to hatchling
  - Updated pyproject.toml: build-backend to "hatchling.build"
  - Replaced `[tool.setuptools.*]` sections with `[tool.hatch.build.*]`
  - Updated license format to PEP 639: `license = {text = "MIT"}`
  - All acceptance criteria verified:
    - `pip install -e ".[dev]"` ✓
    - `make test` (487 tests) ✓
    - `python -m build` ✓
    - `twine check dist/*` ✓
  - See `reporting/migrate-to-hatchling/summary.md` for implementation summary

- [x] **2.6 Search Tool**
  - Implement content search (grep-like)
  - Implement filename search (glob-like)
  - Add regex complexity limits (ReDoS prevention)
  - Add result count limits (max_results parameter)
  - Add timeout enforcement (time.monotonic tracking)
  - Write unit tests (comprehensive error handling tests)
  - See `analysis/api-search-tool.md` for API design
  - See `analysis/security-search-tool.md` for security analysis
  - See `reporting/2.6-search-tool/summary.md` for implementation summary

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
