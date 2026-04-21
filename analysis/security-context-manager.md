# Security Analysis: Context Manager

**Date**: 2026-04-21
**Reviewer**: Security Engineer Agent
**Task**: Task 1.4 - Context Manager Security Review

## Executive Summary

The Context Manager component will persist sensitive conversation data to JSONL files. The current architecture has **no existing security controls** for file operations, session management, or data protection. Before implementation, critical security controls must be designed: path traversal prevention, secure session ID generation, atomic writes, and data sensitivity handling. The default `./context` storage path poses risks if deployed in production.

---

## Critical Findings (CVSS 9.0-10.0)

### 1. Path Traversal Vulnerability (OWASP A01:2025 - Broken Access Control)

**Location**: `ContextConfig.storage_path` and future `load()`/`save()` operations

**Impact**: An attacker controlling session IDs or storage paths could read/write arbitrary files on the system, potentially accessing sensitive system files or overwriting critical configurations.

**Current State**: The `session_id` field accepts any string value including `session_id = "../../../etc/passwd"` which, when combined with `storage_path`, could escape intended directories.

**Remediation**:
```python
# In context/validator.py (new file to create)
import secrets
from pathlib import Path

def validate_session_id(session_id: str, path: str) -> str:
  """Validate and sanitize session ID.
  
  Returns a secure session ID, generating one if 'auto'.
  Raises ValidationError for invalid/unsafe session IDs.
  """
  if session_id == "auto":
    return secrets.token_urlsafe(16)  # 128-bit secure random
  
  # Validate format: alphanumeric, dash, underscore only
  if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
    raise ValidationError(path, session_id, 
      "must contain only alphanumeric, dash, or underscore characters")
  
  # Prevent path traversal
  if '..' in session_id or '/' in session_id or '\\' in session_id:
    raise ValidationError(path, session_id,
      "must not contain path traversal characters")
  
  # Length limits to prevent DoS
  if len(session_id) > 128:
    raise ValidationError(path, session_id,
      "must not exceed 128 characters")
  
  return session_id
```

**Reference**: CWE-22 (Path Traversal), OWASP Path Traversal Prevention Cheat Sheet

---

### 2. Insecure Session ID Generation (OWASP A07:2025 - Authentication Failures)

**Location**: `ContextConfig.session_id = "auto"` implementation (not yet implemented)

**Impact**: Predictable session IDs enable session hijacking attacks where attackers can access other users' conversation history.

**Remediation**:
```python
# Use cryptographically secure random generation
import secrets

def generate_session_id() -> str:
  """Generate a cryptographically secure session ID.
  
  Uses 128 bits of entropy from secrets module.
  Returns URL-safe base64-encoded string.
  """
  return secrets.token_urlsafe(16)  # 22 characters, 128 bits
```

**Reference**: CWE-338 (Use of Cryptographically Weak PRNG), NIST SP 800-90A

---

## High Findings (CVSS 7.0-8.9)

### 3. Sensitive Data Exposure in Context Files (OWASP A04:2025 - Cryptographic Failures)

**Location**: `ContextConfig.storage_path = "./context"` - default persistence location

**Impact**: Context files will store:
- User prompts (potentially containing sensitive information)
- File contents read by tools
- API keys or credentials mentioned in conversation
- LLM responses

**Remediation**:

1. **File Permissions** - Set restrictive permissions on context files:
```python
import os
from pathlib import Path

def create_secure_context_file(path: Path) -> None:
  """Create context file with secure permissions."""
  # Create with 0600 (owner read/write only)
  fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
  os.close(fd)
  # Ensure directory has 0700
  path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
```

2. **Encryption-at-Rest** - Consider encryption for sensitive data (Phase 2)

3. **Data Minimization** - Redact sensitive patterns before persisting

**Reference**: OWASP ASVS V9 - Data Protection, NIST SP 800-111

---

### 4. Race Condition in File Writes (OWASP A08:2025 - Software/Data Integrity)

**Location**: Future context persistence implementation

**Impact**: Concurrent writes or process crashes can result in corrupted/partial JSONL files, leading to data loss or inconsistent state.

**Remediation**:
```python
import os
import tempfile
from pathlib import Path

def atomic_write_jsonl(path: Path, record: dict) -> None:
  """Atomically append a record to a JSONL file.
  
  Uses write-to-temp-then-rename pattern for atomicity.
  """
  # Create temp file in same directory for atomic rename
  fd, temp_path = tempfile.mkstemp(
    dir=path.parent,
    prefix='.tmp_',
    suffix='.jsonl'
  )
  
  try:
    with os.fdopen(fd, 'a') as f:
      f.write(json.dumps(record) + '\n')
    
    # Atomic rename (POSIX)
    temp_path_obj = Path(temp_path)
    temp_path_obj.rename(path)
  except Exception:
    # Clean up temp file on failure
    Path(temp_path).unlink(missing_ok=True)
    raise
```

