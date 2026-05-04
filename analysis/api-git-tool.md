# API Design: Git Tool (Task 2.10)

**Document Version**: 1.0
**Date**: 2026-05-04
**Task**: 2.10 Git Tool from TODO.md
**Status**: Design Complete

## Executive Summary

This document defines the API design for the Git Tool, enabling version control operations within the Yoker agent harness. The design prioritizes security through operation allowlisting, command sanitization, and integration with the existing guardrail system.

**Key Design Decisions**:
- Operation allowlist with safe defaults (read-only operations only)
- Subprocess execution with list arguments (no shell=True)
- Command sanitization via allowlist (no arbitrary command execution)
- Permission handlers for destructive operations (commit, push)
- Integration with existing `PathGuardrail` for repository path validation

---

## 1. Tool Interface

### 1.1 Tool Definition

```python
class GitTool(Tool):
  """Tool for executing Git operations with security guardrails.

  Provides controlled access to Git commands through an operation allowlist.
  Destructive operations (commit, push) require explicit permission handling.
  All commands are executed via subprocess with list arguments to prevent
  shell injection.

  Attributes:
    _config: GitToolConfig with allowed commands and permission requirements.
  """

  def __init__(
    self,
    config: GitToolConfig,
    guardrail: "Guardrail | None" = None,
  ) -> None:
    """Initialize GitTool with configuration and optional guardrail.

    Args:
      config: GitToolConfig specifying allowed operations.
      guardrail: Optional guardrail for repository path validation.
    """
    super().__init__(guardrail=guardrail)
    self._config = config
```

### 1.2 Tool Name and Description

```python
@property
def name(self) -> str:
  return "git"

@property
def description(self) -> str:
  return """Execute Git operations on a repository.

  Supported operations depend on configuration. Default allows:
  - status: Show working tree status
  - log: Show commit logs
  - diff: Show changes between commits
  - branch: List branches
  - show: Show various types of objects

  Destructive operations (commit, push) require explicit permission.
  """
```

---

## 2. JSON Schema for LLM

### 2.1 Operation Schema

```python
def get_schema(self) -> dict[str, Any]:
  """Return Ollama-compatible schema for the git tool.

  Returns:
    Dict with 'type': 'function' and function metadata.
  """
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
            "enum": list(self._get_allowed_operations()),
          },
          "path": {
            "type": "string",
            "description": "Path to the Git repository (defaults to current directory)",
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
```

### 2.2 Operation-Specific Argument Schemas

Each operation has a defined set of allowed arguments:

```python
# Operation argument definitions
OPERATION_ARGS: dict[str, dict[str, Any]] = {
  "status": {
    "short": {"type": "boolean", "description": "Give output in short format"},
    "porcelain": {"type": "boolean", "description": "Machine-readable output"},
  },
  "log": {
    "oneline": {"type": "boolean", "description": "Each commit on single line"},
    "n": {"type": "integer", "description": "Limit number of commits", "minimum": 1, "maximum": 100},
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
}
```

---

## 3. Operation Categories

### 3.1 Read-Only Operations (Safe)

These operations do not modify repository state and are safe by default:

| Operation | Description | Default Allowed |
|-----------|-------------|-----------------|
| `status` | Show working tree status | Yes |
| `log` | Show commit history | Yes |
| `diff` | Show changes between commits/working tree | Yes |
| `branch` | List branches (list only, not create/delete) | Yes |
| `show` | Show commit/tag/branch content | Yes |
| `remote` | Show remote repositories (list only) | Yes |

### 3.2 Destructive Operations (Require Permission)

These operations modify repository state and require explicit permission:

| Operation | Description | Requires Permission |
|-----------|-------------|---------------------|
| `commit` | Record changes to repository | Yes |
| `push` | Update remote refs | Yes |
| `pull` | Fetch and merge from remote | Yes |
| `merge` | Join two or more histories | Yes |
| `reset` | Reset current HEAD to specified state | Yes |
| `checkout` | Switch branches or restore files | Yes |

