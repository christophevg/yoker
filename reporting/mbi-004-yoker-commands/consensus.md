# Consensus: MBI-004 yoker Commands — API Architect + Security Engineer

**Date**: 2026-07-08
**Participants**: API Architect Agent, Security Engineer Agent, Functional Analyst
**Documents reviewed:**
- `analysis/api-mbi-004-yoker-commands.md` (API Architect)
- `analysis/security-mbi-004-yoker-commands.md` (Security Engineer)
- `analysis/mbi-004-yoker-commands.md` (functional analysis, source of truth)

## Purpose

This document consolidates the findings of the two domain reviews, records
the design decisions both agree on, the security requirements that must be
incorporated into the implementation, and the open questions that require
owner resolution before implementation proceeds.

---

## 1. Key Design Decisions Agreed Upon

Both the API Architect and Security Engineer converge on the following
architectural decisions:

### 1.1 Manual dispatcher in front of Clevis

The CLI dispatcher is a lightweight manual layer that peels off the
subcommand and `--with` args, then delegates to Clevis for `Config`-derived
CLI args. `init` and `container` bypass Clevis entirely (they don't need a
`Config`). This preserves the existing annotation-driven CLI generation
pattern and avoids a rewrite of the config CLI surface.

### 1.2 `PluginManifest` extension is additive and backward compatible

Adding `agent: str | None = None` and `prompt: str | None = None` to
`PluginManifest` is a non-breaking change. All existing manifest call sites
remain valid. The run-config fields are carried in a separate
`ResolvedSource` dataclass, not overloading `PluginComponents`, preserving
the single-responsibility boundary.

### 1.3 File-based manifest deserializes into `PluginManifest`

`yoker.toml` deserializes into the same `PluginManifest` shape as the
Python `__YOKER_MANIFEST__`, so the run path has one type to consume
regardless of source type. The file manifest's `[run]` section is the
authoritative run configuration; the Python manifest's `agent`/`prompt`
fields are a convenience fallback for packages that want to be runnable
without a separate `yoker.toml`.

### 1.4 Source abstraction generalizes the loader

Rather than threading folder/zip special cases through `load_plugin`, both
reviews recommend a `Source` abstraction (`kind: Literal["package",
"folder"]`) with a `load_plugin_from_source()` entry point. This keeps the
trust gate (`check_plugin_allowed`) applied uniformly and avoids
duplicating skill/agent loading logic.

### 1.5 `ResolvedSource.cleanup` runs in a `finally` block

GitHub clones and zip extractions use `tempfile.TemporaryDirectory`. The
`run` subcommand calls `resolved.cleanup()` in a `finally` block. For
`loop`, the source is re-resolved each iteration (fresh clone) and cleanup
runs at the end of each iteration.

### 1.6 Reuse the Python API in `run`

The `run` subcommand should delegate to the same config/agent construction
path as `yoker.api.process` / `yoker.api.session` rather than
reimplementing Session+Agent wiring. This prevents the CLI and Python API
from diverging.

### 1.7 Existing security primitives are reusable

The security engineer confirmed that `UrlWebGuardrail` (SSRF protection),
`PathGuardrail` (symlink resolution + root containment), `is_safe_path`
(path containment), and `validate_base_url_trust` (interactive trust prompt
pattern) are all directly reusable for source resolution security. No new
security primitives are needed — the existing ones need to be wired into
the `yoker run` path.

---

## 2. Security Requirements That Must Be Incorporated

The following security findings from the Security Engineer must be
incorporated into the implementation. They have been added as security
acceptance criteria to the corresponding TODO.md tasks.

### 2.1 Critical: Trust gate must cover `yoker run` (C1 + M3)

**Requirement:** Every resolved source must pass
`check_plugin_allowed()` before any code runs (including `tools_module`
imports and `pip install`).

**Implementation impact:**
- `resolve_source()` must be split into two phases:
  - `resolve_source()` — returns metadata only (source type, trust key,
    manifest fields); no imports, no pip install
  - `load_source()` — performs imports, called only after
    `check_plugin_allowed()` returns True
