# API Analysis: Read Tool Hardening (Task 2.3)

**Document Version**: 1.0
**Date**: 2026-04-28
**Task**: 2.3 Read Tool from TODO.md
**Status**: API Design Complete

---

## Summary

This document analyzes the hardening requirements for `ReadTool` (task 2.3) and resolves the central design question: since `PathGuardrail` already exists and is wired into `Agent.process()`, what should `ReadTool` itself do?

**Key Finding**: `ReadTool` should adopt a **defense-in-depth** pattern: it accepts an optional `PathGuardrail` via `__init__` and validates in `execute()` when one is provided, while `Agent.process()` continues to validate at the orchestration layer. This gives standalone safety without duplicating the primary enforcement point.

---

## 1. Current State Review

### 1.1 ReadTool (`src/yoker/tools/read.py`)

- Has **zero validation** - calls `Path(path_str).read_text()` directly
- Handles `FileNotFoundError`, `PermissionError`, generic `Exception`
- Schema exposes only `path` (string, required)
- Stateless: no `__init__` parameters

### 1.2 PathGuardrail (`src/yoker/tools/path_guardrail.py`)

- Fully implemented with:
  - Path traversal prevention (`os.path.realpath()`, `relative_to()` check)
  - Blocked pattern matching (regex, pre-compiled)
  - Extension filtering (`_check_read_extension()`)
  - Size limit enforcement (`_check_file_size()`)
  - Symlink resolution and validation
  - File existence check for read operations
- Already validates `read` tool specifically (lines 117-128)

### 1.3 Agent.process() (`src/yoker/agent.py`, lines 351-356)

```python
# Validate tool parameters through guardrail
validation = self._guardrail.validate(tool_name, tool_args)
if not validation.valid:
    log.info("guardrail_blocked", tool=tool_name, reason=validation.reason)
    result = f"Error: {validation.reason}"
    success = False
else:
    # ... execute tool
```

Guardrail runs **before** `tool.execute()` is called. If blocked, `execute()` never runs.

### 1.4 ListTool Pattern (`src/yoker/tools/list.py`)

`ListTool.execute()` has no guardrail integration. It relies entirely on `Agent.process()` validation. It self-enforces only operational limits (`max_depth`, `max_entries` clamping) and basic I/O error handling.

---

## 2. Design Question Analysis

The user posed three options:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| 1 | ReadTool accepts guardrail and validates in `execute()` | Defense in depth; standalone safety | Duplicates Agent.process() validation; requires config injection |
| 2 | ReadTool remains unvalidated, relies on caller | Single source of truth; simple | Direct calls bypass all security |
| 3 | Lightweight built-in validation + heavy guardrail in Agent | Basic safety without config | Still vulnerable to traversal, patterns, extensions |

### 2.1 Why Option 3 Is Insufficient

Lightweight validation (just checking `path.exists()`) does NOT protect against:
- Path traversal (`../../../etc/passwd`)
- Blocked patterns (`.env`, `credentials`)
- Extension filtering (`.exe`, `.sh`)
- Size limits (10MB log files)

These require config-aware validation that only `PathGuardrail` provides.

### 2.2 Why Option 2 Is Dangerous

`ReadTool` is instantiated in `create_default_registry()` and is directly callable:

```python
tool = ReadTool()
result = tool.execute(path="../../../etc/passwd")  # No validation!
```

This is the "critically vulnerable" state the task highlights.

### 2.3 Why Option 1 Is Best (With Nuance)

The correct design is **Option 1 with an optional guardrail**:
- `ReadTool` accepts an optional `PathGuardrail` in `__init__`
- If provided, `execute()` validates through it before reading
- If not provided, `execute()` works as before (backward compatible)
- `Agent.process()` still validates at the orchestration layer (primary enforcement)
- When `Agent` builds its tool registry, it can inject the guardrail into `ReadTool`

This gives **defense in depth**: the orchestrator validates (primary), and the tool validates (secondary). Either layer can catch violations.

---

## 3. Recommended API Design

### 3.1 ReadTool Class Signature

