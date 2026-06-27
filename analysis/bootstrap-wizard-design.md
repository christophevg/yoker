# Bootstrap Wizard Design (MBI-002, Tasks 2.2–2.5)

**Date**: 2026-06-27
**Task**: MBI-002: Bootstrap — interactive wizard (post-detection)
**Author**: Functional Analyst
**Related**: `analysis/bootstrap-config-detection.md` (task 2.1 API),
`TODO.md` (MBI-002 tasks), `PLAN.md` (MBI-002), `REQUIREMENTS.md`

## Purpose

This document specifies the interactive bootstrap wizard that runs when
`detect_config()` (task 2.1) reports `needs_bootstrap`. It incorporates the
repository owner's direction verbatim and refines the earlier 4-option menu into
a lean, guided flow. The guiding principle, per the owner: **least-possible
steps to a minimal yet complete config**.

## What Changed From the Original Plan

The original PLAN.md described a backend-selection menu offering "Ollama local,
ollama.com API, other". The owner's feedback reshapes the opening: the wizard
no longer opens with a backend menu. It opens by **explaining what yoker is**,
reporting that no config was found, and offering **guided vs. manual** setup.
Backend selection collapses to a single supported backend today (Ollama),
introduced with a short rationale rather than a multi-way menu.

## Revised Wizard Flow (End-to-End)

```
                        __main__.py::main()
                              |
                       detect_config()  (task 2.1)
                              |
                    needs_bootstrap? ─── no ──> normal Agent startup
                              | yes
                              v
                    ┌─────────────────────┐
                    │  BootstrapWizard    │
                    │  .run()             │
                    └─────────────────────┘
                              |
   ┌──────────────────────────────────────────────────────────┐
   │ Step 0  Welcome / explain yoker                          │
   │ Step 1  Report: no config found; offer guided vs manual   │
   │ Step 2  (guided) Backend intro — Ollama, free tier       │
   │ Step 3  "Do you have an ollama account?"                  │
   │          no  ─> point to online guide (docs site)         │
   │          yes ─> Step 4                                    │
   │ Step 4  Split: ollama app (signed in)  vs  API key        │
   │          app path  ─> default backend config, no api key │
   │          apikey path ─> collect key + optional guide link │
   │ Step 5  Model preference: curated list + free text        │
   │ Step 6  Generate ~/.yoker.toml (chmod 600) + continue    │
   └──────────────────────────────────────────────────────────┘
```

### Step 0 — Welcome / Explain Yoker

Explain, in 2–3 lines, what yoker is: **a provider-neutral AI backend for
running agentic workflows**. Set the frame before asking anything.

### Step 1 — Detect & Offer Guided vs Manual

Report that no yoker configuration was found, then offer two paths:

- **Guided setup** (recommended) — walks the user through the remaining steps.
- **Manual setup** — prints the path where config should live and exits, leaving
  the user to author `~/.yoker.toml` themselves.

Choosing manual prints a short skeleton and a link to the docs page, then exits
without writing anything.

### Step 2 — Backend Intro (Guided Only)

A short informational panel (not a multi-way selector): today yoker supports
**Ollama** as the model-neutral provider, with a **free tier** usable to explore
yoker and agentic workflows at no cost. Other backends will be added in the
future. No choice is presented here — there is only one backend today. This
keeps the flow honest (we are not pretending to offer a choice we don't have)
while signalling extensibility.

### Step 3 — Ollama Account Check

Prompt: *"Do you have an ollama account?"*

- **No** — open the docs guide URL (the wizard may launch the user's browser
  directly via `webbrowser.open()`), and say we'll wait until ready, then return
  here and continue. The page itself links to ollama.com for account creation and
  local app/proxy install. The wizard does **not** abort or exit; it pauses,
  surfaces the link, and lets the user resume the flow when they are ready.
- **Yes** — continue to Step 4.

### Step 4 — Connection Method (Split Choice)

Two options, in this order:

1. **Use the ollama app (signed in)** — the user runs the local ollama app/proxy
   and is signed in. The wizard writes the **default backend config with no API
   key** (`base_url = "http://localhost:11434"`). Local models work without
   sign-in; cloud models require the signed-in app.
2. **Use an API key** — the user has generated an API key. The wizard collects
   the key (masked input), optionally displays a link to the online guide for
   creating a key, and stores it in the config.

Prompt wording (locked, app-first key-second):

> Connect via:
>   1) The ollama app running locally (recommended — no key needed)
>   2) An ollama API key

