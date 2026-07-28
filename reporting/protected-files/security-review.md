# Security Review: protected_files Guardrail (MBI-009 T12)

**Reviewer**: security-engineer (Stage b domain review)
**Branch**: feature/protected-files
**Date**: 2026-07-27
**Threat model**: SOFT guardrail — "powerful mistakes, not malicious agents" (owner-approved)
**Verdict**: **approved** — implementation matches the SOFT threat model and the owner's
binding proposals. No blocking issues. Five non-blocking observations follow.

## Files Reviewed

- `src/yoker/tools/guardrails/path.py` — `_check_protected_files`, `is_protected`, `interactive_approvals`
- `src/yoker/core/_processing.py` — `_maybe_block_protected`, `_build_approval_diff`, approval hook in `_run_tool`
- `src/yoker/config/__init__.py` — `PermissionsConfig.protected_files` (16-entry default denylist)
- `src/yoker/ui/interactive.py` — `confirm_approval` (diff render + y/N prompt, fail-safe)
- `src/yoker/ui/batch.py` — `confirm_approval` (always False)
- `src/yoker/ui/handler.py` — `confirm_approval` protocol method
- `src/yoker/core/__init__.py` — `_approval_handler` optional attr
- `src/yoker/cli/chat.py` — `_wire_approval_handler`
- `src/yoker/tools/diff.py` — shared `generate_diff` helper

## Owner's Binding Proposals vs. Implementation

| Proposal | Implementation | Verdict |
|---|---|---|
| SOFT guardrail for powerful mistakes, not malicious agents | Only `write`/`update` gated; reads unrestricted; interactive approve-on-diff; simple block in batch | Matches |
| Option A: interactive approve-on-diff now | `confirm_approval` renders unified diff via shared `generate_diff`, prompts y/N | Matches |
| yoker.toml + expanded scope in denylist | 16 entries including `yoker.toml`, `.git/config`, `.git/hooks/*`, `.github/workflows/*.yml`, `uv.lock`, `poetry.lock` | Matches |
| fnmatch glob matching | `fnmatch.fnmatchcase` against relative path AND basename | Matches |

## Security Focus Areas

### 1. SOFT Guardrail Scope — Correct

The guardrail gates only `write` and `update` (`path.py` lines 168-201). Reading protected
files is allowed (consistent with "reading is safe" — the threat is unintended modification,
not inspection). The interactive flow is gated on a wired `_approval_handler`; otherwise the
simple block fires. This precisely matches the SOFT model: an agent making a "powerful
mistake" (e.g. clobbering `Makefile` during a refactor) gets stopped and the user sees a diff;
a malicious agent is explicitly out of scope.

### 2. Bypass Vectors

**Symlink — closed.** `_resolve_path` uses `os.path.realpath()` (`path.py` line 238), which
collapses `..` and resolves symlinks before any matching. `_relative_for_protected` then
computes the path relative to the allowed root on the resolved path. A symlink within the
project pointing to `Makefile` resolves to the real `Makefile` and matches the basename. A
symlink pointing outside the project fails the `_is_within_allowed_paths` check upstream.

**Make tool — not covered (acceptable for SOFT).** The `make` tool can execute arbitrary
shell that writes files, bypassing the protected_files check. This is a real bypass, but it
falls outside the SOFT threat model: a "powerful mistake" via `make` is gated by the existing
`auto_permission` / env-var allowlist controls on the make tool itself, and a malicious
agent using `make` to write `Makefile` is explicitly out of scope. See observation O-1.

**Git tool — not covered (acceptable for SOFT).** `git checkout`, `git apply`, etc. can
overwrite protected files. Same reasoning as `make`: out of scope for the SOFT model. The
`GitToolConfig.allowed_commands` defaults to read-only ops (`status`, `log`, `diff`,
`branch`, `show`); `commit`/`push` require interactive approval via `auto_permission`. See observation O-1.

### 3. Fail-Safe Behavior — Correct

Three independent fail-safe paths, all denial:

- **Interactive `confirm_approval`** (`interactive.py` lines 425-433): `EOFError` and
  `KeyboardInterrupt` are caught and return `False`; an empty answer (Enter) does not match
  `("y", "yes")` and returns `False`.
- **Handler exception in the processing loop** (`_processing.py` lines 490-494): any
  exception from `handler(path, diff)` is logged and `approved = False`.
