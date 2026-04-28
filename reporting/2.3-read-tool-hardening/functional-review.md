# Functional Review: Task 2.3 - Read Tool Hardening

## Review Summary

**Status: PASS**

All task requirements from TODO.md have been met. The implementation correctly hardens the previously vulnerable ReadTool via defense-in-depth with the shared PathGuardrail, adds all required security features, and includes comprehensive unit and integration tests. The consensus design (optional guardrail in tool + agent-level validation) is fully realized.

---

## Requirements Verification

### Functional Requirements (from TODO.md)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Implement file reading functionality | PASS | `ReadTool.execute()` reads file contents via `Path.read_text()` |
| Add path restriction guardrails | PASS | `PathGuardrail._is_within_allowed_paths()` uses `relative_to()` against configured roots |
| Add file extension filtering | PASS | `PathGuardrail._check_read_extension()` validates against `ReadToolConfig.allowed_extensions` |
| Add size limit enforcement | PASS | `PathGuardrail._check_file_size()` validates against `PermissionsConfig.max_file_size_kb` |
| Add blocked pattern matching (e.g., .env) | PASS | `PathGuardrail._check_blocked_patterns()` uses pre-compiled regex from `ReadToolConfig.blocked_patterns` |
| Write unit tests | PASS | `tests/tools/test_read.py` (14 tests) + `tests/tools/test_read_guardrail.py` (11 tests) |
| Must use shared PathGuardrail | PASS | `PathGuardrail` instantiated once in `Agent.__init__()` and injected into both `ReadTool` and `ListTool` |
| Harden critically vulnerable ReadTool | PASS | Zero-validation tool replaced with multi-layer validation (guardrail + symlink rejection + path resolution + sanitized errors) |

### Consensus Design Alignment: Defense-in-Depth with Optional Guardrail in Tool

| Design Principle | Status | Evidence |
|------------------|--------|----------|
| Guardrail is optional in Tool base class | PASS | `Tool.__init__(guardrail: Guardrail | None = None)` - defaults to None |
| Agent validates before tool execution | PASS | `Agent.process()` lines 363-368 call `self._guardrail.validate()` before `tool.execute()` |
| Tool validates internally if guardrail provided | PASS | `ReadTool.execute()` lines 92-104 call `self._guardrail.validate()` as first step |
| Guardrail shared across filesystem tools | PASS | Same `PathGuardrail` instance injected into `ReadTool` and `ListTool` in `_build_tool_registry()` |
| Tools work without guardrail (backward compat) | PASS | `ReadTool()` without guardrail still validates existence, symlinks, files via internal checks |

---

## Code Evidence

### Defense-in-Depth Validation Flow

```
Agent.process()                     ReadTool.execute()
    |                                      |
    | 1. Guardrail.validate()              | 2. Guardrail.validate()
    |    (agent-level enforcement)         |    (tool-level enforcement)
    |                                      |
    | If blocked -> return error           | If blocked -> return error
    |                                      |
    | If allowed -> tool.execute()         | If allowed -> continue to I/O
    |                                      |
    |                                      | 3. Symlink rejection
    |                                      | 4. Path resolution (realpath)
    |                                      | 5. Existence check
    |                                      | 6. File type check
    |                                      | 7. Read with encoding
```

Both agent and tool independently validate, ensuring the tool is safe even when used outside the Agent flow (e.g., direct API usage, testing, future contexts).

### ReadTool Hardening (src/yoker/tools/read.py)

| Layer | Lines | Purpose |
|-------|-------|---------|
| Guardrail validation | 92-104 | First line of defense - permission boundaries |
| Symlink rejection | 107-114 | Prevents traversal via symlinks before resolution |
| Path resolution | 117-125 | `os.path.realpath()` normalizes and resolves `..` components |
| Existence check | 128-134 | Confirms resolved path exists |
| File type check | 136-142 | Ensures path is a file, not directory |
| Encoding safety | 146 | `encoding="utf-8", errors="replace"` prevents crashes on binary data |
| Error sanitization | 128-166 | Generic error messages without path leakage to LLM |
| Audit logging | 95-99, 147-151 | Internal logging with full paths for debugging |

### PathGuardrail Security (src/yoker/tools/path_guardrail.py)

| Check | Method | Lines |
|-------|--------|-------|
| Allowed roots containment | `_is_within_allowed_paths()` | 154-169 |
| Blocked regex patterns | `_check_blocked_patterns()` | 171-184 |
| Extension filtering | `_check_read_extension()` | 186-206 |
| Size limit enforcement | `_check_file_size()` | 208-231 |
| Path resolution (symlink traversal prevention) | `_resolve_path()` | 136-152 |

