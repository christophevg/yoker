# Testing-Engineer Review Round 1: M.2 Default Tools Behavior (Sentinel Refactor)

- **Task**: M.2 Default Tools Behavior (PR #47, round 1 — sentinel refactor + api.py alignment)
- **Branch**: `feature/m2-default-tools-behavior`
- **Reviewer**: testing-engineer
- **Date**: 2026-07-20
- **Stage**: Stage c (Quality Review — testing-engineer) of the c3:project-review cycle, scoped re-review after owner feedback
- **Verdict**: approved (with minor recommendations — no blockers)

## Scope reviewed

- Source diff: `src/yoker/agents/{schema,__init__,loader,validator}.py`, `src/yoker/core/__init__.py`, `src/yoker/api.py`, `src/yoker/ui/commands/{tools,agents}.py`
- Test diff: `tests/core/test_agent_tools.py`, `tests/agents/{test_loader,test_validator}.py`, `tests/test_agent.py`, `tests/test_api/test_builder.py`
- Re-ran `make test`: 1891 passed, 15 warnings, 0 failures; ruff/mypy clean. +2 tests vs round 0 (`test_tools_none_disables_all`, `test_tools_all_tools_sentinel_keeps_all`).

## Verification against the 9 review prompt points

### 1. 8-case loader matrix — COMPLETE

All eight cases are covered in `tests/agents/test_loader.py` and `tests/core/test_agent_tools.py::TestLoaderMatrix`, with the correct `is ALL_TOOLS` / `== ()` distinction:

| # | Case | Test | Assertion |
|---|------|------|-----------|
| 1 | key absent | `test_load_missing_tools_loads_all_tools_sentinel` (loader); `test_missing_tools_loads_all_tools_sentinel` (matrix) | `tools is ALL_TOOLS` |
| 2 | `tools:` bare | `test_present_null_tools_loads_no_tools[""]` | `tools == ()`, `tools is not ALL_TOOLS` |
| 3 | `tools: null` | `test_present_null_tools_loads_no_tools["null"]` | `tools == ()`, `tools is not ALL_TOOLS` |
| 4 | `tools: ~` | `test_present_null_tools_loads_no_tools["~"]` | `tools == ()`, `tools is not ALL_TOOLS` |
| 5 | `tools: ""` | `test_load_empty_tools_string`; also matrix parametrized | `tools == ()`, `tools is not ALL_TOOLS` |
| 6 | `tools: []` | `test_present_null_tools_loads_no_tools["[]"]` | `tools == ()`, `tools is not ALL_TOOLS` |
| 7 | explicit list | `test_load_explicit_tools_list_filters`; `test_explicit_list_filters` | `tools == ("file:read", "file:list")`, `tools is not ALL_TOOLS` |
| 8 | default `AgentDefinition()` | `test_default_constructor_grants_all_tools` (matrix) | `tools is ALL_TOOLS` |

The missing-vs-present distinction is asserted via identity (`is ALL_TOOLS`), not equality — exactly what the sentinel design calls for. No case conflates the two states.

### 2. api.py contract alignment — COMPLETE (all 5 cases)

`tests/test_api/test_builder.py::TestAgentBuilderTools` covers the full contract:

| Call | Test | Assertion |
|------|------|-----------|
| `yoker.agent()` | `test_tools_default_keeps_all` | `len(a.tools.names) > 0` |
| `yoker.agent(tools=None)` | `test_tools_none_disables_all` (NEW) | `list(a.tools.names) == []` |
| `yoker.agent(tools=[])` | `test_tools_empty_disables_all` | `list(a.tools.names) == []` |
| `yoker.agent(tools=["read"])` | `test_tools_whitelist` | `read` kept, `write`/`git` filtered |
| `yoker.agent(tools=ALL_TOOLS)` | `test_tools_all_tools_sentinel_keeps_all` (NEW) | `len(a.tools.names) > 0` |

The dual contract flagged in round 0 is now eliminated: `yoker.agent(tools=None)` → no tools (matches `AgentDefinition(tools=None)`), verified by an explicit-kwarg test. The two new tests directly address round-0 minor recommendation #4.

### 3. Sentinel-specific tests — GAP (minor, non-blocking)

The `AllToolsSentinel` class in `src/yoker/agents/schema.py` implements five defensive/special methods that are **not exercised by any test**:

| Method | Line | Purpose | Tested? |
|--------|------|---------|---------|
| `__new__` (singleton) | 24-27 | `AllToolsSentinel() is AllToolsSentinel()` | NO |
| `__bool__` | 32-34 | sentinel is truthy (distinct from `()` / `None`) | NO |
| `__iter__` (raises `TypeError`) | 36-39 | non-iterability guard | NO |
| `__eq__` / `__hash__` | 41-45 | identity-based equality | NO |
| `__reduce__` + `_resolve_all_tools` | 47-54 | pickle round-trip preserves singleton | NO |

Coverage report confirms: `src/yoker/agents/schema.py` at 86%, with lines 34, 39, 42, 45, 49, 54 uncovered — exactly these methods.

These are defensive properties: the runtime never iterates the sentinel (all five guard sites use `isinstance(..., AllToolsSentinel)` first), never pickles an `AgentDefinition`, and never compares with `==`. The tests verify the **contract** (the sentinel flows through loader/api/runtime correctly) but not the **sentinel's own guarantees**.

Recommendation (minor): add a small `TestAllToolsSentinel` class with 3-4 tests:
- `AllToolsSentinel() is AllToolsSentinel()` (singleton identity)
- `with pytest.raises(TypeError): iter(ALL_TOOLS)` (non-iterability — the guard that protects the five call sites)
- `pickle.loads(pickle.dumps(ALL_TOOLS)) is ALL_TOOLS` (pickle round-trip — `__reduce__` is implemented, should be verified)
- `bool(ALL_TOOLS) is True` (truthiness — distinct from `()` / `None`)

These are cheap, lock the sentinel's invariants, and would cover the 6 uncovered lines. Non-blocking: the absence of these tests does not put any M.2 acceptance criterion at risk, because the runtime never relies on these methods directly (the `isinstance` guards run first).

### 4. Guard tests — PARTIAL (3 of 5 covered; 2 UI display paths untested)

The five guard sites that protect against iterating the sentinel:

| # | Guard site | Sentinel path covered? | Evidence |
|---|-----------|------------------------|----------|
| 1 | `_warn_missing_tools` (`core/__init__.py:384`) | YES (implicit) | Every `Agent(config=Config(), agent_definition=AgentDefinition())` construction in `TestRuntimeFiltering` takes the early-return. `test_warn_not_emitted_when_tools_explicitly_empty` confirms no spurious warning when sentinel is set. |
| 2 | `validate_agent_definition` (`validator.py:104`) | YES | `tests/agents/test_validator.py` at 100% coverage; `test_validate_empty_tools` asserts `validate_agent_definition(AgentDefinition(...), config.tools) == []` with the default sentinel. |
| 3 | `_namespace_tools` call site (`loader.py:145`) | YES | `test_load_missing_tools_loads_all_tools_sentinel` loads a file with no `tools:` key → sentinel flows through, namespacing skipped, `tools is ALL_TOOLS` preserved. |
| 4 | `/tools` command display (`ui/commands/tools.py:87-88`) | NO | `tests/test_commands/test_tools.py` uses `mock_agent_def.tools = ["read"]` (a list) and `agent.definition = None`. No test passes `tools=ALL_TOOLS` to the command handler. The "Allowed tools: ALL (no `tools:` filter)" line is never asserted. |
| 5 | `/agents` command display (`ui/commands/agents.py:43-44, 70-71`) | NO | `tests/test_commands/test_agents.py` uses `tools=["read","write"]` or `tools=()`. No test uses `tools=ALL_TOOLS`. Coverage report: `agents.py` at 55%, lines 44 and 70-71 uncovered. |

The three runtime/validator/loader guards are well-covered. The two UI display guards are not. This is a minor gap: the UI commands' sentinel branches are simple `isinstance` checks that append a human-readable string, with no behavioral consequence beyond the display. They are also low-risk because the sentinel flows from the same `AgentDefinition` that the runtime tests exercise end-to-end.

Recommendation (minor): add one test each in `tests/test_commands/test_tools.py` and `tests/test_commands/test_agents.py` that constructs an `AgentDefinition` with the default (sentinel) `tools` and asserts `"ALL (no `tools:` filter)"` appears in the command output. Two tests, ~6 lines each.

### 5. Round 0 minor recommendations — 1 of 4 addressed

| # | Round 0 recommendation | Round 1 status |
|---|------------------------|----------------|
| 1 | Regression-marker test for pre-existing file-namespace bug | NOT addressed. No test loads a file with `tools: [read]` and asserts the runtime `agent.tools` outcome. `tests/test_agent.py::test_agent_path_loads_definition` still stops at `definition.tools` and never asserts `core.tools` contents. `TestRuntimeFiltering::test_explicit_list_filters_at_runtime` still uses an in-memory definition with bare names (deliberately bypassing the file namespace, per its docstring). |
| 2 | End-to-end integration test for "explicit list from file" → runtime `agent.tools` | NOT addressed (same as #1 — coupled). |
| 3 | `tools: [""]` and duplicate tool names edge cases | NOT addressed. Loader's `if t` filter on `loader.py:128` and the runtime's set-based dedup are still untested for these inputs. |
| 4 | Explicit `yoker.agent(tools=None)` kwarg test | ADDRESSED. `test_tools_none_disables_all` (new in round 1) calls `yoker.agent(tools=None, config=Config())` and asserts `list(a.tools.names) == []`. |

One of four round-0 minors addressed; three deferred. All remain non-blocking. The file-namespace regression marker (recommendation #1) is still the highest-value deferred gap — it would protect both M.2 and the eventual fix.

### 6. Test quality — no regressions; behavior-focused

No test was weakened in the refactor. Spot-checks:

- `assert d.tools_unspecified is True/False` (round 0) → `assert d.tools is ALL_TOOLS` / `assert d.tools is not ALL_TOOLS` (round 1). These assert the public state of `AgentDefinition.tools`, not an internal side-channel. Strictly more meaningful: the field IS the contract now.
- Runtime tests still assert `agent.tools.get("yoker:read")` (user-facing consequence), not the internal branch choice.
- The one justified implementation-coupling test (`TestDocstringAgreement::test_loader_handles_present_vs_missing_keys`) still inspects `inspect.getsource(parse_agent_definition)` for `"tools" not in frontmatter` and `agent_tools_explicit_null_treated_as_empty`. This is criterion 11 (docstring/comment agreement) — the coupling IS the test. Updated to assert `"ALL_TOOLS"` is documented in the schema and filter docstrings. Justified.
- No `assert True`, no empty bodies, no `pass`-only stubs. All tests have meaningful assertions.
- No new over-mocking. The warning tests still patch `yoker.core.logger.warning`, which is the documented observability contract (`agent_tools_default_granted` is named in the acceptance criteria and the docstring).

No test now couples to implementation in a way it did not in round 0.

### 7. Coverage — 1891 passed (+2); 6 new sentinel lines uncovered

- Overall coverage: 81% (unchanged from round 0 — ceiling effect of the overall codebase).
- `src/yoker/agents/schema.py`: 86% (was 100% in round 0 under `tools_unspecified`). The 6 uncovered lines (34, 39, 42, 45, 49, 54) are the sentinel's special methods — see point 3.
- `src/yoker/agents/loader.py`: 79% — sentinel guard at line 145 is covered; uncovered lines are pre-existing error/edge branches unrelated to M.2.
- `src/yoker/agents/validator.py`: 100% — sentinel guard at line 104 fully covered.
- `src/yoker/core/__init__.py`: 83% — `_filter_tools_by_definition` three branches and `_warn_missing_tools` sentinel early-return covered.
- `src/yoker/api.py`: 91% — the `tools is not ALL_TOOLS` branch at line 142 is covered by the new `test_tools_none_disables_all` and `test_tools_all_tools_sentinel_keeps_all`.
- `src/yoker/ui/commands/tools.py`: 92% — sentinel display branch (lines 87-88) not asserted by any test.
- `src/yoker/ui/commands/agents.py`: 55% — sentinel display branches (lines 44, 70-71) not asserted.

The +2 new tests cover the two new api.py contract cases (`tools=None` → no tools, `tools=ALL_TOOLS` → all tools). The new sentinel code paths (6 lines in `schema.py`) are uncovered — see point 3 for the recommendation.

### 8. Pre-existing file-namespace bug — still no regression marker

Still out of scope for M.2, and still no regression-marker test. The bug: a file-loaded agent with `tools: [read]` gets `definition.tools = ("file:read",)` from the loader, but the runtime registry has `yoker:read`, so branch 3 of `_filter_tools_by_definition` removes it → the agent ends up with NO runtime tools despite the explicit list.

`tests/test_agent.py::test_agent_path_loads_definition` still stops at `definition.tools` (`assert "file:read" in core.definition.tools`) and never asserts `core.tools` contents. `TestRuntimeFiltering::test_explicit_list_filters_at_runtime` still uses an in-memory definition with bare names (deliberately bypassing the file namespace).

Recommendation (minor, non-blocking, carried from round 0): add one regression-marker test:

```python
def test_file_loaded_explicit_bare_tools_currently_resolves_to_no_tools():
  """Pre-existing bug regression marker: file-loaded agents with `tools: [read]`
  get NO runtime tools today because the loader namespaces to `file:read` while
  the registry has `yoker:read`. This test pins the current behaviour; when the
  bug is fixed, update the assertion to `yoker:read` present.
  """
  # load file with tools: [read], construct Agent, assert agent.tools.get("yoker:read") is None
```

This is the single most valuable deferred gap. It protects both M.2 and the eventual fix.

## Consolidated feedback

### Blockers
None.

### Major
None.

### Minor (recommended, non-blocking)
1. **Sentinel invariant tests** (point 3): add 3-4 tests for singleton identity, non-iterability, pickle round-trip, truthiness. Covers the 6 uncovered lines in `schema.py`. Cheap, locks the defensive contract.
2. **UI command sentinel display tests** (point 4): add one test each in `tests/test_commands/test_tools.py` and `tests/test_commands/test_agents.py` asserting `"ALL (no `tools:` filter)"` appears when `AgentDefinition` has the default sentinel. Covers lines 87-88 in `tools.py` and lines 44, 70-71 in `agents.py`.
3. **File-namespace regression marker** (point 8, carried from round 0): add one test pinning the current behaviour for file-loaded explicit bare tools. Highest-value deferred gap.
4. **Edge cases** (carried from round 0): `tools: [""]` (list with empty string) and duplicate tool names in an explicit list. Cheap wins, lock the filtering contract.

## Verdict

**approved** — the sentinel refactor is well-tested for contract behavior across all three layers (loader → schema → runtime/api). The 8-case loader matrix is complete with correct identity-based assertions. The api.py contract is fully covered (all 5 cases, including the two new tests that address round-0 recommendation #4). The three runtime/validator/loader guards are covered. The remaining gaps are minor and non-blocking: the sentinel's own special methods (defensive, never relied on by the runtime because `isinstance` guards run first), two UI display branches (cosmetic), and the three deferred round-0 minors (regression marker, edge cases). No test was weakened in the refactor; assertions moved from the `tools_unspecified` side-channel to the `tools` field itself, which is strictly more meaningful.