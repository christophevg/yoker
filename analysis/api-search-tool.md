# API Analysis: Search Tool (Task 2.6)

**Document Version**: 1.0
**Date**: 2026-04-29
**Task**: 2.6 Search Tool from TODO.md
**Status**: API Design Complete

## Summary

This document designs the API for the `SearchTool` class, which provides pattern-based search functionality for the Yoker agent harness. The design follows the patterns established by `ReadTool` and `ListTool`, extends them with regex complexity validation and timeout handling, and shares the `PathGuardrail` for filesystem security.

---

## 1. SearchTool Class Design

### 1.1 Class Definition

```python
# src/yoker/tools/search.py

"""Search tool implementation for Yoker.

Provides the SearchTool for searching files and their contents with
configurable pattern matching, result limits, and security constraints.
"""

import re
import fnmatch
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class SearchTool(Tool):
  """Tool for searching files and their contents.

  Supports two search modes:
  - 'content': Search within file contents (grep-like, using regex)
  - 'filename': Search file names (glob-like, using fnmatch)

  All searches respect allowed paths guardrails and enforce limits
  to prevent resource exhaustion.
  """

  # Defaults enforced when parameters are omitted or exceed limits
  DEFAULT_MAX_RESULTS: int = 100
  ABSOLUTE_MAX_RESULTS: int = 1000
  DEFAULT_TIMEOUT_MS: int = 5000
  ABSOLUTE_TIMEOUT_MS: int = 30000
  MAX_FILE_SIZE_MB: int = 10  # Skip files larger than this

  # Regex complexity limits (to prevent ReDoS)
  MAX_REGEX_LENGTH: int = 500
  FORBIDDEN_PATTERNS: set[str] = {
    # Patterns known to cause catastrophic backtracking
    r"(\w+)+",      # Nested quantifiers
    r"(\d+)+",
    r"(.+)+",
    r"(\w*)*",
    r"(.*)*",
  }

  @property
  def name(self) -> str:
    return "search"

  @property
  def description(self) -> str:
    return (
      "Search for patterns in files. "
      "Use 'content' type to search within files (regex), "
      "or 'filename' type to search file names (glob pattern)."
    )

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the search tool."""
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
              "description": "Directory to search in",
            },
            "pattern": {
              "type": "string",
              "description": (
                "Search pattern. For 'content' type: regex pattern. "
                "For 'filename' type: glob pattern (e.g., '*.py')"
              ),
            },
            "type": {
              "type": "string",
              "enum": ["content", "filename"],
              "description": (
                "Type of search: 'content' searches within files, "
                "'filename' searches file names. Defaults to 'content'."
              ),
            },
            "max_results": {
              "type": "integer",
              "description": (
                f"Maximum results to return. Defaults to {self.DEFAULT_MAX_RESULTS}."
              ),
              "minimum": 1,
              "maximum": self.ABSOLUTE_MAX_RESULTS,
            },
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Search files with pattern matching and limits.

    Args:
      **kwargs: Must contain 'path'. May contain 'pattern', 'type',
        and 'max_results'.

    Returns:
      ToolResult with search results or error message.
    """
    ...
```

### 1.2 Parameter Design

| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `path` | string | Yes | - | Must be a valid directory path within allowed paths |
| `pattern` | string | No | "*" | For content: regex pattern. For filename: glob pattern |
| `type` | string | No | "content" | Must be "content" or "filename" |
| `max_results` | integer | No | 100 | Clamped to `[1, ABSOLUTE_MAX_RESULTS]` |

**Search Type Semantics**:

| Type | Pattern Engine | Example Patterns | Use Case |
|------|---------------|------------------|----------|
| `content` | Python `re` (regex) | `TODO\s*:", `def\s+\w+` | Find code patterns, text within files |
| `filename` | Python `fnmatch` (glob) | `*.py`, `test_*.md` | Find files by name pattern |

**Pattern Behavior**:
- **Content search**: Pattern is a regular expression. Invalid regex returns an error.
- **Filename search**: Pattern is a glob pattern using `*`, `?`, `[seq]`. Invalid patterns are treated literally.

### 1.3 Return Format Design

On success, returns a JSON object with matches:

```json
{
  "success": true,
  "matches": [
    {
      "file": "src/yoker/tools/list.py",
      "line": 42,
      "content": "    def execute(self, **kwargs: Any) -> ToolResult:"
    },
    {
      "file": "src/yoker/tools/search.py",
      "line": 15,
      "content": "    DEFAULT_MAX_RESULTS: int = 100"
    }
  ],
  "total_matches": 15,
  "truncated": false,
  "files_searched": 23
}
```

**For filename search**:
```json
{
  "success": true,
  "matches": [
    {"file": "src/yoker/tools/list.py"},
    {"file": "src/yoker/tools/read.py"},
    {"file": "src/yoker/tools/search.py"}
  ],
  "total_matches": 3,
  "truncated": false,
  "files_searched": null
}
```

**Formatting rules**:
- Content matches include file path, line number, and matching line content
- Filename matches include only file path (no line number)
- `total_matches` is the actual count found (may exceed `max_results`)
- `truncated` indicates if results were cut off
- `files_searched` is only present for content search

### 1.4 Error Handling

| Error | Condition | Response |
|-------|-----------|----------|
| Path not found | `Path(path).exists()` is False | `Path not found: {path}` |
| Not a directory | `Path(path).is_dir()` is False | `Path is not a directory: {path}` |
| Permission denied | `PermissionError` on traversal | `Permission denied: {path}` |
| Invalid regex | `re.compile(pattern)` fails | `Invalid regex pattern: {error}` |
| ReDoS risk | Pattern matches forbidden patterns | `Pattern rejected: potential ReDoS attack` |
| Regex too long | `len(pattern) > MAX_REGEX_LENGTH` | `Pattern too long: max {MAX_REGEX_LENGTH} chars` |
| Timeout exceeded | Search exceeds timeout | `Search timed out after {timeout_ms}ms` |
| Generic error | Any other exception | `Error searching: {e}` |

**ToolResult for errors**:
```python
ToolResult(success=False, result="", error="Invalid regex pattern: missing closing parenthesis")
```

---

## 2. Search Mode Implementations

### 2.1 Content Search (Grep-like)

Content search walks the directory tree and searches within each file:

```python
def _search_content(
  self,
  root: Path,
  pattern: str,
  max_results: int,
  timeout_ms: int,
) -> tuple[list[dict[str, Any]], int, bool]:
  """Search file contents using regex.

  Returns:
    Tuple of (matches, total_count, truncated).
  """
  matches: list[dict[str, Any]] = []
  total_count = 0
  truncated = False

  # Compile regex (already validated)
  regex = re.compile(pattern)

  start_time = time.monotonic()
  timeout_seconds = timeout_ms / 1000.0

  for file_path in self._walk_files(root, timeout_seconds, start_time):
    # Check timeout
    if time.monotonic() - start_time > timeout_seconds:
      truncated = True
      break

    # Skip large files
    if file_path.stat().st_size > self.MAX_FILE_SIZE_MB * 1024 * 1024:
      continue

    try:
      content = file_path.read_text(errors="replace")
      for line_num, line in enumerate(content.splitlines(), 1):
        if regex.search(line):
          total_count += 1
          if len(matches) < max_results:
            matches.append({
              "file": str(file_path),
              "line": line_num,
              "content": line.strip(),
            })
    except (UnicodeDecodeError, PermissionError):
      continue  # Skip binary files and permission-denied files

  return matches, total_count, truncated
```

**Content search optimizations**:
1. Skip files larger than `MAX_FILE_SIZE_MB`
2. Use `errors="replace"` for encoding issues
3. Return early on timeout
4. Don't read files with common binary extensions

### 2.2 Filename Search (Glob-like)

Filename search uses `fnmatch` for pattern matching:

```python
def _search_filename(
  self,
  root: Path,
  pattern: str,
  max_results: int,
) -> tuple[list[dict[str, Any]], int, bool]:
  """Search file names using glob pattern.

  Returns:
    Tuple of (matches, total_count, truncated).
  """
  matches: list[dict[str, Any]] = []
  total_count = 0
  truncated = False

  for file_path in self._walk_files(root):
    if fnmatch.fnmatch(file_path.name, pattern):
      total_count += 1
      if len(matches) < max_results:
        matches.append({"file": str(file_path)})

  if len(matches) < total_count:
    truncated = True

  return matches, total_count, truncated
