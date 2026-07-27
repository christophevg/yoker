# Security Review: GitHub Tool (MBI-009 T7)

**Date**: 2026-07-27
**Reviewer**: security-engineer
**Baseline**: `analysis/security-github-tool.md` v2.0
**Owner's proposal**: "Operation allowlist (fixed enum, configurable per-project); subcommand blocking is the whole point; subprocess.run(["gh", ...], ...) — list args, no shell; Timeout enforcement (default 30s)"
**Verdict**: APPROVED — no blocking security issues found. Three related (non-blocking) gaps documented below for follow-up.

## Executive Summary

The implementation correctly realizes the security boundary described in
`analysis/security-github-tool.md` v2.0. The operation enum is a hardcoded
dispatch table with no passthrough; `gh api`, `gh extension`, `gh auth token`,
and all write/destructive subcommands are unreachable. Argument-injection
defenses (regex validation, leading-dash rejection, `FORBIDDEN_CHARS`, `--`
separator before positionals, int clamps, enum checks) are all in place.
Subprocess execution follows the `make.py` R4 invariant (`Popen` +
`start_new_session=True` + `os.killpg(SIGKILL)` on timeout). Output redaction
runs before truncation with an extended credential pattern set. No `env_vars`
parameter is exposed. Config validation rejects unknown operations at load
time. The Windows platform gate is present.

Three non-blocking gaps are documented below (missing `NO_COLOR` env,
incomplete success-path audit log, missing `aws_secret` redaction pattern).
None of these creates an exploitable vulnerability; they are hardening
opportunities against the documented requirements.

## Owner's Proposal Assessment

> "Operation allowlist (fixed enum, configurable per-project); subcommand
> blocking is the whole point; subprocess.run(["gh", ...], ...) — list args,
> no shell; Timeout enforcement (default 30s)"

The owner's proposal works and is faithfully implemented. The implementation
adds the necessary concrete defenses the proposal implicitly requires
(regex validation, `FORBIDDEN_CHARS`, `--` separator, process-group kill,
redaction) without introducing unnecessary abstraction. The dispatch table
in `_OPERATION_DISPATCH` is exactly the "subcommand blocking is the whole
point" the owner specified — there is no passthrough, no string concatenation,
no dynamic subcommand selection. The proposal is sound; the implementation
matches it.

## Checklist Results

### 1. Subcommand blocking — PASS

`_OPERATION_DISPATCH` (github.py:64-98) is a hardcoded `dict` mapping 9
operations to fixed `gh` subcommand prefixes. The agent-supplied `operation`
string is checked against `_GITHUB_OPERATIONS` (a `frozenset`, github.py:49-61)
and then against `gh_config.allowed_operations` (github.py:170). There is no
code path where the agent influences which `gh` subcommand runs — they only
influence validated arguments of a fixed subcommand.

None of the 9 dispatched subcommands is `gh api`, `gh extension`, `gh auth
token`, or any write/destructive command. The reachable subcommands are:
`repo view`, `issue list`, `issue view`, `pr list`, `pr view`, `run list`,
`run view`, `release list`, `release view` — all read-only.

### 2. Argument injection — PASS

| Parameter | Validation | Verdict |
|-----------|------------|---------|
| `repo` | `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`, len <= 100, no leading `-`, `FORBIDDEN_CHARS` | Safe |
| `number` | `int` (bool rejected), `[1, 2^31-1]`, `str(int)` cannot produce a flag | Safe |
| `tag` | `^[A-Za-z0-9._-]+$`, len <= 100, no leading `-`, `FORBIDDEN_CHARS` | Safe |
| `label` | `^[A-Za-z0-9._-]+$`, len <= 100, no leading `-`, `FORBIDDEN_CHARS` | Safe |
| `state` | Enum `{"open", "closed", "all"}` | Safe |
| `limit` | `int` (bool rejected), `>= 1`, clamped to `min(limit, config.max_results)` | Safe |
| `operation` | `isinstance(str)` + frozenset membership + config allowlist | Safe |

