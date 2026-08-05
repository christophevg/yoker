"""GitHub tool implementation for Yoker.

Wraps the ``gh`` CLI for a fixed set of GitHub operations. Read operations
are auto-permitted via the default allowlist. Write operations (``pr_create``,
``release_create``) require explicit opt-in via ``allowed_operations`` in
config — they are never in the default allowlist. The operation enum is the
security boundary: the agent can only invoke the hardcoded ``gh`` subcommands
listed in ``_OPERATION_DISPATCH`` — never ``gh extension``, ``gh auth
token``, or any unlisted subcommand. The ``pr_reviews`` and ``pr_comments``
operations use ``gh api`` with hardcoded REST endpoint templates (read-only).

Security model
--------------
- **Operation enum + allowlist**: ``operation`` must be in the fixed enum
  AND in ``GitHubToolConfig.allowed_operations``. Read operations are
  default-allowed; write operations require explicit config opt-in. This is
  the subcommand-blocking gate.
- **No shell**: ``subprocess.Popen`` with list args, ``shell=False``.
- **Argument-injection defenses**: tight regexes for ``repo``/``tag``/``label``,
  enum check for ``state``, int clamps for ``number``/``limit``, leading-dash
  rejection, ``FORBIDDEN_CHARS`` rejection, ``--`` separator before any
  user-supplied positional. Write-operation flag values (``--title=...``,
  ``--body=...``, ``--notes=...``) use ``=`` format so values starting with
  ``-`` are never interpreted as flags.
- **Process-group kill on timeout (R4)**: ``start_new_session=True`` +
  ``os.killpg(SIGKILL)`` so ``gh`` and any children (pagers, git helpers)
  are cleaned up on timeout. POSIX-only — Windows is refused.
- **Output redaction**: stdout/stderr run through an extended credential
  pattern set (GitHub tokens, AWS keys, Slack/npm tokens, URL-embedded
  credentials) BEFORE truncation. Log counts only, never matched text.
- **No env passthrough**: the agent cannot supply env vars (``GH_TOKEN``,
  ``GH_HOST`` are credential-injection channels). The inherited
  ``os.environ`` is passed through unchanged so ``gh`` can find its config.
"""

import asyncio
import json
import os
import re
import signal
import sys
from typing import Annotated, Any

from structlog import get_logger

from yoker.config import GitHubToolConfig
from yoker.tools.annotations import Text, tool
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult

logger = get_logger(__name__)

# --- The security boundary: hardcoded operation → gh subcommand dispatch ---
# No passthrough. The agent never influences which gh subcommand runs; they
# only influence the validated arguments of a fixed subcommand.
_GITHUB_OPERATIONS: frozenset[str] = frozenset(
  {
    "repo_view",
    "issue_list",
    "issue_view",
    "pr_list",
    "pr_view",
    "pr_reviews",
    "pr_comments",
    "workflow_list",
    "workflow_view",
    "workflow_logs",
    "release_list",
    "release_view",
    "pr_create",
    "release_create",
  }
)

# Operations that modify GitHub state. These require explicit opt-in via
# ``GitHubToolConfig.allowed_operations`` — they are NOT in the default
# allowlist. Even when allowed, they are never auto-permitted (the config
# owner must consciously add them).
_WRITE_OPS: frozenset[str] = frozenset({"pr_create", "release_create"})

