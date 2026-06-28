# Security Review: Multi-Provider Backend Design

**Date**: 2026-06-28
**Reviewer**: security-engineer
**Scope**: `analysis/multi-provider-backend-design.md` (final, owner-approved) and the current code it builds on (`config/__init__.py`, `config/writer.py`, `bootstrap/wizard.py` + `steps.py`, `agent/_setup.py`, `builtin/agent.py`, `events/types.py`, `tools/web/`).
**Branch reviewed**: `master` (synced at `1273415`) for the design's base; `feature/mbi-002-bootstrap` for the wizard/writer files the design references.
**Mode**: Review-only. No code or design-note modifications were made.

---

## 1. Executive Summary

The design is a clean, well-scoped refactor that preserves the existing security posture (chmod 0o600 config file, no silent fallback, no secret logging) while extending it to three providers. Two findings require owner attention because they intersect with explicit owner decisions (Q6 CLI args, Q18 OpenAI `base_url`):

- **H1 — API keys surfaced as CLI arguments.** Clevis auto-generates `--backend-*-api-key` flags from the dataclass fields. API keys on the command line leak via shell history, `ps`, and process listings. This is pre-existing for Ollama but the design propagates it to OpenAI and Anthropic. Q6 explicitly keeps per-provider sub-config args as Clevis-generated; this finding asks the owner to amend Q6 so api-key fields are excluded from CLI generation.
- **M1 — `OpenAIConfig.base_url` / `AnthropicConfig.base_url` credential-leakage surface.** Q18 enables Azure/compat gateways via `base_url`. Combined with Clevis's project-level `./yoker.toml` having higher priority than `~/.yoker.toml`, a malicious project config can redirect an API key to an attacker-controlled server. The design note should flag `base_url` as a trust boundary and require https.

The remaining review items (config migration, unknown-provider error, subagent spawn, TurnEndEvent stats, web tools) are confirmed benign or positive.

---

## 2. Risk Register

