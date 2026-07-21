# API Design: `make` Tool — Makefile Target Execution

**Date:** 2026-07-21
**Task:** MBI-009 T1 (Tier 1 critical) — `make` tool, from the 1.0.0 Release Gate
**Reviewer:** API Architect Agent
**Source analysis:** `analysis/mbi-toolset-coverage.md` §7.1, §10 T1
**Owner's proposal (quoted from TODO.md / §7.1):**

```python
async def make(
  target: str,            # Makefile target (e.g., "check", "test", "lint")
  ctx: ToolContext,
  cwd: Annotated[str, PathArg("Working directory")] = ".",
  timeout_ms: int = 300000,
) -> ToolResult:
  """Run a Makefile target and return its output."""
```

> Implementation: `subprocess.run(["make", target], cwd=cwd, ...)` — list args, no shell; PathGuardrail on `cwd`; output truncation (default 100KB); timeout enforcement (default 5 minutes); target validation rejects `;`, `|`, `&`, `$`, backticks; no env var injection; return exit code, stdout, stderr separately.

---

## 1. Summary

The owner's proposal is slim, consistent with the existing `git` tool pattern (fixed operation space + typed parameters + `subprocess.run` with list args), and satisfies all stated requirements. **It works as written.** This design adopts it verbatim and pins down only the details the proposal leaves implicit: the target-validation regex, the `ToolResult` shape (structured dict, per T1.1 "Return exit code, stdout, stderr separately"), the `MakeToolConfig` dataclass, the manifest entry, and the one-line PathGuardrail wiring change.

No abstractions, wrappers, or new indirections are introduced. One concern is flagged (Section 7) about a TOCTOU edge in the `protected_files` guardrail; it is out of scope for this tool's API but noted for T12.

## 2. Function Signature (Final)

```python
# src/yoker/builtin/make.py

from typing import Annotated

from yoker.tools.annotations import Path as PathArg
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult


async def make(
  target: str,
  ctx: ToolContext,
  cwd: Annotated[str, PathArg("Working directory containing the Makefile")] = ".",
  timeout_ms: int = 300000,
) -> ToolResult:
  """Run a Makefile target via subprocess and return its output."""
```

This matches the owner's proposal exactly — parameter names, order, defaults, and the `PathArg` annotation on `cwd`. The only addition is a tighter `PathArg` description string for the LLM-facing schema.

### 2.1 Why not `path` instead of `cwd`?

The existing `git` tool uses `path` as its parameter name, which aligns with the `PathGuardrail` convention of extracting `value.get("path", ...)`. The owner's proposal uses `cwd`, which is more semantic for a *command-execution* tool (where the path is a working directory, not a file to read/write). The guardrail dispatcher (`_validate_tool_args` in `core/_processing.py`) calls `guardrail.validate(spec.name, value)` **per parameter** using the annotated name from `spec.guards`, so `cwd` is dispatched correctly as long as `make` is registered in `_FILESYSTEM_TOOLS` (Section 5). No rename needed.

## 3. Parameter Semantics & Defaults

| Parameter | Type | Default | Semantics |
|-----------|------|---------|-----------|
| `target` | `str` | (required) | Single Makefile target name (e.g., `"check"`, `"test"`, `"lint"`). Validated against a strict regex (Section 4). |
| `ctx` | `ToolContext` | (injected) | Harness-injected; carries `Config` and `Backends`. Not exposed to the LLM. |
| `cwd` | `str` (`PathArg`) | `"."` | Working directory for `make`. Must resolve within `permissions.filesystem_paths`. Validated by `PathGuardrail`. |
| `timeout_ms` | `int` | `300000` (5 min) | Wall-clock timeout for the subprocess. Clamped to `[1000, ctx.config.tools.make.timeout_ms]` — a caller can shorten but not exceed the configured ceiling (Section 6). |

Notes:
- **No env var injection.** `subprocess.run` inherits the parent env by default; we do NOT pass an `env=` argument. This matches the owner's "make reads its own environment" decision.
- **No `args`/`flags` parameter.** The owner's proposal has only `target`; keeping the surface tight prevents flag-injection vectors. Agents needing flags like `-j4` should use a Makefile target that encodes them. (If real-world experience shows this is a blocking gap, add a tightly-validated `args: list[str]` post-1.0 — out of scope now, per the slim-default principle.)
- **`ctx` placement.** The signature puts `ctx` second (after `target`) to match the `git` tool's ordering (operation-first, ctx-second). The `read`/`write` tools use the same convention.

