# Security Analysis: `env_vars` Parameter Proposal

**Date:** 2026-07-21
**Status:** Final
**Scope:** Threat model and abuse-vector enumeration for the owner's proposed
`env_vars: dict[str, str] | None` per-tool-call parameter, plus assessment of a
per-tool env-var-name allowlist mitigation. Compares to the prior `args`-based
design. No code changes — recommendation only.
**Related:** `analysis/security-make-tool.md`, `analysis/api-make-tool.md`,
`src/yoker/plugins/security.py`, `src/yoker/config/__init__.py`,
`src/yoker/builtin/git.py`.

## 0. Owner's Proposal (quoted verbatim)

> Let's first discuss the arguments issue and find a proper solution. In
> `make test TEST=some_file.py` `TEST` is an env var. What if we add the
> possibility to set env vars for a tool call, so instead of `args` we add
> `env_vars`? If we combine this with the option to restrict in configuration
> per tool which env vars can be set, this might be a generic way to solve
> this, while still limiting tool use to controllable subsets.
>
> Think this idea through, trying to find ways to abuse this added `env_vars`
> argument.

Framing: `env_vars` is a generic per-tool-call capability (not `make`-specific).
Each tool declares (in config) an allowlist of env var names the agent may set.
The subprocess inherits the yoker process env **plus** the explicitly-set
`env_vars`.

## 1. Threat Model Summary

- **Attacker**: compromised/prompt-injected agent. Controls both env var
  **names** and **values** unless the framework constrains them.
- **Assets**: yoker process secrets (API keys in env), trust gates
  (`YOKER_TRUST_SOURCE`), subprocess execution context (PATH, LD_*, shell
  startup), network egress (HTTP_PROXY), filesystem reach (`HOME`, `GIT_DIR`),
  host resources (CPU via `-j`), secret-exfiltration channels.
- **Trust boundary crossed**: `env_vars` lets the agent **mutate the execution
  environment of a subprocess the operator authorised for a specific target**.
  Without `env_vars`, the agent controls only the target string (validated) and
  `cwd` (root-contained). With `env_vars`, the agent controls the entire
  process environment for that subprocess — a strictly larger surface.

## 2. Abuse Vector Enumeration

The agent controls **names + values**. Vectors are grouped by impact class.
For each: name, mechanism, impact, whether the proposed allowlist (names only,
default-deny) mitigates it.

### 2.1 Shared-library / interpreter injection (code execution in the subprocess)

| Var | Mechanism | Impact | Allowlist mitigates? |
|-----|-----------|--------|----------------------|
| `LD_PRELOAD` | Loads arbitrary `.so` into every dynamically-linked child | Arbitrary code exec in subprocess context | Yes — deny by default |
| `LD_LIBRARY_PATH` | Hijacks shared lib resolution; can substitute `libc` shim | Code exec / secret capture | Yes |
| `DYLD_INSERT_LIBRARIES`, `DYLD_LIBRARY_PATH` | macOS equivalent of `LD_PRELOAD` | Code exec on macOS hosts | Yes |
| `PYTHONPATH` | Prepends dirs to `sys.path`; `sitecustomize.py`/`.pth` injection runs at interpreter start | Code exec in any python child (pytest, ruff, uv) | Yes |
| `PYTHONSTARTUP` | Path to a file executed on interactive python start | Code exec if any recipe runs `python -i` | Yes |
| `PYTHONHOME` | Redirects python stdlib to attacker dir | Code exec / import confusion | Yes |
| `PERL5OPT`, `PERL5LIB` | `perl -M` flags / lib path injection | Code exec in perl children | Yes |
| `RUBYOPT` | Ruby interpreter flags (`-rrequire_file`) | Code exec in ruby children | Yes |
| `NODE_OPTIONS`, `NODE_PATH` | `--require` module injection into every `node` child | Code exec in node children | Yes |
| `BASH_ENV`, `ENV`, `ZDOTDIR` | Shell startup file injection for any non-interactive `bash`/`sh`/`zsh` a recipe spawns | Code exec in recipe shells | Yes |
| `BASH_FUNC_<name>%%` | Shell function export (CVE-2014-6271-era Shellshock vector; still parsed by older bash) | Code exec in recipe shells | Yes (wildcard needed) |