| ID | Severity | Area | Description | Recommendation | Phase | Owner action |
|---|---|---|---|---|---|---|
| H1 | High | CLI args / secret exposure | Clevis auto-generates `--backend-{ollama,openai,anthropic}-api-key` CLI args from dataclass fields; API keys on the command line leak via shell history, `ps`, `/proc/*/cmdline`, process accounting. Pre-existing for Ollama; design adds two more leak surfaces. | Exclude `api_key` fields from Clevis CLI generation (add a `metadata={"secret": True}` convention and skip such fields in `Factory.configure_parser`, or annotate fields out of CLI generation). Keep env-var and TOML-file as the only key input paths. | Phase 1 (pattern), Phase 2/3 (new fields) | **Design-note amendment** — Q6 currently mandates Clevis-generated per-provider args; owner should carve out api-key fields. |
| M1 | Medium | SSRF / credential leakage | `OpenAIConfig.base_url` (Q18) and `AnthropicConfig.base_url` are forwarded to the provider SDK. `validate_url` only checks scheme+netloc. A non-https or attacker-controlled `base_url` receives the `Authorization: Bearer <key>` header. Project-level `./yoker.toml` overrides `~/.yoker.toml`, so a cloned repo can silently redirect a user's API key. | (a) Require `https://` for `base_url` when an api_key is configured (reject or warn on http). (b) Document `base_url` as a trust boundary in the design note. (c) Consider warning when `base_url` is set via CLI or project config while the api_key comes from user config. | Phase 2 (OpenAI base_url), Phase 3 (Anthropic base_url) | **Design-note amendment** — Q18 should record the https requirement and trust-boundary note. |
| M2 | Medium | Trust boundary / supply chain | Clevis loads `./yoker.toml` (project) with higher priority than `~/.yoker.toml` (user). A malicious project can override `backend.openai.base_url` or `backend.provider` and capture/exhaust a user's API key. Pre-existing for Ollama (`base_url`), amplified by the new `base_url`+`api_key` combination on OpenAI/Anthropic. | Document the project-config trust boundary in the design note and the getting-started guide. Consider a startup warning when `backend.*.base_url` is set in project config but the api_key comes from user config. Long-term: warn when a project config sets any backend credential field. | Phase 2/3 | **Design-note note** (non-blocking; awareness). |
| L1 | Low | URL validation | `validate_url` accepts any scheme (`http`, `https`, `file`, `ftp`, etc.) and URLs with embedded credentials (`https://user:pass@host`). Embedded credentials would be logged by `create_client`'s `host=base_url` log line. | Tighten `validate_url` for backend `base_url` fields to require `http` or `https` scheme and reject userinfo (`@` in netloc). | Phase 1 (Ollama), Phase 2/3 (new configs) | Implementation-time guidance for python-developer. |
| L2 | Low | Secret in TOML rendering | `render_config_toml` serializes `api_key` values into the TOML string. The writer never logs values (documented), but the rendered string is passed to `step_manual` which prints the skeleton to the UI. If a user re-runs manual setup with a config that already contains keys, they would be echoed to the terminal. | `step_manual` should redact `api_key` fields when printing a skeleton (replace with `"<set in file>"` or omit). | Phase 1 (writer is in scope) / wizard follow-up | Implementation-time guidance; note for wizard follow-up (deferred per §8). |
| L3 | Low | Logging hygiene at backend construction | `create_client` logs `host=base_url` and `auth="api_key"` (literal, not the value) — good. The design moves this into `OllamaBackend`/`OpenAIBackend`/`AnthropicBackend` constructors. The same care must be applied in the new backends: never log the api_key, and avoid logging `base_url` if it may carry userinfo. | Add a non-functional requirement to the design note: "backends MUST NOT log api_key values; `base_url` may be logged only after userinfo stripping." | Phase 2/3 | Implementation-time guidance; design-note NFR. |
| I1 | Informational | Subagent credential propagation (positive) | Current `builtin/agent.py::_create_subagent` (lines 150-155) DROPS `api_key` when rebuilding `OllamaConfig` for the subagent — a pre-existing bug that breaks Ollama-cloud subagents. The design's `with_model` helper uses `dataclasses.replace(sub, model=model)` which correctly preserves `api_key` and all other fields. | Confirm the `with_model` helper preserves ALL fields (it does). Add a regression test asserting the subagent's backend config is a faithful copy with only `model` changed. | Phase 1 | Implementation-time guidance (test). |
| I2 | Informational | Multiple secrets in one 0o600 file | With three providers, `~/.yoker.toml` may hold up to three API keys in a single file. `write_config` applies `os.open(0o600)` + `os.chmod(0o600)` to the whole file regardless of content, so all keys are owner-only. No additional risk from the multi-secret shape. | None. Confirm `render_config_toml` union-awareness + `write_config` chmod 600 still cover the whole file (they do). | Phase 1 | None. |
| I3 | Informational | Config migration | Q8: no migration; old files stay valid; new Optional fields default to None. No rewrite window where permissions could be wrong. `~/.yoker.toml` is only written by the wizard (first run) and never re-written by the app, so existing 0o600 files keep their permissions. | None. | Phase 1 | None. |
| I4 | Informational | Unknown-provider error | `create_backend` raises `ConfigurationError` with `sorted(BACKENDS)` — a list of provider-name keys ("ollama", "openai", "anthropic"), not API keys or config contents. No sensitive info leaked. | None. | Phase 1 | None. |
| I5 | Informational | TurnEndEvent stats | New `input_tokens`/`output_tokens` are integer counts. No prompt content, model output, or API key is carried in stats. | None. | Phase 1 | None. |
| I6 | Informational | Web tools "No backend configured" | `websearch`/`webfetch` return `ToolResult(success=False, error="No backend configured ...")` — a generic string with no API key, base_url, or provider config content. `create_web_backends` returns an empty dict when `provider != "ollama"`; no key is materialized. | None. | Phase 2/3 | None. |

---

## 3. Findings by Severity

### 3.1 High