## 4. Target Validation

A single regex defines what a "Makefile target name" is. Anything outside it is rejected with a clear error before `subprocess.run` is called.

```python
import re

# Valid Makefile target characters: letters, digits, and -._+%
# (GNU make also allows % in pattern rules and .PHONY-style dots).
# Reject shell metacharacters explicitly listed by the owner:
#   ; | & $ ` — plus whitespace, newlines, and other shell-active bytes.
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+\-]*$")

_FORBIDDEN_TARGET_CHARS = frozenset({";", "|", "&", "$", "`", "\n", "\r", "\t", " "})
```

Validation rules:
1. `target` must be a `str`; non-string is rejected (`ToolResult(success=False, error="...")`).
2. Empty target rejected.
3. Length cap: `len(target) <= 256` (defensive; matches no real Makefile target length).
4. `_TARGET_RE.fullmatch(target)` must succeed.
5. `target` must not contain any char in `_FORBIDDEN_TARGET_CHARS` (redundant with the regex but explicit and self-documenting — matches the `git` tool's `FORBIDDEN_CHARS` pattern).

On failure: `return ToolResult(success=False, error=f"Invalid make target: {target!r}")`.

**Acceptance mapping (from T1.1):** `make(target="rm -rf /")` is rejected (whitespace + `/` not in regex), and so is `make(target="check; cat /etc/passwd")` (`;` and space rejected). `make(target="check")`, `make(target="test")`, `make(target="lint")` all pass.

## 5. PathGuardrail Wiring (one-line change in `tools/guardrails/path.py`)

The owner's "PathGuardrail on `cwd`" requires `make` to be in the filesystem-tools set. Add it:

```python
# src/yoker/tools/guardrails/path.py
_FILESYSTEM_TOOLS = frozenset(
  {"read", "list", "write", "update", "search", "existence", "mkdir", "git", "make"}
)
```

That is the **only** guardrail change required. Because the dispatcher calls `validate(tool_name, value)` with the raw `cwd` string, and `validate()` already:
- skips the empty-path branch for non-`git` tools (the default `"."` is truthy, so this is fine),
- resolves via `os.path.realpath`,
- checks `_is_within_allowed_paths`,
- runs `_check_blocked_patterns` (harmless for `cwd` — a project dir won't match `\.env` etc.),

`make` gets root-containment validation for free. No `make`-specific branch is needed in `PathGuardrail.validate` (no extension check, no size check, no "file must exist" check fires for `make` because those are gated on `tool_name == "read"|"write"|"update"`).

**Edge case — `cwd` does not exist or is a file:** `subprocess.run` raises `FileNotFoundError`/`NotADirectoryError`. The `make` tool catches these and returns `ToolResult(success=False, error="Working directory does not exist: ...")`. No guardrail change needed.

## 6. `MakeToolConfig` Dataclass

Follows the existing `GitToolConfig` / `SearchToolConfig` pattern exactly (Section 6.4 of the global instructions: "slim, tight, concise is the default").

```python
# src/yoker/config/__init__.py

@dataclass
class MakeToolConfig(ToolConfig):
  """Make tool configuration.

  Attributes:
    enabled: Whether the make tool is enabled (inherited from ToolConfig).
    timeout_ms: Default wall-clock timeout per target invocation, in milliseconds.
    max_output_kb: Per-stream (stdout/stderr) truncation limit in KB.
      When truncation occurs, the affected stream is capped and a
      truncation marker is appended.
  """

  timeout_ms: int = 300000
  max_output_kb: int = 100

  def __post_init__(self) -> None:
    """Validate make tool configuration."""
    validate_positive_int(self.timeout_ms, "tools.make.timeout_ms")
    validate_positive_int(self.max_output_kb, "tools.make.max_output_kb")
```

And register it on `ToolsConfig`:

```python
@dataclass
class ToolsConfig:
  ...
  make: MakeToolConfig = field(default_factory=MakeToolConfig)
