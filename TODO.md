# TODO

## Active: UI Separation Migration (Complete)

**Status:** Completed 2026-06-15 via PR #27

**Goal:** Separate UI from Agent in the yoker codebase, establishing a clean boundary where the Agent layer is purely event-driven and the UI layer handles all presentation.

**Approach:** Clean break - no backward compatibility, no deprecation shims.

**Related Analysis:**
- [Overview and Architecture](analysis/ui-separation-overview.md)
- [IO Operations Catalog](analysis/ui-separation-io-catalog.md)
- [Error Handling Strategy](analysis/ui-separation-errors.md)
- [Agent Module Refactoring](analysis/ui-separation-agent-module.md)
- [UI Handler Design](analysis/ui-separation-ui-design.md)
- [Migration Plan](analysis/ui-separation-migration.md)

**Outcome:** All migration phases complete (UI-001 through UI-055). PR #27 merged the final documentation and examples.

---


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

- [x] **3.2 CLI --with Argument** (2026-06-15)
  - Add `--with <package>` argument to `__main__.py`
  - Support multiple packages: `--with pkgq --with another`
  - Load packages before agent starts (in `main()`)
  - Handle package import errors with user-friendly messages
  - Update README.md with `--with` usage examples
  - Write unit tests for CLI argument handling
  - **Depends on:** 3.1
  - **Satisfies:** User-facing package integration

### Phase 5: Polish (Post-MVP)

- [x] **5.1 Error Handling** (2026-06-15)
  - Define error codes and messages
  - Implement graceful error recovery
  - Add user-friendly error messages
  - Ensure all exceptions are handled
  - **Priority:** P2

- [x] **5.2 Documentation** (2026-06-15)
  - Write README with quick start guide
  - Document all configuration options
  - Write API documentation (Sphinx autodoc)
  - Create usage examples
  - Publish to ReadTheDocs
  - **Priority:** P2

- [x] **5.3 Testing** (2026-06-15)
  - Achieve high test coverage (>80%)
  - Add integration tests for full flows
  - Add guardrail enforcement tests
  - Add edge case tests
  - **Priority:** P2

### Phase 6: Release Preparation

- [ ] **6.1 PyPI Package**
  - [x] Create release notes (HISTORY.md updated for v0.5.0)
  - [ ] Finalize pyproject.toml metadata
  - [ ] Test installation from source distribution
  - [ ] Upload to TestPyPI
  - [ ] Upload to PyPI
  - **Note:** The actual PyPI/TestPyPI upload step cannot be performed by an agent because it requires release manager credentials and authorization. This task remains open pending release manager execution.
  - **Priority:** P3

- [x] **6.2 Examples and Tutorials** (2026-06-15)
  - Create basic example
  - Create research workflow example
  - Write tutorial documentation
  - **Priority:** P3

---

## Launch Preparation: Public Announcement (2026-06-17)

**Source:** Email from Christophe, 2026-06-17
**Goal:** Prepare marketing materials and dedicated website for Yoker's public announcement.
**USP:** "Add LLM capabilities to your Python apps and modules without worrying about the agentic foundations. Agentic Functions."

### Social Media Launch Plan

- [ ] **L.1 Storyboard of Publications**
  - Define ideal sequence to announce and introduce Yoker on social media
  - Predominantly LinkedIn and Instagram
  - Refer to the website in all publications
  - **Priority:** P1

- [ ] **L.2 Publication Timeline**
  - Prepare timeline for releasing articles, posts
  - Investigate: how many posts?
  - Investigate: how long between posts?
  - Investigate: repeating schedule?
  - **Depends on:** L.1
  - **Priority:** P1

### Website Research

- [ ] **L.3 Website Structure Research**
  - Research dedicated website structure for Yoker
  - **Priority:** P1

- [ ] **L.4 Website Examples and Framework Comparisons**
  - Research examples from other frameworks
  - Create comparison with other agent frameworks
  - **Priority:** P1

