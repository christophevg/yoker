# API Architect Review — `make` Tool (PR #48, Stage b)

**Date:** 2026-07-21
**Reviewer:** api-architect agent
**Branch:** `feature/make-tool`
**Stage a (functional review):** passed
**Sources reviewed:**
- `src/yoker/builtin/make.py` (new)
- `src/yoker/tools/guardrails/env.py` (new)
- `src/yoker/config/__init__.py` (modified — `MakeToolConfig`)
- `src/yoker/tools/guardrails/path.py` (modified — `"make"` in `_FILESYSTEM_TOOLS`)
- `src/yoker/builtin/__init__.py` (modified — manifest entry)
- `tests/test_tools/test_make.py` (new)

**Reference designs:**
- `analysis/api-make-tool.md` (original API design)
- `reporting/make-tool/per-target-allowlist-response.md` (owner-approved Option A final design)

---

## Section 1 — API surface alignment

### Signature

Implemented (`src/yoker/builtin/make.py:37-43`):

```python
async def make(
  target: Annotated[str, Text("Makefile target name (e.g., 'check', 'test')")],
  ctx: ToolContext,
  cwd: Annotated[str, PathArg("Working directory containing the Makefile")] = ".",
  timeout_ms: int = 300000,
  env_vars: dict[str, str] | None = None,
) -> ToolResult:
```

Matches the approved signature `make(target, ctx, cwd, timeout_ms, env_vars) -> ToolResult` exactly:
- Parameter names, order, defaults, and types all match.
- `ctx` placed second (matches `git`/`read` convention).
- `env_vars: dict[str, str] | None = None` added per owner-approved Option A response.
- Return type `ToolResult` (structured dict in `.result`).

### Annotations

- `target`: `Annotated[str, Text("Makefile target name (e.g., 'check', 'test')")]` — matches design §7.1 recommendation (the `Text` marker refinement the design explicitly recommended, not a deviation).
- `cwd`: `Annotated[str, PathArg("Working directory containing the Makefile")]` — matches design §2 verbatim (tighter description string included).
- `timeout_ms` and `env_vars`: no yoker markers, which is correct (they are not paths/text content; they are scalar/dict params validated inside the body).

### ToolResult shape (`make.py:131-140`)

```python
return ToolResult(
  success=(proc.returncode == 0),
  result={
    "exit_code": proc.returncode,
    "stdout": stdout_out,
    "stderr": stderr_out,
    "truncated": stdout_truncated or stderr_truncated,
  },
  error=stderr_out if proc.returncode != 0 else None,
)
```

Keys: `{exit_code, stdout, stderr, truncated}` — matches approved design §8.3 exactly. `success` tracks exit code. `error` carries `stderr` on failure so the agent's tool-loop sees a normal error event while still having the structured payload in `.result` (matches `git`'s dual-field convention). Test `test_success_result_dict_keys` asserts the exact key set.

**Section 1 verdict: aligned.**

---

## Section 2 — Config schema correctness

`MakeToolConfig` (`src/yoker/config/__init__.py:451-481`):

