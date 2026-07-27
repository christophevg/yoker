# API Design: GitHub Tool

**Document Version**: 1.1
**Date**: 2026-07-27
**Status**: Ready for implementation (Tier 2, MBI-009 T7)
**Replaces**: v1.0 (2026-04-30) — aligned with codebase conventions (async signature, flat `content_metadata`, `GitHubToolConfig`, `make.py` subprocess pattern)

## 1. Overview

### 1.1 Purpose

The `github` tool provides a secure, structured wrapper around the GitHub CLI
(`gh`) for common read-only repository operations. It enables agents to interact
with GitHub repositories, issues, pull requests, workflow runs, and releases
while maintaining strict security boundaries.

### 1.2 Design Principle

**Structured subcommand blocking is the whole point.** The owner confirmed
(MBI-009 §7.8): "github is required, note that we need to be able to block
certain subcommands (that's the whole point)." Without a general-purpose `run`
tool, this is the ONLY path for agents to interact with GitHub. The fixed
operation enum is the security boundary — the agent can only run the specific
`gh` subcommands in the configured allowlist, not arbitrary `gh` commands.

**Wrapper, not replacement**: wraps `gh` CLI rather than implementing a direct
GitHub API client. This leverages `gh`'s existing authentication
(`gh auth login`), maturity, rate-limit handling, and output formatting, and
keeps the token out of the agent's reach.

### 1.3 Scope

**In Scope (MVP — read-only):**
- `repo_view`, `issue_list`, `issue_view`, `pr_list`, `pr_view`,
  `workflow_list`, `workflow_view`, `release_list`, `release_view`

**Out of Scope (MVP):**
- Any write/mutate operation (create, comment, merge, delete, push)
- Organization-level operations
- Full workflow log viewing (Phase 2 — secrets risk)
- GitHub Enterprise custom base URLs (Phase 2)

### 1.4 Alignment with Codebase Conventions

This tool follows the established patterns of the other built-in tools:

| Concern | Reference | Pattern |
|---------|-----------|---------|
| Async function signature | `builtin/make.py`, `builtin/git.py` | `async def github(operation, ctx, ...) -> ToolResult` |
| Config dataclass | `MakeToolConfig`, `GitToolConfig`, `SearchToolConfig` | `@dataclass class GitHubToolConfig(ToolConfig)` in `config/__init__.py` |
| Subprocess execution | `builtin/make.py` | `subprocess.Popen` + `start_new_session=True` + `os.killpg` on timeout |
| List args, no shell | all command tools | `subprocess` with list args, never `shell=True` |
| Flat `content_metadata` | `builtin/read.py`, `builtin/update.py`, `builtin/search.py` | `{operation, path, content_type, content, metadata: {...}}` |
| Manifest registration | `builtin/__init__.py` | Add `github` to `__YOKER_MANIFEST__.tools` |
| Annotated param markers | `builtin/search.py`, `builtin/make.py` | `Annotated[str, Text("...")]` for string params |

The consumer `core/_processing.py:441-453` reads the flat keys
(`operation`, `path`, `content_type`, `content`, `metadata`) directly off
`tool_result.content_metadata` — this tool MUST emit that exact flat shape
(learned from the `read` C1 bug).

## 2. Tool Interface

### 2.1 Function Signature

```python
async def github(
  operation: str,
  ctx: ToolContext,
  repo: Annotated[str, Text("Repository in OWNER/REPO format (optional; defaults to current repo via gh)")] = "",
  number: int | None = None,
  tag: Annotated[str, Text("Release tag (for release_view only)")] = "",
  limit: int = 30,
  state: Annotated[str, Text("Filter by state for issue/pr list: 'open', 'closed', or 'all'")] = "open",
  label: Annotated[str, Text("Filter by label for issue_list (empty = no filter)")] = "",
  timeout_ms: int | None = None,
) -> ToolResult:
  """Perform a read-only GitHub operation via the gh CLI.

  Operations are restricted to a fixed enum and further gated by the
  configured allowlist (``tools.github.allowed_operations``). All commands
  run via ``subprocess`` with list args (no shell); timeout is enforced by
  killing the whole process group.
  """
```

**Parameter rules:**

| Parameter | Required by | Type / Validation |
|-----------|-------------|-------------------|
| `operation` | all | enum (see §2.2); must be in `allowed_operations` |
| `repo` | optional | `OWNER/REPO` regex `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`, max 100 chars; empty = gh auto-detects from git remote |
| `number` | `issue_view`, `pr_view`, `workflow_view` | positive int (issue/PR number or workflow run ID) |
| `tag` | `release_view` | non-empty string, validated against `^[A-Za-z0-9._-]+$`, max 100 chars |
| `limit` | list operations | int, clamped to `[1, config.max_results]` (default 100) |
| `state` | `issue_list`, `pr_list` | enum: `open`, `closed`, `all` |
| `label` | `issue_list` | string, max 100 chars, `^[A-Za-z0-9._-]+$` (no shell metacharacters) |
| `timeout_ms` | optional | int; clamped to `[1000, config.timeout_ms]` |

### 2.2 Operations (Fixed Enum)

The operation enum is the security boundary. The nine MVP operations are the
only `gh` subcommands the tool will ever invoke. Any other string is rejected
before subprocess execution.

| Operation | gh Subcommand | Required Params |
|-----------|---------------|-----------------|
| `repo_view` | `gh repo view [REPO] --json ...` | — |
| `issue_list` | `gh issue list [REPO] --state --label --limit --json ...` | — |
| `issue_view` | `gh issue view NUMBER [REPO] --json ...` | `number` |
| `pr_list` | `gh pr list [REPO] --state --limit --json ...` | — |
| `pr_view` | `gh pr view NUMBER [REPO] --json ...` | `number` |
| `workflow_list` | `gh run list [REPO] --limit --json ...` | — |
| `workflow_view` | `gh run view NUMBER [REPO] --json ...` | `number` (run ID) |
| `release_list` | `gh release list [REPO] --limit --json ...` | — |
| `release_view` | `gh release view TAG [REPO] --json ...` | `tag` |

**Corrections from v1.0:**
- `release_view` takes a **tag string** (not a number) — `gh release view <tag>`.
  Added the `tag` parameter.
- `workflow_view` takes a **workflow run ID** (integer) — `gh run view <run-id>`.
  The `number` parameter is reused for this.

### 2.3 JSON Field Selection (`--json`)

Each operation passes `--json` with explicit fields so the output is structured
and stable (no screen-scraping). The fields are fixed per operation:

| Operation | `--json` fields |
|-----------|-----------------|
| `repo_view` | `name,owner,description,visibility,stargazerCount,forkCount,primaryLanguage,url` |
| `issue_list` | `number,title,state,labels,author,createdAt` |
| `issue_view` | `number,title,body,state,labels,author,assignees,comments` |
| `pr_list` | `number,title,state,author,headRefName,createdAt` |
| `pr_view` | `number,title,body,state,author,baseRefName,headRefName,mergeable,files` |
| `workflow_list` | `databaseId,name,status,conclusion,headBranch,createdAt` |
| `workflow_view` | `databaseId,name,status,conclusion,jobs` |
| `release_list` | `tagName,name,isDraft,isPrerelease,createdAt` |
| `release_view` | `tagName,name,body,assets` |

Fields are appended as a single comma-joined string argument:
`["--json", "number,title,state,..."]`. No shell parsing is involved.

## 3. Configuration

### 3.1 `GitHubToolConfig`

Add to `src/yoker/config/__init__.py`, following the `MakeToolConfig` /
`SearchToolConfig` pattern:

```python
@dataclass
class GitHubToolConfig(ToolConfig):
  """GitHub tool configuration.

  Attributes:
    allowed_operations: Operations the agent is permitted to run. This is the
      subcommand-blocking security boundary. Defaults to all MVP (read-only)
      operations. Operations in the fixed enum but not in this list are
      rejected. An empty list disables the tool entirely.
    timeout_ms: Default per-call timeout in milliseconds.
    max_results: Maximum items returned per list operation (clamped upper bound
      for the ``limit`` parameter).
    require_explicit_repo: If True, the ``repo`` parameter is required (gh
      auto-detection from git remote is disabled).
    max_output_kb: Per-stream (stdout/stderr) truncation limit in KB.
  """

  allowed_operations: tuple[str, ...] = (
    "repo_view",
    "issue_list",
    "issue_view",
    "pr_list",
    "pr_view",
    "workflow_list",
    "workflow_view",
    "release_list",
    "release_view",
  )
  timeout_ms: int = 30000
  max_results: int = 100
  require_explicit_repo: bool = False
  max_output_kb: int = 100

  def __post_init__(self) -> None:
    """Validate GitHub tool configuration."""
    validate_positive_int(self.timeout_ms, "tools.github.timeout_ms")
    validate_positive_int(self.max_results, "tools.github.max_results")
    validate_positive_int(self.max_output_kb, "tools.github.max_output_kb")
    known = _GITHUB_OPERATIONS  # frozenset of the 9 MVP operations
    for op in self.allowed_operations:
      if op not in known:
        raise ValidationError(
          "tools.github.allowed_operations",
          op,
          f"unknown github operation; allowed: {sorted(known)}",
        )
```

Wire into `ToolsConfig`:

```python
@dataclass
class ToolsConfig:
  ...
  github: GitHubToolConfig = field(default_factory=GitHubToolConfig)
```

### 3.2 TOML Configuration

```toml
[tools.github]
enabled = true
# Subcommand blocking: only these operations are permitted.
# Remove an entry to block that gh subcommand. Empty list disables the tool.
allowed_operations = [
  "repo_view",
  "issue_list",
  "issue_view",
  "pr_list",
  "pr_view",
  "workflow_list",
  "workflow_view",
  "release_list",
  "release_view",
]
timeout_ms = 30000
max_results = 100
require_explicit_repo = false
max_output_kb = 100
```

**Subcommand-blocking examples:**

```toml
# Block workflow and release operations (e.g., secrets-conscious org)
[tools.github]
allowed_operations = ["repo_view", "issue_list", "issue_view", "pr_list", "pr_view"]

# Read-only issues only
[tools.github]
allowed_operations = ["issue_list", "issue_view"]

# Disable the tool entirely
[tools.github]
enabled = false
```

### 3.3 Agent Definition

```markdown
---
name: developer
tools: List, Read, Write, GitHub
---
```

## 4. Implementation Details

### 4.1 Subprocess Execution

Follow `builtin/make.py` exactly: `subprocess.Popen` with
`start_new_session=True` so the child leads its own process group; on timeout,
kill the whole group via `os.killpg(SIGKILL)` to prevent orphaned `gh`
children. **Never** `shell=True`; args are always a list.

```python
proc = subprocess.Popen(
  cmd,                      # ["gh", "issue", "view", "123", "--json", "..."]
  cwd=str(cwd),             # optional: project root, or None
  stdout=subprocess.PIPE,
  stderr=subprocess.PIPE,
  text=True,
  start_new_session=True,
)
try:
  stdout, stderr = proc.communicate(timeout=effective_timeout_seconds)
except subprocess.TimeoutExpired:
  _kill_process_group(proc.pid)
  try:
    stdout, stderr = proc.communicate(timeout=5)
  except subprocess.TimeoutExpired:
    stdout, stderr = (stdout or ""), (stderr or "")
  return ToolResult(success=False, error=f"github operation '{operation}' exceeded timeout ({effective_timeout_ms} ms)")
```

Reuse the `_truncate(text, max_bytes)` and `_kill_process_group(pid)` helpers
from `make.py` (either import them or duplicate the small functions; they are
trivial). Output is truncated per-stream on a UTF-8 boundary with a
`... [truncated]\n` notice.

### 4.2 Command Construction

Each operation builds its command list from a fixed template. No user string is
ever passed unescaped — all values are validated against tight regexes first.

```python
# repo_view, no repo specified (gh auto-detects)
["gh", "repo", "view", "--json", "name,owner,description,..."]

# issue_view with repo and number
["gh", "issue", "view", "123", "--repo", "owner/repo", "--json", "number,title,..."]

# issue_list with state, label, limit
["gh", "issue", "list", "--repo", "owner/repo", "--state", "open", "--label", "bug", "--limit", "30", "--json", "number,title,..."]
```

When `repo` is non-empty, pass it as `["--repo", repo]` rather than as a
positional `OWNER/REPO` argument. This is unambiguous and avoids any
path-as-arg parsing. When `repo` is empty and `require_explicit_repo` is True,
reject with an error. When `repo` is empty and `require_explicit_repo` is
False, omit `--repo` and let `gh` auto-detect from the git remote.

### 4.3 Validation (Pre-Subprocess)

All validation happens before subprocess execution, in this order:

1. **Config type check**: `ctx.config` is `GitHubToolConfig` (else error).
2. **Tool enabled**: `config.enabled` is True (else error).
3. **Operation enum**: `operation` is in `_GITHUB_OPERATIONS` (else error).
4. **Operation allowlist**: `operation` is in `config.allowed_operations` (else
   error — this is the subcommand-blocking gate).
5. **Parameter validation per operation**:
   - `repo` (if non-empty): matches `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`, ≤ 100 chars.
   - `number` (for view ops except `release_view`): positive int.
   - `tag` (for `release_view`): non-empty, matches `^[A-Za-z0-9._-]+$`, ≤ 100 chars.
   - `state`: one of `open`, `closed`, `all`.
   - `label`: matches `^[A-Za-z0-9._-]+$`, ≤ 100 chars.
   - `limit`: clamped to `[1, config.max_results]`.
   - `timeout_ms`: clamped to `[1000, config.timeout_ms]`.
6. **Required-parameter check**: `issue_view`/`pr_view`/`workflow_view` require
   `number`; `release_view` requires `tag` (else error).

Any forbidden character (`;`, `|`, `&`, `$`, backtick, newline, NUL) in any
string parameter is rejected. Leading dashes are rejected (flag injection).

### 4.4 Return Shape — Flat `content_metadata`

On success, the tool returns the raw `gh` JSON output as both `result` and
`content_metadata["content"]`, with the flat shape consumed by
`core/_processing.py:441-453`:

```python
content_metadata = {
  "operation": operation,            # e.g. "issue_view"
  "path": repo or "(current repo)",  # the repo context
  "content_type": "application/json",
  "content": stdout_out,             # the gh JSON output (truncated)
  "metadata": {
    "gh_subcommand": "gh issue view",
    "repo": repo,
    "number": number,                # None if not applicable
    "tag": tag,                      # None if not applicable
    "limit": effective_limit,        # None for view ops
    "state": state,                  # None for non-list ops
    "label": label,                  # None for non-issue-list ops
    "returncode": proc.returncode,
    "truncated": truncated,
  },
}

return ToolResult(
  success=True,
  result=stdout_out,
  content_metadata=content_metadata,
)
```

On error, return `ToolResult(success=False, error=<friendly message>)` with no
`content_metadata`. The `error` string is sanitized (no token leakage — `gh`
does not echo tokens, but we redact any `https://<user>:<token>@host` patterns
found in stderr, reusing the `CREDENTIAL_PATTERN` approach from `git.py`).

### 4.5 Error Handling

| Error | Detection | Response |
|-------|-----------|----------|
| `gh` not installed | `FileNotFoundError` from Popen | `"GitHub CLI not installed or not found in PATH"` |
| Not authenticated | gh exit != 0, stderr contains `authentication required` or `not logged in` | `"GitHub CLI not authenticated. Run 'gh auth login'."` |
| Rate limited | gh exit != 0, stderr contains `rate limit` | `"GitHub API rate limit exceeded. Retry later."` |
| Repo not found | gh exit != 0, stderr contains `could not resolve` / `not found` + `repo` | `"Repository not found: {repo}"` |
| Issue/PR/run not found | gh exit != 0, stderr contains `not found` + view op | `"{Resource} not found: {number/tag}"` |
| Timeout | `subprocess.TimeoutExpired` | Kill process group, `"github operation '{operation}' exceeded timeout ({ms} ms)"` |
| Operation not in allowlist | pre-subprocess check | `"Operation not allowed: {operation}. Allowed: {list}."` |
| Invalid params | pre-subprocess check | Specific validation message |
| Other gh failure | gh exit != 0 | Sanitized stderr (truncated) |

Stderr is always truncated to `max_output_kb` and run through
`CREDENTIAL_PATTERN.sub(r"\1<redacted>@", ...)` before being returned or logged.

## 5. Manifest Registration

In `src/yoker/builtin/__init__.py`:

```python
from yoker.builtin.github import github

__all__ = [
  ...,
  "github",
  ...,
]

__YOKER_MANIFEST__ = PluginManifest(
  tools=[existence, git, list, make, mkdir, read, search, update, webfetch, websearch, write, github],
  skills_dir="skills",
  agents_dir="agents",
)
```

`github` is a **static built-in tool** (in the manifest), not Session-injected.
It needs only `ToolContext` (for config + subprocess) and has no Session or
SkillRegistry dependency.

## 6. Security Model

### 6.1 Security Boundary

The operation allowlist (`config.allowed_operations`) is the security boundary.
The agent cannot run arbitrary `gh` commands — only the nine fixed operations,
and only those enabled in config. This is the whole point of the tool
(owner-confirmed).

### 6.2 Injection Resistance

- **No shell**: `subprocess.Popen` with list args, `shell=False`.
- **Tight regexes**: `repo`, `tag`, `label` validated against
  `^[A-Za-z0-9._-]+$`; `state` is enum-validated; `number`/`limit` are ints.
- **No leading dashes**: string params rejected if they start with `-`.
- **Forbidden chars**: `;|&\`$` + newline + NUL rejected in all string params.
- **Process-group kill**: on timeout, `os.killpg(SIGKILL)` kills `gh` and any
  children (e.g., a pager `gh` might spawn).

### 6.3 Token Handling

The agent never sees the GitHub token. `gh` manages authentication via
`~/.config/gh/hosts.yml` or the system keyring. The tool never reads, logs, or
returns the token. Stderr is scanned for `https://<user>:<secret>@host`
patterns and redacted before return (reusing `git.py`'s
`CREDENTIAL_PATTERN`).

### 6.4 Residual Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Workflow logs may contain leaked secrets | Medium | `workflow_view` returns run metadata + jobs summary, NOT full logs. Full log viewing is Phase 2 with explicit enablement. |
| Rate-limit exhaustion via agent loops | Low | Per-call timeout (30s default), `max_results` cap (100), agent-level retry budget is the caller's responsibility. |
| Private repo data exposure | Low | Auth gated by `gh auth`; private repos require the user's token to have access. The tool does not bypass repo visibility. |

## 7. Testing Strategy

### 7.1 Unit Tests (`tests/test_builtin/test_github.py`)

- Operation enum validation (rejects unknown operations)
- Allowlist enforcement (rejects operations not in `allowed_operations`)
- `repo` format validation (rejects shell metacharacters, leading dashes, bad format)
- `number` / `tag` / `state` / `label` / `limit` validation
- Required-parameter enforcement per operation
- Subprocess invocation with correct list args (mock `subprocess.Popen`)
- Timeout enforcement (mock `TimeoutExpired`, assert process group killed)
- Output truncation
- Error mapping for each error class in §4.5
- Flat `content_metadata` shape (asserts the 5 top-level keys + `metadata`)
- Credential redaction in stderr

### 7.2 Integration Tests

- Mock `gh` via `subprocess.Popen` patching; verify the exact command list per
  operation.
- Test with `gh` not found (`FileNotFoundError`).
- Test with `require_explicit_repo=True` and empty `repo`.

### 7.3 Acceptance (from MBI-009 T7.1)

- `github(operation="pr_view", repo="owner/repo", number=123)` returns PR info
- `github(operation="issue_list", repo="owner/repo")` returns issues
- Operation not in allowlist is rejected
- Operations can be disabled via config (`allowed_operations`)
- Timeout is enforced

## 8. Future Considerations (Post-1.0)

### 8.1 Phase 2: Write Operations

- `issue_create`, `issue_comment`, `pr_create`, `pr_comment`, `release_create`
- Require `allow_destructive = true` + explicit per-operation enablement
- Optional confirmation prompt via `askuserquestion` tool

### 8.2 Phase 2: Destructive Operations

- `pr_merge`, `branch_delete`
- Require `allow_destructive = true` + `destructive_operations` allowlist +
  confirmation

### 8.3 Phase 2: Repository Allowlist

```toml
[tools.github]
allowed_repos = ["owner/repo1", "owner/repo2"]
```

### 8.4 Phase 2: Full Workflow Logs

`workflow_view` with `--log` flag; requires explicit enablement due to
secrets-leak risk.

### 8.5 Phase 2: GitHub Enterprise

Custom base URL configuration (`GH_HOST` env or `--hostname` flag).

## 9. Action Items

- [ ] T7.1 Implement `src/yoker/builtin/github.py` per §2–§5
- [ ] T7.1 Add `GitHubToolConfig` to `src/yoker/config/__init__.py` per §3.1
- [ ] T7.1 Wire `github` into `__YOKER_MANIFEST__` per §5
- [ ] T7.2 Add `tests/test_builtin/test_github.py` per §7
- [ ] T7.2 `make check` green
- [ ] Update `README.md` with `github` tool usage and subcommand-blocking note