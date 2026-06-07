# TODO

## P1: Critical Infrastructure

### Issue #16: Adopt Clevis for Configuration Management

- [ ] **16.1 Migrate Configuration System to Clevis**
  - Replace custom yoker/config/ module (~700 lines) with Clevis package
  - Migrate config/loader.py to Clevis loader pattern
  - Migrate config/schema.py to Clevis schema with frozen dataclasses
  - Migrate config/validator.py to Clevis validation hooks
  - Preserve custom validation via `__post_init__` on config classes
  - Support environment variables via TOML interpolation (Clevis native)
  - Implement configuration discovery: user < project < CLI (Clevis pattern)
  - Ensure minimal breaking changes to public config file format
  - **Estimated time:** 4-6 hours
  - **Priority:** P1 (Critical - blocks other work)
  - **See:** Issue #16
  - **Satisfies:** Configuration infrastructure modernization

## MVP: Package Plugin System (Issue #14)

**Goal:** Enable Python packages to provide tools and skills to yoker via `yoker --with <package>`

**Milestone:** Users can run `uvx --with pkgq yoker --with pkgq` and invoke `/pkgq:create`

### Phase 2: Skill System (Core)

**Goal:** Basic skill system that users can invoke immediately.

**Milestone:** Users can define skills in configured directories and invoke them via `/skill-name` commands or through agent tool calls.

- [x] **2.1 Skill Infrastructure** (2026-06-07)
  - Define `Skill` dataclass (Markdown + YAML frontmatter, similar to AgentDefinition)
  - Implement `SkillLoader` class (load from directory, parse frontmatter)
  - Implement skill context injection (user-level message with skill content)
  - Add skill discovery (`list_skills()` method)
  - Add skill registry to track loaded skills
  - Write unit tests for SkillLoader and skill injection
  - **Satisfies:** Skill invocation capability
  - **See:** PR #15

- [x] **2.2 Slash Command Support** (2026-06-07)
  - Add `/skill-name` command parsing in CLI (prompt_toolkit)
  - Parse `/skill-name` and `/skill-name args` formats
  - Lookup skill in SkillRegistry
  - Build skill context message using `format_invocation_block()`
  - Inject as user message into conversation
  - Handle skill not found error gracefully
  - Load skills from configured directories (yoker.toml `skills_dirs`)
  - Support `YOKER_SKILLS_PATH` environment variable
  - Write unit tests for command parsing and skill injection
  - **Depends on:** 2.1
  - **Estimated time:** 1-2 hours
  - **Satisfies:** User-facing skill invocation via CLI
  - **See:** PR #15

- [x] **2.3 Skill Tool for Agent Invocation** (2026-06-07)
  - Create `SkillTool` in `src/yoker/tools/skill.py`
  - Implement `execute(name: str, args: str = "")` method
  - Lookup skill in SkillRegistry
  - Return skill content via `format_invocation_block()`
  - Add SkillTool to default tool registry
  - Update PathGuardrail (not a filesystem tool)
  - Write unit tests for SkillTool
  - **Depends on:** 2.1
  - **Estimated time:** 1-2 hours
  - **Satisfies:** Agent can invoke skills dynamically
  - **See:** PR #15

### Phase 3: Package Plugin System

**Goal:** Enable Python packages to provide tools, skills, and agents to yoker.

**Milestone:** Packages can register components via `yoker` module namespace.

- [ ] **3.1 Package Plugin Discovery**
  - Import `{package}.yoker` module if present (using importlib)
  - Extract `TOOLS`, `SKILLS`, `AGENTS` lists from module
  - Handle graceful failure when package lacks yoker support
  - Implement namespace format: `{package}:{tool|skill|agent}` (e.g., `pkgq:find`)
  - Register discovered components with respective registries
  - Write unit tests for plugin discovery and registration
  - **Estimated time:** 2-3 hours
  - **Satisfies:** Package integration capability
  - **See:** Issue #14

- [ ] **3.2 CLI --with Argument**
  - Add `--with <package>` argument to `__main__.py`
  - Support multiple packages: `--with pkgq --with another`
  - Load packages before agent starts (in `main_async()`)
  - Handle package import errors with user-friendly messages
  - Update README.md with `--with` usage examples
  - Write unit tests for CLI argument handling
  - **Estimated time:** 1-2 hours
  - **Depends on:** 3.1
  - **Satisfies:** User-facing package integration