### Step 5 — Model Preference

Prompt: *"Pick a model, or accept the default."*

- **Curated list (primary and only approach)**: the wizard presents a curated
  list of recommended models, including the default model, plus a **free-text
  entry** option for users who know the exact model id they want. There is **no
  live fetch** of `GET <base_url>/api/tags` from the local ollama app/proxy.
  Rationale (owner): this is typically a first-time install, so no models will
  have been pulled/used before — fetching the local proxy's tag list is not
  useful. The curated list is the primary and only mechanism.
- **Default model**: `gemini-3-flash-preview:cloud` (cloud, no download needed —
  frictionless first run). This matches the new `Config` default set by the
  companion task (see TODO 2.0). The curated list surfaces this default first
  so accepting the default is a single keystroke.
- **Curated list contents**: the default model plus a small selection of other
  recommended cloud and local models (final contents TBD during implementation;
  minimum is the default + free-text entry).

### Step 6 — Config Generation & Continue into Session

Generate `~/.yoker.toml`:

- Start from the **full default `Config` rendered as TOML** (every field, with
  inline comment annotations explaining each section).
- Override only the non-default values collected by the wizard (model, and
  optionally `api_key`; `base_url` only if the user changed it).
- Write to the **user-level path** `~/.yoker.toml` so it applies across all
  yoker-based apps.
- **`chmod 600`** the file immediately after writing.
- Print a brief confirmation: the config was created at `~/.yoker.toml`
  (home-folder level, shared by all yoker-based apps) and **yoker is continuing
  into the normal session now** — the user does **not** need to rerun `yoker`.
- **Continue, don't exit**: after writing the config, the wizard returns control
  to `__main__.py`, which proceeds straight into the normal Agent startup using
  the freshly-written config, exactly as if a config had existed all along. The
  wizard does not exit the process and does not instruct the user to relaunch.

## Config File Location & Permissions

| Item | Value |
|------|-------|
| User config path | `~/.yoker.toml` (= `Path.home() / ".yoker.toml"`) — matches existing Clevis discovery, satisfies "home folder, across all apps" |
| Project config path | `./yoker.toml` — untouched by the wizard |
| Permissions | `chmod 600` on every yoker config file the wizard writes |
| Existing files | If `~/.yoker.toml` already exists but is `incomplete`, the wizard merges into it (preserving unknown keys) rather than clobbering. If `missing`, it creates a new file. |

**`chmod 600` scope (owner directive)**: applies to all yoker config files the
wizard writes. The detector (task 2.1) reads only; it does not create files.
The wizard's writer (task 2.5) is the component that sets 600 on write. If the
wizard ever writes an intermediate/backup file, that file must also be 600.

**API key storage (security-critical)**: an API key is stored **only** in
`~/.yoker.toml`, never in env vars, never in project-level `./yoker.toml`
(which may be committed to git), never logged, never echoed. The key-entry
prompt uses masked input. The writer sets `chmod 600` before writing the key.

## Model List Fetching — Feasibility Answer (considered and rejected)

To the original question *"can we fetch a list from ollama?"* — yes,
technically. The `ollama` Python library (already a dependency, `ollama>=0.6.0`)
exposes `AsyncClient(host=...).list()`, which calls `GET <host>/api/tags` and
returns the models available to the local ollama instance, including cloud
models once the app is signed in.

**However, live fetch was considered and rejected for the first-install UX.**
The owner's reasoning (verbatim): *"Fetching from the local proxy seems not
useful, because this will typically be a first-time install and no models will
have been used before."* On a fresh install the local proxy has nothing pulled
yet, so `/api/tags` returns an empty or near-empty list that misleads rather
than helps. The wizard therefore uses a **curated list + free-text entry** as
the primary and only approach, and `modellist.py` makes **no network call**.

