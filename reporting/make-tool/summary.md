# `make` Tool — Implementation Summary

**PR:** https://github.com/christophevg/yoker/pull/48
**Branch:** `feature/make-tool`
**Task:** MBI-009 T1, 1.0.0 Release Gate
**Status:** Pending review (not merged)

## What Was Implemented

The `make` built-in tool lets an agent execute Makefile targets via
`subprocess.Popen(["make", target], ...)` with list arguments (no shell). It is
the first tool with explicit per-target environment variable pass-through and
the first to use the new `EnvGuardrail` framework.

Behavior:

- Per-target env var allowlist (`dict[str, tuple[str, ...]]` on `MakeToolConfig`)
- Hard, non-configurable denylist (`YOKER_*`, `LD_*`, `MAKEFLAGS`, `GIT_*`,
  ...) — framework invariants, not waivable by operator
- Value validation: 4 KB per variable, no NUL bytes or newlines, valid UTF-8
- Deny-by-default: empty allowlist means all env vars denied
- `PathGuardrail` on `cwd`
- Process-group kill on timeout via `os.killpg`
- Per-stream output truncation (stdout and stderr independently)

## Key Decisions

- **Owner-approved Option A per-target allowlist**
  (`dict[str, tuple[str, ...]]` on `MakeToolConfig`). Maps cleanly to a
  dataclass field. Option B (per-tool section) would collide with existing
  config fields.
- **Owner-approved hard non-configurable denylist.** `YOKER_*`, `LD_*`,
  `MAKEFLAGS`, `GIT_*`, etc. are framework invariants the operator cannot
  waive. The security-engineer's abuse-vector analysis (especially `MAKEFLAGS`
  reopening the `--eval` bypass) justified this addition.
- **Owner-approved value validation.** 4 KB per variable, no NUL bytes or
  newlines, valid UTF-8.
- **Owner-approved deny-by-default.** An empty allowlist denies all env vars
  rather than allowing all.
- **Owner-approved make-only scope.** No change to `GitToolConfig`.
- **`subprocess.Popen` + `communicate` instead of `subprocess.run`** (earned
  deviation). `run()` does not expose the `Popen` object on
  `TimeoutExpired`, making process-group kill impossible. `Popen` is the
  correct primitive for the timeout-kill requirement (R4).
- **Test path `tests/test_tools/test_make.py`** — matches the actual git test
  location, not the non-existent `tests/test_builtin/` referenced in earlier
  task drafts.

## Files Modified

New:

- `src/yoker/builtin/make.py` — tool implementation
- `src/yoker/tools/guardrails/env.py` — `EnvGuardrail` framework
- `tests/test_tools/test_make.py` — tool tests
- `tests/test_tools/test_env_guardrail.py` — guardrail tests

Modified:

- `src/yoker/config/__init__.py` — added `MakeToolConfig`
- `src/yoker/tools/guardrails/path.py` — R1 + `_get_tool_config` helper
- `src/yoker/builtin/__init__.py` — `make` registered in
  `__YOKER_MANIFEST__`
- `README.md` — Features section, config section, R5 reference
- `examples/yoker.toml` — `[tools.make]` block
- `CLAUDE.md` — module structure entry for `make.py` and `env.py`
- `DEVELOPMENT.md` — MBI-009 T1 summary

Review reports (this folder):

- `functional-review.md`
- `api-architect-review.md`
- `security-review.md`
- `testing-review.md`
- `documentation-review.md`

## Lessons Learned

- **`args` vs `env_vars` design.** The owner's insight that `TEST=file.py` is
  an env var (not a positional arg) led to a cleaner, more correct design. The
  security-engineer's abuse-vector analysis (especially `MAKEFLAGS` reopening
  the `--eval` bypass) justified the hard non-configurable denylist addition.
- **Option A vs Option B.** Per-target allowlist (Option A) maps cleanly to a
  dataclass field; per-tool section (Option B) would collide with existing
  config fields.
- **`subprocess.run` vs `subprocess.Popen`.** `run()` doesn't expose the
  Popen object in `TimeoutExpired`, making process-group kill impossible.
  `Popen` is the correct primitive for R4.

## Verification

`make check` passes (2005 tests). All review stages passed across rounds 0
and 1: functional, API, security, code-quality, testing, documentation.
