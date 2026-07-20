# Owner Feedback Interpretation: `tools_unspecified` vs `ALL_TOOLS` Sentinel

- **Task**: M.2 Default Tools Behavior (PR #47, round 1 — owner feedback)
- **Branch**: `feature/m2-default-tools-behavior`
- **Analyst**: functional-analyst
- **Date**: 2026-07-20
- **Stage**: Analysis only — no code changes
- **Verdict**: The owner's `ALL_TOOLS` sentinel approach is sound. Proceed with the refactor. One implementation detail must be adjusted (do not use a bare `[]` as the sentinel; use a dedicated singleton object). Two new guards (`_warn_missing_tools`, `validate_agent_definition`) are required because the sentinel is not iterable — these are the only non-obvious additions beyond the owner's sketch.

---

## 1. Is the owner's `ALL_TOOLS` sentinel approach sound?

**Yes.** The sentinel approach satisfies all 12 M.2 acceptance criteria and preserves both the YAML missing-vs-empty distinction and the api.py `None`-means-unset contract. It is strictly cleaner than the `tools_unspecified` side-channel: it removes a field from `AgentDefinition`, moves the "unspecified" signal into the `tools` field itself (self-documenting), and eliminates the risk of `tools` and `tools_unspecified` drifting out of sync (e.g. the valid-but-confusing `tools=() + tools_unspecified=True` state).

### Acceptance criteria — each criterion still holds under the sentinel

| # | Criterion | Under `tools_unspecified` | Under `ALL_TOOLS` sentinel | Holds? |
|---|---|---|---|---|
| 1 | Missing `tools` in YAML → all tools | loader sets `tools=() + tools_unspecified=True` | loader sets `tools=ALL_TOOLS` | YES |
| 2 | `tools:` / `null` / `~` / `""` / `[]` → no tools | loader sets `tools=() + tools_unspecified=False` | loader sets `tools=()` | YES |
| 3 | `tools: [read, list]` → filter | loader sets `tools=(...) + tools_unspecified=False` | loader sets `tools=(...)` | YES |
| 4 | In-memory `AgentDefinition()` → all tools | default `tools_unspecified=True` | default `tools=ALL_TOOLS` | YES |
| 5 | `AgentDefinition(tools=None)` / `(tools=[])` → no tools | `__post_init__` normalizes to `()` + flips flag | `__post_init__` normalizes to `()` (sentinel preserved only when `is ALL_TOOLS`) | YES |
| 6 | `AgentDefinition(tools=("yoker:read",))` → filter | non-empty tuple, flag flipped | non-empty tuple, sentinel not set | YES |
| 7 | `config.tools.<name>.enabled=False` drops tool on all-tools grant | branch 1 keeps registry (minus disabled) | branch 1 keeps registry (minus disabled) | YES |
| 8 | WARN `agent_tools_default_granted` on all-tools-by-omission | emitted when `tools_unspecified=True` | emitted when `tools is ALL_TOOLS` | YES |
| 9 | `validate_agent_definition` on runtime path; accepts empty/missing tools | wired in `_validate_definition`; validator no-ops on empty | wired in `_validate_definition`; validator must skip when `tools is ALL_TOOLS` (NEW GUARD — see §4) | YES (with one new guard) |
| 10 | `backwards.md` stays no-tools | `tools: []` → `tools=() + tools_unspecified=False` | `tools: []` → `tools=()` | YES |
| 11 | Docstring/code agreement | docstrings reference `tools_unspecified` | docstrings reference `ALL_TOOLS` sentinel (updated wording) | YES (wording changes) |
| 12 | No regression for explicit-tool filtering / namespace | unchanged filter logic | unchanged filter logic | YES |

### YAML missing-vs-empty distinction — preserved

The loader still uses `"tools" not in frontmatter` (the correct key-presence test). The only change is what it sets when the key is absent:

- **Missing key** → `tools=ALL_TOOLS` (sentinel) — all tools at runtime
- **Present-empty** (`tools:` / `null` / `~` / `""` / `[]`) → `tools=()` — no tools at runtime

The distinction is carried by the `tools` field value itself, not by a side-channel flag. Equally robust.

### api.py `None`-means-unset contract — preserved (but the dual contract remains)

The owner's proposal keeps `AgentDefinition(tools=None)` → no tools (the owner's sketch lists `tools=None` as the "no tools" case). api.py's contract is `yoker.agent(tools=None)` → all tools (`None` means "unset/default" in the Python API surface, consistent with `system_prompt=None`, `skills=None`, `plugins=None`).