- [ ] **L.5 Strong Front Page**
  - Research and design a strong front page example
  - **Priority:** P1

- [ ] **L.6 Clear Getting Started Guide**
  - Research and design clear getting started guide
  - **Priority:** P1

- [ ] **L.7 Best Practices Research**
  - Learn from good examples, find best practices for developer tool websites
  - **Priority:** P2

- [ ] **L.8 Look and Feel Research**
  - Research look and feel for the website
  - **Priority:** P2

- [ ] **L.9 Low Entry / Bootstrapping Showcase**
  - Show low entry barrier and good support for bootstrapping
  - Highlight free Ollama account support
  - **Priority:** P2

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

### Completed 2026-06-15

- [x] **16.1 Migrate Configuration System to Clevis** (2026-06-15)
  - Replaced custom yoker/config/ module with Clevis package
  - Migrated config/loader.py to Clevis loader pattern
  - Migrated config/schema.py to Clevis schema with frozen dataclasses
  - Migrated config/validator.py to Clevis validation hooks
  - Preserved custom validation via `__post_init__` on config classes
  - Supported environment variables via TOML interpolation (Clevis native)
  - Implemented configuration discovery: user < project < CLI (Clevis pattern)
  - Ensured minimal breaking changes to public config file format
  - **See:** Issue #16
  - **Satisfies:** Configuration infrastructure modernization

- [x] **3.1 Package Plugin Discovery** (2026-06-15)
  - Import `{package}.yoker` module if present (using importlib)
  - Extract `TOOLS`, `SKILLS`, `AGENTS` lists from module
  - Handle graceful failure when package lacks yoker support
  - Implement namespace format: `{package}:{tool|skill|agent}` (e.g., `pkgq:find`)
  - Register discovered components with respective registries
  - Write unit tests for plugin discovery and registration
  - **See:** Issue #14
  - **Satisfies:** Package integration capability

### Phase 1: UI Module Structure (2026-06-11)

- [x] **UI-001: Create UI module directory structure** (2026-06-11)
  - Created `yoker/ui/` directory with empty `__init__.py`
  - Created placeholder files: `handler.py`, `base.py`, `bridge.py`
  - Reference: analysis/ui-separation-migration.md#phase-1-foundation
  - Acceptance: Directory structure exists, imports work

- [x] **UI-002: Define UIHandler protocol** (2026-06-11)
  - Added `UIHandler` protocol to `yoker/ui/handler.py`
  - Included all methods: lifecycle, input, content output, diagnostic output, streaming
  - Reference: analysis/ui-separation-ui-design.md#1-uihandler-protocol
  - Acceptance: Protocol defined with all required methods, type hints complete

- [x] **UI-003: Create BaseUIHandler abstract class** (2026-06-11)
  - Added `BaseUIHandler` to `yoker/ui/base.py`
  - Implemented state management (turn count, streaming state)
  - Provided default implementations for convenience methods
  - No formatting logic (implementation-specific)
  - Reference: analysis/ui-separation-ui-design.md#3-base-ui-handler
  - Acceptance: Abstract class with state management, clear abstract methods

- [x] **UI-004: Create UIBridge event dispatcher** (2026-06-11)
  - Added `UIBridge` to `yoker/ui/bridge.py`
  - Bridged EventHandler protocol to UIHandler protocol
  - Dispatched events to appropriate UI methods
  - Handled all event types (TURN_START, TURN_END, THINKING_*, CONTENT_*, TOOL_*, ERROR)
  - Reference: analysis/ui-separation-ui-design.md#2-event-bridge
  - Acceptance: Bridge dispatches all event types correctly

- [x] **UI-005: Update exceptions module** (2026-06-11)
  - Verified `YokerError` base exception exists
  - Ensured `NetworkError`, `ToolError`, `ConfigError`, `AgentError`, `SkillError` exist
  - Added `recoverable` attribute to `NetworkError`
  - Reference: analysis/ui-separation-errors.md#2-exception-hierarchy
  - Acceptance: Exception hierarchy complete, documented

