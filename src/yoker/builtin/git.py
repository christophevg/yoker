"""Git tool implementation for Yoker.

Provides the ``git`` async function for executing Git operations with
security guardrails.

Permission model (secure-by-default):

- ``allowed_commands`` — all commands the tool may execute (default:
  status, log, diff, branch, show, commit, push).
- ``auto_permission`` — subset that is auto-approved without asking
  (default: read-only operations only: status, log, diff, branch, show).

Operations in ``allowed_commands`` but not in ``auto_permission`` (e.g.
``commit``, ``push``) require interactive approval via the
``ctx.approval_handler`` (wired from ``UIHandler.confirm_approval`` in
interactive mode). In batch mode (no handler wired), they are blocked —
fail-safe.

To enable autonomous commits in a trusted workflow, add the operation
to ``auto_permission`` in ``yoker.toml``:

.. code-block:: toml

    [tools.git]
    auto_permission = ["status", "log", "diff", "branch", "show", "commit"]
"""

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Annotated, Any

from structlog import get_logger

from yoker.config import GitToolConfig
from yoker.tools.annotations import Path as PathArg
from yoker.tools.annotations import Text
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult, ValidationResult

logger = get_logger(__name__)

OPERATION_ARGS: dict[str, dict[str, dict[str, Any]]] = {
  "status": {
    "short": {"type": "boolean", "description": "Give output in short format"},
    "porcelain": {"type": "boolean", "description": "Machine-readable output"},
  },
  "log": {
    "oneline": {"type": "boolean", "description": "Each commit on single line"},
    "n": {
      "type": "integer",
      "description": "Limit number of commits",
      "minimum": 1,
      "maximum": 100,
    },
    "since": {"type": "string", "description": "Show commits since date/commit"},
    "until": {"type": "string", "description": "Show commits until date/commit"},
    "author": {"type": "string", "description": "Filter by author"},
    "format": {"type": "string", "description": "Pretty format string"},
  },
  "diff": {
    "cached": {"type": "boolean", "description": "Show staged changes"},
    "stat": {"type": "boolean", "description": "Show diffstat output"},
    "name_only": {"type": "boolean", "description": "Show only names of changed files"},
  },
  "branch": {
    "list": {"type": "boolean", "description": "List branches"},
    "all": {"type": "boolean", "description": "List all branches (remote and local)"},
    "remotes": {"type": "boolean", "description": "List remote branches"},
    "show_current": {
      "type": "boolean",
      "description": "Return just the current branch name (equivalent to --show-current). When true, all other args are ignored.",
    },
  },
  "pull": {},
  "tag": {
    "list": {
      "type": "boolean",
      "description": "Return all tags sorted by creatordate descending (default if neither list nor last is set)",
    },
    "last": {
      "type": "boolean",
      "description": "Return only the most recent tag (equivalent to git describe --tags --abbrev=0). Returns empty if no tags exist.",
    },
    "create": {
      "type": "boolean",
      "description": "Create a new annotated tag with the given name and message",
    },
    "name": {
      "type": "string",
      "description": "Tag name (required when create=true)",
      "max_length": 200,
    },
    "message": {
      "type": "string",
      "description": "Annotation message for the tag (required when create=true, supports multi-line)",
      "unsafe_content": True,
      "max_length": 2000,
    },
  },
  "show": {
    "format": {"type": "string", "description": "Pretty format string"},
    "stat": {"type": "boolean", "description": "Show diffstat output"},
  },
  "add": {
    "all": {"type": "boolean", "description": "Stage all changes in the working tree"},
    "update": {
      "type": "boolean",
      "description": "Stage only tracked files (no new files)",
    },
    "files": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Specific file paths to stage (relative to the repo path). When provided, 'all' and 'update' are ignored.",
    },
  },
  "commit": {
    "message": {
      "type": "string",
      "description": "Commit message (supports multi-line: subject, body, trailers)",
      "unsafe_content": True,
      "max_length": 2000,
    },
    "all": {"type": "boolean", "description": "Commit all changed files"},
    "amend": {"type": "boolean", "description": "Amend previous commit"},
  },
  "push": {
    "all": {"type": "boolean", "description": "Push all branches"},
    "tags": {"type": "boolean", "description": "Push tags"},
    "force": {"type": "boolean", "description": "Force push (dangerous)"},
  },
  "checkout": {
    "branch": {
      "type": "string",
      "description": "Branch name to checkout or create",
    },
    "create": {
      "type": "boolean",
      "description": "Create a new branch (equivalent to -b) and switch to it",
      "flag": "-b",
    },
    "startpoint": {
      "type": "string",
      "description": "Starting point for new branch (commit, tag, or branch name). Only used with create=true.",
    },
  },
  "rm": {
    "cached": {
      "type": "boolean",
      "description": "Untrack and remove from the index, but keep the file in the working tree",
    },
    "r": {
      "type": "boolean",
      "description": "Remove directories recursively",
    },
    "files": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Specific file paths to remove (relative to the repo path). Required.",
    },
  },
}