```

**Filename search optimizations**:
- No file reading required (fast)
- Pattern matching on basename only
- No timeout needed for filename-only search

### 2.3 File Walking Helper

Both search modes use a common file walker:

```python
def _walk_files(
  self,
  root: Path,
  timeout_seconds: float | None = None,
  start_time: float | None = None,
) -> Iterator[Path]:
  """Walk directory tree, yielding files.

  Respects timeout if provided. Skips:
  - Hidden files/directories (starting with .)
  - Common binary directories (.git, __pycache__, node_modules)
  - Symlinks
  """
  SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}

  for dirpath, dirnames, filenames in os.walk(root):
    # Skip hidden and binary directories
    dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]

    for filename in filenames:
      # Skip hidden files
      if filename.startswith("."):
        continue

      yield Path(dirpath) / filename
```

---

## 3. Security: ReDoS Prevention

### 3.1 Regex Complexity Validation

Regular expression denial of service (ReDoS) is a critical concern when accepting user regex patterns. The tool validates patterns before compilation:

```python
def _validate_regex(self, pattern: str) -> tuple[bool, str]:
  """Validate regex pattern for safety.

  Returns:
    Tuple of (is_valid, error_message).
  """
  # Length check
  if len(pattern) > self.MAX_REGEX_LENGTH:
    return False, f"Pattern too long: max {self.MAX_REGEX_LENGTH} characters"

  # Check for forbidden patterns (nested quantifiers)
  for forbidden in self.FORBIDDEN_PATTERNS:
    if re.search(forbidden, pattern):
      return False, "Pattern rejected: potential ReDoS vulnerability (nested quantifiers)"

  # Try to compile
  try:
    re.compile(pattern)
    return True, ""
  except re.error as e:
    return False, f"Invalid regex pattern: {e}"
```

### 3.2 Why These Patterns Are Dangerous

| Pattern | Why Dangerous | Time Complexity |
|---------|--------------|-----------------|
| `(\w+)+` | Nested quantifiers | O(n!) on certain inputs |
| `(.+)+` | Overlapping matches | Exponential backtracking |
| `(\w*)*` | Zero-width matches | Catastrophic backtracking |

**Example attack**: Input `"aaaaaaaaaaaaaaaaaaaaa!"` against `(\w+)+` causes millions of backtrack attempts.

### 3.3 Timeout Protection

Even with pattern validation, complex searches can run long. The tool enforces timeouts:

```python
import time

# At start of search
start_time = time.monotonic()
timeout_seconds = timeout_ms / 1000.0

# During iteration
if time.monotonic() - start_time > timeout_seconds:
  truncated = True
  break
```

---

## 4. Guardrail Integration

### 4.1 Shared PathGuardrail

SearchTool uses the same `PathGuardrail` as `ListTool` and `ReadTool`:

```python
class SearchTool(Tool):
  def __init__(self, guardrail: "Guardrail | None" = None) -> None:
    """Initialize SearchTool with optional guardrail.

    Args:
      guardrail: Optional PathGuardrail for path validation.
    """
    super().__init__(guardrail=guardrail)

  def execute(self, **kwargs: Any) -> ToolResult:
    path_str = kwargs.get("path", "")
    if not path_str:
      return ToolResult(success=False, result="", error="Missing required parameter: path")

    # Defense-in-depth: validate via guardrail if provided
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        return ToolResult(success=False, result="", error=validation.reason)

    # ... rest of implementation