### Phase 5: Polish (Post-MVP)

- [ ] **5.1 Error Handling**
  - Define error codes and messages
  - Implement graceful error recovery
  - Add user-friendly error messages
  - Ensure all exceptions are handled
  - **Priority:** P2

- [ ] **5.2 Documentation**
  - Write README with quick start guide
  - Document all configuration options
  - Write API documentation (Sphinx autodoc)
  - Create usage examples
  - Publish to ReadTheDocs
  - **Priority:** P2

- [ ] **5.3 Testing**
  - Achieve high test coverage (>80%)
  - Add integration tests for full flows
  - Add guardrail enforcement tests
  - Add edge case tests
  - **Priority:** P2

### Phase 6: Release Preparation

- [ ] **6.1 PyPI Package**
  - Finalize pyproject.toml metadata
  - Create release notes
  - Test installation from source distribution
  - Upload to TestPyPI
  - Upload to PyPI
  - **Priority:** P3

- [ ] **6.2 Examples and Tutorials**
  - Create basic example
  - Create research workflow example
  - Write tutorial documentation
  - **Priority:** P3

---

## Future Work (Post-Release)

### Additional Tools (Phase 2 continued)

- [ ] **2.15 Python Tool**
  - Depends on: 2.14 Python Tool Research (complete)
  - Implement Python script execution functionality
  - Support virtual environment activation (uv, pyenv, venv)
  - Implement code validation guardrails (6-layer defense)
  - Define allowed operations and permissions
  - Add timeout and resource limits
  - Write unit tests
  - See `analysis/api-python-tool.md` for API design
  - **Priority:** P4

- [ ] **2.16 Pytest Tool**
  - Implement test execution functionality via pytest
  - Support running all tests, single test file, or selection
  - Add optional `activate_venv` parameter
  - Add optional `filter` parameter for grep pattern
  - Add optional `max_lines` parameter for output
  - Apply PathGuardrail for test file paths
  - Add timeout enforcement
  - Write unit tests
  - See `analysis/api-pytest-tool.md` for API design
  - **Priority:** P4

- [ ] **2.17 AskUserQuestion Tool**
  - Implement interactive question asking capability
  - Support choice-based questions with predefined options
  - Support open-ended questions
  - Add timeout and default value handling
  - Integrate with TUI for interactive sessions
  - Write unit tests
  - See `analysis/api-askuserquestion-tool.md` for API design
  - **Priority:** P4

- [ ] **2.18 Development Workflow Tools**
  - Implement RuffTool for linting/formatting operations
  - Implement MyPyTool for type checking
  - Implement ToxTool for multi-version testing
  - Implement MakeTool for Makefile target execution
  - Implement PyPiTool for package publishing
  - All tools use PathGuardrail for path validation
  - All tools have timeout enforcement
  - Write unit tests for each tool
  - See `analysis/api-dev-tools.md` for API design
  - **Priority:** P4

- [ ] **2.19 GitHub Tool**
  - Implement GitHub CLI wrapper tool for repository operations
  - Support read-only operations: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view
  - Use `gh` CLI with `--json` output for structured responses
  - Add operation allowlist guardrail
  - Add timeout enforcement (default 30 seconds)
  - Add result count limits (max 100 for lists)
  - Handle authentication errors gracefully
  - Subprocess execution with list args (no shell=True)
  - Write unit tests
  - See `analysis/api-github-tool.md` for API design
  - See `analysis/security-github-tool.md` for security analysis
  - **Priority:** P4

- [ ] **2.20 Add [start:stop] Arguments to Output-Heavy Tools**
  - Extend offset/limit pattern to tools with large outputs
  - Add `offset` and `limit` parameters to SearchTool results
  - Add `offset` and `limit` parameters to ListTool
  - Use consistent parameter naming (offset/limit)
  - Add result count metadata (total_matches, shown_matches, has_more)
  - Update tool descriptions
  - Write unit tests for pagination edge cases
  - **Priority:** P4

- [ ] **2.22 uv Tool**
  - Implement uv CLI wrapper tool for Python package management
  - Support common operations: install, sync, add, remove, run, venv
  - Add operation allowlist guardrail
  - Add timeout enforcement (default 60 seconds)
  - Use PathGuardrail for virtual environment paths
  - Handle virtual environment activation
  - Add result parsing for structured output
  - Subprocess execution with list args (no shell=True)
  - Write unit tests
  - See `analysis/api-uv-tool.md` for API design
  - **Priority:** P4

