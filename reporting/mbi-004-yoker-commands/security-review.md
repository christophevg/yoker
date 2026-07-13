# Security Review Report: MBI-004 yoker Commands (Stage b)

**Date**: 2026-07-13
**Reviewer**: Security Engineer Agent
**Branch**: `feature/mbi-004-yoker-commands`
**Prior requirements**: `analysis/security-mbi-004-yoker-commands.md`
**Functional review**: `reporting/mbi-004-yoker-commands/functional-review.md` (Stage a — passed)

## Executive Summary

All security acceptance criteria from the prior security review are
implemented and verified against the source code. The two-phase
resolve/load design (C1, C2, M3) is correctly enforced: `resolve_source()`
returns metadata only with no imports, and `load_source()` is called only
after `check_source_allowed()` returns True in both `yoker run` and
`yoker loop`. GitHub SSRF protection, zip-bomb defenses, container
hardening, folder path-traversal validation, loop resource limits, and
init/config hardening are all present with test coverage. One residual
risk (H2 tool allowlist) was a recommendation not captured in the
acceptance criteria and remains unimplemented; it is noted below as a
non-blocking backlog item.

## Verdict: approved

## Requirements Verification

### C1: Trust gate — PASS

**Files**: `src/yoker/cli/run.py`, `src/yoker/cli/loop.py`,
`src/yoker/plugins/security.py`

- `check_source_allowed()` is called in `run.py` (line 89) and `loop.py`
  (line 88) BEFORE `load_source()` (run.py line 94, loop.py line 94).
- The trust gate fires on the user's config, NOT the manifest-overridden
  config — `check_source_allowed(resolved.trust_key, config, resolved)` is
  called before `_apply_config_overrides()` (run.py line 100, loop.py line
  100). A source cannot influence its own trust decision.
- Decision cascade in `check_source_allowed()` (security.py lines 227-249):
  1. Pre-trusted via `[plugins.trusted]` or `_session_trusted` set.
  2. `YOKER_TRUST_SOURCE=1` env var override (non-interactive opt-in).
  3. Non-interactive (`not sys.stdin.isatty()`) -> reject with styled hint.
  4. Interactive confirmation dialog via `_confirm_source()`.
- Non-interactive rejection is explicit (security.py line 239-242):
  `_print_source_untrusted_noninteractive()` + return False.
- `YOKER_TRUST_SOURCE=1` adds the trust key to `_session_trusted` and
  returns True (security.py lines 233-236).
- Interactive confirmation dialog (`_confirm_source`, security.py lines
  273-333) shows: source type (`kind`), origin (`source_string`), trust key,
  agent, tools_module, and full prompt — matching the H2 remediation
  requirement for an informed trust decision.

**Tests**: `test_run.py` covers trusted/untrusted rejection, env override,
session trust, non-interactive rejection, and dry-run-before-trust.

### C2: tools_module as code (two-phase) — PASS

**Files**: `src/yoker/cli/sources.py`, `src/yoker/plugins/file_manifest.py`

- `resolve_source()` (phase 1) does NOT import `tools_module`:
  - `_resolve_module()`: records trust key only, no import (line 184-197).
  - `_resolve_folder()`: calls `load_file_manifest()` (TOML parse only) and
    `_validate_folder_subpaths()`. No import (line 203-229).
  - `_resolve_github()`: clones + `load_file_manifest()` + validates
    subpaths. No import (line 280-318).
  - `_resolve_zip()`: extracts + `load_file_manifest()` + validates
    subpaths. No import (line 401-441).
- `load_source()` (phase 2) performs the imports:
  - `_load_module_source()`: `load_plugin()` + `importlib.import_module()`
    (line 573-607).
  - `_load_folder_source()`: `_import_tools_module()` which calls
    `importlib.import_module()` (line 610-695).
- `file_manifest.py` explicitly documents (line 33-36): "does NOT import
  `tools_module` or execute any code — the `tools_module` import happens in
  the loader AFTER the trust gate."
- `load_source()` is called only after `check_source_allowed()` in both
  run.py and loop.py.

**Tests**: `test_sources.py` — `test_resolve_folder_does_not_import_tools_module`,
`test_resolve_module_does_not_import_package`, `test_tools_module_imported_in_phase2`.

### C3: GitHub URL security — PASS