# (gh_subcommand_prefix, --json fields, required_param)
_OPERATION_DISPATCH: dict[str, tuple[list[str], str, str | None]] = {
  "repo_view": (
    ["repo", "view"],
    "name,owner,description,visibility,stargazerCount,forkCount,primaryLanguage,url",
    None,
  ),
  "issue_list": (
    ["issue", "list"],
    "number,title,state,labels,author,createdAt",
    None,
  ),
  "issue_view": (
    ["issue", "view"],
    "number,title,body,state,labels,author,assignees,comments",
    "number",
  ),
  "pr_list": (
    ["pr", "list"],
    "number,title,state,author,headRefName,createdAt,reviewDecision,statusCheckRollup",
    None,
  ),
  "pr_view": (
    ["pr", "view"],
    "number,title,body,state,author,baseRefName,headRefName,mergeable,files,reviewDecision,statusCheckRollup",
    "number",
  ),
  "pr_reviews": (
    ["api", "repos/{repo}/pulls/{number}/reviews"],
    "id,user,state,body,submitted_at",
    "number",
  ),
  "pr_comments": (
    ["api", "repos/{repo}/pulls/{number}/comments"],
    "id,user,body,path,line,created_at",
    "number",
  ),
  "workflow_list": (
    ["run", "list"],
    "databaseId,name,status,conclusion,headBranch,createdAt",
    None,
  ),
  "workflow_view": (["run", "view"], "databaseId,name,status,conclusion,jobs", "number"),
  "workflow_logs": (["run", "view", "--log-failed"], "", "number"),
  "release_list": (
    ["release", "list"],
    "tagName,name,isDraft,isPrerelease,createdAt",
    None,
  ),
  "release_view": (["release", "view"], "tagName,name,body,assets", "tag"),
  "pr_create": (
    ["pr", "create"],
    "number,url,title,state",
    None,
  ),
  "release_create": (
    ["release", "create"],
    "url,tagName,name,isDraft,isPrerelease",
    None,
  ),
}

# Operations that use ``gh api`` instead of a regular ``gh`` subcommand.
# For these, the dispatch prefix is a template with ``{repo}`` and/or
# ``{number}`` placeholders, and the fields are passed via ``--jq`` instead
# of ``--json``.
_API_OPS: frozenset[str] = frozenset({"pr_reviews", "pr_comments"})

# Operations that return plain text (not JSON). These skip ``--json`` —
# ``gh`` outputs raw log lines directly to stdout.
_PLAINTEXT_OPS: frozenset[str] = frozenset({"workflow_logs"})

# Operations that accept the named flag.
_STATE_OPS: frozenset[str] = frozenset({"issue_list", "pr_list"})
_LABEL_OPS: frozenset[str] = frozenset({"issue_list"})
_LIMIT_OPS: frozenset[str] = frozenset({"issue_list", "pr_list", "workflow_list", "release_list"})

# --- Validation regexes (tight allowlists) ---
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_TAG_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_VALID_STATES: frozenset[str] = frozenset({"open", "closed", "all"})

# Same set as git.py / make.py: shell metacharacters + owner's five.
_FORBIDDEN_CHARS: frozenset[str] = frozenset({";", "|", "&", "$", "`", "\n", "\r", "\x00"})

_MAX_REPO_LEN = 100
_MAX_TAG_LABEL_LEN = 100
_MAX_NUMBER = 2**63 - 1  # GitHub run IDs are 64-bit integers; PR/issue numbers are much smaller

_TRUNCATION_NOTICE = "\n... [truncated]\n"

# --- Output redaction (extended from git.py's CREDENTIAL_PATTERN) ---
# Patterns are intentionally broad; false positives are acceptable, false
# negatives are not. Applied to stdout and stderr BEFORE truncation.
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
  (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "ghp_token"),
  (re.compile(r"github_pat_[A-Za-z0-9_]{82}"), "github_pat"),
  (re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"), "aws_key_id"),
  (re.compile(r"xox[baprs]-[A-Za-z0-9-]+"), "slack_token"),
  (re.compile(r"npm_[A-Za-z0-9]{36}"), "npm_token"),
  (re.compile(r"(https?://)[^:\s]+:[^@\s]+@"), "url_creds"),
]
_REDACT_REPLACEMENT = "<redacted>"