### Backend Integration (Phase 3)

- [ ] **3.4 Configurable Components Infrastructure**
  - Create base classes (SetMetadata, ComponentSet, ComponentLoader)
  - Implement resolution strategy (additional_dirs override set)
  - Create directory structure (prompts/sets/, skills/sets/, agents/sets/)
  - Implement metadata.toml parsing
  - Add configuration support to Config schema
  - Write unit tests
  - See `analysis/configurable-components-design.md` for design
  - **Priority:** P5

- [ ] **3.5 Prompt Sets Implementation**
  - Create prompts/sets/default/ with main.md, general-purpose.md, explore.md, plan.md
  - Create prompts/sets/minimal/ with shortened prompts
  - Create prompts/sets/detailed/ with verbose prompts
  - Implement PromptTemplate with variable rendering
  - Implement PromptLoader with set support
  - Integrate with Agent class
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** P5

- [ ] **3.6 Skills Sets Implementation**
  - Create skills/sets/default/ with core skills
  - Create skills/sets/minimal/ with essential skills
  - Implement Skill class with frontmatter parsing
  - Implement SkillLoader with set support
  - Integrate with SkillTool
  - Add skill discovery
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** P5

- [ ] **3.7 Agent Sets Implementation**
  - Create agents/sets/default/ with main.md, researcher.md, developer.md, reviewer.md
  - Create agents/sets/research/ with research-focused agents
  - Create agents/sets/development/ with development-focused agents
  - Implement AgentDefinition class with frontmatter parsing
  - Implement AgentLoader with set support
  - Integrate with existing agent.py
  - Add tool filtering per agent definition
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** P5

- [ ] **3.8 Context Reminders Implementation**
  - Implement ContextReminder protocol
  - Implement SkillsReminder (list available skills)
  - Implement ClaudeMdReminder (global + project CLAUDE.md)
  - Implement CurrentDateReminder
  - Implement WorkingDirectoryReminder
  - Implement GitContextReminder (branch, status)
  - Create ReminderComposer class
  - Integrate with Agent message building
  - Write unit tests
  - See `analysis/context-implementation-plan.md` for design
  - **Priority:** P5

- [ ] **3.9 Lazy Loading Implementation**
  - Implement LazyToolRegistry (load tools on first use)
  - Implement LazySkillLoader (load skills on demand)
  - Create core tools set (Read, List, Search, Existence)
  - Add tool caching after first load
  - Implement get_tools_for_request()
  - Add configuration for lazy vs eager loading
  - Write unit tests
  - **Depends on:** 3.4, 3.5, 3.6, 3.7
  - **Priority:** P5

### Future Features (Low Priority)

- [ ] **2.13.1 Local WebSearch Backend**
  - Implement LocalWebSearchBackend using DDGS library
  - Support multiple search backends (bing, brave, ddg, google)
  - Add rate limiting and error handling
  - Integrate with WebSearchTool via plugin system
  - Write unit tests
  - Note: OllamaWebSearchBackend is working, this is for offline-first
  - **Priority:** P6

- [ ] **2.13.2 Local WebFetch Backend**
  - Implement LocalWebFetchBackend using httpx + Trafilatura
  - Implement content extraction with Trafilatura
  - Add SSRF protection and DNS rebinding defense
  - Integrate with WebFetchTool via plugin system
  - Write unit tests
  - Note: OllamaWebFetchBackend is working, this is for full control
  - **Priority:** P6

- [ ] **R.1 Hermes Agent Comparison**
  - Research Hermes Agent architecture and capabilities
  - Compare Hermes to Yoker architecture
  - Compare Hermes to C3 Agentic Harness approach
  - Document findings in research folder
  - Identify features worth incorporating
  - **Priority:** P6

- [ ] **F.1 Multi-Agent Chat Room Demo**
  - Design multi-agent chat room architecture
  - Implement spawn command in TUI to spawn agent from folder
  - Create agent folder structure for spawned agents
  - Implement agent-to-agent communication protocol
  - Create demonstration scenario
  - **Priority:** P6

---

## Done

### Phase 1.7: Async-First Agent Architecture

