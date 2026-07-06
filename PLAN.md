# Plan

This file contains the Intake Backlog with Minimal Business Increments (MBIs).

## Unsorted MBIs

Quick captures for MBI ideas. These are raw requests that haven't been analyzed yet.

[None at this time]

---

## Active MBI

The MBI currently being implemented. Only one Active MBI at a time.

[None — see Backlog for the next MBI to activate (MBI-003: Python API).]

---

## Backlog

Future MBIs, ordered by priority (highest first).

### MBI-003: Python API

**Goal:** Python developers can easily integrate agentic (sub-)workflows in Python function calls, with a clean utility API wrapping the current class-oriented architecture. Example: `yoker.execute_skill("skill-name", "prompt")` or even `from package.skills import skill_name; skill_name("prompt")`.

**Value:** Makes yoker developer-friendly, removing all hurdles to quick integration. Developers can use yoker without understanding internal classes.

**Status:** Ready (unblocked — MBI-007 merged to master 2026-07-06; MBI-002 Bootstrap merged).

**Design source of truth:** `analysis/mbi-003-python-api-design.md` (three-layer utility API: Layer 1 wrappers over existing classes, Layer 2 `execute_skill` one-shot, Layer 3 `yoker.session()` workflow primitive built on the real `Session`).

**Components:**
- [ ] RES: Review current class-oriented API
- [ ] RES: Design developer-friendly utility functions
- [ ] DEV: **Config factory** — create a `Config` in code with a flag to enable/skip normal config loading (TOML discovery + CLI args). Needed by the `agent()` factory function so programmatic callers can construct a Config without touching the filesystem. (Owner request, PR #42 Comment 1.)
- [ ] DEV: Implement utility wrapper functions (build on the real `Session` from MBI-007)
- [ ] DEV: (Optional) Auto-generate functions for detected skills/agents
- [ ] TEST: API usage tests
- [ ] DOCS: Python API documentation with examples

**Acceptance Criteria:**
- [ ] Developers can call `yoker.execute_skill("skill-name", "prompt")` from Python code
- [ ] A Config factory exists for programmatic Config construction (skip filesystem/CLI loading)
- [ ] API documentation shows common integration patterns
- [ ] Utility functions provide clean abstraction over internal classes
- [ ] `yoker.session()` builds on the real `Session` construct from MBI-007

**Dependencies:** MBI-002 (Bootstrap) — DONE (merged 2026-07-01); MBI-007 (Session) — DONE (merged 2026-07-06, PR #43). The `yoker.session()` workflow primitive in Layer 3 builds on the real `Session` construct. The Config factory (owner request, PR #42 Comment 1) is part of MBI-003.

**Note:** The Config factory requirement was raised by the owner in PR #42 Comment 1 and is recorded in `analysis/session-concept-analysis.md` §7.2. It belongs to MBI-003 and is addressed as part of this MBI.

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

### MBI-006: Multi-Provider Backend Support (Completed: 2026-07-01)

**Goal:** Make Yoker provider-neutral at the model layer. A single `ModelBackend` Protocol abstracts chat streaming; the Agent talks to a backend instance, not to `ollama.AsyncClient` directly. Ollama ships via a native SDK backend (`OllamaBackend`); all other providers (OpenAI, Anthropic, Gemini, and 100+ others) ship via a unified `LitellmBackend` wrapping the `litellm` library.

**Value:** Removes vendor lock-in at the model layer. Users can choose Ollama (local/free), OpenAI, Anthropic, or any litellm-supported provider by switching a single config field, without changing their agentic workflows. Establishes the abstraction seam that lets future providers land without touching the Agent hot path.

**Status:** Done

**Design source of truth:** `analysis/multi-provider-backend-design.md` (Phase 1) and `analysis/dual-backend-architecture.md` (Phase 2). Functional counterpart: `analysis/functional-multi-provider-backend.md`.

**Achieved:** Dual backend architecture landed in master. Phase 1 introduced `ModelBackend` Protocol, `ChatChunk` neutral stream type, `OllamaBackend` (native SDK adapter), `create_backend()` factory, and the `with_model()` helper (PR #36). Phase 2 added `LitellmBackend` wrapping the `litellm` library for OpenAI, Anthropic, and 100+ providers, with stream translation, `reasoning_content` mapping, provider-specific parameter mapping, and base_url trust boundary (PR #37). The original three-phase plan (separate OpenAI/Anthropic backends) was superseded by the unified dual-backend approach. Config schema is a tagged union; old `~/.yoker.toml` files remain valid without migration. Subagent spawn is provider-agnostic.

**Merged via:** PR #36 (Phase 1, 2026-06-29) and PR #37 (Phase 2, 2026-07-01).

---

### MBI-002: Bootstrap (Completed: 2026-07-01)

**Goal:** Users run `yoker` for the first time and are guided through: backend selection, model selection, Ollama account creation (with free tier), and config file creation. After completing bootstrap, any package using yoker can run immediately.

**Value:** Lowers barrier to entry. Users can try yoker with minimal friction, increasing adoption and reducing support questions. A few free cloud model cycles should be enough to test a small agentic workflow.

**Status:** Done

**Achieved:** Bootstrap wizard landed in master (`src/yoker/bootstrap/`). `config_provided()` detection in `detect.py` triggers the wizard when no config source is present. Interactive `BootstrapWizard` walks users through backend intro, Ollama account creation guidance, connection-method selection (local app vs API key), and model selection (curated list + free text, no network call). Config writer in `src/yoker/config/writer.py` (annotation-driven, generic) writes `~/.yoker.toml` with `chmod 600`. Non-interactive mode prints stderr warning and exits non-zero. Library mode (`Agent(config=...)`) skips bootstrap. Default model changed to `gemini-3-flash-preview:cloud` (cloud, no download). Bootstrap continues into the normal session after writing config (no rerun needed). Documentation in `docs/guides/getting-started.md`.

**Merged via:** PR #35 (2026-07-01).

---

### ContextManager Refactor (Completed: 2026-07-06)

**Goal:** Refactor the `ContextManager` construct to clean up its responsibilities and align it with the Session-based multi-agent architecture landed in MBI-007. Reduce coupling, clarify ownership of context lifecycle, and prepare the primitive for the workflow layer that MBI-003 (Python API) builds on.

**Value:** Removes accumulated complexity and dual-ownership patterns between `Agent` and `Session` around context management. Makes context handling a coherent single-responsibility primitive, consistent with the post-MBI-007 architecture where `Session` owns team-level concerns and `Agent` is a single-agent chat loop. Prerequisite-quality cleanup before MBI-003 exposes the API to external developers.

**Status:** Done

**Design source of truth:** `analysis/context-manager-refactor-design.md`.

**Achieved:** Replaced the `UserList`-based `ContextManager` with a Protocol + Wrapper architecture. Introduced `ContextManager` Protocol, `BasicContextManager`, `PersistedContextManager`, and `ContextWrapper`. Cleaned up responsibilities and aligned context lifecycle ownership with the Session-based multi-agent architecture.

**Merged via:** PR #44 (2026-07-06).

---

### MBI-007: Session (Completed: 2026-07-06)

**Goal:** Introduce a `Session` construct that manages a team of agents: their lifecycle (create, spawn, monitor, cancel), their registry, recursion depth tracking, event aggregation, and inter-agent messaging. Reduce `Agent` to a single-agent chat loop with no orchestration responsibilities. Establish the primitive that MBI-003 (Python API) builds its workflow layer on top of.

**Value:** Unlocks true multi-agent workflows (fan-out, pipelines, long-lived teams, inter-agent messaging) that were not expressible before. Cleans up `Agent` to a single-responsibility primitive. Makes sub-agents visible via event aggregation, serving Yoker's transparency philosophy. Makes the "Recursive Composition: True Sub-Agents" claim in `docs/rationale.md` fully real.

**Status:** Done

**Design source of truth:** `analysis/session-concept-analysis.md` (finalized, owner-approved — all 10 decisions in §7 resolved via PR #42; clarifications rounds 1 & 2 resolved via PR #43).

**Achieved:** `Session` async context manager landed in master; `AgentRegistry` moved from `Agent` to `Session`; recursion depth tracking moved to `Session`; `builtin/agent.py` reworked to `SpawnAgent` (Session-injected); `SendMessage` Session-injected tool; session-level event types (`SESSION_START/END`, `AGENT_SPAWNED/FINISHED`, `AGENT_MESSAGE`); `EventRecorder` session-scoped; `UIBridge` registered on `Session`; `__main__.py` constructs `Session`, `run_session` renamed to `run_repl`; `[session]` config section; `ToolContext` carries `session`; backend factory + sharing in `Session`. `ListAgents` deferred to a follow-up MBI per PR #43 Clarification 6.

**Merged via:** PR #43 (2026-07-06).

---

### MBI-001: Package Plugin System (Completed: 2026-06-25)

**Goal:** Users can extend Yoker with tools and skills from Python packages via `yoker --with <package>`, and invoke them via `/skill-name` commands or agent tool calls.

**Value:** Enables reusable, shareable Yoker extensions without modifying core codebase. Users can `uvx --with pkgq yoker --with pkgq` and invoke `/pkgq:create`.

**Status:** Done

**Final Validation:**
- [x] Validate plugin system with pkgq project
- [x] Publish release to PyPI

**Achieved:** All core components implemented (Skill Infrastructure, Slash Commands, Skill Tool, Package Plugin Discovery, CLI --with Argument, UI Separation, Error Handling, Documentation, Testing). Validated with pkgq project; v0.6.0 released to PyPI (2026-07-03).

