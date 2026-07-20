# API Architecture Review: M.2 Default Tools Behavior — Round 2

**Date**: 2026-07-20
**Reviewer**: API Architect Agent
**Task**: PR #47 round-2 scoped re-review — verify the owner's simplified `ALL_TOOLS = []` sentinel (replacing the round-1 `AllToolsSentinel` class) and the dual-contract elimination (api.py `None`→`ALL_TOOLS` bridge removed).
**Prior reviews**: round 0 (`api-architect-review.md`), round 1 (`api-architect-review-round1.md` — approved `AllToolsSentinel` class), `owner-feedback-interpretation.md`.
**Scope**: round-2 changed files (`agents/schema.py`, `agents/__init__.py`, `agents/loader.py`, `agents/validator.py`, `core/__init__.py`, `api.py`, `tests/core/test_agent_tools.py`, `CHANGELOG.md`, `DEVELOPMENT.md`).

## Summary

**Approved.** The owner's simplified `ALL_TOOLS = []` sentinel works. It is a faithful implementation of the owner's explicit proposal. The API contract is correctly adhered to with no dual contract: `yoker.agent(tools=None)` means "no tools" at both the api.py and `AgentDefinition` layers, and `yoker.agent()` (default `ALL_TOOLS`) means "all tools". The `tools` parameter handling is clean. The `AllToolsSentinel` class, all eight `isinstance` guards, and the `typing.cast` in api.py are removed. No specific, documented problem with the owner's approach justifies proposing a deviation. Four non-blocking observations follow.

## The Owner's Proposal (quoted)

> ```python
> ALL_TOOLS = []  # unique singleton, checked with `is`
> class AgentDefinition
>   def __init__(tools : list | None = ALL_TOOLS):
>     if tools is ALL_TOOLS:
>       # dynamically populate with all tools from registry
> ```
>
> The ALL_TOOLS check was limited to 1 single spot, and from there on it was just a list of tools, without any impact elsewhere in the codebase.

### Does it work?

**Yes.** The implementation matches the proposal:

- `ALL_TOOLS: list[str] = []` — a module-level empty list, the unique singleton (`src/yoker/agents/schema.py:14`).
- `AgentDefinition.tools` defaults to `ALL_TOOLS` via `field(default_factory=lambda: ALL_TOOLS)` (line 42). The factory returns the SAME object so `is ALL_TOOLS` works (documented in the field comment, line 41).
- `__post_init__` (lines 50-65) preserves the sentinel when `self.tools is ALL_TOOLS`, normalizes `None` → `[]`, and converts tuples → lists. The sentinel survives normalization.
- The sentinel is resolved in ONE place — `Agent._filter_tools_by_definition` (`src/yoker/core/__init__.py:441`) — which replaces `self.definition.tools` with `list(self.tools.names)` (the real list of all tool names from the registry). After this spot, `tools` is a plain list. This matches the owner's "dynamically populate with all tools from registry" sketch.

### Is the "1 single spot" claim accurate?

**In spirit, yes.** The *resolution* (sentinel → real list) is in exactly one spot (`_filter_tools_by_definition`). There are four additional `is ALL_TOOLS` / `is not ALL_TOOLS` *identity checks* elsewhere:

| Site | Purpose | Type |
|------|---------|------|
| `schema.py:59` (`__post_init__`) | Preserve sentinel through normalization | Passthrough |
| `loader.py:143` (`_namespace_tools` guard) | Skip namespacing when sentinel | Passthrough |
| `api.py:140,142` (`_build_config_and_definition`) | Decide whether to build a custom definition | Passthrough |
| `core/__init__.py:441` (`_filter_tools_by_definition`) | **Resolve sentinel to real list** | **Resolution (the 1 spot)** |

The first three are not "impact" — they preserve or passthrough the sentinel without resolving it. After the resolution spot, `tools` is just a list, exactly as the owner stated. The claim holds.

## API Contract Verification

### The owner-confirmed contract

| Call | Expected | Implemented | Verdict |
|------|----------|-------------|---------|
| `AgentDefinition()` | all tools | default_factory → `ALL_TOOLS`; `__post_init__` preserves; resolved to all at runtime | ✓ |
| `AgentDefinition(tools=None)` | no tools | `__post_init__`: `None` → `[]` | ✓ |
| `AgentDefinition(tools=[])` | no tools | `__post_init__`: already `[]`, no change | ✓ |
| `AgentDefinition(tools=["read"])` | only "read" | no transformation; filter at runtime | ✓ |
| `yoker.agent(tools=None)` | no tools (NO dual contract) | `tools=None` passed to `AgentDefinition(tools=None)` → `[]` | ✓ |
| `yoker.agent()` | all tools | default `tools=ALL_TOOLS`; passthrough; Agent builds default `AgentDefinition()` | ✓ |

