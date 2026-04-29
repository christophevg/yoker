# API Analysis: Existence Tool (Task 2.8)

**Document Version**: 1.0
**Date**: 2026-04-29
**Task**: 2.8 File Existence Tool from TODO.md
**Status**: API Design Complete

## Summary

This document designs the API for the `ExistenceTool` class, which provides file and folder existence checking functionality for the Yoker agent harness. The design follows the patterns established by `ReadTool`, `ListTool`, and `SearchTool`, shares the `PathGuardrail` for filesystem security, and returns structured boolean results.

---

## 1. ExistenceTool Class Design

### 1.1 Class Definition

```python
# src/yoker/tools/existence.py

"""Existence tool implementation for Yoker.

Provides the ExistenceTool for checking if files and folders exist with
guardrail validation and path resolution.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class ExistenceTool(Tool):
  """Tool for checking file or folder existence.

  Checks whether a file or directory exists at the given path.
  When a guardrail is provided, validates parameters before checking.
  Resolves paths with realpath and rejects symlinks by default.

  Returns a structured result indicating existence, type (file/directory),
  and path resolution details for debugging.
  """

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize ExistenceTool with optional guardrail.

    Args:
      guardrail: Optional guardrail for parameter validation.
    """
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "existence"

  @property
  def description(self) -> str:
    return "Check if a file or folder exists at the given path"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the existence tool.

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
              "description": "Path to check for existence",
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Check if a file or folder exists.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Resolve the path with os.path.realpath().
      3. Reject symlinks unless explicitly allowed.
      4. Check existence and type (file or directory).
      5. Return structured result with boolean existence flag.

    Args:
      **kwargs: Must contain 'path' key with path to check.

    Returns:
      ToolResult with existence check result or error message.
    """
    ...
```

### 1.2 Parameter Design

| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `path` | string | Yes | - | Must be a valid path string within allowed directories |

**Path Semantics**:
- Path is resolved using `os.path.realpath()` to normalize and resolve symlinks
- Symlinks are rejected by default (security measure)
- Both relative and absolute paths are accepted
- Path must fall within configured `filesystem_paths`

### 1.3 Return Format Design

On success, returns a structured JSON object in the `result` field:

```json
{
  "exists": true,
  "type": "file",
  "path": "/workspace/src/yoker/tools/read.py"
}
```

Or for a directory:

```json
{
  "exists": true,
  "type": "directory",
  "path": "/workspace/src/yoker/tools"
}
```

Or for non-existent path:

```json
{
  "exists": false,
  "type": null,
  "path": "/workspace/nonexistent.txt"
}
```

**Return format fields**:

| Field | Type | Description |
|-------|------|-------------|
| `exists` | boolean | Whether the path exists |
| `type` | string or null | `"file"`, `"directory"`, or `null` if not exists |
| `path` | string | The resolved absolute path that was checked |

**Why structured JSON instead of simple boolean?**

1. **Type information**: LLM benefits from knowing if it's a file or directory
2. **Path confirmation**: Shows the resolved path for debugging
3. **Consistency**: Matches the structured output pattern used by `SearchTool`
4. **Future extensibility**: Can add metadata (size, permissions) later without breaking changes

### 1.4 Error Handling

| Error | Condition | Response |
|-------|-----------|----------|
| Path outside allowed directories | Guardrail validation fails | `Path outside allowed directories: {path}` |
| Path is a symlink | `path.is_symlink()` is True | `Path is a symlink: not permitted` |
| Invalid path format | `os.path.realpath()` fails | `Invalid path` |
| Empty path | `path` parameter is empty | `Parameter 'path' cannot be empty` |
| Permission denied | Cannot access parent directory | `Permission denied: {path}` |

**ToolResult for errors**:
```python
ToolResult(success=False, result="", error="Path outside allowed directories: /etc/passwd")
```

**ToolResult for successful checks**:
```python
ToolResult(success=True, result={"exists": True, "type": "file", "path": "/workspace/file.txt"})
```

**Important distinction**:
- `success=False` means the tool execution failed (error)
- `success=True` with `exists=False` means the path does not exist (valid result)

---

## 2. Guardrail Integration

### 2.1 Shared PathGuardrail

ExistenceTool uses the same `PathGuardrail` as `ReadTool`, `ListTool`, and `SearchTool`:

```python
class ExistenceTool(Tool):
  def execute(self, **kwargs: Any) -> ToolResult:
    path_str = kwargs.get("path", "")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "existence_guardrail_blocked",
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

The `PathGuardrail` needs to be updated to include `"existence"` in the filesystem tools set:

```python
# src/yoker/tools/path_guardrail.py

_FILESYSTEM_TOOLS = frozenset({
  "read", "list", "write", "update", "search", "existence"
})
```

### 2.3 Guardrail Validation for Existence Tool

The `PathGuardrail.validate()` method should check:

1. **Path is a string**: Type validation
2. **Path is not empty**: Empty strings are invalid
3. **Path is within allowed directories**: Security boundary
4. **Path does not match blocked patterns**: e.g., `.env` files

**Note**: Unlike `read` tool, existence check does NOT require:
- File to exist (that's what we're checking)
- Extension validation (we just check existence)
- Size limits (no content is read)

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


class ExistenceTool(Tool):
  """Tool for checking file or folder existence."""

  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    super().__init__(guardrail=guardrail)

  @property
  def name(self) -> str:
    return "existence"

  @property
  def description(self) -> str:
    return "Check if a file or folder exists at the given path"

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
              "description": "Path to check for existence",
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Check if a file or folder exists.

    Returns structured result with exists (boolean), type (file/directory/null),
    and the resolved path.
    """
    path_str = kwargs.get("path", "")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info(
          "existence_guardrail_blocked",
          path=path_str,
          reason=validation.reason,
        )
        return ToolResult(
          success=False,
          result="",
          error=validation.reason,
        )

    # Validate path parameter
    if not isinstance(path_str, str):
      log.warning("existence_invalid_path_type", path_type=type(path_str).__name__)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path parameter",
      )

    if not path_str.strip():
      log.warning("existence_empty_path")
      return ToolResult(
        success=False,
        result="",
        error="Parameter 'path' cannot be empty",
      )

    # Reject symlinks before resolving
    original_path = Path(path_str)
    if original_path.is_symlink():
      log.warning("existence_symlink_rejected", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Path is a symlink: not permitted",
      )

    # Resolve the path
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      log.warning("existence_invalid_path", path=path_str)
      return ToolResult(
        success=False,
        result="",
        error="Invalid path",
      )

    # Check existence and type
    try:
      if resolved.exists():
        if resolved.is_file():
          path_type = "file"
        elif resolved.is_dir():
          path_type = "directory"
        else:
          # Could be a socket, device, etc.
          path_type = "other"

        log.info(
          "existence_check_success",
          path=str(resolved),
          exists=True,
          type=path_type,
        )

        return ToolResult(
          success=True,
          result={
            "exists": True,
            "type": path_type,
            "path": str(resolved),
          },
        )
      else:
        log.info(
          "existence_check_success",
          path=str(resolved),
          exists=False,
          type=None,
        )

        return ToolResult(
          success=True,
          result={
            "exists": False,
            "type": None,
            "path": str(resolved),
          },
        )

    except PermissionError:
      log.warning("existence_permission_denied", path=str(resolved))
      return ToolResult(
        success=False,
        result="",
        error="Permission denied",
      )
    except OSError as e:
      log.error("existence_os_error", path=str(resolved), error=str(e))
      return ToolResult(
        success=False,
        result="",
        error="Error checking path",
      )
```

### 3.2 Package Registration

Update `src/yoker/tools/__init__.py`:

```python
from .existence import ExistenceTool

__all__ = [
  # ... existing exports ...
  "ExistenceTool",
]

def create_default_registry() -> ToolRegistry:
  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(SearchTool())
  registry.register(ExistenceTool())  # Add this
  return registry
```

---

## 4. PathGuardrail Updates

### 4.1 Add to Filesystem Tools Set

```python
# src/yoker/tools/path_guardrail.py

_FILESYSTEM_TOOLS = frozenset({
  "read", "list", "write", "update", "search", "existence"
})
```

### 4.2 Existence-Specific Validation

The `PathGuardrail.validate()` method should handle existence checks differently:

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

  # Existence-specific: no file existence check required
  # (that's what the tool is checking for)
  if tool_name == "existence":
    # Only check path containment and blocked patterns
    return ValidationResult(valid=True)

  # ... rest of existing validation for other tools ...
