# Functional Review: M.2 Default Tools Behavior (Option C)

- **Task**: M.2 Default Tools Behavior (initial implementation, round 0)
- **Branch**: `feature/m2-default-tools-behavior` (PR #47 draft)
- **Reviewer**: functional-analyst
- **Date**: 2026-07-20
- **Stage**: Stage a (Functional Review, BLOCKING)
- **Verdict**: approved (all 12 criteria pass; both deviations sound; no regressions; one pre-existing out-of-scope observation noted)

## Verification method

- Read every modified file (`agents/schema.py`, `agents/loader.py`, `agents/validator.py`, `core/__init__.py`, `api.py`).
- Read every new/modified test file (`tests/core/test_agent_tools.py`, `tests/agents/test_loader.py`, `tests/agents/test_validator.py`, `tests/test_agent.py`, `tests/test_api/test_builder.py`).
- Ran `make test` (1889 passed) and the M.2-specific suite (32 passed + 50 loader/validator passed).
- Probed the two developer-reported deviations with standalone scripts.
- Probed a suspected file-namespace edge case against both the branch and master to confirm pre-existing vs. regression.

## Acceptance criteria verification

### Criterion 1 — Missing `tools` in YAML → all tools
**PASS.** `loader.py:114-116` uses `"tools" not in frontmatter`; missing key → `tools=()`, `tools_unspecified=True`. Runtime branch 1 (`core/__init__.py:432-439`) keeps all config-enabled tools.
Evidence: `tests/core/test_agent_tools.py::TestLoaderMatrix::test_missing_tools_loads_all_tools_flag` and `::TestRuntimeFiltering::test_missing_tools_yaml_grants_all_tools`.

### Criterion 2 — `tools:` / `null` / `~` / `""` / `[]` → no tools
**PASS.** `loader.py:118-132` handles all five present-empty forms. YAML `""` parses to empty string, which hits the `isinstance(tools_raw, str)` branch (`loader.py:127-129`) and produces an empty tuple after comma-split filtering. All set `tools_unspecified=False`.
Evidence: `tests/core/test_agent_tools.py::TestLoaderMatrix::test_present_null_tools_loads_no_tools_flag[""]`, `[null]`, `[~]`, `[]` and `::TestRuntimeFiltering::test_present_null_yaml_disables_tools[*]`. Also `tests/agents/test_loader.py::test_load_present_null_tools_loads_no_tools_flag` and `::test_load_empty_tools_string`.

### Criterion 3 — `tools: [read, list]` → filter (no regression)
**PASS.** `loader.py:130-132` handles YAML lists; `_namespace_tools` applies the `file:`/folder namespace. `tools_unspecified=False`.
Evidence: `tests/core/test_agent_tools.py::TestLoaderMatrix::test_explicit_list_filters` and `::TestRuntimeFiltering::test_explicit_list_filters_at_runtime` (the runtime test uses an in-memory definition with bare names so the `yoker:` prefix handling kicks in).

### Criterion 4 — In-memory `AgentDefinition()` → all tools (no regression)
**PASS.** `schema.py:46` defaults `tools_unspecified=True`; `__post_init__` (`schema.py:54-73`) leaves it True when `tools == ()` is the default. Runtime branch 1 grants all config-enabled tools.
Evidence: `tests/core/test_agent_tools.py::TestInMemoryAgentDefinition::test_default_constructor_grants_all_tools` and `::TestRuntimeFiltering::test_default_definition_grants_all_tools`.

### Criterion 5 — `AgentDefinition(tools=None)` and `AgentDefinition(tools=[])` → no tools
**PASS.** `schema.py:65-70` flips `tools_unspecified=False` for `None` and `list` inputs, normalizing both to `()`.
Evidence: `tests/core/test_agent_tools.py::TestInMemoryAgentDefinition::test_explicit_empty_disables_tools[None]` and `[empty1]`, plus runtime `::test_in_memory_explicit_empty_disables_tools` and `::test_in_memory_explicit_list_disables_tools`.

### Criterion 6 — `AgentDefinition(tools=("yoker:read",))` → filter (no regression)
**PASS.** `schema.py:71-72` flips `tools_unspecified=False` for non-empty tuples; tools kept verbatim.
Evidence: `tests/core/test_agent_tools.py::TestInMemoryAgentDefinition::test_explicit_filter` and `::TestRuntimeFiltering::test_in_memory_explicit_filter` (asserts `yoker:read` present, `yoker:list` absent).

### Criterion 7 — `config.tools.<name>.enabled = False` still drops the tool on all-tools grant
**PASS.** Config-disabled tools are never registered in the tool registry (`core/__init__.py:103` `register_plugin_tools` honours config; built-in registration respects `config.tools.<name>.enabled`). Branch 1 (`tools_unspecified=True`) keeps whatever the registry has — which excludes disabled tools.
Evidence: `tests/core/test_agent_tools.py::TestRuntimeFiltering::test_config_disabled_drops_tool_even_when_all_granted` (sets `config.tools.read.enabled = False`, asserts `yoker:read` absent, `yoker:list` present).

### Criterion 8 — WARN `agent_tools_default_granted` on all-tools-by-omission
**PASS.** `core/__init__.py:433-438` emits via `logger.warning("agent_tools_default_granted", ...)`. structlog `logger.warning` is WARN level (visible by default). The event is emitted exactly once per Agent construction (the `return` immediately after ensures no other branch fires).
Evidence: `tests/core/test_agent_tools.py::TestRuntimeFiltering::test_warn_emitted_on_all_tools_granted_by_omission` asserts one matching call; `::test_warn_not_emitted_when_tools_explicitly_empty` confirms it is NOT emitted for `tools=None`.

### Criterion 9 — `validate_agent_definition` on runtime path; accepts empty/missing tools
**PASS.** `core/__init__.py:107-113` calls `self._validate_definition()` after definition resolution. `_validate_definition` (`core/__init__.py:400-414`) calls `validate_agent_definition` and logs returned warnings without raising. `validator.py:99-102` removed the "must specify at least one tool" guard; empty/missing tools produce no warnings.
Evidence: `tests/core/test_agent_tools.py::TestValidatorOnRuntimePath::test_validator_called_on_agent_construction` (mocks `validate_agent_definition`, asserts called once) and `::test_validator_accepts_empty_tools` (three shapes: default, `tools=None`, `tools=() + tools_unspecified=False`).

### Criterion 10 — `backwards.md` stays a no-tools agent
**PASS.** `examples/plugins/demo/yoker_plugin_demo/agents/backwards.md` retains `tools: []` (bare null in YAML semantics — `[]` parses to empty list). Loader produces `tools=()`, `tools_unspecified=False`. Runtime branch 2 clears the registry.
Evidence: `tests/core/test_agent_tools.py::TestBackwardsRegression::test_backwards_md_loads_no_tools` (asserts `tools == ()`, `tools_unspecified is False`, runtime `agent.tools.names == []`).

### Criterion 11 — Docstring/code agreement
**PASS.**
- `core/__init__.py:416-430` `_filter_tools_by_definition` docstring documents all three Option C branches, names `tools_unspecified=True`/`=False`, and mentions `agent_tools_default_granted`.
- `agents/schema.py:20-31` `AgentDefinition` class docstring documents `tools`/`tools_unspecified` semantics including the YAML forms that map to False.
- `agents/loader.py:109-113` comment in `parse_agent_definition` distinguishes missing key from present-null and names the warning.
Evidence: `tests/core/test_agent_tools.py::TestDocstringAgreement::test_filter_tools_docstring_describes_three_branches`, `::test_schema_tools_field_documents_unspecified`, `::test_loader_handles_present_vs_missing_keys` (source introspection asserts `"tools" not in frontmatter` and `agent_tools_explicit_null_treated_as_empty`).

### Criterion 12 — No regression for explicit-tool filtering and namespace handling
**PASS.** Full suite: 1889 passed, 15 warnings, 0 failures. M.2-specific suite: 82 passed.
Evidence:
- `tests/core/test_agent_tools.py::TestNoRegression::test_explicit_filter_still_filters`, `::test_case_insensitive_filter_still_works`, `::test_namespaced_tools_preserved`.
- `tests/test_agent.py::TestAgentToolMatching::test_case_insensitive_tool_matching`, `::test_empty_tools_list`.
- `tests/test_api/test_builder.py::TestAgentBuilderTools` (all three: whitelist, empty, None).
- `tests/agents/test_validator.py` full file.

## Deviation scrutiny

### Deviation 1 — `api.py` modified to pass `tools_unspecified=tools is None`

**Verdict: SOUND.** No regression. The deviation is necessary to preserve `yoker.process(..., tools=[])` → no-tools semantics under Option C.

**Trace of `yoker.agent()` tools kwarg (post-deviation):**

| Call | `tools is None`? | Inline `AgentDefinition` built? | `tools_unspecified` | Runtime result |
|---|---|---|---|---|
| `yoker.agent()` | True (default) | No — falls through to `Agent()` constructor → `AgentDefinition()` | True (default) | ALL tools |
| `yoker.agent(tools=None)` | True | No — same path as above | True (default) | ALL tools |
| `yoker.agent(tools=[])` | False (`[]` is not None) | Yes — `AgentDefinition(tools=(), tools_unspecified=False)` | False | NO tools |
| `yoker.agent(tools=["read"])` | False | Yes — `AgentDefinition(tools=("read",), tools_unspecified=False)` | False | filter to `read` |
| `yoker.agent(system_prompt="X")` (no tools) | True (default) | Yes — `AgentDefinition(tools=(), tools_unspecified=True)` | True | ALL tools |

**Answer to the developer's question** — `yoker.agent(tools=None)` maps to ALL tools, not no-tools. This is the documented Python API contract (`api.py:190-192`): *"None keeps all configured tools; [] disables all; ["read"] keeps only read"*. The `None` sentinel in api.py means "unset/default" (consistent with `system_prompt=None`, `skills=None`, `plugins=None`). This is a deliberate layering choice: api.py uses `None` as "default", while `AgentDefinition` uses `None` as "explicitly no tools". The two contracts are different but each internally consistent and documented.

**Consistency check:** The api.py deviation preserves the previous `yoker.agent(tools=[])` → no-tools behavior (the comment on the pre-deviation line `# tools=[] clears all tools` still holds). Without the deviation, `tuple([])` would produce `()` and `AgentDefinition(tools=())` would default to `tools_unspecified=True` (ALL tools) — which would have been a regression of the `tools=[]` API. The deviation is correct and necessary.

**Minor UX observation (non-blocking):** A user familiar with `AgentDefinition(tools=None) → no tools` may be surprised that `yoker.agent(tools=None) → ALL tools`. This is mitigated by the api.py docstring being explicit. No action required for M.2.

**Test coverage:** `tests/test_api/test_builder.py::TestAgentBuilderTools::test_tools_whitelist`, `::test_tools_empty_disables_all`, `::test_tools_none_keeps_all` cover all three cases.

### Deviation 2 — `validate_tools` softened from raise to warn; namespaced tools skip static validation

**Verdict: SOUND.** No regression; no silent failure path introduced.

**Justification:** The validator is now wired onto the runtime path (`_validate_definition` is called from `Agent.__init__`). If `validate_tools` still raised on unknown bare tools, agent construction would fail for edge cases that the runtime path previously tolerated (the runtime `_warn_missing_tools` only warned). Softening to warn preserves the warn-only contract.

**Edge cases (all covered, no silent failures):**

| Scenario | Validator behavior | Runtime `_warn_missing_tools` | Final result |
|---|---|---|---|
| Bare typo (`"raed"`) | warn "not a known built-in tool" | warn "agent tools unavailable" + filter out | tool absent, two warnings |
| Disabled built-in (`"search"` with `config.tools.search.enabled=False`) | warn "specified but not enabled" | not in registry (never registered) → not flagged as missing | tool absent, one warning |
| Unknown namespaced (`"pkg:does_not_exist"`) | skip static validation | warn "agent tools unavailable" + filter out | tool absent, one warning |
| Known namespaced present in registry | skip | found in registry, kept | tool present |
| Unknown bare in registry (e.g., plugin bare name) | warn "not a known built-in tool" | found in registry, kept | tool present, one spurious warning (acceptable) |

**Authoritative runtime check:** `core/__init__.py:373-398` `_warn_missing_tools` still runs unchanged after `_validate_definition`, against the actual registry. The validator softening does not weaken the runtime safety net.

**No silent failure path:** The only way a tool request becomes silently absent is if BOTH the validator AND `_warn_missing_tools` are silent. `_warn_missing_tools` is silent only when every requested tool resolves against the registry — in which case the tool IS present. So either the tool is present, or at least one warning fires. Safe.

**Test coverage:** `tests/agents/test_validator.py::TestValidateTools::test_validate_unknown_tool` (warn, not raise), `::test_validate_namespaced_tool_skipped`, `::test_validate_disabled_tool_warning`. `tests/core/test_agent_tools.py::TestValidatorOnRuntimePath` confirms runtime wiring. `tests/test_agent.py::TestAgentToolRegistry::test_agent_warns_on_missing_tools` confirms the runtime warn-on-missing behavior is preserved.

## Edge cases beyond the plan (verified)

- **`tools: ""`** (empty string): hits the `isinstance(tools_raw, str)` branch in `loader.py:127-129`; comma-split on `""` returns `[]`, filtered to `()`. `tools_unspecified=False`. Covered by `tests/agents/test_loader.py::test_load_empty_tools_string`.
- **`tools: 123`** (invalid scalar type): hits the `else` branch in `loader.py:133-140`; raises `ConfigurationError` in strict mode. Covered by `tests/agents/test_loader.py::test_load_invalid_tools_type`.
- **`tools: [read, list]` from a directory load**: `_namespace_tools` applies the folder namespace (e.g., `agents:read`). Runtime filter matches against `yoker:` registered names. See observation below.
- **`AgentDefinition(tools=(), tools_unspecified=False)`**: constructs valid "no tools" definition. Covered by `tests/core/test_agent_tools.py::TestValidatorOnRuntimePath::test_validator_accepts_empty_tools`.

## Pre-existing observation (NOT a regression from M.2 — out of scope)

**File-loaded agents with explicit bare tool names get NO tools at runtime due to namespace mismatch.**

When an agent definition file is loaded via `load_agent_definition(path)`, the loader applies `FILE_NAMESPACE = "file"` to bare tool names: `tools: [read]` becomes `("file:read",)`. The runtime `_filter_tools_by_definition` builds `requested = {"file:read"}` (since `:` is in the name, no `yoker:` prefix is added). The registered built-in tools are `yoker:read`. The filter removes `yoker:read` because `"yoker:read" not in {"file:read"}`. The agent ends up with NO tools, and an "agent tools unavailable" warning is logged.

**Confirmed pre-existing on master** (verified by stashing M.2 changes and re-running the probe): the behavior is identical before and after M.2. The original `_filter_tools_by_definition` had the same `:` branch logic.

**Why M.2 doesn't regress this:** The original code used `simple_name is None and namespace is None` to skip filtering for "default agents"; a file-loaded agent has both set, so it went through the same filter logic. M.2's branch 1 (`tools_unspecified`) is a different default-agent test but produces the same outcome for the file-with-explicit-tools case (which hits branch 3 in both versions).

**Recommendation:** This is a separate bug worth filing (file namespace on requested tools should be reconciled with the `yoker:` registry, or file-loaded agents' bare tool names should not be namespaced). It does not block M.2.

## Final result

- All 12 acceptance criteria: **PASS**.
- Deviation 1 (api.py `tools_unspecified=tools is None`): **SOUND** — necessary to preserve `tools=[]` → no-tools in the Python API; `yoker.agent(tools=None) → ALL tools` is the documented and consistent contract.
- Deviation 2 (validate_tools softened): **SOUND** — runtime `_warn_missing_tools` stays authoritative; no silent failure path.
- Test suite: 1889 passed, 0 failed.
- No regressions identified.
- One pre-existing out-of-scope observation noted (file-namespace/runtime mismatch on explicit bare tool names).

**Verdict: approved.**