---

## Test Coverage

### Unit Tests (`tests/tools/test_read.py`)

| Test | What It Verifies |
|------|-----------------|
| `test_name` | Tool registration name is "read" |
| `test_description` | Description contains "Read" |
| `test_schema` | Schema has `path` parameter, required fields, function metadata |
| `test_read_existing_file` | Basic file reading works |
| `test_read_missing_file` | Missing file returns `success=False` with "not found" |
| `test_read_result_is_toolresult` | Return type is always `ToolResult` |
| `test_read_with_guardrail_blocks` | Guardrail block is respected, reason propagated |
| `test_read_with_guardrail_allows` | Guardrail allow passes through to I/O |
| `test_read_rejects_symlink` | ALL symlinks rejected unconditionally |
| `test_read_encoding_utf8` | UTF-8 content read correctly |
| `test_read_encoding_with_invalid_bytes` | Invalid bytes replaced, not crashed |
| `test_read_sanitizes_error_messages` | Error messages do not contain full paths (tool-level errors) |
| `test_read_resolves_path` | Relative paths with `..` resolved correctly |
| `test_read_not_a_file` | Directory path returns "not a file" |
| `test_read_permission_denied` | `PermissionError` caught, sanitized message returned |

### Integration Tests (`tests/tools/test_read_guardrail.py`)

| Test | What It Verifies |
|------|-----------------|
| `test_allowed_path_allows` | Files within allowed paths succeed |
| `test_path_traversal_blocked` | `../../../etc/passwd` traversal blocked |
| `test_blocked_pattern_env_blocked` | `.env` file blocked by regex pattern |
| `test_blocked_pattern_secret_blocked` | Files with "secret" in name blocked |
| `test_extension_filtering_blocked` | `.pem` extension blocked when not in allowed list |
| `test_extension_filtering_allowed` | `.md` extension allowed when in list |
| `test_size_limit_blocked` | 20KB file blocked when limit is 10KB |
| `test_symlink_outside_root_blocked` | Symlink to outside path blocked (guardrail resolves target) |
| `test_absolute_path_outside_blocked` | Absolute paths outside allowed roots blocked |
| `test_empty_path_blocked` | Empty path parameter blocked |
| `test_no_guardrail_tool_validates_internally` | Tool without guardrail still does basic validation |

---

## Edge Cases Handled

| Edge Case | Handling | Verified By |
|-----------|----------|-------------|
| Empty path string | Guardrail blocks; without guardrail resolves to cwd then blocked by `is_file()` | `test_empty_path_blocked`, implicit in `test_read_not_a_file` |
| Relative path traversal (`../..`) | `os.path.realpath()` resolves; guardrail checks resolved path | `test_path_traversal_blocked` |
| Symlink to allowed path | Rejected by ReadTool before guardrail sees it | `test_read_rejects_symlink` |
| Symlink to outside path | Guardrail resolves target and blocks | `test_symlink_outside_root_blocked` |
| Invalid UTF-8 bytes | `errors="replace"` substitutes replacement character | `test_read_encoding_with_invalid_bytes` |
| Permission denied on read | Caught, sanitized error returned | `test_read_permission_denied` |
| Non-existent file | Guardrail blocks (if configured); tool returns "File not found" | `test_read_missing_file`, `test_allowed_path_allows` |
| Path is a directory | Returns "Path is not a file" | `test_read_not_a_file` |
| Binary file | Read as text with replacement characters | Implicit via `errors="replace"` |
| Large files | Guardrail checks size before reading | `test_size_limit_blocked` |

---

## File Modifications

### `/Users/xtof/Workspace/agentic/yoker/src/yoker/tools/base.py`

| Change | Lines | Purpose |
|--------|-------|---------|
| Added `guardrail` parameter to `Tool.__init__()` | 83-89 | Enables optional guardrail injection for defense-in-depth |

### `/Users/xtof/Workspace/agentic/yoker/src/yoker/tools/read.py`

| Change | Lines | Purpose |
|--------|-------|---------|
| Added `guardrail` parameter to `__init__()` | 32-38 | Accepts optional guardrail |
| Added guardrail validation in `execute()` | 91-104 | Defense-in-depth validation layer |
| Added symlink rejection | 107-114 | Prevents symlink traversal attacks |
| Added path resolution via `os.path.realpath()` | 117-125 | Normalizes paths, resolves `..` components |
| Added explicit UTF-8 encoding with replacement | 146 | Safe text reading for all file types |
| Added sanitized error messages | 128-166 | No path leakage to LLM on I/O errors |
| Added structured logging | 95-151 | Audit trail for security events |

