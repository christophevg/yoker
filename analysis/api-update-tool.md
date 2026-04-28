# API Analysis: Update Tool (Task 2.5)

**Document Version**: 1.0
**Date**: 2026-04-28
**Task**: 2.5 Update Tool from TODO.md
**Status**: API Design Complete

## Summary

This document designs the API for the `UpdateTool` class, which provides precise file editing operations (replace, insert, delete) for the Yoker agent harness. The design follows the exact patterns established by `ReadTool`, `WriteTool`, and `ListTool` for consistency, integrates with the existing `PathGuardrail` and `Config` infrastructure, and adds update-specific guardrails for exact match validation and diff size limits.

---

## 1. UpdateTool Class Design

### 1.1 Class Definition

```python
# src/yoker/tools/update.py

"""Update tool implementation for Yoker.

Provides the UpdateTool for precise file editing with four operations:
replace, insert_before, insert_after, and delete. Supports exact match
validation, diff size limits, and line-based operations with defense-in-depth
guardrail validation.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoker.config.schema import Config
from yoker.logging import get_logger
from yoker.tools.base import Tool, ToolResult

if TYPE_CHECKING:
  from yoker.tools.guardrails import Guardrail

log = get_logger(__name__)


class UpdateTool(Tool):
  """Tool for editing existing files with precise operations.

  Supports four edit operations on text files:
  - replace: Replace matched text with replacement text
  - insert_before: Insert text before a matched line
  - insert_after: Insert text after a matched line
  - delete: Remove matched text

  When a guardrail is provided, validates parameters before editing.
  Resolves paths with realpath, rejects symlinks, and enforces
  exact match requirements and diff size limits from configuration.

  Error messages returned to the LLM are sanitized to avoid leaking
  filesystem structure. Full paths are logged internally for debugging.
  """

  def __init__(
    self,
    guardrail: "Guardrail | None" = None,
    config: Config | None = None,
  ) -> None:
    """Initialize UpdateTool with optional guardrail and config.

    Args:
      guardrail: Optional guardrail for parameter validation.
      config: Optional config for exact match and diff size settings.
        If not provided, defaults to Config().
    """
    super().__init__(guardrail=guardrail)
    self._config = config or Config()

  @property
  def name(self) -> str:
    return "update"

  @property
  def description(self) -> str:
    return (
      "Edit an existing file with precise operations. "
      "Supports: replace (swap text), insert_before, insert_after, "
      "and delete (remove text). Requires exact match by default."
    )

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the update tool.

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
              "description": "Path to the file to update",
            },
            "operation": {
              "type": "string",
              "enum": ["replace", "insert_before", "insert_after", "delete"],
              "description": (
                "The edit operation to perform: "
                "replace (swap text), insert_before/insert_after "
                "(add lines around match), delete (remove matched text)"
              ),
            },
            "old_string": {
              "type": "string",
              "description": (
                "The exact text to search for. "
                "Must match exactly when require_exact_match is true. "
                "Required for replace and delete operations."
              ),
            },
            "new_string": {
              "type": "string",
              "description": (
                "The new text to insert or replace with. "
                "Required for replace, insert_before, and insert_after. "
                "Not used for delete."
              ),
            },
            "line_number": {
              "type": "integer",
              "description": (
                "1-indexed line number for insert_before, insert_after, "
                "and line-based delete operations."
              ),
            },
          },
          "required": ["path", "operation"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Execute a file edit operation.

    Steps:
      1. Validate parameters via guardrail if provided.
      2. Extract and validate path, operation, old_string, and new_string.
      3. Resolve the path with os.path.realpath().
      4. Reject symlinks unless explicitly allowed.
      5. Verify the file exists.
      6. Read file content with UTF-8 encoding.
      7. Validate exact match if configured.
      8. Validate diff size limits.
      9. Perform the requested operation.
      10. Write modified content back to file.
      11. Log update for audit trail.

    Args:
      **kwargs: Must contain 'path' and 'operation'.
        May contain 'old_string', 'new_string', 'line_number'.

    Returns:
      ToolResult with success message or error message.
    """
    ...
```

### 1.2 Parameter Design

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Path to the file to update |
| `operation` | string | Yes | One of: `replace`, `insert_before`, `insert_after`, `delete` |
| `old_string` | string | Conditional | Text to search for (required for replace and content-based delete) |
| `new_string` | string | Conditional | New text for replace/insert operations |
| `line_number` | integer | Conditional | 1-indexed line number for insert and line-based delete |

