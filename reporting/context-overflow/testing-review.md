# Testing Review: IP-12 Context Overflow Management (Stage c)

Branch: feature/context-overflow (uncommitted)
Review date: 2026-07-27
Reviewer: testing-engineer
Verdict: **approved** (with non-blocking observations)

## Summary

All 49 new tests across 4 files pass (`make check` green: 2155 passed,
8 skipped). The suite covers all six acceptance criteria and all three
security refinements. Tests verify behavior (protected set survival,
tail-eviction ordering, tool-call-pair atomicity, hook validation
outcomes, backend kwarg forwarding) rather than implementation details,
and they use real `BaseContextManager` / `Persisted` / `LitellmBackend`
instances instead of mocking the unit under test. The stale-token
regression test correctly reproduces the bug fixed in
`_apply_framework_default` and would fail if the fix were reverted.

## Acceptance Criteria Coverage

| # | Criterion | Covered by | Verdict |
|---|-----------|------------|---------|
| 1 | Context size check before each request | `test_under_cap_does_not_truncate`, `test_over_cap_truncates_and_emits_event` | OK |
| 2 | Drop oldest non-system, keep first user msg | `TestProtectedSetPreserved` (3), `TestOldestDroppedFromTail` (2), `TestKeepFirstUserFalse` (2) | OK |
| 3 | Anthropic context_management passthrough | `test_litellm_anthropic_supports`, `test_litellm_anthropic_forwards_directive`, `test_protocol_declares_attribute` | OK |
| 4 | Non-supporting: strip thinking blocks | `TestStripThinkingBlocks` (3), `test_thinking_blocks_stripped_for_non_supporting_backend`, `test_thinking_blocks_preserved_for_supporting_backend`, `test_litellm_openai_drops_directive`, `test_ollama_accepts_and_ignores_directive` | OK |
| 5 | Optional on_context_overflow hook (with validation) | `TestValidateHookOutput` (9), `TestApplyOverflowHook` (5) | OK |
| 6 | Long sessions no longer crash | Implicit via the overflow loop being bounded and tested; no explicit crash-regression test | See observation 1 |

## Security Refinement Coverage

| # | Refinement | Covered by | Verdict |
|---|-----------|------------|---------|
| 1 | Setup-prefix invariant (protect skill-discovery role=user block) | `test_scaffolding_user_block_protected`, `test_first_real_user_turn_protected_when_keep_first_user_true`, `test_system_messages_protected_even_when_keep_first_user_false` | OK |
| 2 | Hook output validation (shape, no dropped role=system, tool_call/tool_result pairing) | `test_non_list_replacement_fails`, `test_non_dict_item_fails`, `test_item_missing_role_fails`, `test_dropped_system_message_fails`, `test_orphaned_tool_result_fails`, `test_dangling_tool_call_fails`, `test_paired_tool_call_and_result_passes`, `test_invalid_replacement_drops_nothing` | OK |
| 3 | Truncate on a copy | `test_replace_messages_copies_caller_list` (caller-list copy); `test_does_not_mutate_caller_list` (thinking-strip non-mutation); `test_drop_one_atomic_unit_from_tail` (atomic-unit semantics) | OK |

## Test Quality

### Strengths

- **Behavior-focused assertions.** Tests assert on `role`/`content`
  presence in `cm._messages` and `get_context()`, not on internal helper
  state. They would survive any refactor of `_protected_prefix_end` /
  `_atomic_units` as long as the protected-set and atomic-pair
  contracts hold.
- **Real units under test.** Truncation tests use real
  `BaseContextManager`, `Persisted`, and `ContextManagerWrapper`
  instances; backend tests use real `LitellmBackend` / `OllamaBackend`
  with only the downstream SDK call patched. This is the right altitude
  — the test verifies the actual contract, not a mock interaction.
- **Atomic-pair coverage is meaningful.** `test_tool_call_pair_dropped_atomically`
  and `test_tool_call_pair_not_split_by_drop_count_one` verify the
  security invariant that an assistant `tool_calls` message is never
  orphaned from its trailing `role=tool` results, including the boundary
  where `drop_count=1` would naively split the pair.
- **Hook validation matrix is exhaustive.** 9 tests cover the shape,
  system-preservation, and tool-pairing rules plus the valid case. The
  fallback-on-failure path is covered by `test_invalid_replacement_drops_nothing`
  and `test_hook_exception_drops_nothing`.
- **Stale-token regression test is correct.** See dedicated section
  below.

### Stale-Token-Estimate Regression Test

`test_stale_last_input_tokens_does_not_evict_all_droppable` correctly
verifies the bug fixed in `_apply_framework_default`:

- Setup: 8 messages (system 3 chars, user 2 chars, 6× assistant 8 chars
  each), `max_tokens=8`, `stale_last_input_tokens=5000`.
- Math: full list = 53 chars → 13 tokens (char/4). Dropping 3
  assistants → 29 chars → 7 tokens (≤ 8). So 3 assistants must survive.
- The test asserts `assistant_count == 3` — exactly the expected
  post-fix behavior. If the bug were present (passing `last_input_tokens`
  into `_estimate_tokens` inside the loop), the estimate would stay at
  5000 and all 6 droppable assistants would be evicted; the assertion
  would fail with `got 0`.
- The test passes `stale_last_input_tokens` positionally to
  `_manage_context_overflow`, which routes it to `_estimate_tokens` for
  the *initial* over-cap check (correct — the stale value still
  triggers overflow) and then to `_apply_framework_default`, where the
  loop passes `None` (the fix) so the heuristic recalculates on the
  truncated list. The regression test exercises exactly the path the
  fix touched.

This is a high-value regression test.

## Non-blocking Observations

