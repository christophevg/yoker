# Context Overflow Management (IP-12) — Consensus

**Status: APPROVED — consensus reached**

This document records the consensus between the api-architect and security-engineer on the design of context overflow management (IP-12), with the PM-resolved tensions incorporated as binding. It is a coordination summary; the full designs live in:

- `analysis/api-context-overflow.md` (api-architect)
- `analysis/security-context-overflow.md` (security-engineer)

## Consensus Architecture

1. **Size check location**: in `core/_processing.py` `process_message()` before `_chat_stream`, where UsageStats from the previous turn are available and the request is dispatched. Detection is hybrid: last turn's `UsageStats.input_tokens` when available, with a char/4 heuristic fallback when usage stats are absent. No new dependency (e.g., tiktoken).

2. **Truncation entry point**: call `context.truncate_oldest_non_system(keep_first_user=True)` on the context manager. The context manager owns `_messages`; the processing layer owns the decision of when to call it.

3. **Protected set (setup-prefix invariant)**: all `role=system` messages + the contiguous `role=user` scaffolding prefix (including the skill-discovery block emitted by `add_skill_discovery_block()` in `context/manager.py`) + the first real user turn. Drop oldest non-setup messages from the tail.

4. **Drop unit**: tool-call-pair-aware. Never split an assistant `tool_calls` message from its trailing `tool` result messages. Drop in pair-consistent units from the tail.

5. **Backend protocol extension**: add `supports_context_management: bool` (default `False`) and `context_management: dict | None` kwarg to `ModelBackend.chat_stream`. Anthropic backend: pass through the thinking-clearing directive via `context_management`. Non-supporting backends: strip thinking blocks from message dicts programmatically before sending. The stripping is **always-on** when the backend lacks context_management support — no config flag.

6. **`on_context_overflow` hook**: `Callable[[OverflowContext], list[dict] | None]`. If provided and returns a valid list, use it instead of the framework default. If `None` or invalid, fall back to the framework default (`drop_oldest`) and log a warning. Ships as `None` until prompt sets exist; this is an extension point, not the primary mechanism.