```

**Key difference**: For `existence` tool, the guardrail does NOT check if the path exists. It only validates:
- Path is within allowed directories
- Path does not match blocked patterns
- Path is properly formatted

This allows the tool to report `exists: false` for valid paths that don't exist.

---

## 5. Ollama Function Schema

The complete schema returned by `get_schema()`:

```json
{
  "type": "function",
  "function": {
    "name": "existence",
    "description": "Check if a file or folder exists at the given path",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Path to check for existence"
        }
      },
      "required": ["path"]
    }
  }
}
```

**Design notes**:
- Minimal schema: only `path` parameter required
- No type filter parameter: let the tool report the type automatically
- Description is concise but clear for LLM understanding

---

## 6. Comparison with Other Tools

### 6.1 Consistency Analysis

| Aspect | ReadTool | ListTool | SearchTool | ExistenceTool | Consistent? |
|--------|----------|----------|------------|---------------|-------------|
| Base class | `Tool` | `Tool` | `Tool` | `Tool` | Yes |
| Property pattern | `@property` | Same | Same | Same | Yes |
| Schema format | OpenAI function | Same | Same | Same | Yes |
| Error handling | Try/except | Same | Same | Same | Yes |
| Return type | `ToolResult` | Same | Same | Same | Yes |
| Guardrail integration | Optional | Optional | Optional | Optional | Yes |
| Structured output | No (string) | No (string) | Yes (dict) | Yes (dict) | Yes |

### 6.2 Key Differences

| Aspect | ReadTool | ListTool | SearchTool | ExistenceTool |
|--------|----------|----------|------------|---------------|
| Parameters | `path` | `path`, `max_depth`, etc. | `path`, `pattern`, `type` | `path` only |
| Output format | File content string | Tree string | JSON matches | JSON existence |
| Requires existence | Yes (must exist) | Yes (must exist) | No (can be empty) | No (checking it) |
| Resource usage | Reads full file | Walks directory | Walks + reads | Stat only (fast) |

### 6.3 Use Case Comparison

| Tool | When to Use |
|------|-------------|
| `existence` | "Does this file exist?" |
| `read` | "What's in this file?" (must exist) |
| `list` | "What's in this directory?" (must exist) |
| `search` | "Where is this pattern?" (searches recursively) |

---

## 7. Test Design

### 7.1 Test File Location

`tests/test_tools/test_existence.py`

### 7.2 Test Cases

#### Existence Check Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Existing file | `path="/tmp/test.txt"` | `{"exists": true, "type": "file"}` |
| Existing directory | `path="/tmp/test_dir"` | `{"exists": true, "type": "directory"}` |
| Non-existent file | `path="/tmp/nonexistent.txt"` | `{"exists": false, "type": null}` |
| Non-existent directory | `path="/tmp/nonexistent_dir"` | `{"exists": false, "type": null}` |
| Nested existing path | `path="/tmp/a/b/c/file.txt"` | Correct type and existence |
| Symlink path | `path="/tmp/symlink"` | `success=False`, "symlink not permitted" |
| Empty path | `path=""` | `success=False`, "cannot be empty" |
| Path outside allowed | `path="/etc/passwd"` | Blocked by guardrail |

#### Guardrail Integration Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Guardrail allows valid path | Within allowed directories | Normal result |
| Guardrail blocks outside path | Outside allowed directories | `success=False`, guardrail error |
| Guardrail blocks blocked pattern | `.env` file | `success=False`, blocked pattern |
| No guardrail provided | Any path | Direct check (no validation) |

#### Type Detection Tests

| Test | Input | Expected Type |
|------|-------|---------------|
| Regular file | `.txt` file | `"file"` |
| Directory | Directory path | `"directory"` |
| Hidden file | `.hidden` file | `"file"` |
| Hidden directory | `.git` directory | `"directory"` |

### 7.3 Fixtures

```python
import pytest
from pathlib import Path


@pytest.fixture
def temp_structure(tmp_path: Path) -> Path:
  """Create a temporary directory structure for testing."""
  # Files
  (tmp_path / "file.txt").write_text("hello")
  (tmp_path / "file.py").write_text("print('hi')")
  (tmp_path / ".hidden").write_text("hidden content")

  # Directories
  (tmp_path / "subdir").mkdir()
  (tmp_path / "subdir" / "nested.txt").write_text("nested")
  (tmp_path / ".hidden_dir").mkdir()

  # Symlink (for rejection testing)
  (tmp_path / "link_to_file").symlink_to(tmp_path / "file.txt")

  return tmp_path
