# Bug Analysis: Issue #9 - Storage Path Tilde Expansion

## Summary

When `BasicPersistenceContextManager` receives a storage path containing `~` (e.g., `"~/.cache/yoker/sessions"`), it creates a literal `~` directory in the current working directory instead of expanding to the user's home directory.

## Symptoms

- Session files created in wrong location (`./~/...` instead of `~/.cache/yoker/...`)
- Pollutes project directories with `~` folders
- Breaks session discovery (can't find sessions in expected location)

## Expected vs Actual Behavior

| Aspect | Expected | Actual |
|--------|----------|--------|
| Path `~/.cache/yoker/sessions` | `/home/user/.cache/yoker/sessions` | `/cwd/~/.cache/yoker/sessions` |
| Session discovery | Works | Broken |
| Directory pollution | None | Creates `~/` in CWD |

## Root Cause Analysis

### Primary Cause

In `src/yoker/context/basic.py` line 76:

```python
self._storage_path = validate_storage_path(Path(storage_path), "context.storage_path")
```

The `Path(storage_path)` constructor treats `~` as a literal directory name. The `validate_storage_path` function calls `.resolve()` which also doesn't expand `~`.

### Why It Happens

- `Path("~/.cache")` creates a path with literal `~` as first component
- `.resolve()` makes it absolute relative to CWD: `/cwd/~/.cache`
- `.expanduser()` is required to expand `~` to home directory

### Working Reference

`src/yoker/context/session.py` line 46 correctly handles this:

```python
storage_path = Path(storage_path).expanduser()
```

## Proposed Fix

Add `.expanduser()` before validation:

```python
# Line 76 in src/yoker/context/basic.py
# Before:
self._storage_path = validate_storage_path(Path(storage_path), "context.storage_path")

# After:
self._storage_path = validate_storage_path(Path(storage_path).expanduser(), "context.storage_path")
```

## Test Strategy

1. Create unit test that passes `"~/.cache/yoker/sessions"` as storage path
2. Verify the resolved path is under home directory, not CWD
3. Verify no literal `~` directory is created

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Breaking existing behavior | Low | Only adds expansion, no semantic change |
| Security implications | None | Expansion happens before validation |
| Platform compatibility | Low | `expanduser()` works on Windows too |

## Implementation Steps

1. Add failing test demonstrating the bug
2. Add `.expanduser()` call to line 76
3. Verify all existing tests still pass
4. Run new test to confirm fix

## Related

- Issue: #9
- Files: `src/yoker/context/basic.py`, `src/yoker/context/validator.py`