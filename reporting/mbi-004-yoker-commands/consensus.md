# Consensus: MBI-004 yoker Commands — API Architect + Security Engineer

**Date**: 2026-07-08 (revised 2026-07-08 per owner feedback on PR #46)
**Participants**: API Architect Agent, Security Engineer Agent, Functional Analyst
**Documents reviewed:**
- `analysis/api-mbi-004-yoker-commands.md` (API Architect, revised)
- `analysis/security-mbi-004-yoker-commands.md` (Security Engineer)
- `analysis/mbi-004-yoker-commands.md` (functional analysis, source of truth, revised)

## Purpose

This document consolidates the findings of the two domain reviews, records
the design decisions both agree on, the security requirements that must be
incorporated into the implementation, and the open questions that have been
resolved by the owner via PR #46 feedback.

---

## 1. Key Design Decisions (Updated per Owner Feedback PR #46)

### 1.1 CLI subcommands via Clevis commands (owner-directed change)

The owner pushed back on the manual dispatcher: "Clevis has support for
commands." The design now uses Clevis's built-in subcommand mechanism
(`@configclass(cmd=...)`, `get_cmd()`) instead of a manual dispatcher.
Each subcommand is a config class decorated with `@configclass(cmd="X")`,
and Clevis auto-generates CLI args per subcommand. Backward compatibility
is maintained by defaulting to `chat` when no subcommand is given.

### 1.2 Manifest as a generic config-override layer (owner-directed change)

The owner redefined the manifest: "Can't we create a generic way to
override the existing configuration? Just like the CLI arguments can
override. We would have: 2 levels of TOML config -> Manifest overrides ->
CLI overrides." The manifest is now a **generic config-override layer**,
not additive fields on PluginManifest. Layering: base TOML -> manifest
overrides (`agent.toml`) -> CLI overrides. The manifest can override ANY
Config field.

### 1.3 File-based manifest filename: `agent.toml` (owner-directed change)

The owner said: "don't use yoker.toml, that is already used for our
project-level configuration." The file-based manifest is named
`agent.toml`, avoiding the collision with `yoker.toml`.

### 1.4 `PluginManifest` extension is additive and backward compatible

Adding `agent: str | None = None` and `prompt: str | None = None` to
`PluginManifest` is a non-breaking change. These are convenience fallback
fields for Python packages without `agent.toml`. The run-config fields are
carried in a separate `ResolvedSource` dataclass, preserving the
single-responsibility boundary.

### 1.5 Source abstraction generalizes the loader

Both reviews recommend a `Source` abstraction (`kind: Literal["package",
"folder"]`) with a `load_plugin_from_source()` entry point. This keeps the
trust gate (`check_plugin_allowed`) applied uniformly and avoids
duplicating skill/agent loading logic.

### 1.6 Two-phase resolve/load (trust gate before imports)

`resolve_source()` returns metadata only (no imports, no code execution).
`load_source()` performs the actual imports and is called ONLY after
`check_plugin_allowed()` returns True. This two-phase split ensures the
trust gate fires before any code runs.

### 1.7 Trust gate reuses existing guardrails (owner-directed)

The owner confirmed: "Currently when issuing `--with <pkg>` we don't
consider this an explicit opt-in. So, I wouldn't change that behaviour.
Let's keep these guardrails in place and reuse them, not creating parallel
tracks." `yoker run <source>` goes through the same `check_plugin_allowed()`
gate as `--with <source>`. No bypass for named sources.

### 1.8 Agent name resolution: source overrides built-in (owner-confirmed)

The owner confirmed: "source-based named items 'override' existing ones
(although given namespacing, I don't expect that to happen quickly)."

### 1.9 `yoker inspect <source>` — new subcommand (owner-added)

The owner added: "add an additional subcommand: `yoker inspect <source>`
that dumps a report about the source, explaining what it contains, what it
uses, what it does." Inspect is read-only, requires no trust gate, and does
NOT import `tools_module` or execute any code.

### 1.10 No auto-install of `pyproject.toml` (clarified)

The owner asked for clarification on "defer auto-installing
pyproject.toml." This means: when loading a folder source with
`pyproject.toml`, do NOT automatically `pip install` it (build hooks =
arbitrary code execution, CWE-494). Require an explicit `--install` flag,
deferred to a future MBI.

### 1.11 Existing security primitives are reusable

The security engineer confirmed that `UrlWebGuardrail` (SSRF protection),
`PathGuardrail` (symlink resolution + root containment), `is_safe_path`
(path containment), and `validate_base_url_trust` (interactive trust prompt
pattern) are all directly reusable for source resolution security.

---

## 2. Security Requirements That Must Be Incorporated

The following security findings from the Security Engineer must be
incorporated into the implementation. They have been added as security
acceptance criteria to the corresponding TODO.md tasks.

### 2.1 Critical: Trust gate must cover `yoker run` (C1 + M3) — RESOLVED

**Requirement:** Every resolved source must pass
`check_plugin_allowed()` before any code runs (including `tools_module`
imports and `pip install`).

**Owner decision:** Reuse existing `check_plugin_allowed()` — no bypass
for named sources. Same guardrails as `--with`.

**Implementation impact:**
- `resolve_source()` returns metadata only (no imports, no pip install)
- `load_source()` performs imports, called only after trust check passes
- Non-interactive mode rejects untrusted sources by default
- Interactive mode shows a confirmation dialog
- `--dry-run` flag resolves and prints manifest + prompt without executing

**TODO.md tasks affected:** 4.6.1, 4.7.1

### 2.2 Critical: `tools_module` is code, not config (C2) — CORRECTED

**Requirement:** `agent.toml`'s `tools_module` field triggers
`importlib.import_module()` of potentially attacker-supplied code. It must
be treated as code, not configuration.

**Implementation impact:**
- The functional analysis's original claim that "`yoker.toml` is a
  configuration file, not code" has been **corrected** in the revised
  functional analysis. `agent.toml` with `tools_module` is a code
  execution vector.
- `tools_module` imports must not happen before the trust gate fires
- Manifests without `tools_module` are config-only (lower trust tier)
- Config override sections (outside `[run]` and `[plugin]`) are pure
  configuration — they override Config fields but do not execute code

**TODO.md tasks affected:** 4.6.1, 4.5.2

### 2.3 Critical: GitHub URL SSRF and supply-chain protection (C3)

**Requirement:** GitHub URL sources must be validated before cloning.

**Implementation impact:**
- URL must be HTTPS only; HTTP rejected
- Embedded credentials rejected
- SSRF check (`_check_ssrf_for_host`) runs before clone
- Resolved commit SHA recorded for audit
- No auto-`pip install` of the cloned repo (owner-confirmed)
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

**Requirement:** The auto-injected prompt runs with autonomous tool access.

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

## 3. Resolved Open Questions (Owner Feedback PR #46)

All three open questions from the original review have been resolved:

### 3.1 Trust gate for `yoker run <source>` — RESOLVED

**Original disagreement:** API Architect recommended bypassing
`plugins.enabled` (explicit opt-in); Security Engineer required
unconditional trust gate.

**Owner decision:** "Currently when issuing `--with <pkg>` we don't
consider this an explicit opt-in. So, I wouldn't change that behaviour.
Let's keep these guardrails in place and reuse them, not creating parallel
tracks."

**Resolution:** `yoker run <source>` goes through `check_plugin_allowed()`
— same gate as `--with`. No bypass. The Security Engineer's position
prevailed. This is the safer default and eliminates the parallel-track
concern.

### 3.2 Agent name resolution scope — RESOLVED

**Owner decision:** "source-based named items 'override' existing ones
(although given namespacing, I don't expect that to happen quickly)."

**Resolution:** Source's own agent definitions take precedence over
built-in ones. Both reviews agreed on this; the owner confirmed.

### 3.3 File-manifest filename — RESOLVED

**Original question:** `yoker.toml` vs `yoker-manifest.toml` — collision
with project config.

**Owner decision:** "don't use yoker.toml, that is already used for our
project-level configuration - unless we can 'combine' the two - make them
co-exist as one uber-config?"

**Resolution:** Use `agent.toml` as the filename. This avoids the collision
entirely and clearly indicates it's an agentic package manifest. The
manifest lives in the source root, naturally separate from the user/project
config.

---

## 4. New Requirements from Owner Feedback

### 4.1 Clevis commands (not manual dispatcher)

The owner pushed back on the manual dispatcher. The design now uses
Clevis's `@configclass(cmd=...)` and `get_cmd()`. See section 1.1.

### 4.2 Manifest as config-override layer

The owner redefined the manifest as a generic config-override layer. See
section 1.2.

### 4.3 `yoker inspect <source>`

New subcommand added by the owner. See section 1.9. Added as task group
4.12 in TODO.md.

### 4.4 "Defer auto-installing pyproject.toml" — clarified

The owner asked "what do you mean by this?" The clarification: auto-
installing runs build hooks (arbitrary code execution, CWE-494). Do NOT
auto-install by default; require explicit `--install` flag (future MBI).
See section 1.10.

---

## 5. Prioritized Implementation Order (Updated)

1. **4.5.1** — Add `agent`/`prompt` to `PluginManifest` (additive, no
   security risk)
2. **4.5.2** — File-based manifest loading (`agent.toml` parsing, extract
   `[run]`/`[plugin]`, return config overrides)
3. **4.5.3** — Implement `get_yoker_config_with_manifest()` (config
   loading with manifest as override layer)
4. **4.1** — Clevis subcommand config classes (`@configclass(cmd=...)`)
5. **4.6.1** — Source resolution framework with two-phase resolve/load
6. **4.6.2** — Folder path resolution with path validation (H4)
7. **4.6.3** — GitHub URL with SSRF + HTTPS + SHA pinning (C3)
8. **4.6.4** — Zip extraction with bomb/traversal protection (H1)
9. **4.7.1** — `yoker run` with trust gate + dry-run + prompt cap (C1, H2)
10. **4.8.1** — `yoker loop` with finite default + backoff (M1)
11. **4.9.1** — `yoker container` with Dockerfile hardening (H3)
12. **4.12** — `yoker inspect` (read-only report, no trust gate)
13. **4.2, 4.3, 4.4** — `chat`, `init`, `config`
14. **4.10** — Tests (including security tests and inspect tests)
15. **4.11** — Documentation (including `agent.toml` format and trust model)

---

## 6. Summary

The two domain reviews are now fully aligned with the owner's feedback.
The primary tension (trust gate bypass vs. mandatory gate) has been
resolved in favor of the Security Engineer's position: reuse
`check_plugin_allowed()` with no bypass. The CLI design has been updated
to use Clevis's built-in command support instead of a manual dispatcher.
The manifest has been redefined as a generic config-override layer using
`agent.toml`. A new `yoker inspect` subcommand has been added. All
security acceptance criteria remain in place and have been updated to
reflect the resolved design decisions.