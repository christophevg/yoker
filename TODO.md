# TODO

## Priority Overview

Bare-minimum 1.0.0 scope: 8 items + dogfooding gate. Full MBI-008 (Prompt Sets) and MBI-009 (Toolset Coverage) analyses are preserved at `analysis/mbi-prompt-sets.md` and `analysis/mbi-toolset-coverage.md` for post-1.0.0 implementation.

| Priority | Item | Status |
|----------|------|--------|
| **P1** | M.2 Default Tools Behavior | Done (PR #47) |
| **P1** | `make` tool | Open (from MBI-009 T1) |
| **P1** | `read` offset/limit | Open (from MBI-009 T2) |
| **P1** | `search` enhancements | Open (from MBI-009 T3) |
| **P1** | `github` tool | Open (from MBI-009 T7) |
| **P1** | Context overflow management (IP-12) | Open (from MBI-008 T3.5) |
| **P1** | `protected_files` guardrail | Open (from MBI-009 T12) |
| **P1** | MBI-005: Two Assistant Packages | Ready (deps met) |
| **GATE** | Dogfooding Gate | Open |
| **HOLD** | L.1-L.9 Launch Preparation | On hold (wait for owner) |
| **DEFER** | Full MBI-008, full MBI-009 (rest), M.1, M.3, M.4, S.1, 7.1-7.3, other deferred items | Post-1.0.0 |

Completed work is recorded in git history. See `git log -- TODO.md` for prior task breakdowns.

---

## 1.0.0 Release Gate

All items below must be complete before declaring 1.0.0. Implementation order is suggested but not mandatory.

- [x] M.2: Default Tools Behavior (PR #47, 2026-07-20)
- [ ] `make` tool (PR #48, pending review)
- [ ] `read` offset/limit
- [ ] `search` enhancements
- [ ] `github` tool
- [ ] Context overflow management (IP-12)
- [ ] `protected_files` guardrail
- [ ] MBI-005: Two Assistant Packages
- [ ] Dogfooding Gate: Last Yoker sessions done using Yoker itself (not Claude Code)

---

## Bare-Minimum 1.0.0 Tasks

### M.2: Default Tools Behavior

- [x] **M.2 Default Tools Behavior** (PR #47, 2026-07-20)
  - When agent has no explicit tools configuration, ALL tools should be available
  - Without this, agents have no tools
  - Update agent initialization logic
  - Write unit tests
  - **Source:** Maintenance task M.2

### `make` tool

- [ ] **`make` tool — Makefile target execution** (PR #48, pending review)
  - `make(target, ctx, cwd, timeout_ms) -> ToolResult`
  - Target validation (reject shell metacharacters: `;`, `|`, `&`, `$`, backticks)
  - PathGuardrail on `cwd`
  - `subprocess.run(["make", target], ...)` — list args, no shell
  - Output truncation (default 100KB), timeout enforcement (default 5 min)
  - Agent can run `make check`, `make test`, etc.
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T1, Tier 1)
  - **Files:** `src/yoker/builtin/make.py` (new), `src/yoker/builtin/__init__.py` (manifest), `src/yoker/config/__init__.py` (MakeToolConfig)

### `read` offset/limit

- [ ] **`read` offset/limit — efficient large-file reading**
  - Add `offset: int | None = None` and `limit: int | None = None` parameters
  - If `offset` provided, skip to that line (1-indexed); if `limit` provided, return at most that many lines
  - Return total line count in metadata; line numbers included when offset/limit used
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T2, Tier 1)
  - **Files:** `src/yoker/builtin/read.py` (modify), `tests/test_builtin/test_read.py` (extend)
  - **Note:** `package://` URL support from MBI-009 T2.2 is deferred to post-1.0.0

### `search` enhancements

- [ ] **`search` enhancements — context lines, case-insensitive, file-type filter, count mode**
  - Add `case_insensitive: bool = False`, `context_before: int = 0`, `context_after: int = 0`
  - Add `include_pattern: str = ""`, `exclude_pattern: str = ""`, `count_only: bool = False`
  - Cap context lines at 20 to prevent output flooding
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T3, Tier 1)
  - **Files:** `src/yoker/builtin/search.py` (modify), `tests/test_builtin/test_search.py` (extend)

### `github` tool

- [ ] **`github` tool — structured GitHub operations with subcommand blocking**
  - Read-only MVP: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view
  - `subprocess.run(["gh", ...], ...)` — list args, no shell
  - Operation allowlist (fixed enum, configurable per-project); subcommand blocking is the whole point
  - Timeout enforcement (default 30s); result count limits (max 100 for lists)
  - For PR workflow
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T7, Tier 2), `analysis/api-github-tool.md`, `analysis/security-github-tool.md`
  - **Files:** `src/yoker/builtin/github.py` (new), `src/yoker/builtin/__init__.py` (manifest)

### Context overflow management (IP-12)

- [ ] **Context overflow management — framework-level message truncation**
  - Add context size check before each request (framework mechanism: detection + triggering)
  - Framework default: drop oldest non-system messages when over threshold (keeping first user message with config injections)
  - If backend supports `context_management` API field (Anthropic), pass through thinking token clearing directive
  - If backend does not support it, strip thinking blocks from message history programmatically
  - Optional `on_context_overflow` hook for prompt sets that want custom truncation strategies
  - Without this, long sessions crash
  - **Source:** `analysis/mbi-prompt-sets.md` (MBI-008 T3.5, IP-12)

### `protected_files` guardrail

- [ ] **`protected_files` guardrail — soft guardrail for powerful mistakes**
  - When agent writes to a protected file (Makefile, pyproject.toml, tox.ini, etc.), show the user a diff and ask for permission
  - Only apply the change on approval
  - In non-interactive mode, block the change
  - This is a SOFT guardrail — it protects against powerful mistakes, not malicious agents
  - Default denylist: Makefile, makefile, GNUmakefile, Justfile, justfile, Taskfile.yml, pyproject.toml, tox.ini, setup.py, setup.cfg
  - Configurable per-project and per-user; empty list disables all protections
  - Applied to `write` and `update` tools via PathGuardrail
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T12, Tier 1)
  - **Files:** `src/yoker/config/__init__.py` (modify — PermissionsConfig), `src/yoker/tools/guardrails/path.py` (modify)

