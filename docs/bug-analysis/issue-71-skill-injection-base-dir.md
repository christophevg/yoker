# Bug Analysis: Issue #71 - Skill Injection Base Directory Reference

## Summary

The skill invocation block injected into LLM context on every skill invocation
prepended a `Base directory for this skill:` line, instructing agents to use
filesystem access to read skill reference files. The `skill()` tool already
supports a `resource` argument that loads resources relative to the skill's
actual location, making the base-directory guidance obsolete and misleading.

## Symptoms

- Every skill invocation block told agents to resolve and read skill files
  from the filesystem
- Agents could attempt filesystem reads instead of using the `skill()` tool's
  `resource` argument (which handles trust, path resolution and guardrails)

## Expected vs Actual Behavior

| Aspect | Expected | Actual |
|--------|----------|--------|
| Invocation block | Points agents to `skill(skill_name=..., resource=...)` | Prepends `Base directory for this skill:` |
| Resource loading | Via `skill()` tool `resource` argument | Suggests direct filesystem access |
| Docstring example | Matches new behavior | Showed base-dir line |

## Root Cause Analysis

### Primary Cause

`format_invocation_block()` in `src/yoker/skills/injection.py` hardcoded the
base-dir lines in its output:

```python
lines = [
  "<command-message>",
  ...
  "</command-message>",
  "",
  "Base directory for this skill:",
  "",
]
```

### Scope Confirmation

Both consumers of the invocation block go through this single function, so one
fix covers all code paths:

- `src/yoker/core/__init__.py:569` — slash-command invocation
- `src/yoker/builtin/skill.py:86` — `skill()` tool invocation

All other "Base directory" matches in the repository are documentation,
analysis and reporting documents (not code); `loader.py`'s `base_dir`
references are resource-resolution internals unrelated to the injected text.

## Design Decision (Owner)

REPLACE the base-dir block with a pointer to the `skill()` tool's `resource`
argument. Plain removal was NOT acceptable — agents must still receive
guidance on how to obtain skill resources.

## Proposed / Implemented Fix

Replace the base-dir lines with a three-line instruction:

```
To load a bundled reference file this skill provides, use the skill tool's
resource argument (e.g. skill(skill_name="<name>", resource="references/<file>"))
- do not read skill files from the filesystem.
```

Updated the `format_invocation_block()` docstring example accordingly.

## Test Strategy

`tests/test_skills/test_injection.py`:
- `test_format_invocation_includes_base_directory` (asserting the base-dir
  line was present) is replaced by
  `test_format_invocation_points_to_resource_argument`, which asserts:
  1. `"Base directory"` is NOT in the result
  2. `"resource argument"` IS in the result
  3. `skill(skill_name=` example IS in the result

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Agents lose resource-loading guidance | None | Replaced with equivalent `resource`-argument guidance |
| Existing skills referencing base-dir in content | Low | Content comes from skill definitions; not affected by this change |

## Verification

1. TDD: new test failed against buggy code (`assert 'Base directory' not in
   result` reproduced the bug)
2. After fix: `tests/test_skills/test_injection.py` — 19/19 passed
3. `make check` — fix-scope green; 3 pre-existing failures in
   `tests/test_ui/test_interactive.py::TestInteractiveUIHandlerStats` are
   unrelated (tied to uncommitted `ui/interactive.py` work, present before
   this change and explicitly out of scope)

## Related

- Issue: #71
- Branch: `fix/71-skill-injection-base-dir`
- Files: `src/yoker/skills/injection.py`, `tests/test_skills/test_injection.py`