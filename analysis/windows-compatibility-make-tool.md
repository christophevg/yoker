# Windows Compatibility Analysis — `make` Tool (MBI-009 T1, PR #48)

**Scope:** `src/yoker/builtin/make.py`, `src/yoker/tools/guardrails/env.py`,
`src/yoker/config/__init__.py` (`MakeToolConfig`), `tests/test_tools/test_make.py`,
`tests/test_tools/test_env_guardrail.py`.

**Method:** static analysis of the implementation against CPython's
`subprocess`/`signal`/`os` behavior on Windows, cross-checked with the
existing `analysis/security-env-vars-proposal.md` (which already flagged the
Windows case-sensitivity issue at §2.10 and §6.2) and the established
project pattern for platform branches
(`src/yoker/context/validator.py:47`, `src/yoker/context/persisted.py:25`).

---

## 1. POSIX-only API calls identified

| # | File:line | API | Windows behavior | Impact on `make` tool |
|---|-----------|-----|------------------|-----------------------|
| A1 | `make.py:145` | `subprocess.Popen(..., start_new_session=True)` | Parameter is accepted by `Popen.__init__` on all platforms (it's in the signature) but only the POSIX `_execute_child` uses it. On Windows it is a **silent no-op**: the child is NOT placed in a new process group. | Happy path: works (no error). Timeout path: the precondition for R4 (child leads a process group) is silently false on Windows, so recipe children are NOT killable as a group. |
| A2 | `make.py:204` | `os.killpg(pid, signal.SIGKILL)` | **`os.killpg` does not exist on Windows** — `AttributeError` at module-attribute lookup. | On a timeout, `_kill_process_group` raises `AttributeError`. The `except (ProcessLookupError, PermissionError, OSError)` clause does **not** catch `AttributeError`, so it propagates. The subsequent `proc.communicate(timeout=5)` reaping never runs. The tool call crashes with an unhandled exception instead of returning a `ToolResult`. |
| A3 | `make.py:204` | `signal.SIGKILL` | **`signal.SIGKILL` does not exist on Windows.** Windows has `SIGTERM`, `SIGINT`, `CTRL_*` events but no `SIGKILL`. | Same as A2: `AttributeError` on attribute lookup, uncaught by the except clause. Even if `os.killpg` existed, this would still raise. |
| A4 | `make.py:138-146` | `subprocess.Popen` with list argv | Works on Windows. | No issue. |
| A5 | `make.py:136` | `env = {**os.environ, **validated_env}` | Works, but `os.environ` on Windows is case-insensitive (`NTEnviron`), so a `validated_env` key like `Path` silently overwrites `PATH`. | See §3 — this is the mechanism by which the case-sensitivity gap in the denylist is exploited. |

### Secondary POSIX-only concern

| # | File:line | API | Windows behavior | Impact |
|---|-----------|-----|------------------|--------|
| B1 | `make.py:138` | `["make", target]` argv | `make` is not standard on Windows. GNU make can be installed (MSYS2, Cygwin, Chocolatey, WSL) but is not guaranteed. | `FileNotFoundError` is already caught at `make.py:147-149` with the message "make is not installed or not found in PATH". This is correctly handled — no code change needed. Tests that invoke real `make` (see §4) will fail/skip on Windows without a `make` binary. |
| B2 | `make.py:50` | `_TARGET_RE = r"^[A-Za-z0-9][A-Za-z0-9._%+\-]*$"` | Target name syntax is GNU make syntax, which is the same on Windows. | No issue. |
| B3 | `make.py:113` | `Path(cwd).resolve()` | Works on Windows. `PathGuardrail` already has Windows-aware forbidden prefixes (`context/validator.py:40-50`). | No issue. |

---

## 2. Windows-specific env vars to add to the hard denylist

The current `_DENIED_EXACT` set in `env.py` is POSIX-oriented. Windows has
equivalents for several denied POSIX names that are NOT in the denylist, plus
Windows-unique injection/identity vectors.

### 2.1 Windows equivalents of already-denied POSIX names

| POSIX name (denied) | Windows equivalent (NOT denied) | Risk |
|---------------------|----------------------------------|------|
| `HOME` | `USERPROFILE` | Identity / sandbox escape — same role as `HOME` (home dir, credential lookup). |
| `USER` | `USERNAME` | Identity — same role. |
| `USER` | `USERDOMAIN` | Identity / domain context. |
| `PATH` | (already denied, but case-insensitive bypass — see §3) | Executable resolution hijack. |

### 2.2 Windows-unique injection / identity / config vectors

| Name | Why deny |
|------|----------|
| `USERPROFILE` | Home dir; equivalent of `HOME`. Credential files, `.gitconfig`, `.npmrc`, etc. live here. |
| `USERNAME` | Identity; equivalent of `USER`. |
| `USERDOMAIN` | Identity / domain context. |
| `APPDATA` | Per-user app config / credential store location (e.g., npm, pip caches). |
| `LOCALAPPDATA` | Per-user app data; same as `APPDATA`. |
| `PROGRAMDATA` | System-wide app data; shared credential stores. |
| `PROGRAMFILES` | System install root. |
| `PROGRAMFILES(X86)` | 32-bit system install root. |
| `SystemRoot` | Windows system directory (`C:\Windows`). Recipes resolve `cmd.exe`, `powershell.exe` via this. Redirecting it points the recipe at a malicious `cmd.exe`. |
| `WINDIR` | Legacy alias for `SystemRoot`. Same risk. |
| `COMSPEC` | Path to the command interpreter (`cmd.exe` by default). Redirecting this is the Windows analog of `BASH_ENV` — recipe shells invoke it. |
| `PATHEXT` | Ordered list of executable extensions (`.COM;.EXE;.BAT;.CMD;...`). Prepending `.PS1` or a malicious extension turns `make` recipe `foo` into `foo.bat` / `foo.ps1` execution. |
| `SYSTEMDRIVE` | Boot drive root. |
| `HOMEDRIVE` | Home dir drive component. |
| `HOMEPATH` | Home dir path component. |
| `TEMP` | Temp dir; recipes write here. Redirecting to an allowed path enables artifact injection. |
| `TMP` | Alias for `TEMP`. |

### 2.3 Windows DLL-injection vectors (analog of `LD_*` / `DYLD_*`)

POSIX `LD_PRELOAD` / `LD_LIBRARY_PATH` / `DYLD_*` have no direct Windows
equivalent in env-var form (Windows DLL search order is registry- and
manifest-driven, not env-driven). The closest env-driven Windows vectors are:

| Name | Why deny |
|------|----------|
| `PATH` (prepend) | Prepending a malicious dir to `PATH` causes `LoadLibrary`/`SearchPath` to pick up a malicious `version.dll`, `msvcp140.dll`, etc. (DLL search-order hijacking). Already denied on POSIX; case-insensitive bypass is the real gap on Windows (§3). |

There is no Windows env var that directly mirrors `LD_PRELOAD`. The denylist
prefixes `LD_` and `DYLD_` are harmless no-ops on Windows (no env var will
match them in practice).

### 2.4 Recommendation — Windows-specific denylist addition

Add the following to `env.py`, gated by a Windows-only case-insensitive check
(see §3 for the matching strategy):

```python
_WIN_DENIED_EXTRA: frozenset[str] = frozenset({
  "USERPROFILE", "USERNAME", "USERDOMAIN",
  "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
  "PROGRAMFILES", "PROGRAMFILES(X86)",
  "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT",
  "SYSTEMDRIVE", "HOMEDRIVE", "HOMEPATH",
  "TEMP", "TMP",
})
```

This is the same set the prior `analysis/security-env-vars-proposal.md:419-422`
sketched (it listed `PATH`, `PATHEXT`, `COMSPEC`, `SYSTEMROOT`, `WINDIR` as
the core minimum). The extended set above adds the identity/app-data cluster
(`USERPROFILE`, `USERNAME`, `USERDOMAIN`, `APPDATA`, `LOCALAPPDATA`,
`PROGRAMDATA`, `PROGRAMFILES`, `PROGRAMFILES(X86)`, `SYSTEMDRIVE`,
`HOMEDRIVE`, `HOMEPATH`, `TEMP`, `TMP`) for completeness, since each is the
Windows analog of a POSIX name we already deny (`HOME`, `USER`, `LOGNAME`).

---

## 3. Case-sensitivity analysis

### 3.1 The bug

Windows env var names are **case-insensitive**. `PATH`, `Path`, `path` are the
same variable. The current denylist check is exact-string:

```python
# env.py:83
return name in _DENIED_EXACT or _DENIED_PREFIX_RE.match(name) is not None
```

On Windows, an agent can bypass the denylist by setting:

| Denied name | Bypass variant | Effect |
|-------------|----------------|--------|
| `PATH` | `Path`, `path`, `pAtH` | Overwrites `PATH` via `os.environ`'s case-insensitive merge in `env = {**os.environ, **validated_env}`. Executable-resolution hijack. |
| `HOME` (not in `_DENIED_EXACT` on Windows — see §2) | `HOME` (works) | Already not denied on Windows. |
| `MAKEFLAGS` | `MakeFlags`, `makeflags` | Reopens the `--eval` injection vector that the denylist was added to close (per `analysis/security-env-vars-proposal.md` §2.2). This is the most serious bypass. |
| `YOKER_TRUST_SOURCE` | `Yoker_Trust_Source` | Bypasses the framework trust gate. |
| `LD_PRELOAD` | `Ld_Preload` | Less impactful on Windows (no dynamic loader honoring it), but the prefix regex `LD_` is case-sensitive — `Ld_` evades the prefix match. On Windows this is low-impact; on a hypothetical POSIX-with-case-insensitive-env (none exist) it would be critical. |

The prefix regex `_DENIED_PREFIX_RE` is also case-sensitive:
`r"^(?:YOKER_|LD_|DYLD_|BASH_FUNC_|...)"` — `yoker_` and `Ld_` do not match.

### 3.2 The allowlist bypass

The per-target allowlist (`make_config.allowed_env_vars.get(target, ())`) is
also exact-string. An operator who configures `allowed_env_vars = {"test":
("TEST",)}` on Windows intends to permit only `TEST`. An agent setting `Test`
or `test`:

- **Allowlist check:** `name not in allowed_names` — `"Test" not in ("TEST",)`
  is True, so it is rejected as "not in per-target allowlist". This is
  **safe by accident** — the allowlist's exact-match happens to reject
  case variants on Windows, which is the conservative direction. Good.
- **Denylist check:** never reached (rejected at allowlist first).

So the allowlist is NOT bypassable by case-folding on Windows — the agent
must use the exact case the operator configured. The vulnerability is
specifically in the **denylist**: a name that the operator *did* allowlist
(e.g., `MAKEFLAGS` if an operator mistakenly allowlists it) can be bypassed
by case-folding past the denylist. More critically, names the operator
allowlists in a benign way (e.g., `PATH` is not allowlisted, but `Path` is
also not allowlisted) — so the case-folding bypass on the denylist only
matters when the operator has allowlisted a denied name's case-variant.

**Net risk:** The case-sensitivity gap is a **defense-in-depth failure**, not
a primary bypass. The allowlist's exact-match already blocks case-variants.
The denylist's job is to catch operator mistakes (allowlisting `MAKEFLAGS`);
on Windows it fails to catch `MakeFlags` if an operator allowlists
`MakeFlags`. This is a real gap but a narrow one. Still worth fixing — the
cost is low and the framework-invariant principle ("the operator cannot waive
framework invariants") demands it.

### 3.3 Recommended fix — case-insensitive denylist on Windows

In `env.py`, add a platform-aware path:

```python
import sys

_IS_WINDOWS = sys.platform == "win32"

# On Windows, env var names are case-insensitive. The denylist must be
# checked case-insensitively for the security-sensitive names, so that
# `Path`, `MakeFlags`, `Yoker_Trust_Source` cannot bypass the exact-match
# denylist. POSIX stays exact-match (env vars are case-sensitive there).
_WIN_DENIED_EXTRA_UPPER = frozenset(n.upper() for n in _WIN_DENIED_EXTRA)

def is_denied_env_var(name: str) -> bool:
  if name in _DENIED_EXACT:
    return True
  if _DENIED_PREFIX_RE.match(name) is not None:
    return True
  if _IS_WINDOWS:
    upper = name.upper()
    if upper in _WIN_DENIED_EXTRA_UPPER:
      return True
    # Case-insensitive prefix match on Windows
    if upper.startswith(("YOKER_", "LD_", "DYLD_", "BASH_FUNC_",
                         "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
      return True
    # Case-insensitive exact match against _DENIED_EXACT on Windows
    if upper in {n.upper() for n in _DENIED_EXACT}:
      return True
  return False
```

The `_DENIED_EXACT` upper-cased set can be precomputed at module load. The
`_DENIED_PREFIX_RE` is already anchored — on Windows we add a parallel
case-insensitive prefix check.

---

## 4. Test skip strategy

### 4.1 Tests that invoke real `make`

The following tests in `tests/test_tools/test_make.py` invoke the real `make`
binary via `subprocess.Popen`:

- `TestMakeToolTargetValidation.test_check_succeeds` (and all parametrized
  siblings in the same class — they run `make` against a Makefile fixture).
- `TestMakeToolEnvVars.test_env_var_allowed_and_propagated`
- `TestMakeToolEnvVars.test_env_var_denied_when_*` (several)
- `TestMakeToolOutputTruncation.test_output_truncated_when_over_limit`
- `TestMakeToolOutputTruncation.test_small_output_not_truncated`
- `TestMakeToolTimeout.test_timeout_returns_failure`
- `TestMakeToolTimeout.test_timeout_clamped_to_config_ceiling`
- `TestMakeToolTimeout.test_timeout_minimum_one_second`
- `TestMakeToolErrorHandling.test_missing_makefile_returns_nonzero`
- `TestMakeToolErrorHandling.test_nonzero_exit_still_returns_structured_result`
- `TestMakeToolResultStructure.test_success_result_dict_keys`
- `TestMakeToolResultStructure.test_stderr_separate_from_stdout`
- `TestMakeToolIntegrationEndToEnd.test_make_check_end_to_end`
- `TestMakeToolIntegrationEndToEnd.test_make_test_with_env_end_to_end`

These will fail on Windows if `make` is not installed (the `FileNotFoundError`
path returns a `ToolResult(success=False)`, but the tests assert
`result.success is True` for the happy paths).

### 4.2 Tests that mock `os.killpg` / `subprocess.Popen`

- `TestMakeToolTimeout.test_process_group_killed_on_timeout` — mocks
  `make_module.os.killpg`. On Windows, `make_module.os.killpg` does not
  exist, so `mocker.patch.object(make_module.os, "killpg")` will fail to
  find the attribute. This test cannot run on Windows as written.
- `TestMakeToolErrorHandling.test_make_not_installed` — mocks
  `subprocess.Popen`. Works on Windows (Popen exists on both).
- `TestMakeToolSubprocessSecurity.test_command_is_list_not_shell` — mocks
  `subprocess.Popen`. Works on Windows, and asserts
  `kwargs.get("start_new_session") is True`. This assertion will still pass
  on Windows (the kwarg is passed, just ignored). No skip needed.

### 4.3 Recommended skip markers

Add a module-level skip decorator for the whole module (simplest), or
per-class skips:

```python
import sys
import pytest

pytestmark = pytest.mark.skipif(
  sys.platform == "win32",
  reason="make tool requires POSIX process-group support (os.killpg, SIGKILL); "
         "Windows guardrail TBD — see analysis/windows-compatibility-make-tool.md",
)
```

This is the simplest strategy: skip the entire `test_make.py` module on
Windows until either (a) full Windows support is implemented per §5 Option A,
or (b) the no-Windows guardrail of §5 Option B is in place (in which case the
tool itself returns a clean `ToolResult(success=False)` on Windows and a
small set of tests can run to verify that path).

The env guardrail tests (`test_env_guardrail.py`) do NOT need skipping — they
test pure Python functions (`is_denied_env_var`, `validate_env_vars`) with no
subprocess dependency. They should, however, gain Windows-specific
parametrize cases once §3's case-insensitive denylist is implemented (e.g.,
`pytest.param("Path", marks=pytest.mark.skipif(sys.platform!="win32", ...))`
or a dedicated `TestIsDeniedEnvVarWindowsCaseSensitivity` class gated by
`skipif`).

---

## 5. Proposed fix approach — recommendation: Option B (no-Windows guardrail)

### 5.1 The two options

**Option A — Full Windows support.** Make the tool work correctly on Windows:

1. Replace `start_new_session=True` with a platform branch:
   `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` on Windows,
   `start_new_session=True` on POSIX.
2. Replace `_kill_process_group` with a platform branch: on Windows use
   `proc.kill()` (sends `TerminateProcess`) plus
   `subprocess.CREATE_NEW_PROCESS_GROUP` + `SendCTRL_BREAK` if we want to
   kill children — but Windows process groups via `CREATE_NEW_PROCESS_GROUP`
   only allow `CTRL_BREAK_EVENT` signaling, not `TerminateProcess` on the
   whole group. To kill the whole tree on Windows you need either Job Objects
   (`psutil` or a `JOBOBJECT_BASIC_LIMIT_INFORMATION` wrapper) or recursive
   `taskkill /T /F /PID`. Both are significantly more code than the POSIX
   3-line `killpg`.
3. Add the Windows env var denylist (§2.4) and case-insensitive matching (§3.3).
4. Add Windows CI to verify.

**Option B — No-Windows guardrail.** The tool refuses to run on Windows with
a clear error, and tests skip on Windows:

1. At the top of `make()`, check `sys.platform` and return
   `ToolResult(success=False, error="make tool requires POSIX process-group support; not available on Windows")` on `win32`.
2. Still apply §3.3 (case-insensitive denylist) and §2.4 (Windows env var
   denylist) as defense in depth — even though the tool refuses to spawn,
   the guardrail code is shared and should be correct for any future
   subprocess-spawning tool that does support Windows.
3. Skip `test_make.py` on Windows per §4.3.

### 5.2 Recommendation — Option B, with the env guardrail fixes from §2 and §3

Per the **Simplicity Principle** ("Slim, tight, concise is the default. Avoid
indirections, wrappers, and redundant work. Less is the default unless there
is no other way."), Option B is the right choice for 1.0:

1. **The `make` binary is not standard on Windows.** Even with full Windows
   process-group support, the tool is useful only to the subset of Windows
   users who installed GNU make via MSYS2/Cygwin/Chocolatey/WSL. That
   subgroup is better served by running yoker under WSL (where the POSIX
   path works as-is). The cost of Option A is borne by the project for a
   narrow user set with a working alternative.

2. **Windows process-tree kill is genuinely complex.** `os.killpg` is a
   1-line operation. The Windows equivalent requires either Job Objects
   (~50 lines of `ctypes` for `CreateJobObject`, `AssignProcessToJobObject`,
   `SetInformationJobObject` with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and
   a handle lifetime wrapper) or `taskkill /T /F /PID` (shells out to a
   second subprocess, reintroducing the orphaned-children problem if
   `taskkill` itself is killed). Neither is "slim, tight, concise". This is
   the "no other way" condition the Simplicity Principle asks for — and the
   conclusion is that the right answer is **don't do it**, not "do it the
   hard way".

3. **The R4 security invariant (no orphaned recipe children) cannot be
   upheld on Windows without Job Objects.** A half-measure (`proc.kill()`
   only) silently regresses R4 — the security review
   (`reporting/make-tool/security-review.md:17`) verified R4 on POSIX via
   `os.killpg`; the same review would FAIL on Windows with `proc.kill()`
   alone. Shipping a tool that silently downgrades a documented security
   invariant on one platform is worse than refusing to run.

4. **The owner's design throughout MBI-009 T1 has been "minimal correct
   scope".** The owner rejected generic env-vars-across-all-tools in favor
   of make-only; rejected `args` in favor of `env_vars` only; chose Option A
   (per-target allowlist) over Option B (per-target sub-sections) on
   schema-clarity grounds. The same instinct applies here: the minimal
   correct scope for Windows is "not supported, clear error".

5. **The env guardrail fixes (§2, §3) are still worth doing as defense in
   depth.** The `env.py` module is framework infrastructure that any future
   subprocess-spawning tool will reuse. If a future Windows-supporting tool
   calls `validate_env_vars`, the denylist must already be correct for
   Windows. The cost is ~15 lines in `env.py` (a Windows-only frozenset and
   a `sys.platform == "win32"` branch in `is_denied_env_var`). This is
   proportional and aligned with the existing project pattern
   (`context/validator.py:47`, `context/persisted.py:25`).

### 5.3 Concrete changes for Option B

**`src/yoker/builtin/make.py`** — add a platform gate at the top of `make()`
(after config validation, before target validation, so a misconfigured tool
fails fast on the same path on all platforms):

```python
import sys
# ...
if sys.platform == "win32":
  return ToolResult(
    success=False,
    error="make tool requires POSIX process-group support (os.killpg, SIGKILL); "
          "not available on Windows. Run yoker under WSL to use the make tool.",
  )
```

No change to `start_new_session=True`, `os.killpg`, or `signal.SIGKILL` —
they remain as-is for the POSIX path.

**`src/yoker/tools/guardrails/env.py`** — apply §2.4 and §3.3 (Windows env
var denylist + case-insensitive matching). This is defense in depth and
correctness for future Windows-supporting tools; the `make` tool's own
Windows guardrail makes this unreachable from `make` today, but it protects
any future caller.

**`tests/test_tools/test_make.py`** — module-level `pytestmark` skip on
`win32` per §4.3. Add one Windows-only test class (gated by
`pytest.mark.skipif(sys.platform != "win32", ...)`) verifying the platform
gate returns the expected `ToolResult` — this keeps the Windows path
covered without running the POSIX subprocess tests on Windows.

**`tests/test_tools/test_env_guardrail.py`** — add a
`TestIsDeniedEnvVarWindowsCaseSensitivity` class gated by
`pytest.mark.skipif(sys.platform != "win32", ...)` verifying `Path`,
`MakeFlags`, `Yoker_Trust_Source`, `Userprofile`, `Comspec` are denied on
Windows. Add a parallel test class verifying POSIX still rejects only the
exact case (so the Windows branch doesn't accidentally leak to POSIX).

**`README.md`** — add a "Platform support" note: "The `make` tool requires
POSIX process-group APIs (`os.killpg`, `SIGKILL`) and is not available on
Windows. Run yoker under WSL to use `make`." (One sentence in the tool
description.)

**`CLAUDE.md`** — add a one-line note under the `builtin/` section: "make
tool: POSIX-only (sys.platform gate); Windows returns a clear error."

---

## 6. Existing Windows patterns in the codebase

The project already has two platform branches that the proposed fix aligns
with:

| File:line | Pattern | Purpose |
|-----------|---------|---------|
| `src/yoker/context/validator.py:47` | `if platform.system() == "Windows": FORBIDDEN_PATH_PREFIXES = FORBIDDEN_PATH_PREFIXES_WINDOWS else: ...` | Select Windows-specific forbidden path prefixes (`C:\Program Files`, `C:\ProgramData`, `C:\System Volume Information`, etc.) vs UNIX (`/`, `/etc`, `/var`, `/root`, ...). |
| `src/yoker/context/persisted.py:25` | `if sys.platform != "win32": import fcntl else: fcntl = None` | `fcntl.flock` is POSIX-only; Windows has no file locking equivalent. The module gracefully degrades (no locking on Windows). |

The `make` tool's proposed `sys.platform == "win32"` gate
(`make.py`) and `sys.platform == "win32"` branch in `env.py` follow the
same pattern. Consistent with project conventions.

**Other subprocess tools:** `src/yoker/builtin/git.py:344` uses
`subprocess.run(cmd, capture_output=True, text=True, timeout=...)` with NO
`start_new_session` and NO process-group kill. On a timeout,
`subprocess.run` calls `Popen.kill()` (sends `TerminateProcess` on Windows,
`SIGKILL` on POSIX) on the direct child only — git's orphaned children are
possible on both platforms. The `git` tool therefore works on Windows
already, but with the same R4 residual risk (orphaned children) on both
platforms. The `make` tool is held to a stricter R4 bar because Makefile
recipes commonly spawn long-running children (`pytest`, `npm`, etc.), while
git operations typically do not. This justifies the asymmetry: `git` ships
on Windows, `make` does not.

---

## 7. Summary

**POSIX-only APIs in `make.py`:** `start_new_session=True` (silent no-op on
Windows), `os.killpg` (AttributeError on Windows), `signal.SIGKILL`
(AttributeError on Windows). The timeout path crashes with an unhandled
`AttributeError` on Windows; the happy path works only if `make` is
installed.

**Env var denylist gaps on Windows:** (a) Windows-specific identity/config
names (`USERPROFILE`, `USERNAME`, `SystemRoot`, `COMSPEC`, `PATHEXT`, etc.)
are not in the denylist; (b) the denylist's exact-string match is
case-sensitive, but Windows env vars are case-insensitive — `Path`,
`MakeFlags`, `Yoker_Trust_Source` bypass the denylist. The allowlist's
exact-match accidentally blocks case-variant bypass at the allowlist layer,
narrowing the real exposure to operator-mistake cases.

**Recommended approach:** **Option B — no-Windows guardrail.** Add a
`sys.platform == "win32"` gate at the top of `make()` returning a clear
`ToolResult` error. Apply the env guardrail fixes (§2.4 Windows denylist,
§3.3 case-insensitive matching) as defense in depth for future
subprocess-spawning tools. Skip `test_make.py` on Windows with a
module-level `pytestmark`. This aligns with the Simplicity Principle (Windows
process-tree kill requires Job Objects / `taskkill /T`, neither is "slim"),
the owner's minimal-correct-scope instinct throughout MBI-009 T1, and the
existing project platform-branch pattern in `context/validator.py:47` and
`context/persisted.py:25`.

**Files to modify (Option B):**
- `src/yoker/builtin/make.py` — add `sys.platform` gate (~5 lines).
- `src/yoker/tools/guardrails/env.py` — add `_WIN_DENIED_EXTRA` frozenset
  and case-insensitive branch in `is_denied_env_var` (~15 lines).
- `tests/test_tools/test_make.py` — module-level `pytestmark` skip + a
  small Windows-only test class for the platform gate.
- `tests/test_tools/test_env_guardrail.py` — Windows case-sensitivity test
  class + POSIX-exact-case regression class.
- `README.md` and `CLAUDE.md` — one-line platform-support notes.

**No code implementation in this analysis.** Code changes to be tasked
separately.
