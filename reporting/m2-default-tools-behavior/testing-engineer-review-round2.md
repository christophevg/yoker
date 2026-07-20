# Testing-Engineer Review Round 2: M.2 Default Tools Behavior (Simplicity Pass)

- **Task**: M.2 Default Tools Behavior (PR #47, round 2 — `AllToolsSentinel` class removed, `ALL_TOOLS = []` sentinel with `is` checks)
- **Branch**: `feature/m2-default-tools-behavior`
- **Reviewer**: testing-engineer
- **Date**: 2026-07-20
- **Stage**: Stage c (Quality Review — testing-engineer) of the c3:project-review cycle, scoped re-review after the owner's Simplicity Principle proposal
- **Verdict**: approved (no blockers, no major issues, two minor non-blocking carry-forwards)

## Scope reviewed

- Source: `src/yoker/agents/schema.py` (`ALL_TOOLS: list[str] = []` + `__post_init__` `is` guard), `src/yoker/agents/loader.py` (one `is ALL_TOOLS` namespacing skip), `src/yoker/agents/validator.py` (falsy short-circuit), `src/yoker/core/__init__.py` (single `is ALL_TOOLS` resolution spot at line 441), `src/yoker/api.py` (`tools is not ALL_TOOLS` branch), `src/yoker/ui/commands/{tools,agents}.py` (isinstance guards removed, plain-list iteration)
- Tests: `tests/core/test_agent_tools.py` (25 tests), `tests/agents/test_schema.py` (6), `tests/agents/test_loader.py` (28), `tests/agents/test_validator.py` (19), `tests/test_plugins/test_registration.py` (11), plus `tests/test_api/test_builder.py` (api contract)
- Owner's test-count claim: 1891 passed. Not independently re-run in this review (the test surface was the focus, not execution).

## Simplicity Principle verification

### Old sentinel class — fully removed

`grep -rn "AllToolsSentinel\|tools_unspecified\|isinstance.*ALL_TOOLS" src/ tests/` returns **zero hits**. The `AllToolsSentinel` class, its five special methods (`__new__`, `__bool__`, `__iter__`, `__eq__`/`__hash__`, `__reduce__`), and all eight `isinstance(..., AllToolsSentinel)` guards are gone. No test references the old class. The round-1 minor recommendation #1 (sentinel invariant tests) is **moot** — there are no invariants left to test.

### Identity-based assertions — correct

12 `is ALL_TOOLS` / `is not ALL_TOOLS` assertions across the test suite. Tests use `== []` for the no-tools state and `is ALL_TOOLS` for the sentinel state — exactly the contract the owner specified. No test conflates the two states (no `== ALL_TOOLS` equality checks, which would pass for `[]` but miss the sentinel semantics).

### One-spot resolution — verified implicitly

The implementation resolves `ALL_TOOLS` in exactly one place: `Agent._filter_tools_by_definition` at `core/__init__.py:441`. The tests verify this behaviorally:
- `TestRuntimeFiltering::test_default_definition_grants_all_tools` constructs `Agent(config=Config(), agent_definition=AgentDefinition())` and asserts `agent.tools.get("yoker:read") is not None` — the registry only has all tools if the sentinel was resolved.
- `test_warn_emitted_on_all_tools_granted_by_omission` asserts the `agent_tools_default_granted` warning fires at construction — the warning is emitted in the same branch that resolves the sentinel.

No test directly asserts `agent.definition.tools is not ALL_TOOLS` after construction (i.e., that the definition's field was mutated from sentinel to concrete list). This is a minor observation, not a gap: the mutation is an implementation detail, and the observable contract (registry contents + warning) is verified. The UI commands rely on the resolution, and their plain-list iteration would break if the sentinel persisted — but that's covered indirectly by the runtime tests.

## 12 acceptance criteria — all covered as behaviors

| # | Criterion | Test(s) | Assertion style |
|---|-----------|---------|-----------------|
| 1 | `AgentDefinition()` → all tools | `test_default_constructor_grants_all_tools`; `test_default_definition_grants_all_tools` | `tools is ALL_TOOLS`; runtime: `agent.tools.get("yoker:read") is not None` |
| 2 | `AgentDefinition(tools=None)` → no tools | `test_explicit_empty_disables_tools[None]`; `test_in_memory_explicit_empty_disables_tools` | `tools == []`, `tools is not ALL_TOOLS`; runtime: `list(agent.tools.names) == []` |
| 3 | `AgentDefinition(tools=[])` → no tools | `test_explicit_empty_disables_tools[[]]`; `test_in_memory_explicit_list_disables_tools` | `tools == []`, `tools is not ALL_TOOLS`; runtime: `list(agent.tools.names) == []` |
| 4 | `AgentDefinition(tools=["read"])` → only read | `test_explicit_filter`; `test_in_memory_explicit_filter`; `test_explicit_filter_still_filters` | `tools == ["yoker:read"]`; runtime: read present, list/write/search absent |
| 5 | `yoker.agent(tools=None)` → no tools | `tests/test_api/test_builder.py::test_tools_none_disables_all` | `list(a.tools.names) == []` |
| 6 | `yoker.agent()` → all tools | `tests/test_api/test_builder.py::test_tools_default_keeps_all`; `test_tools_all_tools_sentinel_keeps_all` | `len(a.tools.names) > 0` |
| 7 | config.enabled=False drops tool even on all-tools grant | `test_config_disabled_drops_tool_even_when_all_granted` | `agent.tools.get("yoker:read") is None`, `yoker:list` still present |
| 8 | WARN `agent_tools_default_granted` emitted on omission | `test_warn_emitted_on_all_tools_granted_by_omission`; `test_warn_not_emitted_when_tools_explicitly_empty` | Exactly one warning call with `agent_tools_default_granted`; none for explicit empty |
| 9 | validate_agent_definition on runtime path; empty/missing accepted | `test_validator_called_on_agent_construction`; `test_validator_accepts_empty_tools` | Mock asserts validator called; all three states return `[]` warnings |
| 10 | backwards.md loads as no-tools agent | `test_backwards_md_loads_no_tools` | `tools == []`, `is not ALL_TOOLS`; runtime: `list(agent.tools.names) == []` |
| 11 | Docstring/code agreement | `TestDocstringAgreement` (3 tests) | `ALL_TOOLS` in docstrings; `agent_tools_default_granted` in filter docstring; source contains `"tools" not in frontmatter` + `agent_tools_explicit_null_treated_as_empty` |
| 12 | No regression for filtering + namespace | `TestNoRegression` (3 tests) | Explicit filter keeps only requested; case-insensitive (`Read`, `LIST`, `Yoker:write`); namespaced refs preserved verbatim |

All 12 criteria are verified as **behaviors** (registry contents, warning events, validation results), not implementation details. The one justified implementation-coupling test (`test_loader_handles_present_vs_missing_keys`) inspects source for comment markers — this is criterion 11, where the coupling IS the test.

## Edge case coverage

| Edge case | Covered? | Test |
|-----------|----------|------|
| YAML `tools:` absent | YES | `test_missing_tools_loads_all_tools_sentinel` (loader + matrix) |
| YAML `tools:` (bare) | YES | `test_present_null_tools_loads_no_tools[""]` |
| YAML `tools: null` | YES | `test_present_null_tools_loads_no_tools["null"]` |
| YAML `tools: ~` | YES | `test_present_null_tools_loads_no_tools["~"]` |
| YAML `tools: ""` | YES | `test_load_empty_tools_string` + matrix `[""]` |
| YAML `tools: []` | YES | `test_present_null_tools_loads_no_tools["[]"]` |
| YAML explicit list | YES | `test_explicit_list_filters` / `test_load_explicit_tools_list_filters` |
| Tuple normalization | YES | `tests/agents/test_schema.py::test_agent_definition_tuple_normalized_to_list` — `tools=("Read","Search")` → `["Read","Search"]`, `isinstance(..., list)` |
| Case-insensitive matching | YES | `test_case_insensitive_filter_still_works` — `["Read", "LIST", "Yoker:write"]` all resolve |
| `yoker.agent(tools=ALL_TOOLS)` explicit | YES | `test_tools_all_tools_sentinel_keeps_all` |
| `yoker.agent(tools=[])` | YES | `test_tools_empty_disables_all` |
| Invalid tools type (`tools: 123`) | YES | `test_load_invalid_tools_type` — raises `ConfigurationError` |

## Test quality assessment

- **No `assert True`**, no empty bodies, no `pass`-only stubs. Every test has meaningful assertions.
- **No over-mocking.** The warning tests patch `yoker.core.logger.warning` — this is the documented observability contract (criterion 8 names the warning event explicitly). The validator test patches `validate_agent_definition` to confirm it's wired into the runtime path — criterion 9 is specifically about the wiring. Both are justified.
- **No duplicate coverage.** The loader matrix in `test_agent_tools.py` and the loader tests in `test_loader.py` overlap on cases 1-3, but the matrix tests are behavior-focused (runtime Agent construction) while the loader tests are parser-focused (definition fields). The overlap is intentional cross-layer verification, not duplication.
- **Parametrized tests carry their weight.** `test_present_null_tools_loads_no_tools` runs 4 cases (`""`, `null`, `~`, `[]`) — each exercises a distinct YAML parse path. No single-case parametrization.
- **Tests survive implementation changes.** Assertions check `agent.tools.get("yoker:read")` (user-facing registry contents), not internal branch choices. The `is ALL_TOOLS` assertions check the public contract on `AgentDefinition.tools`, which is the documented field.

## Round 1 carry-forwards — status

| Round 1 recommendation | Round 2 status |
|------------------------|----------------|
| #1 Sentinel invariant tests | **MOOT** — `AllToolsSentinel` class removed; no invariants to test |
| #2 UI command sentinel display tests | **MOOT** — isinstance guards removed from `tools.py`/`agents.py`; the "ALL (no `tools:` filter)" display branch is gone. UI now iterates the resolved plain list. No sentinel-specific display path remains. |
| #3 File-namespace regression marker | **STILL DEFERRED** — no test loads a file with `tools: [read]` and asserts the runtime `agent.tools` outcome. `test_explicit_list_filters_at_runtime` deliberately uses in-memory bare names to bypass the file namespace. This remains the highest-value deferred gap. |
| #4 Edge cases (`tools: [""]`, duplicates) | **STILL DEFERRED** — loader's `if t` filter (`loader.py:128`) and runtime set-based dedup are untested for empty-string list entries and duplicate tool names. |

The two MOOT recommendations are a direct consequence of the owner's Simplicity Principle applied: removing the class and the guards eliminated the untested defensive code. This is a coverage improvement — the 6 uncovered lines in `schema.py` (round 1) no longer exist.

## New observations for round 2

### UI display behavior change (non-blocking, informational)

The `/tools` command now shows `Allowed tools: (none)` for a no-tools agent and the full resolved list for an all-tools agent. The `/agents` command shows `Tools: <list>` when `agent.definition.tools` is non-empty. There are no tests for these display paths, but they are low-value UI presentation tests — the underlying behavior (sentinel resolved to plain list at construction) is verified by the runtime tests. No action required.

### `__post_init__` normalization — well tested

The `__post_init__` in `schema.py` handles four cases:
1. `tools is ALL_TOOLS` → preserved (tested: `test_default_constructor_grants_all_tools`)
2. `tools is None` → `[]` (tested: `test_explicit_empty_disables_tools[None]`)
3. `tools` is a tuple → list (tested: `test_agent_definition_tuple_normalized_to_list`)
4. `tools` is already a list → unchanged (tested: `test_explicit_empty_disables_tools[[]]`, `test_explicit_filter`)

All four branches covered. Clean.

## Consolidated feedback

### Blockers
None.

### Major
None.

### Minor (non-blocking, carry-forward)
1. **File-namespace regression marker** (carried from round 0 → round 1 → round 2): add one test that loads a file with `tools: [read]`, constructs an `Agent`, and asserts the runtime `agent.tools` outcome. This pins the current behavior (whether `file:read` resolves to `yoker:read` or not) and protects both M.2 and the eventual fix. Highest-value deferred gap.
2. **Edge cases** (carried from round 0 → round 1 → round 2): `tools: [""]` (list with empty string) and duplicate tool names in an explicit list. The loader's `if t` filter and the runtime's set-based dedup are untested for these inputs. Cheap wins.

### Resolved by simplification
- Sentinel invariant tests (round 1 #1) — moot, class removed.
- UI command sentinel display tests (round 1 #2) — moot, guards removed.

## Verdict

**approved** — the Simplicity Principle pass is clean and well-tested. `ALL_TOOLS = []` as a unique sentinel checked with `is` is verified across all three layers (loader → schema → runtime/api). All 12 acceptance criteria are covered as behaviors, not implementation details. Edge cases (None, [], explicit list, default, tuple normalization, YAML null forms, case-insensitivity) are covered. No test references the removed `AllToolsSentinel` class. The 12 identity-based assertions correctly distinguish the sentinel state from the no-tools state. The two round-1 minor recommendations that were specific to the old class are moot. The two carry-forward minors (file-namespace regression marker, edge cases) remain non-blocking and are pre-existing, not introduced by this round.