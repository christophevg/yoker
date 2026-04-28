# API Review: Read Tool Hardening (Task 2.3)

**Date**: 2026-04-28
**Reviewer**: API Architect Agent
**Task**: Review implementation of guardrail injection, Tool ABC changes, error handling, and test structure for ReadTool hardening.

## Summary

The implementation adds defense-in-depth validation to filesystem tools (primarily `ReadTool`) by:
1. Adding an optional `guardrail` parameter to the `Tool` ABC `__init__`
2. Injecting `PathGuardrail` into tools from `Agent._build_tool_registry()`
3. Validating tool parameters both in `Agent.process()` (primary) and in `tool.execute()` (redundant)
4. Hardening `ReadTool` with symlink rejection, UTF-8 encoding, path resolution, and sanitized error messages
5. Updating `ListTool` to match the guardrail pattern

All 293 tests pass. Typecheck and lint pass.

## Findings

### 1. Guardrail Injection Pattern

**Status: APPROVED with minor note**

The pattern is clean and follows dependency injection best practices:
- `Tool.__init__(guardrail=None)` is backward-compatible
- `Agent._build_tool_registry()` creates tools with `guardrail=self._guardrail`
- Tools check `self._guardrail` in `execute()` before I/O
- Validation happens at two layers: `Agent.process()` (primary) and `tool.execute()` (defense-in-depth)

**Note on double validation**: With the current `Agent.process()` implementation, guardrail validation is performed before `tool.execute()` is called. When the tool also has a guardrail, validation runs twice. This is intentional defense-in-depth but adds a small overhead. The consensus design acknowledges this trade-off.

### 2. Tool ABC Backward Compatibility

**Status: APPROVED**

The change is fully backward-compatible:
- `guardrail` parameter defaults to `None`
- Existing code instantiating `ReadTool()`, `ListTool()` continues to work unchanged
- `create_default_registry()` in `tools/__init__.py` still works without guardrails
- No breaking changes to `execute()`, `get_schema()`, `name`, or `description` signatures

### 3. Error Messages

**Status: APPROVED for ReadTool, FLAG inconsistency with ListTool**

**ReadTool error messages are excellent**:
- Sanitized: no resolved paths leaked to LLM (e.g., "File not found", "Permission denied")
- Internal logging captures full paths for debugging
- Clear, actionable messages for the LLM

**Inconsistency flagged**: `ListTool` still includes raw paths in some errors:
- `ListTool`: `f"Path not found: {path_str}"`
- `ReadTool`: `"File not found"` (sanitized)

For API consistency across filesystem tools, `ListTool` should adopt the same sanitized error pattern.

### 4. Test Structure

**Status: APPROVED with minor note**

**Strengths**:
- `FakeGuardrail` inline in unit tests is a clean testing pattern
- Separation of unit tests (`test_read.py`) and integration tests (`test_read_guardrail.py`) is good
- `test_read_sanitizes_error_messages` directly tests the security requirement
- `test_read_rejects_symlink` covers a key hardening feature
- Tests are consistent with `test_list.py` patterns (class-based, descriptive names)

**Minor note**: The `restricted_config` fixture in `test_read_guardrail.py` uses `type()` to create dummy tool configs. This is pragmatic given the frozen dataclass schema, but if the config schema changes, these dummy types may break. Consider using actual config dataclasses or a factory helper.

### 5. Symlink Handling Inconsistency

**Status: FLAG for follow-up**

`ReadTool` unconditionally rejects symlinks at the top level. `ListTool` does NOT reject a symlink passed as the root `path` parameter - it would follow it into the target directory. The `_build_tree()` method correctly does not follow symlinks during recursion, but the root path check is missing.

For defense-in-depth consistency, `ListTool.execute()` should also reject symlink root paths (or at least not follow them).

### 6. Guardrail.validate() Error Messages

**Status: ACCEPTABLE with note**

`PathGuardrail.validate()` returns error messages that include the original `path_param` (e.g., `"Path outside allowed directories: {path_param}"`). Since this is the path the LLM itself requested, it does not leak unknown filesystem structure - it only echoes back the input. This is acceptable and actually helpful for debugging from the LLM's perspective.

## Recommendations (Prioritized)

1. **LOW - ListTool error sanitization**: Update `ListTool` error messages to match `ReadTool` sanitized pattern (remove raw paths from user-facing errors, keep them in logs).

2. **LOW - ListTool symlink root path handling**: Add symlink rejection for the root path in `ListTool.execute()` to match `ReadTool` behavior.

3. **LOW - Config fixture robustness**: Consider using actual `Config` dataclass instances or a test factory instead of `type()` dynamic class creation in integration test fixtures.

## Conclusion

**APPROVED** for merge. The guardrail injection pattern is well-designed, backward-compatible, and achieves defense-in-depth. Error handling in `ReadTool` is appropriately sanitized. Test coverage is thorough and structure is consistent with project patterns.

Two minor follow-up items are flagged for `ListTool` consistency but are out of scope for the Read Tool Hardening task.

## Action Items

- [ ] (Optional) Sanitize `ListTool` error messages to match `ReadTool`
- [ ] (Optional) Add symlink rejection for root path in `ListTool`
- [ ] (Optional) Refactor `restricted_config` fixture to use real config objects
