# Security Engineer Review — M.2 Default Tools Behavior (Implementation)

Stage: Domain Review (security-engineer), round 0 implementation verification.
Branch: `feature/m2-default-tools-behavior` (PR #47 draft).

## Verdict: **approved**

All 7 required mitigations from my Option C conditional endorsement are
delivered. No residual privilege-expansion vector is left unaddressed. One
minor non-blocking observation noted below.

---

## Mitigation Verification

### 1. Side-channel `tools_unspecified` flag — DELIVERED

`src/yoker/agents/schema.py:46` — `tools_unspecified: bool = True` field on
`AgentDefinition`. `__post_init__` (lines 54-73) flips it to `False` for any
explicit value (`None`, list, non-empty tuple). Default-constructed empty
tuple keeps `True`. The docstring (lines 20-28) documents the semantics.

### 2. Loader uses `"tools" in frontmatter`, not `.get(...) is None` — DELIVERED

`src/yoker/agents/loader.py:114` — `if "tools" not in frontmatter:`. Present
branch (line 117) handles `None`/`str`/`list`/other separately, each setting
`tools_unspecified=False`. Test `test_loader_handles_present_vs_missing_keys`
asserts the source contains the `"tools" not in frontmatter` check.

### 3. WARN-level `agent_tools_default_granted` event, exactly once — DELIVERED

`src/yoker/core/__init__.py:433` — `logger.warning("agent_tools_default_granted", ...)`
inside `_filter_tools_by_definition` branch 1 (line 432: `if
self.definition.tools_unspecified`). `_filter_tools_by_definition` is called
once from `__init__` (line 118). The WARN level is confirmed by the
`logger.warning` call (not `logger.info`/`logger.debug`).

Test `test_warn_emitted_on_all_tools_granted_by_omission`
(`tests/core/test_agent_tools.py:158-168`) patches `yoker.core.logger.warning`
and asserts `len(matching) == 1` — exactly one emission per Agent
construction with all-tools-by-omission.

The complementary `test_warn_not_emitted_when_tools_explicitly_empty`
(lines 170-182) confirms no emission when `tools=None` is explicit.

### 4. Shipped-agent audit — DELIVERED

All shipped agent definitions audited. None relies on field-omission for
all-tools:

| File | `tools:` value | Behavior on upgrade |
|------|----------------|---------------------|
| `examples/agents/markdown.md` | `Read, List, Write, Update` | explicit list — no change |
| `examples/agents/researcher.md` | `Read, List, Update` | explicit list — no change |
| `examples/agents/main.md` | `List, Read, Write, Update` | explicit list — no change |
| `examples/plugins/demo/.../backwards.md` | `[]` | no-tools (regression guard) — no change |
| `examples/plugins/demo/.../demo.md` | explicit list (7 tools) | explicit list — no change |

`backwards.md` retains `tools: []` (no-tools), verified by
`test_backwards_md_loads_no_tools` (line 220-237). No shipped agent would
change behavior under Option C on upgrade.

### 5. `validate_agent_definition` on runtime path; "at least one tool" check removed — DELIVERED

- Runtime wiring: `src/yoker/core/__init__.py:408` —
  `validate_agent_definition(self.definition, self.config.tools)` called from
  `_validate_definition` (line 112 of `__init__`). Not dead code anymore.
- "At least one tool" check removed: `src/yoker/agents/loader.py:142-143`
  comment confirms removal. `validate_tools` (`validator.py:25-72`) returns
  warnings only, no raises for empty tools.
- Test `test_validator_called_on_agent_construction` (line 188-199) patches
  `yoker.core.validate_agent_definition` and asserts `assert_called_once()`.

**Cannot-raise analysis**: `validate_agent_definition` still calls
`validate_non_empty_string` for `name` and `description`
(`validator.py:96-97`), which raises `ValidationError` on empty values. In
practice this cannot fire on the runtime path: the loader (strict=True)
already raises `ConfigurationError` for missing name/description before
reaching the Agent, and the default `AgentDefinition()` has non-empty
`name="default"` / `description="The default/minimal Yoker agent."`. A
programmatically-constructed `AgentDefinition(simple_name="", description="")`
would raise, but that is a caller bug, not a privilege-expansion vector. The
docstring claim "Never raises" in `_validate_definition` (line 403-406) is
slightly inaccurate for the name/description path, but this is a
non-blocking documentation nit, not a security issue.

**`validate_tools` softening safety**: The raise→warn change for unknown
bare tools is safe. The validator was previously dead code (never called from
production), so softening removes no active security check. The runtime
`_warn_missing_tools` check (line 373-398) remains authoritative and still
warns on unavailable tools. Actual tool filtering is in
`_filter_tools_by_definition`, which is unaffected by the validator's
output. No security-relevant check was lost.

### 6. Changelog/upgrade note — DELIVERED

`CHANGELOG.md` Unreleased section (lines 11-33):
- "Changed" entry explains Option C semantics and the new
  `agent_tools_default_granted` WARN event.
- "Upgrade Notes" (lines 28-33) explicitly warns: "Plugins with a missing
  `tools:` line gain all tools on upgrade. Add an explicit `tools: []` to
  agent definition files that should have no tools."
- Actionable: tells plugin authors exactly what to add (`tools: []`) and
  references the `backwards.md` regression guard.

### 7. 8-case test matrix — DELIVERED

`tests/core/test_agent_tools.py` `TestLoaderMatrix` + `TestRuntimeFiltering`
+ `TestInMemoryAgentDefinition` cover all 8 cases:

| Case | Test | Asserts |
|------|------|---------|
| key-absent | `test_missing_tools_loads_all_tools_flag` (line 39) | `tools==()`, `tools_unspecified is True` |
| `tools:` bare (parses null) | parametrize `""` (line 46) | `tools==()`, `tools_unspecified is False` |
| `tools: null` | parametrize `"null"` (line 46) | `tools==()`, `tools_unspecified is False` |
| `tools: ~` | parametrize `"~"` (line 46) | `tools==()`, `tools_unspecified is False` |
| `tools: ""` | `test_load_empty_tools_string` (loader) + parametrize `""` | `tools==()`, `tools_unspecified is False` |
| `tools: []` | parametrize `"[]"` (line 46) | `tools==()`, `tools_unspecified is False` |
| explicit list | `test_explicit_list_filters` (line 54) | namespaced tuple, `tools_unspecified is False` |
| default agent | `test_default_constructor_grants_all_tools` (line 65) + `test_default_definition_grants_all_tools` (line 88) | `tools_unspecified is True`, all tools at runtime |

Runtime behavior is asserted for each branch in `TestRuntimeFiltering`
(lines 88-156), including the config-disabled-tool case (criterion 7, line
148) and the WARN emission (criterion 8, line 158).

---

## Residual Risk Assessment

### api.py `tools=None` → all-tools contract

`src/yoker/api.py:143` — `tools_unspecified=tools is None`. So
`yoker.agent(tools=None)` and `yoker.agent()` (default `tools=None`) both
grant all configured tools; `yoker.agent(tools=[])` grants no tools.

This is **not a new privilege-expansion surface**:
- It is the documented default of the public API (docstring lines 190-191:
  "None keeps all configured tools; [] disables all").
- It is consistent with the Option C YAML semantics (missing `tools:` line
  → all tools) approved in the plan review.
- The WARN `agent_tools_default_granted` event fires for this case (the
  in-memory `AgentDefinition` has `tools_unspecified=True`), so operators
  see it in logs.
- A developer accidentally passing `None` gets the same behavior as the
  default-constructed agent — no silent privilege expansion beyond the
  approved design.

The `None`-vs-`[]` distinction is a documented footgun, but it is the
contract the owner approved. No action required.

### No other unaddressed vectors

- Plugin agent definitions loaded via the Session layer go through the same
  loader (`parse_agent_definition`), so the `tools_unspecified` flag is set
  consistently for plugin agents too.
- The trust gate (`check_source_allowed`) is upstream of agent loading and
  unaffected by this change.
- No new default-allow path was introduced for file-system or network tools
  beyond the approved Option C semantics.

---

## Non-blocking Observation

`_validate_definition` docstring (lines 403-406) says "Never raises — the
runtime `_warn_missing_tools` check stays authoritative." This is slightly
inaccurate: `validate_agent_definition` can raise `ValidationError` for
empty `name`/`description` via `validate_non_empty_string`. In practice
this is unreachable on the runtime path (loader pre-validates; default
`AgentDefinition` has non-empty fields), so it is a documentation nit, not
a security risk. Recommend a future commit either (a) soften
`validate_non_empty_string` to warn-only on the runtime path, or (b) fix
the docstring to say "Never raises for tools-related checks." Not blocking.

---

## Scope Classification

| Finding | Classification | Action |
|---------|---------------|--------|
| All 7 mitigations delivered | Blocking (satisfied) | None — approved |
| `_validate_definition` "never raises" docstring inaccuracy | New (non-blocking) | Backlog: docstring fix or warn-only softening |
| api.py `tools=None` → all-tools | Related (accepted design) | No action — approved contract |

## Positive Observations

- The 8-case test matrix is thorough and asserts both the `tools` tuple and
  the `tools_unspecified` flag in every case.
- The WARN event is verified to be exactly-once via mock call-count
  assertion, not just "called".
- The `backwards.md` regression guard is explicitly tested, protecting
  against future accidental removal of `tools: []`.
- The changelog upgrade note is actionable and references the regression
  guard example.
- The validator softening (raise→warn) preserves the runtime
  `_warn_missing_tools` check as authoritative, so no security-relevant
  signal was lost.