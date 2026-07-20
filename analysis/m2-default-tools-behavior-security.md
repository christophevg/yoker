# Security Review: M.2 Default Tools Behavior

**Task**: M.2 Default Tools Behavior — flip the semantic of an empty/missing `tools` field in agent definitions so that empty/missing means "all registered tools" instead of "no tools".
**Date**: 2026-07-20
**Reviewer**: security-engineer
**Scope**: Security review only. No code changes.

## Executive Summary

The proposed semantic flip is **risk-material** because it changes the meaning of an existing field silently. The current contract is "absent / empty `tools` = locked down (no tools)"; the proposed contract is "absent / empty `tools` = all tools, including `write`, `update`, `git`, `mkdir`, `webfetch`, `websearch`". Built-in tools include filesystem-mutating and network-egress capabilities, so an agent author who wrote `tools: []` (or omitted the field) expecting a read-only / conversational agent would, after the flip, silently gain write, git, and network capabilities.

The strongest concern is **third-party plugin agent definitions**: an agent shipped today with `tools: []` (explicitly opting for "no tools") or with the field omitted would, after a yoker upgrade, be silently upgraded to full tool access with no change to the plugin source. That is a privilege expansion driven by an upgrade, not by the plugin author.

**Recommendation: hybrid** — require an explicit opt-in sentinel (`tools: "*"`, or a dedicated `tools: all` literal) for "all tools", keep `tools: []` / missing as "no tools", and remove the validator/loader guards that currently reject empty/missing only if the owner explicitly wants empty-means-no-tools to be expressible. If the owner insists on empty-means-all, ship it with a changelog/security note, audit all in-repo agent definitions, and add an explicit `tools: none` sentinel so "no tools" remains expressible. See §"Recommendation".

---

## 1. Threat Model: The Semantic Flip

### 1.1 Attack surface delta

| Surface | Current | After flip |
|---|---|---|
| `tools: []` in agent frontmatter | Agent gets NO tools (filter clears registry) | Agent gets ALL registered tools (write, update, git, mkdir, webfetch, websearch, …) |
| `tools:` omitted (missing field) | Loader rejects in strict mode (`ConfigurationError`) | Loader accepts; agent gets ALL tools |
| `tools: ""` (empty string) | Parses to empty tuple → no tools | All tools |
| Third-party plugin agent with missing `tools` | Currently rejected at load time | Silently loaded with full tool access |
| Validator `must specify at least one tool` | Runtime dead code (only called in tests — see §3) | Must be removed/relaxed for flip to work |

The effective runtime gates today are:
1. `src/yoker/agents/loader.py:110-116` — strict-mode rejection of a missing `tools` field.
2. `src/yoker/core/__init__.py:394-443` — `_filter_tools_by_definition`, which **clears** the tool registry when `len(self.definition.tools) == 0`.

The validator at `src/yoker/agents/validator.py:92-93` ("must specify at least one tool") is **not called from any src code path** — only from tests (`grep` confirms no production caller). It is therefore not a real runtime boundary; relying on it would be a false assurance.

### 1.2 STRIDE analysis

| Category | Threat | Current mitigation | Post-flip status |
|---|---|---|---|
| **Elevation of Privilege** | A conversational / read-only agent silently gains `write`, `git`, `webfetch` after a yoker upgrade | Empty `tools` = no tools; missing `tools` = load error | **Broken** — empty/missing = all tools |
| **Tampering** | Agent writes to files it was never intended to touch | Tool availability gated by `tools` field + PathGuardrail | Tool-availability gate removed for empty/missing; PathGuardrail still applies per-tool |
| **Information Disclosure** | Agent uses `webfetch`/`websearch` to exfiltrate context to a third-party endpoint | Network tools only present if listed in `tools` | Network tools auto-granted unless author explicitly lists tools |
| **Repudiation** | Agent performs git operations not authorized by the author | `git` only present if listed | `git` auto-granted; audit logs still record tool calls |
| **Spoofing** | Plugin agent from a third-party package impersonates a privileged agent by omitting `tools` | Missing `tools` rejected at load | **New spoofing-adjacent risk**: untrusted plugin gains full tool surface by saying nothing |
| **Denial of Service** | Agent runs `mkdir`/`write` in a loop, or floods `websearch` | Tool availability + per-tool config (rate limits, size caps) | More tools available = larger DoS surface |

