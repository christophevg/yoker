# Security Review: `make` Tool (PR #48, Stage b)

**Reviewer:** security-engineer
**Date:** 2026-07-21
**Branch:** `feature/make-tool`
**Reference analyses:**
- `analysis/security-make-tool.md` (R1–R5)
- `analysis/security-env-vars-proposal.md` (env_vars abuse vectors, hard denylist, value validation)

## Section 1 — R1–R5 Status

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| **R1** | `"make"` in `_FILESYSTEM_TOOLS`; PathGuardrail fires on `cwd` | **VERIFIED** | `src/yoker/tools/guardrails/path.py:30-32` adds `"make"` to the frozenset. `src/yoker/builtin/make.py:40` annotates `cwd` with `PathArg(...)`. Harness dispatch (`core/_processing.py:531-542`) passes the raw `cwd` string to `PathGuardrail.validate("make", cwd)`, which no longer short-circuits. `test_guardrail_blocks_cwd_outside_allowed` and `test_guardrail_blocks_traversal` confirm. |
| **R2** | Reject leading `-`; reject empty/whitespace target | **VERIFIED** | `make.py:54-57` rejects empty `stripped` and leading `-`. Additionally `_TARGET_RE` (`^[A-Za-z0-9][A-Za-z0-9._%+\-]*$`, line 28) enforces first-char-alphanumeric, which is strictly stronger than a leading-`-` check and also rejects spaces, `=`, and other flag-injection chars. Tests: `test_leading_dash_rejected`, `test_flag_injection_rejected` (`-i`, `-j`, `-C /tmp`), `test_empty_target_rejected`. |
| **R3** | Forbidden chars include `\n\r\x00` plus owner's five (`;|&$` + backtick) | **VERIFIED** | `make.py:32` `_FORBIDDEN_TARGET_CHARS = frozenset({";", "|", "&", "$", "`", "\n", "\r", "\x00"})` — exactly the git `FORBIDDEN_CHARS` set plus the owner's five. Tests: `test_target_with_newline_rejected`, `test_target_with_semicolon_rejected`. |
| **R4** | `start_new_session=True`; `os.killpg` on `TimeoutExpired` | **VERIFIED** | `make.py:100` passes `start_new_session=True` to `Popen`. `make.py:112-124` catches `TimeoutExpired`, calls `_kill_process_group(proc.pid)` which calls `os.killpg(pid, SIGKILL)` (line 159), then reaps with a 5 s `communicate` grace. Developer's deviation from `subprocess.run` to `Popen` is correct and justified: `run()` does not expose the child `Popen` on `TimeoutExpired`, so `proc.pid` would be unreachable. `test_process_group_killed_on_timeout` mocks `os.killpg` and asserts it is called with the child pid and `SIGKILL`. |
| **R5** | Document env-inheritance residual risk | **PARTIAL / MINOR GAP** | `DEVELOPMENT.md:1262-1271` documents R1–R5 but **redefines R5** as "env_vars validated against per-target allowlist + hard denylist + value rules" — that is the env_vars mitigation, not the original R5. The original R5 (`security-make-tool.md` §4) required documenting that **secrets in the yoker process env are readable by Makefile recipes via `printenv`/`env`/`$$VAR`** (Medium-severity residual risk accepted by owner). No README or DEVELOPMENT.md section states this residual risk. Non-blocking (Low severity, doc-only). |

## Section 2 — Hard Denylist Completeness Audit

Reference: `analysis/security-env-vars-proposal.md` §3 caveat 2 (required) and §6.2 sketch (recommended).

### Covered (exact or prefix)

