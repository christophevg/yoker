# Plan

This file contains the Intake Backlog with Minimal Business Increments (MBIs).

## Unsorted MBIs

Quick captures for MBI ideas. These are raw requests that haven't been analyzed yet.

[None at this time]

---

## Active MBI

The MBI currently being implemented. Only one Active MBI at a time.

### MBI-006: Multi-Provider Backend Support

**Goal:** Make Yoker provider-neutral at the model layer. A single `ModelBackend` Protocol abstracts chat streaming; the Agent talks to a backend instance, not to `ollama.AsyncClient` directly. Ollama, OpenAI, and Anthropic each ship as a backend implementation behind the same Protocol, delivered in three phases: Phase 1 introduces the Protocol and reimplements Ollama on it (pure refactor, no behaviour change); Phase 2 adds OpenAI; Phase 3 adds Anthropic. The config schema becomes a tagged-union shape that carries per-provider sub-configs and per-provider parameters. The bootstrap wizard's provider-selection step is deferred to a separate follow-up.

**Value:** Removes vendor lock-in at the model layer. Users can choose Ollama (local/free), OpenAI, or Anthropic by switching a single config field, without changing their agentic workflows. Establishes the abstraction seam that lets future providers land without touching the Agent hot path. Phase 1 alone delivers no user-facing change but unlocks Phases 2 and 3.

**Status:** In Progress

**Design source of truth:** `analysis/multi-provider-backend-design.md` (finalized, owner-approved — all 20 decisions in §11 resolved). Functional counterpart: `analysis/functional-multi-provider-backend.md`.

**Components (3 phases):**
- [ ] DEV: Phase 1 — Protocol + Ollama Refactor (M-sized pure refactor; see TODO.md tasks 6.1-6.8)
- [ ] DEV: Phase 2 — OpenAI Backend (M-sized; add `openai` SDK backend, per-provider curated model list)
- [ ] DEV: Phase 3 — Anthropic Backend (L-sized; block-style stream translation, message-shape rewrite, tool-schema translation, SSE parsing, thinking config)

**Acceptance Criteria (overall MBI):**
- [ ] `ModelBackend` Protocol and `ChatChunk` neutral stream type introduced in `src/yoker/backends/`
- [ ] Ollama behaviour unchanged through the new Protocol (Phase 1)
- [ ] OpenAI backend works end-to-end including tool calls and reasoning-content thinking (Phase 2)
- [ ] Anthropic backend works end-to-end including block-style streaming, system-message extraction, and tool-use round trips (Phase 3)
- [ ] Config schema is a tagged union; old `~/.yoker.toml` files remain valid without migration
- [ ] Subagent spawn is provider-agnostic regardless of active provider
- [ ] `make check` green at each phase boundary; behaviour unchanged for Ollama path throughout

**Dependencies:** PRE-1 (M.5 — populate `Agent._tool_backends` for Ollama) — DONE, merged. Bootstrap wizard provider selection is deferred to a separate follow-up MBI on top of the merged bootstrap PR.

**Out of scope (deferred):** Bootstrap wizard provider selection; `build_bootstrap_overrides` provider-awareness; web tools (`web_search`/`web_fetch`) for non-Ollama providers; embeddings/image generation/model management; live API model discovery; dropping the native Ollama SDK.

---

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

### MBI-007: Session

**Goal:** Introduce a `Session` construct that manages a team of agents: their lifecycle (create, spawn, monitor, cancel), their registry, recursion depth tracking, event aggregation, and inter-agent messaging. Reduce `Agent` to a single-agent chat loop with no orchestration responsibilities. Establish the primitive that MBI-003 (Python API) builds its workflow layer on top of.

**Value:** Unlocks true multi-agent workflows (fan-out, pipelines, long-lived teams, inter-agent messaging) that are not expressible today. Cleans up `Agent` to a single-responsibility primitive. Makes sub-agents visible via event aggregation, serving Yoker's transparency philosophy. Prerequisite for MBI-003's `yoker.session()` workflow primitive to be a facade over a real primitive rather than a missing one. Makes the "Recursive Composition: True Sub-Agents" claim in `docs/rationale.md` fully real.

**Status:** Ready