- [x] **1.7.1 Extract AgentCore Class** (2026-05-23)
  - Created `src/yoker/base.py` with shared state and utilities
  - 51 tests, 98% coverage
  - See: `reporting/1.7.1-agentcore-extraction/summary.md`

- [x] **1.7.2 Async-Only Agent** (2026-05-23)
  - Renamed AsyncAgent to Agent (async-only)
  - All methods are async
  - 1047 tests passing

- [x] **1.7.3 Async Tool Execution** (2026-05-23)
  - All tools converted to async
  - Tool base class has abstract async method

- [x] **1.7.4 Async CLI Integration** (2026-05-23)
  - Created `main_async()` function
  - Uses `prompt_async()` for async input

- [x] **1.7.5 Update Documentation** (2026-05-25)
  - Updated docs/quickstart.md
  - Updated REQUIREMENTS.md

- [x] **1.7.7 Async Event Handler Support** (2026-05-25)
  - Updated ConsoleEventHandler for async operation
  - See: `reporting/1.7.7-async-event-handler/functional-review.md`

- [x] **1.7.8 Async Test Coverage** (2026-05-25)
  - 1047 tests passing, 82% coverage

- [x] **1.7.9 Documentation Updates** (2026-05-25)
  - Async-only architecture documented

- [x] **1.8 Config Auto-Discovery and Agent Definition Path** (2026-05-26)
  - Added `definition` field to `AgentsConfig`
  - Implemented `discover_config()` and `Config.discover()`
  - Environment variable support
  - PR: #13

### Phase 1.6: Documentation

- [x] **1.6.1 Update Documentation Folder**
  - Reviewed and updated all docs/
  - Added feature checkboxes and "Why Yoker?" section
  - See: `reporting/1.6.1-documentation/summary.md`

- [x] **1.6.2 Define Project Rationale**
  - Created rationale document
  - Identified gaps in existing solutions
  - See: `docs/rationale.md`

### Phase 1.5: UI/UX Fixes

- [x] **1.5.1 Remove Thinking Headers**
  - Removed "[thinking]" and "[response]" text headers
  - Used visual styling for thinking sections

- [x] **1.5.2 Fix Mouse Selection in Interactive Mode**
  - Set `mouse_support=False` in PromptSession
  - Text selection works in terminal output
  - See: `reporting/1.5.2-mouse-selection/summary.md`

- [x] **1.5.3 Update Demo Session Script**
  - Updated tool display format
  - Cyan color for tool name
  - Improved replay mode
  - See: `reporting/1.5.3-demo-session/functional-review.md`

- [x] **1.5.4 Event Logging System**
  - Created EventLogger class for JSONL logging
  - EventReplayAgent for full replay
  - See: `reporting/1.5.4-event-logging/summary.md`

- [x] **1.5.5 Show Write/Update Tool Content in CLI** (2026-05-05)
  - Added ToolContentEvent to event types
  - Added ContentDisplayConfig to configuration
  - See: `reporting/1.5.5-write-update-display/consensus.md`

- [x] **1.5.6 Complete Tool Content Display** (2026-05-16)
  - Agent emits ToolContentEvent
  - ConsoleEventHandler displays tool content
  - 47 tests converted from stubs
  - See: `reporting/1.5.6-tool-content-display/summary.md`

### Phase 1: Core Infrastructure

- [x] **1.1 Project Setup**
  - Created Python package structure
  - Set up pyproject.toml
  - Configured development environment

- [x] **1.2 Configuration System**
  - Implemented TOML config loader
  - Defined configuration schema
  - Created example configurations

- [x] **1.3 Agent Definition Loader**
  - Implemented Markdown file parser
  - Parsed YAML frontmatter
  - Created example agent definitions
  - See: `reporting/1.3-agent-definition-loader/summary.md`

- [x] **1.5 Logging System**
  - Integrated structlog for structured logging
  - See: `reporting/1.5-logging-system/summary.md`

### Phase 2: Tool Implementation (Core Tools)

- [x] **2.1 Tool Base Framework**
  - Defined Tool abstract base class
  - Defined ToolResult and ValidationResult types
  - Implemented tool registry

- [x] **2.1.5 Shared PathGuardrail Implementation**
  - Implemented PathGuardrail with config permissions
  - Path traversal prevention, symlinks, blocked patterns
  - See: `analysis/security-list-tool.md`