**Files**: `src/yoker/cli/sources.py`, `src/yoker/tools/web/guardrail.py`

- HTTPS only: `_validate_github_url()` rejects non-https schemes with an
  explicit message naming `git://`, `ssh://`, `file://` (lines 321-338).
- Reject embedded credentials: `parsed.username or parsed.password` check
  (line 332-336).
- SSRF check before clone: `_check_ssrf(host)` calls
  `UrlWebGuardrail._check_ssrf_for_host(host)` which checks localhost,
  private CIDRs, cloud metadata IPs, and domain DNS resolution (guardrail.py
  lines 552-583). Called at line 290 before `_git_clone()` at line 295.
- SHA recording: `_git_clone()` returns `_read_commit_sha()` (short SHA via
  `git rev-parse --short HEAD`), embedded in trust key as
  `github:owner/repo@sha` (line 301).
- No auto-pip install: `_resolve_github()` and `_load_folder_source()` contain
  no `pip install` calls.
- Temp dir with 0o700: `_make_secure_tempdir()` creates
  `tempfile.TemporaryDirectory` then `Path(tmpdir.name).chmod(0o700)` (lines
  540-544). Used by both github and zip paths.

**Tests**: `test_sources.py` — `test_rejects_non_https`, `test_rejects_ssh_scheme`,
`test_rejects_file_scheme`, `test_rejects_embedded_credentials`,
`test_rejects_ssrf_private_ip`, `test_rejects_ssrf_metadata_ip`,
`test_rejects_ssrf_localhost`, `test_successful_clone`.

### H1: Zip safety — PASS

**File**: `src/yoker/cli/sources.py`

- Reject symlinks: `_assert_safe_zip_entry()` checks `S_IFLNK` in
  `external_attr >> 16` (lines 528-534).
- Reject absolute paths: `Path(name).is_absolute()` (line 517-521).
- Reject `..` entries: `".." in Path(name).parts` (line 523-527).
- Max total uncompressed size: `_MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 *
  1024` (100 MB), checked cumulatively (lines 493-501).
- Max entries: `_MAX_ZIP_ENTRIES = 10_000` (line 465-471).
- Max compression ratio: `_MAX_ZIP_COMPRESSION_RATIO = 100`, checked
  per-entry as `uncompressed / compress_size` (lines 484-492).
- `is_safe_path` per entry: `(extract_root / name).resolve()` checked via
  `is_safe_path(extract_root, target)` (lines 503-508).
- Extract to 0o700 temp dir via `_make_secure_tempdir()`.

**Tests**: `test_sources.py` — `test_path_traversal_dotdot_rejected`,
`test_absolute_path_entry_rejected`, `test_symlink_entry_rejected`,
`test_too_many_entries_rejected`, `test_zip_bomb_high_ratio_rejected`,
`test_valid_zip_extracts_and_reads_manifest`.

### H2: Auto-run tool restriction — PASS (core), NOTE (tool allowlist)

**File**: `src/yoker/cli/run.py`, `src/yoker/cli/loop.py`

- Prompt length capped at 10 KB: `MAX_PROMPT_BYTES = 10 * 1024`,
  enforced in both run.py (lines 130-137) and loop.py (lines 129-137).
- `--dry-run` flag: `RunConfig.dry_run` field; `run.py` prints resolved
  info via `_print_dry_run()` and exits before the trust gate and
  `load_source()` (lines 81-84). No code execution in dry-run.
- Tool allowlist: NOT implemented. The confirmation dialog shows
  `tools_module` but there is no manifest `tools` allowlist field, no
  `--allow-tools` CLI flag, and webfetch/websearch are not blocked unless
  explicitly declared. This was a recommendation in the security review
  (H2 remediation) but was NOT included in the acceptance criteria (4.7.1
  covers trust gate, dry-run, prompt cap only). The agent retains
  autonomous access to all built-in tools for auto-run sources. See
  "Residual Risk" below.

**Tests**: `test_run.py` — prompt cap tests, dry-run tests, confirmation
tests.

### H3: Container security — PASS

**File**: `src/yoker/cli/container.py`

- Dockerfile JSON-array form exclusively: all `RUN` and `ENTRYPOINT`
  instructions use `["...", "..."]` form (lines 178, 196, 214-228,
  234-235). No shell-form `RUN`.