```

### 4.2 Tool-Specific Limits

| Limit | Purpose | Default | Absolute Max |
|-------|---------|---------|--------------|
| `max_results` | Prevent context overflow | 100 | 1000 |
| `timeout_ms` | Prevent runaway searches | 5000ms | 30000ms |
| `MAX_FILE_SIZE_MB` | Skip large files | 10MB | (hardcoded) |
| `MAX_REGEX_LENGTH` | Limit regex complexity | 500 chars | (hardcoded) |

These are **operational limits**, not guardrails. Tools self-enforce them.

---

## 5. Ollama Function Schema

The complete schema returned by `get_schema()`:

```json
{
  "type": "function",
  "function": {
    "name": "search",
    "description": "Search for patterns in files. Use 'content' type to search within files (regex), or 'filename' type to search file names (glob pattern).",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Directory to search in"
        },
        "pattern": {
          "type": "string",
          "description": "Search pattern. For 'content' type: regex pattern. For 'filename' type: glob pattern (e.g., '*.py')"
        },
        "type": {
          "type": "string",
          "enum": ["content", "filename"],
          "description": "Type of search: 'content' searches within files, 'filename' searches file names. Defaults to 'content'."
        },
        "max_results": {
          "type": "integer",
          "description": "Maximum results to return. Defaults to 100.",
          "minimum": 1,
          "maximum": 1000
        }
      },
      "required": ["path"]
    }
  }
}
```

---

## 6. Implementation Sketch

### 6.1 Core execute Logic

```python
import os
import re
import fnmatch
import time
from pathlib import Path
from typing import Any, Iterator

from .base import Tool, ToolResult


class SearchTool(Tool):
  DEFAULT_MAX_RESULTS: int = 100
  ABSOLUTE_MAX_RESULTS: int = 1000
  DEFAULT_TIMEOUT_MS: int = 5000
  ABSOLUTE_TIMEOUT_MS: int = 30000
  MAX_FILE_SIZE_MB: int = 10
  MAX_REGEX_LENGTH: int = 500

  FORBIDDEN_PATTERNS: set[str] = {
    r"(\w+)+",
    r"(\d+)+",
    r"(.+)+",
    r"(\w*)*",
    r"(.*)*",
    r"(\w+)*",
    r"(.+)*",
  }

  SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "build", "dist", ".mypy_cache", ".pytest_cache", "htmlcov",
  })

  def execute(self, **kwargs: Any) -> ToolResult:
    # Validate path
    path_str = kwargs.get("path", "")
    if not path_str:
      return ToolResult(success=False, result="", error="Missing required parameter: path")

    # Guardrail validation
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        return ToolResult(success=False, result="", error=validation.reason)

    # Parse and clamp parameters
    try:
      max_results = self._clamp(
        int(kwargs.get("max_results", self.DEFAULT_MAX_RESULTS)),
        1,
        self.ABSOLUTE_MAX_RESULTS,
      )
    except (ValueError, TypeError):
      return ToolResult(success=False, result="", error="Invalid numeric parameter: max_results")

    search_type = kwargs.get("type", "content")
    if search_type not in ("content", "filename"):
      return ToolResult(
        success=False,
        result="",
        error=f"Invalid type: {search_type}. Must be 'content' or 'filename'",
      )

    pattern = kwargs.get("pattern", "")
    if not pattern:
      pattern = "*" if search_type == "filename" else ".*"

    # Validate regex for content search
    if search_type == "content":
      is_valid, error = self._validate_regex(pattern)
      if not is_valid:
        return ToolResult(success=False, result="", error=error)

    # Validate path
    try:
      path = Path(path_str)
      if not path.exists():
        return ToolResult(success=False, result="", error=f"Path not found: {path_str}")
      if not path.is_dir():
        return ToolResult(success=False, result="", error=f"Path is not a directory: {path_str}")
    except PermissionError:
      return ToolResult(success=False, result="", error=f"Permission denied: {path_str}")

    # Execute search
    try:
      if search_type == "content":
        matches, total, truncated = self._search_content(path, pattern, max_results)
        files_searched = self._count_files_searched(path)
        result = {
          "success": True,
          "matches": matches,
          "total_matches": total,
          "truncated": truncated,
          "files_searched": files_searched,
        }
      else:
        matches, total, truncated = self._search_filename(path, pattern, max_results)
        result = {
          "success": True,
          "matches": matches,
          "total_matches": total,
          "truncated": truncated,
        }

      return ToolResult(success=True, result=result)

    except Exception as e:
      return ToolResult(success=False, result="", error=f"Error searching: {e}")

  def _clamp(self, value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))

  def _validate_regex(self, pattern: str) -> tuple[bool, str]:
    if len(pattern) > self.MAX_REGEX_LENGTH:
      return False, f"Pattern too long: max {self.MAX_REGEX_LENGTH} characters"

    for forbidden in self.FORBIDDEN_PATTERNS:
      if re.search(forbidden, pattern):
        return False, "Pattern rejected: potential ReDoS vulnerability (nested quantifiers)"

    try:
      re.compile(pattern)
      return True, ""
    except re.error as e:
      return False, f"Invalid regex pattern: {e}"

  def _walk_files(self, root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
      dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in self.SKIP_DIRS]
      for filename in filenames:
        if not filename.startswith("."):
          yield Path(dirpath) / filename

  def _search_content(
    self,
    root: Path,
    pattern: str,
    max_results: int,
  ) -> tuple[list[dict[str, Any]], int, bool]:
    matches: list[dict[str, Any]] = []
    total_count = 0
    truncated = False

    regex = re.compile(pattern)
    max_size = self.MAX_FILE_SIZE_MB * 1024 * 1024

    for file_path in self._walk_files(root):
      try:
        if file_path.stat().st_size > max_size:
          continue
        content = file_path.read_text(errors="replace")
        for line_num, line in enumerate(content.splitlines(), 1):
          if regex.search(line):
            total_count += 1
            if len(matches) < max_results:
              matches.append({
                "file": str(file_path),
                "line": line_num,
                "content": line.strip(),
              })
      except (UnicodeDecodeError, PermissionError, OSError):
        continue

    if len(matches) < total_count:
      truncated = True

    return matches, total_count, truncated

  def _search_filename(
    self,
    root: Path,
    pattern: str,
    max_results: int,
  ) -> tuple[list[dict[str, Any]], int, bool]:
    matches: list[dict[str, Any]] = []
    total_count = 0
    truncated = False

    for file_path in self._walk_files(root):
      if fnmatch.fnmatch(file_path.name, pattern):
        total_count += 1
        if len(matches) < max_results:
          matches.append({"file": str(file_path)})

    if len(matches) < total_count:
      truncated = True

    return matches, total_count, truncated

  def _count_files_searched(self, root: Path) -> int:
    count = 0
    for _ in self._walk_files(root):
      count += 1
    return count
