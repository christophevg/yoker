# TODO

## Priority Overview

| Priority | MBI/Task | Status |
|----------|----------|--------|
| **P1** | MBI-006: Multi-Provider Backend (Phase 1) | Complete |
| **P1** | MBI-006 Phase 2: LitellmBackend | Ready to start |
| **P1** | MBI-002: Bootstrap | Wrapping up |
| **P1** | MBI-001 Validation | Pending (validate with pkgq, then publish) |
| **P2** | MBI-003: Python API | Backlog (after Bootstrap) |
| **P2** | MBI-004: yoker Commands | Backlog (after Python API) |
| **P2** | MBI-005: Assistant Integration | Backlog (showcase project) |
| **P3** | Maintenance Tasks | M.1-M.4 |
| **P3** | Maintenance Tasks | M.6 (done in MBI-006 Phase 1) |
| **P4+** | Launch Preparation, Architecture, Future Work | See sections below |

---

## Active: MBI-002: Bootstrap

**Goal:** Interactive guided setup for first-time users without configuration.

**Milestone:** Users run `yoker` and are guided through backend selection, model selection, Ollama account creation, and config creation.

### Tasks

- [ ] **2.0 Change Config Default Model to `gemini-3-flash-preview:cloud` (single location)**
  - Update **only** `OllamaConfig.model` in `src/yoker/config/__init__.py` from
    `llama3.2:latest` to `gemini-3-flash-preview:cloud`. This is the **single
    source** of the default model (owner PR #34 point 1).
  - Audit the codebase for any other location referencing a default model
    (literals in `src/`, tests, docs, examples, agent defaults). Any code that
    needs the default must obtain it from the `Config` class (e.g.
    `Config().backend.ollama.model`), not by redefining the literal. Test
    assertions and docs that currently hardcode `llama3.2:latest` are updated to
    the new default or to read it from `Config`.
  - Rationale (owner): frictionless first run — cloud model, no local download
    needed. `llama3.2:latest` would force a download on first use.
  - This default is referenced by the wizard's Step 5 curated list (via
    `Config()`, not a literal) and by the generated config.
  - Write unit tests (assert the single default value; verify no duplicate
    default literals remain in `src/`).
  **Satisfies:** Frictionless default model
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q2 + task 2.0; PR #34 point 1)

- [ ] **2.1 Detect Missing Configuration (`config_provided() -> bool`)**
  - Implement `config_provided() -> bool` in `src/yoker/bootstrap/detect.py`
    (owner PR #34 point 2 — replaces the `ConfigStatus` / `detect_config()` /
    state-machine design).
  - "Provided" means the user induced any config source: `~/.yoker.toml` exists,
    `./yoker.toml` exists, or CLI args override defaults. No field-presence
    check, no `REQUIRED_CONFIG_FIELDS`, no `missing/incomplete/complete` state.
  - Trigger: `if not config_provided(): <wizard or warn-and-exit>`.
  - Wire into `__main__.py::main()` as a pre-flight check before `Agent()`;
    library mode (`Agent(config=...)`) skips detection.
  - Edge cases: empty TOML file exists → `True` (sparse is still provided);
    malformed TOML → `ConfigurationError` (not silent); permission denied →
    error; dangling symlink → treated as not existing.
  - **Write unit tests for the logic** (boolean, file-existence, CLI-arg
    detection) — this is logic, not IO.
  **Satisfies:** Bootstrap trigger condition
  **API design:** See `analysis/bootstrap-config-detection.md`.