### 1.3 Affected agent definition sources

1. **Shipped example agents** (`examples/agents/*.md`, `examples/plugins/demo/yoker_plugin_demo/agents/*.md`) — see §3 audit. The `backwards.md` demo agent ships with `tools: []` and would silently gain all tools.
2. **Third-party plugin agent definitions** loaded via `load_agents_from_package` → `load_agent_definitions(strict=True)`. Today a plugin author who omits `tools` gets a `ConfigurationError`. After the flip, the same plugin silently gets full tool access. **This is the highest-risk class** because yoker does not control the author's intent, and the change is introduced by a yoker upgrade, not by a plugin source change.
3. **User-authored agents** in `~/.yoker/agents/` or `--agents-definition PATH`. Same risk class as plugins but the author and the operator are typically the same person, so intent is clearer.

### 1.4 Defense in depth: is PathGuardrail sufficient?

`PathGuardrail` (`src/yoker/tools/guardrails/path.py`) still applies per-tool regardless of how the tool became available. It enforces:
- Allowed filesystem roots (`permissions.filesystem_paths`).
- Blocked path patterns (`.env`, credentials, etc.).
- Read extension allowlist, write extension blocklist, size limits, mkdir depth.
- `os.path.realpath` resolution (traversal protection).

This is meaningful defense in depth, **but**:
- It only covers filesystem tools (`read`, `list`, `write`, `update`, `search`, `existence`, `mkdir`, `git`). It does **not** cover `webfetch` or `websearch`. Network egress is gated only by `WebGuardrail` (SSRF / domain allow-deny), and only if the agent happens to call those tools.
- The guardrail enforces **where** a tool can operate, not **whether the agent should have the tool at all**. An agent author's intent ("this agent should not be able to write") is a higher-level policy that the `tools` field expresses. The flip removes that policy layer for empty/missing values.
- `git` operations: PathGuardrail validates the `path` parameter but `git` is a powerful tool whose operation enum goes beyond path containment. Granting it implicitly to every agent that forgot to list tools is a meaningful privilege expansion.

**Conclusion**: PathGuardrail is necessary but not sufficient. It narrows the blast radius but does not restore the authorization boundary the flip removes.

---

## 2. Sentinel Evaluation

### 2.1 Should "all tools" require explicit opt-in?

**Yes, strongly.** Opt-in is the safer default because:
- It is **unambiguous**: `tools: "*"` cannot be confused with "I forgot to fill this in" or "I want a conversational agent".
- It is **upgrade-stable**: a yoker upgrade does not change the meaning of an existing field value.
- It matches the principle of least privilege — an agent must declare what it can do.
- It preserves the author's ability to express "no tools" (which the flip removes).

The cost of requiring opt-in is one extra line per agent definition that wants all tools. That cost is borne by authors who explicitly want maximal capability, which is exactly the population that should be making an explicit declaration.

### 2.2 Should "no tools" remain expressible?

**Yes.** "No tools" is a legitimate and useful configuration: conversational agents, format-only agents, agents whose only job is to produce text in a particular style. The `examples/plugins/demo/yoker_plugin_demo/agents/backwards.md` agent ("replies with reversed answers") is a concrete in-repo example of an agent that is intentionally tool-less. After the flip, `tools: []` would mean "all tools", removing the author's ability to express "no tools" at all. That is a regression in expressiveness with a security consequence.

### 2.3 What does Claude Code do?

The research notes (`research/2026-04-22-coding-agent-rationale/README.md`, `research/2026-04-17-coding-agent-harness/README.md`) describe Claude Code's subagent tool as having **context isolation** and the harness as having a 4-layer permission system. The research does not document an "empty tools = all tools" semantic in Claude Code; Claude Code's subagents are described as inheriting a scoped toolset, not as gaining all tools by default. The codebase does not contain evidence that Claude Code uses an empty-means-all convention. This weakens any argument that the flip is needed for Claude Code compatibility.

---

## 3. Audit of Shipped Agent Definitions