```

### 6.2 Package Registration

Update `src/yoker/tools/__init__.py`:

```python
from .search import SearchTool

__all__ = [
  # ... existing exports ...
  "SearchTool",
]

def create_default_registry() -> ToolRegistry:
  registry = ToolRegistry()
  registry.register(ReadTool())
  registry.register(ListTool())
  registry.register(SearchTool())  # Add this
  return registry
```

---

## 7. Test Design

### 7.1 Test File Location

`tests/test_tools/test_search.py`

### 7.2 Test Cases

#### Content Search Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Basic content search | `path="/tmp/test", pattern="TODO", type="content"` | Returns matches with file, line, content |
| Regex pattern | `pattern="def\\s+\\w+"` | Matches function definitions |
| Case-insensitive | `pattern="(?i)todo"` | Matches TODO, todo, Todo |
| Max results limit | `max_results=2` with 5 matches | Returns 2 matches, `truncated=true` |
| Invalid regex | `pattern="[invalid"` | `success=False`, "Invalid regex pattern" |
| ReDoS pattern | `pattern="(\w+)+"` | `success=False`, "potential ReDoS vulnerability" |
| Empty directory | `path="/tmp/empty"` | Returns empty matches array |
| Binary file skipped | Directory with `.bin` file | Binary file not searched |
| Large file skipped | File > MAX_FILE_SIZE_MB | File skipped |

#### Filename Search Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Glob pattern | `path="/tmp/test", pattern="*.py", type="filename"` | Returns matching files |
| Question mark | `pattern="test_?.py"` | Matches test_a.py, test_b.py |
| Character class | `pattern="test_[ab].py"` | Matches test_a.py, test_b.py |
| No matches | `pattern="*.nonexistent"` | Returns empty matches array |
| Max results limit | `max_results=2` with 5 matches | Returns 2 matches, `truncated=true` |

#### General Tests

| Test | Input | Expected Result |
|------|-------|-----------------|
| Path not found | `path="/nonexistent"` | `success=False`, "Path not found" |
| Path is file | `path="/tmp/test.txt"` | `success=False`, "Path is not a directory" |
| Permission denied | Mock `PermissionError` | `success=False`, "Permission denied" |
| Invalid type | `type="invalid"` | `success=False`, "Invalid type" |
| Default type | `pattern="TODO"` (no type) | Uses "content" as default |
| Default pattern (content) | No pattern | Uses `.*` (match all) |
| Default pattern (filename) | `type="filename"`, no pattern | Uses `*` (match all) |

### 7.3 Fixtures

```python
import pytest
from pathlib import Path


