# Security Analysis: GitHub Tool

**Document Version**: 2.0
**Date**: 2026-07-27
**Status**: Active — reviewed and updated for MBI-009 T7 implementation
**Supersedes**: v1.0 (2026-04-30)

## 0. Scope and Methodology

This analysis covers the `github` tool to be implemented in
`src/yoker/builtin/github.py` per MBI-009 T7 (Tier 2, high priority). The tool
wraps the `gh` CLI via `subprocess.run([...], list args, no shell)` and exposes
a fixed-enum `operation` parameter as its primary security boundary.

The v1.0 draft correctly identified the broad threat categories (information
disclosure, rate limits, command injection, unauthorized operations). v2.0 adds
the concrete attack-surface analysis the owner's task list explicitly requests:

- Argument-injection vectors (flags, options, the `--` separator)
- gh-CLI-specific bypass vectors (`gh api`, `gh extension`, `gh repo clone`)
- Process-group cleanup on timeout (the `make.py` invariant R4)
- Output sanitization for secrets that leak into CI/workflow logs
- The default-deny vs default-allow decision for the per-project allowlist

References consulted:

- `src/yoker/builtin/make.py` — subprocess execution pattern (target
  validation, `start_new_session=True`, `os.killpg` on timeout, output
  truncation on a UTF-8 boundary)
- `src/yoker/builtin/git.py` — `DANGEROUS_OPTIONS`, `FORBIDDEN_CHARS`,
  per-operation `OPERATION_ARGS` schema, `_sanitize_output` redaction
- `src/yoker/tools/guardrails/path.py` — PathGuardrail containment model
- `analysis/api-github-tool.md` — tool interface design
- `analysis/mbi-toolset-coverage.md` §7.8 and T7 — owner confirmation that
  "subcommand blocking is the whole point"

---

## 1. Threat Model (STRIDE)

### 1.1 Trust Boundaries

```text
  Agent (LLM output, untrusted parameters)
    │
    │  operation: enum-validated string
    │  repo:      string (OWNER/REPO, validated)
    │  number:    int
    │  limit:     int 1..100
    │  state/label: enum / short string
    │
    ▼  ─── yoker tool boundary ───────────────────────
  github() validation layer
    │   - operation in allowlist? (default-deny)
    │   - per-operation arg schema (git-style OPERATION_ARGS)
    │   - repo format / FORBIDDEN_CHARS / no leading dash
    │   - numeric clamps
    │
    ▼
  subprocess.run(["gh", ...], list args, start_new_session=True)
    │
    ▼  ─── OS process boundary ───────────────────────
  gh CLI  (uses ~/.config/gh/hosts.yml or keyring token)
    │
    ▼
  GitHub API  (out of scope)
```

Three trust boundaries matter:

1. **Agent → tool** (the primary one): the LLM is taken to be adversarial
   per the agent-security model. Every parameter is attacker-controlled.
2. **Tool → gh CLI**: list-args `subprocess.run` removes shell
   metacharacters, but `gh` itself accepts flags that can change behavior
   dramatically (`gh api`, `--jq`, extensions). Argument-shape validation
   must keep parameters out of flag position.
3. **gh CLI → GitHub API**: out of scope; `gh` authenticates with its own
   stored token, which the tool never reads.

### 1.2 Asset Inventory

| Asset | Sensitivity | Tool exposure |
|-------|-------------|---------------|
| GitHub auth token | Critical | Never read by the tool; `gh` manages it in `~/.config/gh/hosts.yml` or keyring. **The tool must not pass `GH_TOKEN` env or read `gh`'s config files.** |
| Repo metadata | Low | Public repos: low. Private repos: medium. |
| Issue/PR content | Low-Medium | May contain security discussion, draft patches, vuln reports. |
| Workflow run logs | Medium-High | CI logs routinely leak secrets (printed env, misconfigured `echo`, debug output). **This is the highest-value read target.** |
| Release bodies | Low | Public. |
| Repo file tree | Out of scope | MVP does not expose `gh api repos/.../contents`. |

### 1.3 STRIDE Threat Table