#### H1 — API keys surfaced as Clevis-generated CLI arguments

**OWASP**: A05 Injection-adjacent / A07 Authentication Failures (secret exposure)
**STRIDE**: Information Disclosure
**Confidence**: High (verified by reading `clevis/__init__.py::Factory.configure_parser`)

Clevis's `Factory.configure_parser` walks every leaf field of every nested dataclass and registers a `--{dotted-path}` argument. There is no `metadata`-based opt-out, no `secret` flag, and no field-name skip list. Consequently:

- `OllamaConfig.api_key` already yields `--backend-ollama-api-key` today (pre-existing).
- `OpenAIConfig.api_key` will yield `--backend-openai-api-key` (Phase 2).
- `AnthropicConfig.api_key` will yield `--backend-anthropic-api-key` (Phase 3).

Command-line arguments are readable by any process under the same user (and sometimes other users) via `ps auxe`, `/proc/<pid>/cmdline`, shell history (`~/.zsh_history`, `~/.bash_history`), process accounting, and CI log capture. Passing `--backend-openai-api-key sk-...` on the CLI is equivalent to publishing the key to local observers.

**Why the design amplifies this**: Q6 explicitly keeps `--backend-provider` and per-provider sub-config args as Clevis-generated. The design note (§9.2) states this ergonomics benefit is the reason for choosing the discriminated-dataclass shape over `typing.Union`. Without an api-key carve-out, the design bakes the leak into two new providers.

**Remediation** (Phase 1 pattern, Phase 2/3 application):
1. Introduce a field-metadata convention, e.g. `field(default=None, metadata={"secret": True, "help": "..."})`.
2. Patch or wrap `Factory.configure_parser` to skip fields whose `metadata["secret"]` is true. (Clevis is a dependency; either contribute an upstream option or filter `list_fields` in a thin Yoker-side subclass/wrapper.)
3. Document that API keys are accepted only via `~/.yoker.toml`, `./yoker.toml`, or env-var interpolation (`${OPENAI_API_KEY}`). The bootstrap wizard already uses `get_secret_input` for masked entry — that path is safe.
4. As a defence-in-depth measure, also scrub `api_key` values from any `repr()`/debug dumps of `Config` (override `__repr__` on the config dataclasses or use `repr=False` on the field).

**Design-note amendment required**: Yes. Q6 should be amended to: "Keep `--backend-provider` and per-provider sub-config args as Clevis-generated, **excluding secret fields** (`api_key`). Secret fields are configurable only via TOML or env-var interpolation."

### 3.2 Medium

#### M1 — `OpenAIConfig.base_url` / `AnthropicConfig.base_url` credential-leakage surface

**OWASP**: A05 SSRF / A04 Cryptographic Failures (credential transport)
**STRIDE**: Information Disclosure / Spoofing
**Confidence**: High

Q18 introduces `OpenAIConfig.base_url: str | None = None`, forwarded to `AsyncOpenAI(base_url=...)`. `AnthropicConfig.base_url` (§7.1) follows the same pattern. The OpenAI/Anthropic SDKs attach the api_key as `Authorization: Bearer <key>` to every request, including to the configured `base_url`.

Threat scenarios:
1. **Self-inflicted**: a user points `base_url` at an http endpoint (e.g., a local proxy) and the key is sent in cleartext.
2. **Project-config injection** (see M2): a cloned repository ships a `./yoker.toml` with `backend.openai.base_url = "https://attacker.example"` and no api_key. Clevis merges project config over user config, so the attacker's `base_url` wins while the user's `~/.yoker.toml` api_key is still loaded. Every request leaks the key to the attacker.
3. **Typo squatting**: a user misconfigures `base_url` to a look-alike domain.

The current `validate_url` (validators.py:18) only checks `result.scheme` and `result.netloc` are non-empty — it allows `http://`, `file://`, and URLs with embedded userinfo.

