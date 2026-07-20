# API Architecture Review: M.2 Default Tools Behavior — Implementation

**Date**: 2026-07-20
**Reviewer**: API Architect Agent
**Stage**: c (Domain Review — api-architect) of c3:project-review cycle
**Task**: M.2 Default Tools Behavior, round 0 implementation on `feature/m2-default-tools-behavior` (PR #47 draft)
**Prior review**: `analysis/m2-default-tools-behavior-api.md` (plan review, Option C endorsed)
**Implementation report**: developer's summary in task brief

## Summary

The implementation is **architecturally sound and approved with recommendations**. Option C is correctly realised: missing `tools` → all tools; explicit empty (`null`/`~`/`""`/`[]`/`None`/`[]`) → no tools; non-empty → filter. The three-branch `_filter_tools_by_definition` is clean, the `simple_name`/`namespace` proxy is removed as planned, and the validator is correctly wired onto the runtime path as warnings-only. Tests (32 new + extended matrix) and `make check` (1889 passed, ruff/mypy clean) confirm coverage.

The one substantive finding is the **api.py dual contract**, which is a direct consequence of the implementation deviating from the plan's recommended `tools: tuple[str, ...] | None = None` sentinel approach in favour of a `tools_unspecified: bool` side-channel flag. The side-channel works correctly and is pragmatic, but it introduced a seam where `yoker.agent(tools=None)` (→ all tools) and `AgentDefinition(tools=None)` (→ no tools) have **opposite semantics for the same kwarg name**. The plan's sentinel approach would have kept both layers consistent. This is a documentation-or-refactor item, not a correctness bug — the implementation behaves correctly in both layers; it is just confusing for users who move between them.

Secondary findings: the YAML-null warning is emitted for only 3 of the 5 present-empty forms (matches the plan, but the developer's "all five handled identically" claim is slightly misleading re: the warning); the `logger.warning` level for `agent_tools_default_granted` is a reasonable deviation from the plan's `logger.info` (better discoverability, at the cost of noisier default-constructed agents); a pre-existing bug where file-loaded agents with bare built-in tool names get NO tools at runtime is NOT worsened by M.2 but becomes more impactful (users who "tighten" an all-tools file agent by adding `tools: [read]` will silently break it) — recommend a follow-up task.

## Findings

### 1. Schema design — `tools_unspecified: bool = True` side-channel

**Sound, with one deviation-from-plan noted.**

The `__post_init__` normalization (`schema.py:54-73`) correctly handles every input form:

| Input | `tools` after | `tools_unspecified` after | Correct? |
|-------|--------------|---------------------------|----------|
| `AgentDefinition()` (default) | `()` | `True` | Yes — all tools |
| `AgentDefinition(tools=None)` | `()` | `False` | Yes — no tools (Option C contract) |
| `AgentDefinition(tools=[])` | `()` | `False` | Yes — no tools |
| `AgentDefinition(tools=("read",))` | `("read",)` | `False` | Yes — filter |
| `AgentDefinition(tools=["read"])` | `("read",)` | `False` | Yes — filter |

The flag is authoritative after `__post_init__`: a caller passing `tools=()` with `tools_unspecified=False` explicitly gets no-tools; passing `tools=()` with `tools_unspecified=True` gets all-tools. No drift.

**Frozen-dataclass concern**: none in practice. `AgentDefinition` is declared `@dataclass` (no `frozen=True`); the `__post_init__` mutations are legal. The module docstring (`schema.py:1`) claims "Provides frozen dataclasses" — this is a **pre-existing docstring inaccuracy**, not introduced by M.2, but M.2 adds mutable state (`tools_unspecified`) that would be wrong if the class were actually frozen. Recommend correcting the docstring in a follow-up.

**Deviation from plan**: the plan (C.3, line 226-229) recommended `tools: tuple[str, ...] | None = None` with `None` as the all-tools sentinel. The implementation chose `tools: tuple[str, ...] = ()` + `tools_unspecified: bool = True` side-channel. Trade-off:

| Aspect | Plan (`None` sentinel) | Impl (side-channel flag) |
|--------|------------------------|--------------------------|
| Downstream iteration of `definition.tools` | Needs `is None` guards (or normalize early) | None-safe — `tools` is always a tuple |
| Field count | 1 (single source of truth) | 2 (flag must stay in sync with intent) |
| api.py ↔ AgentDefinition contract consistency | **Consistent** (see §4) | **Inconsistent** (see §4) |
| Footgun risk | `tools=None` vs `tools=()` is native Python | Flag can be passed incorrectly by direct constructors |

The side-channel is pragmatic (avoids None-guards in `_warn_missing_tools`, `validate_tools`, `_filter_tools_by_definition`), but it is the root cause of the api.py dual contract (§4). Both approaches are valid; the plan's approach would have been cleaner at the contract seam.

### 2. Loader branch logic

**Correct. Minor: warning coverage is narrower than the developer's report implies.**

`loader.py:114` uses `"tools" not in frontmatter` — the correct way to distinguish key-absent from key-present-but-null. All five present-empty forms produce `tools=()` + `tools_unspecified=False` (behavior identical). However, the `agent_tools_explicit_null_treated_as_empty` warning is emitted **only for the YAML-null forms** (`tools:` / `null` / `~`, i.e. `tools_raw is None`), NOT for `tools: ""` or `tools: []`:

| YAML form | `tools_raw` | `tools` | `tools_unspecified` | Warning? |
|-----------|-------------|---------|---------------------|----------|
| `tools:` (bare) | `None` | `()` | `False` | Yes |
| `tools: null` | `None` | `()` | `False` | Yes |
| `tools: ~` | `None` | `()` | `False` | Yes |
| `tools: ""` | `""` | `()` | `False` | **No** (hits `isinstance(str)` branch at line 127) |
| `tools: []` | `[]` | `()` | `False` | **No** (hits `isinstance(list)` branch at line 130) |

This matches the plan (C.3 only specified the warning for `tools_raw is None`). It is defensible — `""` and `[]` are the "intentional empty" forms, less footgun-y than a bare `tools:`. But the developer's report claim "all five present-null/empty forms handled identically" is misleading at the warning level. Recommend tightening the report wording or (better) emitting the warning for `""` and `[]` too, since the warning's purpose is discoverability of the empty-means-no-tools semantic and all five forms share that semantic.

Warning level: `logger.warning` is appropriate — this is a footgun the author should see.

### 3. `_filter_tools_by_definition` three-branch logic

**Clean. Proxy removal safe. WARN level is a reasonable deviation from plan.**

The three branches (`core/__init__.py:431-449`) are correct and well-documented:

- Branch 1 (`tools_unspecified=True`): keep all, emit `agent_tools_default_granted`. Correct.
- Branch 2 (`len(tools)==0` with `tools_unspecified=False`): clear registry. Correct.
- Branch 3 (non-empty): filter with `yoker:` prefix handling for bare names. Unchanged from pre-M.2; correct.

The `simple_name is None and namespace is None` proxy check is removed entirely — `tools_unspecified` carries the intent natively. Safe.

**Deviation from plan (acceptable)**: plan recommended `logger.info` for the all-tools branch; implementation uses `logger.warning`. This is better for discoverability (the plan's stated goal was "authors see it in default logs"), at the cost of being noisy for the common `yoker.agent()` call with no `tools` kwarg. Every default-constructed agent will emit a WARN. If this becomes noisy in production, consider downgrading to `logger.info` for the in-memory default case and keeping WARN only for file/plugin agents with missing `tools:`. Not a blocker.

### 4. api.py deviation — dual contract

**The most significant finding. Acceptable with documentation; the plan's approach would have avoided it.**

The implementation passes `tools_unspecified=tools is None` when constructing `AgentDefinition` (`api.py:143`). This produces a **dual contract on the `tools` kwarg name**:

| Call site | `tools=None` means | `tools=[]` means | `tools=["read"]` means |
|-----------|---------------------|-------------------|------------------------|
| `yoker.agent(tools=...)` | **All tools** (api.py "None = unset") | No tools | Filter |
| `AgentDefinition(tools=...)` | **No tools** (schema "None = explicit none") | No tools | Filter |

The `AgentDefinition` contract is set by `__post_init__` (`schema.py:65-67`: `if self.tools is None: ... tools_unspecified = False`). The api.py contract is set by `_build_config_and_definition` (`api.py:143`: `tools_unspecified=tools is None`). Both are internally correct; they just disagree on what `None` means for the same kwarg name.

**Root cause**: the side-channel deviation (§1). Under the plan's `tools: tuple | None = None` sentinel approach, `yoker.agent(tools=None)` would pass `AgentDefinition(tools=None)` directly, and both layers would agree: `None` = all tools. The implementation's side-channel forces api.py to manually translate `None` → `()` + `tools_unspecified=True`, creating the seam.

**Recommendation**: two options, in priority order:

1. **Preferred (eliminates the dual contract)**: migrate to the plan's `tools: tuple[str, ...] | None = None` sentinel. Single field, single contract. `yoker.agent(tools=None)` and `AgentDefinition(tools=None)` both mean "all tools". Requires: change schema field type + `__post_init__` (keep `None` instead of normalizing to `()`); add `is None` guards in `_warn_missing_tools`, `validate_tools`, `_filter_tools_by_definition`; update tests. Modest refactor — the implementation already has the three-branch structure, just the condition changes from `tools_unspecified` to `tools is None`.

2. **Acceptable (keeps side-channel, documents the seam)**: add a prominent note to `api.py`'s `agent()` docstring explicitly warning that `yoker.agent(tools=None)` ≠ `AgentDefinition(tools=None)`. The current api.py docstring documents the api.py contract clearly (`None` keeps all; `[]` disables all) but does NOT mention the AgentDefinition layer's opposite `None` semantic. A one-line cross-reference would close the gap.

Given the implementation passes 1889 tests and is working, option 2 is pragmatic for round 0. Option 1 is the cleaner long-term state and should be filed as a follow-up.

### 5. Validator on runtime path

**Correctly wired. Slight overlap with `_warn_missing_tools` is complementary, not redundant.**

`_validate_definition` (`core/__init__.py:400-414`) calls `validate_agent_definition` from the Agent constructor, logging warnings only. This puts the previously test/docs-only validator onto the production path — a reasonable tightening.

**Overlap analysis**:
- `validate_tools` (via `validate_agent_definition`) warns when a bare tool name is not a known built-in (checks against `ToolsConfig`'s 7 known tools).
- `_warn_missing_tools` warns when a requested tool is not in the actual `ToolRegistry`.

These are complementary: the validator catches "you wrote `tools: [raed]` (typo of a known built-in)" against the config; the runtime check catches "you wrote `tools: [pkg:echo]` but that plugin isn't loaded" against the registry. Both are warnings. Not redundant.

**Performance**: negligible. `validate_tools` iterates `definition.tools` (small) against 7 known tools; `validate_non_empty_string` is O(1). Runs once per Agent construction. No concern.

**Behavior change to note**: `validate_agent_definition` raises `ValidationError` on empty `name`/`description`. The loader already enforces this in strict mode, so production-loaded definitions are unaffected. But programmatic construction with an empty `name` (e.g. `AgentDefinition(simple_name="")`) will now raise from the Agent constructor where it previously slipped through silently. This is an improvement, not a regression — recommend a CHANGELOG note.

### 6. Pre-existing bug: file-loaded agents with bare built-in tool names

**Confirmed pre-existing. M.2 does not worsen it, but makes it more impactful. Recommend a follow-up task.**

Reproduction path:
1. `load_agent_definition` uses `namespace=FILE_NAMESPACE="file"` (`loader.py:216`).
2. `_namespace_tools(("read",), "file")` namespaces bare names → `("file:read",)` (`loader.py:61`).
3. At runtime, `_filter_tools_by_definition` Branch 3 (`core/__init__.py:452-460`): for `file:read` (has `:`), only `"file:read"` is added to `requested`. The `yoker:` prefix handling only fires for bare names (the `else` branch).
4. Registry has `yoker:read`. `to_remove` includes `yoker:read`. Agent gets **no tools**.

So `tools: [read]` in a file-loaded agent silently yields an agent with zero tools. The existing test `test_load_valid_agent` (`tests/agents/test_loader.py:146-168`) asserts `definition.tools == ("file:Read", "file:Search")` — confirming the namespacing — but no test exercises the runtime filter on these namespaced values, so the bug is uncaught at the runtime layer.

**M.2 impact**: before M.2, a file-loaded agent with NO `tools:` was rejected by the loader, so users were forced to list tools (and hit the bug). After M.2, omitting `tools:` works (all tools), but adding `tools: [read]` to "tighten scope" silently breaks the agent. The bug is the same; the trap is more attractive. A user who reads the M.2 CHANGELOG and decides to scope their previously-all-tools file agent will fall into it.

**Recommendation**: file a follow-up task (not blocking M.2) to fix `_namespace_tools` so bare built-in tool names are NOT namespaced to the file/plugin namespace — only plugin-specific bare names should be. Alternatively, widen Branch 3 to also try the `yoker:` prefix for namespaced-file inputs (less clean). The existing test `test_load_valid_agent` should be extended to assert the runtime filter keeps the tools, not just that the loader produces namespaced names.

### 7. Architecture regressions

**No layering violations. Two minor concerns noted.**

- **Side-channel as parser state on a domain object**: `tools_unspecified` is arguably parser/loader state placed on `AgentDefinition`, a domain dataclass. A purer model would keep this state in the loader and thread it to the Agent constructor as a parameter. The side-channel is pragmatic (avoids threading a new parameter through `Agent.__init__` and `Session.create_primary_agent`), and the alternative is more invasive. Acceptable trade-off, but worth noting that `AgentDefinition` now carries a field whose only consumer is `_filter_tools_by_definition`.

- **Module docstring inaccuracy**: `schema.py:1` says "Provides frozen dataclasses" but `AgentDefinition` is not frozen. Pre-existing, not introduced by M.2, but M.2 adds mutable `__post_init__` state. Recommend correcting the docstring in a follow-up (either remove "frozen" from the docstring or actually freeze the class — the latter would require `object.__setattr__` in `__post_init__`).

- **No abstraction leaks introduced**: the three-branch filter is self-contained, the validator wiring is a single call, the loader branch is local. Clean.

## Compliance Check

- **RESTful design**: N/A (no HTTP endpoints; internal Python API).
- **Async-first**: N/A (no I/O operations introduced by M.2; the change is synchronous schema/loader/filter logic).
- **Plan adherence**: Option C implemented as endorsed. Three deviations: (1) side-channel flag instead of `None` sentinel (§1, §4), (2) `logger.warning` instead of `logger.info` for all-tools branch (§3, acceptable), (3) warning only on YAML-null forms not all five empty forms (§2, matches plan text but not developer's report claim).
- **Backward compat**: `backwards.md` (`tools: []`) remains a no-tools agent — verified by `test_backwards_md_loads_no_tools`. No regression for any shipped definition (per plan §6/C.4).
- **Config gating preserved**: `test_config_disabled_drops_tool_even_when_all_granted` verifies a config-disabled tool is NOT in the all-tools set. Correct.

## Recommendations (priority order)

1. **(Follow-up, not blocking)** Migrate to the plan's `tools: tuple[str, ...] | None = None` sentinel approach to eliminate the api.py ↔ AgentDefinition dual contract (§4). File as a refinement task. If deferred, add a one-line cross-reference in `api.py`'s `agent()` docstring noting `yoker.agent(tools=None)` ≠ `AgentDefinition(tools=None)`.

2. **(Follow-up)** Fix the pre-existing file-loaded bare-tool-names bug (§6) — `_namespace_tools` should not namespace bare built-in tool names. M.2 makes this trap more attractive; a follow-up fix is now higher priority.

3. **(Round 0, minor)** Either emit `agent_tools_explicit_null_treated_as_empty` for `tools: ""` and `tools: []` too (for consistency with the "all five forms share the no-tools semantic" framing), or correct the developer's report claim that "all five forms are handled identically" to "all five forms produce the same `tools=()` + `tools_unspecified=False`; the warning is emitted only for the YAML-null forms" (§2).

4. **(Round 0, minor)** Correct `schema.py:1` module docstring "frozen dataclasses" → "dataclasses" (or freeze the class). Pre-existing, but M.2 adds mutable `__post_init__` state (§1, §7).

5. **(Round 0, minor)** Add a CHANGELOG note that `validate_agent_definition` is now on the runtime path and will raise `ValidationError` on empty `name`/`description` for programmatic constructions (§5).

## Conclusion

**Approved.** The implementation is architecturally sound, correctly realises Option C, and has effectively zero backward-compatibility regression (verified by the `backwards.md` regression guard). The dual-contract finding (§4) is the one item worth acting on, but it is a documentation/refinement concern, not a correctness bug — both layers behave correctly per their own contracts. The pre-existing file-loaded bare-tool bug (§6) is out of scope for M.2 but should be filed as a follow-up with elevated priority given M.2's new all-tools default makes the trap more attractive.

## Next Steps

- Address recommendation 3 (warning coverage or report wording) and recommendation 4 (docstring) as round 0 polish, or explicitly defer with rationale.
- File recommendations 1 and 2 as follow-up tasks in TODO.md.
- Proceed to the next stage of the c3:project-review cycle (quality review).