### MBI-005: Two Assistant Packages

- [ ] **[MBI-005] Create yoker-assistant package**
  - Personal assistant demonstrating setup check, custom looping logic (mail account integration), custom context builders, agent triggering, git integration, and mail responses
  - Users can run `uvx yoker-assistant`

- [ ] **[MBI-005] Create yoker-writing-assistant package**
  - Based on c3:writing-assistant skill
  - Demonstrates skill-based agent specialization
  - Shows how to package a skill-based agent as an executable
  - Users can run `uvx yoker-writing-assistant`

- [ ] **[MBI-005] Documentation for both packages**
  - Comprehensive documentation explaining architecture and patterns
  - Tutorial and examples
  - Both projects serve as reference implementations

**Acceptance Criteria:**
- [ ] Users can run `uvx yoker-assistant` successfully
- [ ] Users can run `uvx yoker-writing-assistant` successfully
- [ ] yoker-assistant demonstrates all yoker capabilities (looping, context, messaging, git)
- [ ] yoker-writing-assistant demonstrates skill-based agent specialization
- [ ] Documentation explains architecture and patterns for both
- [ ] Both projects serve as reference implementations

**Dependencies:** MBI-002 (Bootstrap) — DONE, MBI-003 (Python API) — DONE, MBI-004 (yoker Commands) — DONE

---

## Post-1.0.0

Full MBI-008 (Prompt Sets) and MBI-009 (Toolset Coverage) analyses are preserved at `analysis/mbi-prompt-sets.md` and `analysis/mbi-toolset-coverage.md` for post-1.0.0 implementation. The detailed task breakdowns for these MBIs have been removed from this file to keep it concise; refer to the analysis documents and `git log -- TODO.md` for the full breakdowns.

### MBI-008: Prompt Sets (full)