**Common thread**: these are all **names** an operator would never allowlist for
a `make`/`git`/`pytest` tool. A default-empty allowlist blocks all of them. The
risk materialises only if an operator wide-open-allowlists (`allowed_env_vars =
["*"]` or a glob). **Recommendation: forbid `*` and globs in the allowlist
schema; only literal names allowed.**

### 2.2 Framework-trust bypass (defeats yoker's own gates)

| Var | Mechanism | Impact | Allowlist mitigates? |
|-----|-----------|--------|----------------------|
| `YOKER_TRUST_SOURCE` | `check_source_allowed` (plugins/security.py:108) reads this and auto-trusts the source | **Bypasses the trust gate for `yoker run`** — untrusted source loads & executes | Yes — must be on a hard denylist, not merely absent from allowlist |
| `YOKER_ALLOW_CUSTOM_BASE_URL` | Trust flag for custom backend base URLs | Backend impersonation / API-key redirection | Yes |
| `YOKER_*` (any) | Any framework control var the operator set | Behavioural bypass, depends on var | Yes, but **yoker must hard-deny its own namespace regardless of allowlist** |

**Critical point**: the allowlist is a *permit* list. The owner's proposal as
stated does not mention a *deny* list. `YOKER_*` and a handful of others
(`LD_PRELOAD`, `PATH`, `BASH_ENV`, `DYLD_*`, `GIT_CONFIG_PARAMETERS`,
`MAKEFLAGS`) must be **denied even if an operator mistakenly allowlists them**.
A layered check (allowlist AND not on hard-denylist) is required. See §5.

### 2.3 Secret exfiltration & API-key redirection

| Var | Mechanism | Impact | Allowlist mitigates? |
|-----|-----------|--------|----------------------|
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_API_KEY` | Agent overwrites the key its own backend uses (if a child makes LLM calls) OR plants a key for exfil correlation | Backend credential substitution; lets a malicious recipe use the operator's quota against an attacker-chosen account | Yes — deny by default |
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` | Redirects all HTTP(S) egress through attacker host | **Exfiltration of any secret the recipe reads** (env, files, `git config`) via proxy logging | Yes |
| `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`, `NODE_EXTRA_CA_CERTS` | Substitutes the CA bundle, enabling MITM with an attacker CA | MITM of all TLS egress from the subprocess | Yes |
| `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*` | Inline git config injection (`http.proxy=...`, `url.*.insteadOf=...`, `credential.helper=...`) | Redirects git fetch/push, captures credentials via helper | Yes |
| `HOME`, `USER`, `LOGNAME`, `GIT_AUTHOR_NAME`, `GIT_COMMITTER_EMAIL` | Identity spoofing; `HOME` redirects `.gitconfig`, `.npmrc`, `.netrc`, `.ssh/` resolution | Credential file capture, repudiation, sandbox escape via `~/.ssh/config` | Yes |

**Note on `HTTP_PROXY`**: even a recipe that does nothing malicious can leak
secrets if the agent sets `HTTPS_PROXY` to an attacker host and the recipe
calls `curl $SECRET_URL`. The proxy sees the URL (which may embed tokens) and
the body. **This is the single most dangerous exfil channel `env_vars` opens**
because it requires no recipe modification and works on otherwise-benign
targets like `make test`. Default-deny allowlist blocks it; emphasise in docs.

### 2.4 Defeating existing argument-validation controls