@tool(
  description=(
    "Perform a GitHub operation via the ``gh`` CLI.\n"
    "\n"
    "Operations:\n"
    "  repo_view      — View repository info. Optional: repo.\n"
    "  issue_list     — List issues. Optional: repo, limit, state, label.\n"
    "  issue_view     — View an issue. Required: number. Optional: repo.\n"
    "  pr_list        — List pull requests. Optional: repo, limit, state.\n"
    "  pr_view        — View a pull request. Required: number. Optional: repo, include_comments.\n"
    "  pr_reviews     — List PR reviews. Required: repo, number.\n"
    "  pr_comments    — List PR inline review comments. Required: repo, number.\n"
    "  workflow_list  — List workflow runs (CI). Optional: repo, limit.\n"
    "  workflow_view  — View a workflow run (CI). Required: number (run ID). Optional: repo.\n"
    "  workflow_logs  — View failed-step logs of a workflow run. Required: number (run ID). Optional: repo.\n"
    "  release_list   — List releases. Optional: repo, limit.\n"
    "  release_view   — View a release. Required: tag. Optional: repo.\n"
    "  pr_create      — Create a PR. Required: repo, title, body. Optional: head, base.\n"
    "  release_create — Create a release. Required: repo, tag, title, notes. Optional: draft, prerelease.\n"
    "\n"
    "Common parameters:\n"
    '  repo    — "owner/name" (e.g. "octocat/Hello-World"). If omitted, uses current git repo.\n'
    "  number  — Issue/PR number or workflow run ID (integer >= 1).\n"
    '  state   — Filter: "open", "closed", or "all" (default: "open"). Only for list operations.\n'
    "  limit   — Max items for list operations (default: 30, max: config ceiling).\n"
    "  include_comments — If True, fetch and merge PR comments into pr_view output (only for pr_view).\n"
    "  timeout_ms — Override default timeout in milliseconds (clamped to config ceiling).\n"
    "  draft   — Mark release as draft (only for release_create).\n"
    "  prerelease — Mark release as prerelease (only for release_create).\n"
    "  post_filter — Optional regex to filter output lines. Use specific patterns: "
    "'FAILED|CalledProcessError|short test summary' for CI logs, 'class |def ' for "
    "code structure. Avoid broad terms like 'error' that match test names."
  )
)
async def github(
  operation: Annotated[
    str,
    Text(
      "GitHub operation. One of: repo_view, issue_list, issue_view, pr_list, "
      "pr_view, pr_reviews, pr_comments, workflow_list, workflow_view, "
      "workflow_logs, release_list, release_view, pr_create, release_create."
    ),
  ],
  ctx: ToolContext,
  repo: Annotated[str, Text("Repository as owner/name")] = "",
  number: Annotated[
    int | None,
    Text(
      "Issue/PR number or workflow run ID (required for issue_view, pr_view, workflow_view, pr_reviews, pr_comments)"
    ),
  ] = None,
  tag: Annotated[str, Text("Release tag (for release_view)")] = "",
  limit: Annotated[int, Text("Max items to return for list operations (default: 30)")] = 30,
  state: Annotated[
    str,
    Text(
      "Filter by state: 'open', 'closed', or 'all' (default: 'open', only for issue_list and pr_list)"
    ),
  ] = "open",
  label: Annotated[str, Text("Filter by label (for issue_list)")] = "",
  include_comments: Annotated[
    bool, Text("If True, fetch and merge PR comments into pr_view output (only for pr_view)")
  ] = False,
  timeout_ms: Annotated[
    int | None, Text("Override default timeout in milliseconds (clamped to config ceiling)")
  ] = None,
  # --- pr_create parameters ---
  title: Annotated[str, Text("PR title (for pr_create)")] = "",
  body: Annotated[str, Text("PR body/description (for pr_create)")] = "",
  head: Annotated[str, Text("Source branch for PR (for pr_create)")] = "",
  base: Annotated[str, Text("Target branch for PR (for pr_create)")] = "",
  # --- release_create parameters ---
  notes: Annotated[str, Text("Release notes body (for release_create)")] = "",
  draft: Annotated[bool, Text("Mark release as draft (only for release_create)")] = False,
  prerelease: Annotated[bool, Text("Mark release as prerelease (only for release_create)")] = False,
) -> ToolResult:
  """Perform a GitHub operation via the ``gh`` CLI.

  Read operations are restricted to a fixed enum (the security boundary)
  and further gated by ``GitHubToolConfig.allowed_operations``. Write
  operations (``pr_create``, ``release_create``) require explicit opt-in via
  ``allowed_operations`` — they are NOT in the default allowlist. All commands
  run via ``subprocess`` with list args (no shell); timeout is enforced by
  killing the whole process group.

  When ``include_comments=True`` (only for ``pr_view``), a second ``gh api``
  call fetches PR comments and inline review comments, merged into the
  result JSON under a ``comments`` key.

  ``pr_create`` requires ``repo``, ``title``, and ``body``. Optional ``head``
  (source branch) and ``base`` (target branch) default to the current branch
  and repo default respectively.

  ``release_create`` requires ``repo``, ``tag``, ``title``, and ``notes``.
  Optional ``draft`` and ``prerelease`` flags default to false.
  """
  # --- 1. Config type check ---
  gh_config = ctx.config
  if not isinstance(gh_config, GitHubToolConfig):
    logger.warning("github_invalid_config_type", config_type=type(gh_config).__name__)
    return ToolResult(success=False, error="Invalid configuration for github tool")

  # --- 2. Tool enabled check ---
  if not gh_config.enabled:
    return ToolResult(success=False, error="github tool is disabled")

  # --- 3. Operation in enum check (security boundary) ---
  if not isinstance(operation, str) or operation not in _GITHUB_OPERATIONS:
    logger.info("github_rejected", reason="unknown_operation", operation=operation)
    return ToolResult(
      success=False,
      error=f"Unknown operation: {operation!r}. Allowed: {sorted(_GITHUB_OPERATIONS)}",
    )

  # --- 4. Operation in configured allowlist check (subcommand blocking) ---
  if operation not in gh_config.allowed_operations:
    logger.info(
      "github_rejected",
      reason="operation_not_allowed",
      operation=operation,
    )
    return ToolResult(
      success=False,
      error=(f"Operation not allowed: {operation}. Allowed: {list(gh_config.allowed_operations)}"),
    )

  # --- 5. Per-parameter validation ---
  param_error = _validate_params(operation, repo, number, tag, limit, state, label, gh_config)
  if param_error is not None:
    logger.info("github_rejected", reason="invalid_param", error=param_error)
    return ToolResult(success=False, error=param_error)

  # --- 5b. include_comments only valid for pr_view ---
  if include_comments and operation != "pr_view":
    return ToolResult(
      success=False,
      error=f"Parameter 'include_comments' is only supported for 'pr_view', not '{operation}'",
    )

  # --- 5c. API ops require explicit repo (gh api has no auto-detect) ---
  if operation in _API_OPS and not repo:
    return ToolResult(
      success=False,
      error=f"Operation '{operation}' requires a 'repo' parameter (owner/name)",
    )

  # --- 5d. Write-operation parameter validation ---
  if operation == "pr_create":
    werr = _validate_pr_create_params(repo, title, body, head, base)
    if werr is not None:
      logger.info("github_rejected", reason="invalid_pr_create_param", error=werr)
      return ToolResult(success=False, error=werr)

  if operation == "release_create":
    werr = _validate_release_create_params(repo, tag, title, notes)
    if werr is not None:
      logger.info("github_rejected", reason="invalid_release_create_param", error=werr)
      return ToolResult(success=False, error=werr)

  # --- 6. Required-parameter check ---
  _subcmd, _fields, required = _OPERATION_DISPATCH[operation]
  if required == "number" and (number is None or number < 1):
    return ToolResult(success=False, error=f"Operation {operation!r} requires a positive 'number'")
  if required == "tag" and not tag:
    return ToolResult(success=False, error=f"Operation {operation!r} requires a non-empty 'tag'")

  # --- Windows platform gate (POSIX-only process-group kill) ---
  if sys.platform == "win32":
    return ToolResult(
      success=False,
      error="github tool requires POSIX process-group support; not available on Windows",
    )

  # --- Timeout clamp (caller may lower, never raise, the config ceiling) ---
  effective_timeout_ms = _clamp_timeout(timeout_ms, gh_config.timeout_ms)
  effective_limit = max(1, min(limit, gh_config.max_results))

  cmd = _build_command(operation, repo, number, tag, effective_limit, state, label)
  cmd.extend(_build_write_args(operation, title, body, head, base, notes, draft, prerelease, tag))

  logger.info(
    "github_executing",
    operation=operation,
    repo=repo or "(auto)",
    number=number,
    tag=tag,
    limit=effective_limit,
  )

  # --- Subprocess execution (async so the event loop stays responsive) ---
  try:
    proc = await asyncio.create_subprocess_exec(
      *cmd,
      cwd=None,
      env=os.environ,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
      start_new_session=True,
    )
  except FileNotFoundError:
    logger.error("github_not_found", operation=operation)
    return ToolResult(
      success=False,
      error="GitHub CLI (gh) not found. Install it from https://cli.github.com/",
    )

  stdout = ""
  stderr = ""
  try:
    stdout_b, stderr_b = await asyncio.wait_for(
      proc.communicate(), timeout=effective_timeout_ms / 1000
    )
    stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
    stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
  except asyncio.TimeoutError:
    _kill_process_group(proc.pid)
    try:
      stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=5)
      stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
      stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
    except asyncio.TimeoutError:
      pass
    logger.warning("github_timeout", operation=operation, timeout_ms=effective_timeout_ms)
    return ToolResult(
      success=False,
      error=f"GitHub operation timed out after {effective_timeout_ms}ms",
    )

  # --- Redact secrets BEFORE returning (no truncation here — the framework
  # enforces output limits centrally in _execute_tool AFTER post_filter is
  # applied, so the LLM can use post_filter to narrow large outputs). ---
  stdout, redactions_out = _redact(stdout or "")
  stderr, redactions_err = _redact(stderr or "")
  total_redactions = redactions_out + redactions_err
  if total_redactions:
    logger.info(
      "github_secret_redacted",
      count=total_redactions,
      stdout_redactions=redactions_out,
      stderr_redactions=redactions_err,
    )

  stdout_out = stdout
  stderr_out = stderr

  returncode = proc.returncode
  if operation in _API_OPS:
    gh_subcommand = f"gh api {_OPERATION_DISPATCH[operation][0][1]}"
  elif operation in _WRITE_OPS:
    gh_subcommand = f"gh {' '.join(_OPERATION_DISPATCH[operation][0])}"
  elif operation in _PLAINTEXT_OPS:
    gh_subcommand = f"gh {' '.join(_OPERATION_DISPATCH[operation][0])}"
  else:
    gh_subcommand = f"gh {' '.join(_OPERATION_DISPATCH[operation][0])} --json"

  if returncode == 0:
    # --- pr_view with include_comments: fetch and merge comments ---
    if operation == "pr_view" and include_comments and repo and number:
      stdout_out = await _merge_comments(stdout_out, repo, number, effective_timeout_ms)

    # --- Write ops: gh outputs a URL, not JSON. Parse it into a JSON object. ---
    if operation in _WRITE_OPS:
      stdout_out = _parse_write_output(operation, stdout_out, tag)

    content_type = "text/plain" if operation in _PLAINTEXT_OPS else "application/json"
    content_metadata = {
      "operation": "github",
      "path": repo or "default",
      "content_type": content_type,
      "content": stdout_out,
      "metadata": {
        "gh_subcommand": gh_subcommand,
        "repo": repo,
        "number": number,
        "tag": tag,
        "limit": effective_limit if operation in _LIMIT_OPS else None,
        "state": state if operation in _STATE_OPS else None,
        "label": label if operation in _LABEL_OPS else None,
        "returncode": returncode,
      },
    }
    return ToolResult(
      success=True,
      result=stdout_out,
      content_metadata=content_metadata,
    )

  # --- Error mapping based on stderr content ---
  friendly = _map_error(stderr_out, operation, repo, number, tag)
  logger.info(
    "github_failed",
    operation=operation,
    returncode=returncode,
    redactions=total_redactions,
  )
  return ToolResult(success=False, error=friendly)


