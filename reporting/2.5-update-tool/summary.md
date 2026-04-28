# Implementation Summary: Update Tool (Task 2.5)

## What Was Implemented

The `UpdateTool` class was created to enable the LLM agent to edit existing files safely with four operations:

1. **replace** - Content-based text replacement with exact match validation
2. **insert_before** - Line-based insertion before a specified 1-indexed line number
3. **insert_after** - Line-based insertion after a specified 1-indexed line number
4. **delete** - Content-based deletion by old_string or line-based deletion by line_number

## Files Modified

| File | Action | Description |
|------|--------|-------------|
| `src/yoker/tools/update.py` | Created | UpdateTool implementation |
| `src/yoker/tools/__init__.py` | Updated | Registered UpdateTool in default registry |
| `src/yoker/tools/path_guardrail.py` | Updated | Added update-specific checks (file existence, extension, diff size) |
| `src/yoker/agent.py` | Updated | Added UpdateTool to agent's tool registry |
| `tests/tools/test_update.py` | Created | 35 unit tests covering all operations and edge cases |
| `tests/tools/test_path_guardrail.py` | Updated | 5 additional guardrail tests for update tool |
| `analysis/api-update-tool.md` | Updated | Aligned API design with approved implementation |

## Key Decisions

- **Parameter naming**: Used `old_string`/`new_string` (matches Claude Code's edit tool convention) rather than `search`/`replacement`
- **Line-based inserts**: Use explicit `line_number` parameter for predictability rather than content-based line matching
- **Atomic writes**: Temp file + `os.replace()` to prevent partial writes on crash
- **TOCTOU mitigation**: Fresh file read in `execute()` eliminates race condition window
- **Literal string search only**: Never interprets search text as regex (prevents ReDoS)

## Security Measures

- PathGuardrail validates file existence and type before tool execution
- Read and write extension checks applied to update operations
- Diff size limit enforced against `max_diff_size_kb` config
- Symlinks rejected before path resolution
- Error messages sanitized (no path leakage)

## Verification

- **Tests**: 380 passed (including 35 new UpdateTool tests)
- **Coverage**: 80% overall, 86% for update.py
- **Type checking**: mypy strict mode - clean
- **Linting**: ruff - clean
- **Prototype**: `python -m yoker` starts correctly

## Review Status

- API architect: Approved (design document created)
- Security engineer: Approved (threat model documented)
- Functional analyst: Approved after aligning api-update-tool.md with implementation
- Code reviewer: Approved after wrapping `is_symlink()` in try/except
- Testing engineer: Approved (comprehensive test coverage)
