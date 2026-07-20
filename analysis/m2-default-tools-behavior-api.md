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