The prior `args`-based design (and the `make` tool's `target` validation)
rejects a leading `-` to prevent flag injection. `env_vars` reopens this
without ever touching the `target`/`args` string:

| Var | Mechanism | Impact | Allowlist mitigates? |
|-----|-----------|--------|----------------------|
| `MAKEFLAGS`, `MFLAGS` | Injected into every `make` invocation as if passed on the command line. `MAKEFLAGS="--eval=pwn:\\n\\t rm -rf /"` injects a recipe **without touching `target`** | **Reopens the `--eval` bypass that rejecting leading-`-` on `target` was designed to close** | Yes — deny by default |
| `MAKEFLAGS="-j 1000"` | Unbounded parallelism | DoS / resource exhaustion | Yes |
| `POSIXLY_CORRECT`, `MAKELEVEL` | Alters parser behaviour | Parser quirks, edge-case bypasses | Yes |
| `COLUMNS`, `LINES`, `TERM` | Output-formatting bypass; can trick parsers that wrap output | Output-injection into downstream tool result parsing | Yes |

**This is the decisive argument against treating `env_vars` as safer than
`args`**: `MAKEFLAGS` is functionally equivalent to passing flags via `args`,
and `--eval` via `MAKEFLAGS` is the exact bypass the `target` leading-`-`
rejection exists to prevent. The allowlist must treat `MAKEFLAGS`/`MFLAGS` as
denied-by-default (they are on the hard-denylist in §5).

### 2.5 Path / cwd / GIT workspace redirection

| Var | Mechanism | Impact | Allowlist mitigates? |
|-----|-----------|--------|----------------------|
| `GIT_DIR`, `GIT_WORK_TREE` | Redirects git operations to an attacker-controlled `.git` (which can include hooks, `core.hooksPath`, malicious config) | Arbitrary code exec via git hooks; bypasses `cwd` PathGuardrail entirely | Yes |
| `GIT_PREFIX`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY` | Alters git internals | Index/object-file tampering, race conditions | Yes |
| `PWD` | Misleads tools that trust `$PWD` over `getcwd()` | Path confusion in scripts | Yes |
| `TMPDIR`, `TEMP`, `TMP` | Redirects temp file creation | Race / symlink attacks on temp files | Yes |

### 2.6 Data exfiltration via env-var values the agent constructs

The agent has the `read` tool. Workflow:

1. `read` a sensitive file (`~/.netrc`, `pyproject.toml` with a token,
   `.env`).
2. `make(target="check", env_vars={"BUILD_LOG": "<file contents>"})` — agent
   plants the secret into an *allowlisted* var name.
3. A recipe (or `--eval`-style flag if `MAKEFLAGS` is allowlisted) POSTs
   `$BUILD_LOG` to an attacker host. Even without `MAKEFLAGS`, a benign
   Makefile that logs `env` to a file the agent can later `read` and ship
   via `webfetch` is sufficient.

**Allowlist implication**: an allowlist of **names** does not constrain
**values**. Any allowlisted var becomes an exfil channel for any data the agent
can read. This is true even for a safe-looking name like `TEST` or `BUILD_ID`.
**Mitigation**: value validation — length cap (e.g. 4 KB per var, 32 KB total)
and content restriction (no newlines, no NUL, no control bytes below 0x20
except no restriction at all on printable ASCII/UTF-8). Length cap alone
blocks exfil of large files in a single call; an agent can still chunk, but
chunking is noisy and rate-limitable.

### 2.7 Secret leakage via allowlisted vars the agent sets to computed values

Symmetric to 2.6: the agent sets `env_vars={"BRANCH": "$(cat ~/.ssh/id_rsa |
base64)"}` — wait, no shell expansion happens in `env_vars` values (they're
passed verbatim to `subprocess.run(env=...)`). So the agent must **read** the
secret first, then set the value. Same as 2.6. Confirmed: no shell expansion
risk in `env_vars` values themselves — the value is a literal string.

**But**: if the agent sets a value that *looks* like a secret and a recipe
echoes it, the operator's secret lands in the tool result and thus in the
LLM's context / the session log / the event recorder. This is a **log
hygiene** issue, not new with `env_vars` (the agent can already `read` a
secret and the LLM sees it), but `env_vars` gives the agent a way to *inject*
a value into subprocess output the operator might not realise contains a
secret. Mitigation: same value cap; plus the existing recommendation that
secrets not live in env at all (see `security-make-tool.md` §3.7).

