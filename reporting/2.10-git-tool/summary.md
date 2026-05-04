# Task 2.10 Git Tool - Implementation Summary

**Date**: 2026-05-04
**Status**: Complete
**Commit**: cd25d9c

## What Was Implemented

A GitTool for the yoker agent harness providing secure, controlled access to Git operations.

### Features

1. **Read-Only Operations** (safe by default):
   - `status`: Show working tree status
   - `log`: Show commit history with filtering options
   - `diff`: Show changes between commits/working tree (supports file paths)
   - `branch`: List branches
   - `show`: Show commit details

2. **Permission-Required Operations**:
   - `commit`: Record changes (requires permission handler)
   - `push`: Update remote refs (requires permission handler)

3. **Security Guardrails**:
   - Operation allowlist validation
   - Command injection prevention (no shell=True, list args)
   - Dangerous option blocking (`--upload-pack`, `--git-dir`, `-c`, etc.)
   - Forbidden character filtering (`\n`, `\r`, `\x00`, `` ` ``, `$`, `|`, `;`, `&`)
   - Underscore-form bypass prevention (`--uploadPack` blocked)
   - Flag injection prevention (leading dash rejected)
   - Credential redaction from URLs

4. **Path Handling**:
   - Defaults to `.` (current directory)
   - Accepts files OR directories for diff/show operations
   - PathGuardrail integration for security

5. **Permission System**:
   - Three modes: `allow`, `block`, `ask_user`
   - Destructive operations blocked without explicit permission

6. **Tool Call Display**:
   - Shows operation name and arguments
   - Shows success (✓) or failure (✗) with error message

## Key Decisions

1. **Path can be file or directory**: For diff and show operations, the `path` parameter can be a file path. The tool automatically resolves the parent directory as the working directory.

2. **Path defaults to `.`**: No need to specify path for common operations - defaults to current directory.

3. **Command Building**: Multi-letter options use `=` format (`--format=%s`) to prevent git from interpreting values as revisions/paths.

4. **Permission Model**: Destructive operations require explicit permission handlers in configuration. Default is to block.

5. **Output Sanitization**: Credentials are automatically redacted from remote URLs in output.

## Files Modified

| File | Action |
|------|--------|
| `src/yoker/tools/git.py` | Created (159 lines) |
| `src/yoker/tools/__init__.py` | Updated (export GitTool) |
| `src/yoker/tools/path_guardrail.py` | Updated (git tool allows missing path) |
| `src/yoker/agent.py` | Updated (register GitTool) |
| `src/yoker/events/handlers.py` | Updated (improved tool call display) |
| `tests/test_tools/test_git.py` | Created (64 tests) |
| `README.md` | Updated (features table) |
| `demos/git-tool.md` | Created |
| `media/demo-git-tool.svg` | Created |
| `docs/_static/demo-git-tool.svg` | Created |
| `docs/quickstart.md` | Updated (git tool section) |
| `TODO.md` | Updated (task 2.10 complete) |

## Test Coverage

- **Total tests**: 64
- **Categories**: Schema, Read-only ops, Permission ops, Injection prevention, Path restrictions, Output sanitization, Error handling, Argument validation, Guardrail integration, Return format, Subprocess security, Integration

## Acceptance Criteria Verified

- [x] `make test` (636 tests) ✓
- [x] `make lint` ✓
- [x] `make typecheck` ✓
- [x] GitTool registered and functional
- [x] Security guardrails active
- [x] Demo screenshot generated

## Lessons Learned

1. **Path parameter design**: Users expect git tools to accept file paths directly (e.g., `git diff README.md`). Making `path` accept files OR directories matches user expectations.

2. **Guardrail validation order**: The guardrail validates parameters BEFORE `execute()` is called, so defaults must be handled either in the guardrail or passed by the caller.

3. **LLM schema understanding**: Clear descriptions in the tool schema help LLMs use tools correctly. Updating "Path to Git repository" to "Path to repository, or file for diff/show" improves LLM behavior.

## References

- API Design: `analysis/api-git-tool.md`
- Security Analysis: `analysis/security-git-tool.md`
- Consensus: `reporting/2.10-git-tool/consensus.md`
- Functional Review: `reporting/2.10-git-tool/functional-review.md`