# API Architecture Review: M.2 Default Tools Behavior

**Date**: 2026-07-20
**Reviewer**: API Architect Agent
**Task**: M.2 Default Tools Behavior — architecture review only (no implementation)
**Related**: `TODO.md` (M.2 entry), `PLAN.md` item 1, `analysis/mbi-toolset-coverage.md`

## Summary

The functional-analyst's proposed implementation approach is **architecturally sound and approved with minor refinements**. The four-file change (loader, core, validator, schema) correctly removes the artificial asymmetry between the default in-memory `AgentDefinition()` (keeps all tools) and a named agent with no `tools:` field (currently rejected or clears the registry).

The only design question of substance is **"empty means all" vs. an explicit sentinel** (`tools: "*"`, `tools: all`, `tools: none`). Recommendation: **keep "empty means all"** — it preserves symmetry with the default `AgentDefinition()` behavior, requires no new syntax, and the "author forgot" risk is mitigated by a log line at agent init. A sentinel would add parser/validator surface area for marginal explicitness gain.

## Findings

### 1. Review of the Proposed Implementation Approach

**Proposed changes (from functional-analyst):**

| File | Change | Verdict |
|------|--------|---------|
| `src/yoker/agents/loader.py:110-116` | Drop strict-mode `ConfigurationError` when `tools_raw is None`; treat missing as `tools_raw = []` | **Approved** |
| `src/yoker/core/__init__.py:394-443` | Replace the `len(self.definition.tools) == 0` branch (which clears all tools) with a no-op "keep all tools" branch | **Approved with refinement** (see 1.1) |
| `src/yoker/agents/validator.py:92-93` | Remove the `if not definition.tools: raise ValidationError(...)` guard | **Approved** |
| `src/yoker/agents/schema.py` | Clarify `AgentDefinition.tools` field docstring that `()` means "all available tools" | **Approved** |

**1.1 Refinement on the core change.** The current `len(self.definition.tools) == 0` branch calls `self.tools.clear()` and logs `agent_tools_empty`. The proposed no-op is correct, but:

- The early-return guard at `core/__init__.py:401-402` (default agent: `simple_name is None and namespace is None`) becomes **redundant** once the empty-tuple branch also becomes a no-op. Both branches now do the same thing (keep all tools). Recommendation: **collapse the two branches** into a single early return:

  ```python
  def _filter_tools_by_definition(self) -> None:
    # No explicit tools → keep all registered tools (default behavior).
    # This covers both the default in-memory AgentDefinition() and any
    # named agent whose `tools:` field is missing or empty.
    if len(self.definition.tools) == 0:
      logger.info("agent_tools_default_all", agent=self.definition.name)
      return
    # ...existing explicit-filter logic...
  ```

  This removes the special-case for "default agent" and makes the semantic uniform: **empty `tools` tuple → all tools**, regardless of how the agent was constructed. The `simple_name`/`namespace` check was only ever a proxy for "is this the default agent with `tools=()`", so once `tools=()` uniformly means "all", the proxy is no longer needed.

- Use `logger.info` (not `debug`) for the "all tools" branch so authors see it in default logs and can catch accidental omissions. This is the "author forgot" mitigation (see section 2).

**1.2 Validator removal is safe.** `validate_agent_definition` is called from `yoker/agents/validator.py` and indirectly via the loader's strict path. Removing the `if not definition.tools: raise ValidationError(...)` guard allows empty tools through. The subsequent `validate_tools(definition.tools, ...)` call iterates the empty tuple — no-op, no warnings. Safe.

**1.3 Loader change is safe but note the symmetry break.** Currently strict mode rejects *missing* `tools:` but accepts *empty* `tools: ""` / `tools: []` (lines 121-124 produce an empty tuple, then line 133 comment says "Empty tools list is valid"). After removing the missing-field rejection, both missing and empty produce `tools = ()`. Consistent. Good.

### 2. API Design: "Empty Means All" vs. Sentinel