### 2.8 Locale / parser quirks

| Var | Mechanism | Impact | Allowlist mitigates? |
|-----|-----------|--------|----------------------|
| `LC_ALL`, `LANG`, `LC_CTYPE` | Locale switching; some locales change parser behaviour (`.`, `,` decimal, quoting) | Output-format confusion, edge-case parser bugs | Yes |
| `IFS` | Shell word-splitting separator in recipe shells | Recipe argument injection if a recipe relies on unquoted expansion | Yes |
| `PS1`, `PS2`, `PROMPT_COMMAND` | Shell prompt injection; `PROMPT_COMMAND` runs before each prompt in interactive bash | Code exec in interactive shells (rare in recipes) | Yes |

### 2.9 Resource exhaustion

| Var | Mechanism | Impact | Allowlist mitigates? |
|-----|-----------|--------|----------------------|
| `MAKEFLAGS="-j 1000"` | 1000 parallel jobs | Fork-bomb-style DoS | Yes (deny `MAKEFLAGS`) |
| `NODE_OPTIONS="--max-old-space-size=8192"` | Memory blow-up | OOM | Yes (deny `NODE_OPTIONS`) |
| `UV_*`, `PIP_*`, `CARGO_*`, `RUSTFLAGS` | Build-tool parallelism / index redirection | DoS, supply-chain redirect | Yes |

### 2.10 Compositional / second-order vectors

- **Env var set by a child persists in that child's children only** — yoker's
  own env is not mutated (subprocess inherits a merge). Good: limits blast
  radius to the one subprocess. Bad: any `make` target that invokes `yoker`
  recursively (rare but possible in dev envs) would re-enter with the poisoned
  env.
- **Allowlist bypass via prefix-collision**: if the allowlist check is
  `name.startswith("YOKER_")` rather than exact-match, the agent sets
  `YOKER_TRUST_SOURCE`. **Use exact-string match, never prefix/glob.**
- **Case sensitivity**: env vars on POSIX are case-sensitive; on Windows they
  are not. An allowlist of `["PATH"]` on Windows would also match `Path`. The
  hard-denylist must be checked case-insensitively on Windows for the
  security-sensitive names (`PATH`, `SystemRoot`, `PATHEXT`, `COMSPEC`).

## 3. Does the Allowlist Mitigate Each Vector?

**Yes, with three caveats, for every vector in §2:**

1. **Default must be empty (deny-by-default).** A curated "safe set" default
   is unsafe because no env var is universally safe across all tools
   (`MAKEFLAGS` is safe for a `pytest` tool but fatal for `make`; `PATH` is
   safe-ish for `git` but a hijack vector for anything that runs executables
   by relative name). Each tool starts with `allowed_env_vars = ()` and the
   operator opts in per name.