| STRIDE | Threat | Mitigation (primary) |
|--------|--------|-----------------------|
| Spoofing | Agent impersonates a different repo to read a private repo the user can access | `gh` uses the user's token; tool cannot escalate beyond user's scope. Repo-format validation prevents `--repo` flag injection. |
| Tampering | Agent writes to GitHub (merge, push, delete) | **MVP has no write operations.** Operation enum is fixed; allowlist is default-deny. |
| Repudiation | Agent performs reads with no audit trail | Structured `github_executed` log per call (operation, repo, number, duration, exit_code). |
| Information Disclosure | Workflow logs leak secrets into agent context | Output redaction (regex for common token shapes) + per-stream byte cap + truncation. |
| Denial of Service | Agent loops on `gh` calls, exhausts GitHub API rate limit, or hangs the process | Timeout (30 s default) with process-group kill; result count cap (max 100); rate-limit-error detection returns error to agent. |
| Elevation of Privilege | Agent escapes the operation enum and runs arbitrary `gh` subcommands (`gh api`, `gh extension run`) | Operation enum + per-operation arg schema + `--` separator before any user-supplied positional + repo/number format validation. See §3. |

---

## 2. Security Requirements (carried forward from v1.0)

### 2.1 Operation Allowlist (primary boundary)

The `operation` parameter is a fixed Python `Literal[...]` / Enum. Values
outside the enum cannot be expressed in a well-typed call. At runtime the
value is checked against `GitHubToolConfig.allowed_operations`, which is a
**subset** of the enum. **Default is the full read-only MVP set** (see §5
for why default-allow of the MVP set, not default-deny-of-everything, is
correct here).

```toml
[tools.github]
allowed_operations = [
  "repo_view", "issue_list", "issue_view",
  "pr_list", "pr_view",
  "workflow_list", "workflow_view",
  "release_list", "release_view",
]
# Operations in the enum but absent from this list are rejected.
# Operations NOT in the enum are rejected at the type layer and at runtime.
```

### 2.2 Subprocess Execution

- `subprocess.run(cmd_list, ...)` — **never `shell=True`**, never a single
  string command. This is non-negotiable and inherited from `make.py` and
  `git.py`.
- `start_new_session=True` so the child leads its own process group; on
  timeout the whole group is killed with `os.killpg(pid, SIGKILL)` to
  prevent orphaned `gh` children (make.py R4 invariant).
- Windows platform gate: refuse to run on `win32` (POSIX-only process-group
  kill), mirroring `make.py`.
- Inherited env: `{**os.environ}` is fine for `gh` (it needs `HOME` for
  config and possibly `GH_HOST`/`GH_ENTERPRISE_TOKEN` for enterprise
  setups). **Do not let the agent supply `env_vars` in MVP** — there is no
  legitimate read-only use case and env is the channel for credential
  injection/spoofing (`GH_TOKEN=...`, `GH_HOST=evil.example`). If env passthrough is added later, it must use the
  `make.py` per-target allowlist pattern.

### 2.3 Rate Limiting and Resource Caps

| Guardrail | Default | Enforcement |
|-----------|---------|-------------|
| `timeout_seconds` | 30 | `subprocess` timeout + process-group kill |
| `max_results` (lists) | 100 | Clamp `limit` to `[1, 100]` before passing to `--limit` |
| `max_output_kb` per stream | 256 (match make.py default band) | Truncate on UTF-8 boundary |
| Rate-limit detection | n/a | Parse `gh` stderr for "rate limit" / HTTP 403/429; return a distinct `error` so the agent stops retrying |

---

## 3. Argument-Injection Analysis (new in v2.0)

This is the section v1.0 was missing and the owner's task list explicitly
requests. The `operation` enum prevents arbitrary subcommand selection, but
**each remaining parameter is still attacker-controlled** and `gh` accepts
many flags that change behavior. The git tool's defense is the model here:
a per-operation `OPERATION_ARGS` schema, `FORBIDDEN_CHARS`, and rejection of
any value that starts with `-`.

### 3.1 Threat: Flag Injection via Positional Parameters

**`repo` parameter** (passed as a positional `OWNER/REPO` argument):

- Risk: a value like `--jq=exfiltrate` or `--include` could be interpreted
  as a flag by `gh` and change behavior.