def _validate_text_field(
  name: str,
  value: str,
  min_len: int = 1,
  max_len: int = 100000,
) -> str | None:
  """Validate a free-text field for write operations.

  Uses the same forbidden-char checks as other params but allows newlines
  (PR bodies and release notes are multi-line). Returns error string or None.
  """
  if not value or not isinstance(value, str):
    return f"Parameter '{name}' is required"
  if len(value) < min_len:
    return f"Parameter '{name}' must be at least {min_len} character(s)"
  if len(value) > max_len:
    return f"Parameter '{name}' exceeds {max_len} characters"
  # Reject NUL and shell metacharacters, but allow newlines and tabs.
  forbidden = _FORBIDDEN_CHARS - {"\n", "\r"}
  if any(c in value for c in forbidden):
    return f"Parameter '{name}' contains forbidden character"
  return None


def _validate_branch_name(name: str, field: str) -> str | None:
  """Validate a git branch name for head/base parameters."""
  if not name:
    return None  # optional
  if not isinstance(name, str):
    return f"Parameter '{field}' must be a string"
  if name.startswith("-"):
    return f"Parameter '{field}' must not start with '-'"
  if len(name) > 255:
    return f"Parameter '{field}' exceeds 255 characters"
  # Allow typical branch name characters: alphanumerics, -, _, /, .
  if not re.fullmatch(r"[A-Za-z0-9._/-]+", name):
    return f"Invalid {field} format: {name!r}"
  if _contains_forbidden(name):
    return f"Parameter '{field}' contains forbidden character"
  return None