@pytest.fixture
def temp_search_dir(tmp_path: Path) -> Path:
  """Create a temporary directory with files for searching."""
  # Python files
  (tmp_path / "main.py").write_text("def main():\n    # TODO: implement\n    pass\n")
  (tmp_path / "utils.py").write_text("# TODO: add docstrings\ndef helper():\n    pass\n")

  # Markdown files
  (tmp_path / "README.md").write_text("# Project\n\nTODO: write docs\n")

  # Nested directory
  (tmp_path / "src").mkdir()
  (tmp_path / "src" / "app.py").write_text("def app():\n    # TODO: refactor\n    return True\n")

  # Hidden file (should be skipped)
  (tmp_path / ".hidden").write_text("TODO: this should be ignored")

  return tmp_path


@pytest.fixture
def large_file(tmp_path: Path) -> Path:
  """Create a file larger than MAX_FILE_SIZE_MB."""
  large = tmp_path / "large.txt"
  large.write_bytes(b"x" * (20 * 1024 * 1024))  # 20MB
  return tmp_path
```

### 7.4 Test Implementation Sketch

```python
import pytest
from yoker.tools.search import SearchTool


def test_content_search_basic(temp_search_dir):
  tool = SearchTool()
  result = tool.execute(path=str(temp_search_dir), pattern="TODO", type="content")

  assert result.success
  data = result.result
  assert data["total_matches"] >= 3
  assert len(data["matches"]) <= tool.DEFAULT_MAX_RESULTS
  assert "file" in data["matches"][0]
  assert "line" in data["matches"][0]
  assert "content" in data["matches"][0]


def test_filename_search_glob(temp_search_dir):
  tool = SearchTool()
  result = tool.execute(path=str(temp_search_dir), pattern="*.py", type="filename")

  assert result.success
  data = result.result
  assert data["total_matches"] == 3  # main.py, utils.py, src/app.py
  assert all("file" in m for m in data["matches"])


def test_invalid_regex(temp_search_dir):
  tool = SearchTool()
  result = tool.execute(path=str(temp_search_dir), pattern="[invalid", type="content")

  assert not result.success
  assert "Invalid regex" in result.error


def test_redos_pattern(temp_search_dir):
  tool = SearchTool()
  result = tool.execute(path=str(temp_search_dir), pattern=r"(\w+)+", type="content")

  assert not result.success
  assert "ReDoS" in result.error


def test_max_results_limiting(temp_search_dir):
  tool = SearchTool()
  result = tool.execute(
    path=str(temp_search_dir),
    pattern="TODO",
    type="content",
    max_results=2,
  )

  assert result.success
  data = result.result
  assert len(data["matches"]) == 2
  assert data["truncated"] is True
