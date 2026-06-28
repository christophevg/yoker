# Multi-Provider Backend — Functional Analysis

**Date:** 2026-06-28
**MBI:** MBI-006 — Multi-Provider Backend Support
**Status:** Phase 1 task breakdown ready for implementation
**Related:**
- `analysis/multi-provider-backend-design.md` — design source of truth (finalized, owner-approved; all 20 decisions in §11 resolved)
- `PLAN.md` — MBI-006 entry (Active)
- `TODO.md` — Phase 1 tasks 6.1-6.8

This document is the functional counterpart to the api-architect's design note. It does not re-design the architecture; it translates the owner-approved design into an MBI goal, a phased plan, and atomic Phase 1 tasks with verifiable acceptance criteria.

---

## 1. MBI Goal

Make Yoker provider-neutral at the model layer. A single `ModelBackend` async Protocol abstracts chat streaming; the Agent talks to a backend instance, not to `ollama.AsyncClient` directly. Ollama, OpenAI, and Anthropic each ship as a backend implementation behind the same Protocol. The config schema becomes a tagged-union shape carrying per-provider sub-configs and per-provider parameters.

**Value:** Removes vendor lock-in at the model layer. Users switch Ollama / OpenAI / Anthropic by changing one config field, without touching their agentic workflows. Establishes the abstraction seam that lets future providers land without Agent hot-path changes.

---

## 2. Three-Phase Plan (brief)

| Phase | Scope | Size | Behaviour change |
|---|---|---|---|
| **Phase 1** — Protocol + Ollama Refactor | Introduce `ModelBackend` Protocol + `ChatChunk`; reimplement Ollama on it; widen config to tagged-union; provider-agnostic subagent spawn; `TurnEndEvent` stats fields; `render_config_toml` union-aware. | M | None (pure refactor) |
| **Phase 2** — OpenAI | Add `OpenAIBackend` (`openai` SDK); per-provider curated model list; `OpenAIConfig`/`OpenAIParameters`. | M | New provider available |
| **Phase 3** — Anthropic | Add `AnthropicBackend` (`anthropic` SDK); block-style stream translation; message-shape rewrite (system extraction, tool_use/tool_result blocks); tool-schema translation; SSE parsing; `max_tokens`/`budget_tokens` thinking config. | L | New provider available |