def _validate_pr_create_params(
  repo: str, title: str, body: str, head: str, base: str
) -> str | None:
  """Validate parameters for pr_create operation."""
  if not repo:
    return "Parameter 'repo' is required for pr_create"
  err = _validate_text_field("title", title, max_len=1024)
  if err is not None:
    return err
  err = _validate_text_field("body", body, max_len=100000)
  if err is not None:
    return err
  err = _validate_branch_name(head, "head")
  if err is not None:
    return err
  err = _validate_branch_name(base, "base")
  if err is not None:
    return err
  return None


def _validate_release_create_params(repo: str, tag: str, title: str, notes: str) -> str | None:
  """Validate parameters for release_create operation."""
  if not repo:
    return "Parameter 'repo' is required for release_create"
  if not tag or not isinstance(tag, str):
    return "Parameter 'tag' is required for release_create"
  if tag.startswith("-"):
    return "Parameter 'tag' must not start with '-'"
  if len(tag) > _MAX_TAG_LABEL_LEN:
    return f"Parameter 'tag' exceeds {_MAX_TAG_LABEL_LEN} characters"
  if not _TAG_LABEL_RE.fullmatch(tag):
    return f"Invalid tag format: {tag!r}"
  if _contains_forbidden(tag):
    return "Parameter 'tag' contains forbidden character"
  err = _validate_text_field("title", title, max_len=1024)
  if err is not None:
    return err
  err = _validate_text_field("notes", notes, max_len=100000)
  if err is not None:
    return err
  return None


