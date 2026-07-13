# MBI-004: Yoker Commands -- Implementation Summary

**Branch:** `feature/mbi-004-yoker-commands`
**PR:** https://github.com/christophevg/yoker/pull/46
**Date:** 2026-07-13
**Tests:** 1850 passing (make check green: format, lint, typecheck, test)

## Overview

MBI-004 transforms yoker from a single interactive command into a proper CLI
with seven subcommands. The flagship capability is `yoker run <source>`, which
creates "yoker-based agentic executable packages" -- sources (modules, GitHub
URLs, folders, zip files) containing an extended manifest (`agent.toml`) that
specifies which agent to use and injects an initial prompt.

## Task Groups Implemented (4.1 -- 4.12)

### 4.1 CLI Subcommands via Clevis

Registered seven subcommand config classes using Clevis's `@configclass(cmd=...)`
mechanism. Config-backed subcommands (`chat`, `run`, `loop`, `config`) extend
`Config`; standalone subcommands (`inspect`, `init`, `container`) have their own
fields. `LoopConfig` extends `RunConfig`. Backward compatibility: `yoker` with
no subcommand defaults to `yoker chat`.

**Files:** `src/yoker/cli/commands.py`, `src/yoker/cli/shared.py`,
`src/yoker/__main__.py`

### 4.2 `yoker chat`

Extracted the existing REPL behavior into `run_chat()`. Loads config, constructs
a Session, and runs the interactive REPL or batch mode. Bootstrap wizard
triggers on first run with no config (interactive only). All existing flags
(`--with`, `--ui-mode`, `--backend-*`, etc.) remain available.

**Files:** `src/yoker/cli/chat.py`

### 4.3 `yoker init`

Generates a default configuration file. Interactive mode runs the bootstrap
wizard; non-interactive mode (`--no-interactive`) writes a default `~/.yoker.toml`.
`--path` validates via `validate_storage_path` (rejects `/etc`, `/usr` prefixes).
Refuses overwrite without `--force`. Written files are `chmod 0600`.

**Files:** `src/yoker/cli/init.py`

### 4.4 `yoker config`

Displays current configuration as TOML or JSON. API keys masked
(`***...last4`) unless `--reveal`; `None` keys omitted from output.
Supports `--show-path` to display the config file location.

**Files:** `src/yoker/cli/config_cmd.py`

### 4.5 Manifest as Config-Override Layer

Extended `PluginManifest` with `agent` and `prompt` convenience fields (default
`None`, backward compatible). Implemented `agent.toml` file-based manifest parsing
in `file_manifest.py` -- parses TOML only, does NOT import `tools_module` (deferred
to loader after trust gate). Implemented the configuration cascade: base TOML
(user + project) -> manifest overrides -> CLI args, via
`get_yoker_config_with_manifest()`. Deep-merge applies nested table overrides;
TOML arrays replace tuple-typed fields.

**Files:** `src/yoker/plugins/file_manifest.py`, `src/yoker/plugins/manifest.py`,
`src/yoker/config/__init__.py`

### 4.6 Source Resolution (Two-Phase Resolve/Load)

Implemented the two-phase design: `resolve_source()` returns metadata only
(no imports, no code execution); `load_source()` performs imports and is called
ONLY after the trust gate passes. Four source types supported:

- **Module:** records trust key, no import in phase 1.
- **Folder:** validates subpaths via `is_safe_path`, rejects `..`/absolute paths,
  does NOT auto-install `pyproject.toml`.
- **GitHub URL:** HTTPS only (rejects `git://`, `ssh://`, `file://`); rejects
  embedded credentials; SSRF check via `UrlWebGuardrail`; `git clone --depth 1`;
  records short commit SHA; `0o700` temp dir; cleanup via `ResolvedSource.cleanup`.
- **Zip:** rejects symlink entries, absolute paths, `..` entries; enforces max
  10,000 entries, 100 MB uncompressed, 100:1 compression ratio; `0o700` temp dir.

**Files:** `src/yoker/cli/sources.py`, `src/yoker/plugins/security.py`

### 4.7 `yoker run`