### 3.3 Excluded Operations (Not Supported)

These operations are explicitly excluded for security:

| Operation | Reason |
|-----------|--------|
| `clone` | Creates new repositories outside control |
| `init` | Creates new repositories |
| `config` | Can modify security settings |
| `submodule` | Complex security implications |
| `filter-branch` | History rewriting, dangerous |
| `clean` | Deletes untracked files |
| `gc` | Garbage collection, side effects |

---

## 4. Command Sanitization

### 4.1 Allowlist Approach

All commands are constructed from predefined operation definitions:

```python
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
    if isinstance(value, bool):
      if value:
        cmd.append(f"--{key}")
    elif value is not None:
      cmd.extend([f"--{key}", str(sanitized)])

  return cmd
```

### 4.2 Argument Sanitization

```python
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
    forbidden = ["\n", "\r", "\x00", "`", "$", "|", ";", "&"]
    for char in forbidden:
      if char in value:
        raise ValueError(f"Argument {key} contains forbidden character")

  return str(value)
```

### 4.3 Subprocess Execution

```python
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
```

---

## 5. Configuration Schema

### 5.1 GitToolConfig

Already defined in `src/yoker/config/schema.py`:

```python
@dataclass(frozen=True)
class GitToolConfig(ToolConfig):
  """Git tool configuration.

  Attributes:
    allowed_commands: Allowed git commands.
    requires_permission: Commands that require user permission.
  """

  allowed_commands: tuple[str, ...] = (
    "status",
    "log",
    "diff",
    "branch",
    "show",
  )
  requires_permission: tuple[str, ...] = ("commit", "push")
```

### 5.2 Configuration Example

```toml
[tools.git]
enabled = true
# Read-only operations allowed by default
allowed_commands = ["status", "log", "diff", "branch", "show"]
# Destructive operations require explicit permission
requires_permission = ["commit", "push"]

# Permission handler for git commit
[permissions.handlers.git_commit]
mode = "ask_user"  # or "block" for automated environments
message = "Allow committing changes to this repository?"

# Permission handler for git push
[permissions.handlers.git_push]
mode = "block"  # Block push by default for safety
message = "Push operations are not allowed in this configuration"
```

---

## 6. Permission Integration

### 6.1 Guardrail Validation

The Git tool integrates with `PathGuardrail` to validate repository paths:

```python
def _validate_repository_path(self, path: str) -> ValidationResult:
  """Validate that the path is an allowed Git repository.

  Args:
    path: Repository path to validate.

  Returns:
    ValidationResult indicating if path is valid.
  """
  # Use guardrail if available
  if self._guardrail is not None:
    return self._guardrail.validate("git", {"path": path})

  # Basic validation without guardrail
  try:
    resolved = Path(path).resolve()
  except (OSError, ValueError):
    return ValidationResult(valid=False, reason="Invalid path")

  # Check if path exists and is a Git repository
  if not resolved.exists():
    return ValidationResult(valid=False, reason="Path does not exist")

  if not (resolved / ".git").exists():
    return ValidationResult(valid=False, reason="Not a Git repository")

  return ValidationResult(valid=True)
```

### 6.2 Permission Handler Integration

Destructive operations check permission handlers:

```python
def _check_permission(self, operation: str) -> tuple[bool, str | None]:
  """Check if operation requires and has permission.

  Args:
    operation: Git operation name.

  Returns:
    Tuple of (allowed, reason_if_blocked).
  """
  if operation not in self._config.requires_permission:
    return True, None

  # Check permission handlers from config
  handler_key = f"git_{operation}"
  handler = self._config.permissions.handlers.get(handler_key)

  if handler is None:
    # Default: block destructive operations without explicit handler
    return False, f"Operation {operation} requires permission but no handler configured"

  if handler.mode == "allow":
    return True, None
  elif handler.mode == "block":
    return False, handler.message or f"Operation {operation} is blocked"
  elif handler.mode == "ask_user":
    # In non-interactive mode, treat as block
    # Interactive mode would prompt user (Phase 1 feature)
    return False, f"Operation {operation} requires user confirmation"

  return False, f"Unknown permission mode: {handler.mode}"
