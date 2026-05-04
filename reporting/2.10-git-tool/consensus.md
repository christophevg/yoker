# Consensus Report: Git Tool (Task 2.10)

**Date**: 2026-05-04
**Task**: 2.10 Git Tool
**Status**: Approved for Implementation

## Domain Agents Invoked

| Agent | Document | Status |
|-------|----------|--------|
| c3:api-architect | `analysis/api-git-tool.md` | ✓ Complete |
| c3:security-engineer | `analysis/security-git-tool.md` | ✓ Complete |
| c3:testing-engineer | `tests/test_tools/test_git.py` | ✓ Test stubs created |

## Consensus Decisions

### 1. Operation Categories

**Agreed**:
- **Read-only (safe by default)**: status, log, diff, branch, show
- **Permission required**: commit, push
- **Blocked in MVP**: clone, init, config, submodule, filter-branch, clean, gc

**Security Engineer Addition**: Also block reset --hard, push --force, rebase

### 2. Command Injection Prevention

**Agreed**:
- Subprocess with list arguments (never shell=True)
- `--` delimiter before user-provided arguments
- Argument sanitization (reject leading dash)
- Forbidden characters: `\n`, `\r`, `\x00`, `` ` ``, `$`, `|`, `;`, `&`
- Block dangerous options: `--upload-pack`, `--receive-pack`, `--exec`, `--git-dir`, `--work-tree`, `-c`

### 3. Path Validation

**Agreed**:
- Integrate with existing PathGuardrail
- Validate repository path against `config.permissions.filesystem_paths`
- Block path traversal attempts (`../../`)
- Resolve symlinks and validate real path

### 4. Permission Model

**Agreed**:
- Permission modes: `block` (default), `allow`, `ask_user`
- Destructive operations require explicit permission handler
- Default: commit and push blocked without handler

### 5. Output Sanitization

**Security Engineer Addition**:
- Redact credentials from remote URLs
- Sanitize output to hide embedded tokens/passwords

**Consensus**: Include credential redaction in implementation.

### 6. Timeout and Limits

**Agreed**:
- Default timeout: 30 seconds
- Maximum output lines: 500
- Integer argument limits (e.g., log -n max 100)

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/yoker/tools/git.py` | Create |
| `src/yoker/tools/__init__.py` | Export GitTool |
| `src/yoker/tools/path_guardrail.py` | Add "git" to `_FILESYSTEM_TOOLS` |
| `src/yoker/agent.py` | Register GitTool |
| `tests/test_tools/test_git.py` | Created (63 test stubs) |

## Implementation Checklist

1. [ ] Create `GitTool` class in `src/yoker/tools/git.py`
2. [ ] Implement operation allowlist validation
3. [ ] Implement argument sanitization
4. [ ] Implement permission checking
5. [ ] Implement PathGuardrail integration
6. [ ] Implement output sanitization (credential redaction)
7. [ ] Update `src/yoker/tools/__init__.py`
8. [ ] Update `src/yoker/tools/path_guardrail.py`
9. [ ] Update `src/yoker/agent.py`
10. [ ] Update test stubs to real assertions
11. [ ] Run `make test` to verify

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Command injection via flags | Reject args starting with `-`, use `--` delimiter |
| Config injection via `-c` | Block `-c` and `--config` options |
| Path traversal | PathGuardrail + realpath resolution |
| Credential exposure | Redact URLs in output |
| Shell escaping | List args, no shell=True |

## Approval

- [x] API Architect: Design approved
- [x] Security Engineer: Security measures sufficient
- [x] Testing Engineer: Test coverage adequate (63 tests)

**Status**: Ready for Phase 4 (Implementation)