| Category | Entries | Mechanism |
|----------|---------|-----------|
| Framework trust gates | `YOKER_TRUST_SOURCE`, `YOKER_ALLOW_CUSTOM_BASE_URL`, `YOKER_*` prefix | exact + prefix |
| Shared-library injection | `LD_*` prefix (covers `LD_PRELOAD`, `LD_LIBRARY_PATH`, `LD_AUDIT`); `DYLD_*` prefix (covers `DYLD_INSERT_LIBRARIES`, `DYLD_LIBRARY_PATH`, `DYLD_FALLBACK_LIBRARY_PATH`) | prefix |
| Make-flag injection | `MAKEFLAGS`, `MFLAGS` | exact |
| Git workspace/config redirect | `GIT_DIR`, `GIT_WORK_TREE`, `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*` | exact + prefix |
| Shell startup injection | `BASH_ENV`, `ENV`, `BASH_FUNC_*` prefix | exact + prefix |
| Interpreter injection | `PYTHONSTARTUP`, `PYTHONPATH`, `PYTHONHOME`, `PERL5OPT`, `RUBYOPT`, `NODE_OPTIONS`, `NODE_PATH` | exact |
| Shell parsing | `IFS` | exact |
| Network/TLS redirect | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` | exact |
| Identity/sandbox escape | `HOME`, `USER`, `LOGNAME` | exact |
| API-key substitution | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_API_KEY`, `GITHUB_TOKEN` | exact |
| Inherited, not settable | `PATH` | exact |

### Gaps vs. §3 required hard-denylist (Low severity)

| Entry | Required by | Status | Risk |
|-------|-------------|--------|------|
| `PS1` | §3 caveat 2 | MISSING | Interactive-shell prompt injection — low relevance to non-interactive recipe shells |
| `PROMPT_COMMAND` | §3 caveat 2 | MISSING | Runs before each prompt in interactive bash — low relevance to recipes |
| `GIT_SSL_CAINFO` | §3 caveat 2 | MISSING | TLS CA redirect for git — redundant with `SSL_CERT_FILE`/`CURL_CA_BUNDLE` which are denied, but git-specific |

### Gaps vs. §6.2 sketch (recommended, Low severity)

| Entry | Status | Risk |
|-------|--------|------|
| `ZDOTDIR` | MISSING | zsh startup file redirect — narrow (zsh rarely used as recipe shell) |
| `PERL5LIB` | MISSING | `PERL5OPT` is denied; `PERL5LIB` is a parallel lib-path vector |
| `NODE_EXTRA_CA_CERTS` | MISSING | Node TLS CA redirect — parallel to `NODE_OPTIONS` (denied) |

### Documentation nit

`DEVELOPMENT.md:1242-1244` claims `PYTHON*` and `NODE_*` are denied via prefix, but `env.py` denies them via **exact match** only (`PYTHONSTARTUP`, `PYTHONPATH`, `PYTHONHOME`; `NODE_OPTIONS`, `NODE_PATH`). `PYTHONDEBUG`, `PYTHONUNBUFFERED`, `NODE_DEBUG` etc. are NOT denied. This is consistent with `security-env-vars-proposal.md` §2.1 (which listed only the exact names), but the DEVELOPMENT.md prose overstates coverage. Minor doc fix recommended.

**Net assessment:** The §3-required gaps (`PS1`, `PROMPT_COMMAND`, `GIT_SSL_CAINFO`) are Low severity and do not block shipment. The denylist covers every Critical/High vector (trust-gate bypass, shared-library injection, make-flag injection, git workspace redirect, shell startup, network/TLS redirect, API-key substitution). Recommend adding the three §3-required entries in a follow-up; the six total gaps are additive hardening, not exploitable holes given the per-target allowlist default-empty gate.

## Section 3 — Per-target Allowlist Enforcement

**VERIFIED.** `make.py:77`:
```python
allowed_names = make_config.allowed_env_vars.get(target, ())
```
- Target not in dict → `()` → all env vars rejected (deny-by-default).
- Empty dict `allowed_env_vars={}` → all targets get `()` → all env vars denied for all targets.
- Target in dict but name not in tuple → `name not in allowed_names` → rejected by `env.py:107-108`.