```

Export `MakeToolConfig` from `yoker.config.__init__` (add to `__all__`).

### 6.1 How config flows

`Config.tools.make.timeout_ms` is the **ceiling**. The `timeout_ms` parameter on the function lets the agent *shorten* the timeout for a specific call but not exceed the configured ceiling:

```python
configured_ceiling = ctx.config.tools.make.timeout_ms
effective_timeout_ms = min(timeout_ms, configured_ceiling)
effective_timeout_seconds = max(effective_timeout_ms, 1000) / 1000.0
```

This prevents an agent bypassing the operator's configured ceiling via the function argument. `max_output_kb` is taken directly from config (no per-call override — keeping the surface tight per the owner's proposal, which exposes no `max_output_kb` parameter).

### 6.2 Why no `allowed_targets` / `blocked_targets`?

The TODO spec does not mention a target allowlist or blocklist, and the owner's proposal has only `target` + `cwd` + `timeout_ms`. The `protected_files` guardrail (T12) is the owner's chosen mechanism for preventing Makefile abuse — block the *edit* of Makefile, not the *execution* of targets. Adding an `allowed_targets` list here would duplicate that concern at the wrong layer and complicate the default config. **Not added.** If real-world experience shows a need, it can be added post-1.0 without changing the function signature.

## 7. ToolSpec, Annotations, and Manifest

### 7.1 ToolSpec building

`build_tool_spec(make)` in `yoker.tools.schema` introspects the signature and produces:
- `name`: `"make"` (no namespace when loaded as builtin).
- `description`: first line of the docstring (`"Run a Makefile target via subprocess and return its output."`).
- `schema.parameters.properties`:
  - `target`: `{"type": "string", "description": ""}` (no `PathArg` marker → no guard; the `_TARGET_RE` validation runs inside the tool body, not via the guardrail dispatcher — same as how `git` validates `operation` against `allowed_commands` inside the body).
  - `cwd`: `{"type": "string", "description": "Working directory containing the Makefile"}` with `guard_type = GuardType.PATH`.
  - `timeout_ms`: `{"type": "integer"}` with default `300000`.
- `required`: `["target"]` (only `target` has no default).
- `guards`: `{"cwd": GuardType.PATH}`.

A warning will be emitted by `_build_parameter_schema` for `target` (string param with no yoker marker). This matches the `git` tool's `operation` parameter behavior and is acceptable — `target` is a validated free-form string, not a path. If the warning is undesirable, attach a `Text("Makefile target name")` marker:

```python
target: Annotated[str, Text("Makefile target name (e.g., 'check', 'test')")],
```

**Recommendation:** add the `Text` marker. It is a one-line change, suppresses the warning, and gives the LLM a better description. Not a deviation from the owner's proposal — it is a documentation refinement within the existing annotation framework.

### 7.2 Manifest entry (in `src/yoker/builtin/__init__.py`)

```python
from yoker.builtin.make import make

# In __YOKER_MANIFEST__:
__YOKER_MANIFEST__ = PluginManifest(
  tools=[existence, git, list, make, mkdir, read, search, update, webfetch, websearch, write],
  skills_dir="skills",
  agents_dir="agents",
)
```

Add `"make"` to `__all__`. The `make` tool is a **static built-in** (not Session-injected, not a factory), matching `git`, `read`, etc.

## 8. Execution & Return Shape

### 8.1 Subprocess call

```python
import subprocess

try:
  proc = subprocess.run(
    ["make", target],
    cwd=str(resolved_cwd),
    capture_output=True,
    text=True,
    timeout=effective_timeout_seconds,
  )
  returncode, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
except subprocess.TimeoutExpired as e:
  return ToolResult(
    success=False,
    error=f"make target '{target}' exceeded timeout ({effective_timeout_ms} ms)",
  )
except FileNotFoundError:
  return ToolResult(success=False, error=f"make is not installed or not found in PATH")
except NotADirectoryError:
  return ToolResult(success=False, error=f"Working directory is not a directory: {cwd}")
except OSError as e:
  return ToolResult(success=False, error=f"Error invoking make: {e}")
```

No `shell=True`. No `env=` override. List args only.

### 8.2 Output truncation

Truncate `stdout` and `stderr` **independently** to `max_output_bytes = ctx.config.tools.make.max_output_kb * 1024`. When truncation occurs, append a marker line to the affected stream so the agent can tell:

```python
def _truncate(stream: str, max_bytes: int) -> tuple[str, bool]:
  b = stream.encode("utf-8", errors="replace")
  if len(b) <= max_bytes:
    return stream, False
  # Truncate on a UTF-8 boundary to avoid producing invalid sequences.
  cut = b[:max_bytes].decode("utf-8", errors="ignore")
  return cut + "\n... [truncated]\n", True