- **No handler wired** (`_processing.py` lines 879-881): `handler is None` → returns `None`
  from `_maybe_block_protected` only when the simple block has already run; in interactive
  mode the simple block is skipped, so `handler is None` would pass through — see O-2.

### 4. Non-Interactive Fallback — Correct

`BatchUIHandler.confirm_approval` returns `False` unconditionally (`batch.py` line 339).
`_wire_approval_handler` early-returns for `BatchUIHandler` (`chat.py` lines 136-137), so
`interactive_approvals` stays at its default `False` and the `PathGuardrail.validate` simple
block fires before the tool ever runs. The batch handler's `confirm_approval` is a defensive
safety net that is never reached in practice. Double-layered, correct.

### 5. yoker.toml Protection — Present

`yoker.toml` is in `_DEFAULT_PROTECTED_FILES` (`config/__init__.py` line 263). This closes
the self-modification vector: an agent cannot rewrite the project's yoker config to disable
the guardrail without user approval.

### 6. Expanded Scope — Present

All owner-approved additions are in the default denylist:
- `.git/config` (line 264)
- `.git/hooks/*` (line 265)
- `.github/workflows/*.yml` (line 266)
- `uv.lock` (line 267)
- `poetry.lock` (line 268)

The `*` glob in `.git/hooks/*` matches all hooks at any depth under `.git/hooks/` (fnmatch
`*` matches `/`), which is the desired behavior.

### 7. Matching Strategy — Correct

`fnmatch.fnmatchcase` is used (`path.py` line 315) against both the relative path from the
containing allowed root and the basename. `fnmatchcase` is case-sensitive and
platform-independent (does not consult locale or filesystem case behavior), making matching
predictable. The denylist includes both `Makefile`/`makefile` and `Justfile`/`justfile` to
cover common casing variants.

**Path traversal**: `..` components are collapsed by `os.path.realpath()` before the
relative path is computed, so `subdir/../Makefile` resolves to `Makefile` and matches.
`../Makefile` from the project root resolves outside the allowed root and is blocked by
`_is_within_allowed_paths` upstream.

### 8. `interactive_approvals` Flag — Acceptable (with observation)

The flag is mutable public state on `PathGuardrail`. It defaults to `False` (safe: simple
block fires). It is set to `True` only by `_wire_approval_handler` (`chat.py` line 141),
which atomically also wires `_approval_handler` on the agent. The flag is not exposed via
`ToolContext`, so tools cannot mutate it at runtime. See O-2 for the theoretical
inconsistency hazard.

### 9. Sub-Agent Propagation — Acceptable

Sub-agents construct their own `PathGuardrail` in `Agent.__init__` (`core/__init__.py` line
134) with the default `interactive_approvals=False`, and `_approval_handler` is never wired
on them (only the primary agent gets `_wire_approval_handler` in `chat.py` line 119). The
simple block therefore fires on sub-agents — a hard block, more restrictive than the primary
agent's interactive approval. This is consistent with the SOFT model and avoids prompting the
user from a sub-agent context where the diff context is unclear.

## Non-Blocking Observations

### O-1: `make` and `git` tools can overwrite protected files (Accepted: SOFT scope)

**Severity**: Low (within SOFT model). **OWASP**: A06 Insecure Design (scope boundary).
**STRIDE**: Tampering.

The `make` tool executes arbitrary shell commands; `git checkout`/`apply` can overwrite
files. Both bypass `protected_files` because the check only gates `write`/`update` tool
calls. The owner explicitly scoped this guardrail to "powerful mistakes, not malicious
agents," so this is accepted. If the threat model ever expands to malicious agents, the
`make`/`git` paths become the primary bypass and would need their own file-write auditing.

**Recommendation (backlog, not blocking)**: Document this scope boundary in the
`protected_files` docstring or design note so future maintainers understand the `make`/`git`
paths are intentionally uncovered. No code change needed for the SOFT model.

### O-2: `interactive_approvals=True` without handler would bypass the simple block

**Severity**: Low (not reachable in current code). **OWASP**: A06 Insecure Design.
**STRIDE**: Tampering / Elevation of Privilege.

If `PathGuardrail.interactive_approvals` were ever set to `True` without a corresponding
`_approval_handler` on the agent, `validate` would skip the simple block and
`_maybe_block_protected` would return `None` (handler is None), allowing the write to
proceed with no protection. In current code this state is unreachable: the only setter
(`_wire_approval_handler`) sets both atomically. The hazard is for future maintainers who
might flip the flag independently.

