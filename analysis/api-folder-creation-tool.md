# API Analysis: Folder Creation Tool (Task 2.9)

**Document Version**: 1.0
**Date**: 2026-04-30
**Task**: 2.9 Folder Creation Tool from TODO.md
**Status**: API Design Complete

## Summary

This document designs the API for the `MkdirTool` class, which provides folder creation functionality (mkdir -p equivalent) for the Yoker agent harness. The design follows the patterns established by `WriteTool`, `ExistenceTool`, and other filesystem tools, shares the `PathGuardrail` for security, supports recursive parent creation, and handles existing folders gracefully.

---

## 1. MkdirTool Class Design

### 1.1 Class Definition

```python
# src/yoker/tools/mkdir.py

"""Mkdir tool implementation for Yoker.

Provides the MkdirTool for creating directories with guardrail validation,
recursive parent creation, and graceful handling of existing folders.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class MkdirTool(Tool):
  """Tool for creating directories.

  Creates a directory at the given path with optional recursive parent
  creation. When a guardrail is provided, validates parameters before
  creating. Resolves paths with realpath and rejects symlinks by default.

  Returns a structured result indicating success, creation status, and
  the resolved path for debugging.
  """

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize MkdirTool with optional guardrail.

    Args:
      guardrail: Optional guardrail for parameter validation.
    """
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "mkdir"

  @property
  def description(self) -> str:
    return "Create a directory at the given path"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the mkdir tool.

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
            "path": {
              "type": "string",
              "description": "Path to the directory to create",
            },
            "recursive": {
              "type": "boolean",
              "description": "If true, create parent directories as needed (like mkdir -p). Defaults to false.",
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Create a directory.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate path parameter.
      3. Reject symlinks before resolving.
      4. Resolve the path with os.path.realpath().
      5. Check if path already exists (file or directory).
      6. Create directory, optionally with parents.
      7. Return structured result with creation status.

    Args:
      **kwargs: Must contain 'path' key.
        May contain 'recursive' (default False).

    Returns:
      ToolResult with creation result or error message.
    """
    ...
```

### 1.2 Parameter Design

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | Yes | - | Path to the directory to create |
| `recursive` | boolean | No | `false` | Create parent directories if needed |

**Path Semantics**:
- Path is resolved using `os.path.realpath()` to normalize and resolve symlinks
- Symlinks are rejected by default (security measure)
- Both relative and absolute paths are accepted
- Path must fall within configured `filesystem_paths`

**Recursive Semantics**:
- When `recursive=false`: Only creates the final directory component; fails if parent doesn't exist
- When `recursive=true`: Creates all missing parent directories (like `mkdir -p`)
- If directory already exists: Returns success (idempotent operation)

### 1.3 Return Format Design

On success, returns a structured JSON object in the `result` field:

```json
{
  "created": true,
  "path": "/workspace/src/yoker/tools/newdir"
}
```

Or for an existing directory (idempotent):

```json
{
  "created": false,
  "path": "/workspace/src/yoker/tools",
  "message": "Directory already exists"
}
```

**Return format fields**:

| Field | Type | Description |
|-------|------|-------------|
| `created` | boolean | Whether the directory was created (`false` if already existed) |
| `path` | string | The resolved absolute path that was checked/created |
| `message` | string | Optional message (e.g., "Directory already exists") |

**Why structured JSON instead of simple string?**

1. **Idempotency signaling**: LLM benefits from knowing if directory was newly created or already existed
2. **Path confirmation**: Shows the resolved path for debugging
3. **Consistency**: Matches the structured output pattern used by `ExistenceTool`
4. **Future extensibility**: Can add metadata (permissions, size) later without breaking changes

### 1.4 Error Handling

| Error | Condition | Response |
|-------|-----------|----------|
| Path outside allowed directories | Guardrail validation fails | `Path outside allowed directories: {path}` |
| Path is a symlink | `path.is_symlink()` is True | `Path not accessible` |
| Invalid path format | `os.path.realpath()` fails | `Invalid path` |
| Empty path | `path` parameter is empty | `Parameter 'path' cannot be empty` |
| Parent doesn't exist | `recursive=false` and parent missing | `Parent directory does not exist` |
| Path is a file | Path exists but is a file | `Path exists but is not a directory` |
| Permission denied | Cannot create directory | `Permission denied` |