If a future iteration wants to surface already-pulled models (e.g. a
post-bootstrap `/models` refresh), the same `AsyncClient.list()` call remains
available as a follow-on capability outside the bootstrap flow.

## Security Considerations

1. **API key**: masked input; stored only in `~/.yoker.toml`; file `chmod 600`;
   never written to project config; never logged.
2. **Local ollama without sign-in**: local model access has no sign-in; only
   cloud models require an account + signed-in app. The wizard's copy must not
   imply local use needs credentials.
3. **No secret logging**: wizard logs/echo field **names** and model choices,
   never `api_key` values.
4. **File permissions on write**: `chmod 600` applied atomically after write;
   if write fails, no partial unprivileged file is left.
5. **Path safety**: config path derived from `Path.home()`, not user-supplied
   strings.
6. **Detector (2.1) reads only**; wizard (2.5) writes. Separation preserved.

## Non-Interactive Mode

`yoker` is also used in pipelines/scripts (BatchUIHandler). When
`detect_config()` returns `needs_bootstrap` in **non-interactive** mode:

- **Do not** launch the wizard. The wizard requires a TTY.
- Print a **concise warning** to stderr explaining that no usable config was
  found, name the expected path (`~/.yoker.toml`), and point to the docs guide.
- Exit with a non-zero status so scripts fail fast rather than silently using
  defaults.

Warning wording (approved, final):

> No yoker configuration found at ~/.yoker.toml.
> Run `yoker` interactively to configure, or see <docs URL>.
> Aborting (non-interactive mode).

## Documentation Guides (New Requirement)

Per owner: a dedicated docs-site page describing, in detail with screenshots, how
to create an ollama account and install the local proxy/app, optionally with
per-OS variants. This is referenced by Steps 3 and 4 of the wizard but authored
on the docs site, not embedded in the binary.

- **Structure (decided)**: **one merged page** covering ollama account
  creation + app/proxy install + (optional) API-key creation. Anchors within
  the page let the wizard deep-link to each context (account check, key
  creation). Least duplication; the wizard links to the relevant anchor.
- **Location**: docs site (Sphinx/readthedocs), a new guide e.g.
  `docs/guides/getting-started-with-ollama.md` (exact path TBD with docs).
- **Content**: account creation, app/proxy install (macOS/Linux/Windows),
  signing in, generating an API key, verifying cloud-model access.

## Resolved Open Questions

All open questions have been resolved by the repository owner. Summary of
decisions:

| ID | Topic | Question | Decision |
|----|-------|----------|----------|
| Q1 | Split-choice wording | Confirm exact labels/order for "ollama app" vs "API key" | **Resolved.** App-first, key-second; locked wording above. |
| Q2 | Default cloud demo model | Which cloud model for frictionless demo? | **Resolved.** `gemini-3-flash-preview:cloud`. Additionally, the `Config` default itself changes from `llama3.2:latest` to `gemini-3-flash-preview:cloud` (companion TODO 2.0). |
| Q3 | Non-interactive warning | Confirm abort message wording | **Resolved.** Approved draft as-is (see Non-Interactive Mode). |
| Q4 | Docs page structure | One merged guide or split into two? | **Resolved.** One merged page with anchors. |
| Q5 | Model list curation | Curated list or live fetch? | **Resolved.** Curated list + free-text entry is the **primary and only** approach. Live fetch rejected for first-install UX (typically nothing pulled yet). |

## Module Layout (extends task 2.1's `yoker/bootstrap/`)

```
src/yoker/bootstrap/
  __init__.py      # Public API exports (from 2.1 + wizard additions)
  detect.py        # Config detection (task 2.1)
  wizard.py        # BootstrapWizard: the interactive flow (2.2–2.5 glue)
  steps.py         # Individual step functions (account check, split, model)
  modellist.py     # Curated model list + free-text entry (NO network call)
  writer.py        # Config writer: render Config->TOML, override, write, chmod 600
  __main__wiring   # (in yoker/__main__.py) pre-flight call + non-interactive path
```

