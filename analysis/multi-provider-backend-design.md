# Multi-Provider Backend — Design Note

**Date**: 2026-06-28
**Status**: Final — owner decisions baked in
**Related**: `analysis/api.md` (existing API analysis), `analysis/bootstrap-wizard-design.md`
**Scope**: Introduce a provider-neutral `ModelBackend` Protocol and `ChatChunk` neutral stream type, then add OpenAI and Anthropic alongside the existing native Ollama backend in three phases.

> **Scoping note**: The backend work starts from `master`. The bootstrap wizard's provider-selection step is **out of scope** for these phases and is deferred to a separate follow-up on top of the (merged) bootstrap PR. The phases are purely: Protocol + Ollama refactor (P1), OpenAI backend (P2), Anthropic backend (P3).

---

## 1. Goal & Non-Goals

### Goal
Make Yoker provider-neutral at the model layer. A single `ModelBackend` Protocol abstracts chat streaming; the Agent talks to a backend instance, not to `ollama.AsyncClient` directly. Ollama, OpenAI, and Anthropic each ship as a backend implementation behind the same Protocol. The config schema becomes a tagged-union shape that can carry per-provider sub-configs and per-provider parameters.

### Non-Goals (deferred)
- **Bootstrap wizard provider selection.** The wizard's provider-selection step, `build_bootstrap_overrides` provider-awareness, and any per-provider wizard branching are deferred to a separate follow-up (see §8).
- **Web tools (`web_search`/`web_fetch`) on non-Ollama providers.** The `WebSearchBackend`/`WebFetchBackend` Protocols already exist (`src/yoker/tools/web/backend.py`) and depend on Ollama's native `client.web_search`/`client.web_fetch`. Non-Ollama providers will not get web tools in any phase; this is a documented limitation, not a blocker.
- **Non-streaming chat.** Yoker is streaming-first; the Protocol exposes only `chat_stream`. A blocking `chat()` helper can be added later if needed.
- **Embeddings / image generation / model management endpoints.** Out of scope.
- **Auto-discovery of provider models via live API.** Phase 2/3 use curated lists; live fetch is a future enhancement only.
- **Dropping the native Ollama SDK.** Explicitly NOT a goal — native Ollama SDK support is preserved for native thinking semantics, native stats, and native web tools.
- **Provider billing/account management UI.** Out of scope.

---

## 2. Prerequisites

