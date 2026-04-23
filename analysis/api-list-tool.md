# API Analysis: List Tool (Task 2.2)

**Document Version**: 1.0
**Date**: 2026-04-23
**Task**: 2.2 List Tool from TODO.md
**Status**: API Design Complete

## Summary

This document designs the API for the `ListTool` class, which provides directory listing functionality for the Yoker agent harness. The design follows the exact patterns established by `ReadTool` for consistency, extends them with parameter validation and limit enforcement, and introduces a reusable `PathGuardrail` that can be shared across all filesystem tools.

---

## 1. ListTool Class Design

### 1.1 Class Definition

```python
# src/yoker/tools/list.py

"""List tool implementation for Yoker.

Provides the ListTool for listing directory contents with configurable
depth, entry limits, and pattern filtering. Follows the same patterns
as ReadTool for consistency.
"""

import fnmatch
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ListTool(Tool):
  """Tool for listing directory contents.

  Lists files and directories with optional recursion depth control,
  entry limits, and glob pattern filtering. Returns a tree-formatted
  string for LLM consumption.
  """

  # Defaults enforced when parameters are omitted or exceed limits
  DEFAULT_MAX_DEPTH: int = 1
  DEFAULT_MAX_ENTRIES: int = 1000
  ABSOLUTE_MAX_DEPTH: int = 10
  ABSOLUTE_MAX_ENTRIES: int = 5000

  @property
  def name(self) -> str:
    return "list"

  @property
  def description(self) -> str:
    return (
      "List files and directories. "
      "Supports optional recursion (max_depth), "
      "entry limits (max_entries), and glob pattern filtering."
    )

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the list tool."""
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
              "description": "Path to the directory to list",
            },
            "max_depth": {
              "type": "integer",
              "description": (
                "Maximum recursion depth (1 = immediate children only, "
                "2 = includes subdirectories). Defaults to 1."
              ),
              "minimum": 0,
              "maximum": self.ABSOLUTE_MAX_DEPTH,
            },
            "max_entries": {
              "type": "integer",
              "description": (
                "Maximum total entries to return. "
                f"Defaults to {self.DEFAULT_MAX_ENTRIES}."
              ),
              "minimum": 1,
              "maximum": self.ABSOLUTE_MAX_ENTRIES,
            },
            "pattern": {
              "type": "string",
              "description": (
                "Optional glob pattern to filter entries "
                '(e.g., "*.py" for Python files)'
              ),
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """List directory contents with optional filtering and limits.

    Args:
      **kwargs: Must contain 'path'. May contain 'max_depth',
        'max_entries', and 'pattern'.

    Returns:
      ToolResult with formatted directory listing or error message.
    """
    ...
```

### 1.2 Parameter Design

| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `path` | string | Yes | - | Must be a valid directory path |
| `max_depth` | integer | No | 1 | Clamped to `[0, ABSOLUTE_MAX_DEPTH]` |
| `max_entries` | integer | No | 1000 | Clamped to `[1, ABSOLUTE_MAX_ENTRIES]` |
| `pattern` | string | No | None | Glob pattern passed to `fnmatch.filter` |

**max_depth semantics**:
- `1` = List immediate children only (non-recursive, default)
- `2` = List children and one level of grandchildren
- `0` = List the directory itself (just the path, no children)
- This matches `tree -L` semantics and is intuitive for LLMs

**max_entries semantics**:
- Counts both files and directories
- When exceeded, listing stops and a truncation notice is appended
- Prevents excessively large outputs that exceed LLM context windows

**pattern semantics**:
- Uses Python `fnmatch` for glob-style matching (not regex)
- Applied to the basename of each entry
- Examples: `"*.py"`, `"*.md"`, `"test_*"`
- If pattern is invalid, falls back to listing all entries and logs a warning

### 1.3 Return Format Design

On success, returns a tree-formatted string:

```
src/yoker/
  tools/
    base.py
    registry.py
    guardrails.py
    read.py
    __init__.py
  config/
    loader.py
    schema.py
  __init__.py
  __main__.py
  agent.py

12 entries total (8 files, 4 directories)
```

**Formatting rules**:
- Directories suffixed with `/`
- Indentation: 2 spaces per depth level (matches project style)
- Entries sorted alphabetically (directories first, then files, or mixed? Recommend mixed alphabetical for simplicity)
- Summary line: "{N} entries total ({F} files, {D} directories)"
- If truncated: appends "... ({N} more entries truncated, max_entries={M})"