```python
@dataclass
class MakeToolConfig(ToolConfig):
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

Matches owner-approved Option A shape (per-target-allowlist-response.md §2 "Concrete dataclass sketch"):
- `allowed_env_vars: dict[str, tuple[str, ...]]` ✅ exact
- `max_env_var_bytes: int = 4096` ✅ exact
- `timeout_ms: int = 300000`, `max_output_kb: int = 100` ✅ inherited from original design §6
- Validators: three `validate_positive_int` calls + per-target-key regex validation ✅ matches sketch
- `_TARGET_NAME_RE` defined at module level (`config/__init__.py:429`) and reused in `make.py:28` — same regex, no drift

Registration on `ToolsConfig` (`config/__init__.py:609`):
```python
make: MakeToolConfig = field(default_factory=MakeToolConfig)
```
Also documented in `ToolsConfig` docstring (`__init__.py:594`).

Export in `__all__` (`config/__init__.py:882`): `"MakeToolConfig"` ✅

**Section 2 verdict: correct.**

---

## Section 3 — Manifest entry correctness

`src/yoker/builtin/__init__.py`:

- Import (`__init__.py:14`): `from yoker.builtin.make import make` ✅
- `__all__` (`__init__.py:29`): `"make"` listed alphabetically between `"list"` and `"mkdir"` ✅
- `__YOKER_MANIFEST__.tools` (`__init__.py:47`): `[..., list, make, mkdir, ...]` — `make` is a static built-in (not Session-injected, not a factory), matching `git`, `read`, etc. ✅

`make` is correctly treated as a static built-in tool loaded by the plugin loader from `__YOKER_MANIFEST__`. It is NOT in the Session-injected category (like `agent`/`send_message`), and it is NOT a factory (like `make_skill_tool`). This matches the design §7.2.

**Section 3 verdict: correct.**

---

## Section 4 — Convention adherence

### Pattern match with `git.py`

| Convention | `git.py` | `make.py` | Match |
|------------|----------|-----------|-------|
| Module-level logger | `logger = get_logger(__name__)` | same | ✅ |
| Module-level regex/frozenset | `FORBIDDEN_CHARS`, `_TARGET_RE`-equivalent | `_TARGET_RE`, `_FORBIDDEN_TARGET_CHARS` | ✅ |
| `async def` signature | yes | yes | ✅ |
| `ctx.config` isinstance defensive check | yes (against `GitToolConfig`) | yes (against `MakeToolConfig`, `make.py:46-48`) | ✅ |
| `ToolResult` with `success` + `error` on failure | yes | yes | ✅ |
| Subprocess with list args, no `shell=True` | yes | yes (verified by `test_command_is_list_not_shell`) | ✅ |

### `ToolContext` usage

`ctx.config` is typed as `ToolConfig` on `ToolContext` (`tools/context.py:37`); the isinstance check narrows to `MakeToolConfig` before accessing `.allowed_env_vars` / `.max_env_var_bytes` / `.timeout_ms` / `.max_output_kb`. Correct and defensive — matches `git.py`'s pattern.

### Guardrail integration

`"make"` added to `_FILESYSTEM_TOOLS` (`tools/guardrails/path.py:31`). This is the only guardrail change required. The `PathGuardrail.validate` dispatcher now runs root-containment on `make`'s `cwd` parameter via the per-parameter `guard_type = GuardType.PATH` on the `cwd` annotation. No `make`-specific branch added to `PathGuardrail.validate` (correct — the design §5 explained no make-specific extension/size/existence check is needed).

Verified by tests `test_make_in_filesystem_tools`, `test_guardrail_blocks_cwd_outside_allowed`, `test_guardrail_blocks_traversal`, `test_guardrail_allows_cwd_inside_allowed`.

### Subprocess execution

The implementation uses `subprocess.Popen` + `proc.communicate(timeout=...)` + `os.killpg(pid, SIGKILL)` on timeout (`make.py:93-124`), with `start_new_session=True` so the child leads its own process group. This is a **justified deviation** from the original design §8.1 which used `subprocess.run`: the per-target-allowlist-response.md introduces R4 (process-group kill on timeout), which `subprocess.run`'s internal context manager does not provide — `subprocess.run` kills only the direct child, not the process group, so a `make` target that spawns children (e.g., `pytest` spawning test subprocesses) could leak past the timeout. `Popen` + `killpg` is the correct primitive for R4. Test `test_process_group_killed_on_timeout` verifies `os.killpg` is called with `SIGKILL` and the child's pid.

**Section 4 verdict: adheres to conventions; the one deviation (Popen vs run) is earned by R4.**

---

## Section 5 — Owner's approved design: quoted and confirmed satisfied

Owner's approved design (per-target-allowlist-response.md §2 "Concrete dataclass sketch"):

```python
@dataclass
class MakeToolConfig(ToolConfig):
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

Implementation in `src/yoker/config/__init__.py:451-481` matches this sketch **character-for-character** (modulo the docstring, which is a docstring, not logic).

Validation semantics from §2 "Validation semantics" trace table, verified against test cases:
- `make("test", {"TEST": "foo.py"})` with `allowed_env_vars={"test": ("TEST",)}` → allowed (test `test_env_var_allowed_and_propagated`) ✅
- `make("build", {"TEST": "foo.py"})` (target not in dict) → denied (test `test_env_var_denied_when_target_not_in_allowlist`) ✅
- `make("test", {"MAKEFLAGS": ...})` even if allowlisted → denied by hard denylist (test `test_makeflags_denied_even_if_allowlisted`) ✅
- `make("test", {"TEST": "x"*4097})` → denied by value cap (test `test_oversize_value_rejected`) ✅
- Newline/NUL in value → denied (tests `test_newline_in_value_rejected`, `test_nul_in_value_rejected`) ✅

