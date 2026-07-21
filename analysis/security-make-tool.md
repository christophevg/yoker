# Security Analysis: `make` Tool

**Document Version**: 1.0
**Date**: 2026-07-21
**Status**: Final
**Scope**: Threat model and mitigation review for the proposed `make` built-in tool (MBI-009 T1).
**Reference proposal**: `analysis/mbi-toolset-coverage.md` §7.1 and TODO.md T1.1

## 1. Owner's Proposal (quoted)

From `analysis/mbi-toolset-coverage.md` §7.1 and TODO.md T1.1:

> ```python
> async def make(
>   target: str,            # Makefile target (e.g. "check", "test", "lint")
>   ctx: ToolContext,
>   cwd: Annotated[str, PathArg("Working directory")] = ".",
>   timeout_ms: int = 300000,
> ) -> ToolResult:
> ```
>
> - `subprocess.run(["make", target], cwd=cwd, ...)` — list args, no shell
> - PathGuardrail on `cwd` (must be within project root)
> - Output truncation (default 100KB)
> - Timeout enforcement (default 5 minutes)
> - Target validation: reject targets with shell metacharacters (`;`, `|`, `&`, `$`, backticks)
> - No env var injection (make reads its own environment)

Acceptance criteria (T1.1):
- `make(target="check")` executes and returns output
- `make(target="rm -rf /")` is rejected (shell metacharacter in target)
- Output exceeding 100KB is truncated with a truncation notice
- Timeout is enforced
- `cwd` outside project root is rejected

## 2. Threat Model

### 2.1 Assets

| Asset | Sensitivity | Exposure via `make` tool |
|-------|-------------|--------------------------|
| Filesystem within project root | High | Makefile targets can read/write/delete files in `cwd` tree |
| Shell execution capability | Critical | Any Makefile recipe can spawn arbitrary shell |
| Process environment (env vars) | High | Makefile recipes can read inherited env vars |
| System resources (CPU, disk, memory) | Medium | Long-running or runaway targets |
| Yoker process secrets (API keys in env) | High | Makefile recipes can exfiltrate via `printenv` / network |
| Network egress | Medium | Makefile recipes can `curl`/`wget` arbitrary URLs |

### 2.2 Adversaries

| Actor | Capability | Risk Level |
|-------|------------|------------|
| Compromised / malicious agent | Controls `target` string and `cwd`; can edit project files (incl. Makefile if not protected) | High |
| Prompt-injected LLM | Manipulates tool parameters via instruction | Medium |
| External attacker (MITM on filesystem) | Modifies Makefile out-of-band | Low (out of scope for this tool) |

### 2.3 Attack Surfaces

1. **`target` parameter** — passed as `argv[1]` to `make`. With list-args + no shell, the only injection vector is into `make`'s own argument parser (flags) or target resolution.
2. **`cwd` parameter** — controls where `make` runs; can scope Makefile selection and recipe file writes.
3. **Makefile content itself** — `make` executes recipes that run arbitrary shell. The tool cannot validate recipe content; this is mitigated at the `write`/`update` layer via `protected_files` (T12, in scope of the same release but separate task).
4. **Inherited environment** — `make` and its recipes inherit yoker's full env.
5. **Child process tree** — `make` spawns recipe commands; timeout must kill the whole tree, not just `make`.
6. **Output stream** — unbounded stdout/stderr can flood context and mask errors.

## 3. Assessment of Owner-Proposed Mitigations

### 3.1 List-args `subprocess.run` (no `shell=True`) — ADEQUATE

The proposal `subprocess.run(["make", target], ...)` is the correct pattern. No shell parses the target, so `;`, `|`, `&`, backticks, `$()`, `>`, `<` have no shell semantics. This is the foundational control and it holds. Consistent with `git` tool (`builtin/git.py:344`).

### 3.2 Target validation: reject `;`, `|`, `&`, `$`, backticks — ADEQUATE BUT INCOMPLETE

**Adequate**: With list-args, these characters have no shell meaning to `make`'s argv parser, so rejecting them is belt-and-suspenders. Harmless and consistent with `git`'s `FORBIDDEN_CHARS` (`builtin/git.py:77`).

**Gap (Low severity, recommend fix)**: The proposed character set is missing three entries that `git` already blocks and that have real meaning in `make`'s own parser:
- `\n` and `\r` — GNU make treats a newline in a target name as a target separator and, worse, can interpret what follows as a new makefile directive/recipe line. With list-args this is partially mitigated, but make does parse its argv for newlines in some code paths. `git` blocks these explicitly.
- `\x00` — NUL in argv is rejected by POSIX execve anyway; defense in depth.

**Recommendation**: Reuse `git`'s `FORBIDDEN_CHARS` verbatim (`\n`, `\r`, `\x00`, backtick, `$`, `|`, `;`, `&`). One constant, shared semantics. No new abstraction needed — copy the frozenset.

