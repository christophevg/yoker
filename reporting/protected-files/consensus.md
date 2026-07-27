# Consensus: protected_files Guardrail (MBI-009 T12)

**Status: APPROVED — consensus reached.**

Both api-architect and security-engineer approve the simple block approach for T12.

## Architecture (3 points)

1. **Config**: add one field to `PermissionsConfig` in `src/yoker/config/__init__.py`:
   `protected_files: tuple[str, ...] = ("Makefile", "makefile", "GNUmakefile", "Justfile", "justfile", "Taskfile.yml", "pyproject.toml", "tox.ini", "setup.py", "setup.cfg")`
   Per-project/per-user configurability and empty-list-disables are automatic via the existing Clevis cascade.
2. **Guardrail**: add one method `_check_protected_files(resolved) -> str | None` to `PathGuardrail` in `src/yoker/tools/guardrails/path.py`. Basename exact match (`resolved.name in self._permissions.protected_files`). Returns error message on match. Called from the `write` and `update` branches of `validate()`, before the existing extension checks.
3. **Non-interactive block**: returns `ValidationResult(valid=False, reason=...)` — identical to how `blocked_extensions`/`blocked_patterns` already work. No new error type, no new event, no UI changes, no new class.

~6 lines + two call sites + one config field. No new class, no new Guardrail subclass, no new indirection.

## PM-resolved tensions

1. **Simple block vs interactive approve-on-diff**: RESOLVED → ship the simple block for T12. The owner's accepted design in the analysis doc says "rejected" (block), not "ask for permission." The TODO.md's "show diff and ask permission" language is a discrepancy — the interactive flow doesn't fit the sync guardrail architecture (`validate` is sync, only gets path string, no UI access, no content for diff). Defer interactive approve-on-diff to a separate follow-up task. **Forward to owner as open question.**
2. **yoker.toml protection**: NOT RESOLVED → forward to owner. Both agents flagged that `yoker.toml` is not in the default denylist, and since it controls the guardrail's behavior (`protected_files = []` disables it), an agent could self-disarm. The analysis doc says "for now, leave it unprotected; the config system validates values on load" — but validation doesn't prevent emptying the list. **Forward to owner as open question.**
3. **Filename matching**: RESOLVED → basename exact match (simplest, no glob — YAGNI).
4. **Block unconditionally in both interactive and batch modes**: RESOLVED → yes, unconditional block for T12 (since interactive flow is deferred).

## Security findings (from security-engineer, non-blocking for T12)

- Symlink bypass: already closed (existing `is_symlink()` rejection + `realpath()`)
- `make` tool: can't be exploited (no `-f` flag, target validation)
- `git` tool: no checkout/reset/clean exposed (no overwrite vector)
- Future tools (T5 `file` tool move/rename, T16.8 git checkout, T13 python/exec) must respect `protected_files` when implemented — flag for those tasks
- Denylist completeness: `.git/config`, `.github/workflows/*.yml`, lock files — owner decision on scope

## Owner-stated proposals (binding — quoted verbatim)

- "Accepted. The proposed `protected_files` denylist in `PermissionsConfig` is confirmed. The list includes Makefile, pyproject.toml, tox.ini, etc."
- "The `protected_files` check would be a filename-based check (exact match or glob) applied to `write` and `update` tools."
- "`write` tool: PathGuardrail already checks `blocked_extensions`. Add `protected_files` check before the extension check."
- "`update` tool: PathGuardrail already validates paths for update. Add the same `protected_files` check."
- "`read` tool: No change needed — reading these files is safe, only writing/updating them is dangerous."
- "A `protected_files: []` (empty list) disables all protections (explicit opt-out)"
- "This is a SOFT guardrail — it protects against powerful mistakes, not malicious agents."

## Open questions for the owner (to be posted in the implementation plan)

1. **Simple block vs interactive approve-on-diff**: The TODO says "show the user a diff and ask for permission" but your accepted design says "rejected" (block). The interactive flow doesn't fit the sync guardrail architecture. Proposed: ship the simple block for T12, defer interactive approve-on-diff to a follow-up. Confirm?
2. **`yoker.toml` protection**: Should `yoker.toml` be added to the default denylist? It controls the guardrail's own behavior — an agent could write `protected_files = []` to self-disarm. The analysis doc says "for now, leave it unprotected" but this creates a self-disable vector. Add to denylist, or leave out?
3. **Denylist scope**: Are `.git/config`, `.git/hooks/*`, `.github/workflows/*.yml` in scope of "execution-configuration files"? They can run arbitrary shell on trigger. What about lock files (`uv.lock`, `poetry.lock`)?