2. **A hard-denylist is required in addition to the allowlist.** Operators
   make mistakes; `YOKER_TRUST_SOURCE`, `LD_PRELOAD`, `DYLD_INSERT_LIBRARIES`,
   `BASH_ENV`, `ENV`, `PYTHONSTARTUP`, `MAKEFLAGS`, `MFLAGS`,
   `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_DIR`, `GIT_WORK_TREE`,
   `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `REQUESTS_CA_BUNDLE`,
   `SSL_CERT_FILE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`, `HOME`, `USER`,
   `LOGNAME`, `PATH`, `LD_LIBRARY_PATH`, `LD_PRELOAD`, `NODE_OPTIONS`,
   `PYTHONPATH`, `PYTHONHOME`, `PERL5OPT`, `RUBYOPT`, `IFS`, `PS1`,
   `PROMPT_COMMAND`, `BASH_FUNC_*` must be rejected **even if the operator
   allowlists them**. The framework's security invariants are not the
   operator's to waive via this config knob. (This is the one place this
   analysis adds a guard the owner's proposal did not name — earned because
   the proposal explicitly defers to "restrict in configuration per tool",
   which is a permit list with no deny list, and §2.2 shows permit-only is
   insufficient.)

3. **Value validation is required.** The allowlist constrains names only.
   Without a value cap, every allowlisted name is an exfil channel (§2.6).
   Required value rules:
   - `len(value) <= 4096` bytes per var (configurable ceiling, default 4 KB)
   - `sum(len(v)) <= 32768` bytes across all `env_vars` in one call
   - No NUL bytes (`\x00`) — breaks C-string env handling
   - No newlines (`\n`, `\r`) in values — prevents injection into tools that
     parse env output line-wise (e.g., `printenv` consumed by a parser)
   - Value must be valid UTF-8 (subprocess env on POSIX is bytes; we standardise
     on UTF-8 and reject invalid sequences)

**Does not require**: a content allowlist (e.g., "only alphanumeric values").
That would break legitimate uses like `TEST="tests/test_foo.py::test_bar"`.
Length + no-NUL + no-newline + UTF-8 is the right floor.

## 4. Comparison: `env_vars` + Allowlist vs `args: list[str]` + Leading-`-` Rejection

| Dimension | `args: list[str]` + reject leading `-` | `env_vars` + allowlist + denylist + value rules |
|-----------|----------------------------------------|------------------------------------------------|
| Flag injection into `make` | Closed (leading `-` rejected on every arg) | Closed **only if `MAKEFLAGS`/`MFLAGS` are on the hard-denylist**; if not, `MAKEFLAGS=--eval=...` reopens it (§2.4) |
| `--eval` recipe injection | Closed | Closed via `MAKEFLAGS` denylist entry — **fragile** (depends on the denylist being correct and complete) |
| Argument injection into `git` | Closed (each arg validated, `--upload-pack` etc. in `DANGEROUS_OPTIONS`) | N/A — `git` doesn't read flags from env the same way; but `GIT_CONFIG_PARAMETERS` is the env-equivalent and must be denied |
| Positional-args use cases (`make test TEST=file.py`) | Requires `args` to permit `TEST=file.py` — which is a *make variable override*, not an env var | `env_vars={"TEST": "file.py"}` matches the actual semantics (TEST *is* an env var in `make test TEST=...`) — **semantically cleaner** |
| Exfiltration channel | Limited (args appear in process listing; recipes can still `printenv` of inherited env) | **Strictly larger** — any allowlisted var is an exfil channel for data the agent has read (§2.6) |
| Secret redirection | Not opened (no env mutation) | Opened (`HTTP_PROXY`, `HTTPS_PROXY`, `*_API_KEY`) — closed by denylist |
| Trust-gate bypass | Not opened | Opened (`YOKER_TRUST_SOURCE`) — closed by denylist |
| Shared-library injection | Not opened | Opened (`LD_PRELOAD` etc.) — closed by denylist |
| Default safety | Safe by default (empty `args`, leading-`-` rejection) | Safe by default **only if allowlist defaults to empty AND hard-denylist is enforced regardless of allowlist** |
| Operator misconfiguration blast radius | Low (an operator allowlisting `--eval` in `args` is an obvious smell) | **High** (an operator adding `MAKEFLAGS` to a `make` tool's allowlist looks reasonable but reopens `--eval`) — the denylist is the safety net |
| Surface area | Small (one parameter, one validation) | Larger (names + values + allowlist + denylist + value rules + config schema) |

**Net assessment**: `env_vars` + allowlist is **not inherently safer** than
`args` + leading-`-` rejection. It is **more expressive** (handles the
`TEST=file.py` case correctly) but **opens a strictly larger attack surface**
(env mutation reaches subprocess context, interpreter startup, network
config, trust gates). It is safe to ship **only with the full mitigation
stack** (§5). Without the hard-denylist, it is **less safe** than `args`
because `MAKEFLAGS`-via-env silently reopens the exact bypass `args`'s
leading-`-` rejection was designed to close.

**Which vectors each opens/closes:**

- `args` opens: argument-injection if validation is incomplete; mitigated by
  leading-`-` + `FORBIDDEN_CHARS` (per `security-make-tool.md`).
- `args` closes: all of §2 (no env mutation at all).
- `env_vars` opens: all of §2.
- `env_vars` closes: nothing `args` doesn't also close. It is purely
  additive expressiveness, not additive safety.

## 5. Verdict

**The owner's `env_vars` proposal is sound *for the `make test TEST=...` use
case* — TEST is genuinely an env var, and `env_vars` models it correctly. It
is the semantically right tool.**

**It is safe to ship only with the full mitigation stack:**

1. **Per-tool allowlist, default empty.** `ToolsConfig.<tool>.allowed_env_vars:
   tuple[str, ...] = ()`. Exact-string match only; no globs, no prefixes, no
   `*`. Case-insensitive match on Windows for the security-sensitive names.
2. **Framework hard-denylist, not configurable.** A frozenset in
   `src/yoker/tools/guardrails/env.py` (new, ~30 lines) checked *after* the
   allowlist and *before* the subprocess call. If `name in DENYLIST` (or
   matches `BASH_FUNC_%%` / `YOKER_*` / `LD_*` / `DYLD_*` patterns), reject
   with a `ToolResult(success=False, error=...)` — even if the operator
   allowlisted it. The operator cannot waive framework invariants via this
   knob.
3. **Value validation.** Per-var length cap (4 KB default), total cap (32 KB),
   no NUL, no newlines, valid UTF-8. Configurable ceiling via
   `ToolsConfig.<tool>.max_env_var_bytes`.
4. **Subprocess env construction.** `env = {**os.environ, **validated_env_vars}`
   — yoker's env is the base; agent-supplied vars override. Never replace
   `os.environ` wholesale (that breaks PATH/HOME/locale and breaks Makefiles).
5. **Audit log.** Every `env_vars` call is logged at INFO with
   `tool=<name>, target=<target>, env_vars=<keys>` (names only, not values, to
   avoid leaking secrets into logs if an agent sets a secret value). Matches
   the existing structured-logging pattern.
6. **Docs.** The tool's security-model section must call out: env vars are an
   exfil channel; the allowlist is a permit list, the denylist is enforced;
   secrets should not be in the yoker process env at all when running
   untrusted agents (carries forward `security-make-tool.md` §3.7).

**Hybrid option (recommended for the `make` tool specifically):** ship
`env_vars` *for the variable-override use case* (`TEST=file.py`, `BUILD=release`)
and **do not** add a separate `args` parameter. Rationale: `make`'s
variable-override use case is genuinely env-var-shaped; positional `args`
would duplicate what `env_vars` already covers and reopen the `--eval`-via-argv
vector that `target`'s leading-`-` rejection closes. The `make` tool's
`target` validation stays as-is (leading-`-` rejected, `FORBIDDEN_CHARS`
enforced). `env_vars` is the *only* way the agent passes variable overrides.
**This hybrid is strictly safer than `args` + `env_vars` together** (smaller
surface) and strictly more correct than `args` alone (TEST is an env var, not
a positional arg).

**Not recommended**: a global `allowed_env_vars` at the `ToolsConfig` level
(not per-tool). `MAKEFLAGS` is safe for `pytest` (ignored) and fatal for
`make`; per-tool is the minimum granularity that's safe.

## 6. Config Schema Sketch

Two-part: a per-tool field on each `*ToolConfig`, and a shared hard-denylist
module. Reuses the existing `ToolConfig` base and the
`GitToolConfig.allowed_commands: tuple[str, ...]` pattern verbatim.

### 6.1 Per-tool allowlist (add to each subprocess-spawning ToolConfig)

```python
# src/yoker/config/__init__.py

