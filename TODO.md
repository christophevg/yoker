# TODO

## Priority Overview

Bare-minimum 1.0.0 scope: 8 items + dogfooding gate. Full MBI-008 (Prompt Sets) and MBI-009 (Toolset Coverage) analyses are preserved at `analysis/mbi-prompt-sets.md` and `analysis/mbi-toolset-coverage.md` for post-1.0.0 implementation.

| Priority | Item | Status |
|----------|------|--------|
| **P1** | M.2 Default Tools Behavior | Done (PR #47) |
| **P1** | `make` tool | Done (PR #48) |
| **P1** | `read` offset/limit | Done (PR #49) |
| **P1** | `search` enhancements | Done (PR #50) |
| **P1** | `github` tool | Done (PR #51) |
| **P1** | Context overflow management (IP-12) | Done (PR #52) |
| **P1** | `protected_files` guardrail | Done (PR #53) |
| **P1** | MBI-005: Two Assistant Packages | In progress (external) |
| **P1** | Back-port RichUIHandler output | Done (PR #54) |
| **P1** | Context Persistence Bug Fix | Done (PR #55) |
| **P1** | C3 toolset evaluation | Open (ready to start) |
| **P1** | C3 agents/skills porting | Open (depends on evaluation) |
| **GATE** | Dogfooding Gate | Open |
| **HOLD** | L.1-L.9 Launch Preparation | On hold (wait for owner) |
| **DEFER** | Full MBI-008, full MBI-009 (rest), M.1, M.3, M.4, S.1, 7.1-7.3, other deferred items | Post-1.0.0 |

Completed work is recorded in git history. See `git log -- TODO.md` for prior task breakdowns.

---

## 1.0.0 Release Gate

All items below must be complete before declaring 1.0.0. Implementation order is suggested but not mandatory.

- [x] M.2: Default Tools Behavior (PR #47, 2026-07-20)
- [x] `make` tool (PR #48, 2026-07-21)
- [x] `read` offset/limit (PR #49, 2026-07-22)
- [x] `search` enhancements (PR #50, 2026-07-27)
- [x] `github` tool (PR #51, 2026-07-27)
- [x] Context overflow management (IP-12) (PR #52, 2026-07-27)
- [x] `protected_files` guardrail (PR #53, 2026-07-27)
- [ ] MBI-005: Two Assistant Packages (in progress externally — ../yoker-assistant done, ../yoker-writing-assistant started)
- [x] Back-port RichUIHandler output improvements to InteractiveUIHandler (PR #54, 2026-07-28)
- [x] Context Persistence Bug Fix (dogfooding-discovered) (PR #55, 2026-07-28)
- [ ] C3 toolset evaluation — audit C3 agent/skill definitions against yoker toolset
- [ ] C3 agents/skills porting — port definitions to match yoker toolset
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

- [x] **`make` tool — Makefile target execution** (PR #48, 2026-07-21)
  - `make(target, ctx, cwd, timeout_ms) -> ToolResult`
  - Target validation (reject shell metacharacters: `;`, `|`, `&`, `$`, backticks)
  - PathGuardrail on `cwd`
  - `subprocess.run(["make", target], ...)` — list args, no shell
  - Output truncation (default 100KB), timeout enforcement (default 5 min)
  - Agent can run `make check`, `make test`, etc.
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T1, Tier 1)
  - **Files:** `src/yoker/builtin/make.py` (new), `src/yoker/builtin/__init__.py` (manifest), `src/yoker/config/__init__.py` (MakeToolConfig)

### `read` offset/limit

- [x] **`read` offset/limit — efficient large-file reading** (PR #49, 2026-07-22)
  - Add `offset: int | None = None` and `limit: int | None = None` parameters
  - If `offset` provided, skip to that line (1-indexed); if `limit` provided, return at most that many lines
  - Return total line count in metadata; line numbers included when offset/limit used
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T2, Tier 1)
  - **Files:** `src/yoker/builtin/read.py` (modify), `tests/test_builtin/test_read.py` (extend)
  - **Note:** `package://` URL support from MBI-009 T2.2 is deferred to post-1.0.0

### `search` enhancements

- [x] **`search` enhancements — context lines, case-insensitive, file-type filter, count mode** (PR #50, 2026-07-27)
  - Add `case_insensitive: bool = False`, `context_before: int = 0`, `context_after: int = 0`
  - Add `include_pattern: str = ""`, `exclude_pattern: str = ""`, `count_only: bool = False`
  - Cap context lines at 20 to prevent output flooding
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T3, Tier 1)
  - **Files:** `src/yoker/builtin/search.py` (modify), `tests/test_builtin/test_search.py` (extend)

### `github` tool

- [x] **`github` tool — structured GitHub operations with subcommand blocking** (PR #51, 2026-07-27)
  - Read-only MVP: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view
  - `subprocess.run(["gh", ...], ...)` — list args, no shell
  - Operation allowlist (fixed enum, configurable per-project); subcommand blocking is the whole point
  - Timeout enforcement (default 30s); result count limits (max 100 for lists)
  - For PR workflow
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T7, Tier 2), `analysis/api-github-tool.md`, `analysis/security-github-tool.md`
  - **Files:** `src/yoker/builtin/github.py` (new), `src/yoker/builtin/__init__.py` (manifest)
  - **Delivered (PR #51):**
    - 9 read-only operations (repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view)
    - Hardcoded dispatch table — subcommand blocking is the security boundary
    - subprocess.Popen with list args (no shell), process-group kill on timeout
    - Argument injection defenses, output redaction, no env_vars, Windows platform gate
    - GitHubToolConfig: configurable per-project allowlist, timeout, max_results
    - Flat content_metadata shape
    - Post-merge feedback fix: eliminated duplicated _GITHUB_OPERATIONS via lazy import from yoker.builtin.github (single source of truth)

### Context overflow management (IP-12)

- [x] **Context overflow management — framework-level message truncation** (PR #52, 2026-07-27)
  - Add context size check before each request (framework mechanism: detection + triggering)
  - Framework default: drop oldest non-system messages when over threshold (keeping first user message with config injections)
  - If backend supports `context_management` API field (Anthropic), pass through thinking token clearing directive
  - If backend does not support it, strip thinking blocks from message history programmatically
  - Optional `on_context_overflow` hook for prompt sets that want custom truncation strategies
  - Without this, long sessions crash
  - **Source:** `analysis/mbi-prompt-sets.md` (MBI-008 T3.5, IP-12)
  - **Delivered (PR #52):**
    - Hybrid size detection (UsageStats.input_tokens primary, char/4 fallback — no new dependency)
    - Framework default: drop oldest non-system messages with setup-prefix invariant (all role=system + contiguous role=user scaffolding + first real user turn). Tool-call-pair-aware dropping
    - Backend protocol extension: supports_context_management + context_management kwarg. Anthropic passthrough. Non-supporting: thinking blocks stripped (always-on)
    - Optional on_context_overflow hook with output validation. Ships as None
    - ContextOverflowEvent audit trail
    - Two config fields: max_tokens (200,000) + overflow_keep_first_user (True)
    - Permanent truncation (Persisted rewrites JSONL)
    - Security fix during review: stale-token-estimate bug (one-line fix)
    - 50 new tests across 4 test files + 1 serialization round-trip test

### `protected_files` guardrail

- [x] **`protected_files` guardrail — soft guardrail for powerful mistakes** (PR #53, 2026-07-27)
  - When agent writes to a protected file (Makefile, pyproject.toml, tox.ini, etc.), show the user a diff and ask for permission
  - Only apply the change on approval
  - In non-interactive mode, block the change
  - This is a SOFT guardrail — it protects against powerful mistakes, not malicious agents
  - Default denylist: Makefile, makefile, GNUmakefile, Justfile, justfile, Taskfile.yml, pyproject.toml, tox.ini, setup.py, setup.cfg
  - Configurable per-project and per-user; empty list disables all protections
  - Applied to `write` and `update` tools via PathGuardrail
  - **Source:** `analysis/mbi-toolset-coverage.md` (MBI-009 T12, Tier 1)
  - **Files:** `src/yoker/config/__init__.py` (modify — PermissionsConfig), `src/yoker/tools/guardrails/path.py` (modify)
  - **Delivered (PR #53):**
    - 16-entry default denylist (Makefile, pyproject.toml, yoker.toml, .git/config, .git/hooks/*, .github/workflows/*.yml, uv.lock, poetry.lock, etc.)
    - fnmatch.fnmatchcase matching against relative path + basename
    - Interactive approve-on-diff flow (Option A): unified diff rendered → y/N prompt → apply on approval, block on denial (fail-safe)
    - Non-interactive (batch): simple block via PathGuardrail
    - Config: `permissions.protected_files` (tuple[str, ...]); empty tuple disables
    - `confirm_approval` as optional UIHandler Protocol method (like `agent_spawned`/`agent_finished`)
    - New APIs: `PathGuardrail.is_protected()`, `Agent._approval_handler`, `generate_diff()` shared helper
    - H1 fix during review: insert-operation diff corrected
    - CI fix: mocked PromptSession for TTY-less environments
    - 42 new tests (2197 passed), 22 files changed, ~1700 insertions
    - Review: all 6 stages passed (functional, api-architect, security, code-reviewer, testing, docs)

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

### Back-port RichUIHandler output improvements

- [x] **Back-port RichUIHandler from yoker-assistant to InteractiveUIHandler** (PR #54, 2026-07-28)
  - yoker-assistant has a custom RichUIHandler with improved UI/UX output experience (output-only, no input)
  - Back-port the output improvements to yoker's InteractiveUIHandler
  - Simplify InteractiveUIHandler: remove live/spinner aspects, make output more stable (stdout-like)
  - Options to evaluate:
    - a) Import into InteractiveUIHandler — existing input functionality simply not used (check if read-only use is possible without side effects)
    - b) New read-only UI handler + shared output logic with InteractiveUIHandler
  - RichUIHandler in yoker-assistant serves as inspiration
  - **Source:** Owner request 2026-07-28
  - **Files:** `../yoker-assistant/src/yoker_assistant/rich_ui.py` (inspiration), `src/yoker/ui/interactive.py` (modify)

### Context Persistence Bug Fix (dogfooding-discovered)

- [x] **Context Persistence Bug Fix** (PR #55, 2026-07-28)
  - Discovered during dogfooding: agent loop caused by tool results not being persisted to JSONL context
  - Root cause: `Persisted._persist_full_state` used `get_messages()` (excludes role=tool) instead of `get_context()` (includes all); assistant reasoning lost on tool-call turns; user messages duplicated
  - Fix: 3 bugs fixed across `src/yoker/context/{persisted,manager,wrapper,protocol}.py` and `src/yoker/core/_processing.py`; 8 behavior-asserting tests added
  - **Analysis:** `analysis/context-persistence-bug.md`

### C3 toolset evaluation

- [ ] **C3 toolset evaluation — audit C3 agent/skill definitions against yoker toolset**
  - Go through each agent and skill definition currently in C3
  - Check if the instructions are possible with the current yoker toolset
  - The answer will likely be "no" for many definitions
  - Result: a report stating:
    - Which tools/options on tools are missing
    - How instructions can be rewritten to fit the toolset
  - **Status:** Ready to start
  - **Source:** Owner request 2026-07-28
  - **Files:** `analysis/c3-toolset-evaluation.md` (new report)

### C3 agents/skills porting

- [ ] **C3 agents/skills porting — port definitions to match yoker toolset**
  - Port C3 agents and skills to work with Yoker
  - Include instructions to "ask for tools/more options" if the yoker toolset drastically limits the LLM
  - Open question: where to host yoker-specific vs claude-specific definitions
  - **Status:** To be discussed in detail (depends on C3 toolset evaluation)
  - **Source:** Owner request 2026-07-28
  - **Depends on:** C3 toolset evaluation

---

## Dogfooding Backlog

Improvements discovered while using Yoker to develop Yoker. These are quality-of-life and
workflow improvements that make the agent more effective during dogfooding sessions.

### High Priority

- [ ] **`make` tool: stdout swallowed on failure**
  - When `make` fails (exit code != 0), the `_processing.py` result formatting only surfaces `error` (which was stderr). stdout — where pytest, ruff, and mypy print their actual errors — is discarded. **Fix in progress:** `verbose` flag added + error now includes stdout+stderr on failure.
  - **Files:** `src/yoker/builtin/make.py`, `tests/test_tools/test_make.py`

- [ ] **`update` tool: exact match is brittle**
  - `old_string` must match exactly, including whitespace. Frequently fails with "Search text not found" or "ambiguous match" when file content has subtle differences from what the agent reconstructs.
  - **Proposals:** (a) line-number-based replace mode (`line_number` + `new_string`); (b) fuzzy/whitespace-insensitive matching option; (c) better error messages showing the closest match found.

- [ ] **`context/` directory in `.gitignore`**
  - Thousands of session JSONL files in `context/` are tracked by git and flood `list` output (2000 entries truncated). Should add `context/` to `.gitignore`.
  - **Files:** `.gitignore`

- [ ] **`search` tool: cannot search within a single file**
  - `search` only accepts directories. When the agent needs to find a line/pattern in a specific file, it must `read` the entire file and scan visually, wasting context window.
  - **Proposals:** (a) accept file paths in `search` and search just that file; (b) add a "find lines matching pattern" mode to `read`.

- [ ] **`git` tool: no `git restore` / `git stash`**
  - Cannot discard uncommitted changes to files (`git restore <file>`) or temporarily shelve work (`git stash`). When an edit goes wrong, the agent is stuck with bad content.
  - **Proposal:** Add `restore` operation (with file pathspecs like `add`) and `stash` operation (with `push`/`pop`/`list` sub-args).

### Medium Priority

- [ ] **`make` tool: success output is too verbose**
  - On success, `str(tool_result.result)` returns the full dict including all stdout (e.g., 2200 lines of "PASSED"). The agent rarely needs this. **Fix in progress:** `verbose=False` default returns only stderr on success (usually empty/warnings).
  - **Files:** `src/yoker/builtin/make.py`

- [ ] **`list` tool: noise from `context/` and other large directories**
  - Even with `context/` in `.gitignore`, `list` doesn't respect `.gitignore` — it still shows ignored files.
  - **Proposals:** (a) optionally respect `.gitignore` in `list`; (b) lower default `max_entries` from 2000 to ~200.

- [ ] **`protected_files` guardrail: no override for trusted dev sessions**
  - Writing to `yoker.toml`, `Makefile`, etc. is blocked in batch mode. No env var override exists for trusted development sessions.
  - **Proposal:** `YOKER_ALLOW_PROTECTED_WRITES=1` env var override.

- [ ] **`git` tool: no `git log` file-scoping guidance**
  - Already improved the schema description, but the `log` operation could also support file-scoped logs (e.g., `git log -- path/to/file`). Currently no way to see commit history for a specific file.

- [ ] **`update` tool: no line-number-based insert mode**
  - `insert` operation requires a `line_number`, but `replace` requires `old_string` exact match. A line-number-based replace (replace lines N-M with `new_string`) would be more robust.

### Low Priority

- [ ] **`search` tool: `include_pattern` only filters filenames, not directories**
  - Cannot search only within a specific subdirectory pattern. Must search the whole tree and filter results.
  - **Proposal:** Add `include_dirs` pattern or allow `path` to be a list of directories.

- [ ] **`read` tool: no binary file detection warning**
  - Reading a binary file returns garbled content. Should detect and warn/skip like `search` does.
  - **Proposal:** Add binary detection (check for NUL bytes in first 8KB) and return a clear error.

- [ ] **`git` tool: no `git tag` operation**
  - Cannot list, create, or delete tags. Useful for release workflows.
  - **Proposal:** Add `tag` operation with `list`, `create` (name + optional message), `delete` sub-args.

- [ ] **`git` tool: no `git merge` operation**
  - Cannot merge branches. Would complete the branch workflow (create branch → work → commit → switch back → merge).
  - **Proposal:** Add `merge` operation with branch name arg. Needs careful permission design.

- [ ] **`write` tool: `allow_overwrite` is project-level config, not per-call**
  - Agent cannot overwrite a file even when it explicitly wants to (e.g., rewriting a generated file). Must use `update` instead, which requires exact match.
  - **Proposal:** Per-call `overwrite: bool` flag on `write` tool.

- [ ] **`make` tool: no `make clean` or arbitrary target args**
  - Some Makefile targets need arguments that aren't env vars (e.g., `make clean V=1`). Currently only env_vars are supported.
  - **Proposal:** Consider `make_args` parameter for extra make arguments (with sanitization).

- [ ] **`github` tool: no way to create issues/PRs**
  - Currently read-only. For full dogfooding workflow, creating issues and PRs would be valuable.
  - **Proposal:** Add write operations (issue_create, pr_create) with approval model like git tool.

- [ ] **Context window: no visibility into remaining context budget**
  - Agent doesn't know how much context space is left before overflow truncation kicks in. Would help with planning large operations.
  - **Proposal:** Add context stats to `/context` command (tokens used / max_tokens).

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