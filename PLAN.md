# Plan

This file contains the Intake Backlog with Minimal Business Increments (MBIs).

## Unsorted MBIs

Quick captures for MBI ideas. These are raw requests that haven't been analyzed yet.

[None at this time]

---

## Active MBI

The MBI currently being implemented. Only one Active MBI at a time.

[None at this time — MBI-004 just completed.]

---

## Backlog

Future MBIs, ordered by priority (highest first).

### MBI-003: Python API

**Goal:** Python developers can easily integrate agentic (sub-)workflows in Python function calls, with a clean utility API wrapping the current class-oriented architecture. Example: `yoker.execute_skill("skill-name", "prompt")` or even `from package.skills import skill_name; skill_name("prompt")`.

**Value:** Makes yoker developer-friendly, removing all hurdles to quick integration. Developers can use yoker without understanding internal classes.

**Status:** Done (merged 2026-07-06). Thin single-module facade (`yoker/api.py`): `process`, `do`, `agent`, `session`, `run_sync`. No private helpers remain.

**Design source of truth:** `analysis/mbi-003-python-api-design.md` (three-layer utility API: Layer 1 wrappers over existing classes, Layer 2 `execute_skill` one-shot, Layer 3 `yoker.session()` workflow primitive built on the real `Session`).

**Components:**
- [x] RES: Review current class-oriented API
- [x] RES: Design developer-friendly utility functions
- [x] DEV: **Config factory** — create a `Config` in code with a flag to enable/skip normal config loading (TOML discovery + CLI args). Needed by the `agent()` factory function so programmatic callers can construct a Config without touching the filesystem. (Owner request, PR #42 Comment 1.)
- [x] DEV: Implement utility wrapper functions (build on the real `Session` from MBI-007)
- [ ] DEV: (Optional) Auto-generate functions for detected skills/agents — deferred per design doc §10
- [x] TEST: API usage tests
- [x] DOCS: Python API documentation with examples

**Acceptance Criteria:**
- [x] Developers can call `yoker.process("...")` from Python code (one-shot)
- [x] Developers can call `yoker.do("skill-name", "prompt")` from Python code
- [x] `yoker.agent(...)` returns a configured, reusable `Agent`
- [x] `yoker.session(...)` builds on the real `Session` construct from MBI-007
- [x] A Config factory exists for programmatic Config construction (skip filesystem/CLI loading)
- [x] API documentation shows common integration patterns

**Dependencies:** MBI-002 (Bootstrap) — DONE (merged 2026-07-01); MBI-007 (Session) — DONE (merged 2026-07-06, PR #43).

**Note:** MBI-003 is complete. The optional auto-generate feature (3.7) is deferred to a follow-up MBI.

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

### MBI-004: yoker Commands (Completed: 2026-07-15)

**Goal:** Users can use yoker from the command line with a complete CLI: `yoker chat`, `yoker run`, `yoker loop`, `yoker init`, `yoker config`, `yoker container`. The flagship capability is `yoker run`, which loads a source (module, GitHub URL, folder, zip) containing an extended yoker manifest (agent selection + initial prompt) and runs it as a "yoker-based agentic executable package."

**Value:** Command-line interface is essential for developer workflows and automation. `yoker run` transforms yoker from an interactive tool into a runtime for agentic packages — any plugin can become an executable agent with a single command. Completes the yoker product for first release.

**Status:** Done

**Design source of truth:** `analysis/mbi-004-yoker-commands.md`

**Achieved:** All subcommands implemented and working end-to-end. `chat` (default, backward compatible), `run` (flagship — loads source via two-phase resolution with trust gate, applies manifest config overrides, runs agent non-interactively), `init`, `config`, `loop`, `inspect`, `container`. Extended manifest supports both Python `__YOKER_MANIFEST__` and file-based `agent.toml` with `[run]`/`[plugin]` sections and config-override layering (base TOML → manifest → CLI). Source resolution supports module names, GitHub URLs (HTTPS-only, SSRF-checked), folder paths, and zip files (safe extraction with zip-bomb guards). Clevis 0.7.0 upgrade replaced internal-API workarounds with native public API.

**Merged via:** PR #46 (2026-07-15).

---

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