Under the sentinel, api.py must still translate `None` → `ALL_TOOLS` when constructing the in-memory `AgentDefinition`:

```python
tools=ALL_TOOLS if tools is None else tuple(tools),
```

This replaces the current `tools_unspecified=tools is None` translation. The dual contract flagged by the api-architect review (opposite `None` semantics at the two layers) is **NOT eliminated** by the owner's proposal — only using `None` itself as the all-tools sentinel (the original plan's `tools: tuple | None = None`) would unify them. But the owner explicitly wants `AgentDefinition(tools=None)` → no tools, so the dual contract stays. This is acceptable: the owner's concern is interface pollution by the extra field, not the api.py dual contract (which the owner did not flag).

---

## 2. Sentinel implementation detail — do NOT use a bare `[]`

The owner sketched `ALL_TOOLS = []` with `is` comparison. A bare `[]` works functionally but has four problems:

| Concern | `ALL_TOOLS = []` | `ALL_TOOLS = object()` | Dedicated sentinel class |
|---|---|---|---|
| **Type annotation** | `tools: list = ALL_TOOLS` — but canonical runtime type is `tuple`; mypy sees `list` default vs `tuple[str, ...]` field type → mismatch | `tools: tuple[str, ...] \| object = ALL_TOOLS` — `object` is too broad; mypy can't distinguish sentinel from any other object | `tools: tuple[str, ...] \| _AllToolsSentinel = ALL_TOOLS` — precise, mypy-friendly |
| **Pickling** | `pickle.dumps([])` → `pickle.loads(...)` returns a NEW `[]` → `is ALL_TOOLS` becomes False; breaks if `AgentDefinition` is ever pickled/cached | Same problem — `object()` doesn't round-trip | Can be made to round-trip via `__reduce__` returning a singleton accessor |
| **Equality footgun** | `[] == []` is True — a careless `tools == ALL_TOOLS` (instead of `is`) silently matches ANY empty list, conflating "no tools" with "all tools" | `object() == object()` is False — `==` and `is` agree; no footgun | Same as `object()` — no footgun |
| **Repr / debugging** | `repr(ALL_TOOLS)` → `[]` — ambiguous in tracebacks (looks like "no tools") | `repr(ALL_TOOLS)` → `<object object at 0x...>` — unhelpful | `repr(ALL_TOOLS)` → `ALL_TOOLS` — self-documenting |

**Recommendation: a dedicated sentinel class.** It is the only option that is simultaneously mypy-precise, pickle-safe (via `__reduce__`), equality-safe, and self-documenting in tracebacks. The extra 5 lines are worth the robustness.

### Proposed sentinel

```python
# src/yoker/agents/schema.py

class _AllToolsSentinel:
  """Sentinel meaning "all config-enabled tools" — the default when no
  ``tools`` value is specified. Distinct from ``None`` / ``()`` (no tools)
  and from a non-empty tuple (filter). Check with ``is ALL_TOOLS``.
  """
  __slots__ = ()

  def __repr__(self) -> str:
    return "ALL_TOOLS"

  def __reduce__(self):
    # Pickle support: round-trip back to the singleton.
    return (_resolve_all_tools, ())

  def __bool__(self) -> bool:
    # Not empty — so __post_init__'s len-based branch does not fire on it.
    # (The is-ALL_TOOLS guard runs first anyway, but this prevents surprises
    # if someone writes `if self.tools:`.)
    return True


def _resolve_all_tools() -> "_AllToolsSentinel":
  return ALL_TOOLS


ALL_TOOLS: _AllToolsSentinel = _AllToolsSentinel()
```

The `__bool__` guard is defensive: `__post_init__` checks `is ALL_TOOLS` first, but if any code does `if self.tools:` the sentinel should not be falsy (it represents "all tools", not "no tools").