- [ ] **2.2 Welcome & Guided-vs-Manual Flow**
  - Step 0: explain yoker (provider-neutral AI backend for agentic workflows)
  - Step 1: report no config found; offer guided (recommended) vs manual setup
  - Manual path: print config skeleton + docs link, exit without writing
  - All I/O via `UIHandler` (UI-layer separation intact)
  - **No unit tests** — pure IO/user interaction (owner PR #34 point 3);
    testing is user-driven.
  **Satisfies:** Bootstrap entry / low-friction onboarding
  **Design:** See `analysis/bootstrap-wizard-design.md`

- [ ] **2.3 Ollama Account & Connection-Method Steps**
  - Step 2: backend intro (single backend today: Ollama, free tier, no fake
    multi-way menu)
  - Step 3: "Do you have an ollama account?" → no: **open the docs guide URL**
    (may launch browser via `webbrowser.open()`), say we'll wait, then resume
    — the wizard does **not** abort or exit. yes: continue.
  - Step 4: split choice — (1) ollama app signed in (default backend, no API key)
    or (2) API key (masked input, optional guide link). Locked wording (app-first
    key-second):
    "Connect via: 1) The ollama app running locally (recommended — no key needed)
     2) An ollama API key"
  - Per-owner principle: least-possible steps to a minimal yet complete config
  - **No unit tests** — pure IO/user interaction (owner PR #34 point 3);
    testing is user-driven.
  **Satisfies:** Account/connection guidance
  **Design:** See `analysis/bootstrap-wizard-design.md`

- [ ] **2.4 Model Selection Wizard**
  - `modellist.py`: holds a **curated list** of recommended models (including
    the default, read from `Config().backend.ollama.model` — not a literal) plus
    a **free-text entry** option — **NO network call**. Live fetch via
    `AsyncClient.list()` / `GET /api/tags` was considered and **rejected** for
    first-install UX (owner: first-time install has no models pulled yet, so
    the tag list is empty/useless). Curated list + free text is the **primary
    and only** approach.
  - Step 5 prompt: pick from curated list / accept default / free text
  - Default model `gemini-3-flash-preview:cloud` (matches task 2.0's single
    Config default — cloud, no download needed)
  - **No unit tests** — pure IO/user interaction (owner PR #34 point 3);
    testing is user-driven.
  **Satisfies:** Model selection capability
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q2, Q5)

- [ ] **2.5 Config Writer (in the config module) & Continue into Session**
  - **Lives in `src/yoker/config/writer.py`**, NOT `yoker/bootstrap/writer.py`
    (owner PR #34 point 4). It is a general-purpose config-writing utility;
    the bootstrap wizard calls it, it does not own it. Reusable for in-session
    config augmentation (e.g. "add `plugins enabled = true` to your
    configuration?").
  - **Annotation-driven / generic** (owner PR #34 point 5): reads config-class
    metadata/`help` annotations to render full default `Config` → TOML with
    inline comments. Adding a config field requires NO writer change —
    instrument the config class instead. Never hardcode current field names.
  - Override only non-default values collected by wizard (model, optionally
    api_key/base_url); merge preserving unknown keys.
  - Write to user-level `~/.yoker.toml` (works across all yoker-based apps)
  - **`chmod 600`** every yoker config file written
  - API key stored **only** in `~/.yoker.toml`; never project config, never
    env var, never logged, never echoed
  - Brief confirmation that config was created (home-folder level, shared by
    all yoker-based apps) and that **yoker is continuing into the normal
    session now** — the user does NOT need to rerun `yoker`
  - **Return control to `__main__.py`**, which proceeds straight into normal
    Agent startup using the freshly-written config, as if a config had existed
    all along. The wizard does NOT exit the process or ask the user to relaunch.
  - **Write unit tests for the rendering logic** (TOML output, overrides,
    annotation-driven comments, chmod) — this is logic, not IO.
  **Satisfies:** Config creation capability (generic, reusable)
  **Design:** See `analysis/bootstrap-wizard-design.md` (Annotation-Driven
  ConfigWriter section; PR #34 points 4 & 5)

- [ ] **2.6 Non-Interactive Path & `__main__.py` Wiring**
  - Wire `config_provided()` → `BootstrapWizard` in interactive mode (async).
    The wizard returns after writing config; `__main__.py` then continues into
    normal Agent startup (does not exit after bootstrap).
  - Non-interactive mode (BatchUIHandler): do **not** instantiate wizard; print
    approved stderr warning and exit non-zero:
    "No yoker configuration found at ~/.yoker.toml.
     Run `yoker` interactively to configure, or see <docs URL>.
     Aborting (non-interactive mode)."
  - Library mode (`Agent(config=...)`) skips bootstrap entirely
  - **No unit tests for the wizard IO path** (owner PR #34 point 3); the
    boolean gate logic is tested in 2.1.
  **Satisfies:** Safe non-interactive behavior
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q3)

- [ ] **2.7 Bootstrap Documentation Guide (docs site)**
  - **One merged page** covering ollama account creation + local app/proxy
    install + (optional) API-key creation, with screenshots; optional per-OS
    variants
  - Wizard links to anchors within this page (account check, key creation)
  - Decision: one merged page (least duplication; resolved Q4)
  **Satisfies:** External account/install guidance (referenced by wizard)
  **Owner:** Confirmed new requirement
  **Design:** See `analysis/bootstrap-wizard-design.md` (Resolved Q4)

- [x] **2.8 End-to-end onboarding guide (Python/uv install → yoker → wizard → hello agent)** ✅ (2026-06-28)
  - New docs page `docs/guides/getting-started.md`: Python + uv setup (macOS,
    Windows, Linux), install yoker, run the bootstrap wizard, and perform a
    first "hello agent" interaction on Ollama's free tier.
  - Placed at the top of the `docs/index.md` toctree (entry point for new users).

---

## Active: MBI-006: Multi-Provider Backend Support (Phase 1)

**Goal:** Introduce the `ModelBackend` async Protocol and provider-neutral `ChatChunk` stream type, reimplement the existing Ollama behaviour on top of them, widen the config schema to the tagged-union shape, make subagent spawn provider-agnostic, and add optional stats fields to `TurnEndEvent`. **Pure refactor — no behaviour change, no new provider, no wizard changes.**

**Design source of truth:** `analysis/multi-provider-backend-design.md` §5 (Phase 1). Functional counterpart: `analysis/functional-multi-provider-backend.md`.

**Preconditions:** PRE-1 (M.5 — populate `Agent._tool_backends` for Ollama) — DONE/merged.

**Out of scope for Phase 1:** OpenAI backend, Anthropic backend, bootstrap wizard provider selection, `build_bootstrap_overrides` provider-awareness, web tools for non-Ollama providers, live API model discovery.

### Tasks

- [x] **[MBI-006] 6.1 Backends package: ModelBackend Protocol + ChatChunk types** ✅ (2026-06-29)
  - Create new `src/yoker/backends/` package
  - `src/yoker/backends/protocol.py`: define `ModelBackend` async Protocol with
    `provider` property and `chat_stream(*, model, messages, tools, think, **kwargs) -> AsyncIterator[ChatChunk]` (signature per design §4.3; `**kwargs` purely internal per Q20)
  - `src/yoker/backends/protocol.py`: define provider-neutral stream types:
    `ChatChunkEvent` enum (CONTENT_START/DELTA/STOP, THINKING_START/DELTA/STOP, TOOL_CALL_START/DELTA/STOP, USAGE, DONE), `ToolCallDelta` (index, id, name, arguments_delta), `UsageStats` (input_tokens, output_tokens, prompt_eval_count, eval_count, total_duration_ms), and `ChatChunk` (event, index, text, tool_call, usage) — per design §4.2
  - `src/yoker/backends/__init__.py`: re-export `ModelBackend`, `ChatChunk`, `ChatChunkEvent`, `ToolCallDelta`, `UsageStats` (and `create_backend` once 6.5 lands)
  - Design `ChatChunk` to accommodate Anthropic's block-style streaming even though Anthropic is Phase 3 (explicit `index` for block indexing; START/DELTA/STOP bracketing)
  - Write unit tests asserting the dataclasses are frozen and field defaults are correct
  - **Acceptance:**
    - `from yoker.backends import ModelBackend, ChatChunk, ChatChunkEvent, ToolCallDelta, UsageStats` works
    - `ChatChunk` is frozen; exactly one of `text`/`tool_call`/`usage` is set per `event`
    - `UsageStats` preserves Ollama-native fields (`prompt_eval_count`/`eval_count`/`total_duration_ms`) alongside `input_tokens`/`output_tokens`
    - `make check` green (no existing tests modified)
  **Satisfies:** Protocol + neutral stream type foundation
  **Depends on:** —

- [x] **[MBI-006] 6.2 TurnEndEvent: optional input_tokens/output_tokens stats fields** ✅ (2026-06-29)
  - `src/yoker/events/types.py`: add `input_tokens: int = 0` and `output_tokens: int = 0` to `TurnEndEvent` (Q15)
  - Keep Ollama-native `prompt_eval_count`/`eval_count`/`total_duration_ms` for backwards compatibility
  - Non-breaking: defaults of 0 preserve existing behaviour
  - Update UIBridge/stats display to read whichever is non-zero (UI reads `input_tokens`/`output_tokens` when Ollama-native fields are 0)
  - Write unit tests asserting new fields default to 0 and existing Ollama-native stats still populate
  - **Acceptance:**
    - `TurnEndEvent` has `input_tokens` and `output_tokens` fields defaulting to 0
    - Existing Ollama sessions still populate `prompt_eval_count`/`eval_count`/`total_duration_ms`
    - All existing event tests pass without modification
  **Satisfies:** Provider-agnostic stats surface
  **Depends on:** —

- [x] **[MBI-006] 6.3 Config tagged-union shape + Clevis CLI args** ✅ (2026-06-29)
  - `src/yoker/config/__init__.py`: widen `BackendConfig` to discriminated-dataclass shape — add `openai: OpenAIConfig | None = None` and `anthropic: AnthropicConfig | None = None` Optional fields (Q2)
  - Forward-declare `OpenAIConfig`/`AnthropicConfig` stubs under `TYPE_CHECKING` (Phase 2/3 populate them; Phase 1 only needs the field slots to exist with `None` defaults)
  - Widen `provider` whitelist from `("ollama",)` to `("ollama", "openai", "anthropic")` so the choice arg lists all future providers, but only wire the ollama validation guard in `__post_init__` (require `backend.ollama` when `provider == "ollama"`; openai/anthropic guards added in Phase 2/3)
  - Keep `OllamaParameters.top_k`/`num_ctx` Ollama-specific (Q4); do NOT introduce a shared parameter base class
  - Keep `provider` default `"ollama"` (Q9)
  - Verify Clevis auto-generates `--backend-provider {ollama,openai,anthropic}` and `--backend-openai-*` / `--backend-anthropic-*` args (default None, ignored at runtime in Phase 1)
  - Write unit tests: default `BackendConfig()` yields `provider="ollama"`, `openai=None`, `anthropic=None`; old TOML files (single-Ollama shape) still load (Q8 — strict superset, no migration); `provider="openai"` with `openai=None` does NOT raise in Phase 1 (guard only enforces ollama) — or raises a clear `ValidationError` per design §4.5; pick the behaviour consistent with the design note and document it
  - **Acceptance:**
    - `BackendConfig()` defaults to `provider="ollama"` with `openai`/`anthropic` None
    - Existing `~/.yoker.toml` files load unchanged (no migration script)
    - `--backend-provider` lists all three providers; `--backend-openai-*`/`--backend-anthropic-*` args exist and default to None
    - `make check` green
  **Satisfies:** Config schema superset for all three phases
  **Depends on:** —

- [x] **[MBI-006] 6.4 render_config_toml union-aware** ✅ (2026-06-29)
  - `src/yoker/config/writer.py::render_config_toml`: confirm the generic dataclass walk omits `None` per-provider sub-configs; add explicit handling/tests if needed (Q7 split — writer stays in Phase 1 because it lives in the config module and is reusable)
  - Do NOT touch `build_bootstrap_overrides` (wizard-specific, deferred with §8)
  - Write unit tests asserting a config with `openai=None`/`anthropic=None` writes a TOML file with no `[backend.openai]`/`[backend.anthropic]` section, and that the written file round-trips back to an equal `BackendConfig`
  - **Acceptance:**
    - `render_config_toml` omits `None` per-provider sub-configs
    - Round-trip: `load(render_config_toml(cfg)) == cfg` for an Ollama-only config
    - `make check` green
  **Satisfies:** Config writer union-awareness (reusable, non-wizard)
  **Depends on:** 6.3

- [x] **[MBI-006] 6.5 OllamaBackend adapter + create_backend factory** ✅ (2026-06-29)
  - `src/yoker/backends/ollama.py`: new `OllamaBackend` wrapping `ollama.AsyncClient`
    - Constructor builds the client from `config.backend.ollama` (relocate `agent/_setup.py::create_client` logic here — no behaviour change)
    - `provider` property returns `"ollama"`
    - `chat_stream(*, model, messages, tools, think, **kwargs)` calls `self._client.chat(model, messages, tools, think=think, stream=True)` and translates each native chunk into `ChatChunk`:
      - `message.thinking` -> `THINKING_START`/`THINKING_DELTA`/`THINKING_STOP` (synthesise START before first thinking delta, STOP at end of thinking)
      - `message.content` -> `CONTENT_START` (before first content delta) / `CONTENT_DELTA` / `CONTENT_STOP` (synthesise boundaries; Ollama is delta-style per design §4.2)
      - `message.tool_calls` -> `TOOL_CALL_START`/`TOOL_CALL_DELTA`/`TOOL_CALL_STOP` per call
      - `chunk.done` + native stats (`prompt_eval_count`/`eval_count`/`total_duration`) -> `USAGE` (populate `UsageStats` native fields) then terminal `DONE`
    - Preserves native `think=` flag mapping (Q11) and native stats (Q15)
  - `src/yoker/backends/factory.py`: new. `create_backend(config) -> ModelBackend`; `BACKENDS = {"ollama": lambda cfg: OllamaBackend(cfg)}` only in Phase 1. Unknown provider raises `ConfigurationError` listing configured providers (Q10 — no silent fallback)
  - `src/yoker/agent/_setup.py`: remove `create_client()` (moved into `OllamaBackend`); keep `create_web_guardrails`, `validate_recursion_depth`, `add_skill_discovery_block` unchanged
  - Write unit tests:
    - `create_backend(Config())` returns an `OllamaBackend` instance
    - `create_backend` with unknown provider raises `ConfigurationError` naming configured providers
    - `OllamaBackend.chat_stream` fed a recorded Ollama chunk sequence emits `CONTENT_START` before first `CONTENT_DELTA`, `THINKING_START`/`STOP` around thinking deltas, `TOOL_CALL_START`/`DELTA`/`STOP` per call, and a terminal `DONE` with `UsageStats` populated from native fields
  - **Acceptance:**
    - `create_backend(Config())` is an `OllamaBackend`
    - Unknown provider -> `ConfigurationError` (Agent never starts)
    - `OllamaBackend.chat_stream` emits the documented `ChatChunk` event sequence with synthesised block boundaries
    - `make check` green
  **Satisfies:** Ollama adapter on the new Protocol + factory dispatch
  **Depends on:** 6.1, 6.3

- [x] **[MBI-006] 6.6 Agent wiring: _backend, _resolve_model, _chat_stream, _consume_stream rewrite** ✅ (2026-06-29)
  - `src/yoker/agent/agent.py`:
    - Replace `self._client: AsyncClient | None` with `self._backend: ModelBackend | None`
    - Replace `create_client(self.config, AsyncClient)` with `create_backend(self.config)`
    - Keep optional `backend: ModelBackend | None = None` injection param (renamed from `client`)
    - `_resolve_model()`: read from the active provider's sub-config, not `config.backend.ollama.model` directly. Introduce helper `_active_backend_config(config)` (or `getattr(config.backend, config.backend.provider)`) — keep returning the Ollama model in Phase 1
  - `src/yoker/agent/_processing.py`:
    - `_chat_stream()`: replace `agent._client.chat(...)` with `agent._backend.chat_stream(model=..., messages=..., tools=..., think=...)`
    - `_consume_stream()`: rewrite to iterate `ChatChunk` instead of Ollama-native chunks. Map `ChatChunkEvent` to existing `Event` types (ThinkingStart/Chunk/End, ContentStart/Chunk/End, ToolCallEvent). Accumulate tool calls from `TOOL_CALL_START`/`DELTA`/`STOP`. Build `TurnEndEvent` from `UsageStats`: map `prompt_eval_count`/`eval_count`/`total_duration_ms` to native fields; fall back to `input_tokens`/`output_tokens` for non-Ollama (set native fields to 0 when absent)
  - Add a golden-stream unit test: feed a recorded sequence of `ChatChunk` through `_consume_stream` and assert the emitted `Event` sequence matches a captured Ollama session (design §5.4 acceptance)
  - Do NOT change event types (beyond 6.2), UIBridge mapping, or UI handlers
  - **Acceptance:**
    - All existing tests pass without modification (behaviour unchanged)
    - Golden-stream test: recorded `ChatChunk` sequence -> expected `Event` sequence
    - Ollama round-trip works exactly as before through the new Protocol (interactive + batch)
    - `make check` green
  **Satisfies:** Agent hot path on the new Protocol
  **Depends on:** 6.5, 6.2

- [x] **[MBI-006] 6.7 Subagent spawn provider-agnostic** ✅ (2026-06-29)
  - Introduce `with_model(backend: BackendConfig, model: str) -> BackendConfig` helper in `src/yoker/backends/__init__.py` (or `config` module) — returns a copy of `backend` with `model` overridden on the active sub-config via `getattr`/`dataclasses.replace` (design §9.3)
  - `src/yoker/builtin/agent.py::_create_subagent`: replace the hardcoded `BackendConfig(provider=..., ollama=OllamaConfig(...))` rebuild with the provider-agnostic copy using `with_model`
  - `src/yoker/bootstrap/modellist.py`: read default model from the active provider config (helper), not `config.backend.ollama.model` directly. Curated list stays Ollama-only in Phase 1
  - Phase 1 implements `with_model` for `ollama` only; Phase 2/3 extend to `openai`/`anthropic`
  - Write unit tests: subagent spawn produces a `Config` whose `backend` is a faithful copy of the parent's with only the model overridden, regardless of provider (test under `provider="ollama"`)
  - **Acceptance:**
    - Subagent `Config.backend` equals parent's `backend` with only `model` overridden
    - No hardcoded `OllamaConfig` rebuild in `_create_subagent`
    - `make check` green
  **Satisfies:** Provider-agnostic subagent spawn
  **Depends on:** 6.3, 6.6

- [x] **[MBI-006] 6.8 Phase 1 verification** ✅ (2026-06-29)
  - Run `make check` end-to-end (format, lint, typecheck, test) — all green
  - Verify no existing tests were modified to make the refactor pass (behaviour unchanged)
  - Verify `~/.yoker.toml` written by the wizard still produces a working Ollama session (round-trip unchanged — manual or integration check)
  - Verify `render_config_toml` writes a config with `openai`/`anthropic` absent when those sub-configs are `None`
  - Verify `create_backend(Config())` returns an `OllamaBackend` and unknown provider raises `ConfigurationError`
  - Confirm wizard files (`bootstrap/wizard.py`, `bootstrap/steps.py`) are unchanged (deferred per §8)
  - Confirm `build_bootstrap_overrides` is NOT touched (deferred with the wizard)
  - Confirm web tools (`websearch`/`webfetch`) under Ollama still work (PRE-1 base) and are not extended to other providers
  - **Acceptance:**
    - `make check` green; zero behaviour change on the Ollama path
    - All Phase 1 design §5.4 acceptance criteria verified
    - No wizard changes; no `build_bootstrap_overrides` changes; no new provider wired
  **Satisfies:** Phase 1 completion gate
  **Depends on:** 6.1-6.7

---

## Active: MBI-006 Phase 2: LitellmBackend for Multi-Provider Support

**Goal:** Implement `LitellmBackend` wrapping the litellm library to support OpenAI, Anthropic, and 100+ other providers through a unified interface.

**Design source of truth:** `analysis/dual-backend-architecture.md` (Phase 2). This replaces the original Phase 2 (OpenAI backend) and Phase 3 (Anthropic backend) with a single unified approach.

**Architecture decision:** Dual backend — OllamaBackend (Phase 1, native SDK) for Ollama, LitellmBackend (Phase 2, new) for all other providers.

**Out of scope for Phase 2:** Bootstrap wizard provider selection, `build_bootstrap_overrides` provider-awareness, live API model discovery for non-Ollama providers, extending web tools to non-Ollama providers.

### Tasks

- [ ] **[MBI-006] 8.1 Add litellm dependency**
  - Add `litellm>=1.90.0` to `pyproject.toml` dependencies
  - Run `uv sync` to install the dependency
  - Verify litellm supports Ollama, OpenAI, Anthropic in dependency documentation
  - **Acceptance:**
    - `litellm>=1.90.0` in `pyproject.toml`
    - `uv lock` updated with litellm and its transitive dependencies
    - Import `litellm` succeeds in Python environment
  **Satisfies:** Dependency foundation for LitellmBackend
  **Depends on:** —

- [ ] **[MBI-006] 8.2 Create LitellmBackend implementation**
  - Create `src/yoker/backends/litellm.py` with `LitellmBackend` class
  - Implement `ModelBackend` Protocol from `backends/protocol.py`
  - Constructor takes Yoker config, extracts provider credentials
  - `provider` property returns current provider name
  - `chat_stream()` method:
    - Map Yoker model to litellm model string (`ollama/llama3.2`, `openai/gpt-4o`, `anthropic/claude-sonnet-4`, etc.)
    - Call `litellm.acompletion()` with streaming enabled
    - Translate `ModelResponseStream` chunks to Yoker `ChatChunk` events
    - Synthesize START/STOP events (litellm only emits deltas)
    - Handle `reasoning_content` for thinking/reasoning models
  - Write unit tests with mocked litellm
  - **Acceptance:**
    - `LitellmBackend` implements all `ModelBackend` Protocol methods
    - Constructor extracts API keys from provider-specific config
    - `chat_stream()` returns `AsyncIterator[ChatChunk]`
    - Model string mapping works for OpenAI, Anthropic, and Ollama prefixes
  **Satisfies:** LitellmBackend core implementation
  **Depends on:** 8.1

- [ ] **[MBI-006] 8.3 Implement stream translation**
  - Create `_translate_chunk()` method in LitellmBackend
  - Translate litellm's `ModelResponseStream` to Yoker's `ChatChunk`
  - State tracking for `CONTENT_START`/`CONTENT_STOP` synthesis
  - State tracking for `THINKING_START`/`THINKING_STOP` synthesis (from `reasoning_content`)
  - State tracking for `TOOL_CALL_START`/`TOOL_CALL_STOP` synthesis
  - Emit `USAGE` with `input_tokens`/`output_tokens` from litellm usage stats
  - Emit terminal `DONE` after final chunk
  - Handle litellm exceptions gracefully (network errors, rate limits, auth errors)
  - Write unit tests with recorded chunk sequences
  - **Acceptance:**
    - Delta-only litellm chunks correctly synthesized into START/DELTA/STOP sequences
    - `reasoning_content` mapped to THINKING events
    - Tool calls properly bracketed with START/STOP
    - USAGE event contains token counts from litellm
    - Terminal DONE event always emitted (even on error)
  **Satisfies:** Stream translation layer
  **Depends on:** 8.2

- [ ] **[MBI-006] 8.4 Register LitellmBackend in factory**
  - Update `src/yoker/backends/factory.py`
  - Map OpenAI, Anthropic, and other providers to `LitellmBackend`
  - Keep Ollama mapping to `OllamaBackend` (dual backend architecture)
  - Unknown providers default to `LitellmBackend` (leverages litellm's 100+ providers)
  - Import `LitellmBackend` in `backends/__init__.py`
  - Write unit tests asserting correct backend instantiation per provider
  - **Acceptance:**
    - `create_backend(Config(backend=BackendConfig(provider="openai")))` returns `LitellmBackend`
    - `create_backend(Config(backend=BackendConfig(provider="anthropic")))` returns `LitellmBackend`
    - `create_backend(Config(backend=BackendConfig(provider="ollama")))` returns `OllamaBackend`
    - Unknown provider like `"groq"` returns `LitellmBackend` (litellm handles it)
  **Satisfies:** Factory dispatch for dual backend
  **Depends on:** 8.2

- [ ] **[MBI-006] 8.5 Preserve base_url trust boundary**
  - Keep existing trust boundary validation from Phase 1 (OllamaBackend)
  - Apply to all providers (not just Ollama)
  - `base_url` warning/confirmation for custom endpoints
  - Batch mode `YOKER_ALLOW_CUSTOM_BASE_URL` environment variable support
  - Document security implications in code comments
  - Write unit tests for trust boundary behavior
  - **Acceptance:**
    - Custom `base_url` triggers warning in interactive mode
    - Batch mode requires `YOKER_ALLOW_CUSTOM_BASE_URL=1` for custom endpoints
    - Behavior consistent across Ollama, OpenAI, Anthropic providers
  **Satisfies:** Security: base_url validation
  **Depends on:** 8.2

- [ ] **[MBI-006] 8.6 Configure litellm from Yoker config**
  - Extract API key from provider-specific config (`config.backend.openai.api_key`, `config.backend.anthropic.api_key`, etc.)
  - Map provider-specific parameters to litellm kwargs (`num_ctx`, `budget_tokens`, etc.)
  - Handle `think` flag mapping:
    - OpenAI o-series: `reasoning_effort` parameter
    - Anthropic: `budget_tokens` parameter
    - Other providers: pass through or warn
  - Support all Phase 1 config fields (`model`, `base_url`, `api_key`)
  - Write unit tests for config mapping
  - **Acceptance:**
    - API keys correctly extracted from provider sub-configs
    - Provider-specific parameters passed to litellm
    - `think` flag mapped appropriately per provider
    - Missing API key raises clear `ConfigurationError`
  **Satisfies:** Config → litellm parameter mapping
  **Depends on:** 8.2, 8.4

- [ ] **[MBI-006] 8.7 Verify web tools dispatch**
  - Verify web tools (`websearch`/`webfetch`) still work with Ollama (native SDK path)
  - Verify graceful failure for non-Ollama providers
  - `Agent._create_tool_backends()` only populates web backends when `provider == "ollama"`
  - No changes to web tools implementation (they remain Ollama-specific)
  - Write unit tests asserting web tools behavior per provider
  - **Acceptance:**
    - Ollama provider: web tools populated and functional
    - OpenAI provider: web tools not populated (no error)
    - Anthropic provider: web tools not populated (no error)
    - Attempting to use web tools with non-Ollama provider raises clear error
  **Satisfies:** Web tools dual-backend behavior
  **Depends on:** 8.4

- [ ] **[MBI-006] 8.8 Update with_model helper**
  - Extend `with_model()` helper from Phase 1 to support LitellmBackend
  - Model override works for all litellm providers (simple prefix change in model string)
  - Ollama model override continues to work (Phase 1 behavior)
  - Write unit tests for all providers
  - **Acceptance:**
    - `with_model(backend, "gpt-4o")` produces correct config for OpenAI
    - `with_model(backend, "claude-sonnet-4")` produces correct config for Anthropic
    - `with_model(backend, "llama3.2")` produces correct config for Ollama
    - Unknown provider model strings work via litellm prefix logic
  **Satisfies:** Provider-agnostic model override
  **Depends on:** 8.4, 8.6

- [ ] **[MBI-006] 8.9 Phase 2 verification**
  - Run `make check` end-to-end (format, lint, typecheck, test) — all green
  - Verify no existing tests modified (behaviour unchanged for Ollama path)
  - Write integration tests with mocked OpenAI/Anthropic API responses
  - Optional: integration tests with real OpenAI API (requires API key)
  - Verify `create_backend()` returns `LitellmBackend` for non-Ollama providers
  - Verify `TurnEndEvent` carries `input_tokens`/`output_tokens` from litellm
  - Verify `base_url` trust boundary enforcement
  - **Acceptance:**
    - `make check` green
    - Ollama path unchanged (all existing tests pass)
    - OpenAI backend works end-to-end (mocked or real API)
    - Anthropic backend works end-to-end (mocked or real API)
    - Web tools work with Ollama, fail gracefully with others
    - Native Ollama features preserved (stats, thinking, web tools)
    - Phase 2 acceptance criteria from `analysis/dual-backend-architecture.md` verified
  **Satisfies:** Phase 2 completion gate
  **Depends on:** 8.1-8.8

---

## MBI-001 Validation: Package Plugin System

**Goal:** Final validation before MBI-001 closure.

- [ ] **1.1 Validate with pkgq Project**
  - Test plugin system with pkgq project locally
  - Verify all acceptance criteria work
  - Document any issues found
  **Priority:** P1

- [ ] **1.2 Publish Release to PyPI**
  - Finalize pyproject.toml metadata
  - Test installation from source distribution
  - Upload to TestPyPI
  - Upload to PyPI
  **Priority:** P1
  **Note:** Requires release manager credentials

---

## Maintenance Tasks

Unsorted improvements and fixes.

- [ ] **M.1 Rename yoker: plugin tools to builtin:**
  - Rename namespace from `yoker:` to `builtin:`
  - When listing tools (e.g. /tools), don't include the `builtin:` prefix
  - Update documentation
  **Priority:** P3

- [ ] **M.2 Default Tools Behavior**
  - When agent has no explicit tools configuration, ALL tools should be available
  - Update agent initialization logic
  - Write unit tests
  **Priority:** P3

- [ ] **M.3 Namespace Frontmatter Configuration**
  - Allow namespace configuration in skill and agent frontmatter
  - Update SkillLoader and AgentLoader
  - Write unit tests
  **Priority:** P3

- [ ] **M.4 Clean Up Duplicate Tests**
  - Review all tests for duplicates (e.g. tests/test_tools/test_base.py and tests/tools/test_base.py)
  - Consolidate duplicate tests
  - Ensure full coverage maintained
  **Priority:** P4

- [x] ✅ **M.5 Populate `Agent._tool_backends` for Ollama web tools (prerequisite for multi-provider backend)**
  - `Agent._tool_backends` is initialised to `{}` and never populated, so the
    `websearch` and `webfetch` built-in tools already fail today with
    "No backend configured" regardless of provider. This is a pre-existing bug
    independent of the multi-provider backend design.
  - Fix scope: populate `Agent._tool_backends` with the
    `OllamaWebSearchBackend` / `OllamaWebFetchBackend` instances when the
    configured provider is Ollama, so the web tools actually work. Keep it small
    and focused — this is a bug fix, not a feature.
  - **Prerequisite for:** the multi-provider backend work
    (`analysis/multi-provider-backend-design.md`). The design note documents
    this gap (§7.4 and §9.17 Q17 Option B) and the owner has decided to fix it
    as a separate precondition before the backend phases begin. Do this before
    Phase 1 of the multi-provider backend effort.
  - Write unit tests asserting the `websearch` / `webfetch` backends are
    populated under the Ollama provider and that the tools execute successfully.
  - Do not extend web tools to non-Ollama providers — that remains out of scope
    (design note §7.4); the multi-provider backend effort will handle the
    "Ollama provider required" error path for other providers.
  **Priority:** P2
  **Date:** 2026-06-28

- [x] **M.6 Exclude api_key from Clevis CLI generation** ✅ (2026-06-29)
  - Clevis released `metadata={'cli': False}` support (FR christophevg/clevis#30).
  - Implemented in Phase 1 task 6.3 as part of the config tagged-union + Clevis
    CLI args work (see MBI-006 task 6.3 acceptance criteria).
  - This is a follow-up to the multi-provider backend security review
    (`analysis/security-multi-provider-backend.md`, finding H1) and amends
    design decision Q6 (`analysis/multi-provider-backend-design.md` §11.6).
  - `api_key` fields on `OllamaConfig`/`OpenAIConfig`/`AnthropicConfig` will be
    annotated with `metadata={"cli": False}` in Phase 1 task 6.3; test asserts
    no `--backend-*-api-key` CLI arg is generated.
  **Priority:** P3
  **Date:** 2026-06-29

---

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


## Done: MBI-001: Package Plugin System (2026-06-25)

**Goal:** Enable Python packages to provide tools and skills to yoker via `yoker --with <package>`

**Status:** Core implementation complete. Validation with pkgq project pending before final PyPI release.

### Completed Phases

- [x] **Phase 2: Skill System (Core)** — Skill Infrastructure, Slash Commands, Skill Tool
- [x] **Phase 3: Package Plugin System** — Package Plugin Discovery, CLI --with Argument
- [x] **Phase 5: Polish** — Error Handling, Documentation, Testing
- [x] **Phase 6.2: Examples and Tutorials**

### Remaining

- See **MBI-001 Validation** section above for pkgq validation and PyPI release tasks

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

## Architecture Refactoring: Plugin Config Registration

**Goal:** Enable plugins to register configuration fields dynamically, allowing tool-specific settings without hardcoding in ToolsConfig.

**Related Analysis:**
- [Plugin Architecture](analysis/plugin-architecture.md)

### Phase 7: Config System Refactoring

**Status:** Design required

**Priority:** P5 (Post-MVP architectural improvement)

**Problem:** The current config system uses frozen dataclasses for `ToolsConfig`, which cannot be extended dynamically. Plugins added via `--with` need to register their own configuration fields (e.g., `[tools.pkgq]` settings). This requires architectural changes to the config system.

- [ ] **7.1 Plugin Config Registration System Design**
  - Analyze Clevis `register_field` mechanism
  - Design plugin config registration API
  - Determine how plugins register their config schema
  - Design config discovery and validation flow
  - Document interaction with existing `WebGuardrailConfig` duplication
  - **Priority:** P5
  - **Estimated time:** 4-6 hours (design only)
  - **Note:** This is a design task. Implementation will be a separate task.

- [ ] **7.2 ToolsConfig Dynamic Extension**
  - Change `ToolsConfig` from frozen to mutable dataclass
  - Implement `register_tool_config(name: str, config_class: type)` API
  - Support config field injection at runtime
  - Update existing hardcoded tool configs to use registration pattern
  - **Depends on:** 7.1
  - **Priority:** P5
  - **Estimated time:** 8-12 hours
  - **Note:** Requires Clevis support or local workaround

- [ ] **7.3 Consolidate WebGuardrailConfig Classes**
  - Remove `WebGuardrailConfig` duplication between `tools/web/guardrail.py` and `config/__init__.py`
  - Create single unified `WebGuardrailConfig` class
  - Update `WebSearchToolConfig` and `WebFetchToolConfig` to compose guardrail config
  - Ensure config passes guardrail settings directly to guardrails
  - Update `agent/_setup.py` to use consolidated config classes
  - **Depends on:** 7.2
  - **Priority:** P5
  - **Estimated time:** 2-4 hours
  - **Note:** This task should NOT be done separately. It depends on the plugin config registration system being in place first, because:
    1. The duplication exists because `ToolsConfig` is frozen
    2. When plugins can register config fields, the pattern will change
    3. Hardcoded `WebSearchToolConfig`/`WebFetchToolConfig` will become anti-patterns
    4. Consolidating now would create a pattern that contradicts the plugin system design

**Rationale for Dependency Order:**
- Item 7.1 must complete first to establish the design
- Item 7.2 implements the mechanism that plugins will use
- Item 7.3 consolidates existing configs using the new mechanism
- Doing 7.3 before 7.2 would create throwaway code that contradicts the plugin architecture

**Related Issue:** The duplication in `WebGuardrailConfig` classes is currently intentional:
- `tools/web/guardrail.py::WebGuardrailConfig` is a runtime guardrail config (unfrozen)
- `config/__init__.py::WebSearchToolConfig`/`WebFetchToolConfig` are frozen TOML configs
- `agent/_setup.py` converts frozen configs to runtime configs
- This is a workaround that will be eliminated by proper plugin config registration

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