**Design source of truth:** `analysis/session-concept-analysis.md` (finalized, owner-approved — all 10 decisions in §7 resolved via PR #42).

**Components (high-level — detailed tasks created at implementation time):**
- [ ] DEV: Create `src/yoker/session/` module (`Session` class, `Message` dataclass, `spawn()`, event aggregator, lifecycle via `async with`)
- [ ] DEV: Move `AgentRegistry` ownership from `Agent` to `Session`; plugin loading targets Session. Agents retain a list of names they may spawn (Decision 10)
- [ ] DEV: Move recursion depth tracking from `Agent` to `Session`
- [ ] DEV: Rework `builtin/agent.py` to a thin wrapper capturing Session; `_create_subagent`/`_run_with_timeout` move to Session as `spawn()` (Decision 8)
- [ ] DEV: Add session-level event types (`SESSION_START/END`, `AGENT_SPAWNED/FINISHED`, `AGENT_MESSAGE`); extend `EventRecorder` to session-scoped
- [ ] DEV: Wire `UIBridge` to Session (Decision 5); add optional `agent_spawned(name)`/`agent_finished(name)` to `UIHandler` with no-op defaults in `BaseUIHandler`; tag existing events with `agent_id`
- [ ] DEV: Rework `__main__.py`: construct Session in `main()`, rename `run_session` to `run_repl`, register bridge on Session (Decision 6)
- [ ] DEV: Add `[session]` config section: `max_agents`, `default_isolation_policy`, `event_aggregation` (Decision 7); relocate `tools.agent.max_recursion_depth` semantics
- [ ] DEV: Update `ToolContext` to carry a `session` reference (Decision 8)
- [ ] DEV: Implement backend factory + backend sharing in Session (Decision 9); per-agent override creates a fresh backend
- [ ] TEST: Session lifecycle, spawn, recursion limits, event aggregation, inter-agent messaging, backward compatibility for single-agent use
- [ ] DOCS: Update `docs/rationale.md`, `CLAUDE.md`, `analysis/mbi-003-python-api-design.md`
- [ ] CHECK: `make check` green; existing examples unchanged for single-agent use

**Acceptance Criteria (mapped to the 10 owner decisions):**
- [ ] D1/D4: `Session` is an async context manager (`async with Session(config=...) as session:`) that owns the `AgentRegistry`, tracks recursion depth, and aggregates events from all agents
- [ ] D2: Agents are addressable by a unique name generated by the Session; the Session maintains the name→agent map
- [ ] D3: Inter-agent messages use the `Message(from, to, content, metadata)` dataclass with plain-string content; streaming inter-agent messages are deferred
- [ ] `Agent` no longer holds `agents`, `recursion_depth`, or `max_recursion_depth`; single-agent `process()` works unchanged
- [ ] D8: `Session.spawn(name, prompt, timeout=...)` is canonical; the `agent` tool is a thin wrapper calling `ctx.session.spawn(...)`; `ToolContext` carries a `session` reference; the tool is identical from the model's perspective
- [ ] D5: Events from spawned agents are visible to handlers registered on the Session, tagged with `agent_id`; `UIHandler` has optional `agent_spawned(name)`/`agent_finished(name)` with no-op defaults in `BaseUIHandler`
- [ ] D6: `run_session()` renamed to `run_repl`; `main()` constructs the Session
- [ ] D7: Config has a `[session]` section (`max_agents`, `default_isolation_policy`, `event_aggregation`); per-agent overrides use `dataclasses.replace`
- [ ] D9: Session owns a backend factory and shares backends across agents with the same provider config; per-agent model/provider overrides get a fresh backend
- [ ] D10: `AgentRegistry` lives on Session; `Agent.agents` is removed; agents retain a list of names they may spawn through the Session
- [ ] `python -m yoker` interactive mode works unchanged for the user
- [ ] Existing examples (`library_usage.py`, `batch_mode.py`, `research_workflow.py`) continue to work without modification
- [ ] New `examples/session_demo.py` demonstrates spawning multiple agents in one session
- [ ] `make check` green
- [ ] `docs/rationale.md` updated to reflect real multi-agent support

**Dependencies:** MBI-006 Phase 1 complete (DONE) — for backend sharing across providers. **MBI-007 must merge to master before MBI-003 resumes** (owner closing directive, PR #42).

**Out of scope (deferred):** Inter-agent streaming communication (request-response only in MBI-007); shared context policy beyond `fresh` and `fork`; full session persistence/resumption (one coherent session record); sub-sessions / hierarchical sessions; backend connection pooling.

**Design status:** All 10 design decisions resolved (see `analysis/session-concept-analysis.md` §7). No open design decisions remain. Ready for implementation task breakdown.

---

### MBI-003: Python API

**Goal:** Python developers can easily integrate agentic (sub-)workflows in Python function calls, with a clean utility API wrapping the current class-oriented architecture. Example: `yoker.execute_skill("skill-name", "prompt")` or even `from package.skills import skill_name; skill_name("prompt")`.

**Value:** Makes yoker developer-friendly, removing all hurdles to quick integration. Developers can use yoker without understanding internal classes.

**Status:** On Hold — blocked on MBI-007 (Session) merging to master (owner closing directive, PR #42). The MBI-003 PR is also on hold until MBI-007 lands.

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

**Dependencies:** MBI-002 (Bootstrap) for first-time users; **MBI-007 (Session) — hard blocker: MBI-007 must merge to master before MBI-003 resumes.** The `yoker.session()` workflow primitive in Layer 3 builds on the real Session construct. The Config factory (owner request, PR #42 Comment 1) is also part of MBI-003.

**Note:** The Config factory requirement was raised by the owner in PR #42 Comment 1 and is recorded in `analysis/session-concept-analysis.md` §7.2. It belongs to MBI-003, not MBI-007, and should be addressed when MBI-003 resumes after MBI-007.

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