```python
# src/yoker/tools/read.py

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from .guardrails import Guardrail  # Import Guardrail ABC, not concrete class


class ReadTool(Tool):
  """Tool for reading file contents.

  Reads the entire contents of a file as text. When constructed with
  a guardrail, validates parameters before reading. Returns error
  messages for common failure cases (file not found, permission denied,
  guardrail violation).

  Args:
    guardrail: Optional guardrail to validate parameters before
      execution. When None, execute() performs no pre-validation.
  """

  def __init__(self, guardrail: Guardrail | None = None) -> None:
    self._guardrail = guardrail

  @property
  def name(self) -> str:
    return "read"

  @property
  def description(self) -> str:
    return "Read the contents of a file"

  def get_schema(self) -> dict[str, Any]:
    """Return Ollama-compatible schema for the read tool."""
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
              "description": "Path to the file to read",
            }
          },
          "required": ["path"],
        },
      },
    }

  def execute(self, **kwargs: Any) -> ToolResult:
    """Read a file and return its contents.

    If a guardrail was provided at construction time, validates
    parameters through the guardrail before reading.

    Args:
      **kwargs: Must contain 'path' key with file path.

    Returns:
      ToolResult with file content or error message.
    """
    path_str = kwargs.get("path", "")

    # Defense-in-depth: validate through guardrail if available
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        return ToolResult(
          success=False,
          result="",
          error=f"Guardrail blocked: {validation.reason}",
        )

    try:
      content = Path(path_str).read_text()
      return ToolResult(success=True, result=content)
    except FileNotFoundError:
      return ToolResult(
        success=False,
        result="",
        error=f"File not found: {path_str}",
      )
    except PermissionError:
      return ToolResult(
        success=False,
        result="",
        error=f"Permission denied: {path_str}",
      )
    except Exception as e:
      return ToolResult(
        success=False,
        result="",
        error=f"Error reading file: {e}",
      )
```

### 3.2 Why `Guardrail` ABC (Not `PathGuardrail`)

Importing `Guardrail` (the ABC) keeps `ReadTool` decoupled from the concrete `PathGuardrail` implementation. This follows the Dependency Inversion Principle and allows:
- Unit tests with mock guardrails
- Future guardrail types (e.g., `RateLimitGuardrail`, `AuditGuardrail`)
- No import of `yoker.config.schema` inside the tool module

### 3.3 Agent Integration

`Agent.__init__` should inject the guardrail when building the tool registry:

```python
# In Agent._build_tool_registry() or Agent.__init__
from yoker.tools import ReadTool, ListTool

registry = ToolRegistry()
# Inject the shared PathGuardrail into filesystem tools
if self.agent_definition is not None:
    allowed_tools = {t.lower() for t in self.agent_definition.tools}
    for tool_cls in [ReadTool, ListTool]:
        if tool_cls().name.lower() in allowed_tools:
            registry.register(tool_cls(guardrail=self._guardrail))
else:
    registry.register(ReadTool(guardrail=self._guardrail))
    registry.register(ListTool(guardrail=self._guardrail))
```

**Note**: This requires `ListTool` to also accept an optional guardrail parameter for consistency.

### 3.4 Backward Compatibility

`ReadTool()` with no arguments still works exactly as before. The guardrail is optional. This means:
- Existing tests don't break
- `create_default_registry()` can be updated incrementally
- Direct usage without a guardrail is still possible (documented as "caller must validate")

---

## 4. Schema Analysis

### 4.1 Should the Schema Include New Parameters?

**No.** The `read` tool schema should remain minimal:

```json
{
  "type": "function",
  "function": {
    "name": "read",
    "description": "Read the contents of a file",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Path to the file to read"
        }
      },
      "required": ["path"]
    }
  }
}
```

**Rationale**:
- Extension filtering, size limits, and blocked patterns are **policy** concerns, not **tool interface** concerns
- The LLM should not be asked to provide these - they are enforced by the guardrail based on configuration
- Adding `max_size` or `allowed_extensions` to the schema would give the LLM false control over policy
- This matches the `ListTool` pattern where limits are tool-internal, not schema-exposed

### 4.2 Schema Description Enhancement (Optional)

Consider enriching the description to hint at constraints:

```python
@property
def description(self) -> str:
    return (
        "Read the contents of a file. "
        "Only allowed file types and sizes permitted."
    )
```

This is a hint to the LLM without exposing policy parameters.

---

## 5. Test Coverage Recommendations

### 5.1 Test File: `tests/tools/test_read.py`

Current tests cover basic functionality (3 tests). The hardened version needs:

| Test Case | What It Verifies |
|-----------|------------------|
| `test_read_without_guardrail` | Backward compatibility: works without guardrail |
| `test_read_with_guardrail_allowed` | Guardrail allows permitted file |
| `test_read_with_guardrail_blocked` | Guardrail blocks disallowed file |
| `test_read_guardrail_path_traversal` | Guardrail catches `../../../etc/passwd` |
| `test_read_guardrail_blocked_pattern` | Guardrail catches `.env` files |
| `test_read_guardrail_extension_filter` | Guardrail catches `.exe` files |
| `test_read_guardrail_size_limit` | Guardrail catches oversized files |
| `test_read_guardrail_symlink_escape` | Guardrail catches symlink traversal |
| `test_read_existing_file` | Basic read still works |
| `test_read_missing_file` | FileNotFoundError handled |
| `test_read_permission_denied` | PermissionError handled |
| `test_read_empty_path` | Empty path parameter handled |

### 5.2 Test Patterns

```python
"""Tests for ReadTool with guardrail integration."""

from pathlib import Path
from unittest.mock import Mock

from yoker.tools import ReadTool
from yoker.tools.base import ToolResult, ValidationResult
from yoker.tools.guardrails import Guardrail


class FakeGuardrail(Guardrail):
  """Mock guardrail for testing ReadTool integration."""

  def __init__(self, should_allow: bool = True, reason: str = "") -> None:
    self._should_allow = should_allow
    self._reason = reason

  def validate(self, tool_name: str, params: dict) -> ValidationResult:
    if self._should_allow:
      return ValidationResult(valid=True)
    return ValidationResult(valid=False, reason=self._reason)


class TestReadTool:
  """Tests for ReadTool."""

  def test_read_without_guardrail(self, tmp_path: Path) -> None:
    """ReadTool works without guardrail (backward compatible)."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = ReadTool()  # No guardrail
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"

  def test_read_with_guardrail_allowed(self, tmp_path: Path) -> None:
    """ReadTool with guardrail allows permitted file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    guardrail = FakeGuardrail(should_allow=True)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"

  def test_read_with_guardrail_blocked(self) -> None:
    """ReadTool with guardrail blocks disallowed file."""
    guardrail = FakeGuardrail(
      should_allow=False, reason="Path outside allowed directories"
    )
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path="/etc/passwd")
    assert result.success is False
    assert "Path outside allowed directories" in result.error

  def test_read_missing_file(self) -> None:
    """ReadTool returns error for missing file."""
    tool = ReadTool()
    result = tool.execute(path="/nonexistent/path/file.txt")
    assert result.success is False
    assert "not found" in result.error.lower()

  def test_read_result_is_toolresult(self) -> None:
    """ReadTool execute returns ToolResult."""
    tool = ReadTool()
    result = tool.execute(path="/dev/null")
    assert isinstance(result, ToolResult)
```

### 5.3 Integration Tests (New File)

Create `tests/tools/test_read_guardrail_integration.py` for real `PathGuardrail` + `ReadTool` interaction:

```python
"""Integration tests for ReadTool with PathGuardrail."""

from pathlib import Path

from yoker.config.schema import Config, PermissionsConfig, ReadToolConfig, ToolsConfig
from yoker.tools import ReadTool
from yoker.tools.path_guardrail import PathGuardrail


class TestReadToolGuardrailIntegration:
  """Integration tests proving ReadTool + PathGuardrail hardening."""

  def test_path_traversal_blocked(self, tmp_path: Path) -> None:
    """ReadTool with PathGuardrail blocks traversal."""
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),))
    )
    guardrail = PathGuardrail(config)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path="../../../etc/passwd")
    assert result.success is False
    assert "outside allowed" in result.error.lower()

  def test_blocked_pattern_blocked(self, tmp_path: Path) -> None:
    """ReadTool with PathGuardrail blocks .env files."""
    env_file = tmp_path / "config.env"
    env_file.write_text("secret")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"\.env",))),
    )
    guardrail = PathGuardrail(config)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(env_file))
    assert result.success is False
    assert "blocked pattern" in result.error.lower()

  def test_extension_filtering(self, tmp_path: Path) -> None:
    """ReadTool with PathGuardrail blocks disallowed extensions."""
    exe_file = tmp_path / "malware.exe"
    exe_file.write_text("bad")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(allowed_extensions=(".txt", ".md"))),
    )
    guardrail = PathGuardrail(config)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(exe_file))
    assert result.success is False
    assert "extension not allowed" in result.error.lower()

  def test_size_limit(self, tmp_path: Path) -> None:
    """ReadTool with PathGuardrail blocks oversized files."""
    big_file = tmp_path / "big.txt"
    big_file.write_text("x" * 2048)  # 2KB
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),), max_file_size_kb=1
      )
    )
    guardrail = PathGuardrail(config)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(big_file))
    assert result.success is False
    assert "exceeds size limit" in result.error.lower()

  def test_allowed_file_permitted(self, tmp_path: Path) -> None:
    """ReadTool with PathGuardrail allows permitted file."""
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("hello world")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(allowed_extensions=(".txt",))),
    )
    guardrail = PathGuardrail(config)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(txt_file))
    assert result.success is True
    assert result.result == "hello world"
```

