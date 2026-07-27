# API Review: Context Overflow Management (IP-12)

**Date**: 2026-07-27
**Reviewer**: API Architect Agent
**Task**: Domain review (Stage b) for the Context Overflow Management implementation on `feature/context-overflow`.

## Summary

The implementation is a faithful, slim realization of the owner's approved proposals. The `ModelBackend` Protocol extension (`supports_context_management: bool` + `context_management: dict | None` kwarg) is minimal and structural-typing-safe. The truncation API (`truncate_oldest_non_system` + `replace_messages`) is well-shaped and correctly forwarded through `ContextManagerWrapper` and `Persisted`. The `ContextOverflowEvent` field set is sufficient. The config surface is flatter than the design doc proposed (two fields, not four) — a correct application of the Simplicity Principle. The `on_context_overflow` hook ships as `None` per the owner's "extension point, not primary mechanism" framing.

**Verdict: approved** with four non-blocking observations.

## Findings

### Strengths

1. **Protocol extension is minimal and backward-compatible.** `supports_context_management: bool` is a single capability flag (no capability enum — the design doc's §9 explicitly ruled that out). The `context_management: dict | None` kwarg is provider-defined passthrough (Yoker does not interpret it), correctly typed as `dict[str, Any]` rather than a typed dataclass. The call site uses `getattr(backend, "supports_context_management", False)`, so backends that don't declare the attribute still work — important because `ModelBackend` is a `@runtime_checkable` Protocol, not an ABC.

2. **Truncation API is well-designed.** `truncate_oldest_non_system(keep_first_user: bool = True, drop_count: int = 1) -> int` returns the dropped count, which feeds directly into `ContextOverflowEvent.dropped_count`. The `drop_count` parameter supports batch truncation even though the framework default uses `drop_count=1` in a loop (one atomic unit per iteration so the event's cumulative count is exact). Atomic units (assistant `tool_calls` + trailing `role=tool` results dropped together) correctly preserve tool-call/tool-result pairing — the owner's "drop as a unit" requirement.

3. **`replace_messages` is earned.** The hook replacement path and the thinking-strip fallback both need to overwrite `_messages` atomically. Without `replace_messages`, the processing loop would reach into `_messages` directly, breaking the `Persisted` wrapper's bulk-rewrite invariant. The Protocol docstring correctly notes that persisting implementations must rewrite their storage after replacing the in-memory list. `Persisted.replace_messages` delegates then `_persist_full_state` — one bulk rewrite, not one per message.

4. **Config surface is flatter than proposed — correct simplification.** The design doc (`analysis/api-context-overflow.md` §7) proposed four fields: `max_tokens`, `overflow_strategy`, `overflow_keep_first_user`, `overflow_strip_thinking`. The implementation ships two: `max_tokens` (200_000, validated `positive_int`) and `overflow_keep_first_user` (True). `overflow_strip_thinking` was dropped because the owner's proposal makes the fallback unconditional ("if backend does not support it, strip thinking blocks") — the flag is unearned configurability. `overflow_strategy` was dropped because only one strategy ships. This is exactly the simplification the Simplicity Principle demands.

5. **Event design is sufficient.** `ContextOverflowEvent` carries `message_count`, `estimated_tokens`, `max_tokens`, `dropped_count` — enough for an audit trail and a UI "context trimmed" notice. Frozen dataclass, inherits `timestamp` from `Event`, emitted once per overflow (not per dropped message). No `ContextTrimmedEvent`/`ContextRestoredEvent` — one event, one purpose.

6. **Hook wiring is correct for "ships as None."** `on_context_overflow` is a parameter on `process_message` (a private function called by `Agent._process_consumer`). The hook is `None` by default, so the framework default always runs. `_validate_hook_output` enforces shape, `role=system` preservation, and tool-call/tool-result pairing — the owner's "validated replacement list" requirement. On validation failure, the framework default runs and a warning is logged. The `OverflowContext` TypedDict is the right payload shape (matches D3's template variables).

7. **No unearned abstractions.** No `ContextCompactor`, no `TokenEstimator` class, no `ContextOverflowConfig` nested dataclass, no per-model context-window registry. `_estimate_tokens` is a function (hybrid: last turn's `input_tokens` primary, char/4 fallback — no new dependency, per Q5's recommendation). `_strip_thinking_blocks` is a function. The four `_apply_*`/`_manage_*` helpers in `_processing.py` are factored for readability, not indirection — each has a single responsibility and the `process_message` loop stays clean.

### Observations (Non-Blocking)

#### O1 — `on_context_overflow` is not threaded through `Agent.process()`

`Agent._process_consumer` calls `process_message(self, message)` without forwarding `on_context_overflow`, and `Agent.process(message)` has no hook parameter. So the hook is currently unreachable from the public API — only the unit tests exercise it (via `_apply_overflow_hook` directly).

This is intentional per the owner's framing ("ships as None until prompt sets exist") and the design doc (`agent._on_context_overflow` "stays None until prompt sets wire it"). The current parameter-on-`process_message` approach is arguably cleaner than storing the hook on the Agent because it keeps the Agent stateless with respect to overflow strategy and makes the hook testable in isolation.

When prompt-set integration lands, the wiring will need to either (a) thread the parameter through `Agent.process()` → `_process_consumer` → `process_message`, or (b) store the hook on the Agent and have `_process_consumer` read it. Both are small changes. Flagging so the future wiring point is a conscious decision, not an accidental gap.

**Severity**: Low (intentional, documented).
**Recommendation**: When prompt sets land, prefer option (b) (store on Agent) to avoid changing the public `Agent.process()` signature. The `process_message` parameter can stay as the internal injection point.

#### O2 — `replace_messages` docstring overstates the ownership contract

The Protocol docstring says: "callers should not retain references to the same list." The implementation in `BaseContextManager.replace_messages` does `self._messages = list(messages)` — a defensive copy. So callers CAN safely retain references; the context manager does not take ownership of the passed list.

This is a mild doc/code mismatch. The defensive copy is the right behavior (the processing loop's `_strip_thinking_blocks` returns a fresh list, but `_apply_overflow_hook` passes `list(replacement)` explicitly — both are safe under either contract). The docstring's "should not retain" is stricter than the code requires.

**Severity**: Low (documentation).
**Recommendation**: Either soften the docstring to "the context manager copies the list; callers may safely retain references" or keep the strict contract and document that the copy is defensive. The current wording could mislead a future caller into unnecessary list duplication.

#### O3 — Thinking-strip rewrites JSONL on every turn for `Persisted` + non-supporting backends

`_maybe_strip_thinking` runs every loop iteration (not just on overflow) for backends that lack `supports_context_management`. It calls `replace_messages(_strip_thinking_blocks(messages))`, which in `Persisted.replace_messages` triggers a full `_persist_full_state` — a complete JSONL bulk-rewrite on every turn, even when no messages were actually stripped (the early-return `if not any("thinking" in m for m in messages)` mitigates this when there are no thinking blocks, but once any assistant message has `thinking`, every subsequent turn rewrites the file).

The design doc (§1) noted this concern and originally proposed a *view* (transient, per-request) for truncation to avoid exactly this. The owner's "permanent truncation" decision resolved Q1 for the overflow path, but the thinking-strip path is separate: it runs unconditionally on non-supporting backends, not just on overflow. The strip result is written back into `_messages` (permanent) so thinking blocks don't accumulate — correct behavior, but the persistence cost is a side effect.

**Severity**: Low (performance, not correctness).
**Recommendation**: If JSONL write amplification shows up in profiles, consider (a) making the thinking-strip a *view* (hand stripped list to backend without `replace_messages`) and only persisting the strip on overflow, or (b) tracking a "thinking already stripped" flag on the context to skip re-stripping. No action needed now — flagging for future profiling.

#### O4 — `ContextManager` Protocol gained two methods; external implementations need updating

The `@runtime_checkable` `ContextManager` Protocol now requires `truncate_oldest_non_system` and `replace_messages`. All in-tree implementations (`BaseContextManager`, `SimpleContextManager` via inheritance, `ContextManagerWrapper`, `Persisted`) satisfy the extended Protocol. A third-party `ContextManager` implementation that satisfied the old Protocol would no longer satisfy the new one — `isinstance(cm, ContextManager)` would return `False`, and the methods would be missing at runtime.

This is a breaking change for external implementers of the Protocol. In practice the Protocol is internal-facing (the public API exposes `ContextManager` only as a type annotation on `Agent.__init__`'s `context_manager` parameter), so the blast radius is small. But it's worth noting for the CHANGELOG.

**Severity**: Low (external-compat).
**Recommendation**: Note the Protocol surface change in the CHANGELOG/release notes. No mitigation needed unless external implementers are known to exist.

## Compliance Check

- **RESTful design**: N/A — this is an internal Python API, not an HTTP API. No RPC-style endpoints involved.
- **Async-first**: The implementation is async-first (`_manage_context_overflow` is `async`, `process_message` is `async`). The hook is invoked synchronously inside `_apply_overflow_hook` (not awaited) — acceptable because the hook is a pure CPU operation (validation + list replacement) with no I/O. If a future hook needs I/O (e.g., calling a tokenizer API), it should be made async. Non-blocking.
- **Simplicity Principle**: No unearned abstractions. The implementation dropped two of the four proposed config fields (`overflow_strategy`, `overflow_strip_thinking`) — correct simplification. The `OverflowContext` TypedDict, `_validate_hook_output`, and `replace_messages` are all earned by the owner's "validated hook replacement" requirement.
- **Owner's proposals honored**: All five binding proposals are implemented verbatim:
  - "Framework default: drop oldest non-system messages when over threshold (keeping first user message with config injections)" → `_apply_framework_default` + `_protected_prefix_end` (contiguous user prefix = scaffolding + first real user turn).
  - "If backend supports context_management API field (Anthropic), pass through thinking token clearing directive" → `_ANTHROPIC_CLEAR_THINKING` forwarded via `_chat_stream` when `supports_context_management` is True.
  - "If backend does not support it, strip thinking blocks from message history programmatically" → `_maybe_strip_thinking` + `_strip_thinking_blocks`, always-on for non-supporting backends.
  - "Optional on_context_overflow hook for prompt sets that want custom truncation strategies" → `on_context_overflow` parameter on `process_message`, ships as `None`, `_apply_overflow_hook` + `_validate_hook_output`.
  - "This is an extension point, not the primary mechanism." → hook fires before framework default; on `None`/invalid/exception, framework default runs.
  - max_tokens = 200,000, permanent truncation, setup-prefix invariant — all implemented as approved.

## Recommendations

1. (Optional, future) When wiring the hook through `Agent.process()`, prefer storing the hook on the Agent over changing the public `process()` signature.
2. (Optional, doc) Clarify the `replace_messages` ownership contract in the Protocol docstring.
3. (Optional, future) Monitor JSONL write amplification from `_maybe_strip_thinking` on `Persisted` + non-supporting backends; consider a view-based strip if it shows up in profiles.
4. (Release process) Note the `ContextManager` Protocol surface extension in the CHANGELOG.

## Conclusion

**approved**

The implementation is a clean, minimal realization of the owner's approved design. No blocking API-design issues. The four observations above are all non-blocking (documentation, future-wiring, performance-monitoring, and release-notes). The implementation correctly applies the Simplicity Principle — it ships less than the design doc proposed, and the omissions are justified.

## Next Steps

Proceed to the next domain review (Stage c). No API-design changes required before merge.