- Non-root USER directive: `USER 1000` (line 186).
- No API keys copied into image: explicit comment "Do NOT bake API keys
  into the image" (lines 190-192). Config mounted at runtime via volume
  (compose line 284-285).
- `.dockerignore`/`.containerignore` generated: `_build_ignore_file()`
  excludes `.git`, `__pycache__`, `.env`, `.yoker.toml`, `.ssh`,
  `credentials`, `*.pem`, `*.key`, `.venv`, etc. (lines 43-60, 269-271).
- Yoker version pinned: `pip install yoker=={yoker_version}` (line 178),
  read from `yoker.__version__`.
- GitHub source SHA pinned: `git checkout {sha}` using SHA extracted from
  trust key (lines 221-228), validated as hex 7-40 chars (lines 251-259).
- Source string validated against shell metacharacters:
  `_validate_source_string()` rejects `;&|`$()<>{}...!*#~` (lines 40,
  123-129), called before `resolve_source()` (line 80).

**Tests**: `test_container.py` — JSON-array form, USER 1000, ignore file
content, SHA extraction, metachar rejection, compose generation.

### H4: Folder path traversal — PASS

**File**: `src/yoker/cli/sources.py`

- `skills_dir`/`agents_dir` validated via `_assert_contained()` which
  checks: not absolute, no `..` in parts, and `is_safe_path(folder, target)`
  (lines 257-274).
- `tools_module` validated: rejects `/`, `\`, and `..` — must be a pure
  dotted module name (lines 243-254).
- Validation runs in phase 1 (`_resolve_folder`, `_resolve_github`,
  `_resolve_zip`) before any trust decision. When no `agent.toml` exists,
  defaults (`"skills"`, `"agents"`, `None`) are safe.

**Tests**: `test_sources.py` — `test_skills_dir_with_dotdot_rejected`,
`test_agents_dir_absolute_rejected`, `test_tools_module_with_slash_rejected`.

### M1: Loop resource limits — PASS

**File**: `src/yoker/cli/loop.py`, `src/yoker/cli/commands.py`

- Default `max_iterations` is finite: `LoopConfig.max_iterations = 100`
  (commands.py line 60).
- `--max-duration` supported: `LoopConfig.max_duration: int | None = None`
  (commands.py line 61), enforced in `_run_loop()` (loop.py lines 212-216).
- Stop after 3 consecutive failures: `MAX_CONSECUTIVE_FAILURES = 3`
  (loop.py line 57), checked at line 238-240.
- Exponential backoff: `_BACKOFF_BASE = 2`, `backoff = 2 ** failures`
  (loop.py lines 59, 243).
- Per-iteration timeout: `asyncio.wait_for(..., timeout=iteration_timeout)`
  reusing `config.tools.agent.timeout_seconds` (loop.py lines 145, 223-226).
- Trust gate fires ONCE, load_source ONCE (loop.py lines 88, 94) — no
  per-iteration re-trust needed since the source is loaded once.

**Tests**: `test_loop.py` — `test_loop_runs_n_iterations`,
`test_stops_after_three_failures`, `test_backoff_increases_with_failures`,
`test_max_duration_stops_loop`, `test_untrusted_source_aborts_without_load`.

### L1: init --path rejects forbidden prefixes — PASS

**File**: `src/yoker/cli/init.py`, `src/yoker/context/validator.py`

- `_resolve_path()` calls `validate_storage_path()` which checks
  `FORBIDDEN_PATH_PREFIXES` (`/etc`, `/usr`, `/sys`, `/proc`, `/root`,
  `/var/log`, `/var/db`, `/var/lib`, `/bin`, `/sbin`, `/lib`, plus macOS
  `/private/etc` etc.) (validator.py lines 18-50, 109-135).
- Written files have chmod 0600 (enforced by `write_config`).

**Tests**: `test_init.py` — `test_forbidden_path_prefix_rejected`,
`test_forbidden_path_usr_rejected`, `test_written_file_has_0600_permissions`.

### L2: --force requires confirmation — PASS

**File**: `src/yoker/cli/init.py`

- When `path.exists() and force and sys.stdin.isatty()`, `_confirm_overwrite()`
  is called (init.py lines 81-83, 106-108). Non-interactive `--force`
  overwrites without prompting (acceptable — explicit user flag).

**Tests**: `test_init.py` — `test_refuses_overwrite_without_force`,
`test_force_overwrites_existing_file`, `test_confirmation_message_printed`,
`test_yes_confirms`, `test_no_rejects`.

### L3: config masks API keys unless --reveal — PASS

**File**: `src/yoker/cli/config_cmd.py`

- `_mask_api_keys()` deep-copies config and masks all provider `api_key`
  fields via `_mask_value()` (shows `***...{last4}` or `***` for short keys)
  (lines 85-106).
- Called unless `config.reveal` is True (line 46).
- Covers ollama, openai, anthropic, gemini, generic providers
  (`_PROVIDER_CONFIGS`, line 28).
- Original config is not mutated (deep copy, line 92).

**Tests**: `test_config_cmd.py` — `test_ollama_api_key_masked`,
`test_openai_api_key_masked`, `test_none_api_key_stays_none`,
`test_original_config_not_mutated`, `test_api_key_masked_in_toml_output`,
`test_api_key_revealed_with_flag`.

## Residual Risk (Non-blocking)

### H2-backlog: Tool allowlist for auto-run sources

The security review's H2 remediation recommended a manifest `tools`
allowlist field, a CLI `--allow-tools` override, and blocking
webfetch/websearch unless explicitly declared and confirmed. These were NOT
included in the acceptance criteria (4.7.1) and are NOT implemented. An
auto-run source's agent retains autonomous access to all built-in tools
(read, write, git, webfetch, websearch). The trust confirmation dialog
shows `tools_module` and the full prompt, giving the user visibility into
what the source declares, but does not restrict the tool surface.

**Classification**: New (backlog item). The core acceptance criteria are
met (trust gate, dry-run, prompt cap). Recommend adding the tool allowlist
as a future hardening task if `yoker run` of untrusted sources becomes a
common workflow.

### H3-note: Metacharacter regex missing `"` and `\`

