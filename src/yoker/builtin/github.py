"""GitHub tool implementation for Yoker.

Wraps the ``gh`` CLI for a fixed set of read-only GitHub operations. The
operation enum is the security boundary: the agent can only invoke the nine
hardcoded ``gh`` subcommands listed in ``_OPERATION_DISPATCH`` — never
``gh api``, ``gh extension``, ``gh auth token``, or any write/destructive
subcommand.

Security model
--------------
- **Operation enum + allowlist**: ``operation`` must be in the fixed enum
  AND in ``GitHubToolConfig.allowed_operations`` (default-allow the full
  read-only MVP set). This is the subcommand-blocking gate.
- **No shell**: ``subprocess.Popen`` with list args, ``shell=False``.
- **Argument-injection defenses**: tight regexes for ``repo``/``tag``/``label``,
  enum check for ``state``, int clamps for ``number``/``limit``, leading-dash
  rejection, ``FORBIDDEN_CHARS`` rejection, ``--`` separator before any
  user-supplied positional.
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

import os
import re
import signal
import subprocess
import sys
from typing import Annotated

from structlog import get_logger

from yoker.config import GitHubToolConfig
from yoker.tools.annotations import Text
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
    "workflow_list",
    "workflow_view",
    "release_list",
    "release_view",
  }
)

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
  "workflow_list": (
    ["run", "list"],
    "databaseId,name,status,conclusion,headBranch,createdAt",
    None,
  ),
  "workflow_view": (["run", "view"], "databaseId,name,status,conclusion,jobs", "number"),
  "release_list": (
    ["release", "list"],
    "tagName,name,isDraft,isPrerelease,createdAt",
    None,
  ),
  "release_view": (["release", "view"], "tagName,name,body,assets", "tag"),
}

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
_MAX_NUMBER = 2**31 - 1

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


async def github(
  operation: Annotated[str, Text("GitHub operation from the allowlist")],
  ctx: ToolContext,
  repo: Annotated[str, Text("Repository as owner/name")] = "",
  number: int | None = None,
  tag: Annotated[str, Text("Release tag (for release_view)")] = "",
  limit: int = 30,
  state: str = "open",
  label: Annotated[str, Text("Filter by label (for issue_list)")] = "",
  timeout_ms: int | None = None,
) -> ToolResult:
  """Perform a read-only GitHub operation via the ``gh`` CLI.

  Operations are restricted to a fixed enum (the security boundary) and
  further gated by ``GitHubToolConfig.allowed_operations``. All commands
  run via ``subprocess`` with list args (no shell); timeout is enforced by
  killing the whole process group.
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

  logger.info(
    "github_executing",
    operation=operation,
    repo=repo or "(auto)",
    number=number,
    tag=tag,
    limit=effective_limit,
  )

  # --- Subprocess execution (Popen so we can kill the process group on timeout) ---
  try:
    proc = subprocess.Popen(
      cmd,
      cwd=None,
      env=os.environ,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True,
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
    stdout, stderr = proc.communicate(timeout=effective_timeout_ms / 1000)
  except subprocess.TimeoutExpired:
    _kill_process_group(proc.pid)
    try:
      stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
      stdout, stderr = (stdout or ""), (stderr or "")
    logger.warning("github_timeout", operation=operation, timeout_ms=effective_timeout_ms)
    return ToolResult(
      success=False,
      error=f"GitHub operation timed out after {effective_timeout_ms}ms",
    )

  # --- Redact secrets BEFORE truncation (so a secret just past the cut is not kept) ---
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

  # --- Per-stream truncation on a UTF-8 boundary ---
  max_output_bytes = gh_config.max_output_kb * 1024
  stdout_truncated, stdout_out = _truncate(stdout, max_output_bytes)
  stderr_truncated, stderr_out = _truncate(stderr, max_output_bytes)
  truncated = stdout_truncated or stderr_truncated

  returncode = proc.returncode
  gh_subcommand = f"gh {' '.join(_OPERATION_DISPATCH[operation][0])} --json"

  if returncode == 0:
    content_metadata = {
      "operation": "github",
      "path": repo or "default",
      "content_type": "application/json",
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
        "truncated": truncated,
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
    truncated=truncated,
  )
  return ToolResult(success=False, error=friendly)


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
  """
  subcmd, fields, required = _OPERATION_DISPATCH[operation]
  cmd: list[str] = ["gh", *subcmd]

  if repo:
    cmd.extend(["--repo", repo])

  if operation in _STATE_OPS:
    cmd.extend(["--state", state])
  if operation in _LABEL_OPS and label:
    cmd.extend(["--label", label])
  if operation in _LIMIT_OPS:
    cmd.extend(["--limit", str(limit)])

  cmd.extend(["--json", fields])

  if required == "number":
    cmd.extend(["--", str(number)])
  elif required == "tag":
    cmd.extend(["--", tag])

  return cmd


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