The following precursor must be completed **before** starting Phase 1. It is tracked separately (a dedicated bug-fix TODO entry, not part of this design's phases) and is referenced here so the backend work is not blocked by the pre-existing gap.

| ID | Prerequisite | Owner | Note |
|---|---|---|---|
| PRE-1 | **Populate `Agent._tool_backends` for Ollama.** `Agent._tool_backends` is currently initialised to `{}` and never populated, so `websearch`/`webfetch` already fail today with "No backend configured". Fix this so the `websearch`/`webfetch` tools resolve to `OllamaWebSearchBackend`/`OllamaWebFetchBackend` when `provider == "ollama"`. | separate bug-fix task | Out of scope for the backend phases (Q17). Must land before Phase 1 begins so the Ollama refactor's acceptance criteria (round-trip web tools under Ollama) are verifiable on a non-broken base. |

Phase 1 references PRE-1 in its preconditions (§5) but does not perform the fix.

### 2.1 Follow-up tasks (maintenance)

Maintenance items arising from owner decisions and the security review (`analysis/security-multi-provider-backend.md`). These are tracked separately from the phases.

| ID | Follow-up | Trigger | Note |
|---|---|---|---|
| M.6 | **Exclude `api_key` from Clevis CLI generation.** | Q6 amendment (security H1) | **Resolved (2026-06-29):** Clevis released `metadata={'cli': False}` support. Phase 1 task 6.3 will annotate all `api_key` fields accordingly; no `--backend-*-api-key` CLI args will be generated. This follow-up is no longer needed. |

---

## 3. Current State (Ollama-Only Coupling)

The model layer is hard-wired to the `ollama` SDK. Key coupling points:

| File / symbol | Coupling |
|---|---|
| `src/yoker/config/__init__.py` — `BackendConfig` | `provider: str` validated against `("ollama",)` only; holds a single `ollama: OllamaConfig` field. No slot for other providers. |
| `src/yoker/config/__init__.py` — `OllamaConfig` / `OllamaParameters` | Ollama-specific fields: `base_url`, `api_key`, `model`, `timeout_seconds`, `parameters` (`temperature`, `top_p`, `top_k`, `num_ctx`). |
| `src/yoker/agent/_setup.py` — `create_client()` | Returns `ollama.AsyncClient` directly; reads `config.backend.ollama.{api_key,base_url}`. |
| `src/yoker/agent/agent.py` — `Agent._client` | Typed as `ollama.AsyncClient \| None`; constructed via `create_client(self.config, AsyncClient)`. |
| `src/yoker/agent/agent.py` — `Agent._resolve_model()` | Reads `self.config.backend.ollama.model`. |
| `src/yoker/agent/_processing.py` — `_chat_stream()` | Calls `agent._client.chat(model, messages, tools, think=..., stream=True)` — Ollama SDK signature. |
| `src/yoker/agent/_processing.py` — `_consume_stream()` | Reads `chunk.message.thinking`, `chunk.message.content`, `chunk.message.tool_calls`, and `chunk.done` + `chunk.prompt_eval_count`/`chunk.eval_count`/`chunk.total_duration` — Ollama-native chunk shape. |
| `src/yoker/events/types.py` — `TurnEndEvent` | Carries `prompt_eval_count`, `eval_count`, `total_duration_ms` (Ollama-native stats). |
| `src/yoker/builtin/agent.py` — `_create_subagent()` | Rebuilds a `Config` with `BackendConfig(provider=..., ollama=OllamaConfig(...))` — hardcoded Ollama shape; subagent spawn is provider-specific. |
| `src/yoker/tools/web/backend.py` | `OllamaWebSearchBackend` / `OllamaWebFetchBackend` take `ollama.AsyncClient` and call native `web_search`/`web_fetch`. |
| `src/yoker/bootstrap/wizard.py` + `steps.py` | Entirely Ollama-branded: `step_backend_intro` says "Today yoker supports Ollama", `step_account_check` asks for an "ollama account", `step_connection_method` offers "ollama app vs API key". *(Deferred — see §8.)* |
| `src/yoker/bootstrap/modellist.py` | `curated_models()` reads `config.backend.ollama.model` and lists Ollama-only model ids. |
| `src/yoker/agent/__init__.py` — `Agent._tool_backends` | Initialized to `{}` and never populated; `websearch`/`webfetch` tools currently always fail with "No backend configured" (pre-existing gap — see §2 PRE-1). |

The web-tools backend Protocol (`WebSearchBackend`/`WebFetchBackend`) is already provider-neutral at the *interface* level but the only implementation is Ollama-native and depends on `ollama.AsyncClient`.

---

## 4. Target Architecture

### 4.1 Package layout

```
src/yoker/backends/
├── __init__.py          # public exports: ModelBackend, ChatChunk, create_backend, BACKENDS registry
├── protocol.py          # ModelBackend Protocol + ChatChunk + supporting types
├── factory.py           # create_backend(config) dispatch
├── ollama.py            # OllamaBackend (native ollama SDK, moved out of agent/_setup.py + _processing.py)
├── openai.py            # OpenAIBackend (Phase 2, openai SDK)
└── anthropic.py          # AnthropicBackend (Phase 3, anthropic SDK)
```

### 4.2 `ChatChunk` neutral stream type (designed for all three providers)

Two streaming shapes must be accommodated:
- **Delta-style** (Ollama, OpenAI): each chunk carries a `message.content` / `message.thinking` text delta and optionally partial `tool_calls`; a final chunk carries usage/stats.
- **Block-style** (Anthropic): `content_block_start` declares a block (`text`/`thinking`/`tool_use`) at an `index`; `content_block_delta` carries typed deltas (`text_delta`, `thinking_delta`, `input_json_delta`); `content_block_stop` closes it; `message_start`/`message_delta`/`message_stop` carry usage and completion.

`ChatChunk` uses an explicit event kind so a single type serves both shapes. Backends translate provider-native chunks into `ChatChunk`; the Agent's stream consumer translates `ChatChunk` into the existing `Event` types (`ThinkingStartEvent`, `ContentChunkEvent`, `ToolCallEvent`, `TurnEndEvent`, etc.).

```python
class ChatChunkEvent(Enum):
  CONTENT_START = auto()      # block/text stream opened (Anthropic content_block_start type=text)
  CONTENT_DELTA = auto()      # text delta
  CONTENT_STOP = auto()       # block/text stream closed
  THINKING_START = auto()     # thinking block opened (Anthropic content_block_start type=thinking)
  THINKING_DELTA = auto()     # thinking text delta
  THINKING_STOP = auto()      # thinking block closed
  TOOL_CALL_START = auto()    # tool_use block opened (Anthropic) / first tool delta (delta-style)
  TOOL_CALL_DELTA = auto()    # arguments JSON delta
  TOOL_CALL_STOP = auto()     # tool_use block closed (Anthropic; synthesised by delta-style backends)
  USAGE = auto()              # usage/stats available (may arrive before final DONE)
  DONE = auto()               # stream complete


@dataclass(frozen=True)
class ToolCallDelta:
  """Incremental tool-call fragment, provider-agnostic.

  Attributes:
    index: Block index (Anthropic) or positional identifier (OpenAI/Ollama).
      Used to associate START/DELTA/STOP for the same call.
    id: Tool call id. Set on START when available (OpenAI/Anthropic provide it
      up front; Ollama may synthesise one on STOP).
    name: Tool name. Set on START (OpenAI/Anthropic) or on the first delta
      that carries it (Ollama).
    arguments_delta: JSON fragment of the arguments being streamed. Empty
      string deltas are possible.
  """
  index: int
  id: str | None = None
  name: str | None = None
  arguments_delta: str | None = None


@dataclass(frozen=True)
class UsageStats:
  """Token/duration stats, provider-agnostic.

  Ollama-native fields are kept first-class so native stats are preserved.
  OpenAI/Anthropic map to input_tokens/output_tokens.
  """
  input_tokens: int | None = None       # OpenAI/Anthropic
  output_tokens: int | None = None      # OpenAI/Anthropic
  prompt_eval_count: int | None = None  # Ollama native (== input_tokens)
  eval_count: int | None = None          # Ollama native (== output_tokens)
  total_duration_ms: int | None = None   # Ollama native total duration


@dataclass(frozen=True)
class ChatChunk:
  """A single neutral chunk emitted by a ModelBackend stream.

  Exactly one of ``text`` / ``tool_call`` / ``usage`` is set depending on
  ``event``; the others are ``None``.
  """
  event: ChatChunkEvent
  index: int | None = None   # block index for block-style providers
  text: str | None = None    # text delta for CONTENT_DELTA / THINKING_DELTA
  tool_call: ToolCallDelta | None = None  # for TOOL_CALL_* events
  usage: UsageStats | None = None        # for USAGE / DONE
```

**Field mapping by shape:**

| Field | Delta-style (Ollama/OpenAI) | Block-style (Anthropic) |
|---|---|---|
| `index` | positional tool index (OpenAI); None for content/thinking | block index from `content_block_*` |
| `text` | `message.content` / `message.thinking` delta | `text_delta.text` / `thinking_delta.text` |
| `tool_call` | assembled from `message.tool_calls` deltas | `input_json_delta.partial_json` + block `name`/`id` |
| `usage` | final chunk stats (Ollama: `prompt_eval_count`/`eval_count`/`total_duration`; OpenAI: `usage` in final chunk) | `message.usage.input_tokens` + `message_delta.usage.output_tokens` |

### 4.3 `ModelBackend` Protocol

```python
class ModelBackend(Protocol):
  """Provider-neutral streaming chat backend."""

  @property
  def provider(self) -> str:
    """Provider id, e.g. 'ollama' | 'openai' | 'anthropic'."""
    ...

  async def chat_stream(
    self,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    think: bool = False,
    **kwargs: Any,
  ) -> AsyncIterator[ChatChunk]:
    """Stream a chat completion as a sequence of ChatChunk.

    Implementations MUST emit CONTENT_START before the first CONTENT_DELTA,
    a final USAGE (when available), and a terminal DONE. TOOL_CALL_START/
    DELTA/STOP bracket each tool call. Backends that do not natively signal
    block boundaries (Ollama, OpenAI) synthesise them.
    """
    ...
```

Design notes:
- The Protocol is async-first (Yoker is async-only). No sync wrapper is needed — the whole application is async.
- `**kwargs` is **purely internal** (Q20): backends consume their own `Parameters` config and ignore unknown kwargs. It is not a stable public extension point; per-provider parameters live in config, not in call-site kwargs.
- The Protocol deliberately does NOT expose `web_search`/`web_fetch`. Web tools are a separate backend axis (see §9.4).

### 4.4 `create_backend(config)` dispatch

```python
# src/yoker/backends/factory.py
from yoker.backends.ollama import OllamaBackend
# Phase 2: from yoker.backends.openai import OpenAIBackend
# Phase 3: from yoker.backends.anthropic import AnthropicBackend

BACKENDS: dict[str, Callable[[Config], ModelBackend]] = {
  "ollama": lambda cfg: OllamaBackend(cfg),
  # "openai": ...,  # Phase 2
  # "anthropic": ...,  # Phase 3
}

def create_backend(config: Config) -> ModelBackend:
  provider = config.backend.provider
  try:
    builder = BACKENDS[provider]
  except KeyError:
    raise ConfigurationError(
      f"Unknown backend provider '{provider}'. "
      f"Configured providers: {sorted(BACKENDS)}"
    ) from None
  return builder(config)
```

Per Q10, an unknown provider raises `ConfigurationError` listing configured providers; the Agent never starts. No silent fallback.

### 4.5 Config schema (tagged union)

```python
@dataclass(frozen=True)
class BackendConfig:
  """Backend provider configuration (tagged union by `provider`)."""
  provider: str = field(default="ollama", metadata={"help": "..."})
  ollama: OllamaConfig = field(default_factory=OllamaConfig)
  openai: "OpenAIConfig | None" = None    # Phase 2
  anthropic: "AnthropicConfig | None" = None  # Phase 3

  def __post_init__(self) -> None:
    validate_choice(self.provider, "backend.provider", _ALLOWED_PROVIDERS)
    # Only the selected provider's config is required; others may be None.
    if self.provider == "ollama" and self.ollama is None:
      raise ValidationError("backend.ollama", None, "required when provider='ollama'")
    # Phase 2/3 add equivalent guards for openai/anthropic.
```

Per-provider sub-configs carry provider-specific connection and parameter fields, e.g.:

```python
@dataclass(frozen=True)
class AnthropicConfig:
  api_key: str | None = None
  base_url: str = "https://api.anthropic.com"
  model: str = "claude-3-5-sonnet-20241022"
  timeout_seconds: int = 60
  max_tokens: int = 4096   # REQUIRED by Anthropic API; sensible default (Q13)
  parameters: AnthropicParameters = field(default_factory=AnthropicParameters)

@dataclass(frozen=True)
class AnthropicParameters:
  temperature: float | None = None
  top_p: float | None = None
  top_k: int | None = None
  budget_tokens: int = 1024   # Q12: dedicated field with sensible default, overridable
```

The tagged-union shape keeps Clevis CLI arg generation working (`--backend-ollama-model`, `--backend-openai-model`, `--backend-anthropic-max-tokens`, etc.) because every sub-config remains a plain dataclass field with `metadata["help"]`.

---

## 5. Phase 1 — Protocol + Ollama Refactor

**Goal**: Introduce the `ModelBackend` Protocol and `ChatChunk`, reimplement the existing Ollama behaviour on top of them, widen the config schema shape, and make subagent spawn provider-agnostic. **Pure refactor — no behaviour change.**

### 5.1 Preconditions
- **PRE-1** (§2) must be landed first: `Agent._tool_backends` populated for Ollama. Phase 1 references this prerequisite but does not perform the fix (Q17 — out of scope for the phases).

### 5.2 File-by-file changes

| File | Change |
|---|---|
| `src/yoker/backends/__init__.py` | New. Exports `ModelBackend`, `ChatChunk`, `ChatChunkEvent`, `ToolCallDelta`, `UsageStats`, `create_backend`. |
| `src/yoker/backends/protocol.py` | New. Defines `ModelBackend` Protocol, `ChatChunk`, `ChatChunkEvent`, `ToolCallDelta`, `UsageStats` (as in §4.2/§4.3). |
| `src/yoker/backends/factory.py` | New. `create_backend(config)`; `BACKENDS = {"ollama": ...}` only in Phase 1. |
| `src/yoker/backends/ollama.py` | New. `OllamaBackend` wraps `ollama.AsyncClient`. Constructor builds the client from `config.backend.ollama` (moved from `agent/_setup.py::create_client`). `chat_stream()` calls `self._client.chat(...)` and translates each native chunk into `ChatChunk`: `message.thinking` -> `THINKING_*`, `message.content` -> `CONTENT_*`, `message.tool_calls` -> `TOOL_CALL_*`, `chunk.done` + native stats -> `USAGE` + `DONE`. Preserves `prompt_eval_count`/`eval_count`/`total_duration` in `UsageStats`. Maps the `think` flag to native `think=` (Q11). |
| `src/yoker/agent/agent.py` | Replace `self._client: AsyncClient \| None` with `self._backend: ModelBackend \| None`. Replace `create_client(self.config, AsyncClient)` with `create_backend(self.config)`. Keep an optional `backend: ModelBackend \| None = None` injection param (renamed from `client`). |
| `src/yoker/agent/agent.py` — `_resolve_model()` | Read from the active provider's config, not `config.backend.ollama.model` directly. Introduce a small helper `_active_backend_config(config) -> OllamaConfig \| OpenAIConfig \| ...` or read via `getattr(config.backend, config.backend.provider)`. |
| `src/yoker/agent/_setup.py` | Remove `create_client()` (moved to `OllamaBackend`). Keep `create_web_guardrails`, `validate_recursion_depth`, `add_skill_discovery_block` (unchanged). |
| `src/yoker/agent/_processing.py` — `_chat_stream()` | Replace `agent._client.chat(...)` with `agent._backend.chat_stream(model=..., messages=..., tools=..., think=...)`. |
| `src/yoker/agent/_processing.py` — `_consume_stream()` | Rewrite to iterate `ChatChunk` instead of Ollama-native chunks. Map `ChatChunkEvent` to the existing `Event` types (ThinkingStart/Chunk/End, ContentStart/Chunk/End, ToolCallEvent). Accumulate tool calls from `TOOL_CALL_START`/`DELTA`/`STOP`. Build `TurnEndEvent` from `UsageStats` (map `prompt_eval_count`/`eval_count`/`total_duration_ms`; for non-Ollama, fall back to `input_tokens`/`output_tokens`). |
| `src/yoker/config/__init__.py` — `BackendConfig` | Widen to the tagged-union shape (add `openai` and `anthropic` Optional fields with `None` defaults). `validate_choice(self.provider, ..., ("ollama",))` stays Ollama-only in Phase 1. Add a forward-declaration stub for `OpenAIConfig`/`AnthropicConfig` or import under `TYPE_CHECKING`. |
| `src/yoker/config/writer.py` — `render_config_toml` | Make union-aware: omit `None` per-provider sub-configs. Generic dataclass walk already handles this; confirm and add tests. (Q7 split — the writer is in the config module and reusable, so it stays in Phase 1.) |
| `src/yoker/builtin/agent.py` — `_create_subagent()` | Replace the hardcoded `BackendConfig(provider=..., ollama=OllamaConfig(...))` rebuild with a provider-agnostic copy: carry over the parent's entire `backend` config and override only the `model` on the active sub-config. Introduce `with_model(backend_config, model) -> BackendConfig` helper in `config` or `backends`. |
| `src/yoker/bootstrap/modellist.py` | Read default model from the active provider config (helper), not `config.backend.ollama.model`. Curated list stays Ollama-only in Phase 1. |
| `src/yoker/bootstrap/wizard.py` + `steps.py` | **Unchanged** — wizard stays Ollama-branded. Provider selection is deferred (§8). |

### 5.3 What stays the same
- Ollama native SDK usage (no switch to openai-compat) — Q1.
- Native thinking semantics (`think=` flag).
- Native stats (`prompt_eval_count`/`eval_count`/`total_duration`).
- Native web tools (`OllamaWebSearchBackend`/`OllamaWebFetchBackend`) — untouched (and now reachable once PRE-1 lands).
- All event types and the UIBridge mapping — unchanged.
- CLI arg generation via Clevis — unchanged (new optional config fields add new `--backend-openai-*` args but they default to None and are ignored).
- Bootstrap wizard — unchanged (deferred).

### 5.4 Acceptance criteria (Phase 1)
- `make check` green; all existing tests pass without modification (behaviour unchanged).
- A new unit test asserts `create_backend(Config())` returns an `OllamaBackend` instance.
- A new unit test feeds a recorded sequence of `ChatChunk` through `_consume_stream` and asserts the emitted `Event` sequence matches a captured Ollama session (golden-stream test).
- `OllamaBackend.chat_stream` emits `CONTENT_START` before the first `CONTENT_DELTA`, `THINKING_START`/`STOP` around thinking deltas, `TOOL_CALL_START`/`DELTA`/`STOP` per call, and a terminal `DONE` with `UsageStats` populated from native fields.
- Subagent spawn (`builtin/agent.py::_create_subagent`) produces a `Config` whose `backend` is a faithful copy of the parent's with only the model overridden, regardless of provider.
- `~/.yoker.toml` written by the wizard still produces a working Ollama session (round-trip unchanged).
- `render_config_toml` writes a config with `openai`/`anthropic` absent when those sub-configs are `None`.
- `api_key` fields on `OllamaConfig` (and forward-declared `OpenAIConfig`/`AnthropicConfig`) are annotated with `metadata={'cli': False}`; no `--backend-*-api-key` CLI args are generated by Clevis (H1 resolved).

---

## 6. Phase 2 — OpenAI

**Goal**: Add OpenAI as a second `ModelBackend` implementation using the `openai` SDK and ship a per-provider curated model list. **No wizard changes** — provider selection in the wizard is deferred (§8).

### 6.1 Changes per layer

| Layer | Change |
|---|---|
| `pyproject.toml` | Add `openai` dependency. |
| `src/yoker/backends/openai.py` | New. `OpenAIBackend` wraps `openai.AsyncOpenAI` (constructed with `base_url` from `OpenAIConfig.base_url` when set — Q18, enables Azure/compat gateways). **`base_url` is a trust boundary (Q18 amendment, §9.7):** a non-default `base_url` triggers the interactive warning/confirmation (or batch-mode `YOKER_ALLOW_CUSTOM_BASE_URL=1` gate) applied once at startup, before the backend is constructed. `chat_stream()` calls `client.chat.completions.create(model, messages, tools, stream=True)`. Translate OpenAI deltas into `ChatChunk`: `delta.content` -> `CONTENT_DELTA`; `delta.reasoning_content` (o-series reasoning models) -> `THINKING_DELTA` (Q14); `delta.tool_calls[i]` -> `TOOL_CALL_*` with `index=i`, assembling `id`/`function.name` on the first delta and `function.arguments` fragments on subsequent deltas; final `usage` -> `USAGE`; stream end -> `DONE`. Synthesise `CONTENT_START`/`CONTENT_STOP`/`THINKING_START`/`THINKING_STOP` since OpenAI does not signal block boundaries natively. The `think` flag maps to `reasoning_effort` on reasoning models and is a no-op otherwise (Q11). |
| `src/yoker/backends/factory.py` | Register `"openai"` in `BACKENDS`. |
| `src/yoker/config/__init__.py` | Add `OpenAIConfig` (`api_key`, `base_url: str \| None = None` (Q18, trust boundary per §9.7), `model`, `timeout_seconds`, `parameters: OpenAIParameters` with `temperature`, `top_p`, `max_tokens`, etc.). Wire `openai` field on `BackendConfig`; expand `validate_choice(self.provider, ..., ("ollama", "openai"))`. `OpenAIParameters` is its own class — no shared base with `OllamaParameters` (Q4). |
| `src/yoker/agent/_processing.py` | No change — already consumes `ChatChunk`. Verify `UsageStats.input_tokens`/`output_tokens` map into `TurnEndEvent` (fall back to 0 when native Ollama fields absent). |
| `src/yoker/builtin/agent.py` | `with_model` helper extended to handle `OpenAIConfig`. |
| `src/yoker/bootstrap/modellist.py` | Per-provider curated lists: `curated_models(config, provider)` returns the list for the active provider; `default_model_id(config, provider)` reads the active sub-config. |
| `src/yoker/tools/web/backend.py` | No change. Web tools stay Ollama-only; when `provider != "ollama"`, `websearch`/`webfetch` retain the current "No backend configured" failure (Q16 — leave as-is, do not add the clear-error-result behaviour). |

### 6.2 Per-provider model lists
Curated only in Phase 2 (no live fetch — Q5). `curated_models(config, provider)` returns a provider-specific list sourced from a constant table in `modellist.py`:

```python
CURATED: dict[str, list[CuratedModel]] = {
  "ollama": [...],   # existing list
  "openai": [
    CuratedModel("gpt-4o-mini", "gpt-4o-mini", "fast, low cost"),
    CuratedModel("gpt-4o", "gpt-4o", "balanced"),
    CuratedModel("o3-mini", "o3-mini", "reasoning"),
  ],
}
```

### 6.3 Acceptance criteria (Phase 2)
- `make check` green; new tests for `OpenAIBackend.chat_stream` using a mocked `AsyncOpenAI` streaming a recorded fixture.
- `create_backend(Config(backend=BackendConfig(provider="openai", openai=OpenAIConfig(api_key="sk-..."))))` returns an `OpenAIBackend`.
- `TurnEndEvent` carries `input_tokens`/`output_tokens` for OpenAI sessions (Ollama-native fields remain 0).
- Web tools (`websearch`/`webfetch`) under OpenAI retain the existing failure behaviour and do not crash.
- Subagent spawn under OpenAI produces a faithful backend config copy with the model overridden.
- `OpenAIConfig(base_url=...)` is forwarded to `AsyncOpenAI(base_url=...)` when set (Q18). A non-default `base_url` triggers the trust-boundary warning/confirmation (interactive) or the `YOKER_ALLOW_CUSTOM_BASE_URL=1` gate (batch) per §9.7.

*(The wizard's provider-selection step and `build_bootstrap_overrides` provider-awareness are deferred — see §8.)*

---

## 7. Phase 3 — Anthropic

**Goal**: Add Anthropic as a third `ModelBackend` using the `anthropic` SDK, with message-shape translation, SSE stream parsing, system-message extraction, and tool-block mapping. **No wizard changes** — provider selection in the wizard is deferred (§8).

### 7.1 Changes per layer

| Layer | Change |
|---|---|
| `pyproject.toml` | Add `anthropic` dependency. |
| `src/yoker/backends/anthropic.py` | New. `AnthropicBackend` wraps `anthropic.AsyncAnthropic`. The core work is translation (see §7.2-7.5). The `think` flag maps to `thinking={"type": "enabled", "budget_tokens": N}` using `AnthropicParameters.budget_tokens` (Q11, Q12). |
| `src/yoker/backends/factory.py` | Register `"anthropic"`. |
| `src/yoker/config/__init__.py` | Add `AnthropicConfig` (`api_key`, `base_url` (trust boundary per §9.7, same warning/confirmation behaviour as OpenAI), `model`, `timeout_seconds`, `max_tokens: int = 4096` default (Q13), `parameters: AnthropicParameters` with `temperature`, `top_p`, `top_k`, `budget_tokens: int = 1024` (Q12)). Wire `anthropic` field; expand `validate_choice` to include `"anthropic"`. |
| `src/yoker/bootstrap/modellist.py` | Add `CURATED["anthropic"]` (e.g. `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-opus-4-...`). |
| `src/yoker/builtin/agent.py` | `with_model` extended to `AnthropicConfig`. |

### 7.2 Message-shape translation
Anthropic's API separates `system` from the `messages` array and requires `messages` to be a flat list of `{role, content}` where `content` is a list of content blocks (`text`, `tool_use`, `tool_result`). The backend translates:

- Pull every `role == "system"` message out of the Yoker `messages` list and concatenate into a single `system` string argument (Anthropic accepts `system: str` or `system: list[TextBlock]`).
- Convert `assistant` messages with tool calls: Yoker stores them as `{role: "assistant", tool_calls: [...]}` (OpenAI-ish). Anthropic expects `{role: "assistant", content: [{"type": "tool_use", "id", "name", "input"}, ...]}`.
- Convert `tool` result messages: Yoker stores `{role: "tool", tool_call_id, content}`. Anthropic expects `{role: "user", content: [{"type": "tool_result", "tool_use_id", "content"}]}`.
- Plain `user`/`assistant` text messages become `content: [{"type": "text", "text": ...}]`.

### 7.3 Tool-block mapping
Yoker's tool schemas (OpenAI function-call shape) must be converted to Anthropic's `tools` shape:
- OpenAI: `{"type": "function", "function": {"name", "description", "parameters"}}`.
- Anthropic: `{"name", "description", "input_schema"}`.
The backend translates both directions. Tool-call results from Anthropic (`content_block` of type `tool_use` with `id`, `name`, `input`) map back to Yoker's `{id, function: {name, arguments: json.dumps(input)}}` so `_consume_stream` and `_execute_tool_calls` need no changes.

### 7.4 SSE stream parsing
The `anthropic` SDK exposes `client.messages.stream(...)` as an async context manager yielding events (`message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`). `chat_stream` maps these directly to `ChatChunk`:

| Anthropic event | `ChatChunk` |
|---|---|
| `message_start` | `USAGE` with `input_tokens` from `message.usage` |
| `content_block_start` (type=text) | `CONTENT_START` with `index` |
| `content_block_start` (type=thinking) | `THINKING_START` with `index` |
| `content_block_start` (type=tool_use) | `TOOL_CALL_START` with `index`, `tool_call.id`, `tool_call.name` |
| `content_block_delta` (text_delta) | `CONTENT_DELTA` |
| `content_block_delta` (thinking_delta) | `THINKING_DELTA` |
| `content_block_delta` (input_json_delta) | `TOOL_CALL_DELTA` with `arguments_delta=partial_json` |
| `content_block_stop` | `CONTENT_STOP` / `THINKING_STOP` / `TOOL_CALL_STOP` (by block type tracked via `index`) |
| `message_delta` | `USAGE` with `output_tokens` from `usage` |
| `message_stop` | `DONE` |

This is exactly the block-style shape `ChatChunk` was designed for — no synthesis needed.

### 7.5 System-message extraction
The `chat_stream` signature takes `messages: list[dict]`. The Anthropic backend filters system messages before forwarding (see §7.2). This is internal to the backend; the Agent still passes the full Yoker context including system messages. `agent/_setup.py::_setup_context()` is unchanged.

### 7.6 Acceptance criteria (Phase 3)
- `make check` green; new tests for `AnthropicBackend` using a mocked/recorded SSE fixture covering text, thinking, and tool_use blocks.
- `create_backend` returns an `AnthropicBackend` for `provider="anthropic"`.
- A full tool-call round trip under Anthropic: assistant emits `tool_use`, Yoker executes the tool, returns `tool_result`, assistant responds — verified with an integration-style test using a recorded stream.
- System messages from `SimpleContextManager` are correctly extracted into the Anthropic `system` argument (verified by intercepting the translated request).
- `max_tokens` defaults (4096) and `budget_tokens` defaults (1024) are applied when not set in config (Q12, Q13).
- Subagent spawn under Anthropic produces a faithful backend config copy.

*(The wizard's Anthropic branch is deferred — see §8.)*

---

## 8. Deferred: Bootstrap wizard provider selection

The bootstrap wizard's provider-selection step is **out of scope** for the backend phases. The wizard remains Ollama-branded throughout Phases 1-3. The following are deferred to a separate follow-up on top of the (merged) bootstrap PR, **after** the backend work lands:

- A new **provider-selection step** in the wizard (placement TBD in the follow-up; the earlier "fold into Step 2" recommendation is a candidate but not binding).
- `build_bootstrap_overrides` provider-awareness: setting `backend.provider` and the chosen provider's sub-config fields via dotted paths (e.g. `"backend.provider": "openai"`, `"backend.openai.api_key": "..."`).
- Per-provider branching in `step_backend_intro` / `step_account_check` / `step_connection_method` (e.g. OpenAI account check vs. Ollama app-vs-API-key choice; Anthropic `api_key` collection and `max_tokens` note).
- Any wizard-side rebranding from "Ollama" to provider-neutral language.

**Why deferred**: the backend work starts from `master` and the bootstrap PR is a separate concurrent effort. Folding provider selection into the backend phases would entangle two streams and force the wizard to be modified while it is still being landed. Keeping them separate lets the backend phases land cleanly on `master` and lets the wizard follow-up build on a stable, merged base.

**What is NOT deferred**: `render_config_toml` union-awareness lives in the config module (`src/yoker/config/writer.py`), is reusable by any caller, and stays in Phase 1 (Q7 split). Only the wizard-specific `build_bootstrap_overrides` provider-awareness is deferred.

---

## 9. Cross-Cutting Concerns

### 9.1 Config schema migration
- **Existing `~/.yoker.toml` files** (single-Ollama shape): remain valid. `backend.provider` defaults to `"ollama"` and `backend.ollama` is populated as before. The new `backend.openai`/`backend.anthropic` fields default to `None` and are simply absent from the file. No migration script needed (Q8).
- **Backfilling the config writer**: `src/yoker/config/writer.py::render_config_toml` is generic (walks dataclass fields) and is made union-aware in Phase 1 (Q7 — config module, reusable). It omits `None` per-provider sub-configs. The wizard's `build_bootstrap_overrides` provider-awareness is deferred (§8).
- **Tagged-union shape**: the discriminated-dataclass approach (Optional per-provider sub-configs + `provider` discriminator) is chosen (Q2) over a `typing.Union` because Clevis generates CLI args from dataclass fields and a Union field would break `--backend-ollama-model` ergonomics.

### 9.2 CLI arg generation (Clevis)
Clevis auto-generates `--backend-{provider}-{field}` args from the nested dataclass fields. The new `OpenAIConfig`/`AnthropicConfig` dataclasses automatically yield `--backend-openai-model`, `--backend-anthropic-max-tokens`, etc. The existing `--backend-ollama-model` is unchanged. The `provider` field yields `--backend-provider {ollama,openai,anthropic}` (Q6 — kept as a Clevis-generated choice arg, plus per-provider sub-config args).

**`api_key` CLI exclusion (Q6 amendment, security H1 — resolved):** Clevis now supports `metadata={'cli': False}` to exclude fields from CLI argument generation. Phase 1 annotates all `api_key` fields (`OllamaConfig.api_key`, `OpenAIConfig.api_key`, `AnthropicConfig.api_key`) with this metadata, so no `--backend-*-api-key` CLI args are generated. The security concern is addressed in Phase 1; no deferral needed.

### 9.3 Subagent spawn
`src/yoker/builtin/agent.py::_create_subagent` currently hardcodes `BackendConfig(provider=..., ollama=OllamaConfig(...))`. Introduce a helper:

```python
# src/yoker/backends/__init__.py (or config helper)
def with_model(backend: BackendConfig, model: str) -> BackendConfig:
  """Return a copy of backend with model overridden on the active sub-config."""
  sub = getattr(backend, backend.provider)
  new_sub = dataclasses.replace(sub, model=model)
  return dataclasses.replace(backend, **{backend.provider: new_sub})
```

Phase 1 implements this for `ollama`; Phase 2/3 extend to `openai`/`anthropic`. The subagent then constructs its `Agent` with the copied backend config; `create_backend` dispatches correctly.

### 9.4 Web tools (Ollama-only — documented limitation)
- `WebSearchBackend`/`WebFetchBackend` Protocols (`src/yoker/tools/web/backend.py`) are provider-neutral at the interface, but the only implementations (`OllamaWebSearchBackend`/`OllamaWebFetchBackend`) depend on `ollama.AsyncClient.web_search`/`web_fetch`.
- When `config.backend.provider != "ollama"`, web tools are unavailable. Per Q16, the **current "No backend configured" failure is left as-is** — do not add a clear-error-result behaviour in these phases.
- This is acceptable for all three phases; do not block the phasing on wiring web tools for other providers. A future enhancement could add an OpenAI/Anthropic-native web-fetch backend or a generic HTTP-fetch backend, but that is explicitly out of scope here.
- The pre-existing `Agent._tool_backends` gap is fixed by PRE-1 (§2) before Phase 1 begins; the backend phases themselves do not touch it (Q17).

### 9.5 Stats / events
- `TurnEndEvent` carries Ollama-native `prompt_eval_count`/`eval_count`/`total_duration_ms`. Per Q15, the event gains optional `input_tokens: int = 0` and `output_tokens: int = 0` fields; the Ollama-native fields are kept for backwards compatibility. Under OpenAI/Anthropic the Ollama-native fields stay `0` and `input_tokens`/`output_tokens` are surfaced instead. The UI reads whichever is non-zero.
- `UsageStats` is the single source from backends; `_consume_stream` maps it into `TurnEndEvent`.

### 9.6 Thinking mode
- **Ollama** (Q11): native `think=True` flag on `chat()`. Preserved.
- **OpenAI** (Q11, Q14): reasoning models (`o*` series) emit `reasoning_content` deltas, mapped to `THINKING_*` chunks. The `think` flag maps to `reasoning_effort` on reasoning models and is a no-op on non-reasoning models.
- **Anthropic** (Q11, Q12): thinking is a `content_block` of type `thinking` with a `thinking_delta`. The `think` flag maps to `thinking={"type": "enabled", "budget_tokens": N}` where `N` comes from `AnthropicParameters.budget_tokens` (default 1024, overridable). Requires `max_tokens` config (Q13: `AnthropicConfig.max_tokens: int = 4096` default).

### 9.7 `base_url` trust boundary (Q18 amendment, security M1)
`base_url` is a **trust boundary** for every provider (Ollama, OpenAI, Anthropic). Setting a non-default `base_url` routes model traffic — including the provider `api_key` and all conversation content — to an arbitrary endpoint. Yoker gates its use uniformly across all backends:

- **Interactive mode:** when any provider's `base_url` is set to a non-default value, yoker **warns the user and requests confirmation** before continuing. The warning states that a custom endpoint will receive the API key and all conversation content.
- **Batch / non-interactive mode:** when `base_url` is non-default, yoker **terminates with a warning** unless the explicit environment variable `YOKER_ALLOW_CUSTOM_BASE_URL=1` is set. This keeps automated pipelines safe-by-default while permitting deliberate override.

HTTPS is **recommended but not enforced** — the owner did not require an `https://` mandate; the warning/confirmation mechanism is the mitigation. This behaviour is backend-agnostic: it applies to `OllamaConfig.base_url`, `OpenAIConfig.base_url`, and `AnthropicConfig.base_url` alike, and is implemented in the config validation / startup path (not inside each backend) so the rule is applied once for all providers.

---

## 10. Effort Sizing (T-shirt)

| Phase | Size | Rationale |
|---|---|---|
| Phase 1 — Protocol + Ollama refactor | **M** | New package, Protocol/ChatChunk design, rewrite `_consume_stream`, widen config, provider-agnostic subagent, `render_config_toml` union-awareness. Mechanical but touches the hot path; golden-stream test required. No new deps, no behaviour change. No wizard work. |
| Phase 2 — OpenAI | **M** (slightly smaller without wizard) | New backend impl + new dep + per-provider model lists + config. No wizard provider step (deferred). Translation is straightforward (delta-style, same shape as Ollama). |
| Phase 3 — Anthropic | **L** | Block-style translation is the bulk: message-shape rewrite (system extraction, tool_use/tool_result blocks), tool-schema translation, SSE event mapping, `max_tokens`/`budget_tokens` thinking config. No wizard work. Highest complexity. |

**Total**: M + M + L, sequenced (Q19 — Phase 2 then Phase 3; Phase 2's patterns inform Phase 3). Phase 1 is a prerequisite hard dependency for Phases 2 and 3. PRE-1 (§2) is a prerequisite for Phase 1.

---

## 11. Decisions

All twenty owner decisions are resolved below. Option context is kept brief where it aids readability.

### 11.0 Security amendments (2026-06-28)

The security review (`analysis/security-multi-provider-backend.md`) raised two findings against the backend design. The owner resolved both on 2026-06-28 (PR #36 comment) with the specifics recorded here and applied to the relevant decisions and cross-cutting sections:

- **H1 (high) → Q6 amendment:** Clevis CLI generation exposes `--backend-{provider}-api-key`. The owner did not adopt original options A or B; instead a feature request is being filed with Clevis for field-exclusion support. `api_key` CLI exclusion is **deferred** until Clevis ships that capability; the pre-existing exposure is accepted as a known limitation. Tracked by follow-up M.6 (§2.1). See §11.6 and §9.2.
- **M1 (medium) → Q18 amendment:** `base_url` is a trust boundary. The owner adopted a variant of option A: interactive warning + confirmation for non-default `base_url`; batch mode terminates with a warning unless `YOKER_ALLOW_CUSTOM_BASE_URL=1` is set. The original option A's `https://` requirement is **not** adopted (https recommended but not enforced). Applies uniformly to all providers. See §11.18 and §9.7.

**Update (2026-06-29):** Clevis released `metadata={'cli': False}` support, unblocking H1. Phase 1 will annotate all `api_key` fields accordingly; the security concern is now addressed in Phase 1, not deferred. Follow-up M.6 is marked resolved.

No other decisions (Q1-Q5, Q7-Q17, Q19-Q20) were changed by the security review.

### 11.1 Q1 — Native Ollama SDK
**Decision: KEEP the native `ollama` SDK as the Ollama backend.** Three adapters total (Ollama native, OpenAI, Anthropic). Rejected alternative: switching Ollama to the `openai` SDK against its compat endpoint, which would lose native `prompt_eval_count`/`eval_count`/`total_duration`, native `think`, and native `web_search`/`web_fetch`.

### 11.2 Q2 — Config shape
**Decision: Discriminated dataclass.** `BackendConfig` with `provider: str` + `ollama`/`openai`/`anthropic` Optional sub-config fields. Rejected: `typing.Union` (breaks Clevis CLI arg generation) and plain `dict[str, Any]` (loses validators).

### 11.3 Q3 — Wizard provider selection
**Decision: DEFERRED.** The wizard's provider-selection step is out of scope for the backend phases; revisited separately after the backend work, starting from `master`. See §8.

### 11.4 Q4 — Ollama params
**Decision: Keep `top_k`/`num_ctx` Ollama-specific on `OllamaParameters`.** Other providers get their own parameter classes (`OpenAIParameters`, `AnthropicParameters`). No shared base for now; revisit only if duplication grows. (`num_ctx` is Ollama-only; `top_k` exists in Anthropic but with different semantics.)

### 11.5 Q5 — Model discovery
**Decision: Curated hardcoded lists per provider now; optional live-fetch from provider API in a later phase.** Consistent with the first-install UX decision in `analysis/bootstrap-wizard-design.md`.

### 11.6 Q6 — CLI field
**Decision: Keep `--backend-provider {ollama,openai,anthropic}` as a Clevis-generated choice arg, plus per-provider sub-config args** (`--backend-openai-model`, `--backend-anthropic-max-tokens`, etc.). Users can switch provider without editing TOML.

**Amendment (2026-06-28, security review H1 — resolved 2026-06-29):** Clevis released `metadata={'cli': False}` support (2026-06-29). Phase 1 will annotate all `api_key` fields with this metadata to suppress `--backend-{provider}-api-key` CLI generation. The security concern is addressed in Phase 1; no deferral needed. Follow-up M.6 (§2.1) is marked resolved.

Q6 otherwise stands: `--backend-provider {ollama,openai,anthropic}` remains a Clevis-generated choice arg and per-provider sub-config args remain generated.

### 11.7 Q7 — Writer backfill (split)
**Decision (split):**
- **`render_config_toml` union-awareness stays in Phase 1.** It lives in the config module (`src/yoker/config/writer.py`), is generic and reusable by any caller, and is needed for round-trip correctness.
- **`build_bootstrap_overrides` provider-awareness is DEFERRED** with the wizard (§8). It is wizard-specific and belongs to the deferred follow-up.

### 11.8 Q8 — Config migration
**Decision: No migration needed.** Old files stay valid: `provider` defaults to `"ollama"`, new Optional fields default to `None`. The tagged-union shape is a strict superset.

### 11.9 Q9 — Default provider
**Decision: Keep `ollama` as the default for new users.** Lowest-friction first run (free tier, local-app path).

### 11.10 Q10 — Unknown provider at runtime
**Decision: `create_backend` raises `ConfigurationError` listing configured providers; the Agent never starts.** No silent fallback to Ollama. The error names the configured providers and points to the wizard.

### 11.11 Q11 — `think` flag semantics per provider
**Decision: Map in the Protocol.**
- Ollama -> native `think`.
- OpenAI -> `reasoning_effort` on reasoning models; no-op on non-reasoning models.
- Anthropic -> `thinking={"type": "enabled", "budget_tokens": N}` (N from `AnthropicParameters.budget_tokens`, see Q12).

Rejected: dropping the `think` flag from the Protocol and having each backend read a `thinking` flag from its own parameters config (would break the existing `ThinkingMode` plumbing).

### 11.12 Q12 — Anthropic `budget_tokens`
**Decision: Dedicated `AnthropicParameters.budget_tokens: int` field with a sensible default of 1024, overridable.** Rejected: deriving from `max_tokens` (lossy coupling) and a separate required field (wizard friction).

### 11.13 Q13 — Anthropic `max_tokens`
**Decision: `AnthropicConfig.max_tokens: int = 4096` default, overridable.** Keeps wizard friction low; advanced users override.

### 11.14 Q14 — OpenAI `reasoning_content`
**Decision: Surface as thinking events.** Map `delta.reasoning_content` to `THINKING_*` chunks. Consistent with Ollama/Anthropic thinking UX; users who disable thinking via `ThinkingMode.OFF` won't see it.

### 11.15 Q15 — `TurnEndEvent` stats
**Decision: Add optional `input_tokens: int = 0` and `output_tokens: int = 0`; keep Ollama-native `prompt_eval_count`/`eval_count` for backwards compatibility.** UI reads whichever is non-zero. Rejected: mapping everything into the Ollama-native fields (lossy).

### 11.16 Q16 — Web tools when provider != ollama
**Decision: LEAVE AS-IS.** Retain the current "No backend configured" failure. Do not add the clear-error-result behaviour. (Keeps the phases scoped; a clearer error can be added later alongside any non-Ollama web-fetch backend.)

### 11.17 Q17 — `_tool_backends` gap
**Decision: Out of scope for the phases.** A separate prerequisite bug-fix TODO (PRE-1, §2) populates `_tool_backends` (`websearch`/`webfetch`) when provider is Ollama, **before** Phase 1 starts. The backend phases reference this prerequisite but do not perform the fix.

### 11.18 Q18 — OpenAI `base_url`
**Decision: `OpenAIConfig.base_url: str | None = None`, passed to `AsyncOpenAI(base_url=...)` when set.** Enables Azure OpenAI and OpenAI-compatible gateways. Does not conflict with keeping native Ollama (Q1).

**Amendment (2026-06-28, security review M1):** `base_url` is treated as a **trust boundary** for every provider, not just OpenAI. A non-default `base_url` routes model traffic (including `api_key` and message content) to an arbitrary endpoint, so yoker gates its use with a warning/confirmation mechanism:

- **Interactive mode:** when `base_url` is set to a non-default value, yoker **warns the user and requests confirmation** before continuing. The warning identifies that a custom endpoint will receive the API key and all conversation content.
- **Batch / non-interactive mode:** when `base_url` is non-default, yoker **terminates with a warning** unless the explicit environment variable `YOKER_ALLOW_CUSTOM_BASE_URL=1` is set. This keeps automated pipelines safe-by-default while permitting deliberate override.

The original option A's `https://` requirement is **NOT adopted** — the owner did not require https. HTTPS is **recommended but not enforced**; the warning/confirmation mechanism is the mitigation. This applies to any provider's `base_url` (Ollama, OpenAI, Anthropic) uniformly.

### 11.19 Q19 — Phase ordering
**Decision: Sequential — Phase 2 then Phase 3.** Phase 2's backend/config patterns inform Phase 3. Rejected: parallel execution.

### 11.20 Q20 — `chat_stream` kwargs
**Decision: Purely internal.** Backends consume their own `Parameters` config and ignore unknown kwargs. Not a stable public extension point; per-provider parameters live in config, not in call-site kwargs.