**Operation semantics**:

| Operation | Behavior | Requires `old_string` | Requires `new_string` | Requires `line_number` |
|-----------|----------|----------------------|-----------------------|------------------------|
| `replace` | Find `old_string` text, replace with `new_string` | Yes | Yes | No |
| `insert_before` | Insert `new_string` before `line_number` | No | Yes | Yes |
| `insert_after` | Insert `new_string` after `line_number` | No | Yes | Yes |
| `delete` | Remove `old_string` text or delete `line_number` line | Yes* | No | Yes* |

*Delete requires either `old_string` or `line_number`.

**old_string semantics**:
- By default, `search` must match exactly (configurable via `require_exact_match`)
- For `insert_before`/`insert_after`, `search` matches a complete line
- For `replace`/`delete`, `search` matches any substring or full line
- If multiple matches exist, the first match is used (documented behavior)
- Empty `search` string is rejected with error

**Replacement semantics**:
- For `replace`: the matched `search` text is replaced entirely with `replacement`
- For `insert_before`/`insert_after`: `replacement` is inserted as a new line (or lines if multiline)
- For `delete`: `replacement` is ignored
- Empty `replacement` is valid (useful for clearing content in replace operations)

---

## 2. Operation Implementation Details

### 2.1 Content-Based vs Line-Based Operations

**Design decision**: Use **content-based search** for `replace` and `delete`, and **line-based search** for `insert_before` and `insert_after`.

| Operation | Search Target | Match Behavior |
|-----------|---------------|----------------|
| `replace` | File content (multiline string) | First exact occurrence of `search` substring |
| `delete` | File content (multiline string) | First exact occurrence of `search` substring |
| `insert_before` | Individual lines | First line that equals `search` (after stripping) |
| `insert_after` | Individual lines | First line that equals `search` (after stripping) |

**Rationale**:
- Content-based replace/delete allow editing within lines (e.g., changing a variable name)
- Line-based insert operations are safer and more predictable for adding new lines
- This matches how LLMs naturally think about edits ("change this word" vs "add a line after this one")

### 2.2 Exact Match Validation

When `require_exact_match=True` (default from config):

1. **For replace/delete**: `search` must appear verbatim in the file content
2. **For insert operations**: `search` must match a complete line (after stripping whitespace)
3. If no match is found: return `ToolResult(success=False, error="Search text not found")`
4. If multiple matches exist: operate on the first match, log a warning

When `require_exact_match=False` (not recommended, but configurable):
- Future enhancement: could support substring fuzzy matching or regex
- MVP: still require exact match, just log the configuration override

**Match uniqueness check** (MVP: first match only):
```python
if file_content.count(search) > 1:
  log.warning("update_multiple_matches", path=path, count=file_content.count(search))
  # Still proceed with first match, but log for audit trail
```

### 2.3 Diff Size Limits

The `max_diff_size_kb` config setting limits the size of changes:

1. Calculate the diff size as `len(replacement.encode("utf-8"))` (for replace/insert)
2. For `delete`, diff size is `len(search.encode("utf-8"))`
3. If diff size exceeds `max_diff_size_kb * 1024`: return error

**Rationale**: Prevents the LLM from accidentally making massive changes that are hard to review or revert. Encourages incremental, precise edits.

### 2.4 Line Count Tracking

The result reports `lines_modified`, which counts:
- `replace`: net change in line count (can be negative, zero, or positive)
- `insert_before`/`insert_after`: number of lines inserted (1 or more)
- `delete`: number of lines removed (0 or more, depending on whether search spans lines)

---

## 3. Return Format Design

### 3.1 Success Response

On success, returns a structured text result showing the diff preview:

```
Update successful: 3 lines modified

--- original
+++ updated
@@ -10,12 +10,12 @@
     old_text_here
-    removed_line
+    new_replacement_line
     context_after
```

**Formatting rules**:
- First line: `Update successful: {N} lines modified`
- Unified diff-style preview (±3 lines of context around the change)
- Diff preview limited to reasonable size (e.g., 20 lines max) to avoid flooding LLM context
- If the change is small, show the full replacement text

**ToolResult**:
```python
ToolResult(
  success=True,
  result="Update successful: 3 lines modified\n\n--- original\n+++ updated\n...",
)
```

### 3.2 Error Responses