**Remediation**:
- **Phase 2/3 implementation**: tighten validation for backend `base_url` fields: require scheme in `("http", "https")` (warn on `http` when an api_key is set; reject `file`, `ftp`, etc.), and reject URLs with userinfo (`@` in the authority).
- **Design-note amendment**: Q18 should record: "`base_url` is a trust boundary. Yoker warns when `base_url` is non-https and an api_key is configured. Project-level `./yoker.toml` can override `base_url`; users should audit project configs before running Yoker in a project that sets backend connection fields."
- **Defence in depth**: when `base_url` is set and differs from the provider's official endpoint, log a one-time warning at startup (the `base_url` value, not the key).

#### M2 — Project-level config trust boundary

**OWASP**: A06 Insecure Design / A05 Injection (config-driven)
**STRIDE**: Tampering / Information Disclosure
**Confidence**: High (verified: `clevis/__init__.py` lines 728-732)

Clevis merges configs with project > user > defaults precedence. A `./yoker.toml` checked into a repository (or dropped into a working directory) can override `backend.provider`, `backend.openai.base_url`, `backend.anthropic.base_url`, or any other field. This is pre-existing (Ollama `base_url` is already overridable this way), but the combination of a per-provider `base_url` and a per-provider `api_key` from user config creates a clean credential-exfiltration path.

**Remediation**:
- **Design-note note** (non-blocking): add a sentence to §9.1 noting that `./yoker.toml` is a trust boundary and that running Yoker inside an untrusted project is a risk for backend credential interception.
- **Future hardening** (backlog): emit a startup warning when a backend `base_url` or `api_key` is set in project config, or when a project config sets `base_url` while the api_key comes from user config. This is out of scope for the three phases but should be tracked.
- **User docs**: the getting-started guide should advise users to inspect `./yoker.toml` before running Yoker in a cloned repo.

### 3.3 Low

#### L1 — `validate_url` accepts non-http(s) schemes and embedded userinfo

**Confidence**: High

`validate_url` (validators.py:18-33) uses `urlparse` and only checks `scheme` and `netloc` are non-empty. It accepts `file://`, `ftp://`, `gopher://`, and `https://user:pass@host`. Embedded userinfo would be logged by `create_client`'s `logger.info("async_ollama_client_initialized", host=base_url, ...)`.

**Remediation**: Add a `validate_http_url` variant for backend `base_url` fields that:
- Requires `scheme in ("http", "https")`.
- Rejects URLs where `result.username` or `result.password` is set.
- Optionally warns (does not reject) on `http` when an api_key is configured.

Apply to `OllamaConfig.base_url` (Phase 1, behaviour change — coordinate with owner), `OpenAIConfig.base_url` (Phase 2), `AnthropicConfig.base_url` (Phase 3).

#### L2 — `step_manual` prints config skeleton including any pre-existing api_key

**Confidence**: Medium

`step_manual` (steps.py) calls `render_config_toml(config)` and prints the result. If `config` already carries an `api_key` (e.g., user re-runs wizard with a partial config, or a caller passes a non-default `Config`), the key is echoed to the terminal. The wizard only runs when no `~/.yoker.toml` exists, so the default `Config()` path is safe (api_key is None). The risk is a non-default caller path.

**Remediation**: In `render_config_toml` or `step_manual`, redact fields whose `metadata["secret"]` is true (print `"<set in ~/.yoker.toml>"` instead of the value). This is a wizard-follow-up concern (§8 defers wizard changes), but the `metadata["secret"]` convention from H1 should be established in Phase 1 so the redaction is a one-liner later.

#### L3 — Logging hygiene in new backend constructors

**Confidence**: High

`create_client` (`_setup.py:24-33`) logs `host=base_url` and `auth="api_key"` (the literal string "api_key", not the value). This is correct. The design moves client construction into `OllamaBackend`/`OpenAIBackend`/`AnthropicBackend`. The same discipline must be applied in the new constructors.

**Remediation**: Add a non-functional requirement to the design note: "Backends MUST NOT log api_key values. `base_url` may be logged only after stripping any userinfo component." Enforce via code review in Phase 2/3.