**Recommendation (defense in depth, optional)**: In `_maybe_block_protected`, treat
`interactive_approvals=True` with `handler is None` as a denial rather than a pass-through,
or assert the invariant in `_wire_approval_handler`. This is a one-line defensive guard that
makes the fail-safe explicit. Not required for the SOFT model since the state is unreachable
today.

### O-3: TOCTOU between `is_protected` and the actual write

**Severity**: Low (out of scope for SOFT). **OWASP**: A06 Insecure Design. **STRIDE**:
Tampering.

`is_protected` resolves the path via `realpath` and checks the glob; the actual file write
happens later in `_execute_tool`. A symlink swap between check and write could redirect the
write to a different target. This requires a malicious actor with concurrent filesystem
access, which is outside the "powerful mistakes" threat model.

**Recommendation**: No action for the SOFT model. If the threat model expands, perform the
write through an `O_NOFOLLOW`-style path or re-verify the resolved target immediately before
the write.

### O-4: Case-insensitive filesystems (macOS APFS default)

**Severity**: Low (within SOFT model). **OWASP**: A03 (indirectly, matching weakness).
**STRIDE**: Tampering.

`fnmatchcase` is case-sensitive, but macOS default APFS is case-insensitive. `PyProject.toml`
and `pyproject.toml` are the same file on disk but only the lowercase form is in the
denylist. A "powerful mistake" is unlikely to case-vary deliberately; a malicious agent
could. This is accepted under the SOFT model.

**Recommendation (optional)**: If macOS robustness is desired without going to a full
malicious-agent threat model, add `.PYPROJECT.TOML` or normalize the basename to lowercase
before matching (keeping the case-sensitive relative-path match for `.github/workflows/*.yml`
patterns where case matters on Linux). Not required for the SOFT model.

### O-5: `_build_approval_diff` reads via unresolved `Path(path)`

**Severity**: Informational (display-only, not a security control). **OWASP**: N/A.

`_build_approval_diff` (`_processing.py` lines 911-938) reads the existing file via
`Path(path).read_text()` using the raw path string, not the resolved path. Since `is_protected`
already resolved via `realpath` and matched, reading through a symlink shows the correct
target content. The diff is for human review only and is not a security boundary. No action
required.

## Positive Observations

- **Defense in depth on batch mode**: both the simple block in `validate` and
  `BatchUIHandler.confirm_approval` deny; the belt-and-suspenders design is appropriate.
- **Fail-safe on every exception path**: EOF, Ctrl+C, handler exception, and empty answer
  all converge on denial. No path through `confirm_approval` or `_maybe_block_protected`
  defaults to allow.
- **Symlink resistance via `realpath`**: applied consistently in `_resolve_path` and reused
  by both `validate` and `is_protected`, so the interactive hook and the simple block see
  the same resolved path.
- **POSIX separators for cross-platform glob matching**: `_relative_for_protected` uses
  `as_posix()`, so `.git/hooks/*` matches on Windows as well as POSIX.
- **Atomic wiring in `_wire_approval_handler`**: handler and flag are set together; the
  batch handler is explicitly skipped, preventing the always-False batch handler from
  silently blocking every protected write in interactive use.
- **Shared `generate_diff` helper**: single tested code path for both the update tool's
  content metadata and the approval prompt, avoiding drift between the two diff renderings.
- **Explicit SOFT scope documentation**: the `_DEFAULT_PROTECTED_FILES` and
  `PermissionsConfig.protected_files` docstrings clearly state "SOFT guardrail: protects
  against powerful mistakes, not malicious agents," which prevents future scope creep
  expectations.

## Scope Classification

| Finding | Classification | Action |
|---|---|---|
| O-1: make/git bypass | New (backlog) | Document scope boundary; revisit if threat model expands |
| O-2: interactive_approvals/handler inconsistency | New (backlog) | Optional one-line defensive guard |
| O-3: TOCTOU | New (backlog) | Out of SOFT scope; no action |
| O-4: Case-insensitive FS | New (backlog) | Optional normalization; not required for SOFT |
| O-5: Unresolved Path in diff | New (informational) | No action |

All findings are **New / non-blocking** — none block the T12 task completion. The
implementation correctly satisfies the owner's binding proposals and the SOFT threat model.

## Verdict

**approved**