The flagship command. Security invariant: `resolve_source` -> `--dry-run` ->
`check_source_allowed` (user's OWN config, no manifest) -> `load_source` ->
apply manifest config overrides (CLI still wins) -> resolve agent/prompt ->
prompt cap (10 KB) -> Session/Agent/process -> cleanup. `--agent`/`--prompt`
parsed via local argparse. `--dry-run` prints manifest + prompt without executing.
Source agent definitions override built-ins on conflict (owner-confirmed).

**Files:** `src/yoker/cli/run.py`

### 4.8 `yoker loop`

Resolves + loads source ONCE, then iterates. `--max-iterations` defaults to 100
(finite). `--max-duration` wall-clock timeout. Stops after 3 consecutive failures
with exponential backoff. Per-iteration timeout reuses `config.tools.agent.timeout_seconds`.
Ctrl+C handled gracefully via `asyncio.Event` + signal handler; prints summary.
`--persist`/`--session-id` reuse the same session across iterations.

**Files:** `src/yoker/cli/loop.py`

### 4.9 `yoker container`

Generates Dockerfile/Containerfile + `.dockerignore`/`.containerignore`
(+ optional `docker-compose.yml`). JSON-array form exclusively for
`RUN`/`ENTRYPOINT` (no shell-form injection risk). Source string validated
against shell metacharacters. Non-root `USER 1000` directive. No `~/.yoker.toml`
or API keys copied into the image. Yoker version pinned. GitHub sources pin to
resolved commit SHA. `--engine podman` -> Containerfile; `--output-dir` honored.

**Files:** `src/yoker/cli/container.py`

### 4.10 Tests

All planned test files created. Security invariants tested as invariants (e.g.,
`test_sources.py` patches `builtins.__import__` to fail the test if phase 1
imports `tools_module`). Coverage: 209 tests in the CLI/manifest scope.

**Files:** `tests/test_cli/test_dispatch.py`, `tests/test_cli/test_chat.py`,
`tests/test_cli/test_init.py`, `tests/test_cli/test_config_cmd.py`,
`tests/test_cli/test_sources.py`, `tests/test_cli/test_run.py`,
`tests/test_cli/test_loop.py`, `tests/test_cli/test_container.py`,
`tests/test_cli/test_inspect.py`, `tests/test_plugins/test_file_manifest.py`,
`tests/test_plugins/test_manifest.py`, `tests/test_config/test_config_with_manifest.py`

### 4.11 Documentation

`docs/cli.md` documents all seven subcommands with flags and examples.
`docs/guides/creating-agentic-packages.md` documents `agent.toml` format,
`[run]`/`[plugin]`/config-override sections, the configuration cascade, Python-based
manifest alternative, source types, trust model, and examples. `README.md` has a
"CLI Commands" section with a summary table. `CLAUDE.md` updated with `cli/`
module structure.

**Files:** `docs/cli.md`, `docs/guides/creating-agentic-packages.md`,
`README.md`, `CLAUDE.md`

### 4.12 `yoker inspect`

Read-only source report using phase-1 resolution only (metadata, no imports,
no code execution). No trust gate required. Report covers "what it contains"
(skills, agents, tools_module listed but NOT imported), "what it uses"
(dependencies from pyproject.toml, tools_module declaration), and "what it does"
(agent, prompt, config overrides). For module sources, the Python manifest cannot
be discovered without importing -- the report notes that trust is required
(honest limitation).

**Files:** `src/yoker/cli/inspect.py`

## Key Design Decisions

1. **Clevis commands (owner-directed):** Uses Clevis's built-in subcommand
   mechanism (`@configclass(cmd=...)`, `get_cmd()`) instead of a manual
   dispatcher. Each subcommand is a config class; Clevis auto-generates CLI args.
   Backward compatibility: `yoker` with no subcommand defaults to `yoker chat`.

2. **Manifest as generic config-override layer (owner-directed):** The manifest
   is not additive fields on `PluginManifest` -- it is a generic config-override
   layer. Layering: base TOML -> manifest overrides (`agent.toml`) -> CLI overrides.
   The manifest can override ANY Config field.

3. **File-based manifest named `agent.toml` (owner-directed):** Avoids collision
   with `yoker.toml` used for project-level configuration.

4. **Two-phase resolve/load:** `resolve_source()` returns metadata only (no
   imports, no code execution). `load_source()` performs imports and is called
   ONLY after `check_source_allowed()` returns True. This ensures the trust gate
   fires before any code runs.

5. **Trust gate reuses existing guardrails (owner-directed):** `yoker run <source>`
   goes through the same `check_plugin_allowed()` / `check_source_allowed()` gate
   as `--with <source>`. No bypass for named sources. No parallel trust tracks.

6. **Source agent overrides built-in (owner-confirmed):** Source-based named items
   override existing ones on conflict (given namespacing, rarely expected).

7. **`yoker inspect` -- read-only, no trust gate (owner-added):** Dumps a report
   about a source without importing `tools_module` or executing any code.

8. **No auto-install of `pyproject.toml` (clarified):** When loading a folder
   source with `pyproject.toml`, does NOT automatically `pip install` it
   (build hooks = arbitrary code execution, CWE-494). Deferred to a future MBI.

## Security Measures Implemented

- **Trust gate (C1):** `check_source_allowed()` called before `load_source()` in
  both `run` and `loop`. Uses the user's OWN config (not manifest-overridden) so
  a source cannot influence its own trust decision. Decision cascade: pre-trusted
  -> `YOKER_TRUST_SOURCE=1` env var -> non-interactive rejection -> interactive
  confirmation dialog showing source type, origin, trust key, agent, tools_module,
  and full prompt.

- **Two-phase resolve/load (C2):** `resolve_source()` does NOT import
  `tools_module`. `file_manifest.py` explicitly documents this. `load_source()`
  is called only after the trust gate passes.

- **SSRF protection (GitHub):** HTTPS only; rejects `git://`, `ssh://`, `file://`;
  rejects embedded credentials; SSRF check via `UrlWebGuardrail._check_ssrf_for_host`
  (private IPs, metadata IP 169.254.169.254, localhost).

- **Zip-bomb defenses:** Rejects symlink entries, absolute paths, `..` entries.
  Enforces max 10,000 entries, 100 MB uncompressed, 100:1 compression ratio.

- **Folder path-traversal validation:** `is_safe_path` validates `skills_dir`,
  `agents_dir`, `tools_module` subpaths; rejects `..` and absolute paths.

- **Container hardening (H3):** JSON-array form exclusively for `RUN`/`ENTRYPOINT`.
  Source string validated against shell metacharacters. `base_image` validated
  against whitespace/newlines (Dockerfile directive injection prevention, L3).
  Non-root `USER 1000` directive. No secrets copied into the image. Yoker version
  pinned. GitHub sources pin to resolved commit SHA.

- **Loop resource limits:** `--max-iterations` (default 100, finite). `--max-duration`
  wall-clock timeout. Stops after 3 consecutive failures with exponential backoff.

- **Init/config hardening:** `validate_storage_path` rejects `/etc`, `/usr`
  prefixes. `chmod 0600` on written config files. API keys masked (`***...last4`)
  unless `--reveal`. Overwrite refused without `--force`.

- **Prompt length cap (H2):** 10 KB maximum to prevent resource exhaustion.

## Review Round 1 Fixes Applied

The project review (functional, security, testing) passed with one round of
fixes applied in commit `aec3767`:

1. **Cascade ordering fix:** Changed from manually applying config overrides AFTER
   the trust gate (via a local `_apply_config_overrides` that mutated the config
   dataclass in-place) to properly reloading config with the manifest layer
   inserted between TOML and CLI (via `load_subcommand_config_with_manifest`).
   This ensures the correct cascade: dataclass defaults -> user TOML -> project
   TOML -> manifest overrides -> CLI args. CLI still wins over manifest.

2. **Container path fixes:** Fixed folder `COPY` to use the actual folder basename
   (`Path(source).name`) instead of hardcoded `"source/"`. Fixed zip `COPY` to use
   the actual zip filename instead of hardcoded `"source.zip"`. The build context
   has the user's file, not a hardcoded name.

3. **DRY consolidation:** Moved shared helpers from `run.py`, `loop.py`, and
   `container.py` into `shared.py`: `safe_cleanup`, `parse_run_overrides`,
   `register_source_agents`, `resolve_agent_and_prompt`, `MAX_PROMPT_BYTES`,
   `load_subcommand_config_with_manifest`. Eliminated duplicate `_safe_cleanup`
   implementations and `_register_source_agents` copies.

4. **Type safety:** Replaced `Any` type annotations with `ResolvedSource`
   throughout `container.py`, `inspect.py`, and `run.py`. Added `TextIO` type
   annotation for stdout in inspect. Removed unused `from typing import Any`
   imports.

5. **base_image validation (L3):** Added `_validate_base_image` to reject
   whitespace/newlines in `--base-image` to prevent Dockerfile directive injection
   after the `FROM` line.

## Files Modified/Created (Key Files)

### New Source Files

| File | Purpose |
|------|---------|
| `src/yoker/cli/__init__.py` | CLI package exports |
| `src/yoker/cli/commands.py` | Seven `@configclass(cmd=...)` subcommand configs |
| `src/yoker/cli/shared.py` | Shared helpers: config loading, cleanup, agent registration, manifest-aware config |
| `src/yoker/cli/chat.py` | `yoker chat` -- interactive REPL |
| `src/yoker/cli/run.py` | `yoker run <source>` -- flagship source execution |
| `src/yoker/cli/loop.py` | `yoker loop <source>` -- iterative execution |
| `src/yoker/cli/inspect.py` | `yoker inspect <source>` -- read-only source report |
| `src/yoker/cli/init.py` | `yoker init` -- config file generation |
| `src/yoker/cli/config_cmd.py` | `yoker config` -- config display |
| `src/yoker/cli/container.py` | `yoker container` -- Dockerfile/Containerfile generation |
| `src/yoker/cli/sources.py` | Two-phase source resolution (module, folder, github, zip) |
| `src/yoker/plugins/file_manifest.py` | `agent.toml` parsing (TOML only, no imports) |
| `src/yoker/plugins/security.py` | Trust gate: `check_source_allowed()` + decision cascade |

### Modified Source Files

| File | Change |
|------|--------|
| `src/yoker/__main__.py` | Clevis `get_cmd()` dispatch, `--with` stripping, bootstrap pre-flight for chat only |
| `src/yoker/config/__init__.py` | `get_yoker_config_with_manifest()` cascade implementation |
| `src/yoker/plugins/__init__.py` | Plugin exports for source loading |
| `src/yoker/plugins/manifest.py` | `agent`/`prompt` convenience fields added |
| `src/yoker/agents/registry.py` | `register()` method support for source agents |

### New Test Files

| File | Tests | Focus |
|------|-------|-------|
| `tests/test_cli/test_dispatch.py` | 21 | Dispatch routing, `--with` stripping, backward compat |
| `tests/test_cli/test_chat.py` | 2 | Module importability |
| `tests/test_cli/test_init.py` | 13 | Path validation, overwrite, masking |
| `tests/test_cli/test_config_cmd.py` | 13 | Masking, TOML/JSON output, `--reveal` |
| `tests/test_cli/test_sources.py` | 28 | All four source types, security, two-phase split |
| `tests/test_cli/test_run.py` | 28 | Trust gate ordering, dry-run, prompt cap, overrides |
| `tests/test_cli/test_loop.py` | 12 | Max-iterations, backoff, max-duration, cleanup |
| `tests/test_cli/test_container.py` | 34 | Shell metachar rejection, JSON-array, USER, SHA |
| `tests/test_cli/test_inspect.py` | 9 | Read-only invariant, no trust gate |
| `tests/test_plugins/test_file_manifest.py` | 17 | Manifest parsing, type validation, no-import |
| `tests/test_plugins/test_manifest.py` | 22 | Manifest field additions |
| `tests/test_config/test_config_with_manifest.py` | 9 | Override cascade, CLI precedence |

### Documentation Files

| File | Purpose |
|------|---------|
| `docs/cli.md` | CLI reference for all seven subcommands |
| `docs/guides/creating-agentic-packages.md` | Guide for creating agentic packages with `agent.toml` |
| `README.md` | Updated with CLI Commands section |
| `CLAUDE.md` | Updated with `cli/` module structure |
| `DEVELOPMENT.md` | Development documentation |

## Review Verdicts

- **Functional review:** approved -- all 12 task groups meet acceptance criteria.
- **Security review:** approved -- all security acceptance criteria implemented
  and verified. One residual risk (H2 tool allowlist) noted as non-blocking backlog.
- **Testing engineer review:** approved -- 209 tests in CLI/manifest scope, security
  invariants explicitly tested, two-phase design well-covered. Non-blocking
  recommendations for coverage gaps in `run.py` and `loop.py` internals.

## PR

https://github.com/christophevg/yoker/pull/46