**Reference**: CWE-367 (Time-of-check Time-of-use), OWASP File Upload Cheat Sheet

---

### 5. Subagent Context Isolation Failure (OWASP A01:2025 - Broken Access Control)

**Location**: Future `AgentRunner` implementation for subagent spawning

**Impact**: Subagents could access parent conversation context, leaking sensitive information or allowing prompt injection attacks.

**Remediation**:
```python
class ContextManager:
  """Context manager with isolation boundaries."""
  
  def create_subagent_context(
    self,
    subagent_id: str,
    allowed_tools: set[str]
  ) -> 'ContextManager':
    """Create isolated context for subagent.
    
    Returns a fresh context with no access to parent conversation.
    """
    sub_session_id = f"{self._session_id}_sub_{secrets.token_urlsafe(8)}"
    sub_storage_path = self._storage_path / "subagents" / sub_session_id
    
    # Create isolated context
    return ContextManager(
      session_id=sub_session_id,
      storage_path=sub_storage_path,
      isolation_level='clean'
    )
```

**Reference**: CWE-200 (Exposure of Sensitive Information), STRIDE Information Disclosure

---

## Medium Findings (CVSS 4.0-6.9)

### 6. Missing Error Handling for Corrupted Context Files

**Location**: Future context loading implementation

**Impact**: Malformed JSONL records can crash the application or cause unpredictable behavior.

**Remediation**: Implement safe loading with corruption handling and recovery.

---

### 7. Unbounded Context Growth

**Location**: ContextConfig lacks size/turn limits

**Impact**: Context files can grow indefinitely, leading to disk exhaustion (DoS) or memory issues during loading.

**Remediation**: Add configuration limits:
```python
@dataclass(frozen=True)
class ContextConfig:
  manager: str = "basic_persistence"
  storage_path: str = "./context"
  session_id: str = "auto"
  persist_after_turn: bool = True
  # New security-related fields:
  max_file_size_mb: int = 100
  max_turns: int = 1000
  retention_days: int = 30
```

---

### 8. Default Storage Path in Current Directory

**Location**: `ContextConfig.storage_path: str = "./context"`

**Impact**: Defaulting to current directory may:
- Create context files in version control (if .gitignore not configured)
- Persist sensitive data in project directories

**Remediation**: Use secure default path based on OS:
- Linux/Mac: `~/.local/share/yoker/context` (XDG)
- Windows: `%APPDATA%/yoker/context`
- Fallback: temp directory

---

## Low Findings (CVSS 0.1-3.9)

### 9. Missing Audit Logging

**Location**: ContextConfig lacks audit logging configuration

**Impact**: No visibility into context access patterns, making forensic analysis difficult.

**Remediation**: Add audit logging for context operations.

---

## STRIDE Threat Model for Context Storage

| Threat Category | Threat | Mitigation |
|----------------|--------|------------|
| **Spoofing** | Session ID prediction | Use `secrets.token_urlsafe()` for session IDs |
| **Tampering** | Context file manipulation | Atomic writes, file permissions (0600), integrity checks |
| **Repudiation** | Deny context access | Audit logging for all context operations |
| **Information Disclosure** | Sensitive data in context | Encryption-at-rest, data sanitization, secure permissions |
| **Denial of Service** | Disk exhaustion | Size limits, retention policies, space checks |
| **Elevation of Privilege** | Subagent context access | Strict isolation, sandboxed contexts |

---

## Recommendations (Prioritized)

### Immediate (Before Implementation)

1. Add `validate_session_id()` and `validate_storage_path()` to `config/validator.py`
2. Use `secrets.token_urlsafe(16)` for session ID generation
3. Implement atomic writes for JSONL persistence
4. Set file permissions (0600 for files, 0700 for directories)
5. Add `.gitignore` entry for `context/` directory

### Short-term (Phase 1)

1. Add data sanitization before persistence
2. Implement size/turn limits with cleanup
3. Add comprehensive error handling for corrupted files
4. Add audit logging for context operations

### Long-term (Phase 2+)

1. Add encryption-at-rest support
2. Implement retention policies and auto-cleanup
3. Add integrity verification (checksums)
4. Consider secure deletion (shred on delete)

---

## Key Files to Create/Modify

- `src/yoker/context/validator.py` - Session ID and path validation
- `src/yoker/context/basic.py` - Atomic write implementation
- `src/yoker/exceptions.py` - Add `SessionNotFoundError`, `ContextCorruptionError`
- `.gitignore` - Add `context/` entry

---

## Positive Observations

The project already has:
- Well-structured configuration schema (`frozen=True` dataclasses)
- Validation framework in `config/validator.py`
- Exception hierarchy (`YokerError`, `ConfigurationError`, `ValidationError`)
- Blocked patterns for sensitive files in `ReadToolConfig`