- [x] **UI-006: Export UI module public API** (2026-06-11)
  - Updated `yoker/ui/__init__.py`
  - Exported: `UIHandler`, `BaseUIHandler`, `UIBridge`
  - Reference: analysis/ui-separation-migration.md#phase-1-foundation
  - Acceptance: Public API imports correctly

### Phase 2: Content Types and Events (2026-06-15)

- [x] **UI-007: Add content_type to ContentChunkEvent** (2026-06-15)
  - Added `content_type: str = "text/plain"` field to `ContentChunkEvent`
  - Updated event creation in Agent
  - Reference: analysis/ui-separation-io-catalog.md#31-events-with-variable-content-types
  - Acceptance: ContentChunkEvent has content_type field, default "text/plain"

- [x] **UI-008: Verify ToolContentEvent content_type** (2026-06-15)
  - Ensured `ToolContentEvent` has `content_type` field
  - Documented expected content types (text/plain, text/x-diff, application/json)
  - Reference: analysis/ui-separation-io-catalog.md#31-events-with-variable-content-types
  - Acceptance: Field exists, documented in code comments

- [x] **UI-009: Remove ErrorEvent** (2026-06-15)
  - Removed `ErrorEvent` from `events/types.py`
  - Removed any code that emits `ErrorEvent`
  - Replaced with exception raising
  - Reference: analysis/ui-separation-errors.md#7-migration-notes
  - Acceptance: ErrorEvent removed, exceptions used instead

- [x] **UI-010: Create content type detection utility** (2026-06-15)
  - Created `yoker/content_type.py`
  - Implemented `detect_content_type(content: bytes, path: Path) -> str`
  - Library detection, fallback to extension, fallback to text/plain
  - Reference: analysis/ui-separation-io-catalog.md#33-content-type-detection
  - Acceptance: Utility detects content types, fallbacks work correctly

- [x] **UI-011: Update tools to set content_type** (2026-06-15)
  - `ReadTool`: Detect content type from file
  - `WriteTool`: Set content type to summary (or text/plain)
  - `UpdateTool`: Set content type to diff (text/x-diff)
  - `GitTool`: Use `--no-color`, set content type to text/plain
  - Reference: analysis/ui-separation-io-catalog.md#42-tool-implementation
  - Acceptance: All tools set content_type appropriately

### Phase 3: UI Implementations (2026-06-15)

**PR:** #22

#### Interactive UI Tasks

- [x] **UI-012: Create InteractiveUIHandler skeleton** (2026-06-15)
  - Created `yoker/ui/interactive.py`
  - Extended `BaseUIHandler`
  - Initialized Rich console and prompt_toolkit session
  - Reference: analysis/ui-separation-ui-design.md#4-interactive-ui-handler
  - Acceptance: Class skeleton exists, initializes correctly

- [x] **UI-013: Implement interactive input handling** (2026-06-15)
  - Implemented `get_input()` with prompt_toolkit
  - Support multiline input (Esc+Enter)
  - Support command history
  - Handle EOF and KeyboardInterrupt
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Input works, multiline supported, history works

- [x] **UI-014: Implement interactive lifecycle methods** (2026-06-15)
  - Implemented `start()` - print banner and config info
  - Implemented `shutdown()` - print goodbye message
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Lifecycle methods display appropriate messages

- [x] **UI-015: Implement interactive content streaming** (2026-06-15)
  - Implemented `start_content_stream()`, `stream_content()`, `end_content_stream()`
  - Use Rich Live display for streaming
  - Handle ANSI codes from LLM output
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Content streams with live display, ANSI preserved

- [x] **UI-016: Implement interactive thinking streaming** (2026-06-15)
  - Implemented thinking stream methods
  - Show thinking in gray/dim style
  - Respect `show_thinking` setting
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Thinking streams separately from content