7. **Event**: `ContextOverflowEvent(message_count, estimated_tokens, max_tokens, dropped_count)` in `events/types.py`, emitted once per overflow occurrence. This is the audit trail (satisfies the security-engineer's audit concern) — it records what was dropped.

8. **Config**: two flat fields on `ContextConfig`:
   - `max_tokens: int = 200_000` — context size threshold
   - `overflow_keep_first_user: bool = True` — keep first user message (with config injections) during truncation

   Dropped fields: `overflow_strategy` (the framework always does `drop_oldest`; the hook overrides if present — an enum for a single default is unearned complexity) and `overflow_strip_thinking` (the owner's wording is unconditional — the flag is unearned configurability).

## Resolved Tensions (PM binding)

1. **Permanent vs per-request truncation** → **Permanent**. Dropped messages are removed from `_messages` (matches owner's "messages are simply gone" wording and CC's observed behavior). `ContextOverflowEvent` is the audit trail.

2. **Setup-prefix invariant** → **Incorporated** (security-engineer refinement 1). The protected set is: all `role=system` + contiguous `role=user` scaffolding prefix (including skill-discovery block) + first real user turn. This refines the api-architect's "keep all role=system + first role=user" to be precise about the scaffolding prefix.

3. **Hook output validation** → **Incorporated** (security-engineer refinement 2). The hook's output must be validated for correct shape (roles, `tool_call`/`tool_result` pairing, no orphaned `tool_ids`) and must not drop `role=system` messages. On validation failure: fall back to framework default + log a warning. This is the one guard the hook earns — a malformed list breaks the backend tool-use contract.

4. **Where the size check lives** → **Check in `core/_processing.py`, truncation method on `BaseContextManager`**. Not a real conflict — both agents agree the context manager owns `_messages`; the check lives where the request happens (where UsageStats are available).

5. **`overflow_strip_thinking` flag** → **Dropped**. The owner's wording is unconditional: "if backend does not support it, strip thinking blocks." Behavior is always-on when the backend lacks `context_management` support.

6. **`overflow_strategy` field** → **Dropped**. Keep `drop_oldest` as the only framework strategy. The hook is an extension point that overrides if present — not a strategy enum value. Simpllicity Principle: a strategy enum for a single-default framework is unearned complexity.

7. **`overflow_keep_first_user` field** → **Kept** (default `True`). This is the one behavioral knob that's earned — an advanced user might want to drop everything except system messages. Default `True` matches the owner's proposal.

## Security Refinements Incorporated

All three security-engineer blocking refinements are incorporated as binding:

- **R1 — Setup-prefix invariant**: the protected set explicitly includes the contiguous `role=user` scaffolding prefix (skill-discovery block at `context/manager.py:54-63`) sitting between the system message and the first real user turn. See resolved tension #2.

- **R2 — Hook output validation**: the `on_context_overflow` hook output is validated for shape (roles, `tool_call`/`tool_result` pairing, no orphaned `tool_ids`) and must not drop `role=system` messages. On failure: fall back to framework default + log. See resolved tension #3.

- **R3 — Truncate on a copy**: `get_context()` returns `list(self._messages)`; truncation operates on that copy, not `_messages` in place. `truncate_oldest_non_system()` then assigns the truncated copy back to `_messages` as a single atomic replacement (preserves persisted history integrity and the audit trail via the event). Implemented on `BaseContextManager` + `Persisted` + `Wrapper` + the `ContextManager` Protocol.

Additionally: the security-engineer's positive finding — **framework-driven truncation eliminates prompt-injection-via-summarization risk** — is accepted. The framework does not summarize; it drops. No untrusted content is promoted into a summary that the model then trusts.

## Simplified Config

Three fields were proposed by the api-architect; the consensus keeps **two** (the third, `overflow_strip_thinking`, was mistakenly counted as "kept" — it is dropped per resolution #5):

| Field | Kept? | Default | Rationale |
|-------|-------|---------|-----------|
| `max_tokens` | Yes | `200_000` | Threshold for overflow detection |
| `overflow_keep_first_user` | Yes | `True` | Earned knob — advanced users may drop everything except system |
| `overflow_strategy` | **No** | — | Single default framework; hook is an extension point, not a strategy |
| `overflow_strip_thinking` | **No** | — | Owner's wording is unconditional; always-on when backend lacks support |

(Per the task brief: "Three flat fields on ContextConfig (not four)" — counting only the kept fields, the final config is two fields. The "three vs four" framing in the brief reflects the api-architect's original four minus the one dropped `overflow_strip_thinking`; the consensus drops two, leaving two. The PM resolution #6 additionally drops `overflow_strategy`.)

## Owner-Stated Proposals (Quoted Verbatim)

These are binding — the consensus satisfies each one:

- "Framework default: drop oldest non-system messages when over threshold (keeping first user message with config injections)"
- "If backend supports context_management API field (Anthropic), pass through thinking token clearing directive"
- "If backend does not support it, strip thinking blocks from message history programmatically"
- "Optional on_context_overflow hook for prompt sets that want custom truncation strategies"
- "This is an extension point, not the primary mechanism." (re: hook)
- "R12a: The framework must provide default context overflow management (drop oldest non-system messages when over threshold) without requiring a prompt set template."

**Satisfaction check**:
- Drop-oldest default → architecture point 1-4.
- Anthropic passthrough → architecture point 5.
- Strip thinking when unsupported → architecture point 5 (always-on, no flag).
- Optional hook as extension point → architecture point 6.
- R12a (framework default without prompt set) → ships as `None`; default `drop_oldest` runs unconditionally when over threshold.

## Open Questions for the Owner

To be posted in the implementation plan for confirmation:

1. **`max_tokens` default**: 200,000 is a reasonable default for modern models (Claude 200k, GPT-4 128k, Gemini 1M). Should the default be lower (e.g., 128,000) or per-model? **Recommendation**: 200,000 single config field; user can override.

2. **Permanent truncation confirmation**: the framework permanently removes dropped messages from `_messages` (matching "messages are simply gone"). The `ContextOverflowEvent` records what was dropped for audit. **Confirm this is acceptable.**

3. **Setup-prefix invariant confirmation**: the protected set includes the skill-discovery `role=user` block (scaffolding between system and first real user turn). **Confirm this is the intended behavior.**

## Approvals

- **api-architect**: APPROVES. The consensus preserves the core architecture (check location, hybrid detection, backend protocol extension, hook extension point, event audit trail, permanent truncation). The PM resolutions simplify the config surface in a direction consistent with the api-architect's own Q4 (drop `overflow_strip_thinking`) and the Simplicity Principle (drop `overflow_strategy`). The setup-prefix invariant refines "keep first user" to a precise, correct protected set.

- **security-engineer**: APPROVES. All three blocking refinements are incorporated as binding: setup-prefix invariant (R1), hook output validation (R2), truncate-on-copy (R3). The permanent-truncation + event-audit-trail pairing satisfies the audit concern. Framework-driven truncation (no summarization) preserves the prompt-injection-via-summarization safety property.