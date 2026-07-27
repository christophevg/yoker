# API Architecture: `protected_files` Guardrail (MBI-009 T12)

**Date**: 2026-07-27
**Task**: MBI-009 T12 — Protected files guardrail (Makefile editing security)
**Reviewer**: API Architect Agent
**Source**: `analysis/mbi-toolset-coverage.md` (Section 6.5, T12), TODO.md task description

## Summary

The task is **not implemented**. `PermissionsConfig` has no `protected_files` field; `PathGuardrail` has no protected-files check; `write` and `update` tools have no file-protection logic. The owner has an explicit, confirmed proposal in `analysis/mbi-toolset-coverage.md` that this doc treats as the default (Simplicity Principle).

There is one significant tension between the TODO.md task description (which asks for an interactive diff-and-approve flow) and the owner's accepted design (which is a simple block in PathGuardrail). This doc flags it as an open question and proposes the simple-block approach as the default, with the interactive flow as a follow-up requiring architectural work that is out of scope for T12.

## Current State (Phase 2.3 Verification)

### `src/yoker/config/__init__.py` — `PermissionsConfig` (lines 248-273)

Has `filesystem_paths`, `network_access`, `max_file_size_kb`, `handlers`. **No `protected_files` field.** Adding a field here is the obvious, owner-confirmed home.

### `src/yoker/tools/guardrails/path.py` — `PathGuardrail`

Has checks for: allowed roots, blocked regex patterns, read extension/size, write extension/content-size, update extension/diff-size, mkdir depth. **No protected-files check.** The check would slot in alongside the existing write/update-specific checks (lines 158-193).

### `src/yoker/builtin/write.py` and `update.py`

Both rely on the central `PathGuardrail` via the schema's `Path` annotation. No file-protection check in the tools themselves. `update.py` already builds a unified diff for display metadata (`_build_content_or_diff_metadata`, lines 276-405) — this is a reusable diff generator if an interactive flow is ever added.

### `src/yoker/tools/guardrails/__init__.py` — `Guardrail` base

Sync `validate(tool_name, value) -> ValidationResult`. No async, no UI access, no pausing.

### Guardrail invocation path (`src/yoker/core/_processing.py`)

`_validate_tool_args` (lines 894-909) iterates `spec.guards` and calls `guardrail.validate(spec.name, value)` where `value` is the **individual parameter value** (the path string), not the full args dict. `PathGuardrail.validate` handles both forms (dict-aware), but from the live call path it receives the path string only.