- [x] **UI-017: Implement interactive tool output** (2026-06-15)
  - Implemented `output_tool_call()`, `output_tool_result()`, `output_tool_content()`
  - Respect `show_tool_calls` setting
  - Format tool information appropriately
  - Reference: analysis/ui-separation-ui-design.md#interactive-ui-handler
  - Acceptance: Tool calls and results displayed correctly

- [x] **UI-018: Implement interactive error display** (2026-06-15)
  - Implemented `output_error()` with Rich formatting
  - Handle different error types (NetworkError, ToolError, etc.)
  - Format based on error type and recoverability
  - Reference: analysis/ui-separation-errors.md#42-interactive-implementation
  - Acceptance: Errors displayed with appropriate formatting

#### Batch UI Tasks

- [x] **UI-019: Create BatchUIHandler skeleton** (2026-06-15)
  - Created `yoker/ui/batch.py`
  - Extended `BaseUIHandler`
  - Support stdin/stdout/stderr channels
  - Reference: analysis/ui-separation-ui-design.md#5-batch-ui-handler
  - Acceptance: Class skeleton exists, channels defined

- [x] **UI-020: Implement batch input handling** (2026-06-15)
  - Implemented `get_input()` from stdin
  - Support predefined input messages (set_input_messages)
  - Handle EOF
  - Reference: analysis/ui-separation-ui-design.md#batch-ui-handler
  - Acceptance: Input from stdin works, predefined messages supported

- [x] **UI-021: Implement batch output channels** (2026-06-15)
  - Content → stdout
  - Thinking, errors, stats → stderr
  - No formatting, preserve ANSI
  - Reference: analysis/ui-separation-ui-design.md#batch-ui-handler
  - Acceptance: Output goes to correct channels

- [x] **UI-022: Implement batch streaming** (2026-06-15)
  - Implemented streaming methods (no buffering needed)
  - Direct output to appropriate channels
  - Respect show_thinking, show_tool_calls, show_stats settings
  - Reference: analysis/ui-separation-ui-design.md#batch-ui-handler
  - Acceptance: Streaming works without buffering

#### Shared UI Tasks

- [x] **UI-023: Move LiveDisplay to UI layer** (2026-06-15)
  - Created `yoker/ui/spinner.py`
  - Moved LiveDisplay implementation from `yoker/events/handlers.py`
  - Reference: analysis/ui-separation-migration.md#phase-3-ui-implementations
  - Acceptance: LiveDisplay available to InteractiveUIHandler

- [x] **UI-024: Update UI module exports** (2026-06-15)
  - Updated `yoker/ui/__init__.py`
  - Export: `UIHandler`, `BaseUIHandler`, `UIBridge`, `InteractiveUIHandler`, `BatchUIHandler`
  - Reference: analysis/ui-separation-migration.md#phase-3-ui-implementations
  - Acceptance: All UI classes import correctly

### Phase 4: Refactor Agent Module (2026-06-15)

**PR:** #23

- [x] **UI-025: Create agent package directory structure** (2026-06-15)
  - Created `yoker/agent/` directory
  - Created placeholder files: `__init__.py`, `core.py`, `agent.py`, `processing.py`, `tools.py`
  - Reference: analysis/ui-separation-agent-module.md#2-target-structure
  - Acceptance: Directory structure exists

- [x] **UI-026: Refactor ContextManager to be list-like** (2026-06-15)
  - Modified `ContextManager` to extend `UserList`
  - Implemented `append()` to persist on add
  - Agent sees context as a plain list
  - Reference: analysis/ui-separation-overview.md#4-context-and-contextmanager
  - Acceptance: ContextManager works as list, Agent can use plain list too

