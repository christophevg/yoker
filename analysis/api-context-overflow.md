# API / Backend Architecture: Context Overflow Management (IP-12, MBI-008 T3.5)

**Date**: 2026-07-27
**Reviewer**: API Architect Agent
**Task**: Cross-domain design review for IP-12 (Context Overflow Management)
**Source**: `analysis/mbi-prompt-sets.md` (MBI-008 T3.5, IP-12, D3 — research-informed, owner-reviewed)
**Status**: Not yet implemented. This document defines the backend architecture.

## Summary

IP-12 has zero implementation today. No context-size check, no truncation logic, no
`context_management` passthrough, no thinking-block stripping, no config, no event.
Long sessions crash when they exceed the model's context window.

The owner's design (D3, research-informed and owner-reviewed) is **framework-driven,
not LLM-driven**. It mirrors what Claude Code actually does (verified against 1078
recorded requests): programmatic message truncation + API-level thinking token
clearing. No summarization, no compaction prompt, no LLM involvement.

This document specifies where the check lives, how size is estimated, what is
kept/dropped, how the backend Protocol absorbs `context_management`, the
optional `on_context_overflow` hook, the config additions, and one new event.

## Owner's Proposal (Quoted Verbatim — Default)

From `analysis/mbi-prompt-sets.md` T3.5:

> - Add context size check before each request (framework mechanism: detection + triggering)
> - Framework default: drop oldest non-system messages when over threshold (keeping first user message with config injections)
> - If backend supports `context_management` API field (Anthropic), pass through thinking token clearing directive
> - If backend does not support it, strip thinking blocks from message history programmatically
> - Optional `on_context_overflow` hook for prompt sets that want custom truncation strategies
> - Without this, long sessions crash

From D3 "Revised approach" (owner-reviewed):

> **Framework responsibility** (always active):
> - Estimate context size before each request (heuristic or tokenizer-based)
> - If over threshold, drop oldest non-system messages (keeping the first user message with config injections)
> - If the backend supports `context_management`, pass through the thinking token clearing directive
> - If the backend does not support it, strip thinking blocks from message history programmatically
>
> **Prompt set hook** (optional, for advanced strategies):
> - `on_context_overflow` hook fires with message_count, estimated_tokens, max_tokens, messages
> - If the prompt set provides a `context_overflow.j2` template, it can return a modified message list
> - If no template, the framework's default truncation applies
> - This is an extension point, not the primary mechanism

These proposals work. The architecture below is a direct, slim realization. No
abstraction is added that the owner did not request.

## Verification: What Exists vs What's Missing

| Required piece | Location checked | Status |
|---|---|---|
| Context-size check before request | `src/yoker/core/_processing.py` `process_message()` / `_chat_stream()` | **Missing** — `agent.context.get_context()` is passed straight to `backend.chat_stream()` with no size guard |
| Truncation logic (drop oldest non-system) | `src/yoker/context/manager.py`, `basic.py`, `persisted.py` | **Missing** — no truncation method on `BaseContextManager` or any wrapper |
| Token / size estimation | `src/yoker/context/`, `src/yoker/backends/` | **Missing** |
| `context_management` passthrough (Anthropic) | `src/yoker/backends/protocol.py` `ModelBackend.chat_stream`, `src/yoker/backends/litellm.py` | **Missing** — Protocol has no `context_management` kwarg; LitellmBackend does not forward one |
| Fallback thinking-block stripping | backends + context | **Missing** — `thinking` field is stored on assistant messages (see `add_message`/`add_tool_calls` in `manager.py`) but never stripped before send |
| `on_context_overflow` hook | (prompt set system itself is not yet implemented — MBI-008 Phases 1-2 are prerequisites) | **Missing** (depends on prompt-set framework) |
| Config (`threshold`, `strategy`, etc.) | `src/yoker/config/__init__.py` `ContextConfig` | **Missing** — `ContextConfig` only has `manager`, `storage_path`, `session_id`, `persist_after_turn`, `filename`, `fresh` |
| `ContextOverflow` event | `src/yoker/events/types.py` | **Missing** — no overflow event in `EventType` |

Prerequisite note: IP-12's `on_context_overflow` hook depends on the prompt-set
framework (MBI-008 Phases 1-2). The **framework-responsibility pieces** (size
check, default truncation, `context_management` passthrough, thinking-strip
fallback, config, event) are independent of the prompt-set framework and can
ship first. The hook becomes a thin call-site that is a no-op until prompt
sets exist.

## Architecture

### 1. Where the check lives

Single call site: `src/yoker/core/_processing.py`, inside the `process_message`
while-loop, **before** `_chat_stream(agent)` is invoked.