### No dual contract

Round 1 kept the api.py bridge: `yoker.agent(tools=None)` → all tools (api.py translated `None` → `ALL_TOOLS`), while `AgentDefinition(tools=None)` → no tools. That was the dual contract.

Round 2 removes the bridge. The api.py default is now `tools: list[str] | None = ALL_TOOLS` (line 165), and `tools` is passed through UNCHANGED to `AgentDefinition` (line 146: `tools=tools`). No `None`→`ALL_TOOLS` translation. `None` means "no tools" at both layers.

Traced paths:

- **`yoker.agent()`**: `tools=ALL_TOOLS` (default) → `_build_config_and_definition`: `tools is not ALL_TOOLS` is False, and if `system_prompt is None` too, no custom definition is built → `resolved_definition=None` → `Agent(agent_definition=None)` → `_resolve_agent_definition` returns `AgentDefinition()` (default, `tools=ALL_TOOLS`) → all tools at runtime. ✓
- **`yoker.agent(tools=None)`**: `tools=None` → `tools is not ALL_TOOLS` is True → builds `AgentDefinition(tools=None)` → `__post_init__`: `None` → `[]` → no tools. ✓
- **`yoker.agent(tools=[])`**: `tools=[]` → `tools is not ALL_TOOLS` is True (different object) → builds `AgentDefinition(tools=[])` → `[]` → no tools. ✓
- **`yoker.agent(tools=ALL_TOOLS)` explicit**: same as `yoker.agent()` — sentinel passed through. ✓
- **`yoker.agent(tools=["read"])`**: builds `AgentDefinition(tools=["read"])` → filter. ✓

The `typing.cast` that round 1 needed to bridge the api.py parameter type into the narrower `AgentDefinition` field type is gone (confirmed: api.py imports only `Any, Literal, TypeVar` from `typing`). The round-1 `cast` was a symptom of the `AllToolsSentinel` class introducing a third type the field annotation had to track. With `ALL_TOOLS = []` (a `list[str]`), the field type `list[str] | None` and the api.py parameter type `list[str] | None` agree, and `None`/`[]`/`["read"]`/`ALL_TOOLS` all fit without a bridge. Clean.

### `tools` parameter handling — clean

| Layer | Signature | Default | Normalization |
|-------|-----------|---------|---------------|
| `yoker.agent()` | `tools: list[str] \| None = ALL_TOOLS` | `ALL_TOOLS` (all tools) | none (passthrough) |
| `yoker.session()` | `tools: list[str] \| None = ALL_TOOLS` | `ALL_TOOLS` (all tools) | none (passthrough) |
| `AgentDefinition` | `tools: "list[str] \| None" = field(default_factory=lambda: ALL_TOOLS)` | `ALL_TOOLS` (all tools) | `__post_init__`: preserve sentinel; `None`→`[]`; tuple→list |
| `Agent._filter_tools_by_definition` | — | — | resolve `ALL_TOOLS` → `list(self.tools.names)`; `[]` → clear; non-empty → filter |

The normalization is localized to `__post_init__` (input normalization) and `_filter_tools_by_definition` (runtime resolution). No other layer touches `tools`. The flow is linear and unidirectional. Clean.

## Cleanup Verification

| Round-1 artifact | Round-2 status |
|------------------|----------------|
| `AllToolsSentinel` class | Removed (`schema.py` — no class definition) |
| `__reduce__` / `_resolve_all_tools` | Removed (no pickle support) |
| `isinstance(..., AllToolsSentinel)` guards (8 sites) | All removed; replaced by `is ALL_TOOLS` / `is not ALL_TOOLS` or truthiness |
| `typing.cast` in api.py | Removed |
| api.py `None`→`ALL_TOOLS` bridge | Removed (passthrough) |
| `__bool__` / `__iter__` / `__eq__` / `__hash__` on sentinel | N/A (bare `[]` uses list defaults) |

Confirmed by grep: no `isinstance(..., AllToolsSentinel)` remains in `src/yoker`; no `cast` in api.py; `AllToolsSentinel` is not referenced anywhere.