**When max_depth=0**:
```
src/yoker/

0 entries total (0 files, 1 directory)
```

**When path is a file**:
```
src/yoker/__init__.py

1 entry total (1 file, 0 directories)
```

### 1.4 Error Handling

Follows the same pattern as `ReadTool`:

| Error | Condition | Response |
|-------|-----------|----------|
| Path not found | `Path(path).exists()` is False | `FileNot found: {path}` |
| Not a directory | `Path(path).is_dir()` is False | Shows the file as single entry |
| Permission denied | `PermissionError` on traversal | `Permission denied: {path}` |
| Generic error | Any other exception | `Error listing directory: {e}` |

**ToolResult for errors**:
```python
ToolResult(success=False, result="", error="File not found: /nonexistent")
```

---

## 2. Guardrail Integration Design

### 2.1 Current State

The `Guardrail` ABC exists but is **not yet wired into tool execution**. `ReadTool` has no guardrail integration. The architecture specifies a `PermissionEnforcer` that will validate parameters before tool execution.

### 2.2 Recommended: PathGuardrail (Shared Resource)

Create a `PathGuardrail` class that can be shared between all filesystem tools (`ListTool`, `ReadTool`, `WriteTool`, `UpdateTool`, `SearchTool`):

```python
# src/yoker/tools/guardrails.py (or src/yoker/permissions/guardrails.py)

from pathlib import Path
from typing import Any

from .base import Guardrail, ValidationResult


class PathGuardrail(Guardrail):
  """Guardrail that restricts filesystem operations to allowed paths.

  Validates that the 'path' parameter falls within one of the
  configured allowed prefixes. Shared across all filesystem tools.

  Example:
    guardrail = PathGuardrail(allowed_prefixes=["/workspace", "/docs"])
    result = guardrail.validate("list", {"path": "/workspace/src"})
    # Returns ValidationResult(valid=True)
  """

  def __init__(self, allowed_prefixes: list[str]) -> None:
    """Initialize with allowed path prefixes.

    Args:
      allowed_prefixes: List of absolute or relative path prefixes.
        All paths must start with one of these prefixes to be valid.
    """
    self._allowed_prefixes = [Path(p).resolve() for p in allowed_prefixes]

  def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
    """Validate that the path parameter is within allowed prefixes.

    Args:
      tool_name: Name of the tool being validated.
      params: Tool parameters dictionary.

    Returns:
      ValidationResult indicating whether the path is allowed.
    """
    path_str = params.get("path", "")
    if not path_str:
      return ValidationResult(valid=False, reason="Missing 'path' parameter")

    path = Path(path_str).resolve()

    for allowed in self._allowed_prefixes:
      if path == allowed or allowed in path.parents or path == allowed.parent:
        # Note: `allowed in path.parents` checks if path is inside allowed
        # Actually correct check: str(path).startswith(str(allowed))
        pass

    # Correct implementation:
    try:
      path = Path(path_str).resolve()
    except (OSError, ValueError):
      return ValidationResult(valid=False, reason=f"Invalid path: {path_str}")

    for allowed in self._allowed_prefixes:
      try:
        path.relative_to(allowed)
        return ValidationResult(valid=True)
      except ValueError:
        continue

    return ValidationResult(
      valid=False,
      reason=(
        f"Path '{path_str}' is outside allowed directories: "
        f"{[str(p) for p in self._allowed_prefixes]}"
      ),
    )
```

**Why share PathGuardrail**:
- All filesystem tools use the `path` parameter
- Same validation logic applies (is path within allowed prefixes?)
- Reduces duplication
- Consistent error messages

### 2.3 Tool-Specific Limit Guardrails

The `max_depth` and `max_entries` parameters are **not guardrails** in the permission sense - they are operational limits. Two approaches:

**Approach A: Tool self-enforces (Recommended for MVP)**
- The tool clamps values to absolute maximums internally
- Simple, no external dependency
- Limits are hardcoded per tool class

**Approach B: LimitGuardrail (Future enhancement)**
- A `LimitGuardrail` that reads per-tool limits from config
- More flexible but requires config injection into tools
- Adds complexity before the permission system exists

**Recommendation**: Use Approach A for now. When the PermissionEnforcer is built (Phase 2), it can override or pre-validate these limits before calling `execute()`.