- [x] **2.2 List Tool**
  - Implemented directory listing
  - Path restriction guardrails
  - See: `analysis/api-list-tool.md`

- [x] **2.3 Read Tool**
  - Implemented file reading
  - Path restriction guardrails
  - See: `reporting/2.3-read-tool/summary.md`

- [x] **2.4 Write Tool**
  - Implemented file writing
  - Overwrite protection, size limits
  - See: `reporting/2.4-write-tool/summary.md`

- [x] **2.5 Update Tool**
  - Implemented file editing operations
  - Exact match validation, diff size limits
  - See: `reporting/2.5-update-tool/summary.md`

- [x] **2.6 Search Tool**
  - Implemented content search (grep-like)
  - Implemented filename search (glob-like)
  - Regex complexity limits, timeout enforcement
  - See: `reporting/2.6-search-tool/summary.md`

- [x] **2.7 Agent Tool**
  - Implemented subagent spawning
  - Recursion depth tracking, timeout handling
  - See: `reporting/2.7-agent-tool/consensus.md`

- [x] **2.8 File Existence Tool**
  - Implemented file/folder existence check
  - Path restriction guardrails
  - See: `reporting/2.8-existence-tool/summary.md`

- [x] **2.9 Folder Creation Tool**
  - Implemented folder creation (mkdir -p)
  - Path restriction guardrails
  - See: `reporting/2.9-mkdir-tool/summary.md`

- [x] **2.10 Git Tool**
  - Implemented Git operations (status, log, diff, branch, show)
  - Permission handlers for write operations
  - Command sanitization
  - See: `reporting/2.10-git-tool/summary.md`

- [x] **2.11 WebSearch and WebFetch Tools Research**
  - Recommended custom implementation
  - See: `analysis/websearch-webfetch-research.md`

- [x] **2.12 WebSearch Tool**
  - Implemented WebSearchTool with OllamaWebSearchBackend
  - WebGuardrail with SSRF protection
  - See: `reporting/2.12-websearch-tool/summary.md`

- [x] **2.12 WebFetch Tool**
  - Implemented WebFetchTool with OllamaWebFetchBackend
  - Domain whitelist/blacklist
  - See: `reporting/2.12-webfetch-tool/summary.md`

- [x] **2.14 Python Tool Research**
  - Recommended subprocess isolation + AST validation
  - 6-layer defense model
  - See: `research/2026-05-05-python-execution-safety/README.md`

### Phase 3: Backend Integration

- [x] **3.1 Ollama Client**
  - Implemented HTTP client for Ollama API
  - Streaming response handling
  - Supports local Ollama and ollama.com with API key

- [x] **3.2 Tool Call Processing**
  - Parse tool call requests from LLM responses
  - Route to appropriate tool implementation
  - Tool call loop with deduplication

- [x] **3.3 Context Management Research**
  - Analyzed logged sessions for context patterns
  - Documented sub-agent context isolation
  - See: `analysis/context-management-research.md`

### Phase 4: Agent Runner

- [x] **4.1 Agent Lifecycle**
  - Implemented Agent class with state management
  - Load agent definition from Markdown file

- [x] **4.2 Main Execution Loop**
  - Implemented message exchange loop
  - Context management, tool call loop

- [x] **4.3 Hierarchical Spawning**
  - Implemented internal depth tracking
  - Fresh context for subagents
  - See: AgentTool implementation

### Standard Project Setup

- [x] **migrate-to-hatchling** (2026-04-29)
  - Migrated from setuptools to hatchling
  - See: `reporting/migrate-to-hatchling/summary.md`

- [x] **migrate-to-uv** (2026-04-30)
  - Migrated from pyenv virtualenv to uv
  - Updated Makefile and CI workflow
  - See: `analysis/uv-migration-checklist.md`

### Issues Completed

- [x] **Issue #7: Config Auto-Discovery and Agent Definition Path** (2026-05-26)
  - Config auto-discovery, environment variables
  - PR: #13

- [x] **Issue #10: Add Type Exports** (2026-05-25)
  - Added AgentDefinition and load_agent_definition exports
  - PR: #12

- [x] **Issue #9: Fix ~ in Storage Path** (2026-05-25)
  - Fixed tilde expansion bug
  - PR: #11