# API Architecture Review: M.2 Default Tools Behavior — Round 1

**Date**: 2026-07-20
**Reviewer**: API Architect Agent
**Task**: PR #47 round-1 scoped re-review — verify the two round-0 recommendations (`AllToolsSentinel` class + api.py contract alignment / Option D-1) are correctly implemented.
**Prior reviews**: `reporting/m2-default-tools-behavior/api-architect-review.md` (round 0), `analysis/m2-default-tools-behavior-api.md` (owner `ALL_TOOLS` feedback evaluation, "Owner ALL_TOOLS feedback evaluation" addendum §D).
**Scope**: round-1 changed files only (`agents/schema.py`, `agents/__init__.py`, `agents/loader.py`, `agents/validator.py`, `core/__init__.py`, `api.py`, `ui/commands/tools.py`, `ui/commands/agents.py`, tests, docs).

## Summary

**Approved.** Both recommendations are correctly implemented. The `AllToolsSentinel` class is a clean, production-grade singleton that matches (and modestly exceeds) the round-0 spec. The api.py ↔ `AgentDefinition` dual-contract seam is fully eliminated via Option D-1: `yoker.agent(tools=None)` now means "no tools" at both layers, and `ALL_TOOLS` is the shared "all tools" sentinel. All eight sentinel-guard sites (three runtime + one loader + one validator + three UI) are correctly guarded; no unguarded iteration site remains. The change is a strict architectural improvement over the round-0 `tools_unspecified` side-channel. Three non-blocking observations follow.

## Findings

### 1. `AllToolsSentinel` class design — correct, with a pickle bonus

Implemented at `src/yoker/agents/schema.py:13-57`. Item-by-item verification against the round-0 spec (`analysis/m2-default-tools-behavior-api.md` §D.2.2):

| Feature | Round-0 spec | Implementation | Verdict |
|---------|--------------|----------------|---------|
| Singleton `__new__` | required | lines 24-27: `cls._instance` guard, returns the same instance | ✓ correct |
| `__repr__` → `"ALL_TOOLS"` | required | line 30 | ✓ correct |
| `__bool__` → `True` | required (distinguishes from `None`/`()` falsy) | line 34 | ✓ correct |
| `__iter__` raises `TypeError` | required (prevent accidental iteration) | lines 36-39, message names `is` as the correct test | ✓ correct |
| `__eq__` identity | not in round-0 spec; implied by singleton | lines 41-42: `other is self` | ✓ sound (makes `==` agree with `is`) |
| `__hash__` | not in round-0 spec | line 45: `id(self)` | ✓ sound (consistent with `__eq__`; the singleton is hashable) |
| `__reduce__` for pickle | not in round-0 spec | lines 47-49 + `_resolve_all_tools` (lines 52-54) | ✓ bonus — pickle round-trips back to the singleton via `_resolve_all_tools` rather than reconstructing a new instance, preserving singleton identity across pickle |
| `ALL_TOOLS` module constant | required | line 57 | ✓ correct |

**Public class name (`AllToolsSentinel`, not `_AllToolsSentinel`).** Round 0 spec (§D.2.2) used a public class name; the owner kept it public. **Public is the right call.** `AllToolsSentinel` is part of the public API surface (exported from `yoker.agents`), users may type-annotate against it, and the `isinstance` narrowing the implementation uses at every guard site requires the class to be importable and public. A `_AllToolsSentinel` would have forced downstream code to import a private name for narrowing — worse.

**`__reduce__` is a welcome addition** beyond the round-0 spec. The singleton `__new__` alone does not guarantee pickle round-trips to the same instance: `pickle.loads(pickle.dumps(ALL_TOOLS))` would otherwise construct a new `AllToolsSentinel` via `__new__`, which (because `cls._instance` is already set) returns the existing singleton — so pickle would work even without `__reduce__`. The explicit `__reduce__` makes the intent visible and robust to any future change in `__new__`'s behavior. Good defensive engineering.