DANGEROUS_OPTIONS: frozenset[str] = frozenset(
  {
    "--upload-pack",
    "--receive-pack",
    "--exec",
    "--git-dir",
    "--work-tree",
    "-c",
    "--config",
  }
)

FORBIDDEN_CHARS: frozenset[str] = frozenset(
  {
    "\n",
    "\r",
    "\x00",
    "`",
    "$",
    "|",
    ";",
    "&",
  }
)

CREDENTIAL_PATTERN = re.compile(r"(https?://)[^:]+:[^@]*@")


async def git(
  operation: Annotated[
    str,
    Text(
      "Git operation to execute. One of: status, log, diff, branch, show, "
      "add, commit, push, checkout, rm, pull, tag."
    ),
  ],
  path: Annotated[
    str, PathArg("Path to the Git repository, or file for diff/show operations")
  ] = ".",
  ctx: ToolContext = None,  # type: ignore[assignment]
  args: Annotated[
    dict[str, Any] | None,
    Text(
      "Operation-specific arguments.\n"
      "\n"
      "status: {short: bool, porcelain: bool}\n"
      "log: {oneline: bool, n: int (1-100), since: str, until: str, author: str, format: str}\n"
      "diff: {cached: bool (staged changes), stat: bool (diffstat), name_only: bool}\n"
      "  - To diff a specific file, set the 'path' parameter to the file path, not an arg.\n"
      "branch: {list: bool, all: bool, remotes: bool, show_current: bool (current branch name only)}\n"
      "show: {format: str, stat: bool}\n"
      "  - To show a specific file, set the 'path' parameter to the file path.\n"
      "add: {all: bool (stage everything), update: bool (stage tracked only), files: [str] (specific files)}\n"
      "commit: {message: str (supports multi-line), all: bool, amend: bool}\n"
      "push: {all: bool, tags: bool, force: bool}\n"
      "checkout: {branch: str (required), create: bool (create new branch with -b), startpoint: str (base for new branch)}\n"
      "rm: {cached: bool (untrack without deleting), r: bool (recursive), files: [str] (required, specific file paths to remove)}\n"
      "pull: *(no args)* — sync current branch with remote upstream\n"
      "tag: {list: bool (all tags sorted desc), last: bool (most recent tag only), create: bool (create annotated tag), name: str (tag name, required for create), message: str (annotation message, required for create)}"
    ),
  ] = None,
) -> ToolResult:
  """Execute a Git operation on a repository.

  Read-only operations (status, log, diff, branch, show) are auto-approved.
  Staging operations (add, rm) are auto-approved. Write operations (commit,
  push, checkout) require interactive approval unless explicitly added to
  ``auto_permission`` in config.

  For diff and show, to scope to a specific file, pass the file path as the
  'path' parameter (not as an arg). Example: git(operation='diff',
  path='src/main.py') shows changes for that file only.
  """
  git_config = ctx.config
  if not isinstance(git_config, GitToolConfig):
    logger.warning("git_invalid_config_type", config_type=type(git_config).__name__)
    return ToolResult(success=False, error="Invalid configuration for git tool")
  allowed_commands = git_config.allowed_commands
  auto_permission = git_config.auto_permission

  if not operation:
    return ToolResult(success=False, error="Missing required parameter: operation")

  if not isinstance(operation, str):
    return ToolResult(success=False, error="Parameter 'operation' must be a string")

  if operation not in allowed_commands:
    allowed_list = ", ".join(allowed_commands)
    return ToolResult(
      success=False,
      error=f"Operation not allowed: {operation}. Allowed: {allowed_list}",
    )

  # Secure-by-default: operations not in auto_permission require approval.
  if operation not in auto_permission:
    approved, reason = await _check_approval(operation, ctx)
    if not approved:
      logger.info("git_permission_denied", operation=operation, reason=reason)
      return ToolResult(
        success=False, error=reason or f"Permission denied for operation: {operation}"
      )

  if not isinstance(path, str):
    return ToolResult(success=False, error="Parameter 'path' must be a string")

  validation = _validate_repository_path(path)
  if not validation.valid:
    logger.info("git_path_invalid", path=path, reason=validation.reason)
    return ToolResult(success=False, error=validation.reason)

  try:
    resolved_path = Path(path).resolve()
  except (OSError, ValueError):
    return ToolResult(success=False, error="Invalid path")

  file_arg: str | None = None
  work_dir: Path

  if resolved_path.is_file():
    file_operations = {"diff", "show"}
    if operation in file_operations:
      repo_root = _find_git_root(resolved_path)
      if repo_root is None:
        return ToolResult(success=False, error="Not a Git repository")
      work_dir = repo_root
      file_arg = str(resolved_path.relative_to(repo_root))
    else:
      return ToolResult(
        success=False,
        error=f"Operation '{operation}' requires a directory, not a file",
      )
  else:
    work_dir = resolved_path

  args = args or {}
  if not isinstance(args, dict):
    return ToolResult(success=False, error="Parameter 'args' must be an object")

  # git rm requires explicit file paths.
  if operation == "rm" and "files" not in args:
    return ToolResult(success=False, error="Argument 'files' is required for rm operation")

  # Extract file pathspecs for 'add' and 'rm' — they are appended after
  # '--' on the command line, not as flags. This allows staging/removing
  # individual files.
  file_pathspecs: list[str] = []
  if operation in ("add", "rm") and "files" in args:
    raw_files = args["files"]
    if not isinstance(raw_files, list):
      return ToolResult(success=False, error="Argument 'files' must be an array")
    if not raw_files:
      return ToolResult(success=False, error="Argument 'files' must not be empty")
    for f in raw_files:
      if not isinstance(f, str):
        return ToolResult(success=False, error="Each entry in 'files' must be a string")
      # Reuse the string sanitization to block injection chars.
      file_schema = OPERATION_ARGS[operation]["files"]["items"]
      try:
        sanitized = _sanitize_arg("files", f, file_schema)
      except ValueError as e:
        return ToolResult(success=False, error=str(e))
      file_pathspecs.append(sanitized)
    # Remove 'files' from args so _build_command doesn't try to process it.
    args = {k: v for k, v in args.items() if k != "files"}

  # Extract branch and startpoint for 'checkout' — they are positional
  # args appended after '--' on the command line.
  checkout_pathspecs: list[str] = []
  if operation == "checkout":
    if "branch" not in args or not args["branch"]:
      return ToolResult(success=False, error="Argument 'branch' is required for checkout operation")
    branch_schema = OPERATION_ARGS["checkout"]["branch"]
    try:
      sanitized_branch = _sanitize_arg("branch", args["branch"], branch_schema)
    except ValueError as e:
      return ToolResult(success=False, error=str(e))
    checkout_pathspecs.append(sanitized_branch)
    # Remove 'branch' from args so _build_command doesn't process it.
    args = {k: v for k, v in args.items() if k != "branch"}
    if "startpoint" in args and args["startpoint"]:
      startpoint_schema = OPERATION_ARGS["checkout"]["startpoint"]
      try:
        sanitized_sp = _sanitize_arg("startpoint", args["startpoint"], startpoint_schema)
      except ValueError as e:
        return ToolResult(success=False, error=str(e))
      checkout_pathspecs.append(sanitized_sp)
      args = {k: v for k, v in args.items() if k != "startpoint"}

  # branch --show-current: short-circuit to just the branch name.
  if operation == "branch" and args.get("show_current"):
    cmd = ["git", "branch", "--show-current"]
  # tag: needs special command building (list vs last vs create vs default).
  elif operation == "tag":
    try:
      cmd = _build_tag_command(args)
    except ValueError as e:
      return ToolResult(success=False, error=str(e))
  # pull: no args, just git pull.
  elif operation == "pull":
    cmd = ["git", "pull"]
  else:
    try:
      cmd = _build_command(operation, args, allowed_commands)
    except ValueError as e:
      return ToolResult(success=False, error=str(e))

  if file_arg is not None:
    cmd.extend(["--", file_arg])
  elif file_pathspecs:
    cmd.extend(["--"] + file_pathspecs)
  elif checkout_pathspecs:
    # Branch names are refs, not pathspecs — don't use '--' separator.
    # Flag injection is already prevented by _sanitize_arg (rejects leading '-').
    cmd.extend(checkout_pathspecs)

  logger.info("git_executing", operation=operation, path=str(work_dir))

  try:
    returncode, stdout, stderr = await _execute_command(cmd, work_dir)

    if returncode == 0:
      sanitized_output = _sanitize_output(stdout)
      logger.info(
        "git_success",
        operation=operation,
        path=str(work_dir),
        output_length=len(sanitized_output),
      )
      return ToolResult(success=True, result=sanitized_output.strip() or "(no output)")
    else:
      # tag last: git describe fails when no tags exist — return empty, not error.
      if operation == "tag" and args.get("last"):
        logger.info("git_tag_last_none", path=str(work_dir))
        return ToolResult(success=True, result="")
      sanitized_stderr = _sanitize_output(stderr)
      logger.warning(
        "git_failed",
        operation=operation,
        path=str(work_dir),
        returncode=returncode,
        stderr=sanitized_stderr,
      )
      return ToolResult(
        success=False,
        error=sanitized_stderr.strip() or f"Git command failed with code {returncode}",
      )

  except subprocess.TimeoutExpired:
    logger.warning("git_timeout", operation=operation, path=str(work_dir))
    return ToolResult(success=False, error="Git command timeout exceeded")
  except FileNotFoundError:
    logger.error("git_not_found", operation=operation)
    return ToolResult(success=False, error="Git is not installed or not found in PATH")
  except Exception as e:
    logger.error("git_error", operation=operation, path=str(work_dir), error=str(e))
    return ToolResult(success=False, error=f"Error executing Git command: {e}")