- Defense:
  1. Reject any `repo` value that starts with `-` (single or double dash).
  2. Require the `OWNER/REPO` format: `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`,
     length <= 100. This is tighter than necessary for GitHub names but
     is a safe allowlist.
  3. **Always pass `--` before the user-supplied positional** when the
     subcommand accepts a repo positional, so anything after `--` is
     treated as an operand, not a flag. Example:
     `["gh", "repo", "view", "--", "owner/repo"]`.
     Caveat: verify per-subcommand that `--` is accepted; `gh issue view
     NUMBER -- repo` is the documented form for explicit-repo overrides.
- Residual: none known.

**`number` parameter** (passed as positional for `*_view`):

- Type is `int`; clamped to `[1, 2**31 - 1]`. `str(int)` cannot produce a
  flag. Safe.

**`state`, `label` parameters** (passed as `--state=...`, `--label=...`):

- `state` is `Literal["open", "closed", "all"]` — enum, safe.
- `label` is a free string. Defense:
  1. Reject leading `-`.
  2. Reject `FORBIDDEN_CHARS` (`\n \r \x00` `$ ` ; & |`) — same set as
     `git.py`.
  3. Length <= 100.
  4. Pass as `--label=<sanitized>`, not `--label <sanitized>` (equivocal
     parsing is impossible with `=` form when the value itself contains
     no `=`; the `=` form also makes flag injection via the value
     impossible because the whole `--label=...` is one argv element).
- Residual: a label name containing `--` inside the value is fine because
  it is part of a single argv element, not a separate flag.

### 3.2 Threat: The `--` Separator Itself

The `--` separator is our **friend**, not an attack. It tells `gh` "end of
options; everything after is a positional". Using it before user-supplied
positionals is the defensive pattern. The only way `--` becomes an attack
is if the agent supplies `--` as a value to bypass a subsequent check —
which is prevented by the leading-dash rejection (a literal `--` value
starts with `-`).

### 3.3 Threat: Dangerous gh Flags the Agent Might Try to Inject

These are flags `gh` accepts that would defeat the read-only / scoped
intent. The arg-schema approach means the agent **cannot supply any flag
that is not in the operation's `OPERATION_ARGS`** — same model as
`git.py`. Listed here so the implementer knows what they are not exposing:

| Flag | What it does | Why blocked |
|------|-------------|-------------|
| `--jq <expr>` | Run jq expressions on output | Not in any operation's arg schema → rejected by `_build_command` |
| `--raw-field` / `-F` (for `gh api`) | Arbitrary API requests | `gh api` is not an operation in the enum |
| `--field` / `-f` | Same | Same |
| `--include` (for `gh run list`) | Include older runs | Not in schema |
| `--export-file` | Write output to a file on disk | Not in schema; would bypass output redaction |
| `--web` | Open a browser | Not in schema |
| `--revision` / `--branch` | Change which ref is read | Not in MVP scope |
| `--repo <owner/repo>` | Target a different repo | Use the `repo` parameter instead, with format validation; never pass `--repo` directly from user input |

### 3.4 Threat: `gh` CLI Bypass Vectors (new in v2.0)

This is the owner's explicit concern: "we need to be able to block certain
subcommands (that's the whole point)." The operation enum blocks all of
these by construction — none of them is in the enum. They are listed here
as the explicit "what we are NOT allowing" set, so reviewers can confirm
the enum is in fact the boundary:

| `gh` subcommand | Risk | Status in MVP |
|-----------------|------|----------------|
| `gh api <endpoint>` | **Arbitrary GitHub API access** — read OR write, any endpoint, including `repos/.../contents`, `orgs/.../secrets`, `user/starred`. This is the single biggest bypass if it were ever added. | Not in enum. **Must never be added without a separate security review.** |
| `gh extension run <ext>` | Runs an installed extension, which is arbitrary code | Not in enum |
| `gh repo clone <repo> <dir>` | Writes to filesystem, can clone huge repos (DoS) | Not in enum |
| `gh repo delete` | Destructive | Not in enum |
| `gh pr merge` / `gh pr ready` / `gh pr review` | Write operations | Not in enum |
| `gh issue close` / `gh issue create` / `gh issue comment` | Write operations | Not in enum |
| `gh release create` / `gh release delete` | Write operations | Not in enum |
| `gh run rerun` / `gh run cancel` | Write operations | Not in enum |
| `gh workflow enable/disable` | Write operations | Not in enum |
| `gh auth status` / `gh auth token` | **`gh auth token` prints the token to stdout.** Must never be an operation. | Not in enum |
| `gh secret set/list` | Reads or writes repo secrets | Not in enum |
| `gh ssh-key add` | Adds an SSH key to user account | Not in enum |

**Implementation invariant:** the `operation` → `gh subcommand` mapping
must be a hardcoded dispatch table in `github.py`. The agent never
influences which `gh` subcommand runs; they only influence the validated
arguments of a fixed subcommand. There is no "passthrough" mode.

**Review checklist for adding operations (Phase 2+):** before adding any
operation, the reviewer must (a) confirm the underlying `gh` subcommand is
read-only or, if write, requires the `destructive_operations` config;
(b) confirm the operation cannot reach `gh api`; (c) confirm the operation
does not print credentials.

---

## 4. Token and Credential Exposure (updated)

### 4.1 How `gh` Auth Works

- User runs `gh auth login` once. `gh` stores the token in
  `~/.config/gh/hosts.yml` (plaintext, 0600) or the system keyring.
- On every invocation, `gh` reads the token from its own storage and sends
  it as `Authorization: Bearer <token>` to api.github.com.
- The yoker tool **does not** read `~/.config/gh/hosts.yml`, does not
  read `GH_TOKEN` from the environment, does not print `gh auth status`.
- The tool inherits `os.environ` so that `gh` can find its own config
  (`HOME`, and `GH_HOST`/`GH_ENTERPRISE_TOKEN` for enterprise setups).
  **The tool must not allow the agent to set or override env vars in
  MVP** (see §2.2).

### 4.2 Token Exposure Vectors the Tool Must Close

| Vector | Mitigation |
|--------|-----------|
| `gh auth token` subcommand prints the token | Not in the operation enum |
| Agent passes `GH_TOKEN=...` env to inject a stolen token | No `env_vars` parameter in MVP |
| Token appears in `gh` stderr on auth failure | Output redaction (§4.3) |
| Token in URL form in `git remote -v` output (clone URLs with embedded credentials) | Not applicable — MVP doesn't run `git` |
| Token leaked in workflow logs returned by `workflow_view` | Output redaction (§4.3) |

### 4.3 Output Redaction (new in v2.0)

`gh` output can contain secrets the agent should not hoover into its
context window:

- **Workflow run logs** (the main risk): CI logs frequently contain
  printed env vars, debug `echo` output, or misconfigured action dumps
  that include `gh_token`, `GITHUB_TOKEN`, AWS keys, npm tokens, etc.
- **Issue/PR bodies**: users sometimes paste error output containing
  tokens.
- **`gh` stderr on auth failure**: rare, but `gh` has historically printed
  redacted-then-unredacted auth details in debug mode.

**Required redaction in `github.py`** (mirror `git.py`'s
`CREDENTIAL_PATTERN` approach, extended):

```python
# Patterns are intentionally broad; false positives are acceptable,
# false negatives are not. Redact to <redacted> and log a redaction event.
_REDACT_PATTERNS = [
  (re.compile(r"(gh[pousr]_[A-Za-z0-9]{36,})"), "ghp_token"),
  (re.compile(r"(github_pat_[A-Za-z0-9_]{82})"), "github_pat"),
  (re.compile(r"((?:AKIA|ASIA)[0-9A-Z]{16})"), "aws_key_id"),
  (re.compile(r"([A-Za-z0-9+/]{40})"), "aws_secret"),  # high false-positive; only apply to lines containing "secret"
  (re.compile(r"(https?://)[^:]+:[^@]+@"), "url_creds"),  # same as git.py
  (re.compile(r"(xox[baprs]-[A-Za-z0-9-]+)"), "slack_token"),
  (re.compile(r"(npm_[A-Za-z0-9]{36})"), "npm_token"),
]
```

Apply to stdout and stderr before truncation, before returning to the
agent. Log `github_secret_redacted` events (pattern name + count, never
the matched text).

**Important limitation to document:** regex redaction is best-effort and
will miss secrets with non-standard formats. The defense of last resort is
the per-stream byte cap (§2.3) and the recommendation that operators
disable `workflow_view` for repositories with known secret-leak issues
(allowlist can drop it).

---

## 5. Per-Project Allowlist: Default-Deny vs Default-Allow

The owner's spec says "configurable per-project." The question is what the
default is when `allowed_operations` is unspecified.

**Decision: default-allow the full read-only MVP enum.**

Rationale (against a strict default-deny-of-everything):

1. The enum itself is already a denylist of everything outside it. There
   is no way to express a write operation, `gh api`, or `gh extension`
   through this tool. The "default" the operator is choosing between is
   "which *read-only* operations are enabled."
2. Defaulting to an empty list means a fresh checkout of yoker, with
   `yoker chat`, silently has no GitHub tool — which defeats the purpose
   of T7 ("without a `run` tool, this is the ONLY path for GitHub
   interaction").
3. The operator's per-project knob is for *reducing* the MVP set (e.g.
   "drop `workflow_view` for this repo because its CI logs leak"), not
   for granting additional powers. There are no additional powers to
   grant.

**Where default-deny does apply:**

- Operations *not in the enum*: denied at the type layer and runtime.
- Operations in the enum but removed from `allowed_operations`: denied.
- Phase 2 write operations (`pr_merge`, `issue_create`, etc.):
  **default-deny**, gated behind an explicit `destructive_operations`
  list that is empty by default. This is the asymmetry that matters.

**Validation:** `allowed_operations` values must be validated against the
enum at config-load time. An unknown value is a config error, not a
silent no-op. This prevents typo-driven enablement of an operation that
does not exist (or worse, a future operation that the operator did not
intend to enable).

---

## 6. Timeout and Process Cleanup (new in v2.0)

Adopted directly from `make.py` (R4 invariant):

- `subprocess.Popen(..., start_new_session=True)` so the child leads its
  own process group. (`subprocess.run` is insufficient because on timeout
  it only sends SIGKILL to the immediate child, leaving `gh`'s children
  alive — and `gh` may spawn `git` or other helpers for some
  subcommands.)
- On `TimeoutExpired`: `os.killpg(proc.pid, SIGKILL)`, then
  `proc.communicate(timeout=5)` to reap and collect partial output.
- Return a distinct `error`: `"github operation '{op}' exceeded timeout
  ({ms} ms)"`. Log `github_timeout`.
- `timeout_seconds` is clamped to `[1, config.timeout_seconds]` per call.
  Agent-supplied `timeout_ms` is honored only if lower than the config
  ceiling (matches `make.py`).
- Windows: refuse to run (POSIX-only `os.killpg`). Same gate as `make.py`.

**Why this matters for `gh` specifically:** `gh` can hang on interactive
auth prompts if the user is not authenticated (e.g. first run in a
container). Without `start_new_session` + `killpg`, a hung `gh auth login`
prompt would leave a zombie process group and the yoker agent would
hang indefinitely. The timeout + group-kill is the only reliable cleanup.

**Pre-flight auth check (recommended):** before running the real
operation, the tool can run `gh auth status --json` (with its own short
timeout, e.g. 5 s) once per session and cache the result. If
unauthenticated, return a clear error immediately without invoking the
real subcommand. This avoids the hang path entirely and gives a better
error message. `gh auth status` is read-only and does not print the
token. (Note: still keep the timeout/killpg defense — the pre-flight is
an optimization, not a substitute.)

---

## 7. Output Sanitization and Truncation

- Per-stream byte cap: `max_output_kb` (default 256). Truncate on a UTF-8
  boundary with a `... [truncated]` notice (copy `_truncate` from
  `make.py`).
- Redact secret patterns (§4.3) **before** truncation (so a secret just
  past the truncation point is not accidentally included).
- For list operations, enforce `limit <= 100` at the tool layer
  regardless of what the agent passes. This is a resource cap, not a
  security cap, but it bounds the amount of data the agent can pull into
  context per call.
- Strip ANSI color codes from `gh` output (set `NO_COLOR=1` in the
  inherited env, or pass `--no-color` where supported). Color escapes
  can obscure secret patterns from redaction regexes.

---

## 8. Audit Trail

Every invocation logs a structured event:

```json
{
  "event": "github_executed",
  "timestamp": "2026-07-27T10:30:00Z",
  "operation": "issue_view",
  "repo": "owner/repo",
  "number": 123,
  "exit_code": 0,
  "duration_ms": 342,
  "stdout_bytes": 1024,
  "stderr_bytes": 0,
  "redactions": {"ghp_token": 0, "url_creds": 1},
  "truncated": false
}
```

Never log the token, the full output, or the redacted text. Log counts
only. On rejection (bad operation, bad arg, timeout), log
`github_rejected` with the reason.

---

## 9. Security Checklist for Implementation

### 9.1 Must-Have (Blocking for T7.1)

- [ ] `operation` is a `Literal[...]` with exactly the 9 MVP values; no
      `str` passthrough.
- [ ] Runtime check: `operation` in `config.allowed_operations`; default
      is the full MVP set.
- [ ] `allowed_operations` validated against the enum at config load —
      unknown values raise.
- [ ] `subprocess` invocation uses list args, `start_new_session=True`,
      `NO_COLOR=1` in env.
- [ ] Timeout: `Popen` + `communicate(timeout=...)` + `os.killpg(SIGKILL)`
      on `TimeoutExpired`. Windows gate.
- [ ] `repo` validation: `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`, len <= 100,
      no leading `-`, `FORBIDDEN_CHARS` rejected.
- [ ] `number` is `int`, clamped to `[1, 2**31-1]`.
- [ ] `limit` clamped to `[1, 100]`.
- [ ] `state` is `Literal["open","closed","all"]`.
- [ ] `label`: no leading `-`, `FORBIDDEN_CHARS` rejected, len <= 100,
      passed as `--label=<value>`.
- [ ] `--` separator before user-supplied positionals where the
      subcommand accepts it.
- [ ] Per-operation arg schema (dict of allowed flags per operation,
      `git.py`-style). Unknown args rejected.
- [ ] Output: secret-pattern redaction (§4.3) before truncation; ANSI
      stripped; per-stream byte cap.
- [ ] No `env_vars` parameter in MVP.
- [ ] No `gh api`, `gh extension`, `gh auth token` reachable through any
      operation.
- [ ] Structured logging per call (§8); no token or full output logged.
- [ ] `gh` not installed → clear error. Not authenticated → clear error.

### 9.2 Tests (Blocking for T7.2)

- [ ] Each MVP operation produces the expected `gh` argv list (snapshot
      tests against `subprocess.Popen` mocked).
- [ ] Operation not in enum → rejected at validation.
- [ ] Operation in enum but not in `allowed_operations` → rejected.
- [ ] `repo` starting with `-` → rejected.
- [ ] `repo` with shell metachar → rejected.
- [ ] `repo` not matching `OWNER/REPO` → rejected.
- [ ] `label` starting with `-` → rejected.
- [ ] `label` with newline → rejected.
- [ ] `limit` over 100 → clamped to 100, `--limit=100` in argv.
- [ ] Timeout: mock `Popen.communicate` to raise `TimeoutExpired`;
      assert `os.killpg` called; assert error returned.
- [ ] Redaction: stdout containing `ghp_...` token returns
      `<redacted>`; `redactions` log field incremented.
- [ ] Truncation: stdout larger than `max_output_kb` is truncated on a
      UTF-8 boundary with the notice.
- [ ] Windows gate: on `sys.platform == "win32"`, returns error without
      invoking `gh`.
- [ ] Config load: `allowed_operations = ["bogus_op"]` raises a config
      error.

### 9.3 Phase 2 (Not blocking, documented here for continuity)

- [ ] Write operations (`issue_create`, `pr_merge`, etc.): separate
      `destructive_operations` config, default empty.
- [ ] Repository allowlist (`allowed_repos`).
- [ ] Optional direct-API mode (bypasses `gh`): requires its own security
      review (token storage, SSRF if a custom base URL is allowed).

---

## 10. Comparison with `git.py` and `make.py`

| Concern | `git.py` | `make.py` | `github.py` (this tool) |
|--------|---------|----------|--------------------------|
| Operation allowlist | `allowed_commands` config | `_TARGET_RE` + fixed `make` invocation | Fixed enum + `allowed_operations` config subset |
| Arg schema | `OPERATION_ARGS` per op | None (target only) | `OPERATION_ARGS` per op (same pattern) |
| Dangerous-option block | `DANGEROUS_OPTIONS` set | Leading-dash reject | Leading-dash reject + `FORBIDDEN_CHARS` |
| Shell metachars | `FORBIDDEN_CHARS` | `_FORBIDDEN_TARGET_CHARS` | `FORBIDDEN_CHARS` (same set) |
| Subprocess | `subprocess.run` (no group kill) | `Popen` + `killpg` on timeout | `Popen` + `killpg` on timeout (follow make.py) |
| Output redaction | `CREDENTIAL_PATTERN` (URL creds) | None | Extended pattern set (§4.3) |
| Env passthrough | n/a | `{**os.environ, **validated_env}` | `{**os.environ}` only, no agent env in MVP |
| Path guardrail | Yes (`.git` check) | Yes (PathGuardrail on cwd) | Not needed (no cwd / path param) |

**Note:** `git.py` uses `subprocess.run` (no `start_new_session`, no
group kill). This is a known gap in `git.py` that `make.py` fixed. The
`github` tool should follow `make.py`, not `git.py`, for subprocess
cleanup. (Separately, `git.py` should be backfilled to match — out of
scope for T7, add to backlog.)

---

## 11. Residual Risk

1. **Regex redaction is best-effort.** A secret with a non-standard format
   in a workflow log will pass through. Mitigation: per-stream byte cap;
   operator can disable `workflow_view` for leak-prone repos.
2. **`gh` auth token in `~/.config/gh/hosts.yml` is plaintext** (unless
   keyring is configured). Any process running as the user can read it.
   This is a `gh` design choice, not something the tool can fix. The tool
   does not read the file and does not expose it to the agent.
3. **The agent can read any repo the user's token can access.** The MVP
   has no repo allowlist. If the user's token has broad scope, so does
   the agent. Mitigation: document the recommendation to use a
   minimal-scope token (`public_repo` for public repos only); add
   `allowed_repos` in Phase 2.
4. **`gh` itself can have CVEs.** The tool runs whatever `gh` is on
   `PATH`. Operators should keep `gh` updated. Out of scope for the
   tool to enforce.
5. **Process-group kill on timeout is POSIX-only.** Windows users cannot
   use this tool. Acceptable for MVP; documented in the error message.

---

## 12. Classification of Findings

| Finding | Classification | Action |
|---------|---------------|--------|
| Operation enum as primary boundary | Blocking | Implement in T7.1 |
| Per-operation arg schema (git.py pattern) | Blocking | Implement in T7.1 |
| `--` separator before user positionals | Blocking | Implement in T7.1 |
| Process-group kill on timeout (make.py R4) | Blocking | Implement in T7.1 |
| Output secret redaction (extended patterns) | Blocking | Implement in T7.1 |
| Default-allow full MVP enum; default-deny Phase 2 writes | Blocking | Implement in T7.1 / config validation |
| `gh api` / `gh extension` / `gh auth token` exclusion | Blocking | Verify in review; add to test suite |
| No `env_vars` parameter in MVP | Blocking | Do not add |
| Pre-flight `gh auth status` cache | Related | Recommended optimization; skip if it complicates T7.1 |
| `git.py` subprocess gap (no group kill) | New | Backlog: backfill `git.py` to match `make.py` |
| Repo allowlist (`allowed_repos`) | New | Phase 2 backlog |
| Write operations (`issue_create`, `pr_merge`, etc.) | New | Phase 2 backlog; default-deny |
| Direct-API mode (no `gh`) | New | Post-1.0; separate security review required |

---

## 13. Positive Observations from Reference Code

- `make.py` provides a clean, well-documented subprocess-kill pattern
  (`start_new_session` + `os.killpg`) that `github.py` can adopt
  verbatim.
- `git.py`'s `OPERATION_ARGS` + `DANGEROUS_OPTIONS` + `FORBIDDEN_CHARS`
  pattern is directly transferable and is the right model for
  per-operation arg schemas.
- `git.py`'s `CREDENTIAL_PATTERN` redaction establishes the precedent
  for output sanitization; `github.py` extends it.
- The existing `analysis/api-github-tool.md` design already specifies
  `--json` structured output, which avoids screen-scraping and makes
  redaction easier (well-defined field boundaries).
- Config validation patterns (Clevis) provide config-load-time
  validation of `allowed_operations` against the enum.