```python
# in process_message(), top of while-loop, before _chat_stream:
messages = agent.context.get_context()
messages = _enforce_context_limit(agent, messages)
# pass `messages` (not re-read context) to _chat_stream
```

Today `_chat_stream` re-reads `agent.context.get_context()` itself. That call
moves up one frame so the post-truncation list is what gets sent. This is a
minimal, local change — no new orchestrator, no new pipeline stage.

Why here and not in `BaseContextManager.get_context()`:
- `get_context()` is read-only by contract (returns a copy of `_messages`).
  Truncation mutates conversation history — a semantic side-effect that belongs
  in the processing loop, not in a getter.
- Putting it in the loop keeps `ContextManager` implementations dumb and the
  overflow policy in one visible place.
- The `Persisted` wrapper bulk-rewrites JSONL on every mutating call; if
  truncation mutated `_messages` directly it would trigger a full JSONL rewrite
  per request. Keeping truncation as a *view* (a transformed list handed to the
  backend) avoids touching persistence on every turn. The truncated list is
  NOT written back into `_messages`.

Open question Q1: should truncation be a *view* (transient, per-request) or
*permanent* (mutate `_messages` and persist)? The owner's wording ("drops old
messages from the conversation history" / "messages are simply gone") suggests
permanent. CC's behavior is permanent. But permanent truncation fights the
`Persisted` bulk-rewrite model and loses tool-result/assistant pairing
integrity. **Recommendation: permanent, but only when an overflow actually
fires** (not on every request), via a single explicit
`agent.context.truncate_oldest_non_system(keep_first_user=True)` call. See §5.

### 2. Detecting context size

Three options, in order of accuracy vs cost:

| Method | Source | Cost | Accuracy |
|---|---|---|---|
| Backend-reported `input_tokens` from previous turn | `UsageStats.input_tokens` already captured in `_consume_stream` | Free | Exact, but one turn stale |
| Heuristic char count | `sum(len(str(m.get("content",""))) for m in messages)` | Free | Rough (4 chars/token English, worse for code/JSON) |
| Tokenizer | `tiktoken` / provider tokenizer | Dependency + per-request CPU | Exact |

Owner's wording: "heuristic or tokenizer-based". **Default: hybrid — use the
last reported `input_tokens` if available, fall back to a char heuristic.** No
new dependency. The last-turn `input_tokens` is already tracked in
`TurnEndEvent`/stats; stash it on the agent (e.g.
`agent._last_input_tokens`) and use it as the primary signal. If
`_last_input_tokens + estimated_output_budget > model_context_window`,
trigger truncation.

The threshold is **tokens**, not chars. Config exposes it as tokens.

Open question Q2: where does the model's context-window size come from? Options:
(a) new config field `context.max_tokens` (owner-explicit, default e.g. 200_000),
(b) per-model lookup table,
(c) query the backend.
**Recommendation: (a) — a single `context.max_tokens` config field.** Slim,
explicit, no model registry. Owner decides the default.

### 3. Truncation strategy: what to keep, what to drop

Owner's rule: "drop oldest non-system messages when over threshold (keeping
first user message with config injections)".

Concrete keep/drop, applied to `agent.context.get_context()`:

| Message | Keep? | Why |
|---|---|---|
| All `role == "system"` messages | **Always keep** | System prompt, env reminder, skill discovery block — small, essential |
| First `role == "user"` message | **Always keep** | Owner-specified — carries CLAUDE.md / config injections in the CC set |
| All other user / assistant / tool messages | **Drop oldest first** | The conversation body |
| In-progress tool-call / tool-result pairs | **Drop as a unit** | Never split an assistant tool_call from its tool_result — would corrupt the next request |

Implementation: walk the message list from the front, skipping the protected
prefix (system messages + first user message). From the remainder, drop from
the front (oldest) in **tool-call-pair-aware units** until estimated size is
below threshold. Stop.

A "tool-call-pair-aware unit" = an assistant message with `tool_calls` plus all
trailing `role == "tool"` messages until the next non-tool message. Dropping
the assistant side without its results would leave dangling tool results;
dropping results without the call would leave a call with no response. Both
corrupt provider validation.

### 4. Backend protocol: `context_management` passthrough + thinking-strip fallback

This is the only place the `ModelBackend` Protocol changes.

#### 4a. Protocol addition

Add one optional kwarg to `ModelBackend.chat_stream`:

```python
def chat_stream(
  self,
  *,
  model: str,
  messages: list[dict[str, Any]],
  tools: list[dict[str, Any]] | None = None,
  think: bool = False,
  context_management: dict[str, Any] | None = None,  # NEW
  **kwargs: Any,
) -> AsyncIterator[ChatChunk]: ...
```

`context_management` is a dict (not a typed dataclass) because it is a
provider-defined passthrough — Yoker does not interpret it. The framework
only constructs the one known directive:

