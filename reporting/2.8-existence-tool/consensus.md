# Consensus Report: Existence Tool (Task 2.8)

**Date**: 2026-04-29
**Task**: 2.8 File Existence Tool

## Domain Agents Consulted

| Agent | Document | Status |
|-------|----------|--------|
| c3:api-architect | `analysis/api-existence-tool.md` | ✓ Complete |
| c3:security-engineer | `analysis/security-existence-tool.md` | ✓ Complete |

## Key Design Decisions

### 1. Tool Interface

| Decision | Choice |
|----------|--------|
| Tool name | `"existence"` |
| Parameters | Single `path` parameter (required) |
| Return format | Structured JSON: `{"exists": bool, "type": str|null, "path": str}` |

### 2. Security Measures

| Measure | Priority | Implementation |
|---------|----------|---------------|
| PathGuardrail integration | P0 | Add to `_FILESYSTEM_TOOLS` |
| Symlink rejection | P0 | `path.is_symlink()` check |
| Protected pattern blocking | P0 | Regex pattern matching |
| Generic error messages | P1 | Sanitized error responses |
| Timing attack protection | P1 | Constant-time delays |

### 3. Return Value Distinction

- `success=False` → Tool execution failed (error)
- `success=True, exists=False` → Path does not exist (valid result)

## Implementation Plan

| Step | File | Action |
|------|------|--------|
| 1 | `src/yoker/tools/existence.py` | Create ExistenceTool class |
| 2 | `src/yoker/tools/path_guardrail.py` | Add "existence" to `_FILESYSTEM_TOOLS` |
| 3 | `src/yoker/tools/__init__.py` | Export ExistenceTool, register in default registry |
| 4 | `tests/test_tools/test_existence.py` | Write unit tests |

## Files to Create/Modify

| File | Type | Purpose |
|------|------|---------|
| `src/yoker/tools/existence.py` | New | ExistenceTool implementation |
| `src/yoker/tools/path_guardrail.py` | Modify | Add to filesystem tools set |
| `src/yoker/tools/__init__.py` | Modify | Export and register tool |
| `tests/test_tools/test_existence.py` | New | Unit tests |

## Consensus Status

✓ **APPROVED** - All domain agents agree on the design.