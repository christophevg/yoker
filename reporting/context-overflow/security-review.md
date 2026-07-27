# Security Review Report: IP-12 Context Overflow Management (Stage b)

Branch: feature/context-overflow (uncommitted)
Review date: 2026-07-27
Reviewer: security-engineer

## Executive Summary

All three blocking refinements from the prior security analysis
(`analysis/security-context-overflow.md`) are correctly implemented. The
setup-prefix invariant protects the skill-discovery user block and the first
real user turn; hook output validation checks shape, system-message
preservation, and tool-call/tool-result pairing with fallback to the framework
default on failure; truncation operates on a copy and assigns back atomically.
One non-blocking Medium correctness finding (stale `last_input_tokens` causes
over-truncation) is documented below. Verdict: **approved** with non-blocking
observations.

## Verification of Blocking Refinements

### Refinement 1: Setup-prefix invariant — CORRECT

`_protected_prefix_end` in `src/yoker/context/manager.py:205-253` correctly
identifies the protected prefix:

1. Walks all leading `role=system` messages (always protected).
2. Walks the contiguous `role=user` block that follows. The last user message
   in this block is the "first real user turn" (the one immediately followed by
   an assistant or tool message). Earlier user messages in the block are the
   scaffolding prefix (skill-discovery block from `add_skill_discovery_block`).
3. When `keep_first_user=True` (the default, `overflow_keep_first_user=True`
   in `ContextConfig`), the ENTIRE contiguous user block is protected — both
   scaffolding and first real user turn.
4. When `keep_first_user=False` with a real turn present, only the scaffolding
   prefix is protected (indices `user_run_start..i-2`); the first real user
   turn becomes droppable.
5. When there is no real turn yet (user block runs to end of list), all pending
   user messages stay protected regardless of `keep_first_user`.

Verified against the actual setup flow in `BaseContextManager.agent.setter`
(calls `setup_initial_context` → adds system message, then
`add_skill_discovery_block` → adds user message), which produces the layout
`[system, user(skills), user(first real turn), assistant, tool, ...]` the
function expects. The skill-discovery block sits in the contiguous user prefix
and is protected. Refinement satisfied.

### Refinement 2: Hook output validation — CORRECT

`_validate_hook_output` in `src/yoker/core/_processing.py:126-189` checks:

- **Shape**: `replacement` must be a list; every item must be a dict with a
  `role` key. Returns False on any violation. (lines 149-154)
- **No dropped `role=system` messages**: compares system-message counts;
  rejects if `replacement_system_count < original_system_count`. (lines
  157-160)
- **No orphaned tool results**: collects `referenced_tool_ids` from assistant
  `tool_calls` and `result_tool_ids` from `role=tool` messages (using
  `tool_id` with `name` fallback); rejects if `result_tool_ids` is not a
  subset of `referenced_tool_ids`. (lines 166-184)
- **No dangling tool calls**: rejects if `referenced_tool_ids` is not a subset
  of `result_tool_ids`. (lines 185-187)

Fallback on validation failure: `_apply_overflow_hook` (line 359) returns 0
on validation failure and logs a warning; `_manage_context_overflow` (lines
306-312) then runs `_apply_framework_default`. The hook exception path (lines
352-354) also returns 0 with a warning log. Refinement satisfied.

Minor note (non-blocking): the `tool_id` fallback to `name` (line 178) means
a tool result carrying only a tool name and no unique call id would be
checked against `referenced_tool_ids` by name. In normal Yoker operation
`add_tool_result` always sets `tool_id` to `call.id` (unique), so this is
defensive, not exploitable. A hook that returns tool results with neither
`tool_id` nor `name` would bypass the orphan check (the result is simply not
added to `result_tool_ids`), but such a malformed message would fail at the
backend, not create a security issue.

### Refinement 3: Truncate on a copy — CORRECT

`truncate_oldest_non_system` in `src/yoker/context/manager.py:148-194`:

- Computes `dropped_indices` from atomic units derived from
  `self._messages` (read-only during unit construction).