| File | `tools` value | Intent | Post-flip behavior | Owner-confirmed? |
|---|---|---|---|---|
| `examples/agents/markdown.md` | `Read, List, Write, Update` | Explicit list | Unchanged (explicit list) | N/A |
| `examples/agents/researcher.md` | `Read, List, Update` | Explicit list | Unchanged | N/A |
| `examples/agents/main.md` | `List, Read, Write, Update` | Explicit list | Unchanged | N/A |
| `examples/plugins/demo/yoker_plugin_demo/agents/demo.md` | `existence, list, search, read, skill, yoker_plugin_demo:echo, yoker_plugin_demo:greeting` | Explicit list | Unchanged | N/A |
| `examples/plugins/demo/yoker_plugin_demo/agents/backwards.md` | `[]` | **No tools — "replies with reversed answers"** | **Gains ALL tools (write, git, webfetch, websearch, mkdir, update)** | **No — contradicts stated purpose** |

**Findings**:
- No shipped agent definition omits the `tools` field (the loader would currently reject it).
- One shipped agent definition (`backwards.md`) uses `tools: []`. Its stated purpose is a backwards-formatting conversational agent. After the flip it would silently gain write + git + network capabilities. This is **not** the owner's intent as documented in the agent's own description.
- No in-repo agent definition would benefit from the flip; the flip only creates risk for the existing shipped definitions.

**Note on `backwards.md` and the validator**: `backwards.md` parses successfully through the loader (empty list is accepted, loader line 133). The validator's "must specify at least one tool" check would reject it, but the validator is not called at runtime (see §1.1). So `backwards.md` currently runs with **no tools** (filter clears the registry). The flip would change this to all tools.

---

## 4. Risk Assessment

**Likelihood**: Medium. The flip is triggered by (a) an upgrade to yoker 1.0.0 + (b) any plugin agent definition with empty/missing `tools`. The number of third-party yoker plugins today is small, so the immediate blast radius is limited, but the convention is being set for the 1.0.0 public release and will be copied by future plugin authors.

**Impact**: High. Silent privilege expansion to filesystem-mutating and network-egress tools. For an agent whose author intended no tools, the delta is the maximum possible (from zero tools to all tools).

**Risk rating**: **High** (Medium likelihood × High impact), driven primarily by the third-party-plugin upgrade scenario and the loss of the "no tools" expression.

**OWASP mapping**:
- **A01 Broken Access Control** — the `tools` field is an authorization boundary between the agent and the tool surface; the flip silently disables it for empty/missing values.
- **A06 Insecure Design** — empty-means-all is an unsafe default for a capability declaration field; it conflates "unspecified" with "maximal".
- **A05 Injection** (secondary) — `git`, `write`, `update`, `webfetch` are tools that can be abused if granted to an agent whose prompt was not designed to handle them safely.

---

## 5. Recommendation

**Primary recommendation: hybrid / explicit opt-in.** Do not implement empty-means-all. Instead:

1. **Introduce an explicit "all tools" sentinel**: `tools: "*"` (or `tools: all`). This is the only way to express "give me everything".
2. **Keep `tools: []` / `tools: ""` / missing as "no tools"** (least privilege). This preserves the existing author intent for every shipped agent definition and for any third-party plugin that already uses `tools: []`.
3. **Relax the loader's strict-mode rejection of a missing `tools` field** to accept missing as "no tools" (currently it raises `ConfigurationError`). This is the only behavioral change needed to satisfy "agents should be loadable without an explicit tools list" — and it lands in the safe direction (no tools, not all tools).
4. **Remove or relax the validator's `must specify at least one tool` check** (it is dead code at runtime anyway, but should be consistent with the new semantic).
5. **Update `_filter_tools_by_definition`** to handle the `*` / `all` sentinel explicitly and keep the empty = no-tools branch.

This satisfies the stated M.2 goal ("agents should not crash when `tools` is missing") without the privilege-expansion risk, and it adds the expressiveness the flip was trying to provide ("all tools") in a way that cannot be triggered by accident.

**If the owner insists on empty-means-all**, the following mitigations are required (non-negotiable):