### 2.4 Integration Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Tool Execution Flow                      │
│                                                              │
│   LLM calls: list(path="/workspace/src", max_depth=2)       │
│                      │                                       │
│                      ▼                                       │
│   ┌──────────────────────────────────────────────┐          │
│   │  PermissionEnforcer (Phase 2)                  │          │
│   │                                              │          │
│   │  PathGuardrail.validate("list", params)      │          │
│   │    - Is path in allowed_prefixes?            │          │
│   │                                              │          │
│   │  LimitGuardrail.validate("list", params)     │          │
│   │    - Is max_depth <= config.max_depth?       │          │
│   │    - Is max_entries <= config.max_entries?   │          │
│   │                                              │          │
│   └──────────────────────────────────────────────┘          │
│                      │                                       │
│          Valid? ─────┼─────► ListTool.execute(...)         │
│                      │                                       │
│          Invalid?    └─────► ToolResult(success=False)      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Ollama Function Schema

The complete schema returned by `get_schema()`:

```json
{
  "type": "function",
  "function": {
    "name": "list",
    "description": "List files and directories. Supports optional recursion (max_depth), entry limits (max_entries), and glob pattern filtering.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Path to the directory to list"
        },
        "max_depth": {
          "type": "integer",
          "description": "Maximum recursion depth (1 = immediate children only, 2 = includes subdirectories). Defaults to 1.",
          "minimum": 0,
          "maximum": 10
        },
        "max_entries": {
          "type": "integer",
          "description": "Maximum total entries to return. Defaults to 1000.",
          "minimum": 1,
          "maximum": 5000
        },
        "pattern": {
          "type": "string",
          "description": "Optional glob pattern to filter entries (e.g., '*.py' for Python files)"
        }
      },
      "required": ["path"]
    }
  }
}
```

**Design notes**:
- `minimum` and `maximum` in JSON Schema help the LLM generate valid values
- Descriptions are concise but explain the default behavior
- The LLM should understand that `max_depth=1` is the safe default (non-recursive)
- `pattern` is optional but clearly documented as glob-style

---

## 4. Comparison with ReadTool

### 4.1 Consistency Analysis

| Aspect | ReadTool | ListTool | Consistent? |
|--------|----------|----------|-------------|
| Base class | `Tool` | `Tool` | Yes |
| Property pattern | `@property name`, `@property description` | Same | Yes |
| Schema format | OpenAI function-calling | Same | Yes |
| Error handling | Try/except FileNotFound, PermissionError | Same | Yes |
| Return type | `ToolResult` | Same | Yes |
| Execute signature | `**kwargs: str` | `**kwargs: Any` | *Slightly different* |

### 4.2 Execute Signature Difference

ReadTool uses `**kwargs: str` because its only parameter (`path`) is a string. ListTool has integer parameters (`max_depth`, `max_entries`), so `**kwargs: Any` is more accurate.

**Recommendation**: Change ReadTool to `**kwargs: Any` for consistency, or keep both as `Any` to allow future parameter additions. This is a minor refactor.

### 4.3 Key Differences

| Aspect | ReadTool | ListTool |
|--------|----------|----------|
| Parameters | `path` only | `path`, `max_depth`, `max_entries`, `pattern` |
| Validation | Minimal (file existence) | Depth/entry clamping, pattern validation |
| Output | Raw file content | Structured tree text |
| Recursion | N/A | Configurable |
| Filtering | N/A | Glob pattern support |

### 4.4 Shared Components

Both tools should share:
- `PathGuardrail` for path restriction
- Error handling pattern (FileNotFound, PermissionError, generic Exception)
- `ToolResult` return format

---

## 5. Implementation Sketch

### 5.1 Core execute Logic