**Pre-existing note (not T12's problem):** the `isinstance(value, dict)` branches in `PathGuardrail` (write content-size, update diff-size) therefore never fire from the real call path. They only fire in direct tests. This is a latent bug but orthogonal to T12 — the protected-files check only needs the path, so it works from both call paths.

### Interactive mechanism — does not exist for guardrails

- `UIHandler.get_input(prompt)` is async and exists on the UI layer, but **guardrails have no access to the UI handler**. The guardrail is a sync `validate()` returning a binary `ValidationResult`.
- The existing `PermissionsConfig.handlers` (`HandlerConfig` with mode `block`/`allow`/`ask_user`) is used by the `git` tool for `commit`/`push`. The `ask_user` mode does **not** actually prompt the user — it returns `False` with a message ("Operation X requires user confirmation") that goes back to the agent. There is no live interactive confirmation flow anywhere in the codebase.
- `Config.ui.mode` (`"interactive"` / `"batch"`) is accessible to the guardrail via `self._config.ui.mode`. This is the mechanism to detect non-interactive mode.

## Owner's Stated Proposals (Verbatim, from `analysis/mbi-toolset-coverage.md`)

> **Owner decision (2026-07-16):** Accepted. The proposed `protected_files` denylist in `PermissionsConfig` is confirmed. The list includes Makefile, pyproject.toml, tox.ini, etc.

> **Accepted approach:** Add a `protected_files` field to `PermissionsConfig`:
> ```toml
> [permissions]
> protected_files = [
>   "Makefile", "makefile", "GNUmakefile",
>   "Justfile", "justfile", "Taskfile.yml",
>   "pyproject.toml", "tox.ini", "setup.py", "setup.cfg",
> ]
> ```

> The `protected_files` check would be a filename-based check (exact match or glob) applied to `write` and `update` tools.

> - `write` tool: PathGuardrail already checks `blocked_extensions`. Add `protected_files` check before the extension check.
> - `update` tool: PathGuardrail already validates paths for update. Add the same `protected_files` check.
> - `read` tool: No change needed — reading these files is safe.

> - The `protected_files` list is configurable per-project and per-user (standard Clevis config cascade)
> - A `protected_files: []` (empty list) disables all protections (explicit opt-out)

> **Owner decision (Section 11, #10):** Owner accepted the proposed `protected_files` denylist in `PermissionsConfig`. The list includes Makefile, makefile, GNUmakefile, Justfile, justfile, Taskfile.yml, pyproject.toml, tox.ini, setup.py, setup.cfg. Configurable per-project and per-user.

**Acceptance criteria (T12.1-T12.2):**
- `update(path="pyproject.toml", ...)` is rejected
- `write(path="src/main.py", content="...")` is allowed
- Protected files list is configurable
- Empty `protected_files` list disables all protections

Note: the acceptance criteria say **"rejected"**, not "ask for permission". This is the crux of the open question below.

## Proposed Architecture

### 1. Config: add `protected_files` to `PermissionsConfig`

```python
@dataclass
class PermissionsConfig:
  filesystem_paths: tuple[str, ...] = (".",)
  network_access: str = "none"
  max_file_size_kb: int = 500
  handlers: dict[str, HandlerConfig] = field(default_factory=dict)
  protected_files: tuple[str, ...] = (
    "Makefile", "makefile", "GNUmakefile",
    "Justfile", "justfile", "Taskfile.yml",
    "pyproject.toml", "tox.ini", "setup.py", "setup.cfg",
  )
```

Per-project/per-user configurability is automatic via the existing Clevis cascade (`~/.yoker.toml` → `./yoker.toml` → CLI). Empty list disables protection. No new validation needed (tuple of strings; empty is explicitly valid).

### 2. Guardrail: add `_check_protected_files` to `PathGuardrail`

A new check method, called from the `write` and `update` branches of `validate()`, before the existing extension/size checks. Filename matching: **basename match** against the resolved path's `Path.name`. This is the simplest option that satisfies the owner's "filename-based check" and the default denylist (which is all basenames, no paths, no globs).

```python
def _check_protected_files(self, resolved: Path) -> str | None:
  protected = self._permissions.protected_files
  if not protected:
    return None
  name = resolved.name
  if name in protected:
    return f"File is protected against agent writes: {name}"
  return None
```

Wiring in `validate()`:
- In the `if tool_name == "write":` block (after `is_overwrite` is irrelevant — protect on both create and overwrite), before `_check_write_extension`.
- In the `if tool_name == "update":` block, before the existing read/write extension checks.

This matches the owner's "Add `protected_files` check before the extension check" exactly. No new class, no new Guardrail subclass, no new indirection. One method, ~6 lines, two call sites.

### 3. Non-interactive block (the default behavior)

`ValidationResult(valid=False, reason="File is protected against agent writes: {name}")` is returned. The existing `_validate_tool_args` flow turns this into `"Error: File is protected..."` returned to the agent. This is identical to how `blocked_extensions` and `blocked_patterns` already work. No new error type, no new event, no UI changes.

### 4. Interactive diff-and-approve flow — NOT in scope for T12

The TODO.md task description says "show the user a diff and ask for permission" and "only apply the change on approval". This is **not** part of the owner's accepted design in the analysis doc, and it does not fit the current guardrail architecture:

| Requirement | Blocker |
|---|---|
| Generate a diff | Guardrail's `validate` receives only the path string from `_validate_tool_args`, not the content/old_string/new_string. Diff generation also needs the existing file content (read I/O in a sync guardrail). |
| Ask the user | Guardrail is sync `validate() -> ValidationResult`. No access to `UIHandler.get_input()`. No pausing mechanism. |
| Apply on approval | The guardrail runs *before* the tool executes. It cannot defer the tool call and resume it later. |

The existing `HandlerConfig` `ask_user` mode (used by `git`) does not actually prompt — it returns a blocking message. There is no live interactive confirmation flow anywhere in the codebase to extend.

**Recommendation:** Ship the simple block (owner's accepted approach) for T12. If an interactive approve-on-diff flow is desired, it is a separate, larger feature that needs:
- An async permission-interception point in `_validate_tool_args` (or a new pre-execution hook) that has access to the full tool args and the UI handler.
- A diff-generation utility (reusable from `update.py`'s existing `_build_content_or_diff_metadata`).
- A resume-after-approval mechanism.

That feature should be its own task with its own analysis. T12 should not silently absorb it.

## Filename Matching: Basename vs Glob

The owner said "exact match or glob". The default denylist is all basenames. **Basename exact match** is the simplest, satisfies all acceptance criteria, and needs no new dependencies. Glob support can be added later by changing `name in protected` to `any(fnmatch(name, pat) for pat in protected)` — a one-line change. No need to spec glob now (YAGNI).

## How `ui.mode` is Detected

If the interactive flow is ever added, the guardrail reads `self._config.ui.mode` (`"interactive"` / `"batch"`). For the simple-block default, **the mode does not matter** — the block is unconditional, matching the owner's acceptance criteria ("rejected"). This is the simplest correct behavior: a protected file is blocked regardless of UI mode. The TODO's "in non-interactive mode, block the change" implies interactive mode might *not* block — but that's the unscoped interactive flow, not T12's block.

## Open Questions for the Owner

1. **Interactive approve-on-diff flow.** The TODO.md task description asks for "show the user a diff and ask for permission" / "only apply the change on approval", but your accepted design in `analysis/mbi-toolset-coverage.md` is a simple block in `PathGuardrail` (acceptance criteria say "rejected"). These are inconsistent. The simple block fits the existing architecture; the interactive flow does not (sync guardrail, no UI access, no resume-after-approval). **Proposed default:** ship the simple block for T12. Treat the interactive approve-on-diff flow as a separate follow-up task. **Confirm?**

2. **`yoker.toml` protection.** The analysis doc notes (line 291): "Edge case: `yoker.toml` — this is Yoker's own config. If an agent modifies it, it could change tool settings (e.g., disable guardrails). This should probably be protected too, but it's a Yoker-specific decision. For now, leave it unprotected; the config system validates values on load." **Should `yoker.toml` be added to the default denylist, or left out per the analysis doc's "for now, leave it unprotected"?**

3. **Filename matching: basename exact match only, or glob now?** The default denylist is all basenames. Basename exact match is the simplest. Glob support is a one-line change later if needed. **Proposed default: basename exact match. Confirm?**

4. **Block in both interactive and batch modes?** Per the owner's acceptance criteria ("rejected"), the simple block applies regardless of UI mode. The TODO's "in non-interactive mode, block the change" implies interactive mode might behave differently (approve flow). Since the interactive flow is deferred (Q1), the block is unconditional for T12. **Confirm: block unconditionally in both modes for T12?**

## Action Items

- [ ] Owner confirms Q1-Q4 above.
- [ ] T12.1: Add `protected_files: tuple[str, ...]` to `PermissionsConfig` with the default denylist.
- [ ] T12.2: Add `_check_protected_files` method to `PathGuardrail`; call it from the `write` and `update` branches before extension checks.
- [ ] Tests: `write(path="Makefile", ...)` rejected; `update(path="pyproject.toml", ...)` rejected; `write(path="src/main.py", ...)` allowed; `read(path="Makefile")` allowed (no change); empty `protected_files` disables protection; custom denylist respected.
- [ ] No OpenAPI spec needed (this is a guardrail, not an HTTP API).
- [ ] Documentation: README.md note that `protected_files` is configurable and empty-list disables.