def _build_write_args(
  operation: str,
  title: str,
  body: str,
  head: str,
  base: str,
  notes: str,
  draft: bool,
  prerelease: bool,
  tag: str,
) -> list[str]:
  """Build the extra CLI args for write operations.

  For ``pr_create``: ``--title=...``, ``--body=...``, optional ``--head=...``,
  ``--base=...``.
  For ``release_create``: positional tag, ``--title=...``, ``--notes=...``,
  optional ``--draft``, ``--prerelease``.

  Uses ``=`` format (``--title=value``) so values starting with ``-`` are
  treated as the flag's value, not as a new flag. This is defense-in-depth:
  the values are already validated to not start with ``-`` (branch names,
  tag) or are free-text (title, body, notes) where leading ``-`` is
  acceptable because ``=`` unambiguously assigns the value.
  """
  if operation == "pr_create":
    args: list[str] = [
      f"--title={title}",
      f"--body={body}",
    ]
    if head:
      args.append(f"--head={head}")
    if base:
      args.append(f"--base={base}")
    return args

  if operation == "release_create":
    args = [
      tag,
      f"--title={title}",
      f"--notes={notes}",
    ]
    if draft:
      args.append("--draft")
    if prerelease:
      args.append("--prerelease")
    return args

  return []


def _validate_params(
  operation: str,
  repo: str,
  number: int | None,
  tag: str,
  limit: int,
  state: str,
  label: str,
  config: GitHubToolConfig,
) -> str | None:
  """Validate parameters before subprocess execution. Returns error string or None."""
  # repo
  if repo:
    if not isinstance(repo, str):
      return "Parameter 'repo' must be a string"
    if repo.startswith("-"):
      return "Parameter 'repo' must not start with '-'"
    if len(repo) > _MAX_REPO_LEN:
      return f"Parameter 'repo' exceeds {_MAX_REPO_LEN} characters"
    if not _REPO_RE.fullmatch(repo):
      return f"Invalid repo format: {repo!r}. Expected 'owner/name'"
    if _contains_forbidden(repo):
      return "Parameter 'repo' contains forbidden character"
  elif config.require_explicit_repo:
    return "Parameter 'repo' is required (require_explicit_repo is enabled)"

  # number
  if number is not None:
    if not isinstance(number, int) or isinstance(number, bool):
      return "Parameter 'number' must be an integer"
    if number < 1:
      return "Parameter 'number' must be >= 1"
    if number > _MAX_NUMBER:
      return f"Parameter 'number' must be <= {_MAX_NUMBER}"

  # tag
  if tag:
    if not isinstance(tag, str):
      return "Parameter 'tag' must be a string"
    if tag.startswith("-"):
      return "Parameter 'tag' must not start with '-'"
    if len(tag) > _MAX_TAG_LABEL_LEN:
      return f"Parameter 'tag' exceeds {_MAX_TAG_LABEL_LEN} characters"
    if not _TAG_LABEL_RE.fullmatch(tag):
      return f"Invalid tag format: {tag!r}"
    if _contains_forbidden(tag):
      return "Parameter 'tag' contains forbidden character"

  # limit
  if not isinstance(limit, int) or isinstance(limit, bool):
    return "Parameter 'limit' must be an integer"
  if limit < 1:
    return "Parameter 'limit' must be >= 1"

  # state
  if not isinstance(state, str):
    return "Parameter 'state' must be a string"
  if state not in _VALID_STATES:
    return f"Invalid state: {state!r}. Must be one of {sorted(_VALID_STATES)}"
  if _contains_forbidden(state):
    return "Parameter 'state' contains forbidden character"

  # label
  if label:
    if not isinstance(label, str):
      return "Parameter 'label' must be a string"
    if label.startswith("-"):
      return "Parameter 'label' must not start with '-'"
    if len(label) > _MAX_TAG_LABEL_LEN:
      return f"Parameter 'label' exceeds {_MAX_TAG_LABEL_LEN} characters"
    if not _TAG_LABEL_RE.fullmatch(label):
      return f"Invalid label format: {label!r}"
    if _contains_forbidden(label):
      return "Parameter 'label' contains forbidden character"

  return None