@dataclass
class MakeToolConfig(ToolConfig):
  timeout_ms: int = 300000
  max_output_kb: int = 100
  # Env vars the agent is allowed to set on a `make` call. Default empty
  # (deny-by-default). Exact-string match; no globs. The framework
  # hard-denylist (tools/guardrails/env.py) is enforced regardless of this
  # list — an operator adding "MAKEFLAGS" here will NOT enable it.
  allowed_env_vars: tuple[str, ...] = ()
  # Per-var value length cap in bytes. Default 4 KB; large enough for a test
  # path list, small enough to block exfil of a whole file in one call.
  max_env_var_bytes: int = 4096

  def __post_init__(self) -> None:
    validate_positive_int(self.timeout_ms, "tools.make.timeout_ms")
    validate_positive_int(self.max_output_kb, "tools.make.max_output_kb")
    validate_positive_int(self.max_env_var_bytes, "tools.make.max_env_var_bytes")
    # Reject globs / wildcards in the allowlist — exact names only.
    for name in self.allowed_env_vars:
      if any(ch in name for ch in "*?[") or name == "":
        raise ValidationError(
          "tools.make.allowed_env_vars",
          name,
          "must be a literal env var name (no globs, no empty)",
        )
```

Same field added to `GitToolConfig`, `WebFetchToolConfig`,
`WebSearchToolConfig` — any tool that spawns a subprocess or makes an
out-of-process call influenced by env. Not added to pure-Python tools
(`read`, `write`, `list`, `search`, `existence`, `mkdir`, `update`) — they
don't spawn subprocesses and don't accept `env_vars`.

### 6.2 Framework hard-denylist (new, ~30 lines, not configurable)

```python
# src/yoker/tools/guardrails/env.py

