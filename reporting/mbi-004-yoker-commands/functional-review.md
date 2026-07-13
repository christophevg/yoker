# Functional Review: MBI-004 — Yoker Commands

**Reviewer:** functional-analyst
**Date:** 2026-07-13
**Branch:** `feature/mbi-004-yoker-commands`
**Verdict:** approved

---

## Methodology

For each task group (4.1–4.12), I read the implementation against the acceptance
criteria and security acceptance criteria defined in `TODO.md`. I verified the
end-to-end user flow (CLI help, unknown-subcommand handling, `make check`) and
confirmed backward compatibility (no subcommand → `chat`).

Final verification:
- `make check` green: ruff format (261 files unchanged), ruff lint (all checks
  passed), mypy (no issues in 123 source files), pytest (**1843 passed**).
- `uv run python -m yoker --help` lists all seven subcommands with descriptions.
- `uv run python -m yoker run --help` lists Config-derived args + run-specific.
- `uv run python -m yoker inspect --help` lists only `--source`.
- `uv run python -m yoker bogus-cmd` exits with code 2 and prints the
  valid-choice list.
- Working tree clean (the snapshot in the task brief was stale).

---

## Task-by-task findings

### 4.1 CLI subcommands via Clevis — PASS

- `src/yoker/cli/commands.py` registers all seven subcommand config classes via
  `@configclass(cmd="...")`. Config-backed (`chat`, `run`, `loop`, `config`)
  extend `Config`; standalone (`inspect`, `init`, `container`) are minimal.
  `LoopConfig` extends `RunConfig` as specified.
- `src/yoker/cli/shared.py` provides `load_subcommand_config()` with the
  dev/test security bypass and an `abort()` helper.
- `src/yoker/__main__.py` uses `get_cmd()` for dispatch; `_needs_default_chat()`
  inserts `chat` when no subcommand is given (bare `yoker` or a flag-first
  invocation), preserves `--help`/`-h` top-level help, and lets argparse reject
  unknown positionals with the valid-choice list. `--with` stripping happens
  before dispatch. Bootstrap pre-flight runs for `chat` only.
- Acceptance criteria met: `yoker` with no args → chat; flags-first → chat;
  unknown subcommand → argparse error with choice list; `--with` from any
  position; `yoker run` does not trigger bootstrap; `init`/`inspect`/
  `container` skip base config loading.

### 4.2 `yoker chat` — PASS

- `src/yoker/cli/chat.py` extracts the REPL (bootstrap pre-flight, config load,
  Session construction, `_run_with_session`, `_run_repl`). `run_chat()` receives
  `plugin_packages` from `--with`. The existing REPL/UI tests in
  `tests/test_main.py` import from `yoker.cli.chat` and pass.

### 4.3 `yoker init` — PASS

- `src/yoker/cli/init.py` implements interactive (BootstrapWizard) and
  non-interactive (`write_config`) paths. `--path` validates via
  `validate_storage_path` (rejects `/etc`, `/usr` prefixes). Refuses overwrite
  without `--force`; requires interactive confirmation when overwriting on a
  TTY. Written files are `chmod 0600` (verified by `test_init.py`).

### 4.4 `yoker config` — PASS

- `src/yoker/cli/config_cmd.py` loads `ConfigCmdConfig`, projects to base
  `Config` for rendering (drops display flags), prints TOML or JSON, supports
  `--show-path`. API keys masked (`***...last4`) unless `--reveal`; `None` keys
  omitted from output. Tests in `test_config_cmd.py` cover all flags.

### 4.5 Manifest as config-override layer — PASS

- `PluginManifest` gained `agent` and `prompt` fields (default `None`).
- `file_manifest.py` parses `agent.toml` into `FileManifestResult` with
  `[run]`, `[plugin]`, and config overrides separated; only parses TOML, no
  imports. Rejects malformed TOML and wrong-typed sections with `PluginError`.
- `get_yoker_config_with_manifest()` implements the cascade
  (base TOML → manifest overrides → CLI) using Clevis internals with
  `TODO(clevis-feature-request)` markers. Deep-merge handles nested tables;
  arrays replace tuple-typed fields.
- Note: task 4.5.4 specified `ResolvedSource`/`Source` in `plugins/loader.py`.
  The implementation places them in `src/yoker/cli/sources.py` instead — a
  reasonable design choice (CLI-specific, not a generic plugin concern) that
  still satisfies the functional acceptance criteria (`load_plugin_from_source`
  equivalent is `load_source(resolved)`).

### 4.6 Source resolution — PASS

- `src/yoker/cli/sources.py` implements the two-phase design:
  `resolve_source()` (metadata only) + `load_source()` (imports, after trust).
- All four source types implemented: module, folder, GitHub URL, zip.
- **Folder:** validates `skills_dir`/`agents_dir`/`tools_module` via
  `is_safe_path` and rejects `..`/absolute paths; does NOT auto-install
  `pyproject.toml`.
- **GitHub:** HTTPS only (rejects `git://`, `ssh://`, `file://`); rejects
  embedded credentials; SSRF check via `UrlWebGuardrail._check_ssrf_for_host`
  (private IPs, metadata IP); `git clone --depth 1`; records short commit SHA;
  `0o700` temp dir; cleanup via `ResolvedSource.cleanup`.
- **Zip:** rejects symlink entries, absolute paths, `..` entries; enforces
  max 10,000 entries, 100 MB uncompressed, 100:1 compression ratio; `0o700`
  temp dir; `is_safe_path` per entry.
- Tests in `test_sources.py` cover detection, all four source types,
  traversal rejection, SSRF, zip-bomb defenses, two-phase split, and cleanup.

### 4.7 `yoker run` — PASS