### 3.4 Informational (confirmed benign / positive)

#### I1 — Subagent `with_model` fixes a pre-existing api_key-drop bug (positive)

Current `builtin/agent.py::_create_subagent` (lines 146-156) rebuilds `OllamaConfig` with only `base_url`, `model`, `timeout_seconds`, `parameters` — it omits `api_key`. A parent using Ollama's cloud API (api_key set) spawns a subagent that cannot authenticate. The design's `with_model(backend, model)` helper uses `dataclasses.replace(sub, model=model)`, which preserves `api_key` and every other field. This is a security/correctness improvement.

**Action**: add a regression test in Phase 1 asserting the subagent's active sub-config is identical to the parent's except for `model` (including `api_key`).

#### I2 — Multiple secrets in one 0o600 file (benign)

`write_config` (writer.py) opens with `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)` and then `os.chmod(path, 0o600)`. This applies to the whole file regardless of how many provider sub-configs carry api_keys. The union-aware `render_config_toml` omits `None` sub-configs, so a file with one provider's key still gets 0o600. No per-field or per-section exposure.

#### I3 — Config migration (benign)

Q8: no migration. Old `~/.yoker.toml` files remain valid; `provider` defaults to `"ollama"`; `openai`/`anthropic` default to `None` and are absent from the file. The app never re-writes `~/.yoker.toml` (only the wizard writes it, and only on first run). There is no window where a re-write could relax permissions. Existing Ollama api_keys are neither exposed nor lost.

#### I4 — Unknown-provider error message (benign)

`create_backend` raises `ConfigurationError(f"Unknown backend provider '{provider}'. Configured providers: {sorted(BACKENDS)}")`. `BACKENDS` is a `dict[str, Callable]`; `sorted(BACKENDS)` yields the key set — provider names only. No api_key, base_url, or config content is included. The Agent never starts on an unknown provider (no silent fallback). Confirmed safe.

#### I5 — TurnEndEvent stats (benign)

`TurnEndEvent` gains `input_tokens: int = 0` and `output_tokens: int = 0` (Q15). `UsageStats` carries integer token counts and durations. No prompt text, model output, tool-call arguments, or credentials are carried in stats. The UI reads whichever field is non-zero. Confirmed safe.

#### I6 — Web tools "No backend configured" (benign)

`websearch`/`webfetch` return `ToolResult(success=False, error="No backend configured for web search/fetch")` — a static string. `create_web_backends` (agent/_setup.py:78-127) returns an empty dict when `provider != "ollama"` or when no api_key is set; the api_key is never materialized into the error path. The design's decision to leave this failure as-is (Q16) introduces no new exposure.

---

## 4. Phase-Bound Recommendations

### 4.1 Phase 1 — Protocol + Ollama refactor (patterns to establish now)

