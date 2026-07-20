# Security Engineer Review — M.2 Default Tools Behavior, Round 1 (Sentinel Refactor)

**Scope**: Re-verify the 7 round-0 mitigations under the `ALL_TOOLS` sentinel
refactor + `api.py` contract alignment. Report-only — no code modified.

**Branch**: `feature/m2-default-tools-behavior`
**Files reviewed**: `src/yoker/agents/schema.py`, `src/yoker/agents/loader.py`,
`src/yoker/agents/validator.py`, `src/yoker/core/__init__.py`, `src/yoker/api.py`,
`src/yoker/ui/commands/tools.py`, `src/yoker/ui/commands/agents.py`,
`tests/core/test_agent_tools.py`, `tests/agents/test_loader.py`,
`tests/agents/test_validator.py`, `tests/test_api/test_builder.py`,
`CHANGELOG.md`, `DEVELOPMENT.md`, all 5 shipped agent definitions.

**Test verification**: `uv run pytest tests/core/test_agent_tools.py
tests/agents/test_loader.py tests/agents/test_validator.py
tests/test_api/test_builder.py -q` → 103 passed.

## Mitigation Status

### 1. Side-channel flag → `ALL_TOOLS` sentinel on the `tools` field — DELIVERED

`src/yoker/agents/schema.py:57` declares `ALL_TOOLS: AllToolsSentinel =
AllToolsSentinel()`. `AgentDefinition.tools` field default is `ALL_TOOLS`
(schema.py:85). The previous `tools_unspecified: bool` side-channel is removed
entirely — confirmed by grep: no `tools_unspecified` references remain in
`src/yoker/` or `tests/`. The intent now lives in the `tools` field value
itself, with no secondary flag to keep in sync. Three states are preserved:
`ALL_TOOLS` (default — all tools), `()` (no tools), non-empty tuple (filter).

### 2. Loader uses `"tools" in frontmatter` (not `.get()`) — DELIVERED

`src/yoker/agents/loader.py:114`:

```python
if "tools" not in frontmatter:
  tools: tuple[str, ...] | AllToolsSentinel = ALL_TOOLS
else:
  tools_raw = frontmatter["tools"]
  if tools_raw is None:
    tools = ()
    logger.warning("agent_tools_explicit_null_treated_as_empty", ...)
```

The membership test (`"tools" not in frontmatter`) — not `.get()` — preserves
the missing-vs-empty distinction. Missing key → `ALL_TOOLS` (all tools);
present-null/`~`/`""`/`[]` → `()` (no tools, with a WARN for the bare-null
forms). Test `test_load_missing_tools_loads_all_tools_sentinel` and
parametrized `test_load_present_null_tools_loads_no_tools` (4 empty forms)
cover the matrix.

### 3. WARN `agent_tools_default_granted` fires exactly once at WARN level — DELIVERED

`src/yoker/core/__init__.py:441-447`:

```python
if isinstance(tools, AllToolsSentinel):
  logger.warning(
    "agent_tools_default_granted",
    agent=self.definition.name,
    tool_count=len(self.tools),
    tools=list(self.tools.names),
  )
  return
```

`logger.warning` is WARN level (structlog). The branch fires exactly once per
`Agent` construction because `_filter_tools_by_definition` is called once from
`__init__` (core/__init__.py:119). Test
`test_warn_emitted_on_all_tools_granted_by_omission` (test_agent_tools.py:157)
asserts `len(matching) == 1`. Test
`test_warn_not_emitted_when_tools_explicitly_empty` (line 169) confirms no
WARN fires when `tools=None` (the empty-tools branch emits `agent_tools_empty`
at DEBUG level instead, core/__init__.py:452).

### 4. Shipped-agent audit — `backwards.md` stays `tools: []` — DELIVERED

All 5 shipped agent definitions explicitly specify `tools:`. None rely on
field-omission for all-tools:

| File | `tools:` value |
|------|----------------|
| `examples/agents/markdown.md` | `Read, List, Write, Update` |
| `examples/agents/researcher.md` | `Read, List, Update` |
| `examples/agents/main.md` | `List, Read, Write, Update` |
| `examples/plugins/demo/yoker_plugin_demo/agents/backwards.md` | `[]` (no-tools) |
| `examples/plugins/demo/yoker_plugin_demo/agents/demo.md` | 7-element list |

`backwards.md` stays `tools: []` (no-tools) — verified by reading the file and
by regression test `test_backwards_md_loads_no_tools` (test_agent_tools.py:217)
which asserts `d.tools == ()` and `d.tools is not ALL_TOOLS`, then constructs
an `Agent` and asserts `list(agent.tools.names) == []`.

### 5. `validate_agent_definition` on runtime load path; "at least one tool" check removed — DELIVERED