1. **Audit every shipped agent definition** before release. At minimum, fix `examples/plugins/demo/yoker_plugin_demo/agents/backwards.md` to use an explicit `tools: none` sentinel (see below) so its "no tools" intent is preserved.
2. **Introduce a `tools: none` (or `tools: []` re-flipped, or `tools: off`) sentinel** so "no tools" remains expressible after the flip. Without this, the flip is a regression in expressiveness with no recovery path for authors.
3. **Add a startup warning** when an agent definition is loaded with empty/missing `tools` and is being granted all tools, e.g. `agent_tools_default_granted`. Make the warning visible (not just `debug` level).
4. **Document the semantic change in the changelog and upgrade guide** as a security-relevant behavior change. Plugin authors must be told their `tools: []` agents will gain new capabilities.
5. **Consider a deprecation cycle**: in 1.0.x, warn + keep old semantic; in 1.1.x, flip with warning; in 1.2.x, flip silently. This gives third-party plugin authors time to add explicit `tools` lists.
6. **Re-enable the validator at runtime** (it is currently dead code). A semantic flip that relies on a validator that is never called is not actually enforced.

### Preference

The hybrid/explicit-opt-in path is strictly safer and strictly more expressive (it adds "all tools" without removing "no tools"). It costs one extra line for authors who want all tools. The empty-means-all path costs a security boundary and an expressiveness regression. **Prefer the hybrid path.**

---

## 6. Security Findings Classification

| Finding | Classification | Action |
|---|---|---|
| Semantic flip silently grants write/git/network to `tools: []` agents | Blocking | Resolve before M.2 lands — require sentinel or accept hybrid recommendation |
| `backwards.md` demo agent would gain all tools, contradicting its stated purpose | Blocking | Fix before M.2 lands (either flip direction) |
| Validator `validate_agent_definition` is dead code at runtime (never called from src) | Related | Re-wire validator into the load path as part of M.2, regardless of direction |
| Third-party plugin agents with missing `tools` silently upgrade on yoker upgrade | Blocking | Mitigate via sentinel + changelog + (preferred) hybrid semantic |
| Network tools (`webfetch`, `websearch`) have no PathGuardrail coverage; flip expands their implicit availability | Related | Document network-egress risk; ensure `WebGuardrail` defaults are safe before M.2 |
| No deprecation cycle for a behavior-changing semantic flip | Related | Add changelog + upgrade note; consider deprecation cycle |

---

## 7. Positive Observations

- `PathGuardrail` is well-designed: `os.path.realpath` for traversal, blocked patterns, extension allow/blocklists, size limits, mkdir depth. It provides solid defense in depth for filesystem tools regardless of how tools are granted.
- The current loader's strict-mode rejection of a missing `tools` field is a clear, fail-closed default.
- The `_filter_tools_by_definition` method already distinguishes the "default agent" case (`simple_name is None and namespace is None`) from named agents, which gives a clean place to insert sentinel handling.
- Built-in tool set is explicit and auditable at `src/yoker/builtin/__init__.py:44-48`.
- The agent `agents` allowlist field (spawn authorization) is a separate, well-scoped boundary that is not affected by this flip.

---

## 8. Option C evaluation (owner proposal)

Owner's proposed semantics (PR #47 comment):

1. `AgentDefinition()` — no `tools` field at all → **all tools**.
2. `AgentDefinition(tools=None)` or `AgentDefinition(tools=[])` → **no tools**.

Option C distinguishes a **missing field** (→ all tools) from an **explicit empty value** (→ no tools). This removes the sentinel (`tools: "*"`) that Option B required, at the cost of making the loader distinguish "key absent" from "key present with empty/null value".

### 8.1 Security profile vs. Option B

**Where Option C improves on the original empty-means-all proposal (and on Option B):**

- An author who writes `tools: []` explicitly now gets **no tools** — the silent-privilege-expansion risk for the most common "I explicitly want nothing" form **disappears**. This is the single largest safety gain over the original M.2 proposal and resolves the `backwards.md` regression without any change to that file.
- "No tools" remains expressible without inventing a new sentinel (Option B kept `[]` as no-tools, which is the same outcome, but Option C reaches it by a different conceptual route).
- "All tools" no longer requires authors to learn a sentinel; it is the implicit default of an unspecified capability field, which is a common YAML/TOML convention ("unset = inherit the framework default").

**Where Option C is weaker than Option B (residual risk):**

