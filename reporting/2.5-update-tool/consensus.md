# Consensus Summary: Update Tool (Task 2.5)

## Domain Reviews

### API Architect Review
- **Tool Design**: `UpdateTool` follows existing `WriteTool` pattern, accepting `guardrail` and `config` parameters
- **Operations**: Four operations: `replace`, `insert_before`, `insert_after`, `delete`
- **Exact Match**: When `require_exact_match=True` (default), search must appear verbatim and uniquely
- **Diff Size**: Enforced against `max_diff_size_kb` from `UpdateToolConfig`
- **Return Format**: Structured diff preview on success
- **Integration**: Register in `tools/__init__.py`; PathGuardrail already recognizes `"update"` tool

### Security Engineer Review
- **Critical Risks**: TOCTOU race condition, exact match failures, regex injection, update-as-write bypass
- **Required Mitigations**: Fresh re-read in `execute()`, literal string search only, atomic writes, sanitized errors
- **PathGuardrail Updates**: Add file existence and extension checks for update operations
- **Test Coverage**: 13 security test scenarios defined

## Consensus Decisions

1. **All agents approve** the API design and security approach
2. **Implementation follows existing tool patterns** (ReadTool/WriteTool)
3. **Security measures are practical and implementable** within the existing architecture
4. **PathGuardrail additions are minimal** — adding file existence, extension, and diff size checks
5. **Atomic writes via temp file + `os.replace()`** accepted as sufficient for MVP

## Next Steps

Proceed to implementation planning (Phase 4).