- `src/yoker/cli/run.py` implements the flagship command with the security
  invariant: `resolve_source` → `--dry-run` → `check_source_allowed` →
  `load_source` → apply overrides → resolve agent/prompt → prompt cap →
  Session/Agent/process → cleanup.
- `--agent`/`--prompt` parsed via local argparse (not Config fields).
- Trust gate uses the user's config (not manifest-overridden) — a source
  cannot influence its own trust decision.
- `--dry-run` prints manifest + prompt without executing.
- Prompt length capped at 10 KB.
- `--persist`/`--session-id` control session persistence; without `--persist`
  the run is stateless (`persist_after_turn = False`).
- Source agent definitions override built-ins on conflict (owner-confirmed).
- Tests in `test_run.py` cover trust-gate ordering, dry-run, non-interactive
  rejection, env override, prompt cap, missing agent/prompt, CLI overrides,
  cleanup, and config-override application.

### 4.8 `yoker loop` — PASS

- `src/yoker/cli/loop.py` resolves + loads the source ONCE, then iterates.
- `--max-iterations` defaults to 100 (finite, not unlimited).
- `--max-duration` wall-clock timeout supported.
- Stops after 3 consecutive failures with exponential backoff.
- Per-iteration timeout reuses `config.tools.agent.timeout_seconds`.
- Prints iteration number + UTC timestamp before each run.
- Ctrl+C handled gracefully via `asyncio.Event` + signal handler; prints
  summary (completed iterations, elapsed, stop reason).
- `--persist`/`--session-id` reuse the same session across iterations.
- Tests in `test_loop.py` cover max-iterations, failure-stops, backoff,
  max-duration, interruptible sleep, and cleanup.

### 4.9 `yoker container` — PASS

- `src/yoker/cli/container.py` generates Dockerfile/Containerfile +
  `.dockerignore`/`.containerignore` (+ optional `docker-compose.yml`).
- JSON-array form exclusively for `RUN`/`ENTRYPOINT` (no shell-form
  injection risk). Source string validated against shell metacharacters
  (defense-in-depth).
- Non-root `USER 1000` directive.
- No `~/.yoker.toml` or API keys copied into the image (secret management
  documented as volume-mount comments).
- Yoker version pinned (`pip install yoker==<version>`).
- GitHub sources pin to the resolved commit SHA in the Dockerfile.
- `--engine podman` → Containerfile; `--output-dir` honored.
- Tests in `test_container.py` cover JSON-array form, version pin, non-root
  user, ignore-file contents, SHA extraction, source build steps, and all
  engines/outputs.

### 4.12 `yoker inspect` — PASS

- `src/yoker/cli/inspect.py` uses phase-1 resolution only (metadata, no
  imports, no code execution). No trust gate required (read-only).
- Report covers "what it contains" (skills, agents, tools_module listed
  but NOT imported), "what it uses" (dependencies from pyproject.toml,
  tools_module declaration), and "what it does" (agent, prompt, config
  overrides).
- For module sources, the Python manifest cannot be discovered without
  importing — the report notes that trust is required (honest limitation).
- Tests in `test_inspect.py` cover module/folder reports, no-trust-gate,
  cleanup, and config-override display.

### 4.10 Tests — PASS

- All planned test files exist: `test_dispatch.py`, `test_chat.py` (minimal,
  but REPL behavior covered by `test_main.py`), `test_init.py`,
  `test_config_cmd.py`, `test_sources.py`, `test_run.py`, `test_loop.py`,
  `test_container.py`, `test_inspect.py`, `tests/test_plugins/test_manifest.py`.
- Note: `tests/test_config/test_manifest_overrides.py` (planned in 4.10.5)
  was not created as a separate file — manifest override coverage lives in
  `tests/test_plugins/test_manifest.py`. The functional coverage is present;
  the file layout differs from the plan.
- `make check` green: 1843 tests passed.

### 4.11 Documentation — PASS

- `docs/cli.md` documents all seven subcommands with flags and examples.
- `docs/guides/creating-agentic-packages.md` documents `agent.toml` format,
  `[run]`/`[plugin]`/config-override sections, the configuration cascade,
  Python-based manifest alternative, source types, trust model, and examples.
- `README.md` has a "CLI Commands" section with a summary table, examples
  for each subcommand, the `yoker run` workflow, `yoker inspect` as a safe
  preview, and backward-compatibility note (`yoker` = `yoker chat`).
- `CLAUDE.md` includes `cli/` in the module structure and documents the
  dispatcher pattern.

---

## Edge cases and regressions

- Backward compatibility verified: `yoker` (no args) routes to `yoker chat`;
  flags-first (`yoker --backend-ollama-model X`) routes to `yoker chat`.
- `--with` works from any subcommand position (stripped before dispatch).
- Unknown subcommand → argparse error with valid-choice list, exit code 2.
- Existing examples run without modification (the demo plugin's agent file
  modification is committed; working tree is clean).
- `yoker init --path /etc/yoker.toml` rejected via `validate_storage_path`.
- `yoker run` does not trigger the bootstrap pre-flight (only `chat` does).

---

## Verdict

**approved**

All 12 task groups (4.1–4.12) meet their functional and security acceptance
criteria. `make check` is green (1843 tests passed, format/lint/typecheck
clean). Backward compatibility is preserved. No regressions found.

Two minor deviations from the plan (neither blocking):
1. `ResolvedSource`/`LoadedSource` live in `cli/sources.py` rather than
   `plugins/loader.py` (task 4.5.4) — a reasonable design choice.
2. Manifest-override tests live in `test_plugins/test_manifest.py` rather
   than a separate `test_config/test_manifest_overrides.py` (task 4.10.5) —
   functional coverage is present.