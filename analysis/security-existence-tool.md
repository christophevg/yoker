# Security Analysis: Existence Tool (Task 2.8)

**Document Version**: 1.0
**Date**: 2026-04-29
**Task**: 2.8 File Existence Tool from TODO.md
**Status**: Security Analysis Complete

---

## Executive Summary

The Existence Tool provides boolean file/folder existence checking functionality with path restriction guardrails. While simpler than read/write tools, existence checks still present significant information disclosure risks. An attacker can use existence probes to enumerate filesystem structure, discover hidden files, infer application configuration, and validate paths for subsequent attacks. The shared PathGuardrail provides core protection, but additional safeguards are needed to prevent oracle-based attacks.

**Risk Level**: **MEDIUM** — Existence probes enable filesystem enumeration and serve as reconnaissance for more serious attacks.

---

## Threat Model

### Attack Surface

| Vector | Risk | Mitigation |
|--------|------|------------|
| Path traversal | High | PathGuardrail validation |
| Symlink escape | High | Explicit symlink rejection |
| Existence oracle | Medium | Protected patterns, rate limiting |
| Timing side-channel | Low | Constant-time delays |
| Information disclosure | Medium | Generic error messages |

### STRIDE Analysis

| Category | Threat | Mitigation |
|----------|--------|------------|
| **Information Disclosure** | Filesystem enumeration via existence oracle | Protected patterns, rate limiting |
| **Denial of Service** | High-volume existence checks | Rate limiting |
| **Elevation of Privilege** | Symlink traversal | Symlink rejection, lstat() usage |

---

## Security Requirements

### 1. Path Validation (CRITICAL)

All paths must be validated through `PathGuardrail`:

```python
# Add to _FILESYSTEM_TOOLS in path_guardrail.py
_FILESYSTEM_TOOLS = frozenset({"read", "list", "write", "update", "search", "existence"})
```

### 2. Symlink Rejection (HIGH)

Symlinks must be rejected to prevent path traversal:

```python
if path.is_symlink():
    return ToolResult(success=False, error="Symlink paths are not permitted")
```

**Why**: Symlinks can point outside allowed directories even after realpath resolution.

### 3. Protected Pattern Blocking (HIGH)

Block existence checks for sensitive paths:

```python
PROTECTED_PATTERNS = (
    r"\.env",           # Environment files
    r"\.git",           # Git directories
    r"\.ssh",           # SSH keys
    r"\.aws",           # AWS credentials
    r"credentials",     # Credential files
    r"secrets?",        # Secret files
    r"\.pem$",          # Certificates
    r"\.key$",          # Key files
    r"id_rsa",          # SSH private keys
    r"\.bak$",          # Backup files
)
```

### 4. Timing Attack Protection (MEDIUM)

Add constant-time delays to prevent timing inference:

```python
MIN_DELAY_MS = 5  # Minimum delay to obscure timing differences

def constant_time_exists(path: Path) -> bool:
    start = time.monotonic()
    # ... existence check ...
    elapsed = (time.monotonic() - start) * 1000
    if elapsed < MIN_DELAY_MS:
        time.sleep((MIN_DELAY_MS - elapsed) / 1000)
```

### 5. Error Message Sanitization (MEDIUM)

Return generic error messages to prevent information leakage:

```python
def sanitize_error(error: Exception) -> str:
    error_map = {
        FileNotFoundError: "Path not found",
        PermissionError: "Access denied",
        OSError: "Path check failed",
    }
    return error_map.get(type(error), "Unable to check path")
```

---

## Implementation Security Checklist

| Item | Priority | Status |
|------|----------|--------|
| PathGuardrail integration | P0 | Required |
| Symlink rejection | P0 | Required |
| Protected pattern blocking | P0 | Required |
| Generic error messages | P1 | Required |
| Timing attack protection | P1 | Recommended |
| Rate limiting | P2 | Future |
| Audit logging | P2 | Recommended |

---

## Test Cases for Security

| Test | Input | Expected |
|------|-------|----------|
| Path traversal | `../../../etc/passwd` | Blocked by guardrail |
| Symlink outside root | Symlink to `/etc/shadow` | Rejected |
| Protected pattern | `.env` | Blocked |
| Protected pattern | `credentials.json` | Blocked |
| Timing consistency | Multiple paths | Response times similar |
| Direct execution bypass | `ExistenceTool().execute(path="/etc/shadow")` | Blocked with guardrail |
| Error message leakage | Non-existent sensitive path | Generic "path not found" |

---

## Key Differences from Other Tools

| Tool | Reads Content | Modifies | Existence Risk |
|------|--------------|----------|----------------|
| ReadTool | Yes | No | High (data exfiltration) |
| WriteTool | No | Yes | High (file modification) |
| ExistenceTool | No | No | Medium (information disclosure) |

The Existence Tool has lower direct risk but enables reconnaissance for other attacks.

---

## References

- **CWE-200**: Exposure of Sensitive Information
- **CWE-385**: Covert Timing Channel
- **CWE-59**: Improper Link Resolution Before File Access
- **OWASP A01**: Broken Access Control