def _find_git_root(path: Path) -> Path | None:
  """Walk up from *path* to find the nearest ancestor containing ``.git``."""
  current = path.parent if path.is_file() else path
  while True:
    if (current / ".git").exists():
      return current
    if current.parent == current:
      return None  # Reached filesystem root
    current = current.parent


def _validate_repository_path(path: str) -> ValidationResult:
  """Validate that the path is within an allowed Git repository."""
  try:
    resolved = Path(path).resolve()
  except (OSError, ValueError):
    return ValidationResult(valid=False, reason="Invalid path")

  if not resolved.exists():
    return ValidationResult(valid=False, reason="Path does not exist")

  if _find_git_root(resolved) is None:
    return ValidationResult(valid=False, reason="Not a Git repository")

  return ValidationResult(valid=True)


async def _check_approval(operation: str, ctx: ToolContext) -> tuple[bool, str | None]:
  """Check if the operation is approved.

  If an approval handler is available (interactive mode), use it to
  prompt the user with a preview of what the operation will do.
  If no handler is available (batch mode), fail-safe to denial.
  The handler is called with ``kind="git"`` so the UI renders
  appropriate language (not "Protected file" / "write to").
  """
  handler = ctx.approval_handler
  if handler is None:
    return False, (
      f"Operation '{operation}' requires approval but no interactive handler "
      "is available. Add it to auto_permission in yoker.toml to allow "
      "without confirmation."
    )

  context_label = f"git {operation}"

  # Build a preview for the approval prompt.
  if operation == "commit":
    preview = await _staged_diff_preview()
  elif operation == "push":
    preview = await _push_preview()
  elif operation == "checkout":
    preview = await _checkout_preview()
  else:
    preview = f"git {operation}"

  try:
    approved = await handler(context_label, preview, "git")
  except Exception as e:
    logger.warning("git_approval_error", operation=operation, error=str(e))
    return False, f"Approval handler error for operation '{operation}': {e}"

  if not approved:
    return False, f"User denied git {operation}."
  return True, None