### 2. api.py contract alignment (Option D-1) — dual contract eliminated

Implemented at `src/yoker/api.py:88, 142-149, 167, 195-199, 323, 353-357`. Verification of the five-cell contract matrix from §D.3:

| Call | Round-0 (seam) | Round-1 implementation | Verdict |
|------|----------------|------------------------|---------|
| `yoker.agent()` | all tools (default `None`, translated) | all tools (default `ALL_TOOLS`, pass-through) | ✓ aligned |
| `yoker.agent(tools=ALL_TOOLS)` | n/a (sentinel didn't exist) | all tools (pass-through) | ✓ aligned |
| `yoker.agent(tools=None)` | **all tools** (api.py translated `None`→`ALL_TOOLS`) | **no tools** (pass-through; `AgentDefinition.__post_init__` normalizes `None`→`()`) | ✓ aligned with `AgentDefinition` — seam eliminated |
| `yoker.agent(tools=[])` | no tools | no tools (pass-through; `__post_init__` normalizes `[]`→`()`) | ✓ aligned |
| `yoker.agent(tools=["read"])` | filter | filter (pass-through; `__post_init__` normalizes list→tuple) | ✓ aligned |

**The translation layer is gone.** `tools` flows from `yoker.agent()` → `_build_config_and_definition(tools=...)` → `AgentDefinition(tools=...)` unchanged. The round-0 `tools_unspecified=tools is None` side-channel and the `None`→`ALL_TOOLS` bridge are both removed. One contract on the `tools` kwarg name at both layers.

**The `cast` in `_build_config_and_definition` (line 148).** `tools=cast("tuple[str, ...] | AllToolsSentinel", tools)` is a mypy bridge reflecting the post-`__post_init__` runtime invariant. The input type is `list[str] | AllToolsSentinel | None`; `AgentDefinition.__post_init__` normalizes `None`/`list` to `tuple`, so after construction the field is `AllToolsSentinel | tuple[str, ...]`. mypy cannot track `__post_init__` mutations, so the cast bridges the declared input type to the post-normalization runtime type. **Sound.** The cast does not hide a logic discrepancy — it documents an invariant mypy can't see. See observation 3 below for the annotation tradeoff that makes the cast necessary.

**Docstrings (lines 195-199, 353-357) are accurate.** Both `agent()` and `session()` docstrings state: default `ALL_TOOLS` = all tools; `None` = no tools (matches `AgentDefinition`); `[]` = no tools; `["read"]` = filter. The "matches the `AgentDefinition` contract" phrasing explicitly calls out the alignment — exactly the framing §D.3 recommended.

**No remaining seam.** I searched for any other translation/bridge in api.py and found none. `tools` is passed through at every layer.

### 3. `isinstance` vs `is` for mypy narrowing — acceptable, with a note

Round 0 recommended `tools is ALL_TOOLS` (identity). The implementation uses `isinstance(tools, AllToolsSentinel)` at all seven downstream guard sites:

- `core/__init__.py:384` (`_warn_missing_tools`)
- `core/__init__.py:441` (`_filter_tools_by_definition`)
- `loader.py:145` (`_namespace_tools` guard)
- `validator.py:104` (`validate_agent_definition`)
- `ui/commands/tools.py:39, 87`
- `ui/commands/agents.py:43, 70`

(`schema.py:102` in `__post_init__` uses `is ALL_TOOLS` — the one site that uses identity.)

**Are they equivalent?** At runtime today, yes. The singleton `__new__` guarantees only one `AllToolsSentinel` instance exists, so `isinstance(x, AllToolsSentinel)` ⟺ `x is ALL_TOOLS` for all `x`.

**Subclassing risk.** `isinstance` would return `True` for instances of a subclass of `AllToolsSentinel`; `is ALL_TOOLS` would return `False` (subclass instance is not the singleton). Python does not prevent subclassing (no `final`, no `__init_subclass__` guard). However:
- The singleton `__new__` makes subclassing self-defeating: `SubClass()` calls `super().__new__(SubClass)`, but `cls._instance` (looked up via MRO) finds `AllToolsSentinel._instance` already set, so `super().__new__` is never called and the existing base-singleton is returned — the subclass "instance" is actually the base singleton. A subclass cannot produce a distinct instance.
- The class is in a controlled module, not an extension point.

**Verdict: `isinstance` is acceptable.** The subclassing risk is theoretical and neutered by the singleton `__new__`. Both `is` and `isinstance` narrow to `AllToolsSentinel` for mypy. The implementation's inline comments at each guard site correctly note "AllToolsSentinel is a singleton so this is equivalent to `tools is ALL_TOOLS`" — the reasoning is sound.

**Minor inconsistency (non-blocking).** The `AllToolsSentinel` docstring (line 18-19) recommends "test with ``is ALL_TOOLS``"; the `__post_init__` uses `is`; the seven downstream guards use `isinstance`. The CHANGELOG (line 23) documents both forms as acceptable. This is cosmetic — both work, the comments explain the equivalence — but a reader following the docstring into the source will find a different test form. If desired, a future tidy-up could align all guards on `is ALL_TOOLS` (stricter and matches the docstring) or update the docstring to name `isinstance` as the preferred narrowing form. Not blocking.

### 4. The guard sites — all eight correctly guarded, no missed iteration

The task description named "three guards + two UI guards" (five). The actual implementation has eight sentinel-guard sites. All are correct:

| # | Site | Guard | Iteration it protects |
|---|------|-------|-----------------------|
| 1 | `core/__init__.py:384` (`_warn_missing_tools`) | `isinstance(...) → return` | line 389 `for requested in self.definition.tools:` |
| 2 | `core/__init__.py:441` (`_filter_tools_by_definition`) | `isinstance(...) → return` | line 462 `for tool_name in tools:` (branch 3) |
| 3 | `validator.py:104` (`validate_agent_definition`) | `if not isinstance(...)` | line 105 `validate_tools(definition.tools, ...)` (iterates inside) |
| 4 | `loader.py:145` (`_namespace_tools` guard) | `if not isinstance(...)` | line 146 `tuple(_namespace_tools(tools, ...))` |
| 5 | `ui/commands/tools.py:39` (`_has`) | `isinstance(...) → return True` | line 45 `for requested in ag.definition.tools:` |
| 6 | `ui/commands/tools.py:87` (display) | `isinstance(...)` (elif branch) | line 90 `sorted(agent.definition.tools)` |
| 7 | `ui/commands/agents.py:43` (current agent) | `isinstance(...)` (elif branch) | line 46 `sorted(agent.definition.tools)` |
| 8 | `ui/commands/agents.py:70` (known agents) | `isinstance(...)` (elif branch) | line 73 `sorted(agent_definition.tools)` |

Plus `schema.py:102` (`__post_init__`): `if self.tools is ALL_TOOLS: return` — preserves the sentinel before normalization. Not a guard against iteration, but the sentinel-preservation point §D.2.3 required. Correct.

**No unguarded iteration site.** I grepped `definition\.tools` across `src/yoker` and traced every iteration site (sorted, for-loop, `tuple(...)`, `validate_tools(...)`). Each is preceded by a sentinel guard that returns or branches away before iteration. The `__iter__` raising `TypeError` is the defense-in-depth backstop: if a future code path forgets the guard, the sentinel raises loudly rather than silently iterating as empty.

### 5. Type annotation — clean, with a minor tradeoff

**Declared annotation** (`schema.py:85`): `tools: "tuple[str, ...] | AllToolsSentinel" = ALL_TOOLS`.

**Round-0 spec** (§D.2.4): `tuple[str, ...] | AllToolsSentinel | None = ALL_TOOLS` (including `None`).

The implementation omits `None` (and `list[str]`) from the declared type, even though `__post_init__` accepts and normalizes them. The comment at lines 80-84 explains: "The declared type is broader so callers may pass None / [] at construction (normalized to () in __post_init__); after __post_init__ the runtime type is AllToolsSentinel | tuple[str, ...]." (Minor wording slip: the declared type is *narrower* than what's accepted, not broader — the comment means the *accepted* type is broader than the declared type. The intent is clear.)

**Tradeoff.** Annotating with the post-`__post_init__` invariant (`AllToolsSentinel | tuple[str, ...]`) gives cleaner downstream mypy narrowing — no `None` branch to handle at guard sites — at the cost of:
- Static type checkers flag `AgentDefinition(tools=None)` and `AgentDefinition(tools=[])` as type errors even though they work at runtime.
- The `cast` in `api.py:148` is needed to bridge the api.py parameter type (`list[str] | AllToolsSentinel | None`) into the narrower `AgentDefinition` field type.

Both approaches work. The chosen annotation is pragmatic and the `cast` is a small, localized cost. If the owner prefers, widening the annotation to `tuple[str, ...] | AllToolsSentinel | None | list[str]` would eliminate the `cast` and silence static checkers on `AgentDefinition(tools=None)`, at the cost of adding a `None`/`list` branch at each downstream guard site (or relying on `isinstance` to narrow past them, which it does). **Not blocking either way.** The current annotation is internally consistent and the `cast` documents the invariant.

**Downstream narrowing.** All guard sites use `isinstance(tools, AllToolsSentinel)` which narrows the union to `AllToolsSentinel` in the early-return branch and to `tuple[str, ...]` in the fall-through — no additional narrowing needed anywhere. `len(tools)`, `for ... in tools`, `sorted(tools)`, `tuple(_namespace_tools(tools, ...))` all type-check cleanly in the fall-through. No new narrowing burden introduced.

### 6. Architecture cleanliness vs round 0 — strict improvement

| Aspect | Round 0 (`tools` + `tools_unspecified`) | Round 1 (`AllToolsSentinel` sentinel) |
|--------|------------------------------------------|----------------------------------------|
| Fields carrying intent | 2 (`tools` + `tools_unspecified: bool`) | 1 (`tools`) |
| Invariant to maintain | `tools_unspecified` must stay in sync with whether `tools` was explicitly set | none — the field value IS the intent |
| Failure mode | caller passes `tools=()` with `tools_unspecified=True` (or vice versa) → silent wrong behavior | no secondary field to get wrong |
| api.py ↔ schema contract | dual (api.py `None`=all, schema `None`=none; bridge translation required) | single (both layers: `ALL_TOOLS`=all, `None`/`()`=none) |
| Domain object purity | `tools_unspecified` is parser state on a domain dataclass | `ALL_TOOLS` is a domain value (an intent) |
| Public API surface | `tools_unspecified` leaks into the dataclass constructor | `ALL_TOOLS` is a clear, named constant |
| User-code readability | `yoker.agent(tools_unspecified=True)` — plumbing | `yoker.agent(tools=ALL_TOOLS)` — self-documenting |
| `__iter__` safety | n/a (empty tuple iterates as no-op) | sentinel raises `TypeError` on accidental iteration (defense in depth) |

**New complexity introduced by round 1** (all anticipated in §D.4):
- `AllToolsSentinel` class (~15 lines) — well-encapsulated in `schema.py`.
- `__reduce__` + `_resolve_all_tools` (~5 lines) — pickle support, beyond round-0 spec.
- `cast` in `api.py:148` — one-line mypy bridge.
- `isinstance` guards at 7 sites — net neutral vs `tools_unspecified` checks (same branch count, cleaner conditions).
- `__post_init__` sentinel-preservation guard (line 102) — one `if self.tools is ALL_TOOLS: return` clause.

**Net: strict improvement.** The two-field invariant was the heavier burden; round 1 removes more complexity than it adds. No new complexity that wasn't anticipated.

### 7. Minor observations (non-blocking)

1. **`ALL_TOOLS` not re-exported from top-level `yoker`.** Round 0 §D.5 recommendation 2 said "Export `ALL_TOOLS` publicly from `yoker` (or `yoker.agents`)". It is exported from `yoker.agents` (`agents/__init__.py:12`) — satisfying the "or" — but not from `yoker` (`yoker/__init__.py` does not include it). Users writing `yoker.agent(tools=ALL_TOOLS)` must `from yoker.agents import ALL_TOOLS` rather than `from yoker import ALL_TOOLS`. Acceptable per the round-0 wording; re-exporting from `yoker` would be more discoverable. Not blocking.

2. **`test_tools_none_disables_all` (test_builder.py:77-80)** explicitly covers the behavior change: `yoker.agent(tools=None)` → no tools. This is the test the round-0 addendum §D.7 action items required. Good.

3. **CHANGELOG (lines 29-37)** documents the `yoker.agent(tools=None)` behavior change clearly, including the "use `yoker.agent()` or `yoker.agent(tools=ALL_TOOLS)` for all tools" migration note. Matches §D.7 action item. Good.

## Compliance Check

| Criterion | Status |
|-----------|--------|
| `AllToolsSentinel` dedicated class (not bare `[]`) | ✓ implemented |
| Singleton `__new__`, `__repr__`, `__bool__`, `__iter__` guard | ✓ implemented |
| `__eq__`/`__hash__`/`__reduce__` (beyond spec, sound) | ✓ implemented |
| `AgentDefinition.tools` default `ALL_TOOLS` | ✓ implemented (schema.py:85) |
| `__post_init__` preserves sentinel | ✓ implemented (schema.py:102) |
| `None`/`[]` normalized to `()` (no tools) | ✓ implemented (schema.py:104-107) |
| `tools_unspecified` removed | ✓ removed |
| api.py Option D-1 (sentinel at both layers) | ✓ implemented (api.py:167, 323) |
| api.py `None`→`ALL_TOOLS` bridge removed | ✓ removed |
| `yoker.agent(tools=None)` → no tools | ✓ verified by test_builder.py:77-80 |
| Loader `"tools" not in frontmatter` → `ALL_TOOLS` | ✓ implemented (loader.py:114-115) |
| All iteration sites guarded | ✓ all 8 sites verified |
| `isinstance` narrowing at guard sites | ✓ acceptable (subclassing risk neutered by singleton `__new__`) |
| `ALL_TOOLS` exported (from `yoker.agents`) | ✓ (not from top-level `yoker` — minor) |
| Tests cover behavior change | ✓ test_builder.py:77-80, test_agent_tools.py, test_loader.py, test_validator.py |
| CHANGELOG documents behavior change | ✓ CHANGELOG.md:29-37 |

## Conclusion

**Approved.** Both round-0 recommendations are correctly implemented. The `AllToolsSentinel` class is a clean singleton with a self-documenting `repr`, an `__iter__` guard, and a welcome pickle `__reduce__`. The api.py ↔ `AgentDefinition` dual-contract seam is fully eliminated (Option D-1): one contract on the `tools` kwarg at both layers. All eight sentinel-guard sites are correctly guarded; no unguarded iteration site remains. The change is a strict architectural improvement over the round-0 `tools_unspecified` side-channel. The three observations (`isinstance` vs `is` consistency, `ALL_TOOLS` top-level re-export, annotation width vs `cast`) are non-blocking polish items.

## Next Steps

- Owner may merge PR #47 on this review's endorsement.
- Optional polish (non-blocking, can be follow-up):
  - Align guard-site checks on `is ALL_TOOLS` (or update the `AllToolsSentinel` docstring to name `isinstance` as the preferred narrowing form) for internal consistency.
  - Re-export `ALL_TOOLS` and `AllToolsSentinel` from top-level `yoker` for discoverability.
  - Consider widening the `AgentDefinition.tools` annotation to include `None | list[str]` to eliminate the `cast` in `api.py:148` (tradeoff: downstream `None`/`list` branches at guard sites).