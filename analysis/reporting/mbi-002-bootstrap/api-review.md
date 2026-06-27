# API Architecture Review: MBI-002 Bootstrap Wizard

**Date**: 2026-06-27
**Reviewer**: API Architect Agent
**Task**: MBI-002 Bootstrap Wizard implementation (commits 552d20b, a26d42f)
**Branch**: feature/mbi-002-bootstrap
**Prior stage**: Functional review (passed)

## Summary

The implementation is architecturally sound and faithfully realizes the
agreed design across all eight architectural verification points: module
boundaries, generic annotation-driven writer, minimal boolean detection,
single default source, UI-layer separation, clean integration wiring,
async-first wizard, and a minimal public API surface. The implementation
deviates from the design doc on two edge-case contracts (malformed-TOML
handling in the detector, and merge-on-race in the writer); both are
defensible simplifications, but the design doc has not been updated to
reflect them, creating contract drift. The deviations do not block the
implementation.

**Verdict: APPROVED** — with non-blocking suggestions and two contract-drift
items to resolve at the owner's discretion.

## Findings

### Strengths

- **Module boundaries are correct.** The `bootstrap/` package holds
  detection (`detect.py`), the wizard (`wizard.py`), step functions
  (`steps.py`), and the curated model list (`modellist.py`). The
  `ConfigWriter` lives in `src/yoker/config/writer.py` per owner feedback
  point #4 — not in the bootstrap package. The wizard calls it; it does
  not own it. The writer's API (`render_config_toml`, `write_config`) is
  reusable for in-session augmentation: a caller loads the existing
  config, applies overrides, and writes back.

- **The writer is genuinely annotation-driven.** `writer.py` walks the
  dataclass tree via `dataclasses.fields()` and reads `metadata["help"]`
  for inline comments. There are no hardcoded field names. The test
  `test_new_annotated_field_is_rendered_automatically`
  (`tests/test_config/test_writer.py`) proves the contract: a freshly
  annotated dataclass field renders with no writer change. Owner
  feedback point #5 is satisfied.

- **`config_provided()` is the agreed minimal boolean.** No
  `ConfigStatus`, no state machine, no `REQUIRED_CONFIG_FIELDS`. Owner
  feedback point #2 is satisfied. The CLI-prefix set is derived from
  `dataclasses.fields(Config)` rather than hardcoded, keeping it in sync
  with the schema — a nice touch that goes beyond the design doc.

- **Single default source.** `OllamaConfig.model` in
  `src/yoker/config/__init__.py` is the only literal
  (`"gemini-3-flash-preview:cloud"`). `modellist.py` reads it via
  `Config().backend.ollama.model` — no duplicate literal. Owner feedback
  point #1 is satisfied. (The literal still appears in
  `examples/yoker.toml` and `README.md` as `llama3.2:latest` — that is a
  documentation lag, not an architectural issue, and outside this
  review's scope.)

- **UI-layer separation is intact.** The wizard and steps use
  `UIHandler` for all IO. A `grep` for `print(`/`sys.stdout`/`sys.stderr`
  in `src/yoker/bootstrap/` returns only a docstring mention — no direct
  output. The new protocol methods `output_info` and `get_secret_input`
  are additive, narrowly scoped, and implemented by both
  `InteractiveUIHandler` (masked via `is_password=True`) and
  `BatchUIHandler` (delegates to `get_input`). The non-interactive abort
  path in `__main__.py` writes to stderr directly, which is correct: the
  wizard is not instantiated there, and the warning is the approved
  exit path, not wizard IO.

- **Integration wiring is clean.** `__main__.py::main()` runs
    `config_provided()` before constructing the `Agent` (pre-flight
    gate). The interactive/non-interactive split is a TTY check that
    mirrors `_create_ui`'s selection. After the wizard writes config and
    returns `WRITTEN`, `__main__` falls through to normal `Agent`
    construction — the "continue into session" contract is met. The
    manual path exits cleanly with `sys.exit(0)`.

- **Async-first.** `BootstrapWizard.run()` is `async`, and every step
  function is an `async` coroutine, consistent with yoker's async
  architecture. The wizard is driven via `asyncio.run(_run_bootstrap(...))`.