async def _staged_diff_preview() -> str:
  """Build a preview of staged changes for the approval prompt."""
  try:
    _, stdout, _ = await _execute_command(["git", "diff", "--no-color", "--cached"], Path.cwd())
    if stdout.strip():
      return stdout[:4000]
    # No staged changes — show working tree status instead.
    _, stdout, _ = await _execute_command(["git", "status", "--short"], Path.cwd())
    return f"(no staged changes)\n\nWorking tree:\n{stdout[:2000]}"
  except Exception:
    return "git commit"


async def _push_preview() -> str:
  """Build a preview of what would be pushed."""
  try:
    _, stdout, _ = await _execute_command(
      ["git", "log", "--no-color", "--oneline", "-5", "@{push}.."], Path.cwd()
    )
    if stdout.strip():
      return f"Commits to be pushed:\n{stdout}"
    return "git push (no unpushed commits or no upstream configured)"
  except Exception:
    # @{push} may not be available (no upstream) — fall back to unpushed commits
    try:
      _, stdout, _ = await _execute_command(
        ["git", "log", "--no-color", "--oneline", "-5", "origin/HEAD.."], Path.cwd()
      )
      return f"Commits to be pushed:\n{stdout}" if stdout.strip() else "git push"
    except Exception:
      return "git push"