```

Truncation is reported in the structured result (Section 8.3) so the agent can react programmatically.

### 8.3 `ToolResult` shape

T1.1 says "Return exit code, stdout, stderr separately." `ToolResult.result` is typed `str | dict[str, Any]`, so a structured dict is the natural fit (and the `git` tool returns a flat string only because it has no exit-code requirement to surface). Use a dict:

```python
return ToolResult(
  success=(returncode == 0),
  result={
    "exit_code": returncode,
    "stdout": truncated_stdout,
    "stderr": truncated_stderr,
    "truncated": stdout_truncated or stderr_truncated,
  },
  error=(truncated_stderr.strip() or f"make '{target}' failed with exit code {returncode}")
    if returncode != 0
    else None,
)
```

Rationale for the dual `result`/`error` fields on failure:
- `success=False` + `error` lets the agent's tool-loop treat the failure as a normal error event (the existing convention — `git` does this).
- `result` still carries the structured payload so the agent can inspect `exit_code` and `stdout` (e.g., to read compiler errors from a failed `make check`). Without this, a failing `make check` would lose its stdout, which is the whole reason the agent ran it.

**Concern flagged (out of scope for this tool):** this is the first built-in tool to return a structured dict in `ToolResult.result`. Verify the `UIBridge`/`InteractiveUIHandler` renders `dict` results gracefully (the type allows it, but no existing built-in exercises that path). The `BatchUIHandler` already JSON-serializes `ToolResult.result`, so dict is safe there. This is an implementation concern for T1.1, not a design blocker.

## 9. Edge Cases (mapped to acceptance criteria in T1.1/T1.3)

| Edge case | Handling |
|-----------|----------|
| Missing Makefile (`cwd` has no `Makefile`/`makefile`/`GNUmakefile`) | `make` exits non-zero with stderr `"make: *** No targets specified and no makefile found. Stop."` → `ToolResult(success=False, result={exit_code, stdout, stderr, ...}, error=...)`. No pre-check needed; make's own error is informative. |
| Target not found | `make` exits non-zero with `"No rule to make target 'X'."` → same path as above. |
| Timeout | `subprocess.TimeoutExpired` caught; return `success=False, error="... exceeded timeout (...)"`. The subprocess is killed by `subprocess.run`'s internal context manager. |
| Oversized output | Per-stream truncation (Section 8.2) with `truncated: True` in the result dict. |
| `cwd` outside project root | PathGuardrail returns `ValidationResult(valid=False, reason="Path outside allowed directories: ...")` before the tool body runs; the harness blocks the call. |
| `cwd` does not exist / is a file | `subprocess.run` raises `FileNotFoundError`/`NotADirectoryError`; tool returns `success=False, error="Working directory does not exist: ..."`. (Guardrail does not enforce existence for non-read/update tools, which is correct — `make` should be able to *report* a missing Makefile.) |
| Shell-metachar target (`rm -rf /`, `check; cat`, `$(evil)`) | Rejected by `_TARGET_RE` + `_FORBIDDEN_TARGET_CHARS` before subprocess is invoked. |
| `make` not installed | `FileNotFoundError` from `subprocess.run` → `success=False, error="make is not installed or not found in PATH"`. |
| Non-string `target` (model hallucination) | `isinstance(target, str)` check at top of body → `success=False, error="Invalid target parameter"`. |
| Agent passes `timeout_ms=0` or negative | `validate_positive_int` on `MakeToolConfig.timeout_ms` guards the configured ceiling; per-call `timeout_ms` is clamped: `max(timeout_ms, 1000)` then `min(..., configured_ceiling)`. |
| Makefile edits a protected file at runtime (e.g., target writes to `pyproject.toml`) | **Out of scope for the `make` tool.** A Makefile target can run arbitrary shell; the controlled-tools mitigation is `protected_files` on the `write`/`update` tools, not output-side interception. See Section 7 of `mbi-toolset-coverage.md`. |

## 10. Concerns & Improvements Over the TODO Spec

Quoting the owner's proposal (§7.1 / T1.1):

> - `subprocess.run(["make", target], cwd=cwd, ...)` — list args, no shell
> - PathGuardrail on `cwd`
> - Output truncation (default 100KB)
> - Timeout enforcement (default 5 minutes)
> - Return exit code, stdout, stderr separately

This design adopts that proposal as-is. The only refinements (none rise to "deviation"):

1. **`target` gets a `Text` annotation** for a cleaner LLM-facing schema and to silence the `tool_parameter_missing_yoker_type` warning. Refinement, not deviation.
2. **`timeout_ms` is clamped to `MakeToolConfig.timeout_ms` as a ceiling.** The TODO does not specify whether the per-call `timeout_ms` can exceed the configured default. Clamping is the safer choice and matches the spirit of "controllable tools" — an operator's configured ceiling should not be bypassable by an agent argument. Flag for owner confirmation during implementation review; if the owner prefers the per-call value to be authoritative, drop the clamp (one-line change).
3. **Per-stream truncation, not combined.** The TODO says "output truncation (default 100KB)" without specifying per-stream vs combined. Per-stream is chosen because `stderr` of a failing `make check` is often the valuable part and would be dwarfed by `stdout` under a combined budget. Flag for owner confirmation; trivial to switch.
4. **Structured dict return** (per T1.1 "Return exit code, stdout, stderr separately"). This is the first built-in to use `dict` in `ToolResult.result`. Implementation should verify the UI handler renders dict results. Flagged in Section 8.3, not a design blocker.
5. **No `allowed_targets`/`blocked_targets` config field.** Explicitly *not* added — the owner's proposal does not include it, and `protected_files` (T12) is the chosen mechanism for Makefile-abuse prevention. Adding it here would be the kind of redundant abstraction the slim-default principle forbids.

### 10.1 Out-of-scope concern (T12, not this tool)

The `protected_files` guardrail blocks `write`/`update` on `Makefile` but does not prevent an agent from writing a *new* `Makefile` if none exists (the `write` tool with `allow_overwrite=False` creates new files). If the agent then runs `make(target=...)`, it executes the Makefile it just authored. This is a TOCTOU-shaped hole in T12's design, not in the `make` tool's design — the `make` tool is doing its job (executing targets in the project's Makefile). Flagged here for visibility; the fix belongs in T12 (extend `protected_files` to block `write` creation, not just `update`). No change to the `make` tool API.

## 11. Action Items

**Implementation (T1):**
- [ ] Create `src/yoker/builtin/make.py` with the signature in Section 2, target validation in Section 4, execution in Section 8.
- [ ] Add `MakeToolConfig` to `src/yoker/config/__init__.py` (Section 6), register on `ToolsConfig`, export in `__all__`.
- [ ] Add `"make"` to `_FILESYSTEM_TOOLS` in `src/yoker/tools/guardrails/path.py` (Section 5).
- [ ] Add `make` to `__YOKER_MANIFEST__.tools` and `__all__` in `src/yoker/builtin/__init__.py` (Section 7.2).
- [ ] Verify `UIBridge` / `InteractiveUIHandler` render `dict` `ToolResult.result` (Section 8.3 concern).

**Tests (T1.3):**
- [ ] `tests/test_builtin/test_make.py` — cover each row of the Section 9 edge-case table. Specifically: `make(target="check")` runs; `make(target="rm -rf /")` rejected; output > 100KB truncated with marker; timeout enforced; `cwd` outside project rejected by guardrail; missing Makefile returns structured failure with exit code.

**For owner confirmation at implementation review:**
- [ ] Per-call `timeout_ms` clamped to configured ceiling (Section 10 refinement 2).
- [ ] Per-stream (not combined) truncation budget (Section 10 refinement 3).

## 12. Files Touched (Summary)

| File | Change |
|------|--------|
| `src/yoker/builtin/make.py` | **New.** Tool implementation. |
| `src/yoker/builtin/__init__.py` | Import `make`; add to `__YOKER_MANIFEST__.tools` and `__all__`. |
| `src/yoker/config/__init__.py` | Add `MakeToolConfig`; register on `ToolsConfig`; export in `__all__`. |
| `src/yoker/tools/guardrails/path.py` | One-line change: add `"make"` to `_FILESYSTEM_TOOLS`. |
| `tests/test_builtin/test_make.py` | **New.** Tests per Section 9. |