- Non-interactive mode rejects untrusted sources by default
- Interactive mode shows a confirmation dialog (source type, origin,
  trust key, agent, full prompt, tools_module, tool allowlist)
- `--dry-run` flag resolves and prints manifest + prompt without executing

**TODO.md tasks affected:** 4.6.1, 4.7.1

### 2.2 Critical: `tools_module` is code, not config (C2)

**Requirement:** `yoker.toml`'s `tools_module` field triggers
`importlib.import_module()` of potentially attacker-supplied code. It must
be treated as code, not configuration.

**Implementation impact:**
- The functional analysis's claim that "`yoker.toml` is a configuration
  file, not code" (edge case #9, line 362-365 of the functional analysis)
  is **incorrect** and must be corrected. See section 4 below.
- `tools_module` imports must not happen before the trust gate fires
- Manifests without `tools_module` are config-only (lower trust tier)

**TODO.md tasks affected:** 4.6.1, 4.5.2

### 2.3 Critical: GitHub URL SSRF and supply-chain protection (C3)

**Requirement:** GitHub URL sources must be validated before cloning.

**Implementation impact:**
- URL must be HTTPS only; HTTP rejected
- Embedded credentials rejected
- SSRF check (`_check_ssrf_for_host`) runs before clone
- Resolved commit SHA recorded for audit
- No auto-`pip install` of the cloned repo
- Temp directory uses `0o700` permissions

**TODO.md tasks affected:** 4.6.3

### 2.4 High: Zip extraction safety (H1)

**Requirement:** Zip extraction must prevent path traversal, zip bombs, and
symlink escapes.

**Implementation impact:**
- Reject symlink entries, absolute paths, `..` entries
- Enforce max total uncompressed size (100 MB), max entries (10,000), max
  compression ratio (100:1)
- Use `is_safe_path()` for each entry

**TODO.md tasks affected:** 4.6.4

### 2.5 High: Auto-run prompt and autonomous tool restriction (H2)

**Requirement:** The auto-injected prompt runs with autonomous tool access
(read/write/git/webfetch). This must be restricted.

**Implementation impact:**
- Prompt length capped at 10 KB
- `--dry-run` shows the full prompt and tool allowlist before executing
- Manifest `tools` allowlist field (future enhancement)
- `--allow-tools` CLI override (future enhancement)

**TODO.md tasks affected:** 4.7.1

### 2.6 High: Container hardening (H3)

**Requirement:** Generated Dockerfiles must not introduce injection or
secret-leakage risks.

**Implementation impact:**
- JSON-array form exclusively for `RUN`/`ENTRYPOINT`
- Non-root `USER` directive
- No API keys or `~/.yoker.toml` copied into the image
- `.containerignore` generated
- Yoker version pinned

**TODO.md tasks affected:** 4.9.1

### 2.7 High: Folder source path traversal (H4)

**Requirement:** Manifest-specified directories (`skills_dir`, `agents_dir`)
must not escape the folder root.

**Implementation impact:**
- Resolve `folder/skills_dir` and `folder/agents_dir` and assert
  `is_safe_path(folder_root, resolved)` before loading
- Reject `..` and absolute paths

**TODO.md tasks affected:** 4.6.2

### 2.8 Medium: Loop resource limits (M1)

**Requirement:** `yoker loop` must not run indefinitely by default.

**Implementation impact:**
- Default `--max-iterations` to 100 (not unlimited)
- Add `--max-duration` flag
- Stop after 3 consecutive failures with backoff

**TODO.md tasks affected:** 4.8.1

### 2.9 Low: Init and config hardening (L1, L2, L3)

**Requirement:** `yoker init` and `yoker config` must not leak or overwrite
sensitive data.

**Implementation impact:**
- `yoker init --path` rejects forbidden path prefixes
- `yoker init --force` requires interactive confirmation
- `yoker config` masks `api_key` values unless `--reveal` is passed

