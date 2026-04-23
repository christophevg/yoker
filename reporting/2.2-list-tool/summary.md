# Implementation Summary: Task 2.2 - List Tool

## What Was Implemented

Created `ListTool`, a directory listing tool with optional recursion, entry limits, and glob pattern filtering. The tool is secured by the shared `PathGuardrail` implemented in task 2.1.5.

## Files Created

- **`src/yoker/tools/list.py`**
  - `ListTool` class following `ReadTool` patterns
  - Parameters: `path` (required), `max_depth` (default 1), `max_entries` (default 1000), `pattern` (optional glob)
  - Self-enforces limits with clamping to absolute maximums (`ABSOLUTE_MAX_DEPTH=10`, `ABSOLUTE_MAX_ENTRIES=5000`)
  - Tree-formatted output with 2-space indentation per depth level
  - Summary line: `{N} entries total ({F} files, {D} directories)`
  - Truncation notice when `max_entries` exceeded
  - Does not follow symlinks (shown as files, never recursed into)
  - Error handling: `FileNotFoundError`, `PermissionError` (graceful inline message), generic `Exception`

- **`tests/tools/test_list.py`**
  - 18 comprehensive tests covering flat listing, recursion, depth limits, entry truncation, pattern filtering, nonexistent paths, file-as-path, permission denied, invalid parameters, clamping, empty directory, symlinks, and sorting

## Files Modified

- **`src/yoker/tools/__init__.py`** - Added `ListTool` import, export, and registration in default registry

## Verification Results

- **273 tests pass** (100% pass rate)
- **mypy strict mode**: no issues in 34 source files
- **ruff linting**: all checks pass
- **CLI entry point** (`python -m yoker --help`): works correctly

## Security Notes

- Path security is handled by `PathGuardrail` (task 2.1.5), which validates the root path before `ListTool.execute()` is called
- Symlinks are never followed during recursion (`entry.is_symlink()` check with `continue`)
- `max_depth` and `max_entries` prevent DoS from deep or wide directory trees
- `PermissionError` during `iterdir()` is handled gracefully with inline "... (permission denied)" message

## Next Steps

Task 2.3 (Read Tool hardening) or Task 2.4 (Write Tool) can proceed. Both will reuse the shared `PathGuardrail`.