```

---

## 7. Execute Implementation

### 7.1 Main Execute Method

```python
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
    return ToolResult(
      success=False,
      result="",
      error=f"Operation not allowed: {operation}. Allowed: {', '.join(self._config.allowed_commands)}",
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

  # Validate repository path
  validation = self._validate_repository_path(path)
  if not validation.valid:
    log.info("git_path_invalid", path=path, reason=validation.reason)
    return ToolResult(
      success=False,
      result="",
      error=validation.reason,
    )

  # Resolve path
  try:
    resolved_path = Path(path).resolve()
  except (OSError, ValueError):
    return ToolResult(
      success=False,
      result="",
      error="Invalid path",
    )

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

  # Execute command
  log.info("git_executing", operation=operation, path=str(resolved_path))

  try:
    returncode, stdout, stderr = self._execute_command(
      cmd,
      resolved_path,
      timeout_seconds=30,
    )

    if returncode == 0:
      log.info(
        "git_success",
        operation=operation,
        path=str(resolved_path),
        output_length=len(stdout),
      )
      return ToolResult(
        success=True,
        result=stdout.strip() or "(no output)",
      )
    else:
      log.warning(
        "git_failed",
        operation=operation,
        path=str(resolved_path),
        returncode=returncode,
        stderr=stderr,
      )
      return ToolResult(
        success=False,
        result="",
        error=stderr.strip() or f"Git command failed with code {returncode}",
      )

  except subprocess.TimeoutExpired:
    log.warning("git_timeout", operation=operation, path=str(resolved_path))
    return ToolResult(
      success=False,
      result="",
      error="Git command timed out",
    )
  except Exception as e:
    log.error("git_error", operation=operation, path=str(resolved_path), error=str(e))
    return ToolResult(
      success=False,
      result="",
      error=f"Error executing Git command: {e}",
    )
```

---

## 8. Output Formatting

### 8.1 Status Output

```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  modified:   src/yoker/tools/read.py

Untracked files:
  analysis/api-git-tool.md
```

### 8.2 Log Output (oneline format)

```
a1b2c3d feat: add GitTool implementation
d4e5f6g fix: resolve path traversal in ReadTool
g7h8i9j docs: update README with tool list
```

### 8.3 Diff Output (stat format)

```
 src/yoker/tools/read.py  | 10 +++++-----
 analysis/api-git-tool.md | 50 ++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 55 insertions(+), 5 deletions(-)
```

### 8.4 Branch Output

```
* main
  feature/git-tool
  remotes/origin/main
  remotes/origin/develop
```

---

## 9. Security Considerations

### 9.1 Attack Vectors and Mitigations

| Attack Vector | Mitigation |
|---------------|------------|
| **Shell Injection** | List arguments (no shell=True), argument sanitization |
| **Path Traversal** | PathGuardrail integration, realpath resolution |
| **Command Injection** | Operation allowlist, argument schema validation |
| **Resource Exhaustion** | Timeout enforcement (30s default) |
| **Information Disclosure** | Error message sanitization, no path leakage |
| **Privilege Escalation** | Permission handlers for destructive operations |

### 9.2 Command Injection Prevention

```python
# Example of blocked injection attempt:
args = {
  "operation": "log",
  "args": {
    "format": "$(cat /etc/passwd)",  # Blocked by forbidden characters
  },
}

# Error: Argument format contains forbidden character '$'
```

### 9.3 Path Traversal Prevention

```python
# Example of blocked traversal attempt:
kwargs = {
  "operation": "status",
  "path": "/workspace/../../../etc",
}

# PathGuardrail validates resolved path against allowed roots
# Error: Path outside allowed directories
```

---

## 10. File Locations

### 10.1 Implementation File

```
src/yoker/tools/git.py
```

### 10.2 Test File

```
tests/test_tools/test_git.py
```

### 10.3 Configuration Updates

```
src/yoker/config/schema.py  # GitToolConfig (already exists)
src/yoker/tools/__init__.py  # Export GitTool
src/yoker/tools/path_guardrail.py  # Add "git" to _FILESYSTEM_TOOLS
src/yoker/agent.py  # Register GitTool in _build_tool_registry
```

---

## 11. Test Cases

### 11.1 Basic Operations

| Test | Description |
|------|-------------|
| `test_git_status` | Execute git status on valid repository |
| `test_git_log` | Execute git log with default options |
| `test_git_log_with_limit` | Execute git log -n 5 |
| `test_git_diff` | Execute git diff on valid repository |
| `test_git_branch` | Execute git branch --list |
| `test_git_show` | Execute git show on valid commit |

### 11.2 Security Tests

| Test | Description |
|------|-------------|
| `test_injection_blocked` | Shell injection attempts blocked |
| `test_path_traversal_blocked` | Path traversal attempts blocked |
| `test_disallowed_operation` | Disallowed operation rejected |
| `test_disallowed_argument` | Disallowed argument rejected |
| `test_forbidden_characters` | Arguments with $, ;, | blocked |

### 11.3 Permission Tests

| Test | Description |
|------|-------------|
| `test_commit_blocked_without_permission` | Commit rejected without handler |
| `test_commit_blocked_with_block_handler` | Commit rejected with block mode |
| `test_push_blocked` | Push rejected by default |

### 11.4 Error Handling Tests

| Test | Description |
|------|-------------|
| `test_invalid_path` | Non-existent path returns error |
| `test_not_git_repo` | Non-git directory returns error |
| `test_timeout` | Long-running command times out |
| `test_git_not_installed` | Git not found returns error |

---

## 12. Integration with Existing Systems

### 12.1 PathGuardrail Integration

Add "git" to the filesystem tools set:

```python
# In src/yoker/tools/path_guardrail.py
_FILESYSTEM_TOOLS = frozenset({
  "read",
  "list",
  "write",
  "update",
  "search",
  "existence",
  "mkdir",
  "git",  # Add git tool
})
```

### 12.2 Tool Registry Integration

```python
# In src/yoker/tools/__init__.py
from .git import GitTool

def create_default_registry(parent_agent: "Agent | None" = None) -> ToolRegistry:
  registry = ToolRegistry()
  # ... existing tools ...
  registry.register(GitTool(config=git_config))  # Requires config
  return registry
```

### 12.3 Agent Integration

```python
# In src/yoker/agent.py
from yoker.tools.git import GitTool

def _build_tool_registry(self) -> ToolRegistry:
  registry = ToolRegistry()
  # ... existing tools ...

  # GitTool requires config
  if self.config.tools.git.enabled:
    registry.register(GitTool(
      config=self.config.tools.git,
      guardrail=self._guardrail,
    ))

  return registry
```

---

## 13. Future Enhancements

### 13.1 Phase 1 Enhancements

1. **Interactive Permission Handler**: Implement `ask_user` mode for TUI integration
2. **Push/Pull Operations**: Add with strict permission requirements
3. **Stash Operations**: Add read-only stash list operation

### 13.2 Phase 2 Enhancements

1. **Merge Conflict Detection**: Return structured merge status
2. **Branch Management**: Create/delete branches with permission
3. **Remote Operations**: List remotes, check connectivity

---

## 14. Summary

The Git Tool provides secure, controlled access to Git operations through:

1. **Operation Allowlist**: Only predefined operations are allowed
2. **Command Sanitization**: All arguments validated against schemas
3. **Subprocess Security**: List arguments, no shell=True
4. **Path Validation**: PathGuardrail integration
5. **Permission Handlers**: Destructive operations require explicit permission
6. **Timeout Enforcement**: Prevents resource exhaustion

The design follows established patterns from existing tools (ReadTool, WriteTool) while addressing Git-specific security concerns through defense-in-depth validation and explicit operation categorization.