### 3.3 Reject leading `-` (flag injection) — GAP, RECOMMEND FIX

**Documented gap, earned justification**: GNU make interprets a leading `-` in argv[1] as a flag, not a target. Concrete exploits against `make(target="-<flag>")`:
- `make(target="--eval=pwn:\\n\\t rm -rf /")` injects an ad-hoc target with an arbitrary recipe. `--eval` is a documented GNU make flag that evaluates makefile code passed on the command line. This **bypasses the `protected_files` guardrail** because no Makefile edit is needed — the malicious recipe is supplied via argv.
- `make(target="-i")` puts make in "ignore errors" mode, changing build semantics.
- `make(target="-j")` enables unbounded parallelism (DoS amplifier).
- `make(target="-C /tmp")` changes directory away from the guarded `cwd`.

The owner's proposal does not reject leading `-`. `git` does (`builtin/git.py:332`: `if value.startswith("-"): raise ValueError(...)`).

**Recommendation**: Reject `target` that starts with `-` (after `str.strip()`). Also reject empty/whitespace-only target. This is a one-line check, not a new abstraction. The owner's proposal is the default; this is a concrete, named bypass (`--eval`) that the proposal does not cover.

### 3.4 `cwd` PathGuardrail — GAP, RECOMMEND FIX (blocking)

**Documented gap, earned justification**: `PathGuardrail.validate()` (`tools/guardrails/path.py:97-99`) short-circuits for any tool name not in `_FILESYSTEM_TOOLS`:

```python
_FILESYSTEM_TOOLS = frozenset({"read", "list", "write", "update", "search", "existence", "mkdir", "git"})
...
if tool_name not in _FILESYSTEM_TOOLS:
    return ValidationResult(valid=True)
```

The `make` tool is not in this set. Therefore the `Annotated[str, PathArg(...)]` annotation on `cwd` is a **no-op** — the guardrail will return `valid=True` for any `cwd`, including `/etc`, `/`, or `../../../`. The acceptance criterion "cwd outside project root is rejected" will fail unless this is fixed.

Additionally, `PathGuardrail.validate()` extracts the path from `value.get("path", "")` when given a dict, or treats `value` as the path string when given a string. The harness dispatch (`core/_processing.py:531-542`) passes the raw parameter value, so for the `cwd` parameter it will pass the cwd string directly — `PathGuardrail` will resolve and root-check it correctly **only if `make` is added to `_FILESYSTEM_TOOLS`**.

**Recommendation (blocking)**: Add `"make"` to `_FILESYSTEM_TOOLS` in `src/yoker/tools/guardrails/path.py:30-32`. This is a one-line change to an existing constant. Without it, the headline `cwd` security claim is unenforced. Flag as Blocking for T1.1.

### 3.5 Output truncation (default 100 KB) — ADEQUATE

Consistent with other tools. 100 KB is reasonable for `make` output (compile errors, test summaries). Recommend truncation preserves head + tail with a truncation marker, so the agent sees both the failing target start and the error. This is a quality nit, not a security gap — the owner's proposal is adequate as stated.

### 3.6 Timeout (default 5 min) — ADEQUATE WITH ONE RESIDUAL RISK

**Adequate**: 5 min matches `pytest`/`lint` defaults and covers normal `make check` runs.

**Residual risk (Low)**: `subprocess.run(timeout=...)` raises `TimeoutExpired` and calls `Popen.kill()` on the `make` process, but `make`'s child processes (recipe shells) are **not** in the same kill chain unless `start_new_session=True` (POSIX) or `creationflags=CREATE_NEW_PROCESS_GROUP` (Windows) is set. A malicious or buggy recipe can spawn a long-lived child that survives the timeout and keeps running on the host.

**Recommendation (Low severity)**: Pass `start_new_session=True` to `subprocess.run` and, on `TimeoutExpired`, kill the whole process group. This is a 3-line addition. If the owner prefers the simpler `subprocess.run(timeout=...)` form, the residual risk is: orphaned recipe children can outlive the timeout. Acceptable for a 1.0 trust model where the Makefile is `protected_files`-guarded; flag explicitly in residual risks.

### 3.7 No env var injection (inherit env) — ADEQUATE AS DEFAULT, RESIDUAL RISK NOTED

The owner's proposal: make inherits the yoker process environment. This is the right default — scrubbing env breaks most Makefiles (PATH, HOME, locale, venv-aware tools like `uv`).