```python
  def execute(self, **kwargs: Any) -> ToolResult:
    path_str = kwargs.get("path", "")
    if not path_str:
      return ToolResult(
        success=False, result="", error="Missing required parameter: path"
      )

    # Parse and clamp parameters
    try:
      max_depth = self._clamp(
        int(kwargs.get("max_depth", self.DEFAULT_MAX_DEPTH)),
        0, self.ABSOLUTE_MAX_DEPTH,
      )
      max_entries = self._clamp(
        int(kwargs.get("max_entries", self.DEFAULT_MAX_ENTRIES)),
        1, self.ABSOLUTE_MAX_ENTRIES,
      )
    except (ValueError, TypeError):
      return ToolResult(
        success=False, result="", error="Invalid numeric parameter"
      )

    pattern = kwargs.get("pattern", "")

    try:
      path = Path(path_str)
      if not path.exists():
        return ToolResult(
          success=False, result="", error=f"File not found: {path_str}"
        )

      # If path is a file, return it as single entry
      if not path.is_dir():
        return ToolResult(
          success=True,
          result=f"{path_str}\n\n1 entry total (1 file, 0 directories)",
        )

      # Build tree listing
      lines, file_count, dir_count = self._build_tree(
        path, max_depth, max_entries, pattern
      )

      total = file_count + dir_count
      lines.append("")
      lines.append(
        f"{total} entries total ({file_count} files, {dir_count} directories)"
      )

      return ToolResult(success=True, result="\n".join(lines))

    except PermissionError:
      return ToolResult(
        success=False, result="", error=f"Permission denied: {path_str}"
      )
    except Exception as e:
      return ToolResult(
        success=False, result="", error=f"Error listing directory: {e}"
      )

  def _clamp(self, value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))

  def _build_tree(
    self,
    root: Path,
    max_depth: int,
    max_entries: int,
    pattern: str,
  ) -> tuple[list[str], int, int]:
    """Build tree listing. Returns (lines, file_count, dir_count)."""
    lines: list[str] = [str(root) + "/"]
    file_count = 0
    dir_count = 1  # Count root directory
    entry_count = 1

    if max_depth == 0:
      return lines, file_count, dir_count

    def walk(current: Path, depth: int, prefix: str = "") -> None:
      nonlocal file_count, dir_count, entry_count

      if depth >= max_depth or entry_count >= max_entries:
        return

      try:
        entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
      except PermissionError:
        lines.append(prefix + "... (permission denied)")
        return

      if pattern:
        entries = [e for e in entries if fnmatch.fnmatch(e.name, pattern)]

      for entry in entries:
        if entry_count >= max_entries:
          lines.append(prefix + "... (truncated)")
          return

        if entry.is_dir():
          lines.append(prefix + entry.name + "/")
          dir_count += 1
          entry_count += 1
          walk(entry, depth + 1, prefix + "  ")
        else:
          lines.append(prefix + entry.name)
          file_count += 1
          entry_count += 1

    walk(root, 0)
    return lines, file_count, dir_count
```

### 5.2 Package Registration

Update `src/yoker/tools/__init__.py`:

```python
from .list import ListTool

__all__ = [
  # ... existing exports ...
  "ListTool",
]

def create_default_registry() -> ToolRegistry:
  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())  # Add this
  return registry
```

---

## 6. Test Design

### 6.1 Test File Location

`tests/test_tools/test_list.py`

### 6.2 Test Cases

| Test | Input | Expected Result |
|------|-------|-----------------|
| List flat directory | `path="/tmp/test_dir"` | Shows entries, correct counts |
| Recursive listing | `path="/tmp/test_dir", max_depth=2` | Shows nested entries |
| Depth limit 1 (default) | `path="/tmp/test_dir"` | Only immediate children |
| Depth limit 0 | `path="/tmp/test_dir", max_depth=0` | Only root path shown |
| Pattern filter | `path="/tmp/test_dir", pattern="*.py"` | Only matching entries |
| Max entries truncation | `max_entries=3` on dir with 10 entries | Truncation notice appended |
| Nonexistent path | `path="/nonexistent"` | `success=False`, "File not found" |
| Path is a file | `path="/tmp/test_file.txt"` | Shows file as single entry |
| Permission denied | Mock `PermissionError` | `success=False`, "Permission denied" |
| Invalid max_depth string | `max_depth="abc"` | `success=False`, "Invalid numeric parameter" |
| Negative max_depth | `max_depth=-5` | Clamped to 0 |
| Excessive max_depth | `max_depth=999` | Clamped to `ABSOLUTE_MAX_DEPTH` (10) |
| Invalid pattern | `pattern="[invalid"` | Graceful fallback (no filtering) |
| Empty directory | `path="/tmp/empty"` | Shows path, "0 entries total" |
| Missing path param | No `path` in kwargs | `success=False`, "Missing required parameter" |

### 6.3 Fixtures

```python
import pytest
from pathlib import Path


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
  """Create a temporary directory with nested structure."""
  (tmp_path / "file1.txt").write_text("hello")
  (tmp_path / "file2.py").write_text("print('hi')")
  (tmp_path / "subdir").mkdir()
  (tmp_path / "subdir" / "nested.txt").write_text("nested")
  (tmp_path / "subdir" / "deep").mkdir()
  (tmp_path / "subdir" / "deep" / "bottom.py").write_text("deep")
  return tmp_path
```