def _contains_forbidden(value: str) -> bool:
  """Return True if the value contains any forbidden character."""
  return any(char in value for char in _FORBIDDEN_CHARS)


def _clamp_timeout(timeout_ms: int | None, ceiling_ms: int) -> int:
  """Clamp the caller-supplied timeout to [1000, ceiling_ms]."""
  if timeout_ms is None:
    return ceiling_ms
  return max(min(timeout_ms, ceiling_ms), 1000)


def _build_command(
  operation: str,
  repo: str,
  number: int | None,
  tag: str,
  limit: int,
  state: str,
  label: str,
) -> list[str]:
  """Build the gh command list from the operation's fixed template.

  All user-supplied values have been validated before this is called. The
  ``--`` separator is placed before the user-supplied positional (issue/PR
  number or release tag) so anything after it is treated as an operand,
  not a flag — defense in depth against flag injection.

  For ``_API_OPS`` (``pr_reviews``, ``pr_comments``), the command uses
  ``gh api`` with a URL template and ``--jq`` instead of ``--json``.
  """
  subcmd, fields, required = _OPERATION_DISPATCH[operation]

  if operation in _API_OPS:
    # subcmd is ["api", "repos/{repo}/pulls/{number}/reviews"] etc.
    url_template = subcmd[1]
    url = url_template.replace("{repo}", repo).replace("{number}", str(number))
    return ["gh", "api", url, "--jq", _api_jq_fields(fields)]

  cmd: list[str] = ["gh", *subcmd]

  if repo:
    cmd.extend(["--repo", repo])

  if operation in _STATE_OPS:
    cmd.extend(["--state", state])
  if operation in _LABEL_OPS and label:
    cmd.extend(["--label", label])
  if operation in _LIMIT_OPS:
    cmd.extend(["--limit", str(limit)])

  # Write operations (pr_create, release_create) don't support --json;
  # they output a URL on success which is parsed separately.
  # Plaintext operations (workflow_logs) return raw text, not JSON.
  if operation not in _WRITE_OPS and operation not in _PLAINTEXT_OPS:
    cmd.extend(["--json", fields])

  if required == "number":
    cmd.extend(["--", str(number)])
  elif required == "tag":
    cmd.extend(["--", tag])

  return cmd


def _api_jq_fields(fields: str) -> str:
  """Convert a comma-separated field list to a ``--jq`` expression for ``gh api``.

  Wraps in ``[.[] | { ... }]`` so the expression iterates over array
  elements. When the API returns ``[]`` (empty array), ``.[]`` produces no
  values and the result is ``[]`` — no error.
  """
  field_map = {
    "id": ".id",
    "user": ".user.login",
    "state": ".state",
    "body": ".body",
    "submitted_at": ".submitted_at",
    "path": ".path",
    "line": ".line",
    "created_at": ".created_at",
  }
  parts = [f"{f}: {field_map.get(f, f'.{f}')}" for f in fields.split(",")]
  return "[.[] | {" + ", ".join(parts) + "}]"