| Error | Condition | Response |
|-------|-----------|----------|
| Missing parameter | `path`, `operation`, or `search` missing | `Missing required parameter: {name}` |
| Invalid operation | `operation` not in enum | `Invalid operation: {value}. Must be one of: replace, insert_before, insert_after, delete` |
| Missing replacement | replace/insert without `replacement` | `Missing required parameter: replacement for {operation}` |
| File not found | Path does not exist | `File not found` |
| Not a file | Path is a directory | `Path is not a file` |
| Search not found | `search` text not in file | `Search text not found` |
| Exact match failed | `search` has no exact match | `Search text not found` |
| Diff too large | Diff size exceeds `max_diff_size_kb` | `Diff size exceeds limit: {size}KB > {limit}KB` |
| Permission denied | `PermissionError` on read/write | `Permission denied` |
| Generic error | Any other exception | `Error updating file` |

**ToolResult for errors**:
```python
ToolResult(success=False, result="", error="Search text not found")
```

---

## 4. Guardrail Integration Design

### 4.1 PathGuardrail Integration

`UpdateTool` follows the same pattern as `ReadTool` and `WriteTool`:

```python
# In UpdateTool.execute()
if self._guardrail is not None:
  validation = self._guardrail.validate(self.name, kwargs)
  if not validation.valid:
    log.info("update_guardrail_blocked", path=path_str, reason=validation.reason)
    return ToolResult(success=False, result="", error=validation.reason)
```

The existing `PathGuardrail` already supports `update` (see `_FILESYSTEM_TOOLS` in `path_guardrail.py`). It validates:
1. Path is within allowed directories
2. Path is not blocked by regex patterns
3. File size limits (if applicable)

**Note**: `PathGuardrail` does not currently have update-specific checks (like exact match or diff size). These are handled internally by `UpdateTool` using the `Config` object.

### 4.2 Config-Based Guardrails

`UpdateTool` accepts a `Config` object to access `UpdateToolConfig`:

```python
update_config = self._config.tools.update
require_exact_match = update_config.require_exact_match  # bool, default True
max_diff_size_kb = update_config.max_diff_size_kb        # int, default 100
```

These are **operational limits** (not security guardrails), following the same pattern as `WriteTool`'s `allow_overwrite` and `max_size_kb`.

### 4.3 Validation Flow

```
LLM calls: update(path="src/main.py", operation="replace", search="old_var", replacement="new_var")
              |
              v
  PathGuardrail.validate("update", kwargs)
    - Is path in allowed_paths? -> Yes
    - Is path blocked? -> No
              |
              v
  UpdateTool.execute()
    - Validate operation is valid enum -> Yes
    - Validate search is non-empty -> Yes
    - Validate replacement provided for replace -> Yes
    - Resolve path -> /workspace/src/main.py
    - Check file exists -> Yes
    - Read file content
    - Check exact match -> Found "old_var"
    - Check diff size -> 7 bytes < 100KB limit
    - Perform replacement
    - Write file
    - Return diff preview
```

---

## 5. Ollama Function Schema

The complete schema returned by `get_schema()`:

```json
{
  "type": "function",
  "function": {
    "name": "update",
    "description": "Edit an existing file with precise operations. Supports: replace (swap text), insert_before, insert_after, and delete (remove text). Requires exact match by default.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Path to the file to update"
        },
        "operation": {
          "type": "string",
          "enum": ["replace", "insert_before", "insert_after", "delete"],
          "description": "The edit operation to perform: replace (swap text), insert_before/insert_after (add lines around match), delete (remove matched text)"
        },
        "search": {
          "type": "string",
          "description": "The exact text or line to search for. Must match exactly when require_exact_match is true."
        },
        "replacement": {
          "type": "string",
          "description": "The new text to insert or replace with. Required for replace, insert_before, and insert_after. Not used for delete."
        }
      },
      "required": ["path", "operation", "search"]
    }
  }
}
```

**Design notes**:
- `enum` constraint helps the LLM generate valid operation names
- `replacement` is not in `required` because `delete` does not need it
- Descriptions explicitly mention which operations need `replacement`
- The description emphasizes "exact match" to guide LLM behavior

---

## 6. Comparison with Existing Tools

### 6.1 Consistency Analysis