`MakeToolConfig.__post_init__` (`config/__init__.py:475-481`) validates target keys against `_TARGET_NAME_RE`, preventing malformed keys.

Tests: `test_env_var_denied_when_target_not_in_allowlist`, `test_env_var_denied_when_name_not_in_per_target_tuple`, `test_env_var_allowed_and_propagated` (positive case).

**Owner's Option A (`dict[str, tuple[str, ...]]`)** — confirmed satisfied.

## Section 4 — Value Validation

**MOSTLY VERIFIED, one minor gap.**

| Rule | Required by | Status | Evidence |
|------|-------------|--------|----------|
| Per-var byte cap (4 KB default) | §3 caveat 3 | VERIFIED | `env.py:121-122` `if len(vbytes) > max_bytes` |
| NUL byte rejection | §3 caveat 3 | VERIFIED | `env.py:113-114` |
| Newline (`\n`, `\r`) rejection | §3 caveat 3 | VERIFIED | `env.py:115-116` |
| Valid UTF-8 | §3 caveat 3 | VERIFIED | `env.py:117-120` (`UnicodeError` branch) |
| Non-string value rejection | §6.2 sketch | VERIFIED | `env.py:111-112` |
| **Total cap `sum(len(v)) <= 32768`** | §3 caveat 3, §6.2 sketch | **MISSING** | `env.py` has no running total. An operator who allowlists many names (e.g. 20 vars × 4 KB) could push ~80 KB of agent-constructed data into the subprocess env in one call. |

The 32 KB total cap is the one concrete deviation from the §3 required value rules. Severity is Low: the per-var 4 KB cap bounds single-var exfil, and the allowlist is operator-configured (default empty), so the agent cannot self-grant a large name set. Recommend adding a running `total` check in a follow-up. Non-blocking.

Tests: `test_oversize_value_rejected`, `test_value_at_limit_passes`, `test_nul_byte_in_value_rejected`, `test_newline_in_value_rejected`, `test_carriage_return_in_value_rejected`, `test_non_string_value_rejected`. No test for the 32 KB total cap (because it is not implemented).

## Section 5 — Subprocess Construction (No Bypass Paths)

**VERIFIED.** `make.py:91`:
```python
env = {**os.environ, **validated_env}
```
- Base is `os.environ` (inherit); agent-supplied `validated_env` overlays. Never replaces wholesale.
- `validated_env` is only populated **after** `validate_env_vars` returns `None` (line 78-82). On any failure, `make.py` returns `ToolResult(success=False, error=...)` before reaching the `Popen` call (line 93).
- No other call site constructs env for the subprocess.
- `Popen` receives `env=env` (line 96), `shell` is not set (default `False`), argv is a list `["make", target]` (line 94). `test_command_is_list_not_shell` confirms `shell is not True` and `start_new_session is True`.

No path where unvalidated env_vars reach the subprocess. No shell. No `target` interpolation into env. Clean.

**Audit logging:** `make.py:88` logs `env_keys=list(validated_env)` (names only, not values) at INFO — matches §5.5 of the env-vars proposal (avoid leaking secret values into logs).

## Section 6 — Test Coverage for Security Controls