### 1. No explicit "long sessions no longer crash" regression test (criterion 6)

The acceptance criterion "long sessions no longer crash" is covered
indirectly: `_apply_framework_default`'s `max_iterations` bound and
early-break on `dropped <= 0` are exercised by the over-cap tests, so
the loop provably terminates. There is no test that constructs a
multi-turn-style large context (e.g. 100 messages) and asserts the
overflow path completes without raising. The current over-cap test
with `max_tokens=1` and 5 messages is the closest. This is acceptable
because the loop-termination invariants are tested, but a dedicated
"large context, over cap, no exception" test would make criterion 6
explicit. Non-blocking.

### 2. No end-to-end test through `process_message`

The overflow machinery is tested via `_manage_context_overflow`
directly. `process_message`'s `on_context_overflow` parameter (which
ships as `None`) is not exercised end-to-end. The hook path through
`_manage_context_overflow` → `_apply_overflow_hook` →
`_validate_hook_output` is covered by unit tests but not chained
through the real `process_message` loop. Given the hook ships
disabled, this is a minor integration gap, not a coverage hole. The
framework-default path through `process_message` is similarly not
exercised end-to-end with a real backend; the `_chat_stream`
`context_management` kwarg forwarding is tested separately at the
backend layer. Non-blocking.

### 3. Missing edge cases (minor)

- **Empty `_messages`**: `truncate_oldest_non_system` guards
  `if drop_count <= 0 or not self._messages: return 0`, but no test
  constructs an empty `cm._messages = []` and calls
  `truncate_oldest_non_system`. The `test_truncate_idempotent_when_no_droppable`
  test uses a 2-message all-protected list, which exercises the
  "no droppable units" path but not the empty-list path. Both paths
  return 0, so the risk is low.
- **Single-message context**: not explicitly tested.
- **All-system messages**: `test_system_messages_protected_even_when_keep_first_user_false`
  is close (2 system + 1 user + 1 assistant) but not a pure
  all-system list. The protected-prefix walk handles all-system
  correctly (returns `n`), but it's not asserted.
- **Orphaned tool result in the droppable tail** (no preceding
  assistant `tool_calls`): `_atomic_units` treats a lone `role=tool`
  message as a single-message unit. This is safe but not tested.
  The hook-validation path tests orphaned results
  (`test_orphaned_tool_result_fails`), but the framework-default
  truncation path does not.

These are all low-risk gaps on guard clauses or already-safe
behaviors. Non-blocking.

### 4. Type annotation nit

`test_persisted_truncate_rewrites_jsonl` annotates `tmp_path` as
`pytest.TempPathFactory`, but the `tmp_path` fixture injects a
`pathlib.Path` (`TempPathFactory` is the type of the
`tmp_path_factory` fixture). This is a wrong annotation that doesn't
affect runtime (pytest doesn't enforce annotations) but would fail
strict typecheck if the test files were typechecked. The mypy config
in `pyproject.toml` excludes tests, so this doesn't break `make
check`. Non-blocking; worth fixing for correctness:

```python
def test_persisted_truncate_rewrites_jsonl(self, tmp_path: Path) -> None:
```

### 5. Async style inconsistency

`test_context_overflow_detection.py` uses `asyncio.run()` inside
synchronous test functions, while `test_context_management.py` uses
`@pytest.mark.asyncio`. Both work; the project's `pyproject.toml`
configures `asyncio_mode = "auto"`, so either style is supported.
The `asyncio.run` style is slightly more isolated (no fixture
dependency) but harder to read when interspersed with sync setup.
Non-blocking style observation.

## Test Isolation

Each test constructs its own `BaseContextManager` and assigns
`cm._messages` directly. No shared state across tests. The Persisted
test uses the `tmp_path` fixture for an isolated JSONL directory per
test. The mock agents in `test_context_overflow_detection.py` and
`test_overflow_hook.py` are built per-test via the `_make_agent`
helper. No fixture leakage. Isolation is clean.

## Coverage of Integration Flows

The processing pipeline is unit-tested at the right granularity:

- `_manage_context_overflow` (under/over cap, thinking-strip,
  stale-token) — 5 tests.
- `_apply_overflow_hook` (valid, None, invalid, exception, payload) —
  5 tests.
- `_validate_hook_output` (9 cases) — 9 tests.
- `_strip_thinking_blocks` (drops, non-mutation, length) — 3 tests.
- `_estimate_tokens` (usage, fallback, zero, content sum) — 4 tests.
- Backend `supports_context_management` + `context_management` kwarg
  forwarding — 7 tests.

The only integration gap is the absence of a test that runs
`process_message` end-to-end with a fake backend that returns a
USAGE chunk triggering overflow on the next iteration. This would
verify the `last_input_tokens` capture-from-stats path
(`stats.get("input_tokens")` / `prompt_eval_count`) and the loop's
re-entry into `_manage_context_overflow`. Non-blocking (see
observation 2).

## Missing Tests (Summary)

None blocking. The following would strengthen the suite but are not
required for approval:

1. Empty `_messages` truncation (guard clause).
2. All-system `_messages` truncation (protected-prefix edge).
3. Orphaned tool result in framework-default truncation (lone
   `role=tool` as a single-message atomic unit).
4. End-to-end `process_message` with a fake backend returning a USAGE
   chunk that triggers overflow on the next loop iteration.
5. Explicit "large context, over cap, no exception raised" test for
   criterion 6.

## Verdict

**approved.** The suite covers all acceptance criteria and security
refinements with behavior-focused tests on real units. The
stale-token regression test correctly verifies the fix. The
observations above are non-blocking polish items; none represent a
coverage hole on a safety-critical or behavior-critical path.