`src/yoker/core/__init__.py:113` calls `self._validate_definition()` during
`Agent.__init__`. `_validate_definition` (line 406) calls
`validate_agent_definition(self.definition, self.config.tools)` and logs each
returned warning at WARN level — never raises. Test
`test_validator_called_on_agent_construction` (test_agent_tools.py:187) patches
`validate_agent_definition` and asserts `mock_validate.assert_called_once()`.

"Must specify at least one tool" check: not present in
`src/yoker/agents/validator.py` (read in full, lines 1-127). The comment at
`loader.py:137-138` explicitly notes the check was removed:
`# Empty tools list is valid - agents don't need tools (removed check that
# required at least one tool)`. Test `test_validate_empty_tools`
(test_validator.py:134) asserts that `tools=ALL_TOOLS`, `tools=None`, and
`tools=()` all return `[]` (no warnings, no raises).

The validator skips `validate_tools` when the sentinel is set
(validator.py:104): `if not isinstance(definition.tools, AllToolsSentinel):
warnings.extend(validate_tools(...))` — guarded, no iteration of the sentinel.

### 6. Changelog/upgrade note warning plugin authors — DELIVERED

`CHANGELOG.md:11-37` describes the M.2 change under "Unreleased", including
the `ALL_TOOLS` sentinel semantics and the explicit null/empty forms.
`CHANGELOG.md:39-43` "Upgrade Notes" section:

> **Plugins with a missing `tools:` line gain all tools on upgrade.** Add an
> explicit `tools: []` to agent definition files that should have no tools.
> The bundled `examples/plugins/demo/.../backwards.md` already uses
> `tools: []` as a regression guard.

`DEVELOPMENT.md:11-84` documents the M.2 implementation in detail (schema,
loader, validator, core, UI commands, api.py, tests, changelog).

### 7. 8-case test matrix — DELIVERED

`tests/agents/test_loader.py` (lines 223-306) — 8 distinct cases:

1. `test_load_missing_tools_loads_all_tools_sentinel` — missing key → `ALL_TOOLS`
2. `test_load_present_null_tools_loads_no_tools[empty]` — `tools:` (bare null) → `()`
3. `test_load_present_null_tools_loads_no_tools[null]` — `tools: null` → `()`
4. `test_load_present_null_tools_loads_no_tools[~]` — `tools: ~` → `()`
5. `test_load_present_null_tools_loads_no_tools[[]]` — `tools: []` → `()`
6. `test_load_explicit_tools_list_filters` — non-empty list → filter (namespaced)
7. `test_load_empty_tools_string` — `tools: ""` → `()`
8. `test_load_invalid_tools_type` — `tools: 123` → `ConfigurationError`

`tests/core/test_agent_tools.py` adds runtime coverage for all branches:
default constructor (all), missing YAML (all), present-empty YAML (none),
explicit list (filter), in-memory `None`/`[]` (none), in-memory filter,
config-disabled-drops-tool, WARN-fires-once, WARN-not-on-empty, validator
wired, validator accepts empty, `backwards.md` regression, docstring
agreement, no-regression for filtering/namespace/case-insensitivity.

`tests/test_api/test_builder.py:77-85` covers the api.py contract:
`test_tools_none_disables_all`, `test_tools_empty_disables_all`,
`test_tools_default_keeps_all`, `test_tools_all_tools_sentinel_keeps_all`,
`test_tools_whitelist`.

## Round-1 Specific Scrutiny

### A. WARN fires exactly once under sentinel branch — CONFIRMED

The trigger moved from `tools_unspecified=True` (round 0) to
`isinstance(tools, AllToolsSentinel)` (round 1, core/__init__.py:441). The
single-call-site invariant is unchanged: `_filter_tools_by_definition` is
invoked exactly once from `Agent.__init__` (line 119). The WARN level
(`logger.warning`) is unchanged. Test
`test_warn_emitted_on_all_tools_granted_by_omission` still asserts exactly one
matching call. No regression.

### B. Sentinel vs `tools_unspecified` security equivalence — EQUIVALENT

The sentinel preserves the missing-vs-empty distinction by being the field's
default value. `is ALL_TOOLS` (identity) and `isinstance(tools,
AllToolsSentinel)` (type narrowing) are semantically equivalent because
`AllToolsSentinel` is a singleton (`__new__` returns the cached instance,
schema.py:24-27; `__eq__` is identity, schema.py:41-42). No new
privilege-expansion vector: the only path to all-tools is (a) omit `tools` in
YAML, (b) omit `tools` in `AgentDefinition()` / `yoker.agent()`, or (c)
explicitly pass `ALL_TOOLS`. All three are intentional acts.

### C. api.py `tools=None` → no tools (NEW behavior) — SECURITY IMPROVEMENT

Previously `yoker.agent(tools=None)` → all tools (with WARN). Now → no tools.
This closes an accidental-all-tools footgun: a caller passing `tools=None`
thinking "no tools" now gets no tools, matching the `AgentDefinition`
contract. Test `test_tools_none_disables_all` (test_builder.py:77) confirms.
No new attack surface: the default (`ALL_TOOLS`) and explicit `ALL_TOOLS`
still grant all tools intentionally; `None`/`[]` disable; non-empty lists
filter. The dual contract flagged by the api-architect is eliminated — the
`typing.cast` at api.py:148 reflects the post-`__post_init__` runtime
invariant for mypy; `None`/`list` are normalized by `__post_init__`, not by
api.py.

