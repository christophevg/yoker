# Consensus: `make` Tool (MBI-009 T1)

**Date:** 2026-07-21
**Phase:** 4 — Consensus across API architect + security engineer reviews
**Source proposals:** TODO.md `make` tool spec; `analysis/mbi-toolset-coverage.md` §7.1 and §6.5
**Domain reviews:** `analysis/api-make-tool.md`, `analysis/security-make-tool.md`

---

## 1. Foundation Agreement

Both domain agents approve the owner's proposal as the default. No deviations are introduced.

- **API architect:** "The owner's proposal is slim, consistent with the existing `git` tool pattern... It works as written. This design adopts it verbatim." Signature, parameter order, defaults, `PathArg("Working directory")` on `cwd`, and the `subprocess.run(["make", target], ...)` list-args invocation are preserved exactly.
- **Security engineer:** "The owner's foundational choice (list-args `subprocess.run`, no `shell=True`) is correct and is the single most important control." PathGuardrail on `cwd`, output truncation (default 100KB), timeout (default 5 min), and the shell-metacharacter blocklist are all confirmed sound.

The `protected_files` guardrail (T12) is confirmed as the owner's chosen mechanism for Makefile-abuse prevention — the `make` tool validates target names, not Makefile content. Both agents agree this separation is architecturally correct (§6.5 of `mbi-toolset-coverage.md`).

---

## 2. Blocking Security Findings (must incorporate)

### R1 — Add `make` to `_FILESYSTEM_TOOLS` (Blocking)

`PathGuardrail.validate()` short-circuits to `valid=True` for any tool name not in `_FILESYSTEM_TOOLS` (`src/yoker/tools/guardrails/path.py`). Without this one-line addition, the `Annotated[str, PathArg(...)]` annotation on `cwd` is a **silent no-op** and the acceptance criterion "cwd outside project root is rejected" fails.

**Fix:** add `"make"` to the `_FILESYSTEM_TOOLS` frozenset. One line.

### R2 — Reject `target` starting with `-` (High)

GNU make interprets a leading `-` as a flag, not a target. Concrete bypass named by the security engineer:

- `make(target="--eval=pwn:\n\trm -rf /")` injects an ad-hoc target with an arbitrary recipe via argv — this **bypasses `protected_files`** because no Makefile edit is needed.
- `make(target="-C /tmp")` escapes the guarded `cwd`.
- `make(target="-j")` enables unbounded parallelism (DoS amplifier).

The owner's proposal does not cover leading `-`. `git` already rejects it (`builtin/git.py:332`).

**Fix:** reject `target` if `target.strip().startswith("-")`; also reject empty/whitespace-only target. Two lines.

---

## 3. Low-Severity Hardening (incorporate)

### R3 — Extend forbidden chars to include `\n`, `\r`, `\x00`

Reuse `git`'s `FORBIDDEN_CHARS` frozenset verbatim: `{";", "|", "&", "$", "`", "\n", "\r", "\x00"}`. Newline has meaning in make's argv parser; `git` blocks these already. One constant, shared semantics — no new abstraction.

### R4 — `start_new_session=True` + process-group kill on timeout

`subprocess.run(timeout=...)` kills only the `make` process; recipe children can outlive the timeout. Pass `start_new_session=True` (POSIX) and kill the whole process group on `TimeoutExpired`. Three lines.

### R5 — Document env-inheritance residual risk in README

Any secret the yoker process holds in env (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, etc.) is readable by Makefile recipes via `printenv` or network exfiltration. Scrubbing env breaks more than it protects (PATH, HOME, venv-aware tools like `uv`). Document the residual risk explicitly; do not scrub env.

---

## 4. API Architect Refinements (adopted as-is)

These are refinements within the owner's proposal, not deviations:

1. **Target validation regex:** `_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+\-]*$")` with length cap 256. Combined with R2/R3 this gives belt-and-suspenders validation matching `git`'s pattern.
2. **Structured `ToolResult.result` dict:** `{"exit_code", "stdout", "stderr", "truncated"}` — satisfies T1.1's "Return exit code, stdout, stderr separately." This is the first built-in to return a dict; implementation must verify `UIBridge`/`InteractiveUIHandler` render dict results (the type allows it; `BatchUIHandler` already JSON-serializes dicts).
3. **`MakeToolConfig` following `GitToolConfig` pattern:** fields `timeout_ms` (default 300000), `max_output_kb` (default 100), validated as positive ints in `__post_init__`. Registered on `ToolsConfig`, exported in `__all__`.
4. **No `allowed_targets`/`blocked_targets` allowlist.** Explicitly not added — the owner's proposal does not include it; `protected_files` (T12) handles Makefile abuse at the right layer. Adding a target allowlist would duplicate that concern at the wrong layer and violate the slim-default principle.
5. **`Text("Makefile target name (e.g., 'check', 'test')")` annotation on `target`** — silences the `tool_parameter_missing_yoker_type` warning and gives the LLM a better description. One-line documentation refinement within the existing annotation framework.
6. **`timeout_ms` clamped to `MakeToolConfig.timeout_ms` as ceiling:** `effective = min(timeout_ms, ctx.config.tools.make.timeout_ms)`, then `max(effective, 1000)`. An operator's configured ceiling cannot be bypassed by an agent argument. Matches "controllable tools" spirit. Flagged for owner confirmation at review.

---

## 5. Open Design Question (needs owner decision)

The owner's TODO example and §9.1 acceptance criterion #2 is:

> An agent can run `make test TEST=tests/test_foo.py` using the `make` tool

The proposed signature `make(target, ctx, cwd, timeout_ms)` is single-string — there is no way to pass `TEST=tests/test_foo.py` to make. Passing `target="test TEST=tests/test_foo.py"` fails: `make` receives it as one argv token and looks for a target literally named `test TEST=...`, which does not exist.

**Proposed resolution:** add an `args: list[str] | None = None` parameter, so the call becomes `subprocess.run(["make", target, *(args or [])], ...)` — still list-args, no shell. The agent calls `make(target="test", args=["TEST=tests/test_foo.py"])`.

Rationale:
- Stays list-args (no `shell=True`); does not introduce flag-injection vectors because each element is a separate argv token that make parses as a variable override (`FOO=bar`) or a target — never a shell command.
- `=` in an `args` element is make variable-override semantics (the legitimate `make test TEST=...` pattern), not a security bypass.
- Resolves the open design note in security §3.9 and the API architect's §3 "No args/flags parameter" caveat.
- Does not enlarge the attack surface beyond the owner's already-accepted `make(target, ...)` form; each `args` element is validated only by rejecting leading `-` (no flag injection into make itself).

This is the one place the implementation plan diverges from a strict reading of the owner's proposal. It is flagged as an open question for the owner; the plan below includes it but marks it "awaiting owner confirmation." If the owner prefers to keep the strict single-string signature, drop `args` and re-state acceptance criterion #2 as "deferred to post-1.0."

---

## 6. Files Touched

| File | Change |
|------|--------|
| `src/yoker/builtin/make.py` | **New.** Tool implementation (signature, target validation, subprocess call, truncation, structured result). |
| `tests/test_builtin/test_make.py` | **New.** Tests covering each acceptance criterion + R1-R5. |
| `src/yoker/builtin/__init__.py` | Import `make`; add to `__YOKER_MANIFEST__.tools` and `__all__`. |
| `src/yoker/config/__init__.py` | Add `MakeToolConfig`; register on `ToolsConfig`; export in `__all__`. |
| `src/yoker/tools/guardrails/path.py` | One-line: add `"make"` to `_FILESYSTEM_TOOLS` (R1). |

3 one-line modifications + 1 new builtin module + 1 new test file.