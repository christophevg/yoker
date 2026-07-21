# PR #48 — `env_vars` Discussion (response to owner, comment 5032899305)

**Date:** 2026-07-21
**Author:** functional-analyst
**Related:** `analysis/security-env-vars-proposal.md`, `reporting/make-tool/consensus.md`, `analysis/security-make-tool.md`

---

## Owner's proposal (quoted verbatim)

> Let's first discuss the arguments issue and find a proper solution. In `make test TEST=some_file.py` `TEST` is an env var. What if we add the possibility to set env vars for a tool call, so instead of `args` we add `env_vars`? If we combine this with the option to restrict in configuration per tool which env vars can be set, this might be a generic way to solve this, while still limiting tool use to controllable subsets.
>
> Think this idea through, trying to find ways to abuse this added `env_vars` argument.

## Semantic insight — confirmed

You are correct that `TEST` in `make test TEST=foo.py` is a variable. In GNU make, command-line `VAR=val` is a make variable override; Makefiles commonly `export` it or reference it as `$(TEST)`. Passing it via the subprocess `env` achieves the same effect for the typical pattern. So `env_vars` is semantically the right model — and strictly more correct than the prior `args: list[str]` proposal, which treated `TEST=file.py` as a positional argv token (which make does accept, but env is the cleaner model).

## Abuse vectors found

Full enumeration in `analysis/security-env-vars-proposal.md` (~40 vectors). The decisive ones:

- **`MAKEFLAGS` reopens the `--eval` bypass** that the `make` tool's leading-`-` rejection on `target` was designed to close. `MAKEFLAGS="--eval=pwn:\n\trm -rf /"` injects a recipe without ever touching `target`. This is the decisive argument that `env_vars` is **not safer than `args` by default** — a permit-list-only design silently regresses the existing control.
- **`YOKER_TRUST_SOURCE` bypasses the trust gate** (`plugins/security.py:108`) — `check_source_allowed` reads it and auto-trusts the source. Framework invariants cannot be operator-waivable.
- **`HTTPS_PROXY` / `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`** redirect TLS egress without any recipe modification. A benign `make test` whose recipe curls anything leaks URLs (and any embedded tokens) to an attacker proxy. This is the single most dangerous exfil channel `env_vars` opens because it works on otherwise-benign targets.
- **`LD_PRELOAD` / `PYTHONPATH` / `BASH_ENV` / `DYLD_INSERT_LIBRARIES`** enable code execution in the subprocess on the first dynamic-link or shell-startup event.
- **Exfil via allowlisted values**: the agent `read`s a secret, then `make(target="check", env_vars={"BUILD_LOG": "<secret>"})`; a benign recipe POSTs `$BUILD_LOG`. A name-allowlist alone does not constrain values — every allowlisted name becomes an exfil channel for any data the agent can read.

Net: `env_vars` is **more expressive** than `args` (handles `TEST=file.py` correctly) but opens a **strictly larger attack surface** (env mutation reaches subprocess context, interpreter startup, network config, trust gates). It is safe to ship only with the full mitigation stack below.

## Refined design (owner's proposal + earned mitigations)