## Simplicity Principle Assessment

Per the review instructions: quote the owner's proposal, state whether it works, only propose a deviation if there is a specific, documented problem. "A dedicated class is cleaner" is NOT sufficient.

**The owner's approach works.** It is functionally correct, the contract is adhered to, and the code is simpler (a module-level `[]` vs a 15-line class with `__new__`, `__repr__`, `__bool__`, `__iter__`, `__eq__`, `__hash__`, `__reduce__`).

The round-1 `owner-feedback-interpretation.md` (§2) flagged four concerns with bare `[]`: type annotation, pickling, equality footgun, repr. Evaluating each against the actual round-2 implementation:

| Concern | Round-1 assessment | Round-2 reality | Specific documented problem? |
|---------|-------------------|-----------------|------------------------------|
| **Type annotation** | `list` default vs `tuple` field type mismatch | Field is `list[str] \| None`; `ALL_TOOLS` is `list[str]`; types agree. No mismatch. | **No.** Resolved by using `list` consistently (round 1 used `tuple`). |
| **Pickling** | `pickle.dumps([])` → new `[]` → `is ALL_TOOLS` breaks | No code pickles `AgentDefinition` today (grep: zero hits for `pickle` near `AgentDefinition`). The sentinel is resolved during Agent construction; after resolution `tools` is a plain list that pickles fine. | **No.** Latent only; no current pickle path. |
| **Equality footgun** | `[] == []` is True; `tools == ALL_TOOLS` conflates "no tools" with "all tools" | All code uses `is`/`is not` (grep-verified). Docstrings and field comment say "Test with `is ALL_TOOLS`". Tests enforce `is`. | **No.** Latent only; all current uses are `is`. |
| **Repr/debugging** | `repr(ALL_TOOLS)` → `[]` (ambiguous in tracebacks) | True — tracebacks show `[]` for the sentinel. The field comment and docstring document the sentinel semantics. | **No.** Debugging UX, not a functional bug. |

None of the four concerns rise to "specific, documented problem with the owner's approach" in the current codebase. They are latent risks or UX concerns, all of which the owner explicitly weighed against the simplicity gain and accepted. Per the Simplicity Principle, I do not propose a deviation.

## Non-Blocking Observations

### 1. Latent mutability of the sentinel

`ALL_TOOLS` is a mutable `list`. The `__post_init__` early-return (line 59-60) means the sentinel IS stored as `self.tools` on an `AgentDefinition` before the Agent resolves it. Any code that calls `self.tools.append(...)` or `self.tools.extend(...)` on such a definition before resolution would mutate the shared singleton, corrupting it for all instances.

No current code does this (the loader skips `_namespace_tools` when `tools is ALL_TOOLS`; the validator early-returns; `_warn_missing_tools` early-returns). The risk is latent. If a future contributor adds a mutation path before the resolution spot, the corruption would be silent and global.

A one-line defensive guard in `__post_init__` would eliminate this: after `if self.tools is ALL_TOOLS: return`, the sentinel is stored as-is. An alternative is to make `ALL_TOOLS` a `tuple` (immutable) — but then the field type would need `tuple[str, ...] | list[str] | None`, and the `is` check still works on tuples. Not blocking; noted for awareness.

### 2. `==` vs `is` footgun

`ALL_TOOLS == []` is `True` (both are empty lists). A contributor who writes `if tools == ALL_TOOLS:` instead of `if tools is ALL_TOOLS:` would silently treat any empty list as "all tools". The codebase consistently uses `is` (grep-verified: 11 `is ALL_TOOLS` / `is not ALL_TOOLS` sites, zero `== ALL_TOOLS` sites). The docstring says "Test with `is ALL_TOOLS`". The tests enforce `is`. The risk is latent and mitigated by documentation and convention. Not blocking.

### 3. `/agents` UX gap for unresolved definitions

`ui/commands/agents.py:42,67` uses `if agent_definition.tools:` to decide whether to show a tools line. For known agents in the registry (definitions that have NOT been through Agent construction), `ALL_TOOLS` is `[]` (falsy), so the tools line is skipped — identical to an explicit `tools: []` (no tools) agent. Under round 1, the `isinstance(..., AllToolsSentinel)` guard displayed "all tools" for the sentinel case.

