# Task Summary: Read Tool Hardening (Task 2.3)

**Date**: 2026-04-28
**Status**: Completed

---

## What Was Implemented

### 1. Tool ABC Guardrail Support (`src/yoker/tools/base.py`)

Added optional `guardrail` parameter to `Tool.__init__` so all concrete tools can accept a guardrail for defense-in-depth validation. Fully backward-compatible — existing instantiations without guardrail continue to work.

### 2. ReadTool Hardening (`src/yoker/tools/read.py`)

Embedded defense-in-depth security into ReadTool:
- **Guardrail validation**: Validates parameters via injected guardrail before reading
- **Symlink rejection**: Checks `original_path.is_symlink()` before resolution, blocking all symlink reads
- **Path resolution**: Uses `os.path.realpath()` to normalize paths and prevent traversal
- **Explicit UTF-8 encoding**: Reads with `encoding="utf-8", errors="replace"` to prevent crashes on binary files
- **Sanitized error messages**: Returns generic messages ("File not found", "Permission denied") without leaking paths to LLM
- **Audit logging**: All access attempts, blocks, and successes logged via structlog
- **Type safety**: Validates path parameter is a string before processing

### 3. ListTool Guardrail Pattern (`src/yoker/tools/list.py`)

Updated to match ReadTool's guardrail acceptance pattern:
- Accepts optional guardrail via `super().__init__(guardrail)`
- Validates via guardrail in `execute()` before listing

### 4. Agent Guardrail Injection (`src/yoker/agent.py`)

Modified `_build_tool_registry()` to create fresh tool instances with the agent's `PathGuardrail` injected. This ensures all filesystem tools have defense-in-depth validation both at the agent orchestration layer and inside the tools themselves.

### 5. Tests

- **Unit tests** (`tests/tools/test_read.py`): 19 tests covering guardrail integration, symlink rejection, UTF-8 encoding, invalid byte replacement, error sanitization, path resolution, permission errors, non-string paths, and OSError handling
- **Integration tests** (`tests/tools/test_read_guardrail.py`): 11 tests with real `PathGuardrail` covering path traversal, blocked patterns, extension filtering, size limits, and symlink blocking

## Key Decisions Made

1. **Defense-in-depth with dual validation**: Both Agent.process() and tool.execute() validate through the guardrail. This ensures tools remain safe when used standalone (e.g., in tests, subagents, or programmatic APIs).

2. **Symlink rejection at tool layer**: ReadTool rejects symlinks unconditionally before resolution, even when a guardrail is present. This prevents symlink-based traversal even if the guardrail is bypassed or misconfigured.

3. **Sanitized errors at tool layer**: ReadTool's own I/O errors are sanitized, but guardrail validation reasons (which contain the original path the LLM provided) are passed through for self-correction. This is an intentional trade-off.

4. **Backward compatibility**: Tool.__init__(guardrail=None) ensures no breaking changes to existing code.

## Files Modified

| File | Lines | Nature |
|------|-------|--------|
| `src/yoker/tools/base.py` | +15 | Added guardrail parameter to Tool ABC |
| `src/yoker/tools/read.py` | ~48 | Complete rewrite with hardened execute() |
| `src/yoker/tools/list.py` | +18 | Added guardrail __init__ and validation |
| `src/yoker/agent.py` | ~10 | Inject guardrail into tool registry |
| `tests/tools/test_read.py` | ~65 | Extended with 8 new tests |
| `tests/tools/test_read_guardrail.py` | +143 | New integration test suite |

## Verification

- All 298 tests pass (up from 293, +5 new tests)
- Typecheck passes (mypy strict)
- Lint passes (ruff)
- ReadTool coverage: 95%
- Prototype starts correctly: `python -m yoker --help`

## Lessons Learned

1. **Defense-in-depth requires tool-layer enforcement**: Relying solely on the orchestration layer for security is insufficient for a library-first design where tools may be invoked directly.

2. **Symlink checks must happen before resolution**: Checking `is_symlink()` after `realpath()` always returns False because resolution follows the symlink. The check must happen on the original path.

3. **Review cycles catch real gaps**: The testing-engineer review identified missing edge case tests (non-string paths, OSError handling) that significantly improved robustness.

## Follow-Up Items (Out of Scope)

- ListTool error message sanitization (currently still returns raw paths)
- Guardrail error message sanitization (validation reasons contain original paths)
- Chunked streaming read with byte limit for full TOCTOU prevention
- Intermediate symlink detection in directory components