| Aspect | ReadTool | WriteTool | ListTool | UpdateTool | Consistent? |
|--------|--------|-----------|----------|------------|-------------|
| Base class | `Tool` | `Tool` | `Tool` | `Tool` | Yes |
| Property pattern | `@property name`, `@property description` | Same | Same | Same | Yes |
| Schema format | OpenAI function-calling | Same | Same | Same | Yes |
| Error handling | Try/except with sanitized messages | Same | Same | Same | Yes |
| Return type | `ToolResult` | Same | Same | Same | Yes |
| Guardrail param | `guardrail: Guardrail \| None` | Same | Same | Same | Yes |
| Config param | No | Yes (`Config`) | No | Yes (`Config`) | Follows WriteTool pattern |
| Symlink rejection | Yes | Yes | Yes (in walk) | Yes | Yes |
| Path resolution | `os.path.realpath()` | Same | `Path(path_str)` | `os.path.realpath()` | Yes |

### 6.2 Key Differences

| Aspect | ReadTool | WriteTool | UpdateTool |
|--------|----------|-----------|------------|
| Parameters | `path` | `path`, `content`, `create_parents` | `path`, `operation`, `search`, `replacement` |
| Config usage | None | `allow_overwrite`, `max_size_kb` | `require_exact_match`, `max_diff_size_kb` |
| File must exist | Yes | No (creates new) | Yes |
| Output | Raw file content | Success message | Diff preview with line count |
| Validation | Path, existence | Path, overwrite, size | Path, exact match, diff size, operation |

---

## 7. Implementation Sketch

### 7.1 Core execute Logic

```python
  def execute(self, **kwargs: Any) -> ToolResult:
    path_str = kwargs.get("path", "")
    operation = kwargs.get("operation", "")
    search = kwargs.get("search", "")
    replacement = kwargs.get("replacement", "")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        log.info("update_guardrail_blocked", path=path_str, reason=validation.reason)
        return ToolResult(success=False, result="", error=validation.reason)

    # Validate required parameters
    if not isinstance(path_str, str) or not path_str.strip():
      return ToolResult(success=False, result="", error="Invalid path parameter")

    if not isinstance(operation, str) or operation not in (
      "replace", "insert_before", "insert_after", "delete"
    ):
      return ToolResult(success=False, result="", error=f"Invalid operation: {operation}")

    if not isinstance(search, str):
      return ToolResult(success=False, result="", error="Invalid search parameter")

    if operation != "delete":
      if not isinstance(replacement, str):
        return ToolResult(success=False, result="", error="Invalid replacement parameter")

    # Reject symlinks
    original_path = Path(path_str)
    if original_path.is_symlink():
      return ToolResult(success=False, result="", error="Updating symlinks is not permitted")

    # Resolve path
    try:
      resolved = Path(os.path.realpath(path_str))
    except (OSError, ValueError):
      return ToolResult(success=False, result="", error="Invalid path")

    # Verify file exists
    if not resolved.exists():
      return ToolResult(success=False, result="", error="File not found")
    if not resolved.is_file():
      return ToolResult(success=False, result="", error="Path is not a file")

    # Read file content
    try:
      content = resolved.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
      return ToolResult(success=False, result="", error="Permission denied")
    except OSError:
      return ToolResult(success=False, result="", error="Error reading file")

    # Validate exact match
    update_config = self._config.tools.update
    require_exact = update_config.require_exact_match

    if require_exact and search not in content:
      if operation in ("insert_before", "insert_after"):
        # For line-based ops, check if any line matches exactly
        lines = content.splitlines()
        if not any(line.strip() == search.strip() for line in lines):
          return ToolResult(success=False, result="", error="Search text not found")
      else:
        return ToolResult(success=False, result="", error="Search text not found")

    # Validate diff size
    max_diff_kb = update_config.max_diff_size_kb
    if max_diff_kb > 0:
      if operation == "delete":
        diff_size = len(search.encode("utf-8"))
      else:
        diff_size = len(replacement.encode("utf-8"))
      if diff_size > max_diff_kb * 1024:
        return ToolResult(
          success=False,
          result="",
          error=f"Diff size exceeds limit: {diff_size / 1024:.1f}KB > {max_diff_kb}KB",
        )

    # Perform operation
    try:
      original_lines = content.splitlines(keepends=True)
      modified_content, lines_modified = self._apply_operation(
        content, original_lines, operation, search, replacement
      )
    except ValueError as e:
      return ToolResult(success=False, result="", error=str(e))

    # Write modified content
    try:
      resolved.write_text(modified_content, encoding="utf-8")
      log.info(
        "update_success",
        path=str(resolved),
        operation=operation,
        lines_modified=lines_modified,
      )

      # Build diff preview
      diff_preview = self._build_diff_preview(content, modified_content, search)
      result_text = f"Update successful: {lines_modified} lines modified\n\n{diff_preview}"
      return ToolResult(success=True, result=result_text)

    except PermissionError:
      return ToolResult(success=False, result="", error="Permission denied")
    except OSError:
      return ToolResult(success=False, result="", error="Error writing file")

  def _apply_operation(
    self,
    content: str,
    original_lines: list[str],
    operation: str,
    search: str,
    replacement: str,
  ) -> tuple[str, int]:
    """Apply the edit operation to content.

    Returns:
      Tuple of (modified_content, lines_modified).
    """
    if operation == "replace":
      if search not in content:
        raise ValueError("Search text not found")
      modified = content.replace(search, replacement, 1)
      original_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
      modified_count = modified.count("\n") + (1 if modified and not modified.endswith("\n") else 0)
      return modified, modified_count - original_count

    elif operation == "delete":
      if search not in content:
        raise ValueError("Search text not found")
      modified = content.replace(search, "", 1)
      original_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
      modified_count = modified.count("\n") + (1 if modified and not modified.endswith("\n") else 0)
      return modified, modified_count - original_count

    elif operation in ("insert_before", "insert_after"):
      lines = content.splitlines(keepends=True)
      found = False
      result_lines: list[str] = []
      lines_modified = 0

      for line in lines:
        if not found and line.strip() == search.strip():
          found = True
          if operation == "insert_before":
            result_lines.append(replacement + "\n")
            lines_modified += replacement.count("\n") + 1
          result_lines.append(line)
          if operation == "insert_after":
            result_lines.append(replacement + "\n")
            lines_modified += replacement.count("\n") + 1
        else:
          result_lines.append(line)

      if not found:
        raise ValueError("Search text not found")

      return "".join(result_lines), lines_modified

    else:
      raise ValueError(f"Invalid operation: {operation}")

  def _build_diff_preview(
    self,
    original: str,
    modified: str,
    search: str,
    context_lines: int = 3,
  ) -> str:
    """Build a unified diff preview around the change.

    Returns:
      Diff preview string with context lines.
    """
    original_lines = original.splitlines()
    modified_lines = modified.splitlines()

    # Find the changed line region
    # Simple approach: find search context in original
    try:
      match_idx = original_lines.index(search.strip())
    except ValueError:
      # Fallback: find first differing line
      match_idx = 0
      for i, (o, m) in enumerate(zip(original_lines, modified_lines)):
        if o != m:
          match_idx = i
          break

    start = max(0, match_idx - context_lines)
    end = min(len(original_lines), match_idx + context_lines + 1)

    preview_lines: list[str] = ["--- original", "+++ updated"]
    for i in range(start, end):
      if i < len(original_lines):
        preview_lines.append(f" {original_lines[i]}")

    return "\n".join(preview_lines)
```