**Recommendation: keep "empty means all". Do not introduce a sentinel.**

**Arguments for "empty means all" (winner):**

1. **Symmetry with default `AgentDefinition()`.** The dataclass default `tools: tuple[str, ...] = ()` already produces "all tools" behavior for the default agent. A named agent with no `tools:` field should behave the same way — the field's default value should mean the same thing in both contexts. The current behavior is the inconsistency; M.2 fixes it.

2. **Least surprise for minimal agent definitions.** Yoker's agent definitions are intentionally minimal Markdown+frontmatter. Forcing authors to write `tools: "*"` or `tools: all` on every "general-purpose" agent adds friction for the common case.

3. **No new syntax to parse, validate, document.** A sentinel introduces a new token that the loader must accept, the validator must special-case (skip the "known tool" check), the schema must document, and the `_filter_tools_by_definition` must handle. Each is a small surface, but they add up. "Empty means all" needs none of this.

4. **Consistent with `agents:` field's convention** that "missing/empty = default behavior" (though the defaults differ: `agents=()` means "no spawns", `tools=()` means "all tools" — see section 4).

**Arguments for a sentinel (rejected):**

1. "Author forgot vs. author wants all" — **mitigated by the `logger.info("agent_tools_default_all", ...)` line.** Authors running `yoker` will see the agent got all tools and can add explicit `tools:` if the omission was accidental. A sentinel would force authors to be explicit, but the cost (friction + syntax surface) outweighs the benefit for Yoker's minimal-definition philosophy.

2. "Self-documenting" — **the schema docstring update covers this.** The frontmatter convention is documented in one place; authors who read the docs know `tools:` is optional and defaults to all.

**If a sentinel is later demanded by users**, add `tools: "*"` as an opt-in alias for "all" (parsed to `()` early in the loader), **not** as a replacement for the empty-means-all default. This keeps the door open without introducing it now.

### 3. Namespace Handling in `_filter_tools_by_definition`

**The filtering logic is namespace-aware for the explicit-list case, and the "all tools" case is namespace-agnostic by construction.**

- **Explicit list** (`core/__init__.py:414-423`): bare names like `read` get both `read` and `yoker:read` added to the requested set; namespaced names like `pkg:write` are matched as-is. Correct.
- **Empty tuple** (proposed): no-op, keeps everything in `self.tools`. No namespace matching needed — everything is kept. Correct.
- **`_warn_missing_tools`** (`core/__init__.py:367-392`): iterates `self.definition.tools`. When empty, the loop body doesn't execute — no false "missing tools" warnings. Correct.

**No namespace-handling changes needed for M.2.**

### 4. Interaction with `Session.create_primary_agent`, `yoker/cli/run.py`, and Plugin Agent Definitions

**4.1 `Session.create_primary_agent`.** Resolves the definition, constructs an `Agent`. The `Agent.__init__` calls `_filter_tools_by_definition` at line 112. With M.2:
- Primary agent with no `tools:` field → all session-loaded tools kept. **Desired.**
- Primary agent with explicit `tools:` → filtered as today. **Unchanged.**
- Child agents spawned via `_spawn_internal` → each gets a fresh `ToolRegistry` populated from plugins, then filtered. Empty `tools` → all tools. **Consistent.**

**4.2 `yoker/cli/run.py:166-170`.** Source plugin tools are registered onto the primary agent **after** construction:

```python
if loaded.components.tools:
  session.agent.tools.register_plugin_tools([loaded.components], config)
```

