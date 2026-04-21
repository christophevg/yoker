# Consensus Report: Context Manager Implementation

**Date**: 2026-04-21
**Task**: 1.4 - Context Manager
**Agents**: API Architect, Security Engineer

## Summary

Both domain agents reviewed the Context Manager design and provided complementary perspectives:

| Agent | Focus | Key Deliverable |
|-------|-------|-----------------|
| API Architect | Interface design, JSONL format, integration | `analysis/api-context-manager.md` |
| Security Engineer | Security controls, data protection, threats | `analysis/security-context-manager.md` |

**Overall Status**: ✅ Approved for implementation with resolved recommendations.

---

## Key Decisions

### 1. Session ID Generation

**API Architect**: UUID v4 (`uuid.uuid4()`)
**Security Engineer**: `secrets.token_urlsafe(16)`

**Resolution**: Use `secrets.token_urlsafe(16)` (128-bit cryptographically secure random).

**Rationale**:
- More secure (cryptographically random vs. pseudo-random)
- URL-safe (no encoding issues in filenames)
- Same entropy as UUID v4 (128 bits)
- Recommended by OWASP and NIST

---

### 2. Interface Methods

**Agreement**: Add the following methods to ContextManager interface:

| Method | Purpose | Priority |
|--------|---------|----------|
| `get_session_id()` | Query current session ID | High |
| `clear()` | Reset context for subagent isolation | High |
| `close()` | Resource cleanup | High |
| `start_turn(message)` | Turn boundary tracking | Medium |
| `end_turn(response, tool_calls_count)` | Statistics tracking | Medium |
| `get_messages(role)` | Filter messages by role | Low |

---

### 3. JSONL Format

**Agreement**: Use typed records with these types:

1. `session_start` - Session metadata (model, config, parent_session_id for subagents)
2. `message` - User/assistant/tool messages with sequence numbers
3. `turn` - Statistics boundaries (tokens, timing)
4. `session_end` - Summary statistics

**File naming**: `{storage_path}/{session_id}.jsonl`

---

### 4. Security Controls

**Agreement**: Implement these security controls immediately:

| Control | Implementation | Priority |
|---------|----------------|----------|
| Session ID validation | Alphanumeric, dash, underscore only | Critical |
| Path traversal prevention | Validate no `..`, `/`, `\` in session_id | Critical |
| Secure file permissions | 0600 for files, 0700 for directories | High |
| Atomic writes | Write-to-temp-then-rename pattern | High |
| Error handling | Graceful handling of corrupted JSONL | Medium |
| Size limits | max_file_size_mb, max_turns | Medium |

---

### 5. Context Isolation for Subagents

**Agreement**: Subagents get completely fresh context (no parent inheritance).

**Implementation**:
- `create_subagent_context()` method on ContextManager
- Generates new session_id: `{parent_id}_sub_{random}`
- Stores in separate directory: `{storage_path}/subagents/{sub_session_id}.jsonl`
- `session_start` record includes `parent_session_id` for traceability

---

### 6. Token Counting

**API Architect**: Integrate with backend provider for accurate token counting.
**Security Engineer**: Not addressed.

**Resolution**: Defer to Phase 1. MVP uses message counts only (no token counting).

**Rationale**:
- Token counting requires backend provider integration
- MVP focus is on persistence and isolation
- Message counts sufficient for basic statistics

---

## Implementation Plan

### Phase 1: Core Module Structure

```
src/yoker/context/
  __init__.py          # Public API: ContextManager, ContextStatistics, create_context_manager
  interface.py         # ContextManager protocol, ContextStatistics dataclass
  basic.py             # BasicPersistenceContextManager implementation
  validator.py         # validate_session_id, validate_storage_path
  exceptions.py        # SessionNotFoundError, ContextCorruptionError