```python
{"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}
```

#### 4b. Capability discovery

A backend advertises support via a new boolean attribute on the Protocol
(default `False` for backward compatibility with `OllamaBackend`):

```python
class ModelBackend(Protocol):
  supports_context_management: bool  # default False
  ...
```

`LitellmBackend.supports_context_management` is `True` when
`config.backend.provider == "anthropic"`. `OllamaBackend.supports_context_management`
is `False`.

The processing loop decides:

```python
if agent._backend.supports_context_management:
  kwargs["context_management"] = {"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}
else:
  messages = _strip_thinking_blocks(messages)
```

#### 4c. LitellmBackend forwarding

In `LitellmBackend.chat_stream`, forward `context_management` into
`litellm.acompletion(...)` only when the provider is Anthropic and the
directive is present. Litellm passes unknown kwargs through to the provider
for native providers; for non-Anthropic providers the directive is never
constructed (capability guard), so no leak.

#### 4d. Thinking-strip fallback

`_strip_thinking_blocks(messages)` operates on the **view** passed to the
backend (does not mutate `agent.context._messages`):

```python
def _strip_thinking_blocks(messages: list[dict]) -> list[dict]:
  return [
    {k: v for k, v in m.items() if k != "thinking"}
    for m in messages
  ]
```

The `thinking` key is the only thinking-storage in the message dict shape
today (see `BaseContextManager.add_message` / `add_tool_calls`). One field,
one strip. No recursive walk, no content-block parsing.

Note: today `LitellmBackend` already deep-copies messages and does not forward
the `thinking` key to litellm (it has no mapping to `reasoning_content` on the
request side). So for Litellm+non-Anthropic, stripping is effectively already
happening by omission. Making it explicit is a no-op for Litellm but correct
for any future backend that *does* echo thinking back.

### 5. The `on_context_overflow` hook

Per owner: "Optional `on_context_overflow` hook for prompt sets that want
custom truncation strategies (extension point, not primary mechanism)."

Plug-in point: **same place as the size check** — `process_message`'s
while-loop, after size estimation, before default truncation.