This is a **pre-existing ordering subtlety**, not introduced by M.2:
- With M.2 + empty `tools`: primary agent keeps all tools at init, then source tools are added. **All tools present. Correct.**
- With explicit `tools`: primary agent filters at init (source tools not yet registered, so not in the filter's "available" set), then source tools are added unfiltered. **Source tools bypass the agent's tool list.** This is the existing behavior and is arguably intentional (source tools are explicitly registered by the source itself). M.2 does not change this.

**No new surprise from M.2.** Worth noting in the analysis as a pre-existing interaction, but out of scope for M.2.

**4.3 Plugin agent definitions.** Plugin agents are loaded via `register_configured_plugin_agents` into the session's `AgentRegistry`. Their `tools` field is namespaced by `_namespace_tools` (loader.py:44-62). An empty `tools` tuple passes through `_namespace_tools` unchanged (returns `[]`), then `tuple([])` = `()`. With M.2, a plugin agent with no `tools:` field gets all tools. **Consistent with built-in agents.**

**One caveat:** plugin agents' tools, when explicit, are namespaced to the plugin's namespace (`write` → `pkg:write`). The "all tools" semantic means a plugin agent with no `tools:` field gets **all** registered tools (yoker built-ins + other plugins' tools + its own plugin's tools), not just its own plugin's tools. This is the correct generalization of "all tools" and matches the default-agent behavior. If a plugin author wants only their plugin's tools, they list them explicitly. **Document this in the schema docstring.**

### 5. ToolsConfig Per-Tool `enabled` Gating

**Yes, `ToolsConfig` per-tool `enabled` gating must still apply on top of "all tools".** The current layered model is correct and M.2 preserves it:

1. **Plugin load** (`plugins/loader.py`): global-enabled and security/trust gating.
2. **`ToolRegistry.register_plugin_tools`** (`tools/registry.py:138-154`): calls `_filter_enabled_tools` for `yoker`-namespace tools, dropping any whose `config.tools.<name>.enabled` is `False` (and dropping `websearch`/`webfetch` when no backend API key is set).
3. **`Agent._filter_tools_by_definition`** (M.2 target): agent-level filter.

With M.2, step 3 becomes a no-op when `tools=()`, but **steps 1 and 2 still run**. So "all tools" means "all tools that survived config-level gating" — a disabled tool is not in the "all" set. This is the correct semantic: `config.tools.read.enabled = False` should disable `read` regardless of whether the agent requested it explicitly or got it via "all".

**Acceptance criterion to add:** "When `tools=` is empty/missing, the agent receives all config-enabled tools; tools disabled via `config.tools.<name>.enabled = False` are NOT present."

### 6. Backward Compatibility

**Low risk.** Analysis:

| Existing agent definition shape | Before M.2 | After M.2 | Risk |
|-------------------------------|------------|-----------|------|
| `tools: [explicit list]` | Filtered to list | Filtered to list | None |
| `tools: ""` or `tools: []` | **Rejected by validator** (`must specify at least one tool`) → never reached runtime | All tools | None — was rejected, now accepted |
| `tools:` missing | **Rejected by loader** in strict mode (`Required field 'tools' is missing or empty`) → never reached runtime | All tools | None — was rejected, now accepted |
| No frontmatter / default `AgentDefinition()` | All tools (in-memory path) | All tools (collapsed branch) | None — same behavior, simpler code |

**Key insight:** because the validator and loader currently *reject* empty/missing tools, **no valid agent definition file in the wild can have empty or missing tools**. M.2 strictly *enables a previously-rejected state*; it does not change the behavior of any currently-valid definition. This makes the backward-compat risk effectively zero.

**One soft consideration:** authors who previously worked around the rejection by listing `tools: [read, write, ...]` explicitly on general-purpose agents may want to simplify their definitions to omit `tools:`. This is a documentation/migration note, not a compat risk. Optionally mention in CHANGELOG.

### 7. Schema Asymmetry: `tools` vs. `agents`

The `AgentDefinition` has two list fields with **opposite empty-tuple semantics**:

| Field | Empty tuple meaning | Rationale |
|-------|---------------------|-----------|
| `tools` | **All available tools** (M.2) | Tools are *capabilities* — default = capable of everything the system offers |
| `agents` | **No spawns allowed** | Agents are *permissions* — default = no extra permissions granted (least privilege) |

This asymmetry is **justified by the security model** (capabilities default open, permissions default closed) but should be **explicitly documented** in the schema docstrings to avoid confusion. The `agents` field already has a comment (`schema.py:31-34`); the `tools` field's docstring update (M.2 task) should mirror it and call out the asymmetry.

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Author accidentally omits `tools:` and agent gets more tools than intended | Low | `logger.info("agent_tools_default_all", agent=...)` at init; authors see it in default logs |
| Plugin agent with no `tools:` gets other plugins' tools (unexpected reach) | Low | Document in schema docstring: "all tools" = all registered, config-enabled tools across all plugins. Author can list explicitly to scope. |
| `_warn_missing_tools` produces false warnings on empty `tools` | None | Loop iterates empty tuple — no-op. Verified. |
| Backward-compat break for existing definitions | None | Validator/loader currently reject empty/missing tools; no valid definition is affected |
| `yoker run` source-tools-after-init ordering (pre-existing) | None (pre-existing) | Out of scope for M.2; noted in section 4.2 |
| Tests that asserted `ValidationError` on empty tools now fail | Low (test-only) | Update tests to assert acceptance instead of rejection |

## Recommended Acceptance Criteria Refinements

Add to the M.2 acceptance criteria:

1. **Config gating preserved.** "All tools" = all tools that survived `ToolsConfig` per-tool `enabled` gating and plugin-load security gating. A tool disabled via `config.tools.<name>.enabled = False` is NOT in the "all" set, even when `tools=` is empty/missing.
2. **Logged for discoverability.** When the "all tools" branch is taken, emit `logger.info("agent_tools_default_all", agent=...)` so authors can detect accidental omissions in default log output.
3. **Uniform semantic.** The "all tools" behavior applies identically to: (a) default in-memory `AgentDefinition()`, (b) named agent with missing `tools:` field, (c) named agent with `tools: ""` or `tools: []`, (d) plugin agent with missing/empty `tools`. The `simple_name`/`namespace` special-case in `_filter_tools_by_definition` is collapsed — no proxy check, just `len(tools) == 0 → keep all`.
4. **Schema docstring documents the asymmetry.** `AgentDefinition.tools` docstring states "empty tuple means all available tools (default)" and cross-references `AgentDefinition.agents` where empty means "no spawns".

## Recommended File List Refinements

The functional-analyst's four-file list is correct. Refinements:

| File | Change |
|------|--------|
| `src/yoker/agents/loader.py` | Drop strict-mode rejection of missing `tools:` (lines 111-116). Treat missing as `[]`. |
| `src/yoker/core/__init__.py` | In `_filter_tools_by_definition` (lines 394-443): collapse the default-agent guard (401-402) and the empty-tools branch (405-412) into a single `if len(self.definition.tools) == 0: logger.info("agent_tools_default_all", ...); return`. Keep the explicit-filter logic as-is. |
| `src/yoker/agents/validator.py` | Remove the `if not definition.tools: raise ValidationError(...)` guard (lines 92-93). |
| `src/yoker/agents/schema.py` | Update `tools` field docstring (line 20) to state empty = all available tools; cross-reference `agents` field's opposite convention. |
| `tests/agents/test_loader.py` (extend) | Add: missing `tools:` field loads successfully; empty `tools: ""` and `tools: []` load successfully. |
| `tests/agents/test_validator.py` (extend) | Add: empty `tools` tuple passes validation (no `ValidationError`). |
| `tests/core/test_agent_tools.py` (new or extend) | Add: named agent with `tools=()` has all registered tools; named agent with `tools=()` and a config-disabled tool does NOT have the disabled tool. |

## Action Items

- [ ] Implement M.2 per the refined approach above (out of scope for this review — design only)
- [ ] After implementation, run `make check` and verify the test additions pass
- [ ] Update `CLAUDE.md` "Current State" section to note the M.2 semantic change (empty `tools` = all tools)
- [ ] Consider a CHANGELOG entry noting the new acceptance of missing/empty `tools:` field

## Conclusion

**Approved for implementation** with the refinements above. The proposed approach is architecturally consistent, has effectively zero backward-compatibility risk (because the previously-rejected state was never reachable in valid definitions), and preserves the layered config-gating model. The "empty means all" semantic is the right call over a sentinel; the `logger.info` mitigation addresses the "author forgot" concern without adding syntax surface.

---

## Option C Evaluation (Owner Proposal)

**Date**: 2026-07-20
**Trigger**: PR #47 owner comment — proposed a third option neither reviewer had framed. Owner asked both reviewers to check for oversights.

**Owner's proposal**:

1. Default all tools: `AgentDefinition()` (no `tools` field at all) → all tools.
2. Explicit no tools: `AgentDefinition(tools=None)` or `AgentDefinition(tools=[])` → no tools.

This **distinguishes missing field (→ all tools) from explicit empty (→ no tools)**. My Option A collapsed both into "all tools"; the security-engineer's Option B used a sentinel `tools: "*"` for "all" and empty for "no tools". Option C uses **field absence** as the "all" signal.

### C.1 Is Option C covered by Option A, or genuinely new?

**Genuinely new.** Option A has two semantic states: empty/missing → all tools; explicit non-empty list → filtered. Option C has three: missing → all tools; explicit empty → no tools; explicit non-empty list → filtered. The third state (explicit empty = no tools) is a capability neither A nor today's behavior exposes cleanly. It is closer to the security-engineer's Option B in the "explicit empty = no tools" branch, but differs in how "all tools" is signalled: B requires an opt-in sentinel (`tools: "*"`), C uses field absence.

### C.2 Architectural soundness

**Sound, and arguably a cleaner fix for the asymmetry than Option A.**

The original asymmetry M.2 set out to fix is: `AgentDefinition()` (default `tools=()`) keeps all tools, but a named agent with `tools=()` (via `tools: []` frontmatter) clears all tools. The current code distinguishes these two cases only via a proxy check (`simple_name is None and namespace is None` at `core/__init__.py:401-402`). Both states produce the **same field value** (`tools=()`); the proxy is the only thing separating them.

- **Option A "fixes" the asymmetry by collapsing the two states**: both `tools=()` cases mean "all tools". This removes the "no tools" capability entirely. Authors can no longer express a tool-less agent at all — a real loss.
- **Option C fixes the asymmetry by making the states distinguishable in the data model itself**: `tools=None` (field absent) means "all tools"; `tools=()` (field present, empty) means "no tools". The proxy check is no longer needed because the field value carries the author's intent natively.

Option C is the more principled fix: the bug was never "empty means different things in different contexts" — it was "two different intents (all vs. none) were encoded as the same value, forcing a proxy check." Option C gives each intent its own value. The symmetry argument I made earlier is **weakened but replaced by a stronger one**: instead of "empty should mean the same thing everywhere" (Option A), Option C argues "absent = inherit default, present = author intent" — which is the standard Python dataclass convention and a clearer principle than "empty means all."

The `AgentDefinition()` default behavior is preserved: the dataclass default for `tools` becomes `None` (not `()`), so `AgentDefinition()` → `tools=None` → all tools. Identical to today.

### C.3 Loader/schema feasibility

**Feasible, with two concrete implementation requirements the functional-analyst must follow.**

**Requirement 1: dataclass field type changes to `tuple[str, ...] | None` with default `None`.**

```python
# schema.py
tools: tuple[str, ...] | None = None
```

`None` is the "all tools" sentinel; `()` is the "no tools" value; a non-empty tuple is the explicit filter. Python dataclasses distinguish `None` from `()` natively — no proxy check needed. This is the load-bearing change.

**Requirement 2: loader must distinguish key-absence from key-present-but-null, using `in` rather than `.get()`.**

This is the critical feasibility question. Today `parse_agent_definition` uses `frontmatter.get("tools")`, which returns `None` for both "key absent" and "key present with YAML null value" (e.g. `tools:` with nothing after the colon, or `tools: null`). These are indistinguishable via `.get()`. Under Option C they must diverge:

- `"tools" not in frontmatter` (key absent) → `tools = None` (all tools)
- `"tools" in frontmatter` (key present) with value `None`/`""`/`[]` → `tools = ()` (no tools)
- `"tools" in frontmatter` with a string or list → parse as today

This is detectable via `"tools" in frontmatter` (membership test) rather than `frontmatter.get("tools")`. The loader branch becomes:

```python
if "tools" not in frontmatter:
    tools: tuple[str, ...] | None = None
else:
    tools_raw = frontmatter["tools"]
    if tools_raw is None:  # `tools:` or `tools: null`
        tools = ()
    elif isinstance(tools_raw, str):
        tools = tuple(t.strip() for t in tools_raw.split(",") if t.strip())
    elif isinstance(tools_raw, list):
        tools = tuple(str(t).strip() for t in tools_raw if t)
    else:
        # strict-mode error
        ...
```

**YAML-null footgun.** `tools:` (bare key, nothing after) is YAML null → `tools_raw is None` → "no tools" under Option C. An author who writes `tools:` thinking "no value = default = all tools" would get **no tools** — the opposite of their intent. This is a real footgun that neither Option A nor Option B has.

**Mitigation:** emit a `logger.warning("agent_tools_explicit_null_treated_as_empty", ...)` when `"tools" in frontmatter and tools_raw is None`, suggesting the author either omit the field entirely (for all tools) or write `tools: []` explicitly (for no tools). Document the convention in the schema docstring. The warning makes the footgun discoverable.

**In-memory construction is clean.** `AgentDefinition()` → `tools=None` (all tools). `AgentDefinition(tools=())` → `tools=()` (no tools). `AgentDefinition(tools=("read",))` → filtered. The `None`-vs-`()` distinction is native to Python and needs no special accessor — `self.definition.tools is None` vs `len(self.definition.tools) == 0`.

### C.4 Oversights

**Oversight 1 (mine, significant): `backwards.md` regresses under Option A.**

My original analysis (section 6) claimed "no valid agent definition file in the wild can have empty or missing tools" because the validator rejects empty tools. **This was wrong.** `validate_agent_definition` is **not on the production load path** — only `parse_agent_definition` is, and it accepts `tools: []` (producing `tools=()`). `backwards.md` ships with `tools: []` and today is a no-tools agent in production: `parse_agent_definition` accepts it, then `_filter_tools_by_definition` clears all tools via the `len == 0` branch.

| Definition | Today | Option A | Option C |
|------------|------|----------|---------|
| `examples/.../backwards.md` (`tools: []`) | No tools (via clear branch) | **All tools (regression!)** | No tools (no regression) |

This is a **concrete, shipped counterexample** to my Option A backward-compat claim. Option C is strictly safer here. **Option A would silently turn a no-tools demo agent into an all-tools agent — a behavior change I failed to flag.**

**Oversight 2 (shared): the validator is not on the load path.** Neither reviewer noted that `validate_agent_definition` is dead code in production — it is only invoked from tests, docs, and (optionally) by user code. The "remove the `if not definition.tools` guard" recommendation in my original analysis (and the functional-analyst's) is therefore **less impactful than implied**: removing it changes no production behavior, only unblocks users who call `validate_agent_definition` directly. The real production gate is `parse_agent_definition`'s strict-mode `tools_raw is None` rejection, which is what must change under any of the three options.

**Oversight 3 (new, flagged by Option C): the plugin privilege-expansion risk is unchanged from Option A.** Under Option C, a plugin agent shipped without a `tools:` field gets **all tools** — including other plugins' tools and all yoker built-ins. This is the same risk the security-engineer flagged for Option A. Option C does **not** mitigate it; it only adds the "no tools" capability that A lacked. The mitigation remains the `logger.info` line at agent init, plus documentation. A stricter variant — plugin agents default to "no tools" unless they explicitly opt in — was not requested by the owner and would add namespace-dependent semantics (worth raising with the owner, but not blocking).

**Oversight 4: `tools: ""` (empty string) is now a "no tools" expression.** Today `tools: ""` produces `tools=()` and clears all tools (via the `len == 0` branch). Under Option C it produces `tools=()` and means "no tools". Under Option A it would have meant "all tools". Same regression pattern as `backwards.md`. Option C preserves the today-behavior for `tools: ""` too.

**Oversight 5: the YAML-null footgun (C.3 above).** Neither Option A nor Option B has this; Option C introduces it. The `logger.warning` mitigation handles it but is a new code path the implementation must include.

### C.5 Revised recommendation

**Endorse Option C** over my original Option A and the security-engineer's Option B.

Reasoning, in priority order:

1. **Option A regresses `backwards.md`** (and any `tools: ""`/`tools: []` definition in the wild). My original "effectively zero backward-compat risk" claim was wrong because I incorrectly assumed the validator was on the load path. Option C has **no regression** for any shipped definition: `tools: []` stays "no tools" (today's behavior), `tools: <explicit list>` stays filtered, only missing `tools:` changes (from rejected to "all tools" — a pure capability addition).

2. **Option C preserves the "no tools" capability.** Option A removes it. A tool-less agent (an agent that should only reason, not act) is a legitimate use case — `backwards.md` is one. Removing the capability to fix an asymmetry is the wrong trade.

3. **Option C fixes the root cause; Option A patches the symptom.** The bug is that two intents (all vs. none) are encoded as one value (`()`), forcing a proxy check. Option C gives each intent its own value (`None` vs `()`), eliminating the proxy. Option A eliminates the distinction by deleting one of the intents. The principle "absent = inherit default, present = author intent" is more defensible than "empty means all".

4. **Option B's `tools: "*"` sentinel adds friction for the common case.** Every general-purpose agent would need to write `tools: "*"`. Option C lets the common case be the default (omit the field). The privilege-expansion risk for plugins is real but is the same under B and C for the missing-field case — and under B, plugin authors who omit `tools:` get "no tools" (least privilege), which is safer. **This is the one genuine advantage of B over C.** Worth raising with the owner: if plugin-agent safety is a priority, a hybrid (Option C for built-in/user agents, Option B for plugin agents) could be considered — but that adds complexity and I do not recommend it unless the owner has a concrete third-party-plugin threat in mind.

### C.6 Refined file list (delta vs. original analysis)

The original four-file list is mostly correct; Option C changes the **shape** of the changes, not the files. Deltas:

| File | Original (Option A) | Option C delta |
|------|---------------------|----------------|
| `src/yoker/agents/schema.py` | Update docstring | **Change field type**: `tools: tuple[str, ...] \| None = None`. Update docstring to state: "`None` (default) = all available tools; `()` = no tools; non-empty tuple = explicit filter." Cross-reference `agents` field's opposite convention. |
| `src/yoker/agents/loader.py` | Drop strict-mode rejection of missing `tools:`; treat missing as `[]` | **Use `"tools" in frontmatter` (membership test)**, not `.get()`. Missing → `tools=None`. Present-but-null/empty/`[]`/`""` → `tools=()`. Present non-empty → parse as today. Emit `logger.warning("agent_tools_explicit_null_treated_as_empty", ...)` when `tools_raw is None` (the YAML-null footgun). Drop the strict-mode `tools_raw is None` rejection. Namespace `None` and `()` both pass through `_namespace_tools` unchanged (return `[]` for falsy input — verify this still holds for `None`). |
| `src/yoker/core/__init__.py` | Collapse the two branches into `if len(tools) == 0: keep all` | **Three branches**: `if self.definition.tools is None: logger.info("agent_tools_default_all", ...); return` (all tools). `elif len(self.definition.tools) == 0: logger.info("agent_tools_empty", ...); self.tools.clear(); return` (no tools). Else explicit filter (unchanged). **Remove the `simple_name is None and namespace is None` proxy check entirely** — `None` carries the intent now. |
| `src/yoker/agents/validator.py` | Remove `if not definition.tools: raise ValidationError(...)` | Same removal — still correct. (And note: this validator is not on the production load path; the change only affects callers who invoke it directly.) |
| `tests/agents/test_loader.py` | Add: missing `tools:` loads; `tools: ""` and `tools: []` load | Add: missing `tools:` → `definition.tools is None`; `tools:` (YAML null) → `definition.tools == ()` AND a warning is logged; `tools: []` → `definition.tools == ()`; `tools: ""` → `definition.tools == ()`. |
| `tests/agents/test_validator.py` | Add: empty `tools` passes | Split into two: `tools=None` passes; `tools=()` passes. (Today both raise.) |
| `tests/core/test_agent_tools.py` | Named agent with `tools=()` has all tools | **Three cases**: `tools=None` → all registered tools; `tools=()` → no tools (registry cleared); `tools=("read",)` → only `read`. Plus: `tools=None` with a config-disabled tool → disabled tool NOT in the all-tools set (config gating preserved). |

### C.7 Refined acceptance criteria (delta vs. original)

1. **Three-way semantic.** `tools=None` (field absent / default) → all available tools; `tools=()` (field present, empty) → no tools; `tools=(...)` (non-empty) → explicit filter. Documented in schema docstring.
2. **Config gating preserved.** "All available tools" = all tools that survived `ToolsConfig` per-tool `enabled` gating and plugin-load security gating. A tool disabled via `config.tools.<name>.enabled = False` is NOT in the "all" set, even when `tools is None`.
3. **Logged for discoverability.** Both branches emit distinct `logger.info` events: `agent_tools_default_all` (the `None` branch — flag accidental omissions) and `agent_tools_empty` (the `()` branch — confirm explicit "no tools" intent).
4. **YAML-null footgun warning.** When `tools:` is present in frontmatter with a YAML null value (i.e. `tools:` with nothing after, or `tools: null`), emit `logger.warning("agent_tools_explicit_null_treated_as_empty", ...)` advising the author to either omit the field (for all tools) or write `tools: []` (for no tools). This is the new code path Option C requires that A and B do not.
5. **No proxy check.** The `simple_name is None and namespace is None` early return in `_filter_tools_by_definition` is removed. The `tools is None` check replaces it. The default in-memory `AgentDefinition()` (which now has `tools=None`) takes the "all tools" branch via the same check — uniform semantics, no special case.
6. **No backward-compat regression for shipped definitions.** `backwards.md` (`tools: []`) remains a no-tools agent. Any definition with `tools: <explicit list>` remains filtered. Only the missing-field case changes behavior (from rejected to "all tools") — a pure capability addition.
7. **Schema docstring documents the asymmetry.** `AgentDefinition.tools` docstring states the three states and cross-references `AgentDefinition.agents` where empty means "no spawns" (and there is no `None`-sentinel because spawns are permissions defaulting closed, not capabilities defaulting open).

### C.8 Open question for the owner

The one respect in which Option B is strictly safer than Option C: **third-party plugin agents that omit `tools:`**. Under C they get all tools (privilege expansion from today's "rejected"). Under B they get no tools (least privilege). The mitigation in C is the `logger.info` line plus documentation, which is reasonable for first-party agents but weaker for third-party plugins the user may install without auditing.

If the owner anticipates third-party yoker plugins being installed untrusted, a hybrid is worth considering: built-in/user agents use Option C (missing = all), plugin agents use Option B semantics (missing = no tools, opt-in via `tools: "*"` for all). This adds a namespace-dependent default but is implementable in `parse_agent_definition` by checking the `namespace` argument. **I do not recommend this unless the owner has a concrete third-party threat in mind** — it adds complexity for a hypothetical. Flagging for the owner's decision; not blocking.