### Why not `None` as the sentinel (the original plan / api-architect's preference)?

Using `None` as the all-tools sentinel would **also** eliminate the api.py dual contract (`yoker.agent(tools=None)` and `AgentDefinition(tools=None)` would both mean "all tools"). The api-architect review flagged this as the "preferred" refactor. However:

- The owner **explicitly** sketched `tools=None` as the "no tools" case (not the "all tools" case).
- The owner's stated criterion 5 (`AgentDefinition(tools=None)` → no tools) is the **opposite** of the `None`-as-all-tools sentinel.
- Switching to `None`-as-all-tools would change the `AgentDefinition` contract: `AgentDefinition(tools=None)` would flip from "no tools" to "all tools". That is a different semantic from what the owner proposed.

The owner's proposal (`ALL_TOOLS` sentinel, `None` = no tools) and the api-architect's preference (`None` = all tools) are **two different refactors**. This document analyses the owner's proposal. If the owner wants to additionally align with the api-architect's preference, that is a separate decision — but it would require re-evaluating acceptance criterion 5 (which currently expects `AgentDefinition(tools=None)` → no tools).

---

## 3. Does `tools_unspecified` have ANY advantage over the sentinel?

**No.** The security-engineer's original concern (distinguishing missing-vs-empty in YAML) is handled **equally well** by the sentinel:

| Scenario | `tools_unspecified` | `ALL_TOOLS` sentinel |
|---|---|---|
| YAML `tools:` absent | `tools=() + tools_unspecified=True` | `tools=ALL_TOOLS` |
| YAML `tools: []` present | `tools=() + tools_unspecified=False` | `tools=()` |
| `AgentDefinition()` default | `tools=() + tools_unspecified=True` | `tools=ALL_TOOLS` |
| `AgentDefinition(tools=None)` | `tools=() + tools_unspecified=False` | `tools=()` |

The sentinel has **strictly fewer** states to get wrong:

- Under `tools_unspecified`, the pair `(tools, tools_unspecified)` has 4 reachable combinations but only 3 are meaningful. The invalid combination `tools=("read",) + tools_unspecified=True` is constructible (a caller could pass it explicitly) and would produce surprising behavior (the runtime checks `tools_unspecified` first, so the explicit tool list is ignored and all tools are granted).
- Under the sentinel, `tools` is a single field with exactly 3 reachable states: `ALL_TOOLS`, `()`, non-empty tuple. There is no way to express the invalid combination.

### Edge cases the sentinel handles

- **`AgentDefinition(tools=ALL_TOOLS)` explicit**: equivalent to default — all tools. No drift.
- **`AgentDefinition(tools=())` explicit empty**: no tools. The sentinel is not set, so branch 2 fires. Same as `tools=[]` and `tools=None` after normalization.
- **Pickle round-trip**: handled by `__reduce__` on the sentinel class.
- **`repr` in tracebacks**: `ALL_TOOLS` is self-documenting.

### Edge case the sentinel introduces (NOT present under `tools_unspecified`)

**The sentinel is not iterable.** Two call sites currently iterate over `self.definition.tools`:

1. `core/__init__.py:383` — `_warn_missing_tools`: `for requested in self.definition.tools:`
2. `agents/validator.py:62` — `validate_tools`: `for tool in tools:`

Under `tools_unspecified`, when `tools_unspecified=True`, `self.definition.tools == ()` (an empty tuple, iterable, zero iterations). Under the sentinel, `self.definition.tools is ALL_TOOLS` (a non-iterable object). Both call sites would raise `TypeError: 'object' object is not iterable` if not guarded.

**This is the one new edge case the sentinel introduces.** It requires two new guards (see §4). These guards are semantically correct: when `tools is ALL_TOOLS`, there are no "requested" tools to validate or warn about — all tools are granted by default, so `_warn_missing_tools` and `validate_tools` should skip. The guards are a one-line `if ... is ALL_TOOLS: return` early-exit in each function.

---

## 4. Concrete change description

### `src/yoker/agents/schema.py`