### 7.2 Package Registration

Update `src/yoker/tools/__init__.py`:

```python
from .update import UpdateTool

__all__ = [
  # ... existing exports ...
  "UpdateTool",
]

def create_default_registry() -> ToolRegistry:
  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(WriteTool())
  registry.register(UpdateTool())  # Add this
  return registry
```

---

## 8. Test Design

### 8.1 Test File Location

`tests/test_tools/test_update.py`

### 8.2 Test Cases

| Test | Input | Expected Result |
|------|-------|-----------------|
| Replace text | `operation="replace"`, `search="old"`, `replacement="new"` | File updated, diff preview returned |
| Insert before | `operation="insert_before"`, `search="line2"`, `replacement="new_line"` | Line inserted before matching line |
| Insert after | `operation="insert_after"`, `search="line2"`, `replacement="new_line"` | Line inserted after matching line |
| Delete text | `operation="delete"`, `search="remove_this"` | Text removed, no replacement needed |
| Exact match not found | `search="nonexistent"` | `success=False`, "Search text not found" |
| Missing replacement | `operation="replace"`, no `replacement` | `success=False`, "Missing replacement" |
| Invalid operation | `operation="invalid"` | `success=False`, "Invalid operation" |
| File not found | `path="/nonexistent"` | `success=False`, "File not found" |
| Path is directory | `path="/tmp"` | `success=False`, "Path is not a file" |
| Diff too large | replacement > max_diff_size_kb | `success=False`, "Diff size exceeds limit" |
| Symlink rejection | path is symlink | `success=False`, "Updating symlinks is not permitted" |
| Permission denied | Mock `PermissionError` | `success=False`, "Permission denied" |
| Multiline replacement | replacement contains newlines | Correct line count, proper insertion |
| Empty search | `search=""` | `success=False`, "Search text cannot be empty" |
| Multiple matches | search appears multiple times | First match replaced, warning logged |
| Guardrail blocks | PathGuardrail returns invalid | `success=False`, guardrail reason returned |