### `/Users/xtof/Workspace/agentic/yoker/src/yoker/tools/list.py`

| Change | Lines | Purpose |
|--------|-------|---------|
| Added `guardrail` parameter to `__init__()` | 36-42 | Matches ReadTool pattern |
| Added guardrail validation in `execute()` | 117-130 | Defense-in-depth for list operations |

### `/Users/xtof/Workspace/agentic/yoker/src/yoker/agent.py`

| Change | Lines | Purpose |
|--------|-------|---------|
| Added PathGuardrail initialization | 123-125 | Creates shared guardrail from config |
| Injected guardrail into tools in `_build_tool_registry()` | 174-177 | Both ReadTool and ListTool get same guardrail instance |

### Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `tests/tools/test_read.py` | 14 | Unit tests for ReadTool in isolation |
| `tests/tools/test_read_guardrail.py` | 11 | Integration tests with real PathGuardrail |

---

## Design Decisions

### 1. Defense-in-Depth: Tool-Level + Agent-Level Validation

The consensus design is fully implemented: tools optionally accept a guardrail and validate internally, while the Agent also validates before calling the tool. This creates two independent security boundaries.

**Rationale**: Tools may be used outside the Agent context (direct API, tests, future runners). Tool-level validation ensures safety regardless of caller.

### 2. Unconditional Symlink Rejection in ReadTool

ReadTool rejects ALL symlinks before resolution, regardless of where they point. This is stricter than the guardrail, which resolves symlinks and validates the target.

**Rationale**: Reading through symlinks is a common attack vector. For a read tool, the security benefit of blanket symlink rejection outweighs the convenience of following benign symlinks. ListTool does not reject symlinks at the top level because listing a symlink directory is a different risk profile.

### 3. Sanitized Error Messages

ReadTool returns generic messages like "File not found" and "Permission denied" without embedding the requested path. However, guardrail validation reasons (passed through from PathGuardrail) may contain the original path parameter.

**Trade-off**: The tool's own I/O errors are fully sanitized. Guardrail reasons are intentionally informative for the LLM to understand why access was denied. Full sanitization of guardrail reasons would reduce agent self-correction capability.

### 4. Explicit UTF-8 with Replacement

`resolved.read_text(encoding="utf-8", errors="replace")` ensures the tool never crashes on binary files and always returns a string result.

**Rationale**: The LLM consumes text. Returning a string with replacement characters is more useful than raising an exception or returning raw bytes.

---

## Verification Commands

```bash
# All tests pass
make test

# Type checking passes
make typecheck

# Linting passes
make lint

# Prototype starts correctly
python -m yoker --help
```

---

## Issues Found

**None blocking.**

### Minor Observation: Guardrail Error Messages Contain Paths

PathGuardrail validation reasons include the original `path_param` value (e.g., "Path outside allowed directories: /etc/passwd"). These are passed through to the LLM when the guardrail blocks at the tool level. This is acceptable for debugging and agent self-correction, but represents a partial (not total) sanitization.

**Impact**: Low. The path shown is the one the LLM already requested.
**Recommendation**: If stronger sanitization is needed in the future, sanitize `validation.reason` in ReadTool before returning it to the LLM.

---

## Recommendations

1. **Consider symlink configuration**: If future use cases require reading symlinks within allowed paths, consider adding a `follow_symlinks` configuration option (default `False`) rather than unconditionally rejecting all symlinks.

2. **Add test for guardrail error sanitization**: If total path sanitization becomes a requirement, add a test that verifies the resolved path does not appear in `result.error` even when blocked by a real PathGuardrail.

3. **Schema parameter completeness**: The functional analysis (Section 3.2.1) mentions optional `offset` and `limit` parameters for line-based reading. These are not in scope for the hardening task but could be added in a future enhancement.

---

## Conclusion

**PASS** - Task 2.3 is complete and ready for marking as done.

All acceptance criteria verified:
- ReadTool hardened with multi-layer validation
- Shared PathGuardrail used for path restrictions, extension filtering, size limits, and blocked patterns
- Defense-in-depth architecture realized (agent-level + tool-level validation)
- Symlinks rejected before resolution
- Paths resolved with `os.path.realpath()`
- Explicit UTF-8 encoding with safe fallback
- Error messages sanitized for I/O errors
- Comprehensive unit and integration tests cover all security boundaries
- Prototype remains functional
- All 293 tests pass
- Typecheck and lint pass

The implementation aligns with the consensus design of defense-in-depth with optional guardrail in tool.