1. **Add the sentinel class and `ALL_TOOLS` singleton** at module top (after imports, before `AgentDefinition`):
   - `_AllToolsSentinel` class with `__slots__ = ()`, `__repr__` → `"ALL_TOOLS"`, `__reduce__` for pickle, `__bool__` → `True`.
   - `ALL_TOOLS: _AllToolsSentinel = _AllToolsSentinel()`.
   - Export `ALL_TOOLS` in `__all__`.

2. **Remove the `tools_unspecified` field** from `AgentDefinition` (line 46).

3. **Change the `tools` field default** from `()` to `ALL_TOOLS`:
   ```python
   tools: tuple[str, ...] | _AllToolsSentinel = ALL_TOOLS
   ```

4. **Rewrite `__post_init__`** to handle the sentinel:
   ```python
   def __post_init__(self) -> None:
     if self.tools is ALL_TOOLS:
       return  # sentinel preserved — all tools at runtime
     if self.tools is None:
       self.tools = ()
     elif isinstance(self.tools, list):
       self.tools = tuple(self.tools)
     # else: already a tuple (empty → no tools; non-empty → filter)
   ```
   Remove all `self.tools_unspecified = ...` lines.

5. **Update the class docstring** (lines 20-31): remove the `tools_unspecified` attribute description; document the three `tools` states (`ALL_TOOLS` → all; `()` → none; non-empty → filter). Note that `None` and `[]` normalize to `()`.

6. **Update the field comment** (lines 36-42): describe the three-state `tools` field.

### `src/yoker/agents/loader.py`

1. **Update the `tools` extraction block** (lines 109-140):
   - Import `ALL_TOOLS` from `yoker.agents.schema`.
   - When `"tools" not in frontmatter`: set `tools = ALL_TOOLS` (instead of `tools = ()` + `tools_unspecified = True`).
   - When present-empty (`None` / `""` / `[]`): set `tools = ()` (no `tools_unspecified` to set).
   - When non-empty list/string: set `tools = tuple(...)` (no `tools_unspecified` to set).
   - The `agent_tools_explicit_null_treated_as_empty` warning for bare-null forms is preserved (it warns about `tools:` / `null` / `~` being treated as empty, which is still correct).

2. **Remove the `tools_unspecified=tools_unspecified` kwarg** from the `AgentDefinition(...)` constructor call (line 176).

3. **Update the inline comment** (lines 109-113): describe the sentinel approach (missing key → `ALL_TOOLS`; present-empty → `()`).