### D. Sentinel non-iterability — ALL SITES GUARDED

`AllToolsSentinel.__iter__` raises `TypeError` (schema.py:36-39). Every
iteration site is guarded with `isinstance(..., AllToolsSentinel)` early-return:

| Site | Guard |
|------|-------|
| `loader.py:145` (`_namespace_tools`) | `if not isinstance(tools, AllToolsSentinel):` |
| `validator.py:104` (`validate_tools`) | `if not isinstance(definition.tools, AllToolsSentinel):` |
| `core/__init__.py:384` (`_warn_missing_tools`) | `if isinstance(self.definition.tools, AllToolsSentinel): return` |
| `core/__init__.py:441` (`_filter_tools_by_definition`) | `if isinstance(tools, AllToolsSentinel): ... return` |
| `ui/commands/tools.py:39` (`_has`) | `if isinstance(ag.definition.tools, AllToolsSentinel): return True` |
| `ui/commands/tools.py:87` (render) | `if isinstance(agent.definition.tools, AllToolsSentinel):` |
| `ui/commands/agents.py:43, 70` (render) | `if isinstance(...tools, AllToolsSentinel):` |

Grep across `src/yoker/` for `definition.tools` / `agent_definition.tools`
iteration: no unguarded site found. No runtime TypeError / denial-of-service
vector via the sentinel.

### E. Pickle / deserialization — IDENTITY PRESERVED

`AllToolsSentinel.__reduce__` (schema.py:47-49) returns
`(_resolve_all_tools, ())`; `_resolve_all_tools` (schema.py:52-54) returns the
`ALL_TOOLS` singleton. Empirically verified via `uv run python`:

- `pickle.loads(pickle.dumps(ALL_TOOLS)) is ALL_TOOLS` → True
- `copy.deepcopy(ALL_TOOLS) is ALL_TOOLS` → True
- `copy.copy(ALL_TOOLS) is ALL_TOOLS` → True
- `AgentDefinition` pickle round-trip: `ad.tools is ALL_TOOLS` → True
- `AgentDefinition` deepcopy: `ad.tools is ALL_TOOLS` → True

No pickle/copy/deepcopy scenario loses sentinel identity. An agent cannot
silently gain or lose all tools via deserialization. (Note: `Session.__init__`
deep-copies `parent_config` at line 528, not `agent_definition`; the
`AgentDefinition` is passed through by reference. Even if it were deep-copied,
identity is preserved as shown above.)

### F. Shipped-agent audit (re-confirm) — DELIVERED

Re-confirmed in section 4 above. `backwards.md` stays `tools: []`. No shipped
agent relies on field-omission for all-tools.

## STRIDE / OWASP Notes

- **Information Disclosure / Elevation of Privilege (A01 Broken Access
  Control)**: The all-tools-by-omission behavior is a privilege grant. It is
  mitigated by (a) the visible WARN `agent_tools_default_granted` on every
  such grant, (b) the Upgrade Note in CHANGELOG.md, (c) the shipped-agent
  audit confirming no bundled agent broadens silently on upgrade, and (d) the
  `backwards.md` regression guard. The api.py alignment (C above) further
  reduces accidental-all-tools cases by making `tools=None` mean "no tools".
- **Denial of Service (via sentinel `TypeError`)**: All iteration sites are
  guarded (D above). No runtime crash vector.
- **Tampering (pickle)**: `__reduce__` resolves to the singleton; identity is
  preserved across pickle/copy/deepcopy (E above). No silent privilege change
  via deserialization.

## Scope Classification

| Finding | Classification | Action |
|---------|---------------|--------|
| All 7 round-0 mitigations delivered under sentinel | Blocking | None — approved |
| api.py `tools=None` → no tools | Blocking | Security improvement — approved |
| Sentinel non-iterability guards | Blocking | All sites guarded — approved |
| Pickle identity preservation | Related | Verified — approved |

No new backlog items.

## Verdict

**approved**

All 7 round-0 mitigations are delivered under the `ALL_TOOLS` sentinel
implementation. The sentinel refactor preserves the missing-vs-empty
distinction, the WARN event fires exactly once at WARN level, all iteration
sites are guarded against the non-iterable sentinel, pickle/copy preserve
identity, the shipped-agent audit holds (`backwards.md` stays `tools: []`),
the 8-case test matrix is in place, and the CHANGELOG upgrade note warns
plugin authors. The api.py contract alignment (`tools=None` → no tools) is a
net security improvement that closes an accidental-all-tools footgun. No new
privilege-expansion vector, no runtime crash vector, no deserialization
identity-loss vector.