---

## 6. ListTool Consistency

`ListTool` should be updated to match the same pattern for consistency:

```python
# src/yoker/tools/list.py

class ListTool(Tool):
  def __init__(self, guardrail: Guardrail | None = None) -> None:
    self._guardrail = guardrail

  def execute(self, **kwargs: Any) -> ToolResult:
    if self._guardrail is not None:
      validation = self._guardrail.validate(self.name, kwargs)
      if not validation.valid:
        return ToolResult(
          success=False, result="", error=f"Guardrail blocked: {validation.reason}"
        )
    # ... rest of existing logic
```

This ensures all filesystem tools share the same guardrail integration pattern.

---

## 7. Action Items

| Priority | Task | File(s) | Rationale |
|----------|------|---------|-----------|
| High | Add `guardrail` parameter to `ReadTool.__init__` | `src/yoker/tools/read.py` | Defense-in-depth validation |
| High | Validate through guardrail in `ReadTool.execute()` | `src/yoker/tools/read.py` | Block bad requests at tool layer |
| High | Add `guardrail` parameter to `ListTool.__init__` | `src/yoker/tools/list.py` | Consistency across filesystem tools |
| Medium | Update `Agent._build_tool_registry()` to inject guardrail | `src/yoker/agent.py` | Wire guardrail into tool instances |
| Medium | Update `create_default_registry()` to accept optional guardrail | `src/yoker/tools/__init__.py` | Allow guardrail injection at registry level |
| Medium | Expand `test_read.py` with guardrail tests | `tests/tools/test_read.py` | Unit test coverage |
| Medium | Create `test_read_guardrail_integration.py` | `tests/tools/test_read_guardrail_integration.py` | Integration test coverage |
| Low | Document guardrail usage in tool docstrings | `src/yoker/tools/read.py`, `src/yoker/tools/list.py` | Developer guidance |

---

## 8. Summary of Design Decisions

1. **ReadTool accepts optional `Guardrail` in `__init__`**: Gives defense-in-depth without requiring config in the tool module
2. **`execute()` validates through guardrail when provided**: Secondary enforcement point; primary remains in `Agent.process()`
3. **Schema stays minimal (only `path`)**: Policy parameters (extensions, size limits) are not LLM-facing; they are guardrail-enforced
4. **Uses `Guardrail` ABC, not `PathGuardrail` concrete class**: Decouples tool from guardrail implementation
5. **ListTool updated to match**: Consistent pattern across all filesystem tools
6. **Backward compatible**: `ReadTool()` with no arguments works exactly as before
7. **Test at two levels**: Unit tests with fake guardrails + integration tests with real `PathGuardrail`

---

## 9. Open Questions

| Question | Recommendation |
|----------|----------------|
| Should `Agent` inject guardrail into all tools or only filesystem tools? | Only filesystem tools (`read`, `list`, `write`, `update`) need `PathGuardrail`. Future tools may use different guardrail types. |
| Should the guardrail be injected at registry creation or per-tool instantiation? | Per-tool instantiation is more flexible. `Agent._build_tool_registry()` can pass `guardrail=self._guardrail` to tool constructors that accept it. |
| Should `WriteTool` and `UpdateTool` follow the same pattern when implemented? | Yes. All filesystem tools should accept an optional guardrail and validate in `execute()`. |
