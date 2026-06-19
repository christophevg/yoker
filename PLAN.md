# Plan

This file contains the Intake Backlog with Minimal Business Increments (MBIs).

## Unsorted MBIs

Quick captures for MBI ideas. These are raw requests that haven't been analyzed yet.

- [ ] **Bootstrap & Python API** — After the current MBI, focus on: (1) Bootstrap procedure for first-time users without Ollama configuration — interactive guided setup, and (2) Python API for one-shot skill execution like `yoker.execute_skill("skill-name", "prompt")`.
- [ ] yoker commands: yoker command...
  - [ ] chat      - start in interactive environment
  - [ ] run       - run an agentic workflow from
    - [ ] Python module
    - [ ] GitHub repo
    - [ ] local folder
    - [ ] zip file
  - [ ] loop      - perform run at interval
  - [ ] init      - generate default config (optional with bootstrap questions)
  - [ ] config    - show config
  - [ ] container - generate container setup (podman/docker/container)

---

## Active MBI

The MBI currently being implemented. Only one Active MBI at a time.

### MBI-001: Package Plugin System

**Goal:** Users can extend Yoker with tools and skills from Python packages via `yoker --with <package>`, and invoke them via `/skill-name` commands or agent tool calls.

**Value:** Enables reusable, shareable Yoker extensions without modifying core codebase. Users can `uvx --with pkgq yoker --with pkgq` and invoke `/pkgq:create`.

**Status:** In Progress

**Components:**
- [x] DEV: Skill Infrastructure (Markdown + YAML frontmatter, SkillLoader, skill injection)
- [x] DEV: Slash Command Support (`/skill-name` parsing, skill context injection)
- [x] DEV: Skill Tool for Agent Invocation (SkillTool, agent can invoke skills)
- [ ] DEV: UI Separation Migration (refactoring to support plugin architecture)
- [ ] DEV: Package Plugin Discovery (import `{package}.yoker` modules)
- [ ] DEV: CLI `--with` Argument (load packages at startup)
- [ ] TEST: Unit tests for plugin discovery and registration
- [ ] DOCS: README with quick start guide
- [ ] DOCS: Configuration options documentation
- [ ] DOCS: API documentation (Sphinx autodoc)
- [ ] DOCS: Usage examples

**Tasks:**

From TODO.md (Phase 2 complete, Phase 3 pending):

- [x] **2.1 Skill Infrastructure** — Skill dataclass, SkillLoader, skill context injection
- [x] **2.2 Slash Command Support** — `/skill-name` command parsing in CLI
- [x] **2.3 Skill Tool for Agent Invocation** — SkillTool for agent-initiated skill execution
- [ ] **3.1 Package Plugin Discovery** — Import `{package}.yoker` modules, register components
- [ ] **3.2 CLI --with Argument** — `--with <package>` argument, package loading

From TODO.md (Active: UI Separation Migration — supporting refactoring):

- [ ] **UI Separation Phases 2-8** — Refactoring UI from Agent to support plugin architecture
  - Phase 2: Content Types and Events
  - Phase 3: UI Implementations
  - Phase 4: Refactor Agent Module
  - Phase 5: Slash Commands
  - Phase 6: Entry Point Refactoring
  - Phase 7: Remove Old Code
  - Phase 8: Final Polish

From TODO.md (Phase 5: Polish):

- [ ] **5.1 Error Handling** — Error codes, graceful recovery, user-friendly messages
- [ ] **5.2 Documentation** — README, configuration, API docs, examples

**Acceptance Criteria:**
- [ ] Users can run `uvx --with pkgq yoker --with pkgq`
- [ ] Users can invoke `/pkgq:create` (or any package skill)
- [ ] Skills can be loaded from Python packages
- [ ] Plugin discovery works without errors
- [ ] README documents `--with` usage
- [ ] All unit tests pass

**Dependencies:** None (foundation work complete)

---

## Backlog

Future MBIs, ordered by priority (highest first).

[None yet — Unsorted MBI above will be analyzed and moved here]

---

## Done

Completed MBIs.

[None yet — MBI-001 is the first MBI tracked in PLAN.md]
