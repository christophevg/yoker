# Security Analysis: Read Tool Hardening (Task 2.3)

**Document Version**: 1.0
**Date**: 2026-04-28
**Task**: 2.3 Read Tool from TODO.md
**Status**: Security Review Complete

---

## Summary

The ReadTool currently relies entirely on PathGuardrail inside Agent.process() for security boundary enforcement. While the PathGuardrail implementation is solid, ReadTool.execute() performs zero validation and blindly follows symlinks. This creates defense-in-depth failures: direct invocation of tool.execute() bypasses all access controls, and TOCTOU race conditions exist between guardrail validation and file read operations.

---

## Critical Findings

### 1. Authorization Bypass via Direct Tool Execution (HIGH)

ReadTool.execute() reads any path with no validation. PathGuardrail is only invoked in Agent.process(). If another component, test, or script calls ReadTool().execute(path="/etc/shadow"), all permission boundaries are bypassed.

**Remediation**: Embed guardrail validation directly into ReadTool.execute(). Require a Guardrail instance at tool construction time and validate inside execute() before reading.

### 2. TOCTOU Race Condition via Symlink Swapping (HIGH)

PathGuardrail.validate() resolves symlinks with os.path.realpath(), but ReadTool.execute() later calls Path(path_str).read_text(), which follows symlinks again. A malicious process can replace a symlink target between the guardrail check and the read operation.

**Remediation**: Re-resolve the path immediately before opening and assert it still falls within allowed roots. On Unix, prefer os.O_NOFOLLOW.

### 3. Size Limit TOCTOU (HIGH)

PathGuardrail._check_file_size() calls resolved.stat().st_size, then ReadTool.execute() calls Path.read_text(), loading the entire file into memory. Between stat() and read_text(), a file can be swapped for a much larger one.

**Remediation**: Stream-read in chunks with a cumulative byte limit. Abort if limit exceeded mid-read.

---

## Medium Findings

### 4. Blind Symlink Following When Guardrail Bypassed

Path.read_text() follows symlinks unconditionally. If any code path bypasses the guardrail, symlink-based path traversal is trivial.

**Remediation**: Add explicit symlink check inside ReadTool.execute() before reading. Make it configurable via ReadToolConfig.

### 5. Default Allowed Paths Overly Permissive

PermissionsConfig.filesystem_paths defaults to ("."). The current working directory may contain .ssh/, .aws/, .env, or other sensitive files.

**Remediation**: Change default to empty tuple () so no filesystem access is permitted unless explicitly configured.

### 6. Blocked Patterns Are Bypassable

Default blocked patterns use substring matching without word boundaries. Easily bypassed with variations like .env.local, secrets.bak.

**Remediation**: Expand default blocklist and apply patterns to individual path components.

---

## Low Findings

### 7. Encoding Not Specified

Path.read_text() uses platform default encoding. May cause UnicodeDecodeError on binary files or UTF-8 content.

**Remediation**: Use explicit encoding="utf-8", errors="replace".

### 8. Error Messages Leak Path Information

Error strings return raw path_str (e.g., "File not found: /home/user/.ssh/id_rsa").

**Remediation**: Return sanitized error messages to LLM. Log full path internally for debugging.

### 9. Missing Audit Trail Inside Tool

ReadTool.execute() does not log file access attempts.

**Remediation**: Add structlog logging inside ReadTool.execute() for every access attempt.

---

## Threat Model

| STRIDE | Threat | Status |
|--------|--------|--------|
| Tampering | Symlink swap between check and read | Missing |
| Information Disclosure | Direct tool.execute() reads any file | Missing |
| Denial of Service | Large file swap after size check | Missing |
| Elevation of Privilege | Subagent/plugin calls tool directly | Missing |
| Repudiation | No log of file access inside tool | Missing |

---

## Recommendations (Prioritized)

1. [HIGH] Embed guardrail into ReadTool
2. [HIGH] Stream-read with size enforcement (chunked reading)
3. [HIGH] Symlink hardening (reject or re-resolve)
4. [MEDIUM] Re-resolve before read
5. [MEDIUM] Tighten default configuration
6. [MEDIUM] Expand blocked patterns
7. [LOW] Specify UTF-8 encoding with replacement
8. [LOW] Sanitize error messages
9. [LOW] Add audit logging inside tools

---

## Test Cases for Security Validation

- Path traversal: ../../../etc/passwd
- Symlink outside allowed root
- Symlink swap race condition
- Direct invocation bypass (tool.execute without Agent)
- Blocked pattern variations (.env.local, secrets.bak)
- Extension filtering (.pem, .key)
- Size TOCTOU (file grows between check and read)
- Error message sanitization (no absolute paths leaked)

---

## Files Reviewed

- src/yoker/tools/read.py
- src/yoker/tools/path_guardrail.py
- src/yoker/agent.py
- src/yoker/tools/base.py
- src/yoker/tools/guardrails.py
- src/yoker/config/schema.py
- src/yoker/tools/list.py
