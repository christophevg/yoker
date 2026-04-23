# Implementation Summary: Task 2.1.5 - Shared PathGuardrail

## What Was Implemented

Implemented a shared `PathGuardrail` concrete class and wired it into `Agent.process()` to validate all filesystem tool parameters before execution. This closes the critical security gap where `ReadTool` previously read any file with zero validation.

## Files Created

- **`src/yoker/tools/path_guardrail.py`**
  - `PathGuardrail` class: validates filesystem tools against Config permissions
  - Checks: path resolution, allowed roots, blocked patterns, file extensions, file size
  - Uses `os.path.realpath()` to prevent traversal and resolve symlinks
  - Pre-compiles blocked regex patterns for efficiency
  - Logs allow/block decisions via structlog

- **`tests/tools/test_path_guardrail.py`**
  - 18 comprehensive tests covering all validation scenarios
  - Tests: path traversal, symlinks, blocked patterns, extension filtering, size limits

## Files Modified

- **`src/yoker/tools/__init__.py`** - Added `PathGuardrail` to public API exports
- **`src/yoker/tools/read.py`** - Fixed `execute` signature from `**kwargs: str` to `**kwargs: Any`
- **`src/yoker/config/schema.py`** - Changed `filesystem_paths` default from `()` to `(".",)`
- **`src/yoker/config/validator.py`** - Added validation: empty `filesystem_paths` raises `ValidationError`
- **`src/yoker/agent.py`** - Wired guardrail into `Agent.__init__` and `Agent.process()`:
  - Validates config on initialization
  - Instantiates `PathGuardrail` with loaded config
  - Validates every tool call before execution
  - Returns synthetic error result when guardrail blocks
  - Logs guardrail decisions when `include_permission_checks` is enabled
- **`tests/test_config.py`** - Added test for default filesystem_paths and empty rejection

## Key Decisions

1. **Single guardrail for all filesystem tools** (`read`, `list`, `write`, `update`) to centralize path logic
2. **Agent holds the guardrail**, not ToolRegistry, to keep registry passive
3. **Blocked before execution**: guardrail validates before `tool.execute()`, returning synthetic error to LLM
4. **Security boundary order**: allowed roots first, then blocked patterns, then tool-specific checks
5. **Default filesystem_paths = (".")** instead of empty tuple (which meant "allow all")

## Verification Results

- All 255 tests pass (100% pass rate)
- Mypy strict mode: no issues
- Ruff linting: all checks pass
- CLI entry point (`python -m yoker --help`): works correctly

## Security Impact

- **Path traversal** (`../../../etc/passwd`) is now blocked
- **Symlink escapes** are blocked via `os.path.realpath()` resolution
- **Blocked patterns** (`.env`, `credentials`, `secret`) are enforced
- **Extension filtering** is enforced for read tool
- **File size limits** are enforced for read tool
- **All guardrail decisions are logged** for audit trail

## Next Steps

Task 2.2 (List Tool) can now proceed safely, building on the shared PathGuardrail.
