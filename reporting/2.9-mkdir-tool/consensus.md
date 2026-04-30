# Consensus Report: MkdirTool (Task 2.9)

## Overview

Task: Implement folder creation tool (mkdir -p equivalent) for yoker agent harness.

## Domain Agents

| Agent | Status | Key Contributions |
|-------|--------|-------------------|
| API Architect | ✓ Approved | Tool name `mkdir`, parameters, JSON return format |
| Security Engineer | ✓ Approved | Symlink rejection, blocked patterns, depth limit, guardrail integration |
| Testing Engineer | ✓ Approved | 45 test stubs covering security and functionality |

## Design Decisions

### Tool Name
- **Decision**: `mkdir` (Unix standard)
- **Rationale**: Familiar to LLMs, consistent with Unix conventions

### Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | Yes | - | Path to directory to create |
| `recursive` | boolean | No | `false` | Create parent directories if needed |

### Return Format
```json
{
  "created": true,
  "path": "/absolute/path/to/directory"
}
```

For existing directory (idempotent):
```json
{
  "created": false,
  "path": "/absolute/path/to/directory",
  "message": "Directory already exists"
}
```

### Security Requirements

1. **PathGuardrail Integration** (P0)
   - Add `mkdir` to `_FILESYSTEM_TOOLS` in `path_guardrail.py`
   - Validate path against `filesystem_paths` configuration

2. **Symlink Rejection** (P0)
   - Reject if path is a symlink
   - Reject if any path component is a symlink (for recursive creation)
   - Use `is_symlink()` check on resolved path components

3. **Blocked Patterns** (P0)
   - Block creation of: `.git`, `.ssh`, `.aws`, `.env`, `.kube`, `.gnupg`
   - Block patterns matching: `credentials`, `secrets`
   - Pattern matching on directory name only

4. **Maximum Depth Limit** (P1)
   - Default limit: 20 levels from allowed root
   - Configurable via `FolderCreationToolConfig`

5. **Generic Error Messages** (P1)
   - "Path not accessible" for blocked patterns
   - "Path not accessible" for symlink rejection
   - No information disclosure in errors

6. **No Mode Parameter**
   - Use default umask permissions
   - Prevents creation of world-writable directories

## Implementation Checklist

### Files to Create
- [ ] `src/yoker/tools/mkdir.py` - MkdirTool implementation

### Files to Modify
- [ ] `src/yoker/tools/__init__.py` - Export and register MkdirTool
- [ ] `src/yoker/tools/path_guardrail.py` - Add `mkdir` to `_FILESYSTEM_TOOLS`

### Files to Verify
- [ ] `tests/test_tools/test_mkdir.py` - 45 test stubs (already created)

## Test Coverage

| Category | Count | Status |
|----------|-------|--------|
| Schema tests | 4 | Stubs created |
| Basic creation tests | 4 | Stubs created |
| Idempotency tests | 3 | Stubs created |
| Symlink rejection tests | 3 | Stubs created |
| Path traversal tests | 3 | Stubs created |
| Blocked patterns tests | 4 | Stubs created |
| Depth limit tests | 3 | Stubs created |
| Input validation tests | 4 | Stubs created |
| Guardrail integration tests | 5 | Stubs created |
| Error handling tests | 4 | Stubs created |
| Path resolution tests | 3 | Stubs created |
| Return format tests | 4 | Stubs created |
| Special cases tests | 6 | Stubs created |
| Integration tests | 3 | Stubs created |
| **Total** | **45** | **All stubs created** |

## Consensus

All domain agents approve the design. The implementation should:

1. Follow existing tool patterns (see `existence.py` for reference)
2. Use shared `PathGuardrail` for security
3. Implement symlink rejection at all path components
4. Return structured JSON with `created` boolean
5. Be idempotent (success if directory exists)
6. Include comprehensive tests

**Status**: ✓ Approved for implementation