**TODO.md tasks affected:** 4.3.1, 4.4.1

---

## 3. Open Questions from the API Architect

The API Architect raised three open questions that require owner
resolution before implementation of 4.5/4.6 proceeds:

### 3.1 Trust gate for `yoker run <source>`

**Question:** Should naming a source on the command line bypass
`config.plugins.enabled` (recommended — explicit opt-in), or should the
user also have to set `plugins.enabled = true`?

**Security Engineer position:** `yoker run` must NOT bypass the trust
gate. The source must pass `check_plugin_allowed()` regardless of whether
the user typed it on the command line. The "explicit opt-in" framing
underestimates the risk: a user who runs `yoker run
https://github.com/colleague/useful-tool` may not realize they are
executing arbitrary Python. The trust gate should fire for every source,
with interactive confirmation as the mechanism (not a blanket bypass).

**Consensus:** The two reviews **disagree** on this point. The API
Architect recommends bypassing `plugins.enabled` (the user opted in by
typing the source); the Security Engineer requires the trust gate to
fire unconditionally. **This needs owner resolution.** The security
engineer's position is the safer default: route through
`check_plugin_allowed()` with interactive confirmation, and allow
pre-trusting via `[plugins.trusted]` or an env-var override for
non-interactive use.

### 3.2 Agent name resolution scope

**Question:** Confirm that the manifest's `agent` name resolves against
the source's own agent definitions first, then the built-in registry, with
source winning on conflict.

**Security Engineer position:** Agreed. Source's own agent definitions
should take precedence. No security concern with this resolution order as
long as the source itself has passed the trust gate.

**Consensus:** Both reviews agree on the resolution order. No conflict.

### 3.3 File-manifest filename

**Question:** `yoker.toml` collides with the user/project config filename
(`./yoker.toml` is currently the project config). For a folder source,
`yoker run ./my-folder` looks for `./my-folder/yoker.toml` — no collision
because it's inside the source folder. But for a GitHub clone landing in
the current directory, there's potential confusion. Is `yoker.toml`
acceptable, or should it be `yoker-manifest.toml`?

**Security Engineer position:** No strong security preference. The path
scoping (`<source-root>/yoker.toml`) removes ambiguity. Recommends
`yoker.toml` for simplicity, with clear documentation that this is the
source manifest, not the user/project config.

**Consensus:** Both reviews lean toward `yoker.toml` inside the source
root. The API Architect recommends it with clear documentation. **Needs
owner confirmation.**

---

## 4. Conflicts and Tensions Between the Designs

### 4.1 "yoker.toml is a configuration file, not code" — INCORRECT

**The conflict:** The functional analysis (edge case #9, lines 362-365 of
`analysis/mbi-004-yoker-commands.md`) states:

> `yoker.toml` is trusted the same way `~/.yoker.toml` is trusted — it's
> a configuration file, not code. The `tools_module` field imports Python
> code, which is the same trust model as `--with <package>` (the user
> explicitly chose to load it).

**Security finding C2:** This framing is **incorrect and dangerous**.
`yoker.toml`'s `tools_module` field triggers `importlib.import_module()` of
attacker-supplied code. A file that can execute arbitrary Python at import
time is not "a configuration file" — it is a code execution vector. The
comparison to `--with <package>` is valid only if the same trust gate
(`check_plugin_allowed()`) is applied; today the design does not wire the
trust gate into the file-manifest path.

**Resolution:** The functional analysis must be corrected. The claim should
be replaced with:

> `yoker.toml` is a manifest file that can declare a `tools_module` field.
> When `tools_module` is specified, the manifest triggers
> `importlib.import_module()` of a Python module within the source — this
> is **code execution**, not pure configuration. It must pass the same
> trust gate as `--with <package>` (`check_plugin_allowed()`) before the
> import happens. Manifests without `tools_module` are config-only and
> represent a lower trust tier.

### 4.2 Trust gate bypass — explicit opt-in vs. mandatory gate

