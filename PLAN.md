# Plan

This file contains the Intake Backlog with Minimal Business Increments (MBIs).

## Unsorted MBIs

Quick captures for MBI ideas. These are raw requests that haven't been analyzed yet.

[None at this time]

---

## Active MBI

The MBI currently being implemented. Only one Active MBI at a time.

None — bare-minimum 1.0.0 scope defined, ready to implement.

---

## 1.0.0 Release Gate

All items below must be complete before declaring 1.0.0. The full MBI-008 (Prompt Sets) and MBI-009 (Toolset Coverage) analyses are preserved as post-1.0.0 references at `analysis/mbi-prompt-sets.md` and `analysis/mbi-toolset-coverage.md`. Only the critical slices listed here are pulled forward into the minimal 1.0.0 scope.

### 1.0.0 Scope (in implementation order)

1. **M.2: Default Tools Behavior** — all tools available when no explicit config. Without this, agents have no tools.
2. **`make` tool** — Makefile target execution. Agent can run `make check`, `make test`, etc. (from MBI-009 Tier 1)
3. **`read` offset/limit** — read large files efficiently with offset and limit parameters. (from MBI-009 Tier 1)
4. **`search` enhancements** — context lines, case-insensitive, file-type filter, count mode. (from MBI-009 Tier 1)
5. **`github` tool** — structured GitHub operations with subcommand blocking. For PR workflow. (from MBI-009 Tier 2)
6. **Context overflow management** (IP-12 from MBI-008) — framework-level message truncation when context fills up. Without this, long sessions crash.
7. **`protected_files` guardrail** — when agent writes to a protected file (Makefile, pyproject.toml, tox.ini, etc.), show the user a diff and ask for permission. Only apply on approval. In non-interactive mode, block the change. This is a SOFT guardrail — it protects against powerful mistakes, not malicious agents. (from MBI-009 Tier 1)
8. **MBI-005: Two Assistant Packages** — yoker-assistant + yoker-writing-assistant (based on c3:writing-assistant). Showcase capabilities.

### Dogfooding Gate

- [ ] Last Yoker development sessions must be doable with Yoker itself (not Claude Code)

---

## Backlog

### Post-1.0.0

Items deferred until after the 1.0.0 release.

#### MBI-008: Prompt Sets (full)