This means `/agents` can no longer distinguish "all tools" from "no tools" for known-but-unconstructed agents. For the *current* agent (constructed, sentinel resolved), `/tools` and `/agents` both work correctly (the resolved list is non-empty → shown).

This is a minor UI UX tradeoff, not an API contract issue. The owner's Simplicity Principle accepts this. Not blocking. If desired, a future UI tweak could check `is ALL_TOOLS` explicitly and display "(all)" for the sentinel case — but that reintroduces an `is ALL_TOOLS` check in the UI layer, which the owner's "no impact elsewhere" framing seeks to avoid.

### 4. Pickle round-trip

If `AgentDefinition` is ever pickled before Agent construction (e.g., for caching, multiprocessing, or distributed session state), `pickle.loads(pickle.dumps(definition))` would produce a definition where `self.tools is []` (a new empty list) rather than `self.tools is ALL_TOOLS` — silently flipping "all tools" to "no tools". No current code pickles `AgentDefinition` (grep-verified). If a pickle path is added in the future, this would need a `__getstate__`/`__setstate__` or a custom `__reduce__` on `AgentDefinition` to preserve the sentinel identity. Not blocking; noted for future awareness.

## Compliance Check

| Criterion | Status |
|-----------|--------|
| Owner's `ALL_TOOLS = []` proposal implemented faithfully | ✓ |
| `ALL_TOOLS` is a module-level `[]` singleton | ✓ (`schema.py:14`) |
| Checked with `is` (identity) | ✓ (all 11 sites) |
| Resolved in ONE spot (`_filter_tools_by_definition`) | ✓ (`core/__init__.py:441`) |
| `AgentDefinition()` → all tools | ✓ |
| `AgentDefinition(tools=None)` → no tools | ✓ (`__post_init__`) |
| `AgentDefinition(tools=[])` → no tools | ✓ |
| `AgentDefinition(tools=["read"])` → filter | ✓ |
| `yoker.agent()` → all tools | ✓ (default `ALL_TOOLS`, passthrough) |
| `yoker.agent(tools=None)` → no tools (no dual contract) | ✓ (passthrough, no bridge) |
| `yoker.agent(tools=[])` → no tools | ✓ |
| `yoker.agent(tools=["read"])` → filter | ✓ |
| `yoker.agent(tools=ALL_TOOLS)` → all tools | ✓ |
| `AllToolsSentinel` class removed | ✓ |
| All 8 `isinstance` guards removed | ✓ |
| `typing.cast` removed from api.py | ✓ |
| api.py `None`→`ALL_TOOLS` bridge removed | ✓ |
| Loader `"tools" not in frontmatter` → `ALL_TOOLS` | ✓ (`loader.py:114`) |
| `__post_init__` preserves sentinel | ✓ (`schema.py:59-60`) |
| `default_factory=lambda: ALL_TOOLS` returns SAME object | ✓ (`schema.py:42`, documented line 41) |
| CHANGELOG documents the sentinel + dual-contract elimination | ✓ (`CHANGELOG.md:11-40`) |
| DEVELOPMENT.md documents the implementation | ✓ |
| Tests cover all 12 acceptance criteria | ✓ (`tests/core/test_agent_tools.py`) |

## Conclusion

**Approved.** The owner's simplified `ALL_TOOLS = []` sentinel is a faithful implementation of their explicit proposal, it works, and no specific, documented problem justifies proposing a deviation. The API contract is correctly adhered to with no dual contract: `yoker.agent(tools=None)` means "no tools" at both layers, and the api.py default (`ALL_TOOLS`) means "all tools". The `tools` parameter handling is clean — normalization is localized to `__post_init__`, resolution to one spot, and passthrough everywhere else. The round-1 complexity (`AllToolsSentinel` class, 8 `isinstance` guards, `typing.cast`, `None`→`ALL_TOOLS` bridge) is all gone. The four observations (latent mutability, `==` footgun, `/agents` UX gap, pickle round-trip) are non-blocking latent risks or UX tradeoffs that the owner's Simplicity Principle explicitly accepts.

## Next Steps

- Owner may merge PR #47 on this review's endorsement.
- No blocking action items.
- Optional future polish (non-blocking, can be follow-up):
  - If a pickle/multiprocessing path is added for `AgentDefinition`, add `__getstate__`/`__setstate__` to preserve sentinel identity.
  - If the `/agents` UX gap for unresolved definitions becomes bothersome, add an explicit `is ALL_TOOLS` check in the UI display (trading a small simplicity cost for UX clarity).