The env guardrail (`src/yoker/tools/guardrails/env.py`) implements the three-layer check (per-target allowlist → hard denylist → value rules) in the exact order specified in §2. The hard denylist includes `MAKEFLAGS`, `MFLAGS`, `YOKER_*`, `LD_*`/`DYLD_*`, `GIT_*`, `BASH_ENV`, `ENV`, `PYTHON*`, `NODE_*`, `IFS`, `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`/`NO_PROXY`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `HOME`/`USER`/`LOGNAME`, API keys, `PATH` — matches the framework-invariant intent in §2.

**Section 5 verdict: owner's approved design is satisfied.**

---

## Section 6 — Simplicity check (unearned additions)

Walked the implementation looking for unearned classes / indirections / wrappers / fields beyond the approved design.

| Addition | Earned? | Verdict |
|----------|---------|---------|
| `subprocess.Popen` + `os.killpg` + `start_new_session=True` (replaces `subprocess.run` from original design) | Earned by R4 (process-group kill on timeout) — `subprocess.run` cannot kill the process group | Keep |
| `_kill_process_group(pid)` helper (`make.py:156-161`) | 5-line helper used once; isolates the best-effort try/except so the timeout path reads cleanly. Matches the project's helper style (`_truncate`, `_render_*` in other tools) | Keep |
| `_truncate(text, max_bytes)` helper (`make.py:143-153`) | Matches design §8.2 verbatim — not an addition | Keep |
| `isinstance(make_config, MakeToolConfig)` defensive check (`make.py:46-48`) | Matches `git.py` pattern; defensive against misconfigured registries | Keep |
| `_FORBIDDEN_TARGET_CHARS` frozenset (`make.py:32`) | Explicit/self-documenting; design §4 specified this exact pattern (redundant with regex but matches `git`'s `FORBIDDEN_CHARS` convention) | Keep |
| `stripped.startswith("-")` check (`make.py:56-57`) | Redundant with `_TARGET_RE` (first char must be alnum), but design §4 specified leading-dash rejection explicitly. Self-documenting | Keep |
| `\x00` in `_FORBIDDEN_TARGET_CHARS` | Redundant with regex, but defensive against regex changes | Keep |
| `stripped = target.strip()` for empty check, then `len(target) > 256` and regex against raw `target` | Slight asymmetry (validates stripped for emptiness, raw for length/regex). Whitespace-only targets fail the regex anyway, so no behavior gap. | Cosmetic only — no action required |
| `validated_env = dict(env_vars)` after validation (`make.py:82`) | Copies the dict before merging into `os.environ` so later mutation of the caller's dict cannot affect the subprocess env. Defensive copy, 1 line | Keep |
| Test file path `tests/test_tools/test_make.py` vs design's `tests/test_builtin/test_make.py` | Functionally equivalent; `test_tools/` is consistent with other tool guardrail tests (e.g. `test_env_guardrail.py` lives there too) | Keep — no action |

**No unearned classes, wrappers, or fields detected.** The implementation introduces no new abstractions beyond what the approved design specified. The single deviation from the original design (Popen vs run) is earned by R4 and consistent with the owner-approved per-target-allowlist-response.md.

---

## Section 7 — Verdict

**approved**

The implementation satisfies the approved Option A design on every axis reviewed:

1. API surface (signature, annotations, ToolResult shape) — aligned.
2. Config schema (MakeToolConfig fields, validators, registration, export) — correct.
3. Manifest entry (import, `__all__`, `__YOKER_MANIFEST__.tools`) — correct.
4. Convention adherence (git.py pattern, ToolContext usage, PathGuardrail wiring) — adheres; the one deviation (`Popen` + `killpg`) is earned by R4.
5. Owner's approved design — quoted in §5 and confirmed satisfied, character-for-character on the dataclass sketch; all validation-semantics traces verified by tests.
6. Simplicity — no unearned additions.

Minor cosmetic observations (no action required):
- `stripped` vs raw `target` asymmetry in validation (cosmetic only; no behavior gap because the regex rejects whitespace).
- Test file lives at `tests/test_tools/test_make.py` rather than the design's `tests/test_builtin/test_make.py` — consistent with the sibling `test_env_guardrail.py` location.

Ready to merge.