def _parse_write_output(operation: str, stdout: str, tag: str) -> str:
  """Parse the text output of a write operation into a JSON object.

  ``gh pr create`` outputs a URL like ``https://github.com/owner/repo/pull/42``.
  ``gh release create`` outputs a URL like ``https://github.com/owner/repo/releases/tag/v1.0``.

  Returns a JSON string with a ``url`` field and, for PRs, an extracted ``number``.
  Falls back to ``{"url": stdout.strip()}`` if parsing fails.
  """
  url = stdout.strip()
  result: dict[str, Any] = {"url": url}

  if operation == "pr_create":
    # Extract PR number from URL: .../pull/42
    match = re.search(r"/pull/(\d+)", url)
    if match:
      result["number"] = int(match.group(1))
  elif operation == "release_create":
    result["tagName"] = tag

  return json.dumps(result)


async def _merge_comments(pr_json: str, repo: str, number: int, timeout_ms: int) -> str:
  """Fetch PR comments via ``gh api`` and merge them into the PR JSON output.

  Returns the original JSON if the comments fetch fails or the PR JSON is
  unparseable — never raises.
  """
  url = f"repos/{repo}/pulls/{number}/comments"
  jq = _api_jq_fields("id,user,body,path,line,created_at")
  cmd = ["gh", "api", url, "--jq", jq]

  try:
    proc = await asyncio.create_subprocess_exec(
      *cmd,
      cwd=None,
      env=os.environ,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
      start_new_session=True,
    )
    stdout_b, _stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
    stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
  except (FileNotFoundError, asyncio.TimeoutError, OSError):
    return pr_json

  if proc.returncode != 0:
    return pr_json

  stdout, _ = _redact(stdout or "")
  _truncated, stdout = _truncate(stdout, 100 * 1024)

  try:
    pr_data = json.loads(pr_json)
    comments = json.loads(stdout) if stdout.strip() else []
    pr_data["comments"] = comments
    return json.dumps(pr_data)
  except (json.JSONDecodeError, TypeError):
    return pr_json


def _redact(text: str) -> tuple[str, int]:
  """Redact credential patterns in text. Returns (redacted_text, total_count)."""
  total = 0
  for pattern, _name in _REDACT_PATTERNS:
    text, count = pattern.subn(_REDACT_REPLACEMENT, text)
    total += count
  return text, total


def _truncate(text: str, max_bytes: int) -> tuple[bool, str]:
  """Truncate text to max_bytes on a UTF-8 boundary.

  Returns ``(truncated, text)``. When truncated, appends a truncation notice.
  """
  encoded = text.encode("utf-8")
  if len(encoded) <= max_bytes:
    return False, text
  cut = encoded[:max_bytes].decode("utf-8", errors="ignore")
  return True, cut + _TRUNCATION_NOTICE


def _kill_process_group(pid: int) -> None:
  """Kill the process group led by ``pid``. Best-effort; logs on failure."""
  try:
    os.killpg(pid, signal.SIGKILL)
  except (ProcessLookupError, PermissionError, OSError) as exc:
    logger.warning("github_killpg_failed", pid=pid, error=str(exc))


def _map_error(stderr: str, operation: str, repo: str, number: int | None, tag: str) -> str:
  """Map gh stderr to a friendly, sanitized error message."""
  lower = stderr.lower()
  if (
    "not logged in" in lower
    or "authentication required" in lower
    or ("auth" in lower and "login" in lower)
  ):
    return "gh is not authenticated. Run 'gh auth login' first."
  if "rate limit" in lower:
    return "GitHub API rate limit exceeded. Wait and try again."
  not_found = (
    "not found" in lower or "could not resolve" in lower or bool(re.search(r"no \w+ found", lower))
  )
  if not_found:
    if operation == "repo_view":
      return f"Resource not found: {repo or '(current repo)'}"
    if operation == "release_view":
      return f"Resource not found: {tag}"
    if number is not None:
      return f"Resource not found: {number}"
    return f"Resource not found: {repo or '(current repo)'}"
  # Fall back to the (already truncated + redacted) stderr.
  return stderr.strip() or "GitHub command failed"


__all__ = ["github"]
