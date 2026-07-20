# Functional Review Round 1: M.2 Default Tools Behavior (Sentinel Refactor)

- **Task**: M.2 Default Tools Behavior (PR #47, round 1 — sentinel refactor + api.py alignment)
- **Branch**: `feature/m2-default-tools-behavior`
- **Reviewer**: functional-analyst
- **Date**: 2026-07-20
- **Stage**: Stage a (Functional Review, BLOCKING) — scoped re-review after owner feedback
- **Verdict**: approved (all 12 criteria pass; sentinel sound; dual contract eliminated; no regressions)

## Verification method

- Read every modified source file: `agents/schema.py`, `agents/__init__.py`, `agents/loader.py`, `agents/validator.py`, `core/__init__.py`, `api.py`, `ui/commands/tools.py`, `ui/commands/agents.py`.
- Read every modified test file: `tests/core/test_agent_tools.py`, `tests/agents/test_loader.py`, `tests/agents/test_validator.py`, `tests/test_agent.py`, `tests/test_api/test_builder.py`.
- Ran `make check`: 1891 passed, 15 warnings, 0 failures; ruff/mypy clean.
- Confirmed no `tools_unspecified` references remain in `src/` or `tests/` (grep returned empty).
- Cross-checked the implementation against the owner-feedback interpretation at `reporting/m2-default-tools-behavior/owner-feedback-interpretation.md` and the owner's clarification ("no dual contract, the thin API should adhere to the underlying contracts").

## Acceptance criteria re-verification

### Criterion 1 — Missing `tools` in YAML → all tools
**PASS.** `loader.py:114-115`: `if "tools" not in frontmatter: tools = ALL_TOOLS`. Runtime branch 1 (`core/__init__.py:441-448`) checks `isinstance(tools, AllToolsSentinel)` → keeps all config-enabled tools and emits `agent_tools_default_granted` WARN.
Evidence: `tests/core/test_agent_tools.py::TestLoaderMatrix::test_missing_tools_loads_all_tools_flag` (`assert d.tools is ALL_TOOLS`); `::TestRuntimeFiltering::test_missing_tools_yaml_grants_all_tools`; `tests/agents/test_loader.py::test_load_missing_tools_loads_all_tools_flag` (`assert definition.tools is ALL_TOOLS`).

### Criterion 2 — `tools:` / `null` / `~` / `""` / `[]` → no tools
**PASS.** `loader.py:117-135` handles all five present-empty forms. Bare null / `~` / `""` / `[]` all produce `tools = ()`. The `agent_tools_explicit_null_treated_as_empty` warning is preserved for the bare-null forms. Runtime branch 2 (`core/__init__.py:451-458`) clears the registry.
Evidence: `tests/core/test_agent_tools.py::TestLoaderMatrix::test_present_null_tools_loads_no_tools_flag["", null, ~, []]` (`assert d.tools is not ALL_TOOLS`); `::TestRuntimeFiltering::test_present_null_yaml_disables_tools[*]`; `tests/agents/test_loader.py::test_load_present_null_tools_loads_no_tools_flag`, `::test_load_empty_tools_string`.

### Criterion 3 — `tools: [read, list]` → filter (no regression)
**PASS.** `loader.py:127-128` handles YAML lists → tuple. `_namespace_tools` (guarded at `loader.py:145`) applies the file/folder namespace. Runtime branch 3 (`core/__init__.py:461-480`) filters.
Evidence: `tests/core/test_agent_tools.py::TestLoaderMatrix::test_explicit_list_filters`; `::TestRuntimeFiltering::test_explicit_list_filters_at_runtime`.

### Criterion 4 — In-memory `AgentDefinition()` → all tools (no regression)
**PASS.** `schema.py:85`: `tools: "tuple[str, ...] | AllToolsSentinel" = ALL_TOOLS`. Default constructor preserves the sentinel (`__post_init__` early-returns at `schema.py:102-103`). Runtime branch 1 grants all tools.
Evidence: `tests/core/test_agent_tools.py::TestInMemoryAgentDefinition::test_default_constructor_grants_all_tools` (`assert d.tools is ALL_TOOLS`); `::TestRuntimeFiltering::test_default_definition_grants_all_tools`.

### Criterion 5 — `AgentDefinition(tools=None)` and `AgentDefinition(tools=[])` → no tools
**PASS.** `schema.py:104-107`: `__post_init__` normalizes `None` → `()` and `list` → `tuple(list)` (so `[]` → `()`). The sentinel is preserved only when `tools is ALL_TOOLS`.
Evidence: `tests/core/test_agent_tools.py::TestInMemoryAgentDefinition::test_explicit_empty_disables_tools[None, empty1]` (`assert d.tools is not ALL_TOOLS`, `assert d.tools == ()`); `::TestRuntimeFiltering::test_in_memory_explicit_empty_disables_tools`, `::test_in_memory_explicit_list_disables_tools`.

### Criterion 6 — `AgentDefinition(tools=("yoker:read",))` → filter (no regression)
**PASS.** `schema.py:108`: non-empty tuple passes through unchanged. Runtime branch 3 filters.
Evidence: `tests/core/test_agent_tools.py::TestInMemoryAgentDefinition::test_explicit_filter` (`assert d.tools == ("yoker:read",)`, `assert d.tools is not ALL_TOOLS`); `::TestRuntimeFiltering::test_in_memory_explicit_filter`.

### Criterion 7 — `config.tools.<name>.enabled = False` still drops the tool on all-tools grant
**PASS.** Config-disabled tools are never registered in the tool registry (built-in registration honours `config.tools.<name>.enabled`). Branch 1 keeps whatever the registry has — which excludes disabled tools.
Evidence: `tests/core/test_agent_tools.py::TestRuntimeFiltering::test_config_disabled_drops_tool_even_when_all_granted`.

### Criterion 8 — WARN `agent_tools_default_granted` on all-tools-by-omission
**PASS.** `core/__init__.py:442-447` emits via `logger.warning("agent_tools_default_granted", ...)`. structlog `logger.warning` is WARN level (visible by default). Emitted exactly once per Agent construction — the `return` immediately after ensures no other branch fires. The branch fires only when `isinstance(tools, AllToolsSentinel)`.
Evidence: `tests/core/test_agent_tools.py::TestRuntimeFiltering::test_warn_emitted_on_all_tools_granted_by_omission`; `::test_warn_not_emitted_when_tools_explicitly_empty` confirms it is NOT emitted for `tools=None`/`tools=()`.

### Criterion 9 — `validate_agent_definition` on runtime path; accepts empty/missing tools
**PASS.** `core/__init__.py:113` calls `self._validate_definition()` after definition resolution. `_validate_definition` (`core/__init__.py:406-420`) calls `validate_agent_definition` and logs returned warnings without raising. `validator.py:104` skips `validate_tools` when `isinstance(definition.tools, AllToolsSentinel)` — the sentinel is not iterable, and there is no explicit list to validate anyway.
Evidence: `tests/core/test_agent_tools.py::TestValidatorOnRuntimePath::test_validator_called_on_agent_construction`; `::test_validator_accepts_empty_tools` (three shapes: default `AgentDefinition()` → `tools is ALL_TOOLS`; `tools=None` → `()`; `tools=()` explicit → `()`); `tests/agents/test_validator.py::TestValidateAgentDefinition::test_empty_or_missing_tools_accepted`.

### Criterion 10 — `backwards.md` stays a no-tools agent
**PASS.** `examples/plugins/demo/yoker_plugin_demo/agents/backwards.md` retains `tools: []` (YAML empty list). Loader produces `tools=()`. Runtime branch 2 clears the registry.
Evidence: `tests/core/test_agent_tools.py::TestBackwardsRegression::test_backwards_md_loads_no_tools` (`assert d.tools == ()`, `assert d.tools is not ALL_TOOLS`, runtime `agent.tools.names == []`).

### Criterion 11 — Docstring/code agreement
**PASS.**
- `core/__init__.py:422-436` `_filter_tools_by_definition` docstring documents all three Option C branches referencing `tools is ALL_TOOLS`, `tools == ()`, non-empty filter, and `agent_tools_default_granted`.
- `agents/schema.py:69-72` `AgentDefinition` class docstring documents the three `tools` states (`ALL_TOOLS`, `()`, non-empty) and the `None`/`[]` normalization.
- `agents/schema.py:80-84` field comment explains the broad declared type vs the post-`__post_init__` runtime invariant.
- `agents/loader.py:109-113` comment distinguishes missing key from present-null and names the warning.
- `api.py:195-199` and `:353-357` `tools` kwarg docstrings document the new contract: default `ALL_TOOLS` → all tools; `None` → no tools; `[]` → no tools; `[...]` → filter.
Evidence: `tests/core/test_agent_tools.py::TestDocstringAgreement::test_filter_tools_docstring_describes_three_branches` (`assert "ALL_TOOLS" in doc`, `"agent_tools_default_granted" in doc`); `::test_schema_tools_field_documents_unspecified` (`assert "ALL_TOOLS" in doc`); `::test_loader_handles_present_vs_missing_keys`.

### Criterion 12 — No regression for explicit-tool filtering and namespace handling
**PASS.** Full suite: 1891 passed, 15 warnings, 0 failures. M.2-specific suite green.
Evidence: `tests/core/test_agent_tools.py::TestNoRegression::test_explicit_filter_still_filters`, `::test_case_insensitive_filter_still_works`, `::test_namespaced_tools_preserved`; `tests/test_agent.py::TestAgentToolMatching`; `tests/agents/test_validator.py` full file.

## Sentinel design soundness

`agents/schema.py:13-57` — `AllToolsSentinel` class + `ALL_TOOLS` singleton.

| Dunder | Implementation | Sound? |
|---|---|---|
| `__new__` | `schema.py:24-27` — singleton enforcement via `cls._instance` cache | YES — every `AllToolsSentinel()` returns the same instance |
| `__repr__` | `schema.py:29-30` → `"ALL_TOOLS"` | YES — self-documenting in tracebacks |
| `__bool__` | `schema.py:32-34` → `True` | YES — "all tools" is truthy; distinguishes from `None`/`()` (falsy) |
| `__iter__` | `schema.py:36-39` → raises `TypeError` | YES — fails loud on unguarded iteration; the three required guards prevent this |
| `__eq__` | `schema.py:41-42` → `other is self` (identity-only) | YES — no equality footgun (`ALL_TOOLS == []` is False, `ALL_TOOLS == ()` is False) |
| `__hash__` | `schema.py:44-45` → `id(self)` | YES — consistent with identity-based `__eq__` |
| `__reduce__` | `schema.py:47-49` → `(_resolve_all_tools, ())` | YES — pickle round-trips back to the singleton via `_resolve_all_tools` (`schema.py:52-54`) |

**Class is public** (`AllToolsSentinel`, not `_AllToolsSentinel`): this is actually better than the interpretation document's suggestion of a private class — it enables `isinstance` narrowing in downstream code and clean type annotations like `tuple[str, ...] | AllToolsSentinel`. Not a flaw.

**Singleton subclass edge case:** `__new__` uses `cls._instance`. If a subclass `Sub(AllToolsSentinel)` were defined, `Sub()` would call `__new__(Sub)`, find `cls._instance` inherited (not None — the parent's singleton), and return the parent's singleton. So `isinstance(x, AllToolsSentinel)` still only matches the one singleton. No divergence between `isinstance(x, AllToolsSentinel)` and `x is ALL_TOOLS`.

**No flaw identified.** The sentinel is robust across type, pickle, equality, repr, and iteration axes.

## The three required guards

| Guard | Location | Behavior | Confirmed |
|---|---|---|---|
| `_warn_missing_tools` | `core/__init__.py:384-385` | `if isinstance(self.definition.tools, AllToolsSentinel): return` — early-exit before the `for requested in self.definition.tools:` loop at line 389 | YES |
| `validate_agent_definition` | `validator.py:104-105` | `if not isinstance(definition.tools, AllToolsSentinel): warnings.extend(validate_tools(...))` — skips `validate_tools` (which iterates) when sentinel | YES |
| `_namespace_tools` call site | `loader.py:145-146` | `if not isinstance(tools, AllToolsSentinel): tools = tuple(_namespace_tools(tools, namespace))` — skips namespacing (which iterates) when sentinel | YES |

## UI command guards

| Command | Location | Behavior | Confirmed |
|---|---|---|---|
| `/tools` `_has` | `ui/commands/tools.py:39-40` | `if isinstance(ag.definition.tools, AllToolsSentinel): return True` — every tool marked available | YES |
| `/tools` display | `ui/commands/tools.py:87-88` | `if isinstance(agent.definition.tools, AllToolsSentinel): lines.append("  Allowed tools: ALL (no \`tools:\` filter)")` | YES |
| `/agents` current | `ui/commands/agents.py:43-44` | `if isinstance(agent.definition.tools, AllToolsSentinel): lines.append("      Tools: ALL ...")` | YES |
| `/agents` known | `ui/commands/agents.py:70-71` | Same pattern for each known agent definition | YES |

Both UI commands prevent the `TypeError: 'AllToolsSentinel' is not iterable` that would otherwise fire at the `for requested in ag.definition.tools:` loop (`tools.py:45`) and the `', '.join(sorted(agent.definition.tools))` calls. The `elif agent.definition.tools:` / `elif agent_definition.tools:` fallbacks (truthy tuple → display list) are also safe because the sentinel's `__bool__` returns `True` but the `if isinstance(..., AllToolsSentinel):` branch runs first.

## api.py contract alignment (dual contract eliminated)

`api.py:167` and `:323` — `tools: list[str] | AllToolsSentinel | None = ALL_TOOLS` (default is the sentinel, not `None`).

`api.py:142` — `if system_prompt is not None or tools is not ALL_TOOLS:` builds an in-memory `AgentDefinition` only when the caller overrode something. `tools` is passed through UNCHANGED via `cast("tuple[str, ...] | AllToolsSentinel", tools)` at line 148. **No `None → ALL_TOOLS` translation anywhere in api.py** (confirmed by reading the full `_build_config_and_definition` body).

| Call | `tools` value passed to `AgentDefinition` | `__post_init__` result | Runtime | Match AgentDefinition contract? |
|---|---|---|---|---|
| `yoker.agent()` | (no AgentDefinition built — falls through to `Agent()` → `AgentDefinition()`) | `ALL_TOOLS` (default) | ALL tools | YES |
| `yoker.agent(tools=None)` | `None` | `()` | NO tools | YES — `AgentDefinition(tools=None)` → no tools |
| `yoker.agent(tools=[])` | `[]` | `()` | NO tools | YES — `AgentDefinition(tools=[])` → no tools |
| `yoker.agent(tools=["read"])` | `["read"]` | `("read",)` | filter | YES |
| `yoker.agent(tools=ALL_TOOLS)` | `ALL_TOOLS` | `ALL_TOOLS` (preserved) | ALL tools | YES |
| `yoker.agent(system_prompt="X")` | `ALL_TOOLS` (default) | `ALL_TOOLS` | ALL tools | YES |

**Dual contract eliminated.** The previous round-0 deviation (`tools_unspecified=tools is None`, with `yoker.agent(tools=None)` → ALL tools) is gone. The api.py now adheres to the `AgentDefinition` contract: `None` means "no tools" at both layers. This matches the owner's clarification: "no dual contract, the thin API should adhere to the underlying contracts".

**Docstrings accurate.** `api.py:195-199` and `:353-357`: "The default (`ALL_TOOLS`) grants all config-enabled tools; omit the arg (or pass `ALL_TOOLS` explicitly) for all tools. `None` disables all tools (matches the `AgentDefinition` contract); `[]` also disables all; `["read"]` keeps only `read`." Matches the implementation.

**Test coverage of the new contract.** `tests/test_api/test_builder.py::TestAgentBuilderTools`:
- `test_tools_default_keeps_all` — `yoker.agent()` → all tools.
- `test_tools_none_disables_all` — `yoker.agent(tools=None, config=Config())` → `list(a.tools.names) == []`. (NEW behavior, NEW test — replaces the round-0 `test_tools_none_keeps_all`.)
- `test_tools_empty_disables_all` — `yoker.agent(tools=[], config=Config())` → no tools.
- `test_tools_whitelist` — `yoker.agent(tools=["read"])` → filter.
- `test_tools_all_tools_sentinel_keeps_all` — `yoker.agent(tools=ALL_TOOLS)` → all tools. (NEW test.)

## `isinstance` vs `is` deviation

The developer used `isinstance(tools, AllToolsSentinel)` in source (`core/__init__.py:384,441`, `validator.py:104`, `loader.py:145`, `ui/commands/tools.py:39,87`, `ui/commands/agents.py:43,70`) instead of `tools is ALL_TOOLS`. The interpretation document and the docstring (`schema.py:18-19`) recommend `is ALL_TOOLS`.

**Equivalence proof:** `AllToolsSentinel.__new__` (`schema.py:24-27`) caches a single instance in `cls._instance`. Every `AllToolsSentinel()` call returns that same object. There is no public way to construct a second `AllToolsSentinel` instance, and subclassing inherits the cached singleton (see "Singleton subclass edge case" above). Therefore `isinstance(x, AllToolsSentinel)` is True iff `x is ALL_TOOLS`.

**Acceptable.** The developer's stated reason (mypy narrowing) is legitimate — `isinstance` narrows the union type in the `if` branch, while `is ALL_TOOLS` does not narrow `tuple[str, ...] | AllToolsSentinel` to `AllToolsSentinel` as cleanly in all mypy versions. The two forms are semantically equivalent here. No edge case where they diverge.

**Consistency note (non-blocking):** the codebase mixes `is ALL_TOOLS` (in `__post_init__` at `schema.py:102`, and in api.py at line 142/144) and `isinstance(..., AllToolsSentinel)` (in the guards). Both work. A future cleanup could pick one, but this is cosmetic and does not affect correctness.

## `cast` in api.py

`api.py:148` — `tools=cast("tuple[str, ...] | AllToolsSentinel", tools)`.

**Sound.** The input `tools` has type `list[str] | AllToolsSentinel | None`. The `AgentDefinition.tools` field type is `tuple[str, ...] | AllToolsSentinel` (no `None`). The `cast` tells mypy "after `__post_init__`, the runtime type will be one of these" — and `__post_init__` (`schema.py:102-108`) does indeed normalize `None` → `()` and `list` → `tuple`, so the cast reflects a real runtime invariant.

The cast does NOT hide a type issue — it documents a post-`__post_init__` invariant that mypy cannot infer (dataclass `__post_init__` mutation is opaque to mypy). The alternative (widening the field type to include `None` and `list`) would push the normalization burden to every downstream consumer, which is worse. The cast is the right tool for the job.

## No `tools_unspecified` references remain

`grep -rn "tools_unspecified" src/ tests/` → empty. Fully removed.

## No regressions / test weakening

- **1891 passed** (round 0 was 1889; +2 new tests in `TestAgentBuilderTools`: `test_tools_none_disables_all` and `test_tools_all_tools_sentinel_keeps_all`).
- **No test weakened.** The round-0 `test_tools_none_keeps_all` (asserting the old dual-contract behavior `tools=None` → all tools) is replaced by `test_tools_none_disables_all` (asserting the new aligned behavior `tools=None` → no tools). This is a contract change mandated by the owner's clarification, not a weakening — the new test still asserts a specific, verifiable runtime outcome (`list(a.tools.names) == []`).
- All other M.2 tests retained their behavioral assertions; only the introspection targets shifted from `tools_unspecified is True/False` to `tools is ALL_TOOLS` / `tools == ()` / `tools is not ALL_TOOLS`. These are equivalent or stronger assertions.
- `make check` clean: ruff, mypy, pytest all green.

## Pre-existing observation (carried forward, NOT a regression from this round)

The round-0 observation about file-loaded agents with explicit bare tool names getting no tools at runtime (due to `FILE_NAMESPACE` mismatch with the `yoker:` registry) remains. It was confirmed pre-existing on master in round 0 and is unaffected by the sentinel refactor (the filter logic in branch 3 is unchanged). Out of scope for M.2.

## Final result

- All 12 acceptance criteria: **PASS**.
- Sentinel design: **SOUND** — singleton enforcement, repr, bool, iter (raises), eq (identity), hash, reduce (pickle) all correct.
- Three required guards (`_warn_missing_tools`, `validate_agent_definition`, `_namespace_tools`): **CONFIRMED** in place and effective.
- Two UI command guards (`/tools`, `/agents`): **CONFIRMED** — prevent `TypeError` on sentinel iteration; display "ALL" instead.
- api.py contract alignment: **CONFIRMED** — dual contract eliminated; `yoker.agent(tools=None)` → no tools (matches `AgentDefinition`); docstrings accurate.
- `isinstance` vs `is` deviation: **ACCEPTABLE** — semantically equivalent under singleton enforcement; mypy narrowing benefit is real.
- `cast` in api.py: **SOUND** — reflects a real post-`__post_init__` runtime invariant.
- No `tools_unspecified` references remain.
- No regressions; no tests weakened; 1891 passed; ruff/mypy clean.

**Verdict: approved.**