Signature (aligned with D3's template variables):

```python
# module-level type alias in yoker/prompts/hooks.py (new, when prompt sets ship)
# Until then, the call site uses a plain optional callable.

OverflowContext = dict  # {"message_count", "estimated_tokens", "max_tokens", "messages"}
OverflowResult = list[dict[str, Any]] | None  # modified message list, or None = use framework default

# on_context_overflow: Callable[[OverflowContext], OverflowResult] | None
```

Call sequence in the loop:

```python
if over_threshold:
  await emit(ContextOverflowEvent(...))  # see §6
  hook = agent._on_context_overflow  # None until prompt sets wire it
  if hook is not None:
    custom = hook({...})
    if custom is not None:
      messages = custom
    else:
      messages = _default_truncate(agent, messages)
  else:
    messages = _default_truncate(agent, messages)
```

Until the prompt-set framework (MBI-008 Phases 1-2) lands, `agent._on_context_overflow`
stays `None` and the framework default always runs. IP-12 ships the framework
default + the call-site; the hook plumbing is a one-line `None` check that
prompt sets later fill in. This keeps IP-12 unblocked from the larger
prompt-set dependency.

### 6. Event emission

Add one event to `src/yoker/events/types.py`:

```python
class ContextOverflowEvent(Event):
  type: EventType  # EventType.CONTEXT_OVERFLOW (new enum member)
  message_count: int
  estimated_tokens: int
  max_tokens: int
  dropped_count: int
```

Emit once per overflow event (not per dropped message). The UI layer can render
a "context trimmed" notice; the batch handler can log it. This is the only new
event type.

No `ContextTrimmedEvent` / `ContextRestoredEvent` etc. — one event, one
purpose, matches owner's "per-overflow event" scope.

### 7. Config additions

Extend `ContextConfig` in `src/yoker/config/__init__.py`:

```python
@dataclass
class ContextConfig:
  # ... existing fields ...
  max_tokens: int = 200_000          # context window budget (tokens)
  overflow_strategy: str = "drop_oldest"  # "drop_oldest" | "hook"
  overflow_keep_first_user: bool = True   # protect first user message
  overflow_strip_thinking: bool = True    # fallback when backend lacks context_management
```

`overflow_strategy = "hook"` is the opt-in for prompt-set-driven truncation
(once prompt sets exist). Until then only `"drop_oldest"` is effective;
`"hook"` falls through to default if no hook is registered.

No nested `ContextOverflowConfig` sub-dataclass — four flat fields on
`ContextConfig`. The Simplicity Principle: the owner's proposal is flat; a
nested dataclass is unearned indirection.

Open question Q3: should `max_tokens` live on `ContextConfig` or on
`BackendConfig`? It is a property of the model/backend, but the overflow
policy reads it from the context side. **Recommendation: `ContextConfig`**,
because the overflow logic lives in the processing loop and reads
`agent.config.context`. If the owner prefers `BackendConfig`, that works too —
flag for decision.

### 8. Interaction with existing `ContextManager` Protocol / `BaseContextManager`

Minimal. The Protocol does **not** gain a truncate method. Truncation operates
on the *view* returned by `get_context()`; `get_context()` already returns a
fresh list copy (see `manager.py` line 138: `return list(self._messages)`).

If Q1 is resolved as "permanent" (recommended), add ONE method to the Protocol
and `BaseContextManager`:

```python
def truncate_oldest_non_system(self, keep_first_user: bool = True, drop_count: int = 1) -> int:
  """Drop oldest non-system messages (in tool-pair-aware units). Return count dropped."""
```

`Persisted` overrides it: delegate to wrapped, then `_persist_full_state(...)`
(one bulk rewrite, not one per message). `ContextManagerWrapper` forwards it.
No other surface changes.

### 9. What is explicitly NOT added

- No `ContextCompactor` class.
- No `ContextSummarizer` (LLM-driven summarization). D3 ruled this out.
- No `TokenEstimator` class — a function is enough.
- No per-model context-window registry — one config field.
- No `ContextOverflowConfig` nested dataclass — flat fields.
- No separate "compaction" / "summary" / "restore" events — one event.
- No `capability` enum on the backend — one boolean.
- No mutation of `_messages` from the size-check path when no overflow fires.

## Action Items (Implementation Order)

1. Add `EventType.CONTEXT_OVERFLOW` + `ContextOverflowEvent` to `events/types.py`.
2. Extend `ContextConfig` with `max_tokens`, `overflow_strategy`,
   `overflow_keep_first_user`, `overflow_strip_thinking`.
3. Add `supports_context_management: bool` to `ModelBackend` Protocol;
   set `True` on `LitellmBackend` when provider is Anthropic, `False` on
   `OllamaBackend`.
4. Add `context_management` kwarg to `ModelBackend.chat_stream` and
   `LitellmBackend.chat_stream` (forward only when Anthropic).
5. Add `_strip_thinking_blocks(messages)` helper in `_processing.py`.
6. Add `truncate_oldest_non_system(...)` to `BaseContextManager` + `Persisted`
   + `ContextManagerWrapper` + Protocol (resolves Q1 as "permanent").
7. Add `_enforce_context_limit(agent, messages)` in `_processing.py`:
   estimate size → maybe emit `ContextOverflowEvent` → maybe call hook
   (None for now) → maybe `agent.context.truncate_oldest_non_system(...)`
   → maybe strip thinking → maybe set `context_management` kwarg.
8. Wire it into `process_message`'s while-loop before `_chat_stream`.
9. Tests: threshold-not-exceeded no-op; threshold-exceeded drops oldest
   non-system, keeps system + first user; tool-call pairs stay intact;
   Anthropic path sets `context_management`; non-Anthropic path strips
   thinking; `ContextOverflowEvent` emitted once; persisted file rewritten
   once per overflow.

## Open Questions for the Owner

- **Q1**: Permanent truncation (mutate `_messages`, persist) vs per-request
  view? **Recommendation: permanent, only when an overflow actually fires.**
- **Q2**: Source of `max_tokens` — single config field vs per-model lookup?
  **Recommendation: single `context.max_tokens` field.** What default
  (200_000)?
- **Q3**: `max_tokens` on `ContextConfig` or `BackendConfig`?
  **Recommendation: `ContextConfig`.**
- **Q4**: Should `overflow_strip_thinking` be configurable, or always-on when
  the backend lacks `context_management`? **Recommendation: always-on
  (remove the config flag, keep behavior).** The owner's proposal makes the
  fallback unconditional ("if backend does not support it, strip thinking
  blocks"). The flag is unearned configurability. Flag for decision.
- **Q5**: Is `tiktoken` acceptable as an optional dependency for exact token
  counts, or stick with the hybrid last-turn-`input_tokens` + char heuristic?
  **Recommendation: hybrid, no new dependency.**

## Related Documents

- `analysis/mbi-prompt-sets.md` — IP-12, T3.5, D3 (source of truth for design intent)
- `analysis/context-implementation-plan.md` — older, partly superseded by MBI-008
- `src/yoker/core/_processing.py` — call site
- `src/yoker/context/manager.py`, `protocol.py`, `persisted.py`, `wrapper.py` — extension points
- `src/yoker/backends/protocol.py`, `litellm.py`, `ollama.py` — backend capability + passthrough
- `src/yoker/config/__init__.py` `ContextConfig` — config additions
- `src/yoker/events/types.py` — new event