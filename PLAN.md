# Plan

This file contains the Intake Backlog with Minimal Business Increments (MBIs).

## Unsorted MBIs

Quick captures for MBI ideas. These are raw requests that haven't been analyzed yet.

[None at this time]

---

## Active MBI

The MBI currently being implemented. Only one Active MBI at a time.

### MBI-002: Bootstrap

**Goal:** Users run `yoker` for the first time and are guided through: backend selection, model selection, Ollama account creation (with free tier), and config file creation. After completing bootstrap, any package using yoker can run immediately.

**Value:** Lowers barrier to entry. Users can try yoker with minimal friction, increasing adoption and reducing support questions. A few free cloud model cycles should be enough to test a small agentic workflow.

**Status:** Ready

**Components:**
- [ ] DEV: Detect missing/incomplete configuration
- [ ] DEV: Interactive backend selection wizard (Ollama local, ollama.com API, other)
- [ ] DEV: Model selection wizard for chosen backend
- [ ] DEV: Ollama account creation assistance (free tier guidance)
- [ ] DEV: yoker.toml creation with user choices
- [ ] TEST: Bootstrap flow tests
- [ ] DOCS: Bootstrap documentation

**Acceptance Criteria:**
- [ ] Running `yoker` with no config triggers bootstrap wizard
- [ ] User can choose between Ollama local, ollama.com API, and other backends
- [ ] User can select from available models for chosen backend
- [ ] User receives guidance to create Ollama account for free cloud model cycles
- [ ] yoker.toml is created with user's choices, ready to use immediately
- [ ] After bootstrap, any package using yoker can run

**Dependencies:** None

---

## Backlog

Future MBIs, ordered by priority (highest first).

### MBI-003: Python API

**Goal:** Python developers can easily integrate agentic (sub-)workflows in Python function calls, with a clean utility API wrapping the current class-oriented architecture. Example: `yoker.execute_skill("skill-name", "prompt")` or even `from package.skills import skill_name; skill_name("prompt")`.

**Value:** Makes yoker developer-friendly, removing all hurdles to quick integration. Developers can use yoker without understanding internal classes.

**Status:** Ready

**Components:**
- [ ] RES: Review current class-oriented API
- [ ] RES: Design developer-friendly utility functions
- [ ] DEV: Implement utility wrapper functions
- [ ] DEV: (Optional) Auto-generate functions for detected skills/agents
- [ ] TEST: API usage tests
- [ ] DOCS: Python API documentation with examples

**Acceptance Criteria:**
- [ ] Developers can call `yoker.execute_skill("skill-name", "prompt")` from Python code
- [ ] API documentation shows common integration patterns
- [ ] Utility functions provide clean abstraction over internal classes

**Dependencies:** MBI-002 (Bootstrap) for first-time users

---

### MBI-004: yoker Commands

**Goal:** Users can use yoker from the command line with a complete CLI: `yoker chat`, `yoker run`, `yoker loop`, `yoker init`, `yoker config`, `yoker container`. This completes the initial yoker architecture.

**Value:** Command-line interface is essential for developer workflows and automation. Completes the yoker product for first release.

**Status:** Ready

**Components:**
- [ ] DEV: `yoker chat` — start in interactive environment
- [ ] DEV: `yoker run` — run an agentic workflow from Python module, GitHub repo, local folder, or zip file
- [ ] DEV: `yoker loop` — perform run at interval
- [ ] DEV: `yoker init` — generate default config (optional with bootstrap questions)
- [ ] DEV: `yoker config` — show config
- [ ] DEV: `yoker container` — generate container setup (podman/docker/container)
- [ ] TEST: Command tests
- [ ] DOCS: CLI documentation

**Acceptance Criteria:**
- [ ] All CLI commands work as documented
- [ ] `yoker run` supports multiple sources (module, repo, folder, zip)
- [ ] `yoker loop` runs at specified intervals
- [ ] `yoker container` generates valid container configuration

**Dependencies:** MBI-002 (Bootstrap), MBI-003 (Python API)

---

### MBI-005: Assistant Integration

**Goal:** Showcase yoker's capabilities with a complete example project (yoker-assistant) that demonstrates: checking yoker setup, custom looping logic (mail account integration), custom context builders, agent triggering, git integration, and mail responses. Users can try `uvx yoker-assistant` and experience how low-friction yoker is.

**Value:** Representative pet-project that demonstrates yoker's capabilities. Shows users they are free from vendor lock-in. Includes extensive documentation and serves as a reference implementation.

**Status:** Ready

**Components:**
- [ ] DEV: Create yoker-assistant package project
- [ ] DEV: Implement setup check with bootstrap trigger
- [ ] DEV: Implement custom loop logic (mail account integration)
- [ ] DEV: Implement custom context builder
- [ ] DEV: Implement agent triggering and personalization
- [ ] DEV: Implement git integration (commit/push)
- [ ] DEV: Implement mail response handling
- [ ] DOCS: Comprehensive documentation
- [ ] DOCS: Tutorial and examples

**Acceptance Criteria:**
- [ ] Users can run `uvx yoker-assistant` successfully
- [ ] yoker-assistant demonstrates all yoker capabilities
- [ ] Documentation explains architecture and patterns
- [ ] Project serves as reference implementation

**Dependencies:** MBI-002 (Bootstrap), MBI-003 (Python API), MBI-004 (yoker Commands)

---

## Done

Completed MBIs.

### MBI-001: Package Plugin System (Completed: 2026-06-25)

**Goal:** Users can extend Yoker with tools and skills from Python packages via `yoker --with <package>`, and invoke them via `/skill-name` commands or agent tool calls.

**Value:** Enables reusable, shareable Yoker extensions without modifying core codebase. Users can `uvx --with pkgq yoker --with pkgq` and invoke `/pkgq:create`.

**Status:** Done

**Final Validation:**
- [ ] Validate plugin system with pkgq project
- [ ] Publish release to PyPI

**Achieved:** All core components implemented (Skill Infrastructure, Slash Commands, Skill Tool, Package Plugin Discovery, CLI --with Argument, UI Separation, Error Handling, Documentation, Testing).