import re
from typing import Mapping

# Env var names the framework refuses to let an agent set, regardless of
# the operator's per-tool allowlist. These bypass framework trust gates,
# enable code injection in subprocesses, or redirect network/credentials.
_DENIED_EXACT: frozenset[str] = frozenset({
  # Framework trust gates
  "YOKER_TRUST_SOURCE", "YOKER_ALLOW_CUSTOM_BASE_URL",
  # Shared-library / interpreter injection
  "LD_PRELOAD", "LD_LIBRARY_PATH",
  "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
  "PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME",
  "PERL5OPT", "PERL5LIB", "RUBYOPT",
  "NODE_OPTIONS", "NODE_PATH",
  "BASH_ENV", "ENV", "ZDOTDIR", "PROMPT_COMMAND", "IFS",
  # Shell-flag / make-flag injection (reopens --eval)
  "MAKEFLAGS", "MFLAGS",
  # Git config / workspace redirect
  "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
  "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
  "GIT_SSL_CAINFO",
  # Network / credential redirect
  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
  "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE",
  "NODE_EXTRA_CA_CERTS",
  # Identity / sandbox escape
  "HOME", "USER", "LOGNAME",
  # API-key substitution
  "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
  "OLLAMA_API_KEY", "GITHUB_TOKEN",
})

# Pattern-based denials: checked with re.fullmatch on the upper-cased name.
_DENIED_PATTERNS: tuple[re.Pattern[str], ...] = (
  re.compile(r"YOKER_.*"),
  re.compile(r"LD_.*"),
  re.compile(r"DYLD_.*"),
  # Shellshock-style function exports: BASH_FUNC_foo%%
  re.compile(r"BASH_FUNC_.*%%"),
  re.compile(r"GIT_CONFIG_KEY_\d+"),
  re.compile(r"GIT_CONFIG_VALUE_\d+"),
)

# Also denied on Windows (case-insensitive match there). POSIX is exact.
_WIN_DENIED_EXTRA: frozenset[str] = frozenset({
  "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "WINDIR",
})


def is_denied(name: str, *, case_sensitive: bool = True) -> bool:
  """True if `name` is on the framework hard-denylist."""
  if name in _DENIED_EXACT:
    return True
  upper = name if case_sensitive else name.upper()
  if not case_sensitive and upper in _WIN_DENIED_EXTRA:
    return True
  return any(p.fullmatch(upper) for p in _DENIED_PATTERNS)