**ToolResult for errors**:
```python
ToolResult(success=False, result="", error="Parent directory does not exist")
```

**ToolResult for successful creation**:
```python
ToolResult(success=True, result={"created": True, "path": "/workspace/newdir"})
```

**ToolResult for existing directory (idempotent)**:
```python
ToolResult(success=True, result={"created": False, "path": "/workspace/existing", "message": "Directory already exists"})
```

**Important distinction**:
- `success=False` means the tool execution failed (error)
- `success=True` with `created=False` means the directory already existed (valid result)

---

## 2. Guardrail Integration

### 2.1 Shared PathGuardrail

MkdirTool uses the same `PathGuardrail` as other filesystem tools:

```python
class MkdirTool(Tool):
  def execute(self, **kwargs: Any) -> ToolResult:
    path_str = kwargs.get("path", "")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "mkdir_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # ... rest of implementation
```

### 2.2 PathGuardrail Extension

The `PathGuardrail` needs to be updated to include `"mkdir"` in the filesystem tools set:

```python
# src/yoker/tools/path_guardrail.py

_FILESYSTEM_TOOLS = frozenset({
  "read", "list", "write", "update", "search", "existence", "mkdir"
})
```

### 2.3 Guardrail Validation for Mkdir Tool

The `PathGuardrail.validate()` method should check for mkdir:

1. **Path is a string**: Type validation
2. **Path is not empty**: Empty strings are invalid
3. **Path is within allowed directories**: Security boundary
4. **Path does not match blocked patterns**: e.g., `.git`, `.ssh`