`FORBIDDEN_CHARS` = `{";", "|", "&", "$", "`", "\n", "\r", "\x00"}` — matches
`git.py` / `make.py`.

The `--` separator is placed before user-supplied positionals (`number`,
`tag`) in `_build_command` (github.py:428-432), ensuring they are treated as
operands, not flags. Defense in depth: the leading-dash rejection already
prevents flag injection via these values.

Minor deviation from §3.1: the implementation uses `--label <value>` (two
argv elements) rather than `--label=<value>` (one argv element). This is safe
because the value is validated to match `^[A-Za-z0-9._-]+$` and cannot start
with `-`, so it cannot be interpreted as a flag. The `=` form is defense in
depth that is not required given the existing validation. Not a vulnerability.

### 3. Subprocess execution — PASS

`subprocess.Popen` with list args, `shell` not set (defaults to `False`),
`start_new_session=True` (github.py:218-226). On `TimeoutExpired`:
`os.killpg(pid, signal.SIGKILL)` (github.py:457-462), then
`proc.communicate(timeout=5)` to reap and collect partial output
(github.py:240-243). This matches the `make.py` R4 invariant exactly.

Test `test_command_is_list_no_shell` verifies list args, no shell, and
`start_new_session=True`. Test `test_timeout_returns_failure` verifies
`os.killpg` is called with `SIGKILL`.

### 4. Output redaction — PASS (with one minor gap)

Redaction patterns (github.py:122-129):
- `ghp_*` / `ghu_*` / `ghs_*` etc. (GitHub tokens)
- `github_pat_*` (fine-grained PATs)
- `AKIA` / `ASIA` (AWS key IDs)
- `xox[baprs]-*` (Slack tokens)
- `npm_*` (npm tokens)
- URL-embedded credentials (`https://user:pass@host`)

Applied to stdout and stderr BEFORE truncation (github.py:251-252). Log
counts only, never matched text (github.py:255-260). Correct order:
redact → truncate, so a secret just past the truncation point is not kept.

**Minor gap**: The `aws_secret` pattern (40-char base64 strings on lines
containing "secret") from §4.3 is not implemented. The doc itself notes this
pattern has "high false-positive; only apply to lines containing 'secret'".
Missing it is a Low severity hardening gap, not a vulnerability — the
`aws_key_id` pattern still catches the access key ID portion.

### 5. No env_vars — PASS

There is no `env_vars` parameter in the function signature (github.py:133-143).
The subprocess env is `os.environ` (github.py:221), inherited unchanged so
`gh` can find its own config. The agent cannot inject `GH_TOKEN`, `GH_HOST`,
or any other env var. Test `test_no_env_passthrough` confirms
`env is os.environ`.

### 6. Config validation — PASS

`GitHubToolConfig.__post_init__` (config/__init__.py:535-546) validates every
value in `allowed_operations` against `_GITHUB_OPERATIONS`. Unknown values
raise `ValidationError`. Tests `test_unknown_operation_in_allowlist_raises`
and `test_default_allowlist_has_nine_ops` confirm this.

The default `allowed_operations` is the full 9-operation read-only MVP set
(config/__init__.py:519-529), matching §5's default-allow decision.

### 7. Windows platform gate — PASS

github.py:195-199: `if sys.platform == "win32": return ToolResult(success=False,
error="...not available on Windows")`. The gate is checked before `Popen` is
called. The `TestWindowsPlatformGate` test verifies Popen is not invoked on
Windows.

**Note**: The Windows gate test is skipped on non-Windows platforms
(test_github.py:568), so it never runs in a typical POSIX CI. This is a test
coverage gap, not an implementation gap — the gate logic itself is correct.
Recommend mocking `sys.platform` to test on all platforms. Classified as
New/backlog (Low).

### 8. Read-only enforcement — PASS

All 9 operations map to read-only `gh` subcommands (`view`, `list`). No write
or destructive operation (`merge`, `create`, `delete`, `close`, `comment`,
`rerun`, `cancel`, `enable/disable`, `clone`) is reachable through the enum.
The `requires_permission` concept from `GitToolConfig` is not needed here
because there are no write operations in the MVP enum.

