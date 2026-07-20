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