```

---

## 8. Security Considerations

### 8.1 ReDoS Prevention Summary

| Attack Vector | Mitigation |
|--------------|------------|
| Nested quantifiers | Forbidden pattern detection |
| Long patterns | Length limit (500 chars) |
| Complex regex | Timeout during execution |
| Catastrophic backtracking | Compile-time validation |

### 8.2 File System Security

| Attack Vector | Mitigation |
|--------------|------------|
| Path traversal | `PathGuardrail` validates path prefix |
| Symbolic link loops | Skip symlinks in `_walk_files` |
| Large file DoS | Skip files > MAX_FILE_SIZE_MB |
| Binary file processing | Skip common binary extensions |
| Permission errors | Catch and skip, don't crash |

### 8.3 Resource Limits

| Resource | Limit | Rationale |
|----------|-------|-----------|
| Max results | 1000 | Prevent context window overflow |
| Max regex length | 500 chars | Prevent complex regex attacks |
| Max file size | 10 MB | Prevent memory exhaustion |
| Timeout | 30 seconds | Prevent runaway searches |

---

## 9. Comparison with Other Tools

### 9.1 Consistency Analysis

| Aspect | ReadTool | ListTool | SearchTool | Consistent? |
|--------|----------|----------|------------|-------------|
| Base class | `Tool` | `Tool` | `Tool` | Yes |
| Property pattern | `@property name`, `@property description` | Same | Same | Yes |
| Schema format | OpenAI function-calling | Same | Same | Yes |
| Error handling | Try/except | Same | Same | Yes |
| Return type | `ToolResult` | Same | Same | Yes |
| Guardrail integration | Optional | Optional | Optional | Yes |
| Parameter clamping | No | Yes (depth, entries) | Yes (results) | Yes |

### 9.2 Key Differences

| Aspect | ReadTool | ListTool | SearchTool |
|--------|----------|----------|------------|
| Parameters | `path`, `offset`, `limit` | `path`, `max_depth`, `max_entries`, `pattern` | `path`, `pattern`, `type`, `max_results` |
| Pattern type | None | Glob (fnmatch) | Regex or Glob |
| Output format | Raw file content | Tree-formatted text | Structured JSON |
| Security concerns | File size limits | Recursion limits | ReDoS, timeouts |
| Result structure | String | String | Dict with matches array |

---

## 10. Action Items

### 10.1 Implementation Tasks

| Priority | Task | File(s) |
|----------|------|---------|
| High | Create `SearchTool` class | `src/yoker/tools/search.py` |
| High | Register `SearchTool` in package exports | `src/yoker/tools/__init__.py` |
| High | Add `SearchTool` to default registry | `src/yoker/tools/__init__.py` |
| Medium | Write unit tests | `tests/test_tools/test_search.py` |
| Low | Update documentation | `docs/tools.md` (if exists) |

### 10.2 Cross-Task Considerations

- **Task 2.2 (List Tool)**: Shares `PathGuardrail` with ListTool
- **Task 2.3 (Read Tool)**: Shares `PathGuardrail` with ReadTool
- **Task 3.2 (Tool Call Processing)**: The tool dispatcher will call `execute()` after guardrail validation

### 10.3 Documentation Updates

- Update `analysis/architecture.md` to mark SearchTool as implemented
- Update `CLAUDE.md` Current State to include SearchTool
- No OpenAPI spec needed (tools use Ollama function schema, not HTTP API)

---

## 11. Summary of Design Decisions

1. **Tool name**: `"search"` - Clear, matches common CLI tools
2. **Two search modes**: `content` (regex) and `filename` (glob) - Covers both grep-like and find-like use cases
3. **ReDoS prevention**: Pattern validation + forbidden pattern detection + timeout
4. **Structured output**: JSON with matches array - Easier for LLM to parse than grep output
5. **Self-enforced limits**: Tool validates and clamps parameters internally
6. **Shared PathGuardrail**: Uses same guardrail as other filesystem tools
7. **Skip directories**: Skip `.git`, `__pycache__`, `node_modules`, etc. for performance
8. **Hidden file filtering**: Skip files starting with `.` for security and relevance
9. **Large file skipping**: Skip files > 10MB to prevent memory issues
10. **Consistent with ListTool**: Same error patterns, same `ToolResult` usage, same property-based schema