- [x] **UI-027: Move AgentCore to agent/core.py** (2026-06-15)
  - Moved `AgentCore` class from `base.py` to `agent/core.py`
  - Included event handler management
  - Included guardrail validation
  - Reference: analysis/ui-separation-agent-module.md#41-agentcorepy
  - Acceptance: AgentCore works in new location

- [x] **UI-028: Extract Agent initialization and properties** (2026-06-15)
  - Created `Agent` class in `agent/agent.py`
  - Moved initialization and property accessors
  - Delegated to AgentCore
  - Reference: analysis/ui-separation-agent-module.md#42-agentagentpy
  - Acceptance: Agent initializes correctly, properties work

- [x] **UI-029: Extract message processing logic** (2026-06-15)
  - Created processing logic module in `agent/processing.py`
  - Extracted streaming, tool calls, event emission
  - Kept as methods on Agent class (not separate)
  - Reference: analysis/ui-separation-agent-module.md#43-agentprocessingpy
  - Acceptance: Processing logic in agent module, not separate file

- [x] **UI-030: Extract tool registry building** (2026-06-15)
  - Created `_build_tool_registry()` in `agent/tools.py`
  - Moved tool initialization logic
  - Reference: analysis/ui-separation-agent-module.md#44-agenttoolspy
  - Acceptance: Tool registry builds correctly

- [x] **UI-031: Remove Agent session lifecycle** (2026-06-15)
  - Removed `begin_session()` and `end_session()` methods from Agent
  - Removed `SessionStartEvent` and `SessionEndEvent` from events
  - Agent lifecycle is create → use → discard
  - Reference: analysis/ui-separation-overview.md#6-agent-lifecycle-no-session
  - Acceptance: No session methods, no session events

- [x] **UI-032: Update context module for list-like interface** (2026-06-15)
  - Created `context/` module
  - Created `manager.py` with `ContextManager` extending `UserList`
  - Created `basic.py` with `BasicContextManager`
  - Created placeholder for `PersistenceContextManager`
  - Reference: analysis/ui-separation-overview.md#45-module-structure
  - Acceptance: Context module structure complete

- [x] **UI-033: Update imports throughout codebase** (2026-06-15)
  - Updated `yoker/__init__.py` to import from `yoker.agent`
  - Updated all imports from old locations
  - Reference: analysis/ui-separation-agent-module.md#54-update-imports
  - Acceptance: All imports work, tests pass

- [x] **UI-034: Remove old files** (2026-06-15)
  - Deleted `yoker/base.py`
  - Deleted `yoker/agent.py`
  - Removed session events from `events/types.py`
  - Reference: analysis/ui-separation-agent-module.md#55-remove-old-files
  - Acceptance: Old files deleted, no references remain

### Phase 5: Slash Commands (2026-06-15)

**PR:** #24

- [x] **UI-035: Create commands directory structure** (2026-06-15)
  - Create `yoker/ui/commands/` directory
  - Create `__init__.py` with command registry
  - Create placeholder files for each command
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Directory structure exists

- [x] **UI-036: Add Agent.inject_skill_context() method** (2026-06-15)
  - Add method to inject skill context into conversation
  - Used by skill invocation commands
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Method works, skill context injected correctly

- [x] **UI-037: Move /help command to UI layer** (2026-06-15)
  - Create `commands/help.py`
  - Move help logic from `__main__.py`
  - Command receives UIHandler, outputs via UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /help command works in new location

- [x] **UI-038: Move /think command to UI layer** (2026-06-15)
  - Create `commands/think.py`
  - Move think logic
  - Command sets Agent thinking_mode state
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /think command works

- [x] **UI-039: Move /skills command to UI layer** (2026-06-15)
  - Create `commands/skills.py`
  - Command queries Agent for skill list
  - Outputs via UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /skills command works

- [x] **UI-040: Move /context command to UI layer** (2026-06-15)
  - Create `commands/context.py`
  - Command queries Agent for context state
  - Outputs via UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: /context command works