**Residual risk (Medium, accept explicitly)**: Any secret the yoker process holds in its environment (e.g., `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `OPENAI_API_KEY`) is readable by any Makefile recipe via `printenv`, `env`, or `$$VAR` in a recipe. A malicious Makefile (or a recipe that calls `curl` to an attacker-controlled host) can exfiltrate these secrets. The `protected_files` guardrail reduces but does not eliminate this — `protected_files` blocks the agent from editing the Makefile, but does not block:
- Pre-existing malicious Makefile content (supply-chain)
- Targets that `include` other files (e.g. `.env`-like files) the agent CAN edit
- Targets that shell out to project scripts the agent CAN edit (e.g. `scripts/build.sh`)

**Recommendation**: Do not add env scrubbing (it breaks more than it protects). Instead:
1. Document the residual risk in the tool's security model.
2. Recommend (separate task) that yoker's sensitive API keys be loaded from a secrets store, not passed via env, when running untrusted agents. This is an architecture-level concern outside the scope of T1.1.
3. Owner accepts the residual risk explicitly (see §5).

### 3.8 Recursive make / Makefile arbitrary shell — OUT OF SCOPE FOR `make` TOOL

GNU make recipes are shell. The `make` tool cannot constrain what a recipe does — that is the entire point of `make`. This is correctly mitigated at the `write`/`update` layer via `protected_files` (T12). The `make` tool's job is target-name validation + path scoping + resource limits, not recipe auditing.

**Confirmation**: This is out of scope for the `make` tool itself. The mitigation is T12 (`protected_files`). The two tasks are paired; T1.1 should ship alongside T12, or the residual risk is that an agent can `write` a malicious Makefile and then `make(target="pwn")`. Recommend sequencing: T12 should not land after T1.1 by more than one release cycle.

### 3.9 `=` in target (make variable override) — NOTED, NOT RECOMMENDED

GNU make treats `make FOO=bar` as a variable override, and `make target=foo` similarly. A target containing `=` (e.g. `make(target="CFLAGS=-O0")`) would override a make variable rather than run a target. This is a semantic confusion, not a security bypass — the agent can already run `make check` and a malicious CFLAGS only affects the build, not yoker's security boundary. The owner's proposal does not address `=` and I do not recommend adding a check for it; it would break legitimate uses like `make(test="tests/test_foo.py")` (TODO.md's own acceptance criterion: `make test TEST=tests/test_foo.py`).

Wait — re-reading the TODO.md acceptance: `make test TEST=tests/test_foo.py`. The proposed signature is `make(target, ...)` with no `variables` parameter. If the agent passes `target="test TEST=tests/test_foo.py"`, the shell-metacharacter check passes (no forbidden char), and `make` receives it as a single argv element. GNU make will parse this as `target=test` + variable override `TEST=...`? No — make parses each argv element; `test TEST=tests/test_foo.py` is a single string that make treats as one token. It would not split on the space. So this acceptance criterion requires either a separate `variables` parameter or the agent passing `target="test"` and the framework adding `TEST=...` separately. This is a design gap in the proposed signature, not a security issue. Flag for the owner as a design note (out of security scope).

## 4. Specific Recommendations

| # | Recommendation | Severity | Justification | Cost |
|---|----------------|----------|---------------|------|
| R1 | Add `"make"` to `_FILESYSTEM_TOOLS` in `tools/guardrails/path.py` | **Blocking** | Without it, the `cwd` PathGuardrail is a no-op; acceptance criterion "cwd outside project root is rejected" fails | 1 line |
| R2 | Reject `target` starting with `-` after `strip()`; reject empty/whitespace target | High | `--eval=<recipe>` bypasses `protected_files` via argv; `-C` escapes guarded `cwd`; `-j` DoS amplifier | 2 lines |
| R3 | Use the same `FORBIDDEN_CHARS` set as `git` (add `\n`, `\r`, `\x00`) | Low | Consistency; newline has meaning in make's parser | 1 line (copy frozenset) |
| R4 | Pass `start_new_session=True` to `subprocess.run`; on `TimeoutExpired`, kill the process group | Low | Prevents orphaned recipe children outliving the timeout | 3 lines |
| R5 | Document env-inheritance residual risk in the tool's security model section of README | Low | Secrets in env are readable by recipes; users must know | Doc only |
| R6 | Sequence T12 (`protected_files`) alongside or before T1.1 | Process | Without T12, the agent can `write` a malicious Makefile and `make(target=pwn)` | None |

No new abstractions, classes, or wrappers are introduced. R1-R4 are additions to existing constants / existing call sites in the proposed `make.py`. The owner's proposal remains the default; these are concrete, named gaps with earned justification.

## 5. Residual Risks (owner to accept explicitly)

| Risk | Severity | Mitigation in place | Remaining exposure |
|------|----------|---------------------|-------------------|
| Makefile recipes run arbitrary shell | High (accepted) | `protected_files` (T12) blocks agent from editing Makefile | Pre-existing malicious Makefile; recipe scripts the agent can edit; `include` directives pulling agent-writable files |
| Secrets in env are readable by recipes | Medium | None (inherit env is the correct default) | Any recipe can `printenv` / exfiltrate via network |
| Recipe children can outlive timeout | Low (if R4 not adopted) | `subprocess.run` timeout kills `make` only | Orphaned long-running children |
| `--eval`-style flag injection via target | High → Low (after R2) | R2 rejects leading `-` | None after R2 |
| `cwd` outside project root | High → None (after R1) | R1 enables the existing PathGuardrail | None after R1 |
| Variable-override via `=` in target | Informational | None | Semantic confusion, not a security bypass; needed for `make test TEST=...` pattern |

## 6. Security Checklist for Implementation

### 6.1 Implementation Requirements (must verify in T1.1 / T1.3)

- [ ] `make` added to `_FILESYSTEM_TOOLS` in `tools/guardrails/path.py`
- [ ] `target` validation: reject if `target.strip()` is empty
- [ ] `target` validation: reject if `target` starts with `-` (flag injection)
- [ ] `target` validation: reject if `target` contains any of `\n \r \x00` \` `$` `|` `;` `&`
- [ ] `subprocess.run(["make", target], cwd=<resolved>, capture_output=True, text=True, timeout=..., start_new_session=True)`
- [ ] On `TimeoutExpired`: kill the process group (if R4 adopted)
- [ ] Output truncated to `max_output_kb` (default 100) with truncation marker
- [ ] `cwd` resolved via `os.path.realpath` before being passed to subprocess (matches PathGuardrail behavior)
- [ ] Return code, stdout, stderr reported separately in `ToolResult`
- [ ] No env var injection (inherit) — confirmed as default design
- [ ] `MakeToolConfig` with `timeout_ms` (default 300000) and `max_output_kb` (default 100); validated as positive ints in `__post_init__` (matches `ListToolConfig` pattern)

### 6.2 Testing Requirements (T1.3)

- [ ] `make(target="check")` executes and returns output
- [ ] `make(target="rm -rf /")` rejected (space is fine, but `/` is not forbidden — should this be rejected? See note)
- [ ] `make(target="--eval=...")` rejected (leading `-`)
- [ ] `make(target="-i")` rejected (leading `-`)
- [ ] `make(target="")` rejected (empty)
- [ ] `make(target="  ")` rejected (whitespace-only)
- [ ] `make(target="check\nrm -rf /")` rejected (newline)
- [ ] `make(cwd="/etc")` rejected (outside project root — verifies R1)
- [ ] `make(cwd="../../")` rejected (traversal — verifies R1)
- [ ] Output > 100 KB truncated with marker
- [ ] Timeout enforced; process tree killed
- [ ] Exit code, stdout, stderr reported separately

**Note on `make(target="rm -rf /")`**: The TODO.md acceptance criterion lists this as "rejected (shell metacharacter in target)". With list-args, `rm -rf /` has no shell meaning — `make` would look for a target literally named `rm -rf /` and fail with "No rule to make target". The forbidden-char check (`-` is not in the forbidden set) would NOT reject it. To match the acceptance criterion, either:
- Add space to forbidden chars (breaks legitimate multi-word targets — but `make` targets don't have spaces, so this is safe), OR
- Re-state the acceptance criterion as "rejected because no such target exists, returns non-zero exit code" rather than "rejected by validation".

Recommend: add space to forbidden chars for `target` (Makefile target names cannot contain spaces per POSIX make spec). This makes the acceptance criterion pass as written.

## 7. Positive Observations

- The owner's foundational choice (list-args `subprocess.run`, no `shell=True`) is correct and is the single most important control.
- The `protected_files` guardrail (T12) is the right place to mitigate Makefile-editing attacks, not the `make` tool. The separation is architecturally sound.
- Reusing `PathGuardrail` (rather than a new make-specific path check) is the right call — once R1 is applied, the existing root-containment logic covers `cwd` for free.
- Consistent with the existing `git` tool pattern (operation allowlist → target validation; FORBIDDEN_CHARS; list-args; subprocess.run).
- Output truncation + timeout defaults match the rest of the toolset.

## 8. Summary

The owner's proposal is sound on the foundational controls (no shell, PathGuardrail, timeout, truncation, target character blocklist). Two real gaps require fixes before T1.1 can meet its stated acceptance criteria:

1. **Blocking (R1)**: `make` must be added to `_FILESYSTEM_TOOLS` or the `cwd` PathGuardrail is silently skipped. The acceptance criterion "cwd outside project root is rejected" will fail without this one-line change.
2. **High (R2)**: `target` must reject leading `-` to prevent `--eval`-based recipe injection that bypasses `protected_files`.

Three smaller hardening items (R3-R5) are recommended but not blocking. The residual risks (Makefile arbitrary shell, env inheritance) are real but are the correct trade-off for a 1.0 trust model and should be accepted explicitly by the owner.