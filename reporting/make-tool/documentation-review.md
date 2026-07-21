# PR #48 — `make` Tool Documentation Review (Stage D)

**Date:** 2026-07-21
**Reviewer:** end-user-documenter
**Scope:** User-facing and agent-facing documentation for the `make` built-in tool (MBI-009 T1, PR #48), including R5 env-inheritance residual risk.

---

## Section 1 — README completeness

**Verdict: incomplete.**

`README.md` does not mention the `make` tool at all. Concretely:

- The **Features / Current Features** checklist (lines 472-483) lists every other built-in tool (`read`, `write`, `update`, `list`, `search`, `existence`, `mkdir`, `git`, `websearch`, `webfetch`, `agent`, `skill`) but has **no entry for `make`**.
- The **Configuration** section (lines 599-604) shows a `[tools.read]` example and references `examples/yoker.toml` as the "full configuration reference", but neither README nor `examples/yoker.toml` contains a `[tools.make]` section. The example config file lists `[tools.list]`, `[tools.read]`, `[tools.write]`, `[tools.update]`, `[tools.search]`, `[tools.agent]`, `[tools.git]`, `[tools.mkdir]`, `[tools.websearch]`, `[tools.webfetch]`, `[tools.content_display]` — **no `[tools.make]`**.
- The config schema (`allowed_env_vars`, `max_env_var_bytes`, `timeout_ms`, `max_output_kb`) is **not documented** in README.
- The per-target allowlist TOML shape (Option A from the approved design) is **not shown** in README.
- The env-inheritance residual risk (R5) is **not documented** in README.

A new built-in tool is a user-visible feature. Operators reading README cannot discover that `make` exists, how to configure it, or that recipes inherit the yoker process env.

---

## Section 2 — Inline docs (make.py, env.py, MakeToolConfig)

### `src/yoker/builtin/make.py`

**Module docstring:** present and adequate. States the guardrails (target validation, per-target env_var allowlist + framework hard-denylist, output truncation, process-group kill on timeout). Does **not** mention R5 env-inheritance residual risk — see Section 4.

**Function docstring:** `"""Execute a Makefile target via ``make <target>``."""` — **insufficient per the review criteria**. The criteria require the function docstring to document parameters, return value, and the security model (target validation, env_vars allowlist + denylist + value validation). The current one-liner documents none of:
- Parameters: `target`, `ctx`, `cwd`, `timeout_ms`, `env_vars` (types, semantics, defaults).
- Return: `ToolResult` with `result` dict shape `{exit_code, stdout, stderr, truncated}`.
- Security model: target regex + forbidden chars + leading-`-` rejection (R2/R3); per-target allowlist deny-by-default + non-configurable hard denylist + value rules (R5); PathGuardrail on `cwd` (R1); process-group kill on timeout (R4); output truncation per stream.
- Config clamping: `timeout_ms` is clamped to `min(timeout_ms, config.timeout_ms)` with a 1s floor.

The parameter semantics are partially conveyed by the `Annotated[..., Text(...)]` / `PathArg(...)` markers (which become the model-facing tool schema), but the function docstring itself does not cover them, and the return shape / security model is not described anywhere a developer reading the function would see it.

### `src/yoker/tools/guardrails/env.py`

**Module docstring:** present and good. States the purpose (non-configurable hard denylist, enforced regardless of operator allowlist), the rationale (bypass framework trust gates, code injection, network/credential redirect), and the pattern (mirrors `path.py`).

**`is_denied_env_var` docstring:** present, clear.

**`validate_env_vars` docstring:** present and thorough — documents return contract (`(name, error) | None`), the caller obligation (MUST return `ToolResult(success=False)` without spawning on failure), and the per-entry checks (allowlist, denylist, str type, byte length, NUL, newlines, UTF-8). This is the strongest docstring in the change.

### `src/yoker/config/__init__.py` — `MakeToolConfig`

**Docstring:** present and **matches the approved design sketch**. Documents all four fields per the owner-approved Option A response:
- `timeout_ms` — default timeout in ms.
- `max_output_kb` — max per-stream output in KB.
- `allowed_env_vars` — per-target allowlist, keys are Makefile target names, deny-by-default, empty dict = all env vars denied for all targets.
- `max_env_var_bytes` — max byte size per env var value.

`__post_init__` has a one-line docstring. No gap here.

---

## Section 3 — CLAUDE.md module structure

**Verdict: out of sync.**

`CLAUDE.md`'s module-structure tree does not list either new file:

- `builtin/` section (lines 76-88) lists `read.py`, `write.py`, `update.py`, `list.py`, `mkdir.py`, `existence.py`, `search.py`, `git.py`, `webfetch.py`, `websearch.py`, `skill.py` — **no `make.py`**.
- `tools/guardrails/` section (lines 134-136) lists `__init__.py` and `path.py` — **no `env.py`**.
- The `builtin/__init__.py` comment (line 77) says "declaring read, write, git, websearch, ..." — `make` is not mentioned (the `...` ellipsis technically covers it, but every other tool is listed explicitly).
- The prose at line 235 listing built-in tools (`read`, `write`, `git`, `websearch`, etc.) does not mention `make`.

Per the CLAUDE.md conventions, the module structure should be updated when new modules are added. Both `builtin/make.py` and `tools/guardrails/env.py` are new modules and should be listed.

---

## Section 4 — R5 env-inheritance residual risk documentation

**Verdict: not documented anywhere users will see it.**

The owner's R5 requirement (from the security review, quoted in the per-target-allowlist response brief) was:

> "Document the env-inheritance residual risk — Makefile recipes inherit the yoker process env, so any secret in env is readable by recipes. Operators should load sensitive API keys from a secrets store when running untrusted agents."

Where R5 could plausibly be documented, and the status:

| Location | Status |
|----------|--------|
| `README.md` Features / Configuration | Not present |
| `README.md` Security note near API-key handling | Not present |
| `docs/guides/` | No guide entry for `make` tool exists |
| `docs/` (any page) | No mention of `make` tool or env inheritance |
| `src/yoker/builtin/make.py` module docstring | Mentions "per-target env_var allowlist + framework hard-denylist" but **not** that recipes inherit the yoker process env, and **not** the operator guidance about secrets stores for untrusted agents |
| `src/yoker/builtin/make.py` function docstring | Not present (one-liner only) |
| `MakeToolConfig` docstring | Documents the allowlist mechanics but not the residual risk |
| `examples/yoker.toml` | No `[tools.make]` section, no warning comment |

The residual risk is **not documented in any location an operator or developer will encounter**. The `env.py` guardrail and per-target allowlist mitigate the *agent-supplied* env_vars surface, but they do **not** address the inherited `os.environ` — `make.py` line 91 explicitly does `env = {**os.environ, **validated_env}`, so any secret already in the yoker process env (e.g. `ANTHROPIC_API_KEY` exported in the shell that launched yoker) is readable by the Makefile recipe. This is exactly the residual risk R5 asks to be documented, and it is absent.

This is the most significant gap in the review, because R5 was an explicit owner requirement attached to this PR.

---

## Section 5 — Gaps and recommendations

Ordered by impact.

### G1. R5 env-inheritance residual risk — not documented (BLOCKER)

**Action:** Add a "Security: env inheritance" note to the `make` tool documentation covering:
1. Makefile recipes inherit the yoker process environment (`os.environ`).
2. Any secret in the yoker process env (API keys, tokens) is readable by the recipe.
3. The per-target allowlist + hard denylist govern only **agent-supplied** `env_vars`; they do **not** filter the inherited env.
4. Operator guidance: when running untrusted agents, load sensitive API keys from a secrets store / avoid exporting them into the shell env that launches yoker.

Recommended placements (at least one, preferably two):
- `src/yoker/builtin/make.py` module docstring (developer-facing, co-located with the code that does `env = {**os.environ, **validated_env}`).
- `README.md` Configuration section or a new "Tool security" note near the existing API-key handling note (operator-facing).

### G2. README does not mention the `make` tool (BLOCKER)

**Action:** Add a `[x] make tool - ...` entry to the Features / Current Features checklist (line ~483, alongside `git`, `websearch`, etc.), with a one-line description that includes the guardrails (target validation, per-target env_var allowlist, output truncation, process-group kill on timeout).

### G3. `[tools.make]` config schema not documented (BLOCKER)

**Action:** Add a `[tools.make]` block to `examples/yoker.toml` (the "full configuration reference" README points to) showing all four fields with comments, including the per-target allowlist subsection form:

```toml
[tools.make]
timeout_ms = 300000
max_output_kb = 100
max_env_var_bytes = 4096

# Per-target env_var allowlist (deny-by-default). Targets not listed
# receive no agent-supplied env vars. The framework hard-denylist
# (YOKER_*, LD_*, MAKEFLAGS, *_API_KEY, ...) is enforced regardless.
[tools.make.allowed_env_vars]
test = ["TEST"]
lint = ["LINT_FLAGS", "LINT_CONFIG"]
```

And add a short "Make tool" subsection in README's Configuration section pointing to it, including the R5 residual-risk note (G1).

### G4. `make.py` function docstring insufficient (NON-BLOCKER)

**Action:** Expand the `make()` function docstring to document:
- Parameters (`target`, `ctx`, `cwd`, `timeout_ms`, `env_vars`) with types and semantics.
- Return (`ToolResult` with `result` dict `{exit_code, stdout, stderr, truncated}`).
- Security model: R1 (PathGuardrail on `cwd`), R2/R3 (target regex + forbidden chars + no leading `-`), R4 (`start_new_session` + `os.killpg` on timeout), R5 (per-target allowlist + hard denylist + value validation on `env_vars`).
- Config clamping: `timeout_ms` clamped to `min(timeout_ms, config.timeout_ms)` with a 1s floor.

### G5. CLAUDE.md module structure out of sync (NON-BLOCKER)

**Action:** Update the `builtin/` tree in `CLAUDE.md` to add:
```
│   ├── make.py              # make: execute Makefile targets with env_var guardrails
```
And update the `tools/guardrails/` tree to add:
```
│   │   ├── env.py           # EnvVarGuardrail (per-tool allowlist + hard denylist)
```
Optionally update the `builtin/__init__.py` comment and the line-235 prose to mention `make` explicitly.

### G6. No docs/ guide entry for the `make` tool (OPTIONAL)

The `docs/guides/` directory has getting-started guides but no per-tool reference. This is consistent with the existing pattern (other tools like `git`, `websearch` also lack dedicated guide pages and are only documented in README + `examples/yoker.toml`). **Not a gap relative to the existing docs standard**, but if the project wants a per-tool reference page, `make` is a good candidate given its security surface. Recommend deferring unless the project standard changes.

---

## Section 6 — Verdict

**rejected:**

The `make` tool implementation is solid and `MakeToolConfig` + `env.py` docstrings meet the approved design sketch, but the documentation does not satisfy the owner's R5 requirement or the README completeness criteria for a new built-in tool. Specifically, before this PR can be approved:

1. **G1 (R5 residual risk):** Add the env-inheritance residual-risk note to at least one user-facing location (README) and to the `make.py` module docstring. This is the owner's explicit R5 requirement and is currently absent everywhere.
2. **G2 (README Features):** Add a `make` tool entry to the Features / Current Features checklist.
3. **G3 (Config schema):** Add a `[tools.make]` block (with `allowed_env_vars` subsection example) to `examples/yoker.toml` and a short README subsection pointing to it (including the R5 note).

Recommended (non-blocking) but should be addressed in the same PR for consistency:

4. **G4:** Expand the `make()` function docstring to document parameters, return shape, and the R1-R5 security model.
5. **G5:** Update `CLAUDE.md` module structure to list `builtin/make.py` and `tools/guardrails/env.py`.

G6 (docs/ guide page) is optional and deferred.

---

## Round 1 scoped re-run

**Date:** 2026-07-21
**Reviewer:** end-user-documenter
**Scope:** Verify the developer's fixes for the 3 blocking gaps (G1, G2, G3) and 2 non-blocking items (G4, G5) from round 0.

### G1. R5 env-inheritance residual risk — FIXED

Evidence in two locations, as recommended:

**Developer-facing** — `src/yoker/builtin/make.py` module docstring (lines 22-27):

> Residual risk (R5): the subprocess env is ``{**os.environ, **validated_env}``,
> so Makefile recipes inherit the yoker process env. Any secret present in
> yoker's env (API keys, tokens) is readable by recipes. The per-target
> allowlist + hard denylist only govern agent-supplied ``env_vars`` — they do
> not filter the inherited env. Operators should load sensitive API keys from
> a secrets store (not plain env vars) when running untrusted agents.

**Operator-facing** — `README.md` "make tool configuration" subsection (lines 634-639):

> **Env-inheritance residual risk:** Makefile recipes inherit the yoker
> process env, so any secret present in yoker's env (API keys, tokens) is
> readable by recipes. The per-target allowlist and framework hard-denylist
> only govern agent-supplied `env_vars` — they do not filter the inherited
> env. Load sensitive API keys from a secrets store (not plain env vars)
> when running untrusted agents.

Both notes clearly communicate all four required points: (1) recipes inherit `os.environ`, (2) secrets in env are readable, (3) the allowlist governs only agent-supplied vars, (4) operator guidance to use a secrets store for untrusted agents.

### G2. README Features entry — FIXED

`README.md` line 480 (Features / Current Features checklist):

> - [x] `make` tool - Execute Makefile targets (e.g., `make check`, `make test`) with target validation, per-target env var allowlist, and process-group timeout enforcement.

Placed alongside the other built-in tool entries, matching the format and mentioning the guardrails.

### G3. `[tools.make]` config schema — FIXED

**`examples/yoker.toml`** lines 104-116:

```toml
[tools.make]
enabled = true
timeout_ms = 300000
max_output_kb = 100
max_env_var_bytes = 4096

# Per-target env var allowlist (deny-by-default). Keys are Makefile target
# names; values are the env var names that target is permitted to receive.
# Targets not listed deny all env vars. A framework hard-denylist
# (yoker.tools.guardrails.env) is enforced regardless of this allowlist.
[tools.make.allowed_env_vars]
test = ["TEST"]
lint = ["LINT_FLAGS", "LINT_CONFIG"]
```

All four fields are documented (`timeout_ms`, `max_output_kb`, `max_env_var_bytes`, plus the `enabled` flag consistent with other tool blocks). The subsection form of `allowed_env_vars` is shown.

**`README.md`** "make tool configuration" subsection (lines 607-632) documents the schema inline, including both forms of `allowed_env_vars`:

- Subsection form (lines 613-624): `[tools.make.allowed_env_vars]` with `test = ["TEST"]`, `lint = ["LINT_FLAGS", "LINT_CONFIG"]`.
- Inline-table form (lines 628-632): `allowed_env_vars = {test = ["TEST"], lint = ["LINT_FLAGS", "LINT_CONFIG"]}`.

All four required fields are present and accurate. Both Option A TOML shapes are shown clearly.

### G4. `make()` function docstring expanded — FIXED (non-blocking)

`src/yoker/builtin/make.py` lines 66-89 now documents:
- All five parameters (`target`, `ctx`, `cwd`, `timeout_ms`, `env_vars`) with types, semantics, and defaults.
- The `ToolResult` return shape: `{"exit_code": int, "stdout": str, "stderr": str, "truncated": bool}` and the `success`/`error` semantics.
- Timeout clamping to `[1000, make_config.timeout_ms]`.
- A reference to the module docstring for the full security model including R5.

### G5. CLAUDE.md module structure — FIXED (non-blocking)

`CLAUDE.md` line 86 now lists:

> `│   ├── make.py              # make: Makefile target execution`

`CLAUDE.md` line 137 now lists:

> `│   │   ├── env.py           # EnvGuardrail (env var allowlist + hard denylist + value validation)`

Both new modules are present in the tree.

### Verdict — approved

All three blocking gaps (G1, G2, G3) are fixed with quoted evidence in the expected locations. Both non-blocking items (G4, G5) are also addressed. The R5 env-inheritance residual risk is clearly communicated to both operators (README) and developers (module docstring). The `[tools.make]` config schema is accurate and complete, with both the inline-table and subsection forms of `allowed_env_vars` shown. G6 (docs/ guide page) remains optional and deferred, consistent with the existing docs standard.