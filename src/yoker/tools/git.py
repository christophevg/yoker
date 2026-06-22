"""Git tool implementation for Yoker.

Provides the ``git`` async function for executing Git operations with
security guardrails.
"""

import re
import subprocess
from pathlib import Path
from typing import Annotated, TYPE_CHECKING, Any

from structlog import get_logger

from yoker.annotations import Path as PathArg
from yoker.tools.base import ToolResult, ValidationResult
from yoker.tools.context import ToolContext

if TYPE_CHECKING:
  from yoker.config import GitToolConfig

log = get_logger(__name__)

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
  },
  "show": {
    "format": {"type": "string", "description": "Pretty format string"},
    "stat": {"type": "boolean", "description": "Show diffstat output"},
  },
  "commit": {
    "message": {"type": "string", "description": "Commit message"},
    "all": {"type": "boolean", "description": "Commit all changed files"},
    "amend": {"type": "boolean", "description": "Amend previous commit"},
  },
  "push": {
    "all": {"type": "boolean", "description": "Push all branches"},
    "tags": {"type": "boolean", "description": "Push tags"},
    "force": {"type": "boolean", "description": "Force push (dangerous)"},
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
  operation: str,
  path: Annotated[
    str, PathArg("Path to the Git repository, or file for diff/show operations")
  ] = ".",
  args: dict[str, Any] | None = None,
  ctx: ToolContext | None = None,
) -> ToolResult:
  """Execute a Git operation on a repository."""
  # Get config values
  if ctx is not None and ctx.config is not None:
    git_config: "GitToolConfig" = ctx.config
    allowed_commands = git_config.allowed_commands
    requires_permission = git_config.requires_permission
  else:
    # Fallback defaults
    from yoker.config import GitToolConfig
    default_config = GitToolConfig()
    allowed_commands = default_config.allowed_commands
    requires_permission = default_config.requires_permission

  # Permission handlers from context backends (if available)
  permission_handlers = ctx.backends.get("permission_handlers") if ctx else None

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

  allowed, reason = _check_permission(operation, allowed_commands, requires_permission, permission_handlers)
  if not allowed:
    log.info("git_permission_denied", operation=operation, reason=reason)
    return ToolResult(
      success=False, error=reason or f"Permission denied for operation: {operation}"
    )

  if not isinstance(path, str):
    return ToolResult(success=False, error="Parameter 'path' must be a string")

  validation = _validate_repository_path(path)
  if not validation.valid:
    log.info("git_path_invalid", path=path, reason=validation.reason)
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
      work_dir = resolved_path.parent
      file_arg = resolved_path.name
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

  try:
    cmd = _build_command(operation, args, allowed_commands)
  except ValueError as e:
    return ToolResult(success=False, error=str(e))

  if file_arg is not None:
    cmd.extend(["--", file_arg])

  log.info("git_executing", operation=operation, path=str(work_dir))

  try:
    returncode, stdout, stderr = _execute_command(cmd, work_dir)

    if returncode == 0:
      sanitized_output = _sanitize_output(stdout)
      log.info(
        "git_success",
        operation=operation,
        path=str(work_dir),
        output_length=len(sanitized_output),
      )
      return ToolResult(success=True, result=sanitized_output.strip() or "(no output)")
    else:
      sanitized_stderr = _sanitize_output(stderr)
      log.warning(
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
    log.warning("git_timeout", operation=operation, path=str(work_dir))
    return ToolResult(success=False, error="Git command timeout exceeded")
  except FileNotFoundError:
    log.error("git_not_found", operation=operation)
    return ToolResult(success=False, error="Git is not installed or not found in PATH")
  except Exception as e:
    log.error("git_error", operation=operation, path=str(work_dir), error=str(e))
    return ToolResult(success=False, error=f"Error executing Git command: {e}")


def _validate_repository_path(path: str) -> ValidationResult:
  """Validate that the path is within an allowed Git repository."""
  try:
    resolved = Path(path).resolve()
  except (OSError, ValueError):
    return ValidationResult(valid=False, reason="Invalid path")

  if not resolved.exists():
    return ValidationResult(valid=False, reason="Path does not exist")

  check_dir = resolved.parent if resolved.is_file() else resolved

  if not (check_dir / ".git").exists():
    return ValidationResult(valid=False, reason="Not a Git repository")

  return ValidationResult(valid=True)


def _check_permission(
  operation: str,
  allowed_commands: tuple[str, ...],
  requires_permission: tuple[str, ...],
  permission_handlers: dict[str, Any] | None,
) -> tuple[bool, str | None]:
  """Check if operation requires and has permission."""
  if operation not in requires_permission:
    return True, None

  handler_key = f"git_{operation}"
  handler = permission_handlers.get(handler_key) if permission_handlers else None

  if handler is None:
    return False, f"Operation {operation} requires permission but no handler configured"

  if handler.mode == "allow":
    return True, None
  elif handler.mode == "block":
    return False, handler.message or f"Operation {operation} is blocked"
  elif handler.mode == "ask_user":
    return False, f"Operation {operation} requires user confirmation"

  return False, f"Unknown permission mode: {handler.mode}"


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
        if len(key) == 1:
          cmd.append(f"-{key}")
        else:
          cmd.append(f"--{key}")
    elif value is not None:
      if len(key) == 1:
        cmd.extend([f"-{key}", sanitized])
      else:
        cmd.append(f"--{key}={sanitized}")

  return cmd


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
      raise ValueError(f"Argument {key} exceeds length limit")
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


def _execute_command(
  cmd: list[str],
  cwd: Path,
  timeout_seconds: int = 30,
) -> tuple[int, str, str]:
  """Execute a Git command via subprocess."""
  result = subprocess.run(
    cmd,
    cwd=str(cwd),
    capture_output=True,
    text=True,
    timeout=timeout_seconds,
  )
  return result.returncode, result.stdout, result.stderr


def _sanitize_output(output: str) -> str:
  """Sanitize output to redact credentials."""
  return CREDENTIAL_PATTERN.sub(r"\1<redacted>@", output)


__all__ = ["git", "OPERATION_ARGS"]