The `_SHELL_METACHARS` regex in `container.py` (line 40) does not include
`"` (double quote) or `\` (backslash), which are the dangerous characters
for JSON-array-form Dockerfile strings. A source string containing `"`
could break out of the JSON string in the generated Dockerfile. This is
low-risk because the source is user-supplied (self-inflicted, not
remote-attacker-controlled), and `resolve_source()` / `_validate_github_url()`
further constrain the URL form. Defense-in-depth would add `"` and `\` to
the regex.

**Classification**: New (low priority). Not blocking — the threat model
for H3 is attacker-controlled source strings, which require the user to
type them at the CLI.

## Scope Classification

| Finding | Classification | Action |
|---------|---------------|--------|
| C1 trust gate | Verified | None — implemented |
| C2 two-phase import | Verified | None — implemented |
| C3 GitHub SSRF/pinning | Verified | None — implemented |
| H1 zip safety | Verified | None — implemented |
| H2 prompt cap + dry-run | Verified | None — implemented |
| H2 tool allowlist | New | Backlog: future hardening |
| H3 container hardening | Verified | None — implemented |
| H3 metachar regex gap | New | Low: add `"` and `\` to regex |
| H4 folder traversal | Verified | None — implemented |
| M1 loop limits | Verified | None — implemented |
| L1 init path validation | Verified | None — implemented |
| L2 --force confirmation | Verified | None — implemented |
| L3 config key masking | Verified | None — implemented |

## Positive Observations

- The two-phase resolve/load split is a clean security invariant, enforced
  consistently across `run`, `loop`, `inspect`, and `container`. `inspect`
  and `container` use phase 1 only (no code execution), correctly avoiding
  the trust gate.
- The trust gate uses the user's config, not the manifest-overridden config,
  preventing a source from influencing its own trust decision.
- Zip-bomb defenses are layered: entry count, per-entry compression ratio,
  cumulative uncompressed size, symlink rejection, absolute path rejection,
  `..` rejection, and `is_safe_path` per entry.
- Container generation uses JSON-array form exclusively with a non-root
  user, secret-excluding `.dockerignore`, version pinning, and SHA pinning.
- Test coverage is comprehensive for all security requirements.
- Structured logging records trust decisions (`source_trusted`,
  `source_trusted_via_env`, `source_not_trusted_non_interactive`,
  `source_rejected_by_user`), partially addressing the M2 audit-log
  recommendation.