`BootstrapWizard` is async (yoker is async-first). It consumes a `UIHandler` for
all I/O (no direct `print`), keeping the UI-layer separation intact. In batch /
non-interactive mode the wizard is **not** instantiated; `__main__.py` emits the
warning and exits.

## Requirements Coverage

| Requirement source | Covered by |
|---|---|
| Detect missing config | task 2.1 (existing design) |
| Frictionless default model (cloud, no download) | task 2.0 (Config default change) |
| Explain yoker + offer guided/manual | Step 0–1 (task 2.2) |
| Single-backend intro (Ollama, free tier) | Step 2 (task 2.3) |
| Account check + online guide pointer (open URL, wait, resume) | Step 3 + docs page (task 2.3) |
| Connection method (app vs API key, locked wording) | Step 4 (task 2.3) |
| Model selection via curated list + free text (no live fetch) | Step 5 (task 2.4) |
| Generate config at home-folder level, then continue into session | Step 6 (task 2.5) |
| chmod 600 on all written config files | writer (task 2.5) |
| API key stored only in ~/.yoker.toml | writer (task 2.5) |
| Non-interactive abort (approved wording) | __main__.py wiring (task 2.6) |
| Documentation guide (one merged page with anchors) | docs site (task 2.7) |

## Revised Task Breakdown (for TODO.md)

The original tasks 2.2–2.5 are refined into the components above. Proposed
updated task list:

- **2.0** Change Config Default Model to `gemini-3-flash-preview:cloud`
  - Update `Config` schema default in `src/yoker/config.py` (and anywhere else
    the default is defined) from `llama3.2:latest` to
    `gemini-3-flash-preview:cloud`
  - Rationale: frictionless first run — cloud model needs no local download
  - This is the default the wizard references and offers in Step 5
- **2.1** Detect Missing Configuration *(unchanged — see bootstrap-config-detection.md)*
- **2.2** Welcome & Guided-vs-Manual Flow
  - Step 0 (explain yoker) + Step 1 (offer guided/manual; manual path prints skeleton + link)
  - Consumes `ConfigStatus` from 2.1; emits via `UIHandler`
- **2.3** Ollama Account & Connection-Method Steps
  - Step 2 (backend intro), Step 3 (account check → open docs URL + wait/resume,
    no abort), Step 4 (split: app vs API key, locked wording, masked key entry)
- **2.4** Model Selection Wizard
  - `modellist.py`: **curated list** of recommended models (including the
    default `gemini-3-flash-preview:cloud`) + free-text entry — **no network
    call**. Live fetch was considered and rejected for first-install UX.
  - Step 5 prompt (pick from curated list / accept default / free text)
- **2.5** Config Writer & Continue into Session
  - Render full Config→TOML with comments, override wizard-collected values,
    write `~/.yoker.toml`, `chmod 600`
  - Print brief confirmation that config was created and yoker is continuing
  - **Return control to `__main__.py`** which proceeds into the normal Agent
    session using the freshly-written config — the wizard does NOT exit or ask
    the user to rerun
  - API key stored only here
- **2.6** Non-Interactive Path & `__main__.py` Wiring
  - Wire `detect_config()` → wizard in interactive mode (wizard returns;
    `__main__.py` continues to Agent startup)
  - Non-interactive: warn (approved wording) + exit non-zero (no wizard
    instantiation)
- **2.7** Bootstrap Documentation Guide (docs site)
  - **One merged page**: ollama account + app/proxy install + (optional)
    key-creation, with screenshots/per-OS variants; wizard links to anchors
- **TEST** Bootstrap flow tests *(spans 2.0, 2.2–2.6)*

## Notes

- This document intentionally avoids prescribing exact UI rendering (Rich
  panels, prompt_toolkit widgets) — that is the UI layer's concern and must go
  through `UIHandler`. The wizard calls `UIHandler` methods; concrete styling is
  decided in the interactive handler.
- The wizard is **optional to invoke** in library mode: callers passing an
  explicit `Config` skip bootstrap entirely (per task 2.1 design).