| Bypass attempt | Test | File | Result |
|----------------|------|------|--------|
| `MAKEFLAGS` via env even if allowlisted | `test_makeflags_denied_even_if_allowlisted` | test_make.py | PASS |
| `--eval` via target (leading `-`) | `test_leading_dash_rejected`, `test_flag_injection_rejected` (`-i`, `-j`, `-C /tmp`) | test_make.py | PASS |
| `LD_PRELOAD` (and `LD_*` prefix) | `test_denied_names` parametrize | test_env_guardrail.py | PASS (unit) |
| `YOKER_TRUST_SOURCE` | `test_denied_yoker_prefix_rejected_even_if_allowlisted` | test_env_guardrail.py | PASS (unit) |
| Traversal cwd (`../../`) | `test_guardrail_blocks_traversal` | test_make.py | PASS |
| cwd outside project root (`/etc`) | `test_guardrail_blocks_cwd_outside_allowed` | test_make.py | PASS |
| Oversize value (> 4 KB) | `test_oversize_value_rejected` | test_make.py + test_env_guardrail.py | PASS |
| Newline in value | `test_newline_in_value_rejected` | test_make.py + test_env_guardrail.py | PASS |
| NUL in value | `test_nul_in_value_rejected` | test_make.py + test_env_guardrail.py | PASS |
| Carriage return in value | `test_carriage_return_in_value_rejected` | test_env_guardrail.py | PASS |
| Empty/whitespace target | `test_empty_target_rejected` | test_make.py | PASS |
| Target with `;` / space / newline | `test_target_with_semicolon_rejected`, `test_target_with_space_rejected`, `test_target_with_newline_rejected` | test_make.py | PASS |
| Process group killed on timeout | `test_process_group_killed_on_timeout` (mocks `os.killpg`) | test_make.py | PASS |
| Timeout enforced | `test_timeout_returns_failure`, `test_timeout_clamped_to_config_ceiling`, `test_timeout_minimum_one_second` | test_make.py | PASS |
| Output truncation | `test_output_truncated_when_over_limit` | test_make.py | PASS |
| No `shell=True` | `test_command_is_list_not_shell` | test_make.py | PASS |
| Non-dict env_vars | `test_env_vars_not_dict_rejected` | test_make.py | PASS |
| Deny-by-default (empty allowlist) | `test_empty_allowlist_rejects_all` | test_env_guardrail.py | PASS |

**Coverage assessment:** All ten bypass attempts named in the review criteria are covered, either end-to-end through the make tool or at the guardrail unit level. `LD_PRELOAD` and `YOKER_TRUST_SOURCE` are covered at the guardrail unit level (the make tool delegates to the same `validate_env_vars`); an end-to-end make-tool test for one of these would be a nice-to-have but is not required given the delegation is a single function call.

## Section 7 — Owner's Approved Security Design: Quote and Confirmation

> Q1 ✅: Hard non-configurable denylist (YOKER_*, LD_*, DYLD_*, MAKEFLAGS, MFLAGS,
> GIT_*, BASH_ENV, ENV, PYTHONPATH, PYTHONSTARTUP, etc.)
> Q2 ✅: Value validation (4 KB per-var, 32 KB total, no NUL, no newlines, valid UTF-8)
> Q3 ✅: Make-only (no change to GitToolConfig)
> Q4 ✅: Deny-by-default (empty allowed_env_vars dict = all denied)
> Option A ✅: Per-target allowlist `dict[str, tuple[str, ...]]`

| Approval point | Satisfied? | Notes |
|----------------|------------|-------|
| Q1 — hard non-configurable denylist | YES | `env.py` module-level frozenset + prefix regex; not configurable; enforced after allowlist. Three §3-required entries missing (`PS1`, `PROMPT_COMMAND`, `GIT_SSL_CAINFO`) — Low severity, see §2. |
| Q2 — value validation (4 KB, 32 KB, no NUL, no newlines, UTF-8) | PARTIAL | 4 KB per-var ✓, NUL ✓, newlines ✓, UTF-8 ✓. **32 KB total cap MISSING** — Low severity, see §4. |
| Q3 — make-only | YES | Only `MakeToolConfig` has `allowed_env_vars`; `GitToolConfig` unchanged. |
| Q4 — deny-by-default | YES | `allowed_env_vars: dict = field(default_factory=dict)`; `.get(target, ())` returns `()` for any target not in the dict. |
| Option A — per-target allowlist | YES | `dict[str, tuple[str, ...]]` confirmed in `MakeToolConfig` and used in `make.py:77`. |

## Section 8 — Verdict

### **APPROVED** (with non-blocking recommendations)

The `make` tool implementation satisfies every Blocking and High-severity control from `security-make-tool.md` and `security-env-vars-proposal.md`:

- R1 (PathGuardrail on `cwd`): verified, tested.
- R2 (leading-`-` / empty / whitespace rejection): verified, tested, and **over-delivered** via `_TARGET_RE` first-char-alphanumeric.
- R3 (forbidden chars including `\n\r\x00` + owner's five): verified, tested.
- R4 (process-group kill on timeout): verified via the developer's correct `Popen` deviation, tested with `os.killpg` mock.
- Hard denylist: every Critical/High vector covered; three Low-severity §3 entries missing.
- Per-target allowlist + deny-by-default: verified, tested.
- Value validation: 4 of 5 rules implemented; 32 KB total cap missing (Low).
- Subprocess construction: no bypass paths; inherit + overlay; no shell.

### Non-blocking recommendations (backlog / follow-up)

1. **Add `PS1`, `PROMPT_COMMAND`, `GIT_SSL_CAINFO` to `_DENIED_EXACT`** in `env.py` — closes the §3-required gaps. ~3 lines.
2. **Add the 32 KB total cap** to `validate_env_vars` (running `total += len(vbytes); if total > 32768: return ...`) — closes the §3 caveat 3 gap. ~3 lines + 1 test.
3. **Add `ZDOTDIR`, `PERL5LIB`, `NODE_EXTRA_CA_CERTS`** to `_DENIED_EXACT` — completes the §6.2 sketch. ~3 lines.
4. **Document the env-inheritance residual risk** (original R5) in `DEVELOPMENT.md` or `README.md`: "Secrets in the yoker process env (e.g. `ANTHROPIC_API_KEY`) are readable by Makefile recipes via `printenv`/`env`/`$$VAR`. Load secrets from a secrets store, not env, when running untrusted agents." ~3 lines of prose.
5. **Fix `DEVELOPMENT.md` denylist prose**: `PYTHON*` and `NODE_*` are exact-match, not prefix — either add prefixes or correct the prose. Doc-only.
6. **Optional**: add an end-to-end make-tool test for `LD_PRELOAD` or `YOKER_TRUST_SOURCE` via `env_vars` to complement the unit-level guardrail tests.

None of these block merge. They are additive hardening and documentation accuracy items suitable for a follow-up PR or backlog ticket.

---

## Section 9 — Round 2 Scoped Re-run: Windows Env Guardrail Extension

**Reviewer:** security-engineer
**Date:** 2026-07-21
**Scope:** `src/yoker/tools/guardrails/env.py` — `_WIN_DENIED_EXTRA` frozenset (17 Windows-specific env vars) + case-insensitive matching on Windows in `is_denied_env_var`. Pre-computed uppercased frozensets at module load. POSIX path unchanged.

### 9.1 Case-insensitivity correctness on Windows

`is_denied_env_var` (`env.py:109-131`) flow for `sys.platform == "win32"`:

1. Exact match against `_DENIED_EXACT` (case-sensitive) — misses case variants.
2. `_DENIED_PREFIX_RE.match` (case-sensitive regex) — misses case variants.
3. Windows branch: `upper = name.upper()`; check `_DENIED_EXACT_UPPER`, `_WIN_DENIED_EXTRA_UPPER`, then `upper.startswith(_WIN_PREFIXES_UPPER)`.

| Input | Path | Result |
|-------|------|--------|
| `"Path"` | not in exact; regex miss; win32 branch: `"PATH" in _DENIED_EXACT_UPPER` | **True** ✅ |
| `"MakeFlags"` | win32 branch: `"MAKEFLAGS" in _DENIED_EXACT_UPPER` | **True** ✅ |
| `"Yoker_Trust_Source"` | regex miss (case-sensitive `YOKER_`); win32 branch: `"YOKER_TRUST_SOURCE".startswith(("YOKER_", ...))` | **True** ✅ |
| `"comspec"` | win32 branch: `"COMSPEC" in _WIN_DENIED_EXTRA_UPPER` | **True** ✅ |
| `"SystemRoot"` | exact miss (case-sensitive); win32 branch: `"SYSTEMROOT" in _WIN_DENIED_EXTRA_UPPER` | **True** ✅ |

Tests: `tests/test_tools/test_env_guardrail.py:191-216` (`TestIsDeniedEnvVarWindowsCaseSensitivity`, Windows-only). All five required cases covered.

### 9.2 POSIX case-sensitivity preserved

The Windows branch is gated by `if sys.platform == "win32":` (`env.py:123`). On POSIX the function returns after the two case-sensitive checks (exact + regex) and never uppercases.

| Input | POSIX result | Evidence |
|-------|--------------|----------|
| `"Path"` | **False** (case-sensitive; `Path` ≠ `PATH`) | `env.py:119` `name in _DENIED_EXACT` — `"Path"` not in set; regex miss; no upper branch |
| `"PATH"` | **True** | `env.py:119` — `"PATH" in _DENIED_EXACT` |

Tests: `tests/test_tools/test_env_guardrail.py:219-231` (`TestIsDeniedEnvVarPosixCaseSensitivity`, POSIX-only). Confirms `Path` is NOT denied on POSIX (regression guard against the Windows branch leaking).

### 9.3 Windows denylist completeness

The 17 entries in `_WIN_DENIED_EXTRA` cover every Windows-specific identity/path/config vector enumerated in the review criteria:

| Category | Entries | Status |
|----------|---------|--------|
| Home/identity | `USERPROFILE`, `USERNAME`, `USERDOMAIN`, `HOMEDRIVE`, `HOMEPATH` | ✅ |
| System paths | `SystemRoot`, `WINDIR`, `SYSTEMDRIVE` | ✅ |
| Shell | `COMSPEC`, `PATHEXT` | ✅ |
| Data/program paths | `APPDATA`, `LOCALAPPDATA`, `PROGRAMDATA`, `PROGRAMFILES`, `PROGRAMFILES(X86)` | ✅ |
| Temp | `TEMP`, `TMP` | ✅ |

**Candidate additions assessed:**

| Candidate | Risk | In scope for 1.0.0 minimal? |
|-----------|------|------------------------------|
| `PSModulePath` | PowerShell module search path — code injection if a recipe invokes `powershell` | **Defer.** The make tool's Windows platform gate (`make.py:101-105`) returns before any subprocess is spawned, so env_vars never reach a Windows subprocess via `make`. The guardrail is defense-in-depth for the validation path only. Reasonable additive for a follow-up alongside any future Windows-capable subprocess tool. |
| `DOTNET_ROOT` | .NET runtime redirect | **Defer.** Cross-platform (not Windows-specific); low relevance to make recipes. |
| `JAVA_HOME` / `CLASSPATH` | Java runtime/class redirect | **Defer.** Cross-platform; not Windows-specific. If added, belongs in `_DENIED_EXACT` (POSIX-relevant too), not `_WIN_DENIED_EXTRA`. |
| `LIB` / `INCLUDE` | MSVC lib/include path injection — could redirect compilation | **Defer.** Narrow (MSVC-only); same platform-gate reasoning as `PSModulePath`. |

**Assessment:** The 17-entry set is complete for the 1.0.0 minimal guardrail. The platform gate means no Windows subprocess is spawned, so the Windows denylist is pure defense-in-depth. `PSModulePath` is the most defensible additive (parallel to `PYTHONPATH`/`NODE_PATH`), but adding it is non-blocking and fits a follow-up with the Section 8 recommendations. No entries are **missing** in the blocking sense.

### 9.4 No bypass paths on Windows

**Unicode case-folding:** Python's `str.upper()` uses Unicode default case folding (not locale-aware), so `"i"` → `"I"` and `"İ"` (U+0130, Turkish dotted capital I) → `"İ"` (stays as-is). Windows env var names are ASCII by convention (Win32 environment blocks use UTF-16 but names are ASCII); Python's `os.environ` on Windows is case-insensitive and normalizes to uppercase. The Turkish-I edge case is not a real concern for env var names. **No bypass.**

**Prefix-regex gap:** `_DENIED_PREFIX_RE` (`env.py:73-75`) is case-sensitive, so a case variant like `yoker_foo` does NOT match the regex. The Windows branch closes this via `upper.startswith(_WIN_PREFIXES_UPPER)` (`env.py:129`), which uppercases both the name and the prefixes. **No gap.**

**Multiple-case dict keys:** If an agent supplies both `Path` and `PATH` in `env_vars`, `validate_env_vars` iterates the dict and calls `is_denied_env_var` on each name — both are denied. (On Windows, Python's `os.environ` would merge them anyway, but validation catches both before that point.) **No bypass.**

### 9.5 `validate_env_vars` integration

`env.py:154-170` iterates `env_vars.items()`; for each entry calls `is_denied_env_var(name)` at line 157. The Windows case-insensitive path is entirely encapsulated in `is_denied_env_var`, so `validate_env_vars` needs no platform branching — it flows through correctly. The per-target allowlist check (`name not in allowed_names`, line 155) runs BEFORE the denylist check, so a denied name that is also allowlisted is still rejected (denylist is a hard invariant that the operator cannot waive). **Confirmed.**

### 9.6 `make.py` platform gate

`make.py:101-105`:
```python
if sys.platform == "win32":
    return ToolResult(
      success=False,
      error="make tool requires POSIX process-group support; not available on Windows",
    )
```

This runs BEFORE target validation, cwd resolution, env_vars validation, and `Popen` creation. On Windows, no env vars reach a subprocess via the make tool. The env guardrail's Windows branch is therefore **defense-in-depth** for the validation path (exercised if a future tool spawns a Windows subprocess without a platform gate) and for consistency with the Windows env-var case-insensitivity model. The gate is the correct primary control: R4 (`os.killpg`/`SIGKILL`/`start_new_session`) is POSIX-only, and a Windows process-tree kill via Job Objects is explicitly out of scope for 1.0. **Confirmed correct.**

Test: `tests/test_tools/test_make_windows.py:30-38` (`TestWindowsPlatformGate.test_make_rejected_on_windows`, Windows-only) asserts `not result.success` and `"not available on Windows" in result.error`.

### 9.7 Round 2 Verdict

### **APPROVED**

| Verification point | Result |
|--------------------|--------|
| Case-insensitivity correctness on Windows (`Path`, `MakeFlags`, `Yoker_Trust_Source`) | ✅ Confirmed (code path + Windows-only tests) |
| POSIX case-sensitivity preserved (`Path` not denied, `PATH` denied) | ✅ Confirmed (POSIX-only regression tests) |
| Windows denylist completeness (17 entries) | ✅ Complete for 1.0.0 minimal guardrail; `PSModulePath` is a non-blocking additive for a follow-up |
| No bypass paths (Unicode edge cases, prefix-regex case gap, multi-case dict keys) | ✅ No bypass; Windows env var names are ASCII; win32 upper-branch closes the case-sensitive regex gap |
| `validate_env_vars` integration | ✅ Calls `is_denied_env_var` per entry; Windows path flows through correctly; denylist enforced after allowlist (hard invariant) |
| `make.py` platform gate | ✅ Returns before subprocess creation on Windows; env guardrail is defense-in-depth; tested |

**Non-blocking additive recommendation (backlog):** Add `PSModulePath` to `_WIN_DENIED_EXTRA` in a follow-up alongside the Section 8 recommendations — closes the PowerShell module-injection vector parallel to `PYTHONPATH`/`NODE_PATH`. ~1 line. Only relevant if a future Windows-capable subprocess tool is added, since `make` itself is platform-gated.

No blocking issues. The Windows env guardrail extension is correct, complete for 1.0.0, and properly tested on both platforms.
