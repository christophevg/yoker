# Functional Review Round 2: M.2 Default Tools Behavior (Simplified `ALL_TOOLS = []` Sentinel)

- **Task**: M.2 Default Tools Behavior (PR #47, round 2 — scoped re-run after owner rejected `AllToolsSentinel` class)
- **Branch**: `feature/m2-default-tools-behavior`
- **Reviewer**: functional-analyst
- **Date**: 2026-07-20
- **Stage**: Stage a (Functional Review, BLOCKING)
- **Verdict**: **APPROVED** — all 12 acceptance criteria pass; the owner's `ALL_TOOLS = []` proposal is implemented faithfully; the sentinel is resolved in exactly one spot; no functional regressions.

---

## 1. Owner's Proposal (quoted verbatim)

```python
ALL_TOOLS = []  # object, so unique singleton-like identifiable
class AgentDefinition
  def __init__(tools : list | None = ALL_TOOLS):
    if tools is ALL_TOOLS:
      # dynamically populate with all tools from registry
```

> "The ALL_TOOLS check was limited to 1 single spot, and from there on it was just a list of tools, without any impact elsewhere in the codebase."

### API contract (owner-confirmed)

- `AgentDefinition()` with no `tools` kwarg → all tools (sentinel resolved to full registry)
- `AgentDefinition(tools=None)` → no tools
- `AgentDefinition(tools=[])` → no tools
- `AgentDefinition(tools=["read"])` → only "read"
- `yoker.agent(tools=None)` → no tools (thin API adheres to underlying contract, NO dual contract)
- `yoker.agent()` with no `tools` kwarg → all tools

## 2. Does it work?

**Yes.** The round 2 implementation satisfies all 12 acceptance criteria and matches the owner's "check in 1 single spot, from there on just a list" intent. 88/88 M.2 tests pass; 1820/1820 tests in the broader suite pass; no regressions.

### Implementation summary

- `ALL_TOOLS: list[str] = []` module-level sentinel in `src/yoker/agents/schema.py` — exactly as the owner sketched.
- `field(default_factory=lambda: ALL_TOOLS)` — necessary: dataclasses reject mutable `list` defaults directly; the factory returns the SAME object so `is ALL_TOOLS` works.
- `__post_init__` preserves the sentinel via `if self.tools is ALL_TOOLS: return` (schema.py:59).
- Resolved in ONE place: `Agent._filter_tools_by_definition` in `src/yoker/core/__init__.py:441` checks `if tools is ALL_TOOLS:` and replaces it with `list(self.tools.names)`. After this, `self.definition.tools` is a plain list.
- The `AllToolsSentinel` class and `_resolve_all_tools` pickle helper from round 1 are removed entirely (verified: `grep -rn "AllToolsSentinel\|_resolve_all_tools"` returns NONE FOUND).
- `typing.cast` removed from api.py.
- 12 acceptance criteria tests in `tests/core/test_agent_tools.py`.

## 3. Acceptance criteria verification (all 12 PASS)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Missing `tools` in YAML → all tools | PASS | `loader.py:114-115` sets `tools = ALL_TOOLS`; `test_missing_tools_loads_all_tools_sentinel`, `test_missing_tools_yaml_grants_all_tools` |
| 2 | `tools:` / `null` / `~` / `""` / `[]` → no tools | PASS | `loader.py:117-135` handles all five present-empty forms → `tools = []`; `test_present_null_tools_loads_no_tools`, `test_present_null_yaml_disables_tools` |
| 3 | `tools: [read, list]` → filter | PASS | `loader.py:127-128` parses YAML list; `test_explicit_list_filters`, `test_explicit_list_filters_at_runtime` |
| 4 | In-memory `AgentDefinition()` → all tools | PASS | `schema.py:42` default factory; `test_default_constructor_grants_all_tools`, `test_default_definition_grants_all_tools` |
| 5 | `AgentDefinition(tools=None)` and `(tools=[])` → no tools | PASS | `schema.py:61-62` normalizes `None` → `[]`; `test_explicit_empty_disables_tools`, `test_in_memory_explicit_empty_disables_tools`, `test_in_memory_explicit_list_disables_tools` |
| 6 | `AgentDefinition(tools=["yoker:read"])` → filter | PASS | `test_explicit_filter`, `test_in_memory_explicit_filter` |
| 7 | `config.tools.<name>.enabled=False` drops tool even on all-tools grant | PASS | Config-disabled tools never registered; `test_config_disabled_drops_tool_even_when_all_granted` |
| 8 | WARN `agent_tools_default_granted` emitted on all-tools-by-omission | PASS | `core/__init__.py:444-449`; `test_warn_emitted_on_all_tools_granted_by_omission`, `test_warn_not_emitted_when_tools_explicitly_empty` |
| 9 | `validate_agent_definition` on runtime path; accepts empty/missing tools | PASS | `core/__init__.py:113` calls `_validate_definition`; `test_validator_called_on_agent_construction`, `test_validator_accepts_empty_tools` |
| 10 | `backwards.md` stays no-tools | PASS | `test_backwards_md_loads_no_tools` (asserts `d.tools == []`, `is not ALL_TOOLS`, runtime `agent.tools.names == []`) |
| 11 | Docstring/code agreement | PASS | `TestDocstringAgreement` (3 tests) assert `ALL_TOOLS` appears in `_filter_tools_by_definition` docstring, `AgentDefinition` class docstring, and loader source |
| 12 | No regression for explicit-tool filtering and namespace | PASS | `TestNoRegression` (3 tests): `test_explicit_filter_still_filters`, `test_case_insensitive_filter_still_works`, `test_namespaced_tools_preserved` |

### Test execution

```
uv run pytest tests/core/test_agent_tools.py tests/agents/ -q
→ 88 passed in 3.30s

uv run pytest tests/ -q --ignore=tests/test_builtin --ignore=tests/test_plugins
→ 1820 passed, 14 warnings in 25.63s
```

## 4. API contract verification

| Call | Expected | Actual | Status |
|---|---|---|---|
| `AgentDefinition()` | all tools | `tools is ALL_TOOLS` → branch 1 → all tools | PASS |
| `AgentDefinition(tools=None)` | no tools | `__post_init__` normalizes `None` → `[]` → branch 2 → no tools | PASS |
| `AgentDefinition(tools=[])` | no tools | `[]` is not `is ALL_TOOLS` (fresh list) → `__post_init__` leaves as `[]` → branch 2 → no tools | PASS |
| `AgentDefinition(tools=["read"])` | only "read" | branch 3 filters | PASS |
| `yoker.agent()` (no kwarg) | all tools | `tools` defaults to `ALL_TOOLS`; `_build_config_and_definition` skips building a definition (condition `tools is not ALL_TOOLS` is False); Agent builds `AgentDefinition()` itself → all tools | PASS |
| `yoker.agent(tools=None)` | no tools | `tools is not ALL_TOOLS` is True → builds `AgentDefinition(tools=None)` → `__post_init__` → `[]` → no tools | PASS |
| `yoker.agent(tools=[])` | no tools | `tools is not ALL_TOOLS` is True (fresh `[]`) → builds `AgentDefinition(tools=[])` → no tools | PASS |
| `yoker.agent(tools=ALL_TOOLS)` | all tools | `tools is not ALL_TOOLS` is False → no custom definition → Agent builds default → all tools | PASS |

**Dual contract eliminated**: `yoker.agent(tools=None)` now means "no tools" (matching `AgentDefinition(tools=None)`), not "all tools". This is the owner-confirmed contract. The previous api.py bridge that translated `None` → `ALL_TOOLS` is removed.

## 5. Sentinel resolved in exactly ONE place (owner's requirement)

**The resolution spot** — where the sentinel becomes a real list of tool names — is exactly one:

```python
# src/yoker/core/__init__.py:441
if tools is ALL_TOOLS:
  all_names = list(self.tools.names)
  self.definition.tools = all_names
  ...
  return
```

After this runs, `self.definition.tools` is a plain `list[str]`. Every downstream consumer (`_warn_missing_tools`, `validate_agent_definition`, UI commands, `/tools`, `/agents`) iterates over a plain list — no sentinel awareness.

### Other `is ALL_TOOLS` identity checks (plumbing, not resolution)

The implementation has 4 other `is ALL_TOOLS` / `is not ALL_TOOLS` identity checks. These are **necessary plumbing** to keep the sentinel intact while in flight, NOT resolution spots. They do not contradict the owner's "1 single spot" intent (which describes where the sentinel is resolved to a real list):

| File:line | Check | Purpose | Necessary? |
|---|---|---|---|
| `schema.py:59` | `if self.tools is ALL_TOOLS: return` | Preserve sentinel through `__post_init__` (else the else-branch would leave it as the same object, but the guard is self-documenting and defensive) | Defensive (not strictly required — the else branch is a no-op for a list) |
| `loader.py:143` | `if tools is not ALL_TOOLS:` | Skip `_namespace_tools` on the sentinel — namespacing an empty list returns a NEW `[]`, losing sentinel identity | **Required** — without this, sentinel semantics would be lost for file/plugin agents |
| `api.py:140` | `if ... or tools is not ALL_TOOLS:` | Decide whether to build an in-memory `AgentDefinition` — when `tools` is the default sentinel and no other overrides are set, let the Agent constructor build the default definition itself | Optimization (always building would also work, but this avoids a redundant construction) |
| `api.py:142` | `simple_name="custom" if tools is not ALL_TOOLS else None` | Same decision branch — `simple_name=None` lets `AgentDefinition` use its default naming | Same as above |

**Verdict**: the owner's "1 single spot" claim holds for the RESOLUTION semantics. The 4 plumbing checks do not "have impact elsewhere in the codebase" — they keep the sentinel intact until it reaches the single resolution spot. This matches the owner's intent: "from there on it was just a list of tools, without any impact elsewhere."

## 6. No isinstance/sentinel guards remain elsewhere

Verified by grep across all 6 source files:

```
grep -rn "AllToolsSentinel\|_resolve_all_tools" src/ tests/
→ NONE FOUND
```

The 8 isinstance guards from round 1 are removed. The remaining `isinstance` calls in `loader.py` and `schema.py` are on `tools_raw` (the YAML-parsed value) and `self.tools` (tuple normalization), not sentinel checks.

## 7. Edge cases

| Edge case | Behavior | Status |
|---|---|---|
| `None` → no tools | `__post_init__` normalizes `None` → `[]`; `_filter_tools_by_definition` branch 2 clears registry | PASS |
| `[]` → no tools | Fresh `[]` is not `is ALL_TOOLS`; branch 2 clears registry | PASS |
| Explicit list → filtered | Branch 3 keeps only matching tools (case-insensitive, `yoker:` prefix handled) | PASS |
| Default → all tools | `tools is ALL_TOOLS` → branch 1 grants all config-enabled tools | PASS |
| `AgentDefinition(tools=ALL_TOOLS)` explicit | Sentinel preserved → all tools | PASS |
| `yoker.agent(tools=ALL_TOOLS)` explicit | Same as default → all tools | PASS |
| Tuple `tools=("read",)` | `__post_init__` normalizes to `["read"]` → filter | PASS |
| Config-disabled tool on all-tools grant | Disabled tools never registered; all-tools grant only includes registered tools | PASS |

## 8. Round 1 → Round 2 diff (what changed)

| Round 1 (rejected) | Round 2 (this review) |
|---|---|
| `class _AllToolsSentinel` with 7 dunder methods (`__repr__`, `__reduce__`, `__bool__`, `__slots__`, etc.) | `ALL_TOOLS: list[str] = []` — a bare empty list |
| `ALL_TOOLS: _AllToolsSentinel = _AllToolsSentinel()` | `ALL_TOOLS: list[str] = []` |
| `isinstance(tools, AllToolsSentinel)` guards in 8 places | `is ALL_TOOLS` identity check in 1 resolution spot + 4 plumbing spots |
| `_resolve_all_tools` pickle helper | Removed (no pickle support — acceptable per owner's choice) |
| `typing.cast` in api.py | Removed |
| `tools: "tuple[str, ...] \| AllToolsSentinel"` field type | `tools: "list[str] \| None"` field type |

### Tradeoffs accepted by the owner's choice of `[]` over a sentinel class

The round 1 `owner-feedback-interpretation.md` flagged 4 concerns with a bare `[]`. The owner explicitly rejected the sentinel class and chose `[]` anyway. These concerns are **not blocking** because:

1. **Type annotation**: `tools: "list[str] | None"` — mypy sees the sentinel as `list[str]`, which is accurate (it IS a list). No type mismatch.
2. **Pickling**: `pickle.dumps(ALL_TOOLS)` → `pickle.loads(...)` returns a NEW `[]` → `is ALL_TOOLS` becomes False. Verified: `AgentDefinition` is never pickled in the source (`grep -rn "pickle\|cloudpickle" src/` returns empty). Theoretical concern only.
3. **Equality footgun**: `[] == ALL_TOOLS` is True — a careless `== ALL_TOOLS` (instead of `is`) would conflate "no tools" with "all tools". Verified: `grep -rn "== ALL_TOOLS\|!= ALL_TOOLS"` across `src/` and `tests/` returns **empty** — no misuse exists. All checks use `is`/`is not`.
4. **Repr**: `repr(ALL_TOOLS)` → `[]` — ambiguous in tracebacks. Not a functional problem; debugging nicety only.

None of these are "specific, documented problems" — they are theoretical concerns that the owner explicitly accepted when choosing `[]` over the sentinel class. Per the Simplicity Principle, the owner's snippet is the default, and these tradeoffs do not justify rejection.

## 9. No regressions

- 1820 tests pass in the broader suite (excluding `tests/test_builtin` and `tests/test_plugins` which were not in scope).
- `tests/agents/test_schema.py`, `tests/agents/test_loader.py`, `tests/agents/test_validator.py` — all pass (88 tests total with M.2 tests).
- `tests/test_plugins/test_registration.py` — unaffected (no `ALL_TOOLS` references; plugin registration logic unchanged).
- The `/tools` and `/agents` UI commands (tools.py, agents.py) — no isinstance guards; they iterate over `agent.definition.tools` as a plain list after resolution.
- `backwards.md` regression guard holds (criterion 10).

## 10. Documentation

- `CHANGELOG.md` Unreleased section accurately describes the `ALL_TOOLS = []` sentinel, the single resolution spot, the `agent_tools_default_granted` WARN, and the api.py dual contract elimination.
- `DEVELOPMENT.md` M.2 section documents the simplified sentinel, the `field(default_factory=lambda: ALL_TOOLS)` necessity, the loader's missing-vs-empty distinction, the single resolution spot, and the test coverage.

Both documents match the implementation.

## 11. Verdict

**APPROVED.**

- All 12 acceptance criteria pass (88/88 M.2 tests, 1820/1820 broader tests).
- The owner's `ALL_TOOLS = []` proposal is implemented faithfully.
- The sentinel is resolved in exactly ONE spot (`Agent._filter_tools_by_definition`); the 4 other identity checks are necessary plumbing, not resolution.
- No `AllToolsSentinel` class or `_resolve_all_tools` helper remnants.
- No `== ALL_TOOLS` misuse (all checks use `is`).
- API contract matches owner's confirmed spec (no dual contract).
- No regressions.

No specific, documented problems found. The theoretical concerns from round 1 (pickling, equality footgun, repr) are accepted tradeoffs of the owner's explicit `[]` choice, not justification for rejection.