### 8.3 Fixtures

```python
import pytest
from pathlib import Path


@pytest.fixture
def temp_file(tmp_path: Path) -> Path:
  """Create a temporary file with known content."""
  file_path = tmp_path / "test.txt"
  content = "line1\nline2\nline3\nold_text here\nline5\n"
  file_path.write_text(content, encoding="utf-8")
  return file_path


@pytest.fixture
def update_tool(mock_config: Config) -> UpdateTool:
  """Create an UpdateTool with test configuration."""
  return UpdateTool(config=mock_config)
```

---

## 9. PathGuardrail Updates

### 9.1 Current State

`PathGuardrail` in `src/yoker/tools/path_guardrail.py` already includes `"update"` in `_FILESYSTEM_TOOLS` (line 27) and maps `"update"` to `tools.update` in `_get_tool_config()` (line 313). However, it does not implement update-specific validation beyond path checks.

### 9.2 Recommended Enhancements

Add update-specific checks to `PathGuardrail.validate()`:

```python
# After write-specific checks, add:
# Update-specific checks
if tool_name == "update":
  # Check if file exists (updates require existing files)
  if not resolved.exists():
    return ValidationResult(valid=False, reason=f"File not found: {path_param}")

  # Check if path is a file (not directory)
  if resolved.exists() and not resolved.is_file():
    return ValidationResult(valid=False, reason=f"Path is not a file: {path_param}")
```

**Note**: File existence check for update is important because:
- `WriteTool` creates files, so non-existence is fine
- `UpdateTool` edits files, so non-existence is an error
- This check is already done in `UpdateTool.execute()`, but adding it to the guardrail provides defense-in-depth

---

## 10. Action Items

### 10.1 Implementation Tasks

| Priority | Task | File(s) |
|----------|------|---------|
| High | Create `UpdateTool` class | `src/yoker/tools/update.py` |
| High | Register `UpdateTool` in package exports | `src/yoker/tools/__init__.py` |
| High | Add `UpdateTool` to default registry | `src/yoker/tools/__init__.py` |
| Medium | Add update-specific checks to `PathGuardrail` | `src/yoker/tools/path_guardrail.py` |
| Medium | Write unit tests | `tests/test_tools/test_update.py` |
| Low | Add `tests/test_tools/__init__.py` if missing | `tests/test_tools/__init__.py` |

### 10.2 Cross-Task Considerations

- **Task 2.6 (Search Tool)**: Search results may feed into `UpdateTool` operations (e.g., find then replace)
- **Task 3.2 (Tool Call Processing)**: The tool dispatcher must route `update` calls to `UpdateTool`
- **Config validation**: `config.validator.validate_config()` already validates `tools.update.max_diff_size_kb`

### 10.3 Documentation Updates

- Update `analysis/architecture.md` tool list to reflect UpdateTool as implemented
- Update `CLAUDE.md` Current State section to include UpdateTool
- No OpenAPI spec needed (tools use Ollama function schema, not HTTP API)

---

## 11. Summary of Design Decisions

1. **Four operations**: `replace`, `insert_before`, `insert_after`, `delete` - covers all common editing needs
2. **Content-based replace/delete, line-based insert**: Allows both in-line edits and structured line additions
3. **Exact match by default**: Prevents accidental partial replacements; configurable via `require_exact_match`
4. **First match only**: Simple, predictable behavior; logs warning if multiple matches exist
5. **Diff size limits**: Encourages incremental changes; configurable via `max_diff_size_kb`
6. **Config injection**: Follows `WriteTool` pattern for accessing tool-specific settings
7. **Unified diff preview**: Familiar format for reviewing changes; limited context to avoid flooding
8. **Shared PathGuardrail**: Reuses existing path validation; adds update-specific existence checks
9. **Sanitized errors**: Follows existing tool pattern - no filesystem structure leakage
10. **Consistent with existing tools**: Same class structure, property pattern, error handling, logging