All 13 injection points, 2 prompt sets (Yoker default + Claude Code demo), Jinja2 templates, plugin integration. Only IP-12 (context overflow management) is pulled into 1.0.0.

**Analysis:** `analysis/mbi-prompt-sets.md`

### MBI-009: Toolset Coverage (rest)

Remaining tools and enhancements not pulled into 1.0.0:
- `pytest` tool (Tier 2)
- `file` tool — delete, copy, move, chmod, symlink (Tier 2)
- `askuserquestion` tool — static built-in, interactive (Tier 2)
- `lint` tool — consolidated ruff + mypy (Tier 2)
- `uv` tool — package management (Tier 2)
- `git` enhancement — add + checkout (Tier 3)
- `webfetch` enhancement — prompt parameter (Tier 3)
- `read` `package://` URL support (deferred from 1.0.0 slice)

**Analysis:** `analysis/mbi-toolset-coverage.md`

### Maintenance (post-1.0.0)

- [ ] **M.1 Rename yoker: plugin tools to builtin:**
  - Rename namespace from `yoker:` to `builtin:`
  - When listing tools (e.g. /tools), don't include the `builtin:` prefix
  - Update documentation

- [ ] **M.3 Namespace from Plugin/Package**
  - Allow namespace configuration derived from the plugin/package, not from skill/agent frontmatter
  - Update SkillLoader and AgentLoader
  - Write unit tests

- [ ] **M.4 Clean Up Duplicate Tests**
  - Review all tests for duplicates (e.g. tests/test_tools/test_base.py and tests/tools/test_base.py)
  - Consolidate duplicate tests
  - Ensure full coverage maintained

### S.1: Secure API Key Storage with Keyring

- [ ] **S.1 Secure API Key Storage with Keyring**
  - Use Python `keyring` library to securely store API keys instead of plain text in config files
  - During bootstrap wizard, use `keyring.set_password('yoker', '<provider>', api_key)` to store
  - On startup, retrieve with `keyring.get_password('yoker', '<provider>')`
  - Fallback to config file if keyring is unavailable or user opts out
  - Support all providers: Ollama, OpenAI, Anthropic, Gemini
  - **Reference:** User request 2026-07-01

### 7.1-7.3: Plugin Config Registration

- [ ] **7.1 Plugin Config Registration System Design**
  - Analyze Clevis `register_field` mechanism
  - Design plugin config registration API
  - Determine how plugins register their config schema
  - Design config discovery and validation flow
  - Document interaction with existing `WebGuardrailConfig` duplication
  - **Note:** This is a design task. Implementation will be a separate task.

- [ ] **7.2 ToolsConfig Dynamic Extension**
  - Change `ToolsConfig` from frozen to mutable dataclass
  - Implement `register_tool_config(name: str, config_class: type)` API
  - Support config field injection at runtime
  - Update existing hardcoded tool configs to use registration pattern
  - **Depends on:** 7.1
  - **Note:** Requires Clevis support or local workaround

- [ ] **7.3 Consolidate WebGuardrailConfig Classes**
  - Remove `WebGuardrailConfig` duplication between `tools/web/guardrail.py` and `config/__init__.py`
  - Create single unified `WebGuardrailConfig` class
  - **Depends on:** 7.2

### Other Deferred Items

- [ ] **3.4 Configurable Components Infrastructure**
  - Create base classes (SetMetadata, ComponentSet, ComponentLoader)
  - Implement resolution strategy (additional_dirs override set)
  - Create directory structure (prompts/sets/, skills/sets/, agents/sets/)
  - See `analysis/configurable-components-design.md` for design

- [ ] **3.6 Skills Sets Implementation**
  - Create skills/sets/default/ with core skills
  - Create skills/sets/minimal/ with essential skills
  - Implement SkillLoader with set support
  - **Depends on:** 3.4

- [ ] **3.7 Agent Sets Implementation**
  - Create agents/sets/default/ with main.md, researcher.md, developer.md, reviewer.md
  - Implement AgentLoader with set support
  - **Depends on:** 3.4