- Builds `new_messages` via a list comprehension over
  `list(self._messages)` (an explicit copy), filtering out dropped indices.
  No in-place mutation of `_messages` occurs during iteration.
- Assigns `self._messages = new_messages` atomically as the final step.
- `dropped_count` is computed from the length difference before assignment.

`replace_messages` (line 196-203) does `self._messages = list(messages)` — a
new list, no aliasing with the caller's list. Forwarding through
`ContextManagerWrapper` (`wrapper.py:88-99`) and `Persisted`
(`persisted.py:185-207`) is correct; the persisted wrapper rewrites the JSONL
file after the operation so on-disk state matches in-memory state. Refinement
satisfied.

## Additional Security Assessment

### Non-blocking finding: Stale `last_input_tokens` causes over-truncation

**Classification**: Related (correctness issue with security-adjacent impact)
**Severity**: Medium (CVSS ~4.5) — correctness; Low for security

**Location**: `src/yoker/core/_processing.py:375-405` (`_apply_framework_default`)

**Description**: `_estimate_tokens` (lines 89-123) returns `last_input_tokens`
directly when it is set and > 0, ignoring the actual message list. In
`_apply_framework_default`, the truncation loop (lines 390-404) calls
`_estimate_tokens(messages, last_input_tokens)` after each drop, but
`last_input_tokens` is the value captured from the PREVIOUS turn's backend
USAGE chunk — it does not reflect the truncated list. When
`last_input_tokens > max_tokens`, the estimate never decreases as messages
are dropped, so the loop continues until either all droppable messages are
exhausted (`dropped <= 0`) or `max_iterations` is hit.

**Impact**: The framework default drops ALL droppable messages (the entire
non-protected history) even when dropping one or two atomic units would
suffice. The protected prefix (system + skill discovery + first user turn)
is still preserved, so this is not a safety-policy bypass. The impact is
over-eviction of conversation history: earlier user instructions and
assistant reasoning are lost more aggressively than necessary, which is the
same class of risk as the "flooding evicts history" concern from the prior
review but self-inflicted rather than attacker-driven.

**Why not blocking**: The protected prefix invariant holds. No
safety-critical message (system prompt, skill discovery, first user turn)
can be dropped by this bug. The over-truncation only affects droppable
messages that would have been eligible for eviction anyway — just more of
them than needed. This is a correctness/efficiency issue, not a security
vulnerability.

