# Consensus Summary: PathGuardrail Implementation (Task 2.1.5)

## Date
2026-04-23

## Status
APPROVED for implementation. Both domain agents agree on the need for a shared PathGuardrail before implementing ListTool.

## Agents Involved
- api-architect (a1c5e7176a359d187)
- security-engineer (a7a1d77c356d9ed2f)

## Key Decisions

### 1. Shared PathGuardrail Required (Security)
Both agents agree that a shared `PathGuardrail` must be implemented before `ListTool`. The security agent identified that the current `ReadTool` has zero validation and can read any file on the filesystem. The api-architect recommended a shared guardrail that can be reused across all filesystem tools (read, list, write, update, search).

### 2. Guardrail Integration Point (API)
The api-architect recommends that tools do NOT call guardrails themselves; instead, the future `PermissionEnforcer` (or `Agent.process()`) should validate before `execute()`. The security agent agrees and specifically recommends wiring guardrail validation into `Agent.process()` before `tool.execute()`.

### 3. Path Resolution Strategy (Security)
Both agents agree on:
- Resolve input paths with `os.path.realpath()` to collapse `..` and resolve symlinks for validation
- Validate resolved path is within `config.permissions.filesystem_paths`
- Do not follow symlinks during directory recursion (`followlinks=False`)
- Apply blocked patterns to both file and directory names

### 4. Default Values (API + Security)
| Parameter | Default | Source |
|-----------|---------|--------|
| max_depth | 1 (ListTool), 5 (absolute max) | API design |
| max_entries | 1000 (ListTool), 2000 (absolute max) | API design |
| filesystem_paths | ("."), not empty | Security recommendation |
| blocked_patterns | See security analysis | Security recommendation |

### 5. Pattern Style (API)
The api-architect recommends glob-style patterns (using `fnmatch`) rather than regex for LLM friendliness. The security agent recommends regex patterns (as configured in `config.schema.py`). **Consensus**: Use regex patterns (as already configured in the schema) for guardrails, but glob-style for the `pattern` parameter in `ListTool`.

## Security Findings Accepted

1. **Critical**: ReadTool has zero validation and must be hardened before ListTool is released
2. **Critical**: Guardrail ABC exists but is never invoked — dead code
3. **High**: Path traversal possible without proper path resolution and validation
4. **High**: Symlink traversal is a bypass vector for path restrictions
5. **Medium**: Default empty `filesystem_paths` is ambiguous and dangerous

## Implementation Order

1. Implement `PathGuardrail` concrete class in `src/yoker/tools/guardrails.py`
2. Wire guardrail validation into `Agent.process()`
3. Add structured logging for guardrail decisions
4. Update `ReadTool` to work with guardrail enforcement
5. Verify all tests pass
6. Then proceed to task 2.2 ListTool

## Files to Modify

- `src/yoker/tools/guardrails.py` - Add PathGuardrail implementation
- `src/yoker/agent.py` - Wire guardrail into `Agent.process()`
- `src/yoker/tools/read.py` - Update to use guardrail (or at least be compatible)
- `src/yoker/config/schema.py` - Review defaults (filesystem_paths should be ("."))
- `tests/` - Add guardrail unit tests

## Next Steps

Proceed to Phase 4: Plan Mode for task 2.1.5 (PathGuardrail Implementation).
