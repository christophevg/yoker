# Consensus Report: Task 2.6 Search Tool

**Date**: 2026-04-29
**Status**: Approved for Implementation

## Domain Agent Reviews

### API Architecture (c3:api-architect)

**Document**: `analysis/api-search-tool.md`

**Key Design Decisions**:
1. **Two search modes**:
   - `type="content"`: Grep-like regex search in file contents
   - `type="filename"`: Find-like glob pattern matching

2. **Parameters**:
   - `path` (required): Directory to search
   - `pattern` (optional): Regex for content, glob for filename (default: "*" or ".*")
   - `type` (optional): "content" or "filename" (default: "content")
   - `max_results` (optional): Result limit (default: 100, absolute max: 1000)

3. **ReDoS Prevention**:
   - Pattern length limit (500 characters)
   - Forbidden pattern detection (nested quantifiers)
   - Compile-time regex validation
   - File size limit (10MB max)
   - Timeout protection

4. **Return Format**:
   ```json
   {
     "success": true,
     "matches": [
       {"file": "path/to/file.py", "line": 42, "content": "..."}
     ],
     "total_matches": 15,
     "truncated": false,
     "files_searched": 23
   }
   ```

5. **Consistency**:
   - Follows Tool base class pattern
   - Uses shared PathGuardrail
   - Same error handling patterns

### Security Engineering (c3:security-engineer)

**Document**: `analysis/security-search-tool.md`

**Key Security Recommendations**:

1. **Critical - ReDoS Prevention**:
   - Use `regex` module with timeout support (third-party)
   - Pattern complexity validation for dangerous constructs
   - Bounded quantifiers enforcement

2. **High - Information Disclosure**:
   - Blocked content patterns for credentials/API keys
   - Result sanitization for sensitive values
   - Pattern blocking for credential enumeration

3. **Medium - Resource Exhaustion**:
   - File size limits (500KB default)
   - Result set limits (500 max)
   - Timeout enforcement (10 seconds)
   - Binary file filtering

4. **Medium - Path Containment**:
   - Reuse existing PathGuardrail
   - Already handles symlink rejection

5. **Logging**:
   - Log all search operations with pattern, path, results count, duration

## Consensus Points

| Topic | API Design | Security | Consensus |
|-------|-----------|----------|-----------|
| PathGuardrail reuse | ✓ Uses shared | ✓ Uses shared | **Agreed** |
| ReDoS prevention | Complexity validation + timeout | Regex module + timeout | **Agreed** - Use both approaches |
| Result limits | max_results parameter | Hard limit 500 | **Agreed** - Use both |
| File size limits | 10MB skip | 500KB config | **Agreed** - Use configurable limit |
| Blocked patterns | Not specified | Credential patterns | **Agreed** - Implement optional blocking |

## Resolved Decisions

### 1. ReDoS Prevention Strategy

**Decision**: Use Python's standard `re` module with validation and timeout wrapper.

**Rationale**:
- The `regex` module adds a dependency
- Standard library `re` is sufficient with proper validation
- Use `signal.alarm()` or threading timeout for enforcement
- Pattern complexity validator blocks dangerous constructs

**Implementation**:
```python
FORBIDDEN_PATTERNS = [
    r'\([^)]*[+*][^)]*\)[+*]',     # Nested quantifier: (a+)+
    r'\([^)]*\|[^)]*\)[+*]',        # Alternation with repetition
    r'[^)]*[+*][^)]*[+*]',          # Adjacent quantifiers
]

def validate_pattern(pattern: str) -> ValidationResult:
    for forbidden in FORBIDDEN_PATTERNS:
        if re.search(forbidden, pattern):
            return ValidationResult(valid=False, reason=f"Pattern contains dangerous construct")
    return ValidationResult(valid=True)
```

### 2. Dependency Decision

**Decision**: Do NOT add `regex` module dependency. Use standard library `re` with timeout enforcement via threading.

**Rationale**:
- Minimize dependencies
- Standard library is sufficient for this use case
- Threading timeout provides adequate protection

### 3. Blocked Content Patterns

**Decision**: Implement as optional configuration, not hardcoded.

**Rationale**:
- Different deployments have different security requirements
- Some projects need to search for patterns like "password"
- Make it configurable via TOML

**Configuration**:
```toml
[tools.search]
blocked_patterns = []  # Empty by default, user can configure
```

### 4. File Size Limit

**Decision**: Use 500KB default, configurable via TOML.

**Rationale**:
- 500KB is reasonable for text files
- Allows searching typical source files
- User can increase for specific use cases

## Implementation Plan

### Phase 1: Core Implementation
1. Create `SearchTool` class in `src/yoker/tools/search.py`
2. Implement content search (grep-like)
3. Implement filename search (glob-like)
4. Add ReDoS pattern validation
5. Add result truncation
6. Use shared `PathGuardrail`

### Phase 2: Security Enhancements
1. Add timeout enforcement (threading-based)
2. Add file size filtering
3. Add binary file filtering
4. Add configurable blocked patterns

### Phase 3: Testing
1. Unit tests for both search modes
2. Security tests for ReDoS patterns
3. Performance tests for large directories
4. Edge case tests (binary files, encoding)

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/yoker/tools/search.py` | Create - SearchTool implementation |
| `src/yoker/tools/__init__.py` | Modify - Register SearchTool |
| `tests/test_tools/test_search.py` | Create - Unit tests |
| `analysis/api-search-tool.md` | Created by api-architect |
| `analysis/security-search-tool.md` | Created by security-engineer |

## Approval

- [x] API Architecture review complete
- [x] Security review complete
- [x] Consensus reached on all design decisions
- [x] Implementation plan defined
- [x] Files to modify identified

**Approved for implementation** by project-manager agent.