1. **`env_vars: dict[str, str] | None = None`** parameter on `make` (replaces the prior `args` proposal).
2. **Per-tool configurable allowlist** (your proposal) — `allowed_env_vars: tuple[str, ...] = ()` on each subprocess-spawning `*ToolConfig`, mirroring the existing `GitToolConfig.allowed_commands`. **Default empty (deny-by-default).** Exact-string match only; no globs, no `*`, no prefixes.
3. **Non-configurable hard denylist** (earned addition) — small, fixed frozenset enforced by the framework regardless of the operator's allowlist: `YOKER_*`, `LD_*`, `DYLD_*`, `MAKEFLAGS`, `MFLAGS`, `GIT_DIR`, `GIT_WORK_TREE`, `GIT_CONFIG_*`, `GIT_CONFIG_PARAMETERS`, `BASH_ENV`, `ENV`, `BASH_FUNC_*`, `PYTHONSTARTUP`, `PYTHONPATH`, `PYTHONHOME`, `PERL5OPT`, `RUBYOPT`, `NODE_OPTIONS`, `NODE_PATH`, `IFS`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `HOME`, `USER`, `LOGNAME`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_API_KEY`, `GITHUB_TOKEN`, `PATH` (inherited, not settable). Lives in a new `src/yoker/tools/guardrails/env.py` (~30 lines, mirrors the `path.py` pattern). **The operator cannot waive these — framework invariants are not theirs to waive.** This is the one place we diverge from a permit-only reading of your proposal; earned because §2.2 and §2.4 of the security analysis show permit-only is insufficient (`MAKEFLAGS` looks reasonable to allowlist and silently reopens `--eval`).
4. **Value validation** (earned addition) — per-var cap 4 KB, total cap 32 KB, no NUL, no newlines, valid UTF-8. Without this, every allowlisted name is an exfil channel (the agent `read`s a secret, sets `env_vars={"TEST": "<secret>"}`, a benign recipe ships it).
5. **Subprocess env construction**: `env = {**os.environ, **validated_env_vars}` — inherits yoker's env (so `PATH`, `HOME`, locale, venv-aware tools work) and layers the allowlisted, denylist-checked, value-validated vars on top. Never replaces `os.environ` wholesale.
6. **Hybrid recommendation**: ship `env_vars` only; do **not** add `args` to `make`. `target` validation stays as-is (R1–R5 from the prior security review stand — leading-`-` rejection, `FORBIDDEN_CHARS`, PathGuardrail on `cwd`, `start_new_session=True`, env-inheritance residual risk documented). This is strictly safer than `args + env_vars` (smaller surface) and strictly more correct than `args` alone (TEST is an env var, not a positional arg).

## Updated implementation plan (files vs. prior plan)

| File | Change |
|------|--------|
| `src/yoker/builtin/make.py` | **New.** Signature now has `env_vars` instead of `args`. |
| `src/yoker/tools/guardrails/env.py` | **New (~30 lines).** `is_denied_env_var()`, `validate_env_vars()` — allowlist + hard-denylist + value rules. Mirrors `path.py` pattern. |
| `tests/test_builtin/test_make.py` | **New.** Tests for env_vars: allowlist enforcement, denylist enforcement (operator allowlists `MAKEFLAGS` → still rejected), value validation (oversize, NUL, newline), inheritance. |
| `tests/test_tools/test_env_guardrail.py` | **New.** Unit tests for the new guardrail. |
| `src/yoker/config/__init__.py` | **Modify.** Add `allowed_env_vars: tuple[str, ...] = ()` and `max_env_var_bytes: int = 4096` to `MakeToolConfig`. Open question Q3 below on whether `GitToolConfig` also gets them this PR. |
| `src/yoker/tools/guardrails/path.py` | **Modify.** R1 — add `"make"` to `_FILESYSTEM_TOOLS`. Unchanged from prior plan. |
| `src/yoker/builtin/__init__.py` | **Modify.** Manifest entry. Unchanged. |

## Open questions (need your decisions before implementation)

- **Q1:** Do you accept the hard non-configurable denylist as an addition to your per-tool allowlist? Required to keep `MAKEFLAGS`-via-env from reopening the `--eval` bypass that `target`'s leading-`-` rejection was designed to close.
- **Q2:** Do you accept the value validation (4 KB per-var, 32 KB total, no NUL/newlines, valid UTF-8)? Required to prevent exfil via allowlisted values (agent `read`s a secret, plants it in an allowlisted var, benign recipe ships it).
- **Q3:** Should `env_vars` be a generic framework capability (added to `git` and future subprocess tools now) or just `make` for now? Affects whether `GitToolConfig` gets `allowed_env_vars` in this PR.
- **Q4:** Is deny-by-default (empty allowlist) the right default? Operator opts in per tool, per name.

Waiting for your decisions on Q1–Q4 before updating the implementation plan and proceeding.