### 6.4 Mocking Strategy

- Use `tmp_path` fixture for real filesystem operations
- Use `monkeypatch` to simulate `PermissionError` on `Path.iterdir()`
- No need to mock `fnmatch` (it's deterministic)

---

## 7. Recommendations for Guardrail System

### 7.1 Immediate Actions

1. **Create `PathGuardrail`** in `src/yoker/tools/guardrails.py` (or a new `src/yoker/permissions/` module)
2. **Document that tools do NOT call guardrails themselves** - guardrails are called by the PermissionEnforcer before execution
3. **Keep limit enforcement inside tools** for MVP simplicity

### 7.2 Future Integration (Phase 2)

When the `PermissionEnforcer` is built:

```python
class PermissionEnforcer:
  def __init__(self, config: PermissionsConfig) -> None:
    self._guardrails: dict[str, list[Guardrail]] = {
      "list": [PathGuardrail(config.filesystem_paths)],
      "read": [PathGuardrail(config.filesystem_paths)],
      # ...
    }

  def validate(self, tool_name: str, params: dict[str, Any]) -> ValidationResult:
    for guardrail in self._guardrails.get(tool_name, []):
      result = guardrail.validate(tool_name, params)
      if not result.valid:
        return result
    return ValidationResult(valid=True)
```

### 7.3 Why Limits Are Not Guardrails

| Guardrail | Limit |
|-----------|-------|
| **Purpose** | Security (prevent unauthorized access) | Operational safety (prevent overload) |
| **Source** | Configuration (`permissions.filesystem_paths`) | Tool defaults + config overrides |
| **Failure mode** | Block execution entirely | Clamp/truncate results |
| **Shared?** | Yes (PathGuardrail across tools) | No (per-tool logic) |

This distinction keeps the guardrail system focused on security boundaries while tools handle their own operational constraints.

---

## 8. Action Items

### 8.1 Implementation Tasks

| Priority | Task | File(s) |
|----------|------|---------|
| High | Create `ListTool` class | `src/yoker/tools/list.py` |
| High | Register `ListTool` in package exports | `src/yoker/tools/__init__.py` |
| High | Add `ListTool` to default registry | `src/yoker/tools/__init__.py` |
| Medium | Create `PathGuardrail` (shared) | `src/yoker/tools/guardrails.py` or `src/yoker/permissions/guardrails.py` |
| Medium | Write unit tests | `tests/test_tools/test_list.py` |
| Low | Add `tests/test_tools/__init__.py` | `tests/test_tools/__init__.py` |

### 8.2 Cross-Task Considerations

- **Task 2.3 (Read Tool)**: When implementing ReadTool enhancements, share `PathGuardrail` with ListTool
- **Task 2.4 (Write Tool)**: Will also need `PathGuardrail` + overwrite protection guardrail
- **Task 3.2 (Tool Call Processing)**: The tool dispatcher will eventually need to call guardrails before `execute()`

### 8.3 Documentation Updates

- Update `analysis/architecture.md` tool list to reflect ListTool as implemented
- Update `CLAUDE.md` Current State section to include ListTool
- No OpenAPI spec needed (tools use Ollama function schema, not HTTP API)

---

## 9. Summary of Design Decisions

1. **Tool name**: `"list"` - Simple, unambiguous, matches common CLI tools
2. **Default max_depth=1**: Non-recursive by default for safety; LLM can request deeper recursion explicitly
3. **Glob patterns over regex**: `fnmatch` is safer, more intuitive for LLMs, and sufficient for file filtering
4. **Tree-formatted output**: Human-readable for LLM context windows; directories marked with `/`
5. **Self-enforced limits**: Tools clamp their own parameters; guardrails focus on security (path restrictions)
6. **Shared PathGuardrail**: All filesystem tools will use the same path validation logic
7. **File-as-path handling**: If `path` points to a file, return it as a single entry instead of erroring
8. **Absolute maximums**: Hard caps (`ABSOLUTE_MAX_DEPTH=10`, `ABSOLUTE_MAX_ENTRIES=5000`) prevent abuse even if config is missing
9. **Consistent with ReadTool**: Same error patterns, same `ToolResult` usage, same property-based schema