```

### 7.4 Test Implementation Sketch

```python
import pytest
from yoker.tools.existence import ExistenceTool
from yoker.tools.base import ToolResult


def test_existing_file(temp_structure):
  tool = ExistenceTool()
  result = tool.execute(path=str(temp_structure / "file.txt"))

  assert result.success
  assert result.result["exists"] is True
  assert result.result["type"] == "file"
  assert "file.txt" in result.result["path"]


def test_existing_directory(temp_structure):
  tool = ExistenceTool()
  result = tool.execute(path=str(temp_structure / "subdir"))

  assert result.success
  assert result.result["exists"] is True
  assert result.result["type"] == "directory"


def test_nonexistent_path(temp_structure):
  tool = ExistenceTool()
  result = tool.execute(path=str(temp_structure / "nonexistent.txt"))

  assert result.success
  assert result.result["exists"] is False
  assert result.result["type"] is None


def test_symlink_rejected(temp_structure):
  tool = ExistenceTool()
  result = tool.execute(path=str(temp_structure / "link_to_file"))

  assert result.success is False
  assert "symlink" in result.error.lower()


def test_empty_path():
  tool = ExistenceTool()
  result = tool.execute(path="")

  assert result.success is False
  assert "empty" in result.error.lower()


def test_hidden_file_exists(temp_structure):
  tool = ExistenceTool()
  result = tool.execute(path=str(temp_structure / ".hidden"))

  assert result.success
  assert result.result["exists"] is True
  assert result.result["type"] == "file"
```

---

## 8. Security Considerations

### 8.1 Path Security

| Attack Vector | Mitigation |
|--------------|------------|
| Path traversal (`../../../etc/passwd`) | `PathGuardrail` validates path prefix |
| Symlink escape | Explicit symlink rejection |
| Path with null bytes | Path resolution fails |
| Blocked patterns (`.env`) | `PathGuardrail` pattern matching |

### 8.2 Information Disclosure

| Concern | Mitigation |
|---------|------------|
| Existence oracle attack | PathGuardrail restricts to allowed directories |
| Timing attacks | Not applicable (fast operation) |
| Path enumeration | Guardrail blocks outside paths |

### 8.3 Why Symlink Rejection

Symlinks can escape allowed directories even after realpath resolution:
1. Symlink inside allowed dir -> points outside
2. Realpath follows the symlink
3. Result is outside allowed dir

By rejecting symlinks at the source, we prevent this escape vector.

---

## 9. Action Items

### 9.1 Implementation Tasks

| Priority | Task | File(s) |
|----------|------|---------|
| High | Create `ExistenceTool` class | `src/yoker/tools/existence.py` |
| High | Add `"existence"` to `_FILESYSTEM_TOOLS` | `src/yoker/tools/path_guardrail.py` |
| High | Register `ExistenceTool` in package exports | `src/yoker/tools/__init__.py` |
| High | Add `ExistenceTool` to default registry | `src/yoker/tools/__init__.py` |
| Medium | Write unit tests | `tests/test_tools/test_existence.py` |
| Low | Update documentation | `CLAUDE.md` Current State |

### 9.2 Cross-Task Considerations

- **Task 2.9 (Folder Creation Tool)**: Will also need `PathGuardrail` integration
- **Task 3.2 (Tool Call Processing)**: Tool dispatcher will call `execute()` after guardrail validation

### 9.3 Documentation Updates

- Update `CLAUDE.md` to include ExistenceTool in tools list
- Update `analysis/architecture.md` if it lists tools

---

## 10. Summary of Design Decisions

1. **Tool name**: `"existence"` - Clear, noun-based, indicates what's being checked
2. **Minimal schema**: Only `path` parameter - LLM doesn't need to specify type filter
3. **Structured JSON output**: Returns `{"exists": bool, "type": str|null, "path": str}` for clarity
4. **Type auto-detection**: Tool reports whether it's a file or directory automatically
5. **Symlink rejection**: Security measure to prevent path traversal via symlinks
6. **Guardrail integration**: Uses shared `PathGuardrail` for path containment validation
7. **No existence requirement**: Unlike `read`, the path doesn't need to exist (that's what we're checking)
8. **Success vs exists distinction**: `success=False` is error; `success=True, exists=False` is valid result
9. **Consistent with existing tools**: Same patterns as `ReadTool`, `ListTool`, `SearchTool`
10. **Fast operation**: Only uses `stat()` call, no file reading