- [x] **UI-041: Create skill invocation command** (2026-06-15)
  - Create `commands/skill_invoke.py`
  - Handle `/<skill-name>` commands
  - Call `Agent.inject_skill_context()`
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Skill invocation works

- [x] **UI-042: Create command registry** (2026-06-15)
  - Create registry in `yoker/ui/commands/__init__.py`
  - Register all commands
  - Provide dispatch mechanism
  - Reference: analysis/ui-separation-migration.md#phase-5-slash-commands
  - Acceptance: Command registry dispatches commands correctly

### Phase 6: Entry Point Refactoring (2026-06-15)

**PR:** #25

- [x] **UI-043: Add UI configuration to Config** (2026-06-15)
  - Add `UIConfig` dataclass to config
  - Include mode, show_thinking, show_tool_calls, show_stats
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Config has UI section

- [x] **UI-044: Create run_session() helper** (2026-06-15)
  - Create session loop function
  - Handle exception catching and UI error display
  - Handle cleanup
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Session loop works with UI handler

- [x] **UI-045: Refactor __main__.py to use UIHandler** (2026-06-15)
  - Create UI handler based on mode (interactive or batch)
  - Create UIBridge and connect to Agent
  - Call `ui.start()` and `ui.shutdown()` directly
  - Remove all print statements
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: __main__.py uses UI handler, no print statements

- [x] **UI-046: Implement mode selection logic** (2026-06-15)
  - Parse CLI arguments for mode
  - Create appropriate UI handler
  - Wire up with Clevis config
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Mode selection works (interactive vs batch)

- [x] **UI-047: Remove old command dispatch from __main__.py** (2026-06-15)
  - Remove inline command handling
  - Use command registry from UI layer
  - Reference: analysis/ui-separation-migration.md#phase-6-entry-point-refactoring
  - Acceptance: Command dispatch uses registry

### Phase 7: Remove Old Code (2026-06-15)

**PR:** #26

- [x] **UI-048: Remove ConsoleEventHandler** (2026-06-15)
  - Delete `yoker/events/handlers.py`
  - Update `yoker/events/__init__.py`
  - Verify all references removed
  - Reference: analysis/ui-separation-migration.md#phase-7-remove-old-code
  - Acceptance: ConsoleEventHandler removed, no references

- [x] **UI-049: Clean up imports** (2026-06-15)
  - Remove unused imports from all files
  - Update `__all__` exports
  - Reference: analysis/ui-separation-migration.md#phase-7-remove-old-code
  - Acceptance: No unused imports, exports clean

- [x] **UI-050: Remove old code from __main__.py** (2026-06-15)
  - Remove all deprecated code paths
  - Verify no dead code
  - Reference: analysis/ui-separation-migration.md#phase-7-remove-old-code
  - Acceptance: __main__.py is clean, minimal

### Phase 8: Final Polish (2026-06-15)

**PR:** #27

**Goal:** Documentation and examples.

**Dependency:** All previous phases complete

- [x] **UI-051: Update README.md** (2026-06-15)
  - Document interactive mode usage
  - Document batch mode usage
  - Add library usage example
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: README updated with new usage patterns

- [x] **UI-052: Create batch mode example** (2026-06-15)
  - Create `examples/batch_mode.py`
  - Show batch mode usage
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: Example works correctly

- [x] **UI-053: Create library usage example** (2026-06-15)
  - Create `examples/library_usage.py`
  - Show how to use yoker as library
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: Example works correctly

- [x] **UI-054: Create custom handler example** (2026-06-15)
  - Create `examples/custom_handler.py`
  - Show how to implement custom UIHandler
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: Example works correctly

- [x] **UI-055: Update CLAUDE.md** (2026-06-15)
  - Document new module structure
  - Document UI layer architecture
  - Update current state section
  - Reference: analysis/ui-separation-migration.md#phase-8-final-polish
  - Acceptance: CLAUDE.md reflects new architecture

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