- The risk shifts from `tools: []` to **field omission**: an author who **forgets the field entirely** still silently gains all tools. Option B made "all tools" opt-in via an unambiguous sentinel; Option C makes "all tools" the default for forgetfulness.
- Whether "field absent" is a stronger author-intent signal than "field empty" is a judgement call. In practice, YAML authors rarely omit a field they meant to set; tooling and templates usually carry a `tools:` line. But "the author forgot" is a real failure mode, and it lands in the **maximally permissive** direction (all tools, including `write`, `git`, `webfetch`, `websearch`). Option B's failure mode for a forgotten field was "no tools" — fail-closed. Option C's failure mode for a forgotten field is "all tools" — fail-open.
- **STRIDE Elevation-of-Privilege**: under Option C, the privilege-expansion vector is "plugin author forgot the `tools:` line", not "plugin author wrote `tools: []`". The vector is smaller (forgetting a field is less common than writing an empty list when copying a template), but the consequence is identical to the original M.2 proposal for that subset of cases.

**Net assessment**: Option C is **strictly safer than the original M.2 empty-means-all proposal** (it removes the `tools: []` → all-tools trap and the `backwards.md` regression), and **slightly less safe than Option B** (it removes the sentinel's unambiguous opt-in for "all tools" and accepts fail-open-on-omission). The gap between Option C and Option B is small but real, and is concentrated in the "author forgot the field" scenario.

### 8.2 Third-party plugin agents on upgrade

This is the critical case for Option C.

- A plugin shipped today with `tools: []` (explicit empty) → under Option C: **still no tools**. No regression. `backwards.md` falls in this group — regression avoided.
- A plugin shipped today with **no `tools:` line at all** → today: rejected at load time (`ConfigurationError` from the strict loader, `loader.py:112-116`). After upgrading to yoker 1.0.0 with Option C: **silently gains all tools**. This **is** a privilege expansion driven by a yoker upgrade, not by a plugin source change. The plugin author never opted into all tools; they simply failed to specify, and the old loader treated that as a load error (fail-closed), while the new loader treats it as all-tools (fail-open).

So Option C does **not** fully eliminate the upgrade-driven privilege expansion — it narrows it from "all plugins with `tools: []` or missing" to "plugins with missing `tools`". The narrowing is meaningful (most careful plugin authors write `tools:` even if empty), but the residual risk is the same kind of risk as the original M.2 proposal: an upgrade grants capabilities the plugin author never asked for.

**Is "field absent" a reasonable default-open signal?** It is defensible (it matches the convention of "unspecified = framework default"), but it is the wrong default direction for a **capability** field. Capability fields should default to the least capability (least privilege), not to maximal capability. The framework default for an unspecified tools field could just as defensibly be "no tools" (Option B) as "all tools" (Option C). The choice is a policy choice, not a convention forced by YAML.

**Recommendation for this axis**: Option C is acceptable **only if** the upgrade-driven expansion for missing-field plugins is acknowledged and mitigated (see §8.4).

### 8.3 Feasibility / YAML parsing pitfalls

The loader must distinguish four forms:

| Form | YAML parse result | Distinguishable from key-absent? |
|---|---|---|
| (no `tools:` line) | `frontmatter` dict has no `"tools"` key | Yes — `"tools" not in frontmatter` |
| `tools:` (bare key, no value) | `None` (key present, value `None`) | Yes — `"tools" in frontmatter and frontmatter["tools"] is None` |
| `tools: null` / `tools: ~` | `None` (key present, value `None`) | Yes — same as above |
| `tools: ""` | `""` (empty string) | Yes — `"tools" in frontmatter` |
| `tools: []` | `[]` (empty list) | Yes — `"tools" in frontmatter` |

**Conclusion: Option C is implementable as specified.** `yaml.safe_load` preserves the distinction between "key absent" and "key present with `None`/empty value". The current loader uses `frontmatter.get("tools")`, which **collapses** absent and `None` into the same `None` return — so implementing Option C requires changing the loader to test `"tools" in frontmatter` before reading the value. That is a one-line change and is reliable.

**Pitfalls to flag for the implementation:**

1. **`tools:` with no value must be classified as "explicit empty" → no tools**, not as "missing". An author who writes `tools:` (a bare key) has signalled awareness of the field; treating that as no-tools matches the owner's stated semantics (`tools: None` → no tools). The loader must use `key in frontmatter`, not `frontmatter.get(key) is None`, to distinguish.
2. **`tools: null` and `tools: ~`** parse to `None` and must be treated identically to `tools:` (explicit empty → no tools), per the owner's `tools: None` rule. This is the same code branch as pitfall #1.
3. **Default agent (no AgentDefinition)**: the existing `_filter_tools_by_definition` already short-circuits when `simple_name is None and namespace is None` (the in-memory default agent), keeping all tools. Option C must preserve this branch — it is not the same case as a loaded agent definition with missing `tools`, and conflating them would re-introduce ambiguity.
4. **Schema default**: `AgentDefinition.tools` currently defaults to `()` (empty tuple). Under Option C, `()` must mean "no tools" (which it already does at runtime via the `len == 0` branch in `_filter_tools_by_definition`), and the "all tools" signal must be carried by a **separate** flag (e.g. `tools_unspecified: bool`) or by a sentinel tuple value, because `tuple[str, ...]` cannot represent "absent" — `()` is already taken for "explicitly empty". This is the single most important implementation detail: **the dataclass field cannot by itself carry Option C's three states (missing / empty / list)**. The loader must set a side-channel flag (e.g. `tools_unspecified=True` when the key was absent) and the runtime filter must consult that flag.
5. **Plugin manifest agent definitions** (loaded via `load_agents_from_package` → `parse_agent_definition`): the same `"tools" in frontmatter` test must be applied there, so plugin agents get the same Option C semantics as user-authored agents. This is the path that drives the upgrade-driven privilege expansion in §8.2.
6. **`tools: ""`** (empty string) currently parses to an empty tuple (loader line 121-124). Under Option C this is "explicit empty → no tools", which the current code already produces. No change needed, but the test must confirm `""` is treated as explicit, not absent.
7. **Comments-only `tools:` block** (e.g. `tools:\n  # todo`) — `yaml.safe_load` parses this as `None` (key present, no value). Under Option C: no tools. Implementer should add a test for this form.

**Bottom line**: Option C is implementable, but it is **not** implementable as "just flip the empty branch". It requires a side-channel flag on `AgentDefinition` to carry the missing-vs-empty distinction, because the existing `tools: tuple[str, ...] = ()` field cannot represent three states on its own. This is the main implementation hazard the owner should be aware of.

### 8.4 Endorsement and required mitigations

**Position: conditional endorsement of Option C**, with the following non-negotiable mitigations. Option B remains the strictly-safer choice; Option C is acceptable because it eliminates the most common silent-expansion vector (`tools: []` → all tools) and the `backwards.md` regression, at the cost of a residual upgrade-driven expansion for missing-field plugins that must be explicitly addressed.

**Required mitigations under Option C:**

1. **Side-channel flag on `AgentDefinition`** (e.g. `tools_unspecified: bool = False`) set by the loader when `"tools" not in frontmatter`. The runtime filter (`_filter_tools_by_definition`) consults this flag: `tools_unspecified=True` → keep all tools; `tools_unspecified=False` and `tools == ()` → clear the registry. Without this, Option C cannot be expressed in the dataclass and the loader's `frontmatter.get("tools")` will silently collapse the two cases back together.
2. **Loader change**: replace the `frontmatter.get("tools")` check with `"tools" in frontmatter` for the absent-vs-empty distinction. Treat `None`, `""`, `[]`, and `~` as "explicit empty → no tools" (per owner's spec).
3. **Startup warning when all-tools is granted by default-omission**: emit a `WARN`-level log event `agent_tools_default_granted` with the agent name and source path whenever `tools_unspecified=True` results in all tools being granted. This must be visible (not `debug`), so operators can see when a plugin agent gained all tools by omission. This is the single most important compensating control for the §8.2 upgrade-expansion risk.
4. **Audit shipped agent definitions for missing `tools`**: every shipped agent definition in `examples/` and `src/yoker/` must have an explicit `tools:` line. If any shipped agent legitimately wants all tools, it should use an explicit opt-in form — under Option C the cleanest such form is `tools: [read, list, write, update, git, mkdir, existence, search, webfetch, websearch, skill]` (explicit list) or a documented "all tools" marker. **No shipped agent definition should rely on field-omission to mean "all tools"** — that pattern is exactly what the §8.2 upgrade risk warns against, and shipping it in-repo would set the wrong precedent for plugin authors.
5. **Re-wire the validator into runtime** (already flagged in §6). Under Option C, the validator's `must specify at least one tool` check must be removed (it contradicts Option C), but the rest of `validate_agent_definition` should be called from the production load path, not only from tests. A semantic change that depends on a validator that is never called is not actually enforced.
6. **Changelog and upgrade note** explicitly calling out: "Plugin agents shipped without a `tools:` field will now gain all built-in tools on upgrade to yoker 1.0.0. Plugin authors should add an explicit `tools:` line to every agent definition. Use `tools: []` to declare a tool-less agent." This is security-relevant and must be in the upgrade guide, not just the changelog.
7. **`backwards.md`** stays at `tools: []` — under Option C this is "no tools", preserving its stated purpose. No file change required. (This is the concrete win Option C has over the original M.2 proposal.)
8. **Test matrix** (acceptance criteria): the loader/runtime must be tested for all of: (a) key absent → all tools + warning logged; (b) `tools:` bare → no tools; (c) `tools: null` → no tools; (d) `tools: ~` → no tools; (e) `tools: ""` → no tools; (f) `tools: []` → no tools; (g) `tools: [read]` → only `read`; (h) default agent (no definition) → all tools, no warning.

### 8.5 Revised file list under Option C

- `src/yoker/agents/schema.py` — add `tools_unspecified: bool = False` to `AgentDefinition` (or equivalent side-channel). Update docstring.
- `src/yoker/agents/loader.py` — replace `frontmatter.get("tools")` with `"tools" in frontmatter` test; set `tools_unspecified=True` when key absent; treat `None`/`""`/`[]`/`~` as explicit empty → `tools=()`. Lines 110-132.
- `src/yoker/core/__init__.py` — `_filter_tools_by_definition` (lines 394-443): add branch for `tools_unspecified=True` → keep all tools + emit `agent_tools_default_granted` warning; keep `len(tools) == 0 and not tools_unspecified` → clear registry.
- `src/yoker/agents/validator.py` — remove the `must specify at least one tool` check (lines 92-93); re-wire the rest of the validator into the load path.
- `src/yoker/agents/registry.py` or loader caller — call `validate_agent_definition` at load time (currently only called from tests).
- `examples/agents/*.md` and `examples/plugins/demo/yoker_plugin_demo/agents/*.md` — audit; ensure no shipped agent relies on field-omission for all-tools. `backwards.md` unchanged.
- `tests/agents/test_loader.py` (or equivalent) — add the 8-case test matrix from §8.4 item 8.
- `CHANGELOG.md` / upgrade notes — document the upgrade-driven expansion for missing-field plugins.
- `README.md` / agent authoring docs — document the three-state semantic: omit → all tools (with warning), `tools: []`/`null`/`~`/`""` → no tools, explicit list → those tools.

### 8.6 Recommendation summary

- **Option B (sentinel) remains strictly safer** because its failure mode for a forgotten field is fail-closed (no tools), while Option C's failure mode for a forgotten field is fail-open (all tools). The sentinel is unambiguous and is not affected by YAML's None-vs-absent collapse.
- **Option C is acceptable with the mitigations in §8.4**. It eliminates the `tools: []` → all-tools trap (the most common form of silent expansion) and the `backwards.md` regression, and is implementable with a side-channel flag. The residual risk (missing-field plugins gain all tools on upgrade) is real but smaller than under the original M.2 proposal, and is addressed by the startup warning, the changelog note, and the audit of shipped agents.
- **If the owner wants Option C without the side-channel flag**: not viable. The dataclass `tools: tuple[str, ...] = ()` field cannot represent three states. Attempting to use `None` as "all tools" inside the dataclass (treating `None` as all-tools and `()` as no-tools) would invert the owner's spec (the owner said `tools: None` → no tools), and would re-introduce the YAML-collapse pitfall (bare `tools:` parses to `None`, which would then mean all-tools — the opposite of the owner's intent). The side-channel flag is non-negotiable for Option C.
- **Default direction**: if the owner is undecided, Option B is the recommended choice on security grounds. Option C is the recommended choice on ergonomics grounds (no sentinel to learn). The security cost of Option C is the §8.2 upgrade-expansion risk; the ergonomic cost of Option B is one extra line for authors who want all tools.