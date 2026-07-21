# PR #48 — Per-Target Allowlist Response (comment 5033135719)

**Date:** 2026-07-21
**Author:** functional-analyst
**Responds to:** owner comment 5033135719 (2026-07-21T10:59:55Z)

---

## Owner's comment (quoted verbatim)

> Hard deny ist: ✅
> Value validation: ✅
> Generic available for all tools: ❌ Let's start with the `make` tool only. For now I don't think other tools benefit from having configuration options using env vars - please review and confirm.
> Deny-by-default: ✅
>
> Additional feature question: Can we make the allowed env vars list configurable at target level? So, the `TEST` variable is only allowed for the `test` target. What would the `make` tool's configuration look like?
>
> Something like this?
> ```
> [tools.make]
> allowed_env_vars = { test : [ "TEST" ] }
> ```
> or
> ```
> [tools.make.test]
> allowed_env_vars = [ "TEST" ]
> ```

## Q1–Q4 decisions acknowledged

- **Q1 (hard non-configurable denylist):** APPROVED.
- **Q2 (value validation):** APPROVED.
- **Q3 (generic across all tools):** REJECTED — make-only for now. Owner asks us to review other subprocess tools and confirm. See §1 below.
- **Q4 (deny-by-default):** APPROVED.

## 1. Q3 confirmation — make-only is correct

Reviewed every subprocess-spawning built-in tool:

| Tool | Spawns subprocess? | Env-vars use case? | Verdict |
|------|--------------------|--------------------|---------|
| `make` (new) | Yes (`subprocess.run`) | Yes — `TEST=file.py`, `LINT_FLAGS=...` are legitimate variable-override use cases (make's own `VAR=val` semantics) | In scope |
| `git` | Yes (`subprocess.run`, `git.py:344`) | No — git config is args-based (`allowed_commands`, `requires_permission`). Env vars git might want (`GIT_SSH_COMMAND`, `GIT_EDITOR`, `GIT_DIR`, `GIT_WORK_TREE`, `GIT_CONFIG_PARAMETERS`) are framework-injection vectors the hard denylist blocks. Git has no "variable override" use case analogous to make's `TEST=`. | Out of scope |
| `webfetch` | No — HTTP backend (`webfetch.py:53`, `backend.fetch`) | N/A — env vars don't reach an HTTP client the same way | Out of scope |
| `websearch` | No — HTTP backend (`websearch.py:50`, `backend.search`) | N/A | Out of scope |
| `read`, `write`, `update`, `list`, `mkdir`, `existence`, `search` | No — in-process filesystem ops | N/A | Out of scope |

**Confirmation:** `make` is the only built-in tool where `env_vars` provides a legitimate variable-override use case. The git tool's config surface is already covered by `allowed_commands` / `requires_permission`, and the env vars it might want are exactly the framework-injection vectors the hard denylist blocks. webfetch/websearch use HTTP clients. File ops don't spawn subprocesses.

**Conclusion: Q3 is correctly rejected — make-only this PR. No change to `GitToolConfig`.**

## 2. Per-target allowlist analysis — recommend Option A

### Owner's two proposals on the table

**Option A** (inline table or subsection):
```toml
[tools.make]
allowed_env_vars = { test = ["TEST"] }

# or equivalently, as a subsection:
[tools.make.allowed_env_vars]
test = ["TEST"]
lint = ["LINT_FLAGS"]
```

**Option B** (per-target section):
```toml
[tools.make.test]
allowed_env_vars = ["TEST"]
```

### Analysis

| Concern | Option A | Option B |
|---------|----------|----------|
| Schema clarity | One `dict[str, tuple[str, ...]]` field on `MakeToolConfig` — clean dataclass mapping | Requires `MakeToolConfig` to accept arbitrary free-form target-name subkeys — no clean dataclass shape; would need a `dict[str, TargetConfig]` field or a dynamic-section parser, both of which fight the existing `ToolConfig`/`MakeToolConfig` dataclass schema |
| TOML semantics | Idiomatic — `[tools.make.allowed_env_vars]` is a named subsection with a known schema (`dict[str, list[str]]`); inline-table form also valid | `[tools.make.test]` creates a sub-section under `tools.make`, but `MakeToolConfig` has fixed fields (`timeout_ms`, `max_output_kb`, `enabled`). Target names are free-form strings, not fixed config keys — this fights TOML's "section = fixed schema" model. |
| Extensibility | Adding per-target `timeout_ms` later = add another dict field `target_timeouts: dict[str, int]`. No collision. | Adding per-target `timeout_ms` later = mix it into the `[tools.make.test]` section — but then `test` as a target collides with `test` as a config field namespace, and operators can't tell target-sections from real config fields. |
| Validation | Straightforward: iterate dict keys, check each matches target-name regex; iterate values, check each is a string. One validation loop. | Must distinguish "target sections" from real `MakeToolConfig` fields when parsing — adds parsing complexity and ambiguity (what if a target is named `enabled` or `timeout_ms`?). |
| Collision with existing fields | None — `allowed_env_vars` is a new field, separate from `timeout_ms`, `max_output_kb`, `enabled`. | **Real collision risk:** target names like `enabled`, `timeout_ms`, `max_output_kb`, `max_env_var_bytes` would shadow real `MakeToolConfig` fields. Operators cannot safely name a target `test` if we later add a `test` config field. |
| Simplicity Principle | Closer to the existing pattern (`GitToolConfig.allowed_commands: tuple[str, ...]` is a single-field allowlist). | Introduces a new pattern (dynamic sections) not present anywhere else in the config system. |

**Recommendation: Option A.** It maps cleanly to a single dataclass field, is idiomatic TOML (named subsection with a known schema), avoids the collision-with-config-fields problem entirely, and extends naturally if we add per-target settings later.

**Why Option B is awkward:** it treats free-form target names as config sections, which (a) has no clean dataclass representation, (b) collides with existing and future `MakeToolConfig` fields (target named `enabled`/`timeout_ms`), and (c) forces the parser to distinguish target-sections from real config fields — an ambiguity that doesn't exist in Option A.

### Concrete dataclass sketch (Option A)

```python
import re
from dataclasses import dataclass, field

from yoker.config.validators import validate_positive_int
from yoker.exceptions import ValidationError

_TARGET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+\-]*$")


@dataclass
class MakeToolConfig(ToolConfig):
  """Make tool configuration.

  Attributes:
    timeout_ms: Default timeout in milliseconds.
    max_output_kb: Maximum output size per stream in KB.
    allowed_env_vars: Per-target allowlist of env var names. Keys are
      Makefile target names; values are the env var names that target is
      permitted to receive. Targets not in the dict deny all env vars
      (deny-by-default). Empty dict = all env vars denied for all targets.
    max_env_var_bytes: Maximum byte size per env var value.
  """

  timeout_ms: int = 300000
  max_output_kb: int = 100
  allowed_env_vars: dict[str, tuple[str, ...]] = field(default_factory=dict)
  max_env_var_bytes: int = 4096

  def __post_init__(self) -> None:
    validate_positive_int(self.timeout_ms, "tools.make.timeout_ms")
    validate_positive_int(self.max_output_kb, "tools.make.max_output_kb")
    validate_positive_int(self.max_env_var_bytes, "tools.make.max_env_var_bytes")
    for target in self.allowed_env_vars:
      if not _TARGET_NAME_RE.fullmatch(target):
        raise ValidationError(
          "tools.make.allowed_env_vars",
          target,
          f"invalid target name key: {target!r}",
        )
```

### TOML shape (Option A)

Inline-table form (one target):
```toml
[tools.make]
allowed_env_vars = { test = ["TEST"] }
```

Subsection form (multiple targets — clearer):
```toml
[tools.make.allowed_env_vars]
test = ["TEST"]
lint = ["LINT_FLAGS", "LINT_CONFIG"]
docs = ["DOCS_DIR"]
```

Both forms bind to the same `dict[str, tuple[str, ...]]` field.

### Validation semantics

When `make(target="test", env_vars={"TEST": "foo.py"})` is called:

1. Look up `allowed_env_vars.get("test", ())` → `("TEST",)`.
2. For each key `k` in `env_vars`:
   - `k` must be in `("TEST",)` — the per-target allowlist.
   - `k` must not be in the hard denylist (`MAKEFLAGS`, `LD_*`, `YOKER_*`, etc.) — framework invariant, not waivable.
   - `value` must pass value validation (≤ `max_env_var_bytes` bytes, no NUL, no newlines, valid UTF-8).
3. If `target` is not in `allowed_env_vars` dict → `()` returned → all env vars denied (deny-by-default).
4. If `env_vars` is `None` or empty → no validation needed, proceed normally (env still inherited from `os.environ`).

Concrete trace:

| Call | Allowlist result | Hard denylist | Value validation | Outcome |
|------|------------------|---------------|-------------------|---------|
| `make("test", {"TEST": "foo.py"})` | `"TEST" ∈ ("TEST",)` ✓ | not denied ✓ | 6 bytes ✓ | Allowed |
| `make("build", {"TEST": "foo.py"})` | `"TEST" ∉ ()` (target not in dict) | — | — | Rejected (deny-by-default) |
| `make("test", {"MAKEFLAGS": "--eval=..."})` | `"MAKEFLAGS" ∉ ("TEST",)` | (would also be blocked) | — | Rejected by allowlist |
| `make("test", {"TEST": secrets})` where operator allowlisted `TEST` | `"TEST" ∈ ("TEST",)` ✓ | not denied ✓ | ≤ 4 KB, no NUL/newlines ✓ | Allowed (value cap limits exfil) |
| `make("lint", {"LINT_FLAGS": "-x"})` with `lint = ["LINT_FLAGS"]` | `"LINT_FLAGS" ∈ ("LINT_FLAGS",)` ✓ | not denied ✓ | 2 bytes ✓ | Allowed |

## 3. Updated implementation plan — files list

| File | Change |
|------|--------|
| `src/yoker/config/__init__.py` | Add `MakeToolConfig` with `allowed_env_vars: dict[str, tuple[str, ...]] = field(default_factory=dict)` (per-target, deny-by-default) and `max_env_var_bytes: int = 4096`. Register on `ToolsConfig.make`; export in `__all__`. **No change to `GitToolConfig` (Q3 rejected — make-only).** |
| `src/yoker/builtin/make.py` | New. Signature: `make(target, ctx, cwd=".", timeout_ms=300000, env_vars: dict[str, str] \| None = None) -> ToolResult`. Validation: target regex + forbidden chars + leading-`-` rejection (unchanged from prior plan); env_vars validated via the new `env.py` guardrail using the per-target allowlist. Subprocess: `subprocess.run(["make", target], cwd=resolved, env={**os.environ, **validated}, capture_output=True, text=True, timeout=..., start_new_session=True)`. |
| `src/yoker/tools/guardrails/env.py` | New (~30 lines). `is_denied_env_var(name)`, `validate_env_vars(env_vars, allowed_names, max_bytes)` — per-target allowlist + hard denylist + value rules. Mirrors `path.py` pattern. |
| `src/yoker/tools/guardrails/path.py` | One line — add `"make"` to `_FILESYSTEM_TOOLS` (R1, unchanged from prior plan). |
| `src/yoker/builtin/__init__.py` | One line — manifest entry for `make`. |
| `tests/test_builtin/test_make.py` | New. Coverage: per-target allowlist (target in dict → allowed vars only; target not in dict → all env vars denied; operator allowlists `MAKEFLAGS` → still denied by hard denylist); value validation (oversize, NUL, newline); env inheritance; target validation; timeout; output truncation. |
| `tests/test_tools/test_env_guardrail.py` | New. Unit tests for the env guardrail (allowlist, denylist, value rules). |

## 4. Open item

Waiting for owner confirmation on **Option A vs. Option B**, then I'll update the implementation plan and proceed to implementation.