def validate_env_vars(
  tool_name: str,
  env_vars: Mapping[str, str] | None,
  allowed: tuple[str, ...],
  max_var_bytes: int,
) -> tuple[dict[str, str], list[str]]:
  """Validate agent-supplied env_vars against allowlist + denylist + value rules.

  Returns (validated_env_dict, rejection_reasons). On any rejection the
  caller MUST return ToolResult(success=False, error=...) without spawning.
  """
  if not env_vars:
    return {}, []
  reasons: list[str] = []
  accepted: dict[str, str] = {}
  total = 0
  case_sensitive = True  # POSIX; flip for Windows in the tool body
  for name, value in env_vars.items():
    if not isinstance(name, str) or not isinstance(value, str):
      reasons.append(f"{name!r}: name and value must be strings")
      continue
    if name not in allowed:
      reasons.append(f"{name!r}: not in tools.{tool_name}.allowed_env_vars")
      continue
    if is_denied(name, case_sensitive=case_sensitive):
      reasons.append(f"{name!r}: on framework hard-denylist")
      continue
    if "\x00" in value:
      reasons.append(f"{name!r}: NUL byte in value")
      continue
    if "\n" in value or "\r" in value:
      reasons.append(f"{name!r}: newline in value")
      continue
    vbytes = value.encode("utf-8")
    if len(vbytes) > max_var_bytes:
      reasons.append(f"{name!r}: value exceeds {max_var_bytes} bytes")
      continue
    total += len(vbytes)
    if total > 32768:
      reasons.append(f"{name!r}: total env_vars exceeds 32 KB")
      continue
    accepted[name] = value
  return accepted, reasons
```

### 6.3 Wiring in the tool body (one call, no new abstraction)

```python
# src/yoker/builtin/make.py (sketch — NOT for implementation per scope)

allowed = ctx.config.tools.make.allowed_env_vars
validated, reasons = validate_env_vars(
  "make", env_vars, allowed, ctx.config.tools.make.max_env_var_bytes,
)
if reasons:
  return ToolResult(success=False, error="; ".join(reasons))

env = {**os.environ, **validated}
proc = subprocess.run(["make", target], cwd=cwd, env=env, ...)
```

Three lines plus the import. No new class, no wrapper, no indirection beyond
the one `validate_env_vars` function (which is earned: it encodes the
denylist + value rules the owner's permit-list-only proposal lacks, and is
reused by every subprocess-spawning tool).

### 6.4 Config TOML example

```toml
[tools.make]
timeout_ms = 300000
max_output_kb = 100
allowed_env_vars = ["TEST", "BUILD", "VARIANT"]
max_env_var_bytes = 4096
```

An operator adding `MAKEFLAGS` here gets a runtime `ToolResult(success=False,
error="'MAKEFLAGS': on framework hard-denylist")` — the denylist is enforced
regardless of the allowlist. This is the safety net that makes the proposal
shippable.

## 7. Summary

- The owner's `env_vars` proposal is **semantically correct** for the
  `make test TEST=...` use case (TEST is an env var, not a positional arg).
- It opens a **strictly larger attack surface** than `args`: §2 enumerates
  ~40 abuse vectors across interpreter injection, trust-gate bypass, secret
  redirection, exfil, flag injection via `MAKEFLAGS`, and git workspace
  redirect.
- A **permit-list-only** mitigation (the owner's "restrict in configuration
  per tool") is **insufficient** — operator misconfiguration is likely
  (`MAKEFLAGS` looks reasonable) and reopens the `--eval` bypass that the
  `make` tool's `target` validation was designed to close.
- The **full mitigation stack** (per-tool allowlist default-empty + framework
  hard-denylist not configurable + value validation + audit log) makes it safe
  to ship. The denylist is the one added guard this analysis recommends over
  the owner's permit-only framing — earned by §2.2 and §2.4.
- **Recommended hybrid**: ship `env_vars` for variable overrides; do **not**
  add `args` to `make`. `target` validation (leading-`-` rejection,
  `FORBIDDEN_CHARS`) stays as-is. `env_vars` is the sole variable-override
  path.
- **Not recommended**: global (non-per-tool) allowlist; `args` + `env_vars`
  together (duplicates surface); any default allowlist that is non-empty.