async def _checkout_preview() -> str:
  """Build a preview of the working tree state for the approval prompt."""
  try:
    _, stdout, _ = await _execute_command(["git", "status", "--short"], Path.cwd())
    if stdout.strip():
      return f"Working tree (uncommitted changes may be carried over):\n{stdout[:2000]}"
    return "git checkout (clean working tree)"
  except Exception:
    return "git checkout"


def _build_command(
  operation: str,
  args: dict[str, Any],
  allowed_commands: tuple[str, ...],
) -> list[str]:
  """Build a Git command from operation and arguments."""
  if operation not in allowed_commands:
    raise ValueError(f"Operation not allowed: {operation}")

  cmd: list[str] = ["git", operation]

  color_operations = {"diff", "log", "show"}
  if operation in color_operations:
    cmd.append("--no-color")

  allowed_args = OPERATION_ARGS.get(operation, {})

  for key, value in args.items():
    if key not in allowed_args:
      raise ValueError(f"Argument not allowed for {operation}: {key}")

    sanitized = _sanitize_arg(key, value, allowed_args[key])

    if isinstance(value, bool):
      if value:
        # Use custom flag if specified in schema (e.g. create -> -b)
        custom_flag = allowed_args[key].get("flag")
        if custom_flag:
          cmd.append(custom_flag)
        elif len(key) == 1:
          cmd.append(f"-{key}")
        else:
          cmd.append(f"--{key.replace('_', '-')}")
    elif value is not None:
      if len(key) == 1:
        cmd.extend([f"-{key}", sanitized])
      else:
        cmd.append(f"--{key.replace('_', '-')}={sanitized}")

  return cmd


