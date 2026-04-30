# Security Analysis: MkdirTool (Directory Creation)

**Document Version**: 1.0
**Date**: 2026-04-30
**Tool**: MkdirTool (`src/yoker/tools/mkdir.py`)
**Status**: Security Analysis Complete

---

## Executive Summary

The MkdirTool provides directory creation functionality with multi-layered security protections. While directory creation appears benign, it presents significant risks including path traversal, symlink exploitation, resource exhaustion through deep nesting, and filesystem information disclosure. The implementation uses defense-in-depth with PathGuardrail integration, explicit symlink rejection, depth limiting, and generic error messages to mitigate these threats.

**Risk Level**: **MEDIUM-HIGH** — Directory creation enables filesystem modification and can be exploited for privilege escalation, persistence mechanisms, or denial of service.

---

## Threat Model

### Attack Surface

| Vector | Risk | Mitigation | Implementation |
|--------|------|------------|----------------|
| Path traversal | Critical | PathGuardrail validation, realpath resolution | Lines 98-110, 141-149 |
| Symlink escape | Critical | Explicit symlink rejection before resolution | Lines 130-138 |
| Deep directory bombing | High | Depth limit from allowed root | PathGuardrail lines 372-402 |
| Resource exhaustion | Medium | Depth limiting, parent existence check | Lines 184-192 |
| Information disclosure | Medium | Generic error messages | Lines 138, 159, 223 |
| Race conditions | Low | Atomic operations, path resolution | Lines 195-201 |
| File overwrite | Medium | File vs directory check | Lines 152-160 |

### STRIDE Analysis

| Category | Threat | Mitigation |
|----------|--------|------------|
| **Spoofing** | Creating directories with misleading names | Blocked patterns for credential/secrets |
| **Tampering** | Modifying filesystem structure | PathGuardrail containment, depth limits |
| **Repudiation** | Unlogged directory creation | Structured logging on all operations |
| **Information Disclosure** | Error messages reveal filesystem state | Generic error messages |
| **Denial of Service** | Deep directory nesting, disk exhaustion | Depth limits (max_depth), parent existence check |
| **Elevation of Privilege** | Path traversal to privileged locations | PathGuardrail root containment, symlink rejection |

---

## Security Requirements

### 1. Path Containment (CRITICAL)

All paths must be validated through `PathGuardrail` to ensure containment within allowed directories:

```python
# PathGuardrail._is_within_allowed_paths() check
if self._guardrail is not None:
    validation = self._guardrail.validate(self.name, kwargs)
    if not validation.valid:
        return ToolResult(success=False, error=validation.reason)
```

### 2. Symlink Rejection (CRITICAL)

Symlinks must be rejected BEFORE path resolution to prevent escape via symlink chains:

```python
# MkdirTool.execute() - Line 130-138
original_path = Path(path_str)
if original_path.is_symlink():
    log.warning("mkdir_symlink_rejected", path=path_str)
    return ToolResult(
        success=False,
        error="Path not accessible",  # Generic message
    )
```

### 3. Depth Limiting (HIGH)

Directory depth from allowed root must be limited to prevent deep nesting attacks:

```python
# PathGuardrail._check_mkdir_depth() - Lines 372-402
max_depth = mkdir_config.max_depth  # Default: 20
for root in self._allowed_roots:
    try:
        relative = resolved.relative_to(root)
        depth = len(relative.parts)
        if depth >= max_depth:
            return f"Path depth exceeds limit: {depth} >= {max_depth}"
```

### 4. Blocked Pattern Matching (HIGH)

Sensitive path patterns are blocked to prevent creating directories that could shadow security-critical files:

```python
blocked_patterns: tuple[str, ...] = (
    r"\.env",           # Environment files
    r"\.git",           # Git directories
    r"\.ssh",           # SSH directories
    r"\.aws",           # AWS credentials
    r"\.gnupg",         # GPG keys
    "credentials",      # Credential files
    r"secrets?",        # Secret files
)
```

### 5. Generic Error Messages (MEDIUM)

All security-sensitive errors return generic messages to prevent information disclosure:

| Condition | Error Message |
|-----------|---------------|
| Symlink detected | "Path not accessible" |
| Path is a file | "Path not accessible" |
| Permission denied | "Permission denied" |
| Parent missing | "Parent directory does not exist" |
| Guardrail blocked | Guardrail reason (informative but contained) |

### 6. Idempotent Behavior (MEDIUM)

Existing directory returns success, not error - matching `mkdir -p` semantics.

### 7. File vs Directory Check (MEDIUM)

Reject creation when path is already a file to prevent confusion and potential symlink placement.

---

## Implementation Security Checklist

| Item | Priority | Status | Location |
|------|----------|--------|----------|
| PathGuardrail integration | P0 | Implemented | Lines 98-110 |
| Symlink rejection | P0 | Implemented | Lines 130-138 |
| Path resolution (realpath) | P0 | Implemented | Lines 141-149 |
| Blocked pattern matching | P0 | Implemented | PathGuardrail |
| Depth limit enforcement | P0 | Implemented | PathGuardrail lines 372-402 |
| Generic error messages | P1 | Implemented | Lines 138, 159, 223 |
| File vs directory check | P1 | Implemented | Lines 152-160 |
| Parent existence check (non-recursive) | P1 | Implemented | Lines 184-192 |
| Idempotent success (existing dir) | P1 | Implemented | Lines 161-175 |

---

## OWASP Top 10:2025 Mapping

| Category | Relevance to MkdirTool |
|----------|------------------------|
| **A01: Broken Access Control** | Path containment, root validation |
| **A02: Security Misconfiguration** | Depth limits, blocked patterns |
| **A05: Injection** | Path traversal as injection vector |
| **A06: Insecure Design** | Idempotent design, error handling |
| **A08: Software/Data Integrity** | Filesystem integrity protection |

---

## CWE References

| CWE | Description | Mitigation |
|-----|-------------|------------|
| **CWE-22** | Path Traversal | PathGuardrail, realpath resolution |
| **CWE-23** | Relative Path Traversal | realpath resolution, root containment |
| **CWE-36** | Absolute Path Traversal | PathGuardrail root validation |
| **CWE-41** | Improper Resolution of Path Equivalence | realpath normalization |
| **CWE-59** | Improper Link Resolution Before File Access | Symlink rejection |
| **CWE-200** | Exposure of Sensitive Information | Generic error messages |
| **CWE-400** | Uncontrolled Resource Consumption | Depth limiting |

---

## Configuration Reference

```toml
[tools.mkdir]
enabled = true
max_depth = 20  # Maximum depth from allowed root

[permissions]
filesystem_paths = [".", "/safe/project/path"]
```

---

## References

- **OWASP Path Traversal**: https://owasp.org/www-community/attacks/Path_Traversal
- **CWE-22**: Improper Limitation of a Pathname to a Restricted Directory
- **CWE-59**: Improper Link Resolution Before File Access
- **OWASP A01:2025**: Broken Access Control
- **OWASP A05:2025**: Injection (Path Traversal)