# Testing-Engineer Review: M.2 Default Tools Behavior (Option C)

- **Task**: M.2 Default Tools Behavior (initial implementation, round 0)
- **Branch**: `feature/m2-default-tools-behavior` (PR #47 draft)
- **Reviewer**: testing-engineer
- **Date**: 2026-07-20
- **Stage**: Stage c (Quality Review — testing-engineer) of the c3:project-review cycle
- **Verdict**: approved (with minor recommendations — no blockers)

## Scope reviewed

- `tests/core/test_agent_tools.py` (new, 32 tests, 4 test classes)
- `tests/agents/test_loader.py` (8-case matrix for `tools:` forms)
- `tests/agents/test_validator.py` (empty/missing accepted; runtime wiring)
- `tests/test_agent.py` (updated for Option C — `TestAgentToolMatching::test_empty_tools_list` now parameterises `None` and `[]`)
- `tests/test_api/test_builder.py::TestAgentBuilderTools` (3 tests: whitelist, empty, None)
- Source under test: `src/yoker/agents/{loader,schema,validator}.py`, `src/yoker/core/__init__.py`, `src/yoker/api.py`

Re-ran the M.2 suite: 32/32 pass. Combined M.2 surface (`tests/core/test_agent_tools.py` + `tests/agents/` + `tests/test_api/test_builder.py` + `tests/test_agent.py`): 149/149 pass.

## Coverage of the 7 review prompt points

### 1. Coverage gaps — Option C behaviours with no test

| Behaviour | Covered? | Evidence |
|---|---|---|
| WARN `agent_tools_default_granted` fires (not just "all tools present") | YES | `TestRuntimeFiltering::test_warn_emitted_on_all_tools_granted_by_omission` asserts exactly one matching `logger.warning` call with `args[0] == "agent_tools_default_granted"`. `::test_warn_not_emitted_when_tools_explicitly_empty` confirms it does NOT fire on `tools=None`. |
| `config.tools.<name>.enabled = False` interaction with all-tools-by-omission (criterion 7) | YES | `TestRuntimeFiltering::test_config_disabled_drops_tool_even_when_all_granted` sets `config.tools.read.enabled = False`, asserts `yoker:read` absent, `yoker:list` present. |
| `yoker.agent(tools=None)` → all-tools vs `yoker.agent(tools=[])` → no-tools (api.py contract) | PARTIAL | `TestAgentBuilderTools::test_tools_empty_disables_all` covers `tools=[]`. `::test_tools_none_keeps_all` calls `yoker.agent()` with the default (which IS `tools=None`), not an explicit `tools=None` kwarg. Same code path, so behaviour is verified, but the explicit-kwarg form is not distinguished. Minor. |
| `backwards.md` regression guard (criterion 10) end-to-end | YES | `TestBackwardsRegression::test_backwards_md_loads_no_tools` loads the file from `examples/plugins/demo/yoker_plugin_demo/agents/backwards.md`, asserts `tools == ()`, `tools_unspecified is False`, AND constructs an `Agent` to assert `agent.tools.names == []`. True end-to-end. |
| Namespace handling regression (criterion 12) | YES | `TestNoRegression::test_namespaced_tools_preserved` (in-memory `yoker:read` preserved verbatim) and `::test_case_insensitive_filter_still_works` (mixed `Read`, `LIST`, `Yoker:write` resolves to `yoker:` names). Loader-side namespacing covered by `tests/agents/test_loader.py::test_load_explicit_tools_list_filters` (`file:read`, `file:list`). |

No blocker-level gaps against the 12 acceptance criteria.

### 2. Test meaningfulness

Tests assert **behaviour**, not implementation:

- Runtime tests assert `agent.tools.get("yoker:read")` (the user-facing consequence), not the internal `_filter_tools_by_definition` branch choice.
- Warning tests use `patch("yoker.core.logger.warning")` and inspect `call_args_list` — this couples to the logger surface (structlog event name), which is the documented observability contract (`agent_tools_default_granted` is named in the docstring and the acceptance criteria). Acceptable.
- One justified implementation-coupling case: `TestDocstringAgreement::test_loader_handles_present_vs_missing_keys` inspects `inspect.getsource(parse_agent_definition)` for the strings `"tools" not in frontmatter` and `agent_tools_explicit_null_treated_as_empty`. This is a deliberate docstring/comment-agreement test (criterion 11) — the coupling IS the test. Justified; flagged here for transparency.

No tests found that assert only internal data structures or framework plumbing.

### 3. Edge cases — what's missing

| Edge case | Status | Notes |
|---|---|---|
| `tools: [""]` (list with empty string) | NOT TESTED | Loader filters empty strings via `if t` on `loader.py:131`, producing `()` + `tools_unspecified=False`. Cheap to add; would lock the filtering contract. |
| `tools: false` / `tools: 0` (wrong scalar types) | NOT TESTED | Only `tools: 123` is covered by `tests/agents/test_loader.py::test_load_invalid_tools_type`. `false` (bool) and `0` (int) hit the same `else` branch but are not asserted. Low value. |
| `tools:` followed by comment / `tools: # comment` | NOT TESTED | YAML parses to `None` → `tools_unspecified=False`. Low value. |
| Very large tool lists | NOT TESTED | Low value; no size-dependent logic. |
| Duplicate tool names in explicit list (e.g. `tools: [read, read]`) | NOT TESTED | Runtime filter uses a set, dedups silently. Cheap to add a test asserting no error and one entry kept. Low value. |
| Namespaced vs bare mixed in explicit list | PARTIAL | `test_case_insensitive_filter_still_works` mixes `Read`, `LIST`, `Yoker:write` — close enough. |

None of these are blockers; the documented plan only required `""`/`null`/`~`/`[]`, all of which are covered.

### 4. Integration flows

The suite is mostly unit-level, with ONE genuine end-to-end test: `TestBackwardsRegression::test_backwards_md_loads_no_tools` (file → loader → Agent → runtime tool set). This covers the "no-tools" end-to-end path.

There is NO end-to-end test for the "explicit list from file" path that asserts which tools are present at runtime. `TestAgentAgentPath::test_agent_path_loads_definition` (`tests/test_agent.py:316`) loads a file with `tools: [read, list]` and builds an `Agent`, but only asserts `"file:read" in core.definition.tools` — it does NOT assert what `core.tools` (the runtime registry) contains. See point 5 for why this matters.

Recommendation (minor): add one integration test that loads a file with `tools: [read]` and asserts the runtime `agent.tools` contents. This would also force a resolution of the pre-existing bug in point 5 (or pin it as a documented regression-marker).

### 5. Pre-existing bug: file-loaded agents with explicit bare tool names get NO tools

**NOT COVERED by any test.** The functional review documents this clearly (file-namespace mismatch: loader produces `file:read`, runtime registry has `yoker:read`, branch 3 filter removes it). No test asserts the current runtime outcome for this case.

`tests/test_agent.py::test_agent_path_loads_definition` stops at `definition.tools` — it never reaches `core.tools`. `tests/core/test_agent_tools.py::TestRuntimeFiltering::test_explicit_list_filters_at_runtime` uses an in-memory definition with bare names (deliberately bypassing the file namespace, as the test docstring explains), so it does not exercise the bug.

Recommendation (minor, non-blocking for M.2): add a regression-marker test that asserts the **current** behaviour so a future fix is detectable:

```python
def test_file_loaded_explicit_bare_tools_currently_resolves_to_no_tools():
  """Pre-existing bug regression marker: file-loaded agents with `tools: [read]`
  get NO runtime tools today because the loader namespaces to `file:read` while
  the registry has `yoker:read`. This test pins the current behaviour; when the
  bug is fixed, update the assertion to `yoker:read` present.
  """
  # ... load file with tools: [read], construct Agent, assert agent.tools.get("yoker:read") is None
```

This is the single most valuable gap to fill. It is not a blocker for M.2 because the bug is pre-existing and out of scope, but pinning it would prevent silent regression and make a future fix detectable.

### 6. Test infrastructure

- `tests/core/__init__.py` is an empty package marker, consistent with `tests/agents/__init__.py`, `tests/backends/__init__.py`, `tests/tools/__init__.py`, etc. No duplication; follows the existing project pattern.
- No conftest is needed in `tests/core/` — the root `tests/conftest.py` handles environment setup; per-test isolation is achieved via `tmp_path` and fresh `Config()` / `Agent()` construction per test.
- No shared mutable state observed. `patch("yoker.core.logger.warning")` is scoped per-test via the `with` block.
- One subtle isolation note: `test_warn_emitted_on_all_tools_granted_by_omission` patches `yoker.core.logger.warning`, which is the structlog logger bound at import time in `yoker/core/__init__.py`. This is correct — the same logger reference is used by `_filter_tools_by_definition`. No isolation risk.
- No global mutation (`os.environ`, clevis parser state, etc.) in the new tests. The clevis-global-state caveat from MBI-004 does not apply here.

### 7. Coverage 81% unchanged — did the +32 tests actually cover the new code?

Yes. The unchanged 81% is a ceiling effect of the overall codebase; the new code paths are small and fully exercised:

| New code path | Covering tests |
|---|---|
| `agents/loader.py:114-140` (missing vs present-null vs str vs list vs else) | `TestLoaderMatrix::*`, `tests/agents/test_loader.py::test_load_present_null_tools_loads_no_tools_flag[*]`, `::test_load_empty_tools_string`, `::test_load_invalid_tools_type`, `::test_load_explicit_tools_list_filters` |
| `agents/schema.py:54-73` (`__post_init__` branch logic) | `TestInMemoryAgentDefinition::*` |
| `agents/validator.py:99-102` (removed guard + `validate_tools` warn-not-raise) | `TestValidatorOnRuntimePath::test_validator_accepts_empty_tools`, `tests/agents/test_validator.py::TestValidateTools::test_validate_unknown_tool`, `::test_validate_namespaced_tool_skipped` |
| `core/__init__.py:400-471` (`_validate_definition` + three-branch `_filter_tools_by_definition`) | `TestRuntimeFiltering::*` (all branches), `TestValidatorOnRuntimePath::test_validator_called_on_agent_construction` |
| `api.py:142-144` (`tools_unspecified=tools is None`) | `tests/test_api/test_builder.py::TestAgentBuilderTools::*` |

The new tests are not "testing existing behaviour" — they exercise branches that did not exist on master (the `tools_unspecified` flag, the three-branch filter, the runtime validator wiring, the loader's missing-vs-present distinction). The +32 tests are well-targeted.

## Consolidated feedback

### Blockers
None.

### Major
None.

### Minor (recommended, non-blocking)
1. Add a regression-marker test for the pre-existing file-namespace bug (point 5). This is the highest-value minor gap; it protects both M.2 and the eventual fix.
2. Add an end-to-end integration test for the "explicit list from file" path that asserts runtime `agent.tools` contents (point 4). Couples to point 1 — if done together, one test resolves both.
3. Optionally cover `tools: [""]` (list with empty string) and duplicate tool names in an explicit list — cheap wins, lock the filtering contract.
4. Optionally add an explicit `yoker.agent(tools=None)` test (distinct from the default) — same code path, but makes the contract visible.

## Verdict

**approved** — the test suite covers all 12 acceptance criteria with behaviour-level assertions, the new code paths are fully exercised, and the 32 new tests are meaningful (no `assert True`, no implementation-only coupling beyond the one justified docstring-agreement test). The remaining gaps are minor, non-blocking, and mostly about pinning pre-existing behaviour and edge cases outside the M.2 plan.