def _build_tag_command(args: dict[str, Any]) -> list[str]:
  """Build a git tag command.

  - ``create: true`` → ``git tag -a <name> -m <message>`` (annotated tag)
  - ``last: true`` → ``git describe --tags --abbrev=0`` (most recent tag)
  - ``list: true`` or no args → ``git tag --sort=-creatordate`` (all tags, newest first)

  Returns the command list. Caller handles the non-zero exit for ``last``
  when no tags exist.
  """
  if args.get("create", False):
    name = args.get("name", "")
    message = args.get("message", "")
    if not name:
      raise ValueError("Argument 'name' is required for tag create")
    if not message:
      raise ValueError("Argument 'message' is required for tag create")
    return ["git", "tag", "-a", name, "-m", message]
  if args.get("last", False):
    return ["git", "describe", "--tags", "--abbrev=0"]
  # Default to list when neither is set, or when list is explicitly true.
  return ["git", "tag", "--sort=-creatordate"]


def _sanitize_arg(
  key: str,
  value: Any,
  schema: dict[str, Any],
) -> str:
  """Sanitize an argument value against its schema."""
  expected_type = schema.get("type")
  if expected_type == "boolean":
    if not isinstance(value, bool):
      raise ValueError(f"Argument {key} must be boolean")
  elif expected_type == "integer":
    if not isinstance(value, int):
      raise ValueError(f"Argument {key} must be integer")
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if minimum is not None and value < minimum:
      raise ValueError(f"Argument {key} must be >= {minimum}")
    if maximum is not None and value > maximum:
      raise ValueError(f"Argument {key} must be <= {maximum}")
  elif expected_type == "string":
    if not isinstance(value, str):
      raise ValueError(f"Argument {key} must be string")
    if len(value) > 1000:
      max_length = schema.get("max_length", 1000)
      if len(value) > max_length:
        raise ValueError(f"Argument {key} exceeds length limit ({max_length})")
    # When unsafe_content is set (e.g. commit message), the content is
    # free-form prose -- only the NUL byte is rejected. The shell injection
    # chars in FORBIDDEN_CHARS are safe here because commands are executed
    # via subprocess with a list (no shell). When unsafe_content is not
    # set, all FORBIDDEN_CHARS are rejected as before.
    if schema.get("unsafe_content", False):
      if "\x00" in value:
        raise ValueError(f"Argument {key} contains NUL byte")
    else:
      for char in FORBIDDEN_CHARS:
        if char in value:
          raise ValueError(f"Argument {key} contains forbidden character")

    if value in DANGEROUS_OPTIONS:
      raise ValueError(f"Argument {key} contains dangerous option: {value}")

    lower_val = value.lower().replace("_", "-")
    if lower_val in DANGEROUS_OPTIONS or f"--{lower_val}" in DANGEROUS_OPTIONS:
      raise ValueError(f"Argument {key} contains dangerous option variant")

    if value.startswith("-"):
      raise ValueError(f"Argument {key} starts with dash, potential flag injection")

  return str(value)


async def _execute_command(
  cmd: list[str],
  cwd: Path,
  timeout_seconds: int = 30,
) -> tuple[int, str, str]:
  """Execute a Git command via async subprocess."""
  try:
    proc = await asyncio.create_subprocess_exec(
      *cmd,
      cwd=str(cwd),
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
    )
  except FileNotFoundError:
    raise
  try:
    stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
  except asyncio.TimeoutError:
    proc.kill()
    await proc.wait()
    raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_seconds) from None
  stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
  stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
  return proc.returncode or 0, stdout, stderr


def _sanitize_output(output: str) -> str:
  """Sanitize output to redact credentials."""
  return CREDENTIAL_PATTERN.sub(r"\1<redacted>@", output)


__all__ = ["git", "OPERATION_ARGS"]