4. **Namespace application**: `_namespace_tools` is called on `tools` before constructing `AgentDefinition`. When `tools is ALL_TOOLS`, `_namespace_tools` must NOT be called (it expects a list/tuple). Add a guard:
   ```python
   if tools is not ALL_TOOLS:
     tools = tuple(_namespace_tools(tools, namespace))
   ```
   This is a **third new guard** beyond the two in §3 (the sentinel is not a sequence, so `_namespace_tools`'s `[str(t) for t in tools]` would fail).

### `src/yoker/core/__init__.py`

1. **Import `ALL_TOOLS`** from `yoker.agents.schema`.

2. **`_filter_tools_by_definition`** (lines 416-471):
   - Change branch 1 from `if self.definition.tools_unspecified:` to `if self.definition.tools is ALL_TOOLS:`.
   - Branch 2 (`len(tools) == 0`) and branch 3 (filter) are unchanged.
   - Update the docstring (lines 419-430): replace `tools_unspecified=True`/`=False` wording with `tools is ALL_TOOLS` / `tools == ()` wording.

3. **`_warn_missing_tools`** (line 373-398): **add a new early-return guard**:
   ```python
   def _warn_missing_tools(self) -> None:
     if self.definition.tools is ALL_TOOLS:
       return  # all tools granted by default — nothing to check
     ...
   ```
   This is required because the sentinel is not iterable. Without it, `for requested in self.definition.tools:` would raise `TypeError`.

4. **`_validate_definition`** (lines 400-414): no change needed here — the guard goes in `validate_agent_definition` (see below). Alternatively, the guard could go here:
   ```python
   if self.definition.tools is not ALL_TOOLS:
     warnings = validate_agent_definition(...)
   ```
   Either location works; guarding in `validate_agent_definition` is cleaner (the validator owns the "what to validate" decision).

### `src/yoker/agents/validator.py`

1. **`validate_agent_definition`** (line 102): **add a guard** before calling `validate_tools`:
   ```python
   if definition.tools is not ALL_TOOLS:
     warnings.extend(validate_tools(definition.tools, tools_config, "agent.tools"))
   ```
   When `tools is ALL_TOOLS`, there is nothing to validate (all tools are granted; no explicit list to check for typos/disabled). Skip.

2. **Update the comment** (lines 99-101): replace `tools_unspecified` wording with `ALL_TOOLS` sentinel wording.

3. **`validate_tools` signature** (`tools: tuple[str, ...]`): unchanged — it only ever receives a tuple now (the sentinel is filtered out by the caller).

### `src/yoker/api.py`

1. **Import `ALL_TOOLS`** from `yoker.agents.schema`.

2. **`_build_config_and_definition`** (lines 132-144): replace the `tools_unspecified=tools is None` translation with the sentinel:
   ```python
   if system_prompt is not None or tools is not None:
     resolved_definition = AgentDefinition(
       simple_name="custom" if tools is not None else None,
       system_prompt=system_prompt if system_prompt is not None else "You are a helpful assistant.",
       tools=ALL_TOOLS if tools is None else tuple(tools),
     )
   ```
   Remove the `tools_unspecified=tools is None` kwarg. The `tools=tuple(tools) if tools is not None else ()` line becomes `tools=ALL_TOOLS if tools is None else tuple(tools)` — when `tools is None` (unset), pass `ALL_TOOLS` (all tools); when `tools` is a list (including `[]`), pass `tuple(tools)` (no tools or filter).

3. **Update the inline comment** (lines 133-135): replace `tools_unspecified=False` wording with `ALL_TOOLS` sentinel wording.

### Tests

1. **`tests/core/test_agent_tools.py`** — the primary M.2 test file:
   - Replace every `assert d.tools_unspecified is True` with `assert d.tools is ALL_TOOLS`.
   - Replace every `assert d.tools_unspecified is False` with `assert d.tools is not ALL_TOOLS` (or, more precisely, `assert d.tools == ()` for the empty cases and `assert d.tools == (...)` for the filter cases — the `is not ALL_TOOLS` check is redundant when `tools == ()` is also asserted).
   - `TestInMemoryAgentDefinition.test_explicit_empty_disables_tools` (line 72-76): remove the `tools_unspecified` assertion; keep `assert d.tools == ()`.
   - `TestInMemoryAgentDefinition.test_default_constructor_grants_all_tools` (line 65-69): change to `assert d.tools is ALL_TOOLS`.
   - `TestValidatorOnRuntimePath.test_validator_accepts_empty_tools` (line 201-214): remove the `tools=(), tools_unspecified=False` case (the sentinel replaces it); the `tools=()` case (default) becomes `tools=ALL_TOOLS` (default). The three shapes become: (a) default `AgentDefinition()` → `tools is ALL_TOOLS`; (b) `tools=None` → `tools == ()`; (c) `tools=()` explicit → `tools == ()`.
   - `TestDocstringAgreement` (lines 243-265): replace `assert "tools_unspecified=True" in doc` / `"tools_unspecified=False" in doc` with `assert "ALL_TOOLS" in doc` (or the equivalent sentinel wording). Update `test_schema_tools_field_documents_unspecified` to assert the sentinel is documented.
   - `TestBackwardsRegression.test_backwards_md_loads_no_tools` (line 234): replace `assert d.tools_unspecified is False` with `assert d.tools == ()` (or `assert d.tools is not ALL_TOOLS`).
   - Module docstring (lines 5-6): update the description of criteria 1 and 2 to reference `ALL_TOOLS` instead of `tools_unspecified`.

2. **`tests/agents/test_loader.py`** (lines 222-293):
   - Replace `assert definition.tools_unspecified is True` with `assert definition.tools is ALL_TOOLS`.
   - Replace `assert definition.tools_unspecified is False` with `assert definition.tools is not ALL_TOOLS` (or rely on the existing `assert definition.tools == ()`).
   - Update the docstrings of the test methods that reference `tools_unspecified`.

3. **`tests/agents/test_validator.py`** (lines 134-152):
   - Update the comment on line 135-136: replace `tools_unspecified flag decides` with `ALL_TOOLS sentinel decides`.
   - The `definition_all` case (line 137-141): `tools=()` default → now `tools=ALL_TOOLS` default (just `AgentDefinition(simple_name=..., description=...)` without `tools` kwarg, or explicitly `tools=ALL_TOOLS`).
   - The `definition_none` case (line 145-150): `tools=None` → `tools == ()` after normalization. No change to the assertion (`warnings == []`).

4. **`tests/test_agent.py`** (line 470): update the comment — replace `tools_unspecified=True` with `tools is ALL_TOOLS`.

5. **`tests/test_api/test_builder.py`**: the three `TestAgentBuilderTools` tests (`test_tools_whitelist`, `test_tools_empty_disables_all`, `test_tools_none_keeps_all`) should still pass unchanged — they assert runtime behavior (which is identical under the sentinel). No test changes needed here unless they introspect `tools_unspecified` (grep confirms they do not).

### `CHANGELOG.md`

Update the Unreleased entry (lines 11-21):

- Replace the last paragraph (lines 19-21) about `tools_unspecified: bool` side-channel with: "An `ALL_TOOLS` sentinel (module-level singleton in `yoker.agents.schema`) distinguishes 'no `tools` line' (default `ALL_TOOLS` — all tools) from 'tools explicitly empty' (`()` — no tools). Check with `is ALL_TOOLS`."
- The upgrade note (lines 30-33) is unchanged.

### `DEVELOPMENT.md`

Update the M.2 section (lines 11-59):

- Line 13: replace "Option C side-channel `tools_unspecified` flag" with "Option C `ALL_TOOLS` sentinel".
- Lines 18-23 (`agents/schema.py`): describe the `_AllToolsSentinel` class, the `ALL_TOOLS` singleton, the `tools` field default, and the `__post_init__` sentinel guard. Remove the `tools_unspecified` field description.
- Lines 24-29 (`agents/loader.py`): describe setting `tools=ALL_TOOLS` when key absent, `tools=()` when present-empty. Note the `_namespace_tools` guard for the sentinel.
- Lines 34-42 (`core/__init__.py`): describe the three branches as `tools is ALL_TOOLS` → all, `tools == ()` → none, non-empty → filter. Note the new `_warn_missing_tools` guard.
- Lines 43-49 (`api.py`): describe `tools=ALL_TOOLS if tools is None else tuple(tools)` (replaces `tools_unspecified=tools is None`).
- Lines 53-59 (Tests): note the test updates (sentinel assertions replace flag assertions).

### `reporting/m2-default-tools-behavior/functional-review.md` and other review docs

These are historical review documents for round 0. They reference `tools_unspecified` throughout. They should NOT be rewritten (they are a record of the round-0 review). The round-1 review (after the refactor) will document the sentinel approach. Optionally, add a note at the top of `functional-review.md` pointing to this interpretation document and the upcoming round-1 review.

---

## 5. Acceptance criteria impact

The 12 criteria **do not need to change**. Their semantic intent is identical under both implementations. The only textual change is in the evidence/implementation references (criterion 11 docstring agreement now checks for `ALL_TOOLS` instead of `tools_unspecified`).

Two criteria deserve explicit confirmation:

- **Criterion 4** ("In-memory `AgentDefinition()` → all tools"): Still holds. Default `tools=ALL_TOOLS` → branch 1 → all tools.
- **Criterion 5** ("`AgentDefinition(tools=None)` and `AgentDefinition(tools=[])` → no tools"): Still holds. `__post_init__` normalizes both to `()`. The sentinel is preserved only when `tools is ALL_TOOLS` (the default or an explicit `tools=ALL_TOOLS` pass).

One criterion has a subtler wording update (not a semantic change):

- **Criterion 9** ("`validate_agent_definition` on runtime path; accepts empty/missing tools"): The validator now skips `validate_tools` when `tools is ALL_TOOLS` (the guard). The criterion's intent — "empty/missing tools are accepted, no error raised" — still holds. The mechanism changes from "validator sees empty tuple" to "validator skips when sentinel is set".

---

## 6. Summary

**The owner's approach is sound — proceed with the refactor.**

### Key points

1. **The `ALL_TOOLS` sentinel satisfies all 12 acceptance criteria** and preserves both the YAML missing-vs-empty distinction and the api.py `None`-means-unset contract.

2. **Use a dedicated sentinel class, not a bare `[]`.** A bare `[]` has type-annotation, pickling, equality-footgun, and repr problems. A small `_AllToolsSentinel` class with `__repr__`, `__reduce__`, and `__bool__` is the cleanest form (5 extra lines, full robustness).

3. **`tools_unspecified` has NO advantage over the sentinel.** The sentinel is strictly cleaner: fewer fields, fewer states, no drift risk. The security-engineer's missing-vs-empty concern is handled equally well by the loader's `"tools" not in frontmatter` check + sentinel assignment.

4. **Three new guards are required** because the sentinel is not iterable (a bare `object` / sentinel class cannot be looped over):
   - `_warn_missing_tools`: early-return when `tools is ALL_TOOLS`.
   - `validate_agent_definition`: skip `validate_tools` when `tools is ALL_TOOLS`.
   - `_namespace_tools` call site in loader: skip when `tools is ALL_TOOLS`.
   These are semantically correct (all-tools grant has nothing to validate/warn/namespace) and are one-line `if ... is ALL_TOOLS: return` / `if ... is not ALL_TOOLS:` guards.

5. **The api.py dual contract is NOT eliminated** by the owner's proposal. `yoker.agent(tools=None)` → all tools (api.py translates `None` → `ALL_TOOLS`) while `AgentDefinition(tools=None)` → no tools (the owner's explicit choice). This is acceptable — the owner did not flag the dual contract as a concern; the concern was the `tools_unspecified` field pollution. If the owner later wants to also eliminate the dual contract, that would require using `None` itself as the all-tools sentinel (the original plan / api-architect's preference), which would flip acceptance criterion 5.

6. **The 12 acceptance criteria do not change.** Only the evidence/implementation references shift (criterion 11 docstrings now reference `ALL_TOOLS`).

### Files to change (7 source + 4 test + 2 doc + 1 optional review note)

| File | Change |
|---|---|
| `src/yoker/agents/schema.py` | Add `_AllToolsSentinel` + `ALL_TOOLS`; remove `tools_unspecified`; change `tools` default to `ALL_TOOLS`; rewrite `__post_init__`; update docstring. |
| `src/yoker/agents/loader.py` | Set `tools=ALL_TOOLS` when key absent; remove `tools_unspecified` kwarg; guard `_namespace_tools` call; update comments. |
| `src/yoker/agents/validator.py` | Guard `validate_tools` call with `is not ALL_TOOLS`; update comment. |
| `src/yoker/core/__init__.py` | `_filter_tools_by_definition` branch 1 checks `is ALL_TOOLS`; add `_warn_missing_tools` early-return guard; update docstring. |
| `src/yoker/api.py` | Replace `tools_unspecified=tools is None` with `tools=ALL_TOOLS if tools is None else tuple(tools)`; update comment. |
| `tests/core/test_agent_tools.py` | Replace `tools_unspecified` assertions with `is ALL_TOOLS` / `== ()` assertions; update docstring-agreement tests. |
| `tests/agents/test_loader.py` | Replace `tools_unspecified` assertions with sentinel assertions; update test docstrings. |
| `tests/agents/test_validator.py` | Update comments; adjust `definition_all` to use default (sentinel). |
| `tests/test_agent.py` | Update one comment (line 470). |
| `CHANGELOG.md` | Replace `tools_unspecified` paragraph with `ALL_TOOLS` sentinel description. |
| `DEVELOPMENT.md` | Rewrite M.2 section to describe sentinel approach. |
| `reporting/m2-default-tools-behavior/functional-review.md` | Optional: add a pointer to this interpretation (do NOT rewrite the historical review). |

### Estimate

This is a mechanical refactor: ~50 lines of source changes, ~30 lines of test assertion swaps, ~20 lines of doc updates. The three new guards are the only non-obvious additions. No semantic change to any acceptance criterion. The test suite should pass unchanged in behavior (1889+ tests, all green) after the assertion swaps.