"""Git tool implementation for Yoker.

Provides the GitTool for executing Git operations with security guardrails
including operation allowlisting, command sanitization, and permission handlers.
"""

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.config.schema import GitToolConfig, HandlerConfig
from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult, ValidationResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)

# Operation argument definitions with validation schemas
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

# Dangerous options that should be blocked
DANGEROUS_OPTIONS: frozenset[str] = frozenset({
  "--upload-pack",
  "--receive-pack",
  "--exec",
  "--git-dir",
  "--work-tree",
  "-c",
  "--config",
})

# Forbidden characters in argument values
FORBIDDEN_CHARS: frozenset[str] = frozenset({
  "\n",
  "\r",
  "\x00",
  "`",
  "$",
  "|",
  ";",
  "&",
})

# Credential pattern for URL redaction (matches user:pass@host)
# Note: [^@]* allows empty passwords (user:@host)
CREDENTIAL_PATTERN = re.compile(r"(https?://)[^:]+:[^@]*@")


class GitTool(Tool):
  """Tool for executing Git operations with security guardrails.

  Provides controlled access to Git commands through an operation allowlist.
  Destructive operations (commit, push) require explicit permission handling.
  All commands are executed via subprocess with list arguments to prevent
  shell injection.

  Attributes:
    _config: GitToolConfig with allowed commands and permission requirements.
    _permission_handlers: Dict of operation name to HandlerConfig.
  """

  def __init__(
    self,
    config: GitToolConfig,
    guardrail: "Guardrail | None" = None,
    permission_handlers: dict[str, HandlerConfig] | None = None,
  ) -> None:
    """Initialize GitTool with configuration and optional guardrail.

    Args:
      config: GitToolConfig specifying allowed operations.
      guardrail: Optional guardrail for repository path validation.
      permission_handlers: Optional permission handlers for destructive ops.
    """
    super().__init__(guardrail=guardrail)
    self._config = config
    self._permission_handlers = permission_handlers or {}

  @property
  def name(self) -> str:
    return "git"

  @property
  def description(self) -> str:
    return """Execute Git operations on a repository.

Supported operations depend on configuration. Default allows:
- status: Show working tree status
- log: Show commit logs
- diff: Show changes (can target specific file with path parameter)
- branch: List branches
- show: Show various types of objects

Destructive operations (commit, push) require explicit permission.

For diff and show, the path parameter can be a file to diff/show that file.
"""

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the git tool.

    Returns:
      Dict with 'type': 'function' and function metadata.
    """
    allowed_ops = list(self._get_allowed_operations())
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "operation": {
              "type": "string",
              "description": "Git operation to perform",
              "enum": allowed_ops,
            },
            "path": {
              "type": "string",
              "description": "Path to the Git repository, or file for diff/show operations (defaults to current directory)",
            },
            "args": {
              "type": "object",
              "description": "Operation-specific arguments",
              "additionalProperties": True,
            },
          },
          "required": ["operation"],
        },
      },
    }

  def _get_allowed_operations(self) -> tuple[str, ...]:
    """Get the list of allowed operations from config."""
    return self._config.allowed_commands

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute a Git operation.

    Steps:
      1. Extract and validate operation parameter.
      2. Validate repository path via guardrail.
      3. Check permission for destructive operations.
      4. Build and sanitize command.
      5. Execute command via subprocess.
      6. Format and return result.

    Args:
      **kwargs: Must contain 'operation' key, optional 'path' and 'args'.

    Returns:
      ToolResult with command output or error message.
    """
    # Extract operation
    operation = kwargs.get("operation")
    if not operation:
      return ToolResult(
        success=False,
        result="",
        error="Missing required parameter: operation",
      )

    if not isinstance(operation, str):
      return ToolResult(
        success=False,
        result="",
        error="Parameter 'operation' must be a string",
      )

    # Check operation is allowed
    if operation not in self._config.allowed_commands:
      allowed_list = ", ".join(self._config.allowed_commands)
      return ToolResult(
        success=False,
        result="",
        error=f"Operation not allowed: {operation}. Allowed: {allowed_list}",
      )

    # Check permission for destructive operations
    allowed, reason = self._check_permission(operation)
    if not allowed:
      log.info("git_permission_denied", operation=operation, reason=reason)
      return ToolResult(
        success=False,
        result="",
        error=reason or f"Permission denied for operation: {operation}",
      )

    # Extract and validate path
    path = kwargs.get("path", ".")
    if not isinstance(path, str):
      return ToolResult(
        success=False,
        result="",
        error="Parameter 'path' must be a string",
      )

    # Validate repository path via guardrail
    validation = self._validate_repository_path(path)
    if not validation.valid:
      log.info("git_path_invalid", path=path, reason=validation.reason)
      return ToolResult(
        success=False,
        result="",
        error=validation.reason,
      )

    # Resolve path and determine if it's a file or directory
    try:
      resolved_path = Path(path).resolve()
    except (OSError, ValueError):
      return ToolResult(
        success=False,
        result="",
        error="Invalid path",
      )

    # Handle path that could be file or directory
    # For operations like diff, path can be a file
    # For operations like status, log, path must be a directory
    file_arg: str | None = None
    work_dir: Path

    if resolved_path.is_file():
      # Path is a file - operations that support file paths
      file_operations = {"diff", "show"}
      if operation in file_operations:
        work_dir = resolved_path.parent
        file_arg = resolved_path.name
      else:
        return ToolResult(
          success=False,
          result="",
          error=f"Operation '{operation}' requires a directory, not a file",
        )
    else:
      # Path is a directory
      work_dir = resolved_path

    # Extract operation arguments
    args = kwargs.get("args", {})
    if not isinstance(args, dict):
      return ToolResult(
        success=False,
        result="",
        error="Parameter 'args' must be an object",
      )

    # Build command with sanitization
    try:
      cmd = self._build_command(operation, args)
    except ValueError as e:
      return ToolResult(
        success=False,
        result="",
        error=str(e),
      )

    # Add file argument if path was a file
    if file_arg is not None:
      cmd.extend(["--", file_arg])

    # Execute command
    log.info("git_executing", operation=operation, path=str(work_dir))

    try:
      returncode, stdout, stderr = self._execute_command(
        cmd,
        work_dir,
        timeout_seconds=30,
      )

      if returncode == 0:
        # Sanitize output to redact credentials
        sanitized_output = self._sanitize_output(stdout)
        log.info(
          "git_success",
          operation=operation,
          path=str(work_dir),
          output_length=len(sanitized_output),
        )
        return ToolResult(
          success=True,
          result=sanitized_output.strip() or "(no output)",
        )
      else:
        # Sanitize stderr too
        sanitized_stderr = self._sanitize_output(stderr)
        log.warning(
          "git_failed",
          operation=operation,
          path=str(work_dir),
          returncode=returncode,
          stderr=sanitized_stderr,
        )
        return ToolResult(
          success=False,
          result="",
          error=sanitized_stderr.strip() or f"Git command failed with code {returncode}",
        )

    except subprocess.TimeoutExpired:
      log.warning("git_timeout", operation=operation, path=str(work_dir))
      return ToolResult(
        success=False,
        result="",
        error="Git command timeout exceeded",
      )
    except FileNotFoundError:
      log.error("git_not_found", operation=operation)
      return ToolResult(
        success=False,
        result="",
        error="Git is not installed or not found in PATH",
      )
    except Exception as e:
      log.error("git_error", operation=operation, path=str(work_dir), error=str(e))
      return ToolResult(
        success=False,
        result="",
        error=f"Error executing Git command: {e}",
      )

  def _validate_repository_path(self, path: str) -> ValidationResult:
    """Validate that the path is within an allowed Git repository.

    Path can be a file or directory. For files, the parent directory is checked.

    Args:
      path: Path to validate (file or directory).

    Returns:
      ValidationResult indicating if path is valid.
    """
    # Use guardrail if available
    if self._guardrail is not None:
      return self._guardrail.validate(self.name, {"path": path})

    # Basic validation without guardrail
    try:
      resolved = Path(path).resolve()
    except (OSError, ValueError):
      return ValidationResult(valid=False, reason="Invalid path")

    # Check if path exists
    if not resolved.exists():
      return ValidationResult(valid=False, reason="Path does not exist")

    # Determine the directory to check for .git
    if resolved.is_file():
      check_dir = resolved.parent
    else:
      check_dir = resolved

    # Check if directory is within a Git repository
    if not (check_dir / ".git").exists():
      return ValidationResult(valid=False, reason="Not a Git repository")

    return ValidationResult(valid=True)

  def _check_permission(self, operation: str) -> tuple[bool, str | None]:
    """Check if operation requires and has permission.

    Args:
      operation: Git operation name.

    Returns:
      Tuple of (allowed, reason_if_blocked).
    """
    if operation not in self._config.requires_permission:
      return True, None

    # Check permission handlers
    handler_key = f"git_{operation}"
    handler = self._permission_handlers.get(handler_key)

    if handler is None:
      # Default: block destructive operations without explicit handler
      return False, f"Operation {operation} requires permission but no handler configured"

    if handler.mode == "allow":
      return True, None
    elif handler.mode == "block":
      return False, handler.message or f"Operation {operation} is blocked"
    elif handler.mode == "ask_user":
      # In non-interactive mode, treat as block
      return False, f"Operation {operation} requires user confirmation"

    return False, f"Unknown permission mode: {handler.mode}"

  def _build_command(
    self,
    operation: str,
    args: dict[str, Any],
  ) -> list[str]:
    """Build a Git command from operation and arguments.

    Uses allowlist validation to prevent arbitrary command execution.
    All arguments are validated against operation schema.

    Args:
      operation: Git operation name (must be in allowed_operations).
      args: Operation-specific arguments.

    Returns:
      List of command parts for subprocess (no shell interpolation).

    Raises:
      ValueError: If operation or arguments are not allowed.
    """
    if operation not in self._config.allowed_commands:
      raise ValueError(f"Operation not allowed: {operation}")

    # Start with git command
    cmd: list[str] = ["git", operation]

    # Get allowed arguments for this operation
    allowed_args = OPERATION_ARGS.get(operation, {})

    # Add validated arguments
    for key, value in args.items():
      if key not in allowed_args:
        raise ValueError(f"Argument not allowed for {operation}: {key}")

      # Validate and sanitize value
      sanitized = self._sanitize_arg(key, value, allowed_args[key])

      # Add argument to command
      # Single-letter options use single dash (e.g., -n), others use double dash
      if isinstance(value, bool):
        if value:
          if len(key) == 1:
            cmd.append(f"-{key}")
          else:
            cmd.append(f"--{key}")
      elif value is not None:
        if len(key) == 1:
          # Single-letter options: use space (e.g., -n 5)
          cmd.extend([f"-{key}", sanitized])
        else:
          # Multi-letter options: use equals (e.g., --format=%s)
          # This prevents git from interpreting the value as a revision/path
          cmd.append(f"--{key}={sanitized}")

    return cmd

  def _sanitize_arg(
    self,
    key: str,
    value: Any,
    schema: dict[str, Any],
  ) -> str:
    """Sanitize an argument value against its schema.

    Prevents injection through argument values.

    Args:
      key: Argument name.
      value: Argument value.
      schema: Expected type and constraints.

    Returns:
      Sanitized string value.

    Raises:
      ValueError: If value fails validation.
    """
    # Type validation
    expected_type = schema.get("type")
    if expected_type == "boolean":
      if not isinstance(value, bool):
        raise ValueError(f"Argument {key} must be boolean")
    elif expected_type == "integer":
      if not isinstance(value, int):
        raise ValueError(f"Argument {key} must be integer")
      # Range validation
      minimum = schema.get("minimum")
      maximum = schema.get("maximum")
      if minimum is not None and value < minimum:
        raise ValueError(f"Argument {key} must be >= {minimum}")
      if maximum is not None and value > maximum:
        raise ValueError(f"Argument {key} must be <= {maximum}")
    elif expected_type == "string":
      if not isinstance(value, str):
        raise ValueError(f"Argument {key} must be string")
      # Length limits
      if len(value) > 1000:
        raise ValueError(f"Argument {key} exceeds length limit")
      # Forbidden characters that could cause injection
      for char in FORBIDDEN_CHARS:
        if char in value:
          raise ValueError(f"Argument {key} contains forbidden character")

      # Check for dangerous options (before dash check for better error messages)
      if value in DANGEROUS_OPTIONS:
        raise ValueError(f"Argument {key} contains dangerous option: {value}")

      # Check for underscore form bypass (e.g., --uploadPack)
      lower_val = value.lower().replace("_", "-")
      if lower_val in DANGEROUS_OPTIONS or f"--{lower_val}" in DANGEROUS_OPTIONS:
        raise ValueError(f"Argument {key} contains dangerous option variant")

      # Check for leading dash (flag injection attempt) - after dangerous option check
      if value.startswith("-"):
        raise ValueError(f"Argument {key} starts with dash, potential flag injection")

    return str(value)

  def _execute_command(
    self,
    cmd: list[str],
    cwd: Path,
    timeout_seconds: int = 30,
  ) -> tuple[int, str, str]:
    """Execute a Git command via subprocess.

    Uses list arguments (no shell=True) for security.
    Captures stdout and stderr separately.

    Args:
      cmd: Command parts as list (e.g., ["git", "status", "--short"]).
      cwd: Working directory (repository path).
      timeout_seconds: Maximum execution time.

    Returns:
      Tuple of (return_code, stdout, stderr).

    Raises:
      subprocess.TimeoutExpired: If command exceeds timeout.
    """
    result = subprocess.run(
      cmd,
      cwd=str(cwd),
      capture_output=True,
      text=True,
      timeout=timeout_seconds,
      # No shell=True - prevents shell injection
    )
    return result.returncode, result.stdout, result.stderr

  def _sanitize_output(self, output: str) -> str:
    """Sanitize output to redact credentials.

    Redacts credentials from URLs in the output.

    Args:
      output: Raw command output.

    Returns:
      Sanitized output with credentials redacted.
    """
    # Redact credentials from URLs like https://user:pass@host
    return CREDENTIAL_PATTERN.sub(r"\1<redacted>@", output)


__all__ = ["GitTool", "OPERATION_ARGS"]