**Remediation (owner's choice)**: In the truncation loop, recalculate the
estimate from the current (truncated) message list rather than reusing the
stale `last_input_tokens`. The simplest approach: pass `last_input_tokens=None`
to `_estimate_tokens` inside `_apply_framework_default` so it falls back to
the char/4 heuristic on the current list, or add a `recalculate` flag. This
is a one-line change inside the loop and does not add abstraction.

### Truncation safety — no safety-critical drops

The framework default preserves all `role=system` messages and the contiguous
user prefix (skill discovery + first real user turn). Atomic units
(`_atomic_units`, lines 255-282) group assistant+tool_calls with trailing
`role=tool` results so tool-call/tool-result pairing is never split during
truncation. No scenario was identified in which safety-critical messages are
dropped under normal operation. Confirmed: orphaned tool results (no preceding
assistant tool_calls) are treated as single-message units and can be dropped
independently — this is safe (no pairing to break) and arguably cleans up
inconsistent state.

### Exploitation via truncation — inherent, mitigated

An attacker (or misbehaving tool) can flood the context with large tool
outputs to evict earlier user instructions or assistant reasoning. This is
inherent to any fixed-window strategy (Claude Code has the same property)
and is the owner's proposal working as designed. The existing per-tool
output caps (`max_output_kb` on `make`/`github`, `max_size_kb` on
`webfetch`, `max_content_bytes` on content display) remain the correct
control point. No new guard needed. The over-truncation finding above makes
this slightly worse (more history evicted than necessary), which is the
one concrete reason to address it.

### Thinking-block stripping — safe

`_strip_thinking_blocks` (lines 63-86) removes only the `thinking` key via
shallow-copied dicts (`dict(msg)` + `pop`); it preserves `content` and the
assistant message itself. Matches Claude Code's `clear_thinking_20251015`
with `keep: "all"` behavior. For backends supporting `context_management`
(Anthropic), the provider-side directive is forwarded instead
(`_chat_stream`, lines 440-444) and no client-side strip runs. No safety
implication: the thinking trace is intermediate state, not a safety control;
the model's decisions live in assistant `content`, which is preserved.

### Denial of service — not a vector

`_estimate_tokens` uses `last_input_tokens` (O(1) lookup) when available,
else a char/4 heuristic that iterates the message list once (O(n), cheap
string-length sums). No tokenizer is invoked. The size check is not a DoS
vector. The `_apply_framework_default` loop is bounded by
`max_iterations = len(context) + 1` and breaks early when no more droppable
messages remain. No unbounded computation.

### Information leakage — no cross-context mixing

Truncation operates on a single agent's `_messages` via
`agent.context.get_context()` (returns `list(self._messages)` — a copy).
`replace_messages` creates a new list from the input. The hook receives a
copy of the list (though the dict items are shared references — see note
below). No agent-to-agent context mixing occurs; session isolation is
governed by `SessionConfig.default_isolation_policy`, which is a separate
mechanism unaffected by IP-12.

Non-blocking observation (Low): the hook receives `messages` from
`get_context()`, which shallow-copies the list but shares the dict item
references. A hook that mutates a dict in place (e.g.,
`messages[0]["content"] = "..."`) would mutate the context's actual dict.
This is not a security vulnerability because the hook is a trusted extension
(plugin trust gate, same as all IP-1..IP-13 templates), but the
implementation could defensively deep-copy the dicts passed to the hook if
desired. Flagging as Low; no action required given the trust gate.

## Findings Classification

| Finding | Classification | Action |
|---------|---------------|--------|
| Stale `last_input_tokens` causes over-truncation in `_apply_framework_default` | Related | Address in current task (one-line fix in the truncation loop) |
| Hook receives shared dict references (shallow copy) | New (Low) | Backlog; defensive deep-copy if untrusted hooks ever become a concern |
| `tool_id` fallback to `name` in validation | New (Low) | Backlog; tighten to `tool_id`-only if hook abuse becomes a concern |

## Positive Observations

- The setup-prefix invariant is precisely specified and correctly handles all
  edge cases (no skills, no real turn yet, `keep_first_user=False`).
- Atomic units guarantee tool-call/tool-result pairing is never split by the
  framework default — a subtle invariant that is easy to get wrong.
- The hook validation is comprehensive (shape, system preservation, orphaned
  results, dangling calls) with a clean fallback to the framework default on
  any failure, including exceptions.
- `_apply_framework_default` has a hard iteration cap and an early break on
  `dropped <= 0`, preventing infinite loops when truncation cannot reduce the
  estimate (e.g., all messages protected).
- Truncation and replacement forward correctly through `ContextManagerWrapper`
  and `Persisted`, re-persisting the JSONL state so the on-disk audit trail
  matches in-memory state.
- The `ContextOverflowEvent` (audit trail) was implemented as recommended in
  the prior review, carrying `message_count`, `estimated_tokens`,
  `max_tokens`, and `dropped_count`.
- The hybrid token estimation (last `input_tokens` primary, char/4 fallback)
  avoids the tokenizer DoS vector flagged in the prior review.

## Verdict

**approved** — all three blocking refinements are correctly implemented. The
single non-blocking Medium finding (stale `last_input_tokens` over-truncation)
is a correctness issue with security-adjacent impact (over-eviction of
history) that the owner should consider addressing in the current task, but
it does not breach the protected-prefix invariant or introduce a security
vulnerability. The owner's approved proposals (max_tokens=200,000, permanent
truncation, setup-prefix invariant, framework default dropping oldest
non-system messages) are faithfully implemented without unnecessary
abstraction.