- **Public API surface is clean and minimal.**
  `yoker/bootstrap/__init__.py` exports exactly `config_provided`,
  `BootstrapWizard`, `BootstrapResult`. `yoker/config/writer.py` exports
  `render_config_toml` and `write_config`. `modellist.py`'s helpers and
  `steps.py`'s step functions are internal to the package and not
  re-exported.

### Issues Found

#### Issue 1: Detector deviates from design doc on malformed/permission-denied TOML

- **Severity**: Low (architecturally acceptable; contract drift).
- **Where**: `src/yoker/bootstrap/detect.py` (docstring lines 82–86 and
  the `config_provided()` body); design doc
  `analysis/bootstrap-config-detection.md` edge-case table (lines
  234–235).
- **What's wrong**: The design doc's edge-case table specifies that
  malformed TOML should raise `ConfigurationError` and permission-denied
  should raise `ConfigurationError`. The implementation only checks
  `Path.exists()` and never opens the files, so malformed TOML returns
  `True` (file exists) and permission-denied returns `True` (existence
  does not require read permission on Unix). The docstring documents
  this as a deliberate choice ("surfacing parse errors is left to the
  normal config-loading path").
- **Architectural assessment**: The implementation's approach is
  leaner and more consistent with the owner's "minimal boolean"
  philosophy (PR #34 point 2). Raising from the detector would require
  parsing the file, duplicating error-handling that Clevis already
  performs during `Agent` construction with richer diagnostics. Letting
  the config loader surface parse errors at the normal load point is a
  cleaner separation of concerns: the detector answers the boolean
  ("did the user do anything config-related?"), the loader validates
  content. **This is architecturally acceptable.**
- **Recommended fix**: Update the design doc's edge-case table
  (`analysis/bootstrap-config-detection.md` lines 234–235) to match the
  implemented behavior, so the contract and code agree. Alternatively,
  if the owner prefers the raise-on-error contract, add a parseability
  check to the detector — but this is not recommended given the
  minimalism direction.

#### Issue 2: Writer clobbers instead of merging on race

- **Severity**: Low (unlikely race; contract drift; design awkwardness).
- **Where**: `src/yoker/config/writer.py` line 164 (`os.O_TRUNC`); design
  doc `analysis/bootstrap-wizard-design.md` line 191 ("the writer merges
  rather than clobbers, preserving unknown keys").
- **What's wrong**: The design doc specifies that if a config file
  appears between detection and write (race), the writer should merge
  rather than clobber, preserving unknown keys. The implementation uses
  `os.O_TRUNC` and rewrites the file from the rendered `Config`, which
  discards any keys not represented in the dataclass (e.g., user
  comments, manually-added unknown fields).
- **Architectural assessment**: 
  - **Bootstrap race**: genuinely unlikely — the wizard only runs when
    `config_provided()` is `False` (no file exists), and the user would
    have to author a config in the seconds between detection and write.
  - **Reuse case**: the design doc's reuse story ("add `plugins enabled
    = true` to your configuration") is supported by the current API:
    the caller loads the existing config via `get_yoker_config()`,
    passes it to `write_config(config, path, overrides={...})`, and the
    writer renders the full config + override. Clobbering is the
    caller's choice, not a writer limitation. Unknown keys outside the
    dataclass schema would still be lost on rewrite — but the
    annotation-driven rendering cannot preserve them anyway (it renders
    from the dataclass, not from the parsed TOML).
  - **Merge + annotation-driven tension**: implementing true merge
    (preserve unknown keys) would require round-tripping through
    `tomllib` to capture keys not in the dataclass, then layering
    annotation-driven comments on top — architecturally awkward and
    arguably at odds with the "render from the dataclass" model.
  **The clobber is architecturally acceptable**, but it is a contract
  violation against the design doc.
- **Recommended fix**: Update the design doc
  (`analysis/bootstrap-wizard-design.md` line 191) to state that the
  writer renders from the dataclass (clobber semantics) and that
  unknown keys are not preserved across writes; document that the race
  is accepted as unlikely. If true merge is ever required (e.g., for
  in-session augmentation that must preserve user comments), add a
  separate `merge_config_toml()` helper that operates on the parsed
  TOML dict rather than the dataclass — do not overload the
  annotation-driven writer.

### Compliance Check

| Verification point | Status | Notes |
|---|---|---|
| Module boundaries (writer in config, not bootstrap) | Pass | `config/writer.py`, called by wizard |
| Generic annotation-driven writer (no hardcoded field names) | Pass | `dataclasses.fields()` + `metadata["help"]`; test proves it |
| `config_provided()` is simple boolean | Pass | No state machine |
| Single default source | Pass | Only `OllamaConfig.model`; modellist reads via `Config()` |
| UI-layer separation (UIHandler for all IO) | Pass | No direct `print` in bootstrap package |
| Integration wiring (pre-flight, interactive split, continue) | Pass | `__main__.py` clean |
| Async-first wizard | Pass | `BootstrapWizard.run()` is async |
| Public API surface clean and minimal | Pass | 3 exports from bootstrap, 2 from writer |
| RESTful / RPC N/A | N/A | No HTTP API in this MBI |
| Error handling (RFC 7807) | N/A | No HTTP error responses in this MBI |

### Non-blocking Suggestions

1. **Encapsulation: `DOCS_HOME_URL` import.** `__main__.py` imports
   `DOCS_HOME_URL` from `yoker.bootstrap.steps` (line 26), reaching past
   the public API into an internal module. Consider either re-exporting
   `DOCS_HOME_URL` (and the related docs URLs) from
   `yoker/bootstrap/__init__.py`, or moving the docs-URL constants to a
   small `yoker/bootstrap/docs.py` module and importing from there. Low
   priority; the current code works.

2. **Sync `write_config()` in an async wizard.** `BootstrapWizard.run()`
   is async and `await`s every step, but calls `write_config(...)`
   synchronously (line 121). File I/O is blocking. For a small config
   file the latency is negligible, but for strict async-first
   consistency an `async def write_config` (using `asyncio.tothread` or
   `aiofiles`) would be more consistent. Low priority; do not block on
   this.

3. **`step_account_check` swallows `webbrowser.Error` silently.** The
   URL is already printed above, so the user is not left without a link,
   but a one-line `ui.output_info` noting that the browser could not be
   launched would be friendlier. UX, not architecture.

4. **`_create_ui(Config())` during bootstrap.** `__main__.py` line 194
   constructs a `Config()` to decide the UI handler for the wizard. This
   is correct (the wizard runs before any config is loaded, and
   `Config().ui.mode` defaults to `"interactive"`), but it's worth a
   one-line comment noting that the bootstrap UI is always interactive
   because `config_provided()` is `False` implies no `--ui-mode` flag.
   The existing comment at lines 186–189 already covers this — no
   change needed, just confirming it reads correctly.

## Recommendations

Prioritized:

1. **Resolve contract drift on the two deviations** (Issue 1 and
   Issue 2). Either update the design docs to match the implemented
   behavior (recommended — the implementations are the simpler,
   owner-aligned choices), or update the code to match the docs. This is
   documentation work, not code work, but it keeps the design docs
   authoritative.
2. (Optional) Re-export the docs-URL constants from
   `yoker/bootstrap/__init__.py` to avoid `__main__.py` reaching into
   `yoker.bootstrap.steps`.
3. (Optional) Consider an async `write_config` variant for strict
   async-first consistency in a future iteration.

## Conclusion

**APPROVED.** The architecture is sound. The bootstrap package is
correctly scoped, the `ConfigWriter` is correctly placed in the config
module and is genuinely generic, detection is the agreed minimal
boolean, the default model has a single source, the UI-layer separation
is preserved with clean additive protocol methods, the `__main__.py`
wiring is correct (pre-flight gate, interactive/non-interactive split,
continue-into-session), the wizard is async-first, and the public API
surface is minimal. The two deviations from the design doc's edge-case
contracts are defensible simplifications aligned with the owner's
minimalism direction; they should be reconciled with the design docs
but do not block the implementation.

## Next Steps

- Functional review already passed; this API review approves.
- Owner decides on the two contract-drift items (update docs vs.
  update code). Recommended: update the design docs to match.
- Hand off to code-reviewer / testing-engineer for their domains
  (out of scope for this review).