| # | Recommendation | Type |
|---|---|---|
| P1-1 | Introduce `metadata={"secret": True}` on `OllamaConfig.api_key` and establish the convention that secret fields are excluded from CLI generation and redacted in skeletons. (Requires a Clevis-side or wrapper-side skip — coordinate with the api-architect on whether to patch Clevis or wrap `Factory`.) | **Design-note amendment** (H1) |
| P1-2 | Add `validate_http_url` (scheme in http/https, no userinfo) and apply to `OllamaConfig.base_url`. Warn (don't reject) on `http` when an api_key is set. | Implementation-time (L1) |
| P1-3 | Add a regression test asserting `with_model` preserves `api_key` and all other fields on the active sub-config (I1). | Implementation-time |
| P1-4 | Confirm `render_config_toml` union-awareness + `write_config` chmod 0o600 still cover the whole file when `openai`/`anthropic` sub-configs are present (I2). | Implementation-time (test) |
| P1-5 | Add a design-note NFR: "Backends MUST NOT log api_key values; `base_url` may be logged only after userinfo stripping." (L3) | **Design-note amendment** |

### 4.2 Phase 2 — OpenAI (when the provider is wired)

| # | Recommendation | Type |
|---|---|---|
| P2-1 | Apply the `metadata={"secret": True}` convention to `OpenAIConfig.api_key` and confirm it is excluded from CLI generation. | Implementation-time (depends on P1-1) |
| P2-2 | Apply `validate_http_url` to `OpenAIConfig.base_url`; warn on non-https when api_key is set (M1, L1). | Implementation-time |
| P2-3 | Record the `base_url` trust-boundary note in Q18 (M1, M2). | **Design-note amendment** |
| P2-4 | `OpenAIBackend` constructor must not log the api_key; log `base_url` only after stripping userinfo. | Implementation-time (L3) |

### 4.3 Phase 3 — Anthropic

| # | Recommendation | Type |
|---|---|---|
| P3-1 | Apply `metadata={"secret": True}` to `AnthropicConfig.api_key` (P1-1). | Implementation-time |
| P3-2 | Apply `validate_http_url` to `AnthropicConfig.base_url` (default `https://api.anthropic.com` is already https) (M1, L1). | Implementation-time |
| P3-3 | `AnthropicBackend` constructor must not log the api_key. | Implementation-time (L3) |

---

## 5. Items Requiring Owner Escalation (Design Decisions)

Two findings require an owner decision because they amend finalized Q-decisions:

1. **H1 — amend Q6** to exclude `api_key` (secret) fields from Clevis CLI generation. This is a security-driven change to an owner-approved ergonomics decision. The owner must decide between:
   - (a) Patching/wrapping Clevis to skip `metadata["secret"]` fields (recommended; preserves ergonomics for non-secret fields).
   - (b) Accepting the leak for parity with the current Ollama behaviour (not recommended; doubles the leak surface).
   - (c) Removing all per-provider sub-config args from CLI and keeping only `--backend-provider` (rejects the Q6 ergonomics rationale entirely).

2. **M1 — amend Q18** to record that `base_url` is a trust boundary and that Yoker requires/recommends https and rejects userinfo. This is a constraint on an owner-approved feature, not a rejection of it.

All other findings are implementation-time guidance for the python-developer or backlog items for the wizard follow-up (§8).

---

## 6. Positive Observations

- **chmod 0o600 via `os.open` + `os.chmod`** in `write_config` is the correct pattern (atomic permission setting, no race window where the file is world-readable). The design preserves it.
- **No silent fallback** on unknown provider (Q10) — the Agent refuses to start. This prevents accidentally routing a configured-for-Ollama session to a different provider.
- **`with_model` helper** fixes a pre-existing api_key-drop bug in subagent spawn (I1).
- **`create_client` logging discipline** (logs `auth="api_key"` literal, not the value) is the right pattern; the design note should carry it forward as an NFR (L3).
- **Bootstrap wizard uses `get_secret_input`** for masked API key entry — the collection path is safe; only the CLI-arg path (H1) leaks.
- **Web tools failure path** returns a static string with no config content (I6).
- **Tagged-union config shape** keeps validators on every sub-config, avoiding the "untyped dict" loss of validation (Q2 rationale is sound from a security perspective).

---

## 7. Scope Classification

| Finding | Classification | Action |
|---|---|---|
| H1 — API keys as CLI args | **Blocking** | Amend Q6 before Phase 2 lands a second leak surface; Phase 1 should establish the `secret` metadata convention. |
| M1 — base_url credential leakage | **Related** | Phase 2/3 implementation mitigation; Q18 design-note amendment. |
| M2 — Project-config trust boundary | **New** (backlog) | Design-note note now; startup-warning hardening as a separate follow-up. |
| L1 — validate_url tightening | **Related** | Phase 1 implementation for Ollama; Phase 2/3 for new configs. |
| L2 — step_manual skeleton redaction | **New** (wizard follow-up) | Tracked for §8 follow-up; depends on P1-1 `secret` metadata. |
| L3 — Backend logging NFR | **Related** | Design-note NFR; Phase 2/3 code review. |
| I1-I6 | Informational | Tests / confirmation only. |