### 9. Timeout handling — PASS

`_clamp_timeout` (github.py:390-394) clamps the caller-supplied `timeout_ms`
to `[1000, config.timeout_ms]`. The agent can lower the timeout but never
raise it above the config ceiling. Default ceiling is 30000ms (30s), matching
the owner's proposal. On timeout, the process group is killed and a distinct
error is returned (github.py:245-248). Test `test_timeout_clamped_to_config_ceiling`
verifies the clamping.

## Findings Classification

| Finding | Classification | Severity | Action |
|---------|---------------|----------|--------|
| Missing `NO_COLOR=1` in subprocess env | Related | Low | Add `NO_COLOR=1` to inherited env to strip ANSI from stderr (mitigates redaction bypass via color codes) |
| No success-path `github_executed` audit log | Related | Low-Medium | Log a completion event on success with duration_ms, stdout_bytes, stderr_bytes, redactions count, truncated flag per §8 |
| Missing `aws_secret` redaction pattern | Related | Low | Add the 40-char pattern scoped to lines containing "secret" per §4.3 |
| Windows gate test only runs on Windows | New | Low | Mock `sys.platform` in test to verify gate logic on POSIX CI |
| `workflow_list`/`workflow_view` naming vs `gh run` subcommand | New | Low | Operation names suggest workflow definitions but map to workflow runs; UX/naming issue, not security |

## Positive Observations

- The dispatch table is exactly the right design: a hardcoded `dict` with no
  string concatenation, no dynamic subcommand selection, no passthrough mode.
  This is the security boundary the owner specified and it is correctly
  implemented.
- The `--` separator before user-supplied positionals is correct defense in
  depth, matching §3.1.
- The redaction-before-truncation ordering is correct (§7). A secret just
  past the truncation point is not accidentally included.
- The `require_explicit_repo` config option is a nice defense-in-depth
  feature not strictly required by the doc — it lets operators force explicit
  repo specification, preventing `gh` from auto-detecting an unintended repo
  from the current git remote.
- The `isinstance(number, bool)` rejection (github.py:335) is a good catch —
  Python booleans are `int` subclasses and `True` would pass `>= 1` checks.
- Config validation at load time (not just at runtime) prevents
  typo-driven enablement of nonexistent operations, matching §5.
- Test coverage is thorough: all 9 operations have argv snapshot tests, all
  validation paths have rejection tests, timeout/killpg is tested, redaction
  is tested, truncation is tested, config validation is tested.
- The `_contains_forbidden` check on `state` (github.py:366-367) is redundant
  given the enum check, but harmless defense in depth.

## Remediation Recommendations (Non-Blocking)

### R1: Add `NO_COLOR=1` to subprocess env (Low)

```python
env = {**os.environ, "NO_COLOR": "1"}
proc = subprocess.Popen(cmd, ..., env=env, ...)
```

This prevents `gh` from emitting ANSI escape codes in stderr, which could
obscure secret patterns from the redaction regexes. The `--json` flag already
ensures stdout is plain JSON, so this primarily protects stderr.

### R2: Add success-path audit log (Low-Medium)

After a successful execution (around github.py:293), add:

```python
logger.info(
  "github_executed",
  operation=operation,
  repo=repo or "(auto)",
  number=number,
  returncode=returncode,
  duration_ms=...,  # measure with time.monotonic() around communicate()
  stdout_bytes=len(stdout_out.encode("utf-8")),
  stderr_bytes=len(stderr_out.encode("utf-8")),
  redactions=total_redactions,
  truncated=truncated,
)
```

This closes the audit-trail gap from §8: every call currently logs
`github_executing` (pre-execution) but not a completion event with the
outcome and metrics.

### R3: Add `aws_secret` redaction pattern (Low)

```python
(re.compile(r"(?m)^(?=.*secret).{0,200}([A-Za-z0-9+/]{40})", re.IGNORECASE), "aws_secret"),
```

Or more simply, apply the 40-char pattern only to lines containing "secret"
(case-insensitive), as the doc specifies. High false-positive rate is
acceptable per §4.3.