- [ ] **3.9 Lazy Loading Implementation**
  - Implement LazyToolRegistry (load tools on first use)
  - Implement LazySkillLoader (load skills on demand)
  - Create core tools set (Read, List, Search, Existence)
  - **Depends on:** 3.4, 3.5, 3.6, 3.7

- [ ] **2.13.1 Local WebSearch Backend**
  - Implement LocalWebSearchBackend using DDGS library
  - Note: OllamaWebSearchBackend is working, this is for offline-first

- [ ] **2.13.2 Local WebFetch Backend**
  - Implement LocalWebFetchBackend using httpx + Trafilatura
  - Note: OllamaWebFetchBackend is working, this is for full control

- [ ] **R.1 Hermes Agent Comparison**
  - Research Hermes Agent architecture and capabilities
  - Compare Hermes to Yoker architecture
  - Document findings in research folder

- [ ] **F.1 Multi-Agent Chat Room Demo**
  - **Note:** Handled by ../yoker-chat

- [ ] **MBI-007 7.8.7 ListAgents tool** — Deferred to a follow-up MBI (PR #43 Clarification 6)
  - Session-injected tool returning (name, status) for active agents

- [ ] **MBI-003 3.7 Auto-generate functions for detected skills/agents** — Deferred per design doc section 10

### Subsumed by MBI-008 / MBI-009

These items are retained for history. They are now covered by the new MBIs and should not be worked on independently.

- [x] **2.15 Python Tool** — Covered by MBI-009 (`read` `package://` URLs; `exec` deferred)
- [x] **2.16 Pytest Tool** — Covered by MBI-009 (T4: `pytest` tool)
- [x] **2.17 AskUserQuestion Tool** — Covered by MBI-009 (T6: `askuserquestion` tool)
- [x] **2.18 Development Workflow Tools** — Covered by MBI-009 (`make` tool + `lint` tool)
- [x] **2.19 GitHub Tool** — Covered by MBI-009 (T7: `github` tool)
- [x] **2.20 Add [start:stop] Arguments to Output-Heavy Tools** — Covered by MBI-009 (`read` offset/limit; `search` enhancements)
- [x] **2.22 uv Tool** — Covered by MBI-009 (T9: `uv` tool)
- [x] **3.5 Prompt Sets Implementation** — Covered by MBI-008
- [x] **3.8 Context Reminders Implementation** — Partially covered by MBI-008

---

## Launch Preparation: Public Announcement (On Hold)

**Source:** Email from Christophe, 2026-06-17
**Goal:** Prepare marketing materials and dedicated website for Yoker's public announcement.
**USP:** "Add LLM capabilities to your Python apps and modules without worrying about the agentic foundations. Agentic Functions."
**Status:** On hold — start only when owner signals implementation work is finalizing.

### Social Media Launch Plan

- [ ] **L.1 Storyboard of Publications**
  - Define ideal sequence to announce and introduce Yoker on social media
  - Predominantly LinkedIn and Instagram
  - Refer to the website in all publications
  - **Priority:** P1

- [ ] **L.2 Publication Timeline**
  - Prepare timeline for releasing articles, posts
  - Investigate: how many posts?
  - Investigate: how long between posts?
  - Investigate: repeating schedule?
  - **Depends on:** L.1
  - **Priority:** P1

### Website Research

- [ ] **L.3 Website Structure Research**
  - Research dedicated website structure for Yoker
  - **Priority:** P1

- [ ] **L.4 Website Examples and Framework Comparisons**
  - Research examples from other frameworks
  - Create comparison with other agent frameworks
  - **Priority:** P1

- [ ] **L.5 Strong Front Page**
  - Research and design a strong front page example
  - **Priority:** P1

- [ ] **L.6 Clear Getting Started Guide**
  - Research and design clear getting started guide
  - **Priority:** P1

- [ ] **L.7 Best Practices Research**
  - Learn from good examples, find best practices for developer tool websites
  - **Priority:** P2

- [ ] **L.8 Look and Feel Research**
  - Research look and feel for the website
  - **Priority:** P2

- [ ] **L.9 Low Entry / Bootstrapping Showcase**
  - Show low entry barrier and good support for bootstrapping
  - Highlight free Ollama account support
  - **Priority:** P2