```

### Phase 2: Implementation Details

#### `interface.py` - ContextManager Protocol

```python
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class ContextManager(Protocol):
    """Interface for context management strategies."""
    
    def get_session_id(self) -> str: ...
    def add_message(self, role: str, content: str, ...) -> None: ...
    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str, ...) -> None: ...
    def get_context(self) -> list[dict[str, Any]]: ...
    def get_messages(self, role: str | None = None) -> list[dict[str, Any]]: ...
    def start_turn(self, message: str) -> None: ...
    def end_turn(self, response: str, tool_calls_count: int = 0) -> None: ...
    def save(self) -> None: ...
    def load(self, session_id: str) -> None: ...
    def clear(self) -> None: ...
    def delete(self) -> None: ...
    def get_statistics(self) -> 'ContextStatistics': ...
    def close(self) -> None: ...
```

#### `basic.py` - Secure Session ID Generation

```python
import secrets

def generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(16)  # 22 chars, 128 bits
```

#### `basic.py` - Atomic Write

```python
def _atomic_append(self, record: dict) -> None:
    """Atomically append record to JSONL file."""
    import tempfile
    
    # Write to temp file
    fd, temp_path = tempfile.mkstemp(
        dir=self._file_path.parent,
        prefix='.tmp_',
        suffix='.jsonl'
    )
    try:
        with os.fdopen(fd, 'a') as f:
            f.write(json.dumps(record) + '\n')
        # Atomic rename
        Path(temp_path).rename(self._file_path)
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
```

#### `validator.py` - Session ID Validation

```python
import re
from yoker.exceptions import ValidationError

def validate_session_id(session_id: str, path: str = "session_id") -> str:
    """Validate session ID for security.
    
    Returns validated session_id or raises ValidationError.
    """
    # Validate format: alphanumeric, dash, underscore only
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        raise ValidationError(path, session_id,
            "must contain only alphanumeric, dash, or underscore characters")
    
    # Prevent path traversal
    if '..' in session_id or '/' in session_id or '\\' in session_id:
        raise ValidationError(path, session_id,
            "must not contain path traversal characters")
    
    # Length limits
    if len(session_id) > 128:
        raise ValidationError(path, session_id,
            "must not exceed 128 characters")
    
    return session_id
```

---

## Files to Create

| File | Description |
|------|-------------|
| `src/yoker/context/__init__.py` | Public API exports |
| `src/yoker/context/interface.py` | ContextManager protocol |
| `src/yoker/context/basic.py` | BasicPersistenceContextManager |
| `src/yoker/context/validator.py` | Validation functions |
| `src/yoker/context/exceptions.py` | Context-specific exceptions |
| `tests/context/__init__.py` | Test package |
| `tests/context/test_basic.py` | BasicPersistence tests |
| `tests/context/test_validator.py` | Validation tests |

---

## Configuration Updates

Add to `.gitignore`:
```
# Context storage
context/
```

Update `ContextConfig` (optional for MVP):
```python
@dataclass(frozen=True)
class ContextConfig:
    manager: str = "basic_persistence"
    storage_path: str = "./context"
    session_id: str = "auto"
    persist_after_turn: bool = True
    # Phase 1 additions:
    # max_file_size_mb: int = 100
    # max_turns: int = 1000
```

---

## Test Coverage Requirements

| Test Category | Coverage Target |
|---------------|-----------------|
| Session ID generation | 100% |
| Session ID validation | 100% |
| Path traversal prevention | 100% |
| Atomic writes | 100% |
| Context persistence | 100% |
| Context loading | 100% |
| Context isolation | 100% |
| Error handling | 100% |

---

## Deferred to Phase 1

1. Token counting (requires backend integration)
2. Context compaction/summarization
3. Data sanitization for sensitive patterns
4. Encryption-at-rest support
5. Retention policies and auto-cleanup

---

## Approval

Both domain agents approve the implementation with the following conditions:

1. ✅ Use `secrets.token_urlsafe(16)` for session IDs (security)
2. ✅ Implement all interface methods (API design)
3. ✅ Add security validation (security)
4. ✅ Use atomic writes (security)
5. ✅ Set secure file permissions (security)
6. ✅ Implement context isolation (both)

**Status**: Approved for implementation.