**The conflict:** The API Architect recommends that `yoker run <source>`
bypass `config.plugins.enabled` because the user explicitly opted in by
typing the source name (section 3.7.1 and section 4.4 of the API review).
The Security Engineer requires the trust gate to fire unconditionally
(finding C1).

**Resolution:** This is the most significant tension. The Security
Engineer's position is safer: `yoker run` naming a source is analogous to
`--with` naming a package — both should pass the trust gate. The
"explicit opt-in" argument underestimates the risk of social engineering
(convincing a user to run a source). **Owner decision required.** The
recommended compromise: `yoker run` does NOT require
`config.plugins.enabled = true` globally (the user shouldn't have to
enable plugins globally just to run one source), but it DOES require the
specific source to pass `check_plugin_allowed()` — either via
`[plugins.trusted]` entry, interactive confirmation, or env-var override.
This satisfies both positions: no global gate, but per-source trust.

### 4.3 Auto-install of `pyproject.toml` — defer vs. gate

**The conflict:** The functional analysis mentions optionally installing a
folder's `pyproject.toml` as a package. The API Architect recommends
deferring this (no auto-install in MBI-004). The Security Engineer goes
further: auto-install runs build hooks (CWE-494, finding M4) and must
never happen without an explicit `--install` flag gated by trust.

**Resolution:** Both reviews agree on deferral for MBI-004. The Security
Engineer's stronger position (explicit `--install` flag, never auto-install)
should be the documented policy. The functional analysis's "optionally
install it as a package (deferred)" language should be corrected to "do
NOT auto-install; require explicit `--install` flag, gated by the trust
gate. Deferred to a future MBI."

### 4.4 `yoker loop` default iterations — unlimited vs. finite

**The conflict:** The functional analysis specifies `--max-iterations`
default as "unlimited." The Security Engineer requires a finite default
(100) to prevent resource exhaustion (finding M1).

**Resolution:** The Security Engineer's position is safer. Default to 100
iterations. Users who need unlimited can pass `--max-iterations 0` (or a
very large number). This has been added as a security acceptance criterion
to task 4.8.1 in TODO.md.

---

## 5. Prioritized Implementation Order

Combining the API Architect's dependency graph with the Security Engineer's
prioritized fix order, the recommended implementation sequence is:

1. **4.5.1** — Add `agent`/`prompt` to `PluginManifest` (additive, no
   security risk)
2. **4.5.2** — File-based manifest loading (`yoker.toml` parsing, no
   imports yet)
3. **4.1** — CLI dispatcher (no security surface; infrastructure)
4. **4.6.1** — Source resolution framework with **two-phase
   resolve/load** (C1 + M3: trust gate before imports)
5. **4.6.2** — Folder path resolution with **path validation** (H4)
6. **4.6.3** — GitHub URL with **SSRF + HTTPS + SHA pinning** (C3)
7. **4.6.4** — Zip extraction with **bomb/traversal protection** (H1)
8. **4.7.1** — `yoker run` with **trust gate + dry-run + prompt cap** (C1,
   H2)
9. **4.8.1** — `yoker loop` with **finite default + backoff** (M1)
10. **4.9.1** — `yoker container` with **Dockerfile hardening** (H3)
11. **4.2, 4.3, 4.4** — `chat`, `init` (with path validation + force
    confirmation), `config` (with API key masking)
12. **4.10** — Tests (including security tests for all the above)
13. **4.11** — Documentation (including corrected trust model)

---

## 6. Summary

The two domain reviews are broadly complementary. The API Architect
provides the structural design (dispatcher, manifest, source abstraction,
loader generalization); the Security Engineer provides the protective
layer (trust gate, path validation, SSRF, zip safety, container
hardening). The primary tension is the trust gate question (bypass vs.
mandatory), which requires owner resolution. The functional analysis's
claim that `yoker.toml` is "a configuration file, not code" must be
corrected per finding C2. All security acceptance criteria have been added
to the corresponding TODO.md tasks.