**Goal:** Extract all prompt generation from the codebase into external Jinja2 template files (prompt sets). Define 13 injection points (7 existing + 6 new). Ship a Yoker default set (minimal, byte-identical to current behavior) and a Claude Code demo set (mimics Claude Code's injection behavior). Prompt sets become the fourth plugin component type alongside tools, skills, and agents.

**Value:** Makes prompts independent of the codebase (no code changes to modify prompts), swappable at configuration time, distributable as part of plugins/packages, and versionable/customizable per project. The Claude Code demo set demonstrates full compatibility with Claude Code's context injection behavior.

**Status:** Ready (post-1.0.0)

**Analysis source of truth:** `analysis/mbi-prompt-sets.md` (finalized — all 6 design decisions D1-D6 resolved, owner-approved)

**Note:** Only IP-12 (context overflow management) is pulled into 1.0.0. The rest is post-1.0.0.

**Scope:**
- 13 injection points (IP-1 through IP-13): 7 existing (system prompt, skill discovery/invocation, tool descriptions, tool param descriptions, agent/send_message tool descriptions) + 6 new (session start, env info, file change, tool result, context overflow, context update)
- 6 implementation phases: Infrastructure, Externalize Existing, New Hooks, Claude Code Set, Plugin Integration, Testing/Docs
- Two prompt sets: Yoker default (minimal, byte-identical) + Claude Code demo (all 13 hooks active)
- Jinja2 runtime dependency
- `[prompts]` config section (`set`, `set_path`)
- `prompt_sets` field on `PluginManifest`

**Acceptance Criteria:**
- [ ] Jinja2 is a runtime dependency; prompt set loader and renderer work
- [ ] 13 injection points defined as framework hooks with documented template variables
- [ ] All existing hardcoded prompt strings externalized into default prompt set templates
- [ ] Default prompt set produces byte-identical output to current hardcoded behavior
- [ ] `[prompts]` config section allows selecting a prompt set by name or path
- [ ] `PluginManifest` supports `prompt_sets`; plugins can declare prompt sets
- [ ] Claude Code prompt set implements all 13 hooks with CC-matching templates
- [ ] Unit tests for each template in both prompt sets
- [ ] Integration tests verify prompt set switching changes context without code changes
- [ ] Framework provides default context overflow management without requiring a template

**Dependencies:** MBI-001 (Plugin System) — DONE, MBI-007 (Session) — DONE

---

#### MBI-009: Toolset Coverage (rest)

**Goal:** Ensure Yoker's built-in toolset provides ~97% coverage of a typical agentic development workload. 7 new tools + 4 enhancements + `protected_files` guardrail.

**Value:** Without a comprehensive toolset, agents stall on routine tasks (running tests, executing linters, managing files) and the user must intervene with manual shell commands. Research showed 39.7% of all tool calls in a real development session were shell commands — the single largest gap.

**Status:** Ready (post-1.0.0 for remaining items)

**Analysis source of truth:** `analysis/mbi-toolset-coverage.md` (finalized — revision 5, all 11 open questions resolved, owner-approved)

**Design principle:** Specialized, controllable tools with fixed operation enums — NOT a general-purpose shell. Each tool uses `subprocess.run` with list args (no `shell=True`).

**Pulled into 1.0.0:** `make` tool, `read` offset/limit, `search` enhancements, `github` tool, `protected_files` guardrail.

**Post-1.0.0 scope (rest):**
- `pytest` tool (Tier 2)
- `file` tool — delete, copy, move, chmod, symlink (Tier 2)
- `askuserquestion` tool — static built-in, interactive (Tier 2)
- `lint` tool — consolidated ruff + mypy (Tier 2)
- `uv` tool — package management (Tier 2)
- `git` enhancement — add + checkout (Tier 3)
- `webfetch` enhancement — prompt parameter (Tier 3)
- `read` `package://` URL support (Tier 1, deferred from 1.0.0 slice)

**Dependencies:** — (no blocking MBIs)

---

#### Maintenance: M.1, M.3, M.4

**Goal:** Three maintenance tasks deferred to post-1.0.0.

**Status:** Open (post-1.0.0)

**Tasks:**
- [ ] M.1: Rename `yoker:` plugin tools namespace to `builtin:`; hide `builtin:` prefix in `/tools` listing
- [ ] M.3: Namespace from plugin/package, not frontmatter — allow namespace configuration derived from the plugin/package, not from skill/agent frontmatter
- [ ] M.4: Clean up duplicate tests (e.g., `tests/test_tools/test_base.py` vs `tests/tools/test_base.py`)

**Dependencies:** —

---

#### S.1: Secure API Key Storage with Keyring

**Goal:** Use Python `keyring` library to securely store API keys instead of plain text in config files. During bootstrap wizard, use `keyring.set_password('yoker', '<provider>', api_key)` to store. On startup, retrieve with `keyring.get_password('yoker', '<provider>')`. Fallback to config file if keyring is unavailable or user opts out. Support all providers: Ollama, OpenAI, Anthropic, Gemini.

**Value:** Eliminates API keys from plain-text config files, reducing the risk of accidental exposure via dotfile sharing, backup systems, or version control.

**Status:** Open (post-1.0.0)

**Dependencies:** —

---

#### 7.1-7.3: Plugin Config Registration

**Goal:** Enable plugins to register configuration fields dynamically, allowing tool-specific settings without hardcoding in ToolsConfig. This unblocks the `WebGuardrailConfig` consolidation and enables plugin-provided tools to have their own config sections.

**Value:** Plugins added via `--with` need to register their own configuration fields (e.g., `[tools.pkgq]` settings). Without this, plugin tools cannot be configured per-project. Also eliminates the `WebGuardrailConfig` duplication between `tools/web/guardrail.py` and `config/__init__.py`.

**Status:** Backlog (post-1.0.0)

**Tasks:**
- [ ] 7.1: Plugin Config Registration System Design (analyze Clevis `register_field`, design API, document flow)
- [ ] 7.2: ToolsConfig Dynamic Extension (change from frozen to mutable, implement `register_tool_config` API)
- [ ] 7.3: Consolidate `WebGuardrailConfig` classes (eliminate duplication using new registration pattern)

**Dependencies:** Clevis `register_field` mechanism (may require upstream support)

---

#### Other Deferred Items

- 3.4 Configurable Components Infrastructure (base classes, resolution strategy, directory structure)
- 3.6 Skills Sets (skills/sets/default/, skills/sets/minimal/, SkillLoader with set support)
- 3.7 Agent Sets (agents/sets/default/, agents/sets/research/, AgentLoader with set support)
- 3.9 Lazy Loading (LazyToolRegistry, LazySkillLoader, core tools set)
- 2.13.1 Local WebSearch Backend (DDGS library, offline-first)
- 2.13.2 Local WebFetch Backend (httpx + Trafilatura, full control)
- R.1 Hermes Agent Comparison (research Hermes architecture, compare to Yoker)
- F.1 Multi-Agent Chat Room Demo (handled by ../yoker-chat)
- MBI-007 7.8.7 ListAgents tool (Session-injected tool for agent discovery)
- MBI-003 3.7 Auto-generate functions for detected skills/agents (deferred per design doc section 10)

### On Hold

Items that start only when the owner signals implementation work is finalizing.

#### L.1-L.9: Launch Preparation

**Goal:** Prepare marketing materials and dedicated website for Yoker's public announcement.

**USP:** "Add LLM capabilities to your Python apps and modules without worrying about the agentic foundations. Agentic Functions."

**Status:** On hold — start only when owner signals implementation work is finalizing.

**Tasks:**
- [ ] L.1 Storyboard of Publications
- [ ] L.2 Publication Timeline (depends on L.1)
- [ ] L.3 Website Structure Research
- [ ] L.4 Website Examples and Framework Comparisons
- [ ] L.5 Strong Front Page
- [ ] L.6 Clear Getting Started Guide
- [ ] L.7 Best Practices Research
- [ ] L.8 Look and Feel Research
- [ ] L.9 Low Entry / Bootstrapping Showcase

---

## Done

Completed MBIs.

### MBI-004: yoker Commands (Completed: 2026-07-15)

**Goal:** Users can use yoker from the command line with a complete CLI: `yoker chat`, `yoker run`, `yoker loop`, `yoker init`, `yoker config`, `yoker container`. The flagship capability is `yoker run`, which loads a source (module, GitHub URL, folder, zip) containing an extended yoker manifest (agent selection + initial prompt) and runs it as a "yoker-based agentic executable package."

**Value:** Command-line interface is essential for developer workflows and automation. `yoker run` transforms yoker from an interactive tool into a runtime for agentic packages — any plugin can become an executable agent with a single command. Completes the yoker product for first release.

**Status:** Done

**Design source of truth:** `analysis/mbi-004-yoker-commands.md`

**Achieved:** All subcommands implemented and working end-to-end. `chat` (default, backward compatible), `run` (flagship — loads source via two-phase resolution with trust gate, applies manifest config overrides, runs agent non-interactively), `init`, `config`, `loop`, `inspect`, `container`. Extended manifest supports both Python `__YOKER_MANIFEST__` and file-based `agent.toml` with `[run]`/`[plugin]` sections and config-override layering (base TOML -> manifest -> CLI). Source resolution supports module names, GitHub URLs (HTTPS-only, SSRF-checked), folder paths, and zip files (safe extraction with zip-bomb guards). Clevis 0.7.0 upgrade replaced internal-API workarounds with native public API.

**Merged via:** PR #46 (2026-07-15).

---

### MBI-006: Multi-Provider Backend Support (Completed: 2026-07-01)

**Goal:** Make Yoker provider-neutral at the model layer. A single `ModelBackend` Protocol abstracts chat streaming; the Agent talks to a backend instance, not to `ollama.AsyncClient` directly. Ollama ships via a native SDK backend (`OllamaBackend`); all other providers (OpenAI, Anthropic, Gemini, and 100+ others) ship via a unified `LitellmBackend` wrapping the `litellm` library.

**Value:** Removes vendor lock-in at the model layer. Users can choose Ollama (local/free), OpenAI, Anthropic, or any litellm-supported provider by switching a single config field, without changing their agentic workflows. Establishes the abstraction seam that lets future providers land without touching the Agent hot path.

**Status:** Done

**Design source of truth:** `analysis/multi-provider-backend-design.md` (Phase 1) and `analysis/dual-backend-architecture.md` (Phase 2). Functional counterpart: `analysis/functional-multi-provider-backend.md`.

**Achieved:** Dual backend architecture landed in master. Phase 1 introduced `ModelBackend` Protocol, `ChatChunk` neutral stream type, `OllamaBackend` (native SDK adapter), `create_backend()` factory, and the `with_model()` helper (PR #36). Phase 2 added `LitellmBackend` wrapping the `litellm` library for OpenAI, Anthropic, and 100+ providers, with stream translation, `reasoning_content` mapping, provider-specific parameter mapping, and base_url trust boundary (PR #37). The original three-phase plan (separate OpenAI/Anthropic backends) was superseded by the unified dual-backend approach. Config schema is a tagged union; old `~/.yoker.toml` files remain valid without migration. Subagent spawn is provider-agnostic.

**Merged via:** PR #36 (Phase 1, 2026-06-29) and PR #37 (Phase 2, 2026-07-01).

---

### MBI-002: Bootstrap (Completed: 2026-07-01)

**Goal:** Users run `yoker` for the first time and are guided through: backend selection, model selection, Ollama account creation (with free tier), and config file creation. After completing bootstrap, any package using yoker can run immediately.

**Value:** Lowers barrier to entry. Users can try yoker with minimal friction, increasing adoption and reducing support questions. A few free cloud model cycles should be enough to test a small agentic workflow.

**Status:** Done

**Achieved:** Bootstrap wizard landed in master (`src/yoker/bootstrap/`). `config_provided()` detection in `detect.py` triggers the wizard when no config source is present. Interactive `BootstrapWizard` walks users through backend intro, Ollama account creation guidance, connection-method selection (local app vs API key), and model selection (curated list + free text, no network call). Config writer in `src/yoker/config/writer.py` (annotation-driven, generic) writes `~/.yoker.toml` with `chmod 600`. Non-interactive mode prints stderr warning and exits non-zero. Library mode (`Agent(config=...)`) skips bootstrap. Default model changed to `gemini-3-flash-preview:cloud` (cloud, no download). Bootstrap continues into the normal session after writing config (no rerun needed). Documentation in `docs/guides/getting-started.md`.

**Merged via:** PR #35 (2026-07-01).

---

### ContextManager Refactor (Completed: 2026-07-06)

**Goal:** Refactor the `ContextManager` construct to clean up its responsibilities and align it with the Session-based multi-agent architecture landed in MBI-007. Reduce coupling, clarify ownership of context lifecycle, and prepare the primitive for the workflow layer that MBI-003 (Python API) builds on.

**Value:** Removes accumulated complexity and dual-ownership patterns between `Agent` and `Session` around context management. Makes context handling a coherent single-responsibility primitive, consistent with the post-MBI-007 architecture where `Session` owns team-level concerns and `Agent` is a single-agent chat loop. Prerequisite-quality cleanup before MBI-003 exposes the API to external developers.

**Status:** Done

**Design source of truth:** `analysis/context-manager-refactor-design.md`.

**Achieved:** Replaced the `UserList`-based `ContextManager` with a Protocol + Wrapper architecture. Introduced `ContextManager` Protocol, `BasicContextManager`, `PersistedContextManager`, and `ContextWrapper`. Cleaned up responsibilities and aligned context lifecycle ownership with the Session-based multi-agent architecture.

**Merged via:** PR #44 (2026-07-06).

---

### MBI-007: Session (Completed: 2026-07-06)

**Goal:** Introduce a `Session` construct that manages a team of agents: their lifecycle (create, spawn, monitor, cancel), their registry, recursion depth tracking, event aggregation, and inter-agent messaging. Reduce `Agent` to a single-agent chat loop with no orchestration responsibilities. Establish the primitive that MBI-003 (Python API) builds its workflow layer on top of.

**Value:** Unlocks true multi-agent workflows (fan-out, pipelines, long-lived teams, inter-agent messaging) that were not expressible before. Cleans up `Agent` to a single-responsibility primitive. Makes sub-agents visible via event aggregation, serving Yoker's transparency philosophy. Makes the "Recursive Composition: True Sub-Agents" claim in `docs/rationale.md` fully real.

**Status:** Done

**Design source of truth:** `analysis/session-concept-analysis.md` (finalized, owner-approved — all 10 decisions in section 7 resolved via PR #42; clarifications rounds 1 & 2 resolved via PR #43).

**Achieved:** `Session` async context manager landed in master; `AgentRegistry` moved from `Agent` to `Session`; recursion depth tracking moved to `Session`; `builtin/agent.py` reworked to `SpawnAgent` (Session-injected); `SendMessage` Session-injected tool; session-level event types (`SESSION_START/END`, `AGENT_SPAWNED/FINISHED`, `AGENT_MESSAGE`); `EventRecorder` session-scoped; `UIBridge` registered on `Session`; `__main__.py` constructs `Session`, `run_session` renamed to `run_repl`; `[session]` config section; `ToolContext` carries `session`; backend factory + sharing in `Session`. `ListAgents` deferred to a follow-up MBI per PR #43 Clarification 6.

**Merged via:** PR #43 (2026-07-06).

---

### MBI-003: Python API (Completed: 2026-07-06)

**Goal:** Python developers can easily integrate agentic (sub-)workflows in Python function calls, with a clean utility API wrapping the current class-oriented architecture.

**Value:** Makes yoker developer-friendly, removing all hurdles to quick integration. Developers can use yoker without understanding internal classes.

**Status:** Done (merged 2026-07-06). Thin single-module facade (`yoker/api.py`): `process`, `do`, `agent`, `session`, `run_sync`. No private helpers remain.

**Design source of truth:** `analysis/mbi-003-python-api-design.md` (three-layer utility API: Layer 1 wrappers over existing classes, Layer 2 `execute_skill` one-shot, Layer 3 `yoker.session()` workflow primitive built on the real `Session`).

**Note:** The optional auto-generate feature (3.7) is deferred to a follow-up MBI (post-1.0.0).

---

### MBI-001: Package Plugin System (Completed: 2026-06-25)

**Goal:** Users can extend Yoker with tools and skills from Python packages via `yoker --with <package>`, and invoke them via `/skill-name` commands or agent tool calls.

**Value:** Enables reusable, shareable Yoker extensions without modifying core codebase. Users can `uvx --with pkgq yoker --with pkgq` and invoke `/pkgq:create`.

**Status:** Done

**Final Validation:**
- [x] Validate plugin system with pkgq project
- [x] Publish release to PyPI

**Achieved:** All core components implemented (Skill Infrastructure, Slash Commands, Skill Tool, Package Plugin Discovery, CLI --with Argument, UI Separation, Error Handling, Documentation, Testing). Validated with pkgq project; v0.6.0 released to PyPI (2026-07-03).