**Ordering (Q19):** sequential — Phase 1 is a hard prerequisite for Phases 2 and 3; Phase 2 then Phase 3 (Phase 2's patterns inform Phase 3).

---

## 3. Phase 1 Scope

**Pure refactor — no behaviour change, no new provider, no wizard changes.**

### 3.1 In scope

- New `src/yoker/backends/` package with:
  - `ModelBackend` async Protocol (`chat_stream(*, model, messages, tools, think, **kwargs) -> AsyncIterator[ChatChunk]`)
  - Provider-neutral `ChatChunk` dataclass (content, thinking, tool_calls, done, stats) — designed to accommodate Anthropic's block-style streaming even though Anthropic is Phase 3 (explicit `index` for block indexing; START/DELTA/STOP bracketing)
  - `OllamaBackend` adapter wrapping the existing `ollama.AsyncClient` (relocates current `_consume_stream`/`create_client` logic into the adapter — no behaviour change)
  - `create_backend(config)` factory dispatching on `config.backend.provider` (only `ollama` wired in Phase 1)
- Config schema: widen `BackendConfig` to the discriminated-dataclass shape (`provider: str` + `ollama`/`openai`/`anthropic` Optional sub-configs, only `ollama` populated/validated in Phase 1); widen `provider` whitelist to `("ollama","openai","anthropic")` but only wire ollama. Keep `OllamaParameters.top_k`/`num_ctx` Ollama-specific.
- `render_config_toml` (config writer) made union-aware (omits `None` per-provider sub-configs).
- Subagent spawn (`builtin/agent.py::_create_subagent`) made provider-agnostic via a `with_model(backend, model)` helper (no hardcoded `OllamaConfig` rebuild).
- `TurnEndEvent`: add optional `input_tokens`/`output_tokens` (default 0); keep Ollama-native fields for backwards compatibility.
- Agent hot path: `Agent._client` -> `Agent._backend`; `_resolve_model` reads active provider config; `_chat_stream` calls `backend.chat_stream`; `_consume_stream` rewritten to iterate `ChatChunk` and map to existing `Event` types.
- `bootstrap/modellist.py`: read default model from active provider config (helper); curated list stays Ollama-only.

### 3.2 Out of scope (deferred)

- **Bootstrap wizard provider selection** — the wizard's provider-selection step, `build_bootstrap_overrides` provider-awareness, and any per-provider wizard branching are deferred to a separate follow-up MBI on top of the merged bootstrap PR (design §8).
- **OpenAI backend** — Phase 2.
- **Anthropic backend** — Phase 3.
- **Web tools (`web_search`/`web_fetch`) for non-Ollama providers** — documented limitation; the current "No backend configured" failure is left as-is (Q16). Web tools stay Ollama-only across all three phases.
- **Live API model discovery** — curated hardcoded lists only (Q5); live fetch is a future enhancement.
- **Dropping the native Ollama SDK** — explicitly NOT a goal (Q1); native Ollama SDK support is preserved for native thinking semantics, native stats, and native web tools.
- **Non-streaming chat / embeddings / image generation / model management / provider billing UI** — out of scope.

### 3.3 Preconditions

| ID | Prerequisite | Status |
|---|---|---|
| PRE-1 (M.5) | Populate `Agent._tool_backends` for Ollama so `websearch`/`webfetch` resolve to `OllamaWebSearchBackend`/`OllamaWebFetchBackend` when `provider == "ollama"`. | **DONE** — merged 2026-06-28. Phase 1 references but does not perform this fix (Q17). |

---

## 4. Phase 1 Task Breakdown

Atomic tasks tagged `[MBI-006]` in `TODO.md`. Each task includes unit tests (TDD where applicable). The design note's acceptance criteria emphasize "tests green, behaviour unchanged."

### 6.1 Backends package: ModelBackend Protocol + ChatChunk types
**Scope:** Create `src/yoker/backends/` with `protocol.py` (`ModelBackend` Protocol, `ChatChunk`, `ChatChunkEvent`, `ToolCallDelta`, `UsageStats`) and `__init__.py` re-exports.
**Acceptance:**
- Public imports work: `from yoker.backends import ModelBackend, ChatChunk, ChatChunkEvent, ToolCallDelta, UsageStats`
- `ChatChunk` frozen; one of `text`/`tool_call`/`usage` set per `event`
- `UsageStats` preserves Ollama-native fields alongside `input_tokens`/`output_tokens`
- `make check` green
**Depends on:** —

### 6.2 TurnEndEvent: optional input_tokens/output_tokens stats fields
**Scope:** Add `input_tokens: int = 0` and `output_tokens: int = 0` to `TurnEndEvent`; keep Ollama-native fields; update UI stats display to read whichever is non-zero.
**Acceptance:**
- New fields default to 0; existing Ollama sessions still populate native fields
- All existing event tests pass without modification
**Depends on:** —

### 6.3 Config tagged-union shape + Clevis CLI args
**Scope:** Widen `BackendConfig` with `openai`/`anthropic` Optional fields (None defaults); forward-declare sub-config stubs under `TYPE_CHECKING`; widen `provider` whitelist to `("ollama","openai","anthropic")`; only wire ollama validation guard; keep `OllamaParameters.top_k`/`num_ctx` Ollama-specific; verify Clevis arg generation.
**Acceptance:**
- `BackendConfig()` defaults to `provider="ollama"`, `openai=None`, `anthropic=None`
- Existing `~/.yoker.toml` files load unchanged (no migration)
- `--backend-provider` lists all three; `--backend-openai-*`/`--backend-anthropic-*` args exist, default None
**Depends on:** —

### 6.4 render_config_toml union-aware
**Scope:** Confirm/extend `render_config_toml` to omit `None` per-provider sub-configs; do NOT touch `build_bootstrap_overrides` (deferred).
**Acceptance:**
- `render_config_toml` omits `None` per-provider sub-configs
- Round-trip: `load(render_config_toml(cfg)) == cfg` for an Ollama-only config
**Depends on:** 6.3

### 6.5 OllamaBackend adapter + create_backend factory
**Scope:** `backends/ollama.py` (`OllamaBackend` wrapping `AsyncClient`, relocating `create_client` logic; `chat_stream` translates native chunks to `ChatChunk` with synthesised block boundaries); `backends/factory.py` (`create_backend` dispatch, `BACKENDS = {"ollama": ...}` only; unknown provider -> `ConfigurationError`); remove `create_client` from `agent/_setup.py`.
**Acceptance:**
- `create_backend(Config())` returns `OllamaBackend`; unknown provider raises `ConfigurationError`
- `OllamaBackend.chat_stream` emits the documented `ChatChunk` event sequence (CONTENT_START before first CONTENT_DELTA, THINKING_START/STOP around thinking, TOOL_CALL_START/DELTA/STOP per call, terminal DONE with native `UsageStats`)
**Depends on:** 6.1, 6.3

### 6.6 Agent wiring: _backend, _resolve_model, _chat_stream, _consume_stream rewrite
**Scope:** Replace `Agent._client` with `Agent._backend`; `create_backend(self.config)`; `_resolve_model` reads active provider config; `_chat_stream` calls `backend.chat_stream`; `_consume_stream` rewritten to iterate `ChatChunk` and map to existing `Event` types; build `TurnEndEvent` from `UsageStats` (native fields, fall back to `input_tokens`/`output_tokens`); golden-stream test.
**Acceptance:**
- All existing tests pass without modification (behaviour unchanged)
- Golden-stream test: recorded `ChatChunk` -> expected `Event` sequence
- Ollama round-trip works exactly as before (interactive + batch)
**Depends on:** 6.5, 6.2

### 6.7 Subagent spawn provider-agnostic
**Scope:** `with_model(backend, model) -> BackendConfig` helper (in `backends/__init__.py` or `config`); replace hardcoded `OllamaConfig` rebuild in `builtin/agent.py::_create_subagent`; `bootstrap/modellist.py` reads default model from active provider config (curated list stays Ollama-only).
**Acceptance:**
- Subagent `Config.backend` equals parent's with only `model` overridden (regardless of provider)
- No hardcoded `OllamaConfig` rebuild in `_create_subagent`
**Depends on:** 6.3, 6.6

### 6.8 Phase 1 verification
**Scope:** End-to-end `make check`; verify no existing tests modified; wizard round-trip; `render_config_toml` union-awareness; `create_backend` dispatch + error; confirm wizard/`build_bootstrap_overrides`/web-tools-for-non-Ollama unchanged.
**Acceptance:**
- `make check` green; zero behaviour change on the Ollama path
- All design §5.4 acceptance criteria verified
- No wizard changes; no `build_bootstrap_overrides` changes; no new provider wired
**Depends on:** 6.1-6.7

---

## 5. Requirements Coverage

Phase 1 satisfies the following requirements derived from the design note:

- **R-MPB-1:** Provider-neutral `ModelBackend` Protocol exists in `src/yoker/backends/`. → 6.1
- **R-MPB-2:** Provider-neutral `ChatChunk` stream type accommodates both delta-style and block-style providers. → 6.1
- **R-MPB-3:** Existing Ollama behaviour is preserved through the new Protocol (no behaviour change). → 6.5, 6.6, 6.8
- **R-MPB-4:** `create_backend(config)` dispatches on `config.backend.provider`; unknown provider raises `ConfigurationError`. → 6.5
- **R-MPB-5:** Config schema is a tagged-union superset; old configs remain valid without migration. → 6.3
- **R-MPB-6:** `render_config_toml` omits `None` per-provider sub-configs. → 6.4
- **R-MPB-7:** Subagent spawn is provider-agnostic. → 6.7
- **R-MPB-8:** `TurnEndEvent` carries provider-agnostic stats alongside Ollama-native stats. → 6.2, 6.6
- **R-MPB-9:** Native Ollama SDK, native thinking, native stats, and native web tools are preserved. → 6.5, 6.8
- **R-MPB-NF-1:** `make check` green at Phase 1 boundary; no existing test modified. → 6.8

---

## 6. Key Decisions Inherited (from design §11)

- **Q1:** Keep native `ollama` SDK as the Ollama backend.
- **Q2:** Discriminated dataclass for `BackendConfig` (not `Union`, not `dict`).
- **Q4:** `top_k`/`num_ctx` stay Ollama-specific; no shared parameter base class.
- **Q7 (split):** `render_config_toml` union-awareness in Phase 1; `build_bootstrap_overrides` deferred with wizard.
- **Q8:** No config migration (tagged-union is a strict superset).
- **Q9:** `ollama` remains the default provider.
- **Q10:** Unknown provider -> `ConfigurationError` (no silent fallback).
- **Q15:** `TurnEndEvent` gains `input_tokens`/`output_tokens`; Ollama-native fields kept.
- **Q16:** Web tools for non-Ollama providers left as-is (no clear-error behaviour added).
- **Q17:** `_tool_backends` gap fixed by PRE-1 (M.5), not by the backend phases.
- **Q19:** Sequential phases — Phase 1, then Phase 2, then Phase 3.
- **Q20:** `chat_stream` `**kwargs` purely internal; per-provider parameters live in config.

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `_consume_stream` rewrite introduces subtle behaviour drift on the Ollama hot path. | Golden-stream test (6.6) using a recorded Ollama session; all existing tests must pass unmodified (6.8). |
| Clevis CLI arg generation breaks with new Optional sub-config fields. | Verify in 6.3 that `--backend-openai-*`/`--backend-anthropic-*` args exist and default to None; `make check` covers CLI surface. |
| Config round-trip regression for existing users. | 6.4 round-trip test; 6.8 manual round-trip with wizard-written `~/.yoker.toml`. |
| Scope creep into wizard or new providers. | Explicit out-of-scope list (§3.2); 6.8 verification confirms wizard/`build_bootstrap_overrides` unchanged. |
| `with_model` helper leaks Ollama assumptions. | Helper is provider-agnostic via `getattr`/`dataclasses.replace`; 6.7 tests under `provider="ollama"` and asserts faithful copy. |