**Note**: Unlike `read` tool, mkdir check does NOT require:
- Path to exist (that's what we're creating)
- File size limits (no content)
- Extension validation (directories don't have extensions)

**PathGuardrail validation for mkdir**:

```python
def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
  # ... existing validation ...

  # Mkdir-specific: only check path containment and blocked patterns
  # Path doesn't need to exist (we're creating it)
  if tool_name == "mkdir":
    return ValidationResult(valid=True)

  # ... rest of existing validation ...
```

---

## 3. Implementation Sketch

### 3.1 Core execute Logic

```python
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class MkdirTool(Tool):
  """Tool for creating directories."""

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "mkdir"

  @property
  def description(self) -> str:
    return "Create a directory at the given path"

  def get_schema(self) -> dict[str, Any]:
    return {
      "type": "function",
      "function": {
        "name": self.name,
        "description": self.description,
        "parameters": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "Path to the directory to create",
            },
            "recursive": {
              "type": "boolean",
              "description": "If true, create parent directories as needed (like mkdir -p). Defaults to false.",
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Create a directory.

    Returns structured result with created (boolean), path, and optional message.
    """
    path_str = kwargs.get("path", "")
    recursive = bool(kwargs.get("recursive", False))

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "mkdir_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # Validate path parameter type
    if not isinstance(path_str, str):
      log.warning("mkdir_invalid_path_type", path_type=type(path_str).__name__)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path parameter",
      )

    # Validate path is not empty
    if not path_str.strip():
      log.warning("mkdir_empty_path")
      return ToolResult(
        success=False,
        result="",
        error="Parameter 'path' cannot be empty",
      )

    # Reject symlinks before resolving to prevent traversal via symlinks
    original_path = Path(path_str)
    if original_path.is_symlink():
      log.warning("mkdir_symlink_rejected", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Path not accessible",
      )

    # Resolve the path to normalize
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      log.warning("mkdir_invalid_path", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path",
      )

    # Check what exists at the path
    try:
      if resolved.exists():
        if resolved.is_file():
          log.warning("mkdir_path_is_file", path=str(resolved))
          return ToolResult(
            success=False,
            result="",
            error="Path exists but is not a directory",
          )
        elif resolved.is_dir():
          # Directory already exists - idempotent success
          log.info(
            "mkdir_already_exists",
            path=str(resolved),
            recursive=recursive,
          )
          return ToolResult(
            success=True,
            result={
              "created": False,
              "path": str(resolved),
              "message": "Directory already exists",
            },
          )
    except PermissionError:
      log.warning("mkdir_permission_denied_check", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Permission denied",
      )

    # Check parent exists for non-recursive mode
    parent = resolved.parent
    if not recursive and not parent.exists():
      log.info("mkdir_parent_missing", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Parent directory does not exist",
      )

    # Create directory
    try:
      if recursive:
        resolved.mkdir(parents=True, exist_ok=True)
        log.info("mkdir_created_recursive", path=str(resolved))
      else:
        resolved.mkdir(parents=False, exist_ok=False)
        log.info("mkdir_created", path=str(resolved))

      return ToolResult(
        success=True,
        result={
          "created": True,
          "path": str(resolved),
        },
      )

    except PermissionError:
      log.warning("mkdir_permission_denied", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Permission denied",
      )
    except OSError as e:
      log.error("mkdir_os_error", path=str(resolved), error=str(e))
      return ToolResult(
        success=False,
        result="",
        error="Error creating directory",
      )
```

### 3.2 Package Registration

Update `src/yoker/tools/__init__.py`:

```python
from .mkdir import MkdirTool

__all__ = [
  # ... existing exports ...
  "MkdirTool",
]

def create_default_registry(parent_agent: "Agent | None" = None) -> ToolRegistry:
  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(WriteTool())
  registry.register(UpdateTool())
  registry.register(SearchTool())
  registry.register(ExistenceTool())
  registry.register(MkdirTool())  # Add this
  registry.register(AgentTool(parent_agent=parent_agent))
  return registry
```

---

## 4. PathGuardrail Updates

### 4.1 Add to Filesystem Tools Set

```python
# src/yoker/tools/path_guardrail.py

_FILESYSTEM_TOOLS = frozenset({
  "read", "list", "write", "update", "search", "existence", "mkdir"
})
```

### 4.2 Mkdir-Specific Validation

The `PathGuardrail.validate()` method should handle mkdir differently:

```python
def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
  # ... existing path extraction and resolution ...

  # Check allowed roots
  if not self._is_within_allowed_paths(resolved):
    return ValidationResult(valid=False, reason=f"Path outside allowed directories: {path_param}")

  # Check blocked patterns
  blocked_reason = self._check_blocked_patterns(resolved)
  if blocked_reason:
    return ValidationResult(valid=False, reason=blocked_reason)

  # Mkdir-specific: no file existence check required
  # (we're creating the directory)
  if tool_name == "mkdir":
    # Only check path containment and blocked patterns
    return ValidationResult(valid=True)

  # ... rest of existing validation for other tools ...
```

**Key difference**: For `mkdir` tool, the guardrail does NOT check if the path exists. It only validates:
- Path is within allowed directories
- Path does not match blocked patterns
- Path is properly formatted

This allows the tool to create new directories.

---

## 5. Ollama Function Schema

The complete schema returned by `get_schema()`:

```json
{
  "type": "function",
  "function": {
    "name": "mkdir",
    "description": "Create a directory at the given path",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Path to the directory to create"
        },
        "recursive": {
          "type": "boolean",
          "description": "If true, create parent directories as needed (like mkdir -p). Defaults to false."
        }
      },
      "required": ["path"]
    }
  }
}
```

**Design notes**:
- Minimal schema: only `path` required, `recursive` optional
- Clear description for LLM understanding
- Follows same pattern as `WriteTool.create_parents` parameter

---

## 6. Comparison with Other Tools

### 6.1 Consistency Analysis

| Aspect | WriteTool | ExistenceTool | MkdirTool | Consistent? |
|--------|-----------|---------------|-----------|-------------|
| Base class | `Tool` | `Tool` | `Tool` | Yes |
| Property pattern | `@property` | Same | Same | Yes |
| Schema format | OpenAI function | Same | Same | Yes |
| Error handling | Try/except | Same | Same | Yes |
| Return type | `ToolResult` | Same | Same | Yes |
| Guardrail integration | Optional | Optional | Optional | Yes |
| Structured output | No (string) | Yes (dict) | Yes (dict) | Yes |

### 6.2 Key Differences

| Aspect | WriteTool | ExistenceTool | MkdirTool |
|--------|-----------|---------------|-----------|
| Parameters | `path`, `content`, `create_parents` | `path` only | `path`, `recursive` |
| Output format | Simple string | JSON existence | JSON creation status |
| Modifies filesystem | Yes | No | Yes |
| Creates parents | Yes (optional) | No | Yes (optional) |
| Idempotent | No (fails on existing) | N/A | Yes (succeeds on existing) |

### 6.3 Use Case Comparison

| Tool | When to Use |
|------|-------------|
| `existence` | "Does this file/folder exist?" |
| `mkdir` | "Create this directory" |
| `write` | "Write this content to a file" |
| `list` | "What's in this directory?" |

---

## 7. Test Design

### 7.1 Test File Location

`tests/test_tools/test_mkdir.py`

### 7.2 Test Cases

#### Directory Creation Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Create new directory | `path="/tmp/newdir"` | `{"created": true, "path": "..."}` |
| Create nested directory (recursive) | `path="/tmp/a/b/c", recursive=true` | `{"created": true}` |
| Create nested directory (non-recursive) | `path="/tmp/a/b/c", recursive=false` | `success=False`, "parent does not exist" |
| Create existing directory | `path="/tmp/existing"` | `{"created": false, "message": "..."}` |
| Create where file exists | `path="/tmp/file.txt"` | `success=False`, "not a directory" |
| Symlink path | `path="/tmp/symlink"` | `success=False`, "path not accessible" |
| Empty path | `path=""` | `success=False`, "cannot be empty" |
| Path outside allowed | `path="/etc/newdir"` | Blocked by guardrail |

#### Guardrail Integration Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Guardrail allows valid path | Within allowed directories | Normal result |
| Guardrail blocks outside path | Outside allowed directories | `success=False`, guardrail error |
| Guardrail blocks blocked pattern | `.git` directory | `success=False`, blocked pattern |
| No guardrail provided | Any path | Direct creation (no validation) |

#### Recursive Mode Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Create single directory | `recursive=false` | Creates only final directory |
| Create with parents | `recursive=true` | Creates all missing parents |
| Existing parents | `recursive=true`, parents exist | Creates only final directory |
| Deep nesting | `recursive=true`, `/a/b/c/d/e` | Creates full path |

### 7.3 Fixtures

```python
import pytest
from pathlib import Path


@pytest.fixture
def temp_structure(tmp_path: Path) -> Path:
  """Create a temporary directory structure for testing."""
  # Existing files
  (tmp_path / "file.txt").write_text("hello")

  # Existing directories
  (tmp_path / "existing_dir").mkdir()
  (tmp_path / "parent_dir").mkdir()

  # Symlink (for rejection testing)
  (tmp_path / "link_to_dir").symlink_to(tmp_path / "existing_dir")

  return tmp_path
```

### 7.4 Test Implementation Sketch

```python
import pytest
from yoker.tools.mkdir import MkdirTool
from yoker.tools.base import ToolResult


def test_create_new_directory(temp_structure):
  tool = MkdirTool()
  result = tool.execute(path=str(temp_structure / "newdir"))

  assert result.success
  assert result.result["created"] is True
  assert "newdir" in result.result["path"]
  assert (temp_structure / "newdir").is_dir()


def test_create_existing_directory(temp_structure):
  tool = MkdirTool()
  result = tool.execute(path=str(temp_structure / "existing_dir"))

  assert result.success
  assert result.result["created"] is False
  assert result.result["message"] == "Directory already exists"


def test_create_nested_recursive(temp_structure):
  tool = MkdirTool()
  result = tool.execute(
    path=str(temp_structure / "a" / "b" / "c"),
    recursive=True,
  )

  assert result.success
  assert result.result["created"] is True
  assert (temp_structure / "a" / "b" / "c").is_dir()


def test_create_nested_non_recursive(temp_structure):
  tool = MkdirTool()
  result = tool.execute(
    path=str(temp_structure / "newdir" / "nested"),
    recursive=False,
  )

  assert result.success is False
  assert "parent" in result.error.lower()


def test_create_where_file_exists(temp_structure):
  tool = MkdirTool()
  result = tool.execute(path=str(temp_structure / "file.txt"))

  assert result.success is False
  assert "not a directory" in result.error.lower()


def test_symlink_rejected(temp_structure):
  tool = MkdirTool()
  result = tool.execute(path=str(temp_structure / "link_to_dir"))

  assert result.success is False
  assert "not accessible" in result.error.lower()


def test_empty_path():
  tool = MkdirTool()
  result = tool.execute(path="")

  assert result.success is False
  assert "empty" in result.error.lower()


def test_recursive_creates_parents(temp_structure):
  tool = MkdirTool()
  result = tool.execute(
    path=str(temp_structure / "deep" / "nested" / "dir"),
    recursive=True,
  )

  assert result.success
  assert (temp_structure / "deep" / "nested" / "dir").is_dir()
  assert (temp_structure / "deep").is_dir()
  assert (temp_structure / "deep" / "nested").is_dir()


def test_non_recursive_parent_must_exist(temp_structure):
  tool = MkdirTool()
  result = tool.execute(
    path=str(temp_structure / "parent_dir" / "child"),
    recursive=False,
  )

  assert result.success
  assert (temp_structure / "parent_dir" / "child").is_dir()
```

---

## 8. Security Considerations

### 8.1 Path Security

| Attack Vector | Mitigation |
|--------------|------------|
| Path traversal (`../../../etc/newdir`) | `PathGuardrail` validates path prefix |
| Symlink escape | Explicit symlink rejection |
| Path with null bytes | Path resolution fails |
| Blocked patterns (`.git`) | `PathGuardrail` pattern matching |

### 8.2 Information Disclosure

| Concern | Mitigation |
|---------|------------|
| Existence oracle | PathGuardrail restricts to allowed directories |
| Path enumeration | Guardrail blocks outside paths |
| Error message leakage | Generic error messages |

### 8.3 Denial of Service

| Concern | Mitigation |
|---------|------------|
| Disk space exhaustion | No explicit limit (future: quota) |
| Deep path creation | OS limits apply |
| Infinite loop symlinks | Symlink rejection |

### 8.4 Why Symlink Rejection

Symlinks can escape allowed directories even after realpath resolution:
1. Symlink inside allowed dir -> points outside
2. Realpath follows the symlink
3. Result is outside allowed dir

By rejecting symlinks at the source, we prevent this escape vector.

### 8.5 Why Idempotent

Directory creation is idempotent (succeeds if already exists) for safety:
- Prevents unnecessary error handling in LLM
- Matches `mkdir -p` behavior (standard Unix)
- Allows retry on failure without state concerns
- Simpler LLM logic (create directory, don't worry if it exists)

---

## 9. Action Items

### 9.1 Implementation Tasks

| Priority | Task | File(s) |
|----------|------|---------|
| High | Create `MkdirTool` class | `src/yoker/tools/mkdir.py` |
| High | Add `"mkdir"` to `_FILESYSTEM_TOOLS` | `src/yoker/tools/path_guardrail.py` |
| High | Register `MkdirTool` in package exports | `src/yoker/tools/__init__.py` |
| High | Add `MkdirTool` to default registry | `src/yoker/tools/__init__.py` |
| Medium | Write unit tests | `tests/test_tools/test_mkdir.py` |
| Low | Update documentation | `CLAUDE.md` Current State |

### 9.2 Cross-Task Considerations

- **PathGuardrail**: Already supports filesystem tools, just needs `"mkdir"` added
- **Tool Call Processing**: Tool dispatcher will call `execute()` after guardrail validation
- **Configuration**: No new configuration needed (uses existing `filesystem_paths`)

### 9.3 Documentation Updates

- Update `CLAUDE.md` to include MkdirTool in tools list
- Update `analysis/architecture.md` if it lists tools

---

## 10. Summary of Design Decisions

1. **Tool name**: `"mkdir"` - Standard Unix command name, familiar to users and LLMs
2. **Minimal schema**: Only `path` required, `recursive` optional - Simple for LLM to use
3. **Structured JSON output**: Returns `{"created": bool, "path": str}` for clarity
4. **Idempotent operation**: Returns success if directory already exists
5. **Recursive parameter**: Matches `WriteTool.create_parents` pattern for consistency
6. **Symlink rejection**: Security measure to prevent path traversal via symlinks
7. **Guardrail integration**: Uses shared `PathGuardrail` for path containment validation
8. **No existence requirement**: Unlike `read`, the path doesn't need to exist (we're creating it)
9. **Success vs created distinction**: `success=False` is error; `success=True, created=False` is valid result
10. **Consistent with existing tools**: Same patterns as `WriteTool`, `ExistenceTool`