# TODO

## Priority Overview

| Priority | MBI/Task | Status |
|----------|----------|--------|
| **P1** | MBI-008: Prompt Sets | Ready (analysis complete) |
| **P1** | MBI-009: Toolset Coverage for 1.0.0 | Ready (analysis complete) |
| **P1** | M.1 Rename yoker: to builtin: | Open |
| **P1** | M.2 Default Tools Behavior | Open |
| **P2** | MBI-005: Assistant Integration (2 packages) | Backlog (deps met) |
| **P2** | M.3 Namespace from Plugin/Package | Open |
| **P2** | S.1 Secure API Key Storage | Open |
| **P2** | 7.1-7.3 Plugin Config Registration | Backlog |
| **P3** | M.4 Clean Up Duplicate Tests | Open |
| **HOLD** | L.1-L.9 Launch Preparation | On hold (wait for owner) |
| **DEFER** | 3.4, 3.6, 3.7, 3.9, 2.13.x, R.1, F.1, deferred items | Post-1.0.0 |

Completed work is recorded in git history. See `git log -- TODO.md` for prior task breakdowns.

---

## 1.0.0 Release Gate

All items below must be complete before declaring 1.0.0.

- [ ] MBI-008: Prompt Sets (13 injection points, 2 prompt sets, Jinja2 templates)
- [ ] MBI-009: Toolset Coverage (7 new tools + 4 enhancements + protected_files guardrail)
- [ ] M.1: Rename yoker: to builtin:
- [ ] M.2: Default Tools Behavior
- [ ] M.3: Namespace from Plugin/Package
- [ ] M.4: Clean Up Duplicate Tests
- [ ] S.1: Secure API Key Storage with Keyring
- [ ] MBI-005: Two Assistant Packages (yoker-assistant + yoker-writing-assistant)
- [ ] 7.1-7.3: Plugin Config Registration
- [ ] Dogfooding Gate: Last Yoker sessions done using Yoker itself (not Claude Code)

---

## MBI-008: Prompt Sets

**Goal:** Extract all prompt generation from the codebase into external Jinja2 template files (prompt sets). 13 injection points, 2 prompt sets (Yoker default + Claude Code demo), 6 implementation phases.

**Design source of truth:** `analysis/mbi-prompt-sets.md` (finalized — all 6 design decisions D1-D6 resolved, owner-approved)

**Milestone:** All prompts are external Jinja2 templates; switching prompt sets changes injected context without code changes; Claude Code demo set demonstrates full CC compatibility.

### Phase 1: Infrastructure

- [ ] **[MBI-008] T1.1 Add Jinja2 dependency and prompt set module skeleton**
  - Add `jinja2` to `pyproject.toml` dependencies
  - Create `src/yoker/prompts/` module: `__init__.py`, `loader.py`, `schema.py`
  - Define `PromptSet` dataclass (metadata + template map), `PromptSetLoader` class
  - No behavior change yet — just the infrastructure
  - **Satisfies:** R1, R2, R5

- [ ] **[MBI-008] T1.2 Add `[prompts]` config section**
  - Add `PromptsConfig` dataclass to `config/__init__.py` with `set` and `set_path` fields
  - Add `prompts: PromptsConfig` to `Config`
  - Wire into Clevis config schema
  - **Satisfies:** R13, R14

- [ ] **[MBI-008] T1.3 Create default prompt set directory**
  - Create `src/yoker/prompts/sets/default/` with `manifest.toml`
  - Add empty template files (filled in Phase 2)
  - **Satisfies:** R19

### Phase 2: Externalize Existing Injection Points

- [ ] **[MBI-008] T2.1 Externalize IP-1 (system prompt)**
  - Create `system_prompt.j2` in the default set, replicating `SimpleContextManager.system_prompt` and `environment_reminder` output
  - Modify `SimpleContextManager.setup_initial_context()` to call the prompt set loader
  - Verify byte-identical output
  - **Satisfies:** R8

- [ ] **[MBI-008] T2.2 Externalize IP-2 (skill discovery)**
  - Create `skill_discovery.j2` replicating `format_discovery_block()` output
  - Modify `BaseContextManager.add_skill_discovery_block()` to call the prompt set
  - Verify byte-identical output
  - **Satisfies:** R9

- [ ] **[MBI-008] T2.3 Externalize IP-3 (skill invocation)**
  - Create `skill_invocation.j2` replicating `format_invocation_block()` output
  - Modify `Agent.inject_skill_context()` and `skill` tool to call the prompt set
  - Verify byte-identical output
  - **Satisfies:** R9

- [ ] **[MBI-008] T2.4 Externalize IP-4, IP-5 (tool descriptions)**
  - Create `tool_description.j2` (passthrough) and `tool_param_desc.j2` (passthrough) in default set
  - Add enrichment step in `ToolRegistry.get_schemas()` that calls the prompt set
  - Verify byte-identical output with default set
  - **Satisfies:** R10

- [ ] **[MBI-008] T2.5 Externalize IP-6, IP-7 (session tool descriptions)**
  - Create `agent_tool_desc.j2` and `send_message_desc.j2` in default set
  - Modify `make_spawn_agent_tool()` and `make_send_message_tool()` to call the prompt set
  - Verify byte-identical output
  - **Satisfies:** R11

### Phase 3: New Injection Point Hooks

- [ ] **[MBI-008] T3.1 Implement IP-8 (session start)**
  - Add hook call site in Session or Agent first-turn
  - Gather config_files, current_date, cwd, git_status variables
  - No-op for default set; template exists for Claude Code set
  - **Satisfies:** R12

- [ ] **[MBI-008] T3.2 Implement IP-9 (env info)**
  - Add hook call site for agents/skills listing injection
  - Gather available_agents, available_skills variables
  - No-op for default set
  - **Satisfies:** R12

- [ ] **[MBI-008] T3.3 Implement IP-10 (file change)**
  - Add hook call site for file change events
  - Gather file_path, change_type variables
  - Default set: minimal one-line notification (D2 approved)
  - Claude Code set: full file modification notice
  - **Satisfies:** R12

- [ ] **[MBI-008] T3.4 Implement IP-11 (tool result post-processing)**
  - Add hook call site in `_execute_single_tool_call()` after tool result
  - Gather tool_name, tool_result, is_truncated, total_lines variables
  - No-op for default set
  - **Satisfies:** R12

- [ ] **[MBI-008] T3.5 Implement IP-12 (context overflow)**
  - Add context size check before each request (framework mechanism: detection + triggering)
  - Framework default: drop oldest non-system messages when over threshold (keeping first user message with config injections)
  - If backend supports `context_management` API field (Anthropic), pass through thinking token clearing directive
  - If backend does not support it, strip thinking blocks from message history programmatically
  - Optional `on_context_overflow` hook for prompt sets that want custom truncation strategies
  - **Satisfies:** R12, R12a

- [ ] **[MBI-008] T3.6 Implement IP-13 (context update)**
  - Add state change detection (config files, skills, agents)
  - Add hook call site with changed_state, new_content
  - No-op for default set
  - **Satisfies:** R12

### Phase 4: Claude Code Prompt Set

- [ ] **[MBI-008] T4.1 Create Claude Code prompt set structure**
  - Create `src/yoker/prompts/sets/claude-code/` with `manifest.toml`
  - Reference all 13 template files
  - **Satisfies:** R20

- [ ] **[MBI-008] T4.2 Implement Claude Code system prompt template (IP-1)**
  - Add git status, env block, model name, subagent permission/notes
  - Use research branch output as reference
  - **Satisfies:** R20

- [ ] **[MBI-008] T4.3 Implement Claude Code skill templates (IP-2, IP-3)**
  - Match CC skill listing format with triggers and usage hints
  - Match CC skill invocation format
  - **Satisfies:** R20

- [ ] **[MBI-008] T4.4 Implement Claude Code tool description templates (IP-4, IP-5)**
  - Enriched descriptions with behavioral guidance, safety rules
  - Same descriptions for all agents (Yoker's equal-agents architecture — D4)
  - **Satisfies:** R20, R12b

- [ ] **[MBI-008] T4.5 Implement Claude Code session tool templates (IP-6, IP-7)**
  - Add spawn guidance and communication patterns
  - **Satisfies:** R20

- [ ] **[MBI-008] T4.6 Implement Claude Code session start template (IP-8)**
  - Config files + currentDate in `<system-reminder>` format
  - Use research branch reference
  - **Satisfies:** R20

- [ ] **[MBI-008] T4.7 Implement Claude Code env_info, file_change, tool_result, context templates (IP-9 through IP-13)**
  - Match CC formats from research branch output
  - **Satisfies:** R20, R21

### Phase 5: Plugin Integration

- [ ] **[MBI-008] T5.1 Add prompt_sets to PluginManifest**
  - Add `prompt_sets: list[PromptSet]` field to `PluginManifest`
  - Update `plugins/loader.py` to discover prompt sets from manifests
  - **Satisfies:** R16, R17

- [ ] **[MBI-008] T5.2 Wire plugin prompt set registration**
  - Plugin-provided prompt sets are registered in the loader
  - Config can select a plugin-provided set by name
  - **Satisfies:** R17, R18

### Phase 6: Testing and Documentation

- [ ] **[MBI-008] T6.1 Unit tests for prompt set loader and renderer**
  - Test loading from filesystem and from package
  - Test template rendering with mock variables
  - Test missing template = no-op
  - **Satisfies:** R27

- [ ] **[MBI-008] T6.2 Byte-identical output tests for default set**
  - Verify each externalized injection point produces identical output to the pre-migration hardcoded behavior
  - **Satisfies:** R26

- [ ] **[MBI-008] T6.3 Claude Code set tests**
  - Verify each template renders with expected content
  - Verify system prompt includes git status, env block, model name
  - Verify tool descriptions are enriched
  - **Satisfies:** R27

- [ ] **[MBI-008] T6.4 Integration tests for prompt set switching**
  - Start agent with default set, capture context
  - Switch to Claude Code set, verify context changes
  - Switch to custom path set, verify it works
  - **Satisfies:** R27

- [ ] **[MBI-008] T6.5 Documentation**
  - Update CLAUDE.md module structure with `prompts/` module
  - Update README.md with prompt set concept and configuration
  - Create `docs/guides/prompt-sets.md` with how to create custom prompt sets

---

## MBI-009: Toolset Coverage for 1.0.0

**Goal:** 7 new tools + 4 enhancements + protected_files guardrail. ~97% coverage of a typical agentic development workload. Specialized, controllable tools — NOT a general-purpose shell.

**Design source of truth:** `analysis/mbi-toolset-coverage.md` (finalized — revision 5, all 11 open questions resolved, owner-approved)

**Milestone:** An agent can run a full Yoker development session (make check, pytest, lint, file ops, GitHub ops, web fetch) without missing-tool friction.

### Phase 1: Critical Tools (Tier 1)

- [ ] **[MBI-009] T1.1 Implement `make` tool in `src/yoker/builtin/make.py`**
  - `make(target, ctx, cwd, timeout_ms) -> ToolResult`
  - Target validation (reject shell metacharacters: `;`, `|`, `&`, `$`, backticks)
  - PathGuardrail on `cwd`
  - `subprocess.run(["make", target], ...)` — list args, no shell
  - Output truncation (default 100KB), timeout enforcement (default 5 min)
  - Return exit code, stdout, stderr separately
  - **Files:** `src/yoker/builtin/make.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:** `make(target="check")` executes; `make(target="rm -rf /")` rejected; timeout enforced; cwd guardrail works

- [ ] **[MBI-009] T1.2 Add `MakeToolConfig` to Config**
  - `timeout_ms`: default timeout (5 minutes)
  - `max_output_kb`: output truncation limit (100KB)
  - **Files:** `src/yoker/config/__init__.py` (modify)

- [ ] **[MBI-009] T1.3 `make` tool tests**
  - Test target execution, shell metacharacter rejection, output truncation, timeout, cwd guardrail
  - **Files:** `tests/test_builtin/test_make.py` (new)

- [ ] **[MBI-009] T2.1 Add `offset` and `limit` to `read` tool**
  - Add `offset: int | None = None` and `limit: int | None = None` parameters
  - If `offset` provided, skip to that line (1-indexed); if `limit` provided, return at most that many lines
  - Return total line count in metadata; line numbers included when offset/limit used
  - **Files:** `src/yoker/builtin/read.py` (modify)

- [ ] **[MBI-009] T2.2 Add `package://` URL support to `read` tool**
  - If `path` starts with `package://`, resolve to installed package source file
  - `package://clevis` -> `clevis/__init__.py`; `package://clevis/get_config` -> module containing `get_config`
  - Uses `importlib.util.find_spec()` to locate the package; read-only, no code execution
  - **Files:** `src/yoker/builtin/read.py` (modify)

- [ ] **[MBI-009] T2.3 `read` enhancement tests**
  - Test offset only, limit only, both, offset beyond file, limit exceeding file, total line count, `package://` resolution
  - **Files:** `tests/test_builtin/test_read.py` (extend)

- [ ] **[MBI-009] T3.1 Add new parameters to `search` tool**
  - `case_insensitive: bool = False`, `context_before: int = 0`, `context_after: int = 0`
  - `include_pattern: str = ""`, `exclude_pattern: str = ""`, `count_only: bool = False`
  - Cap context lines at 20 to prevent output flooding
  - **Files:** `src/yoker/builtin/search.py` (modify)

- [ ] **[MBI-009] T3.2 `search` enhancement tests**
  - Test case-insensitive, context lines, include/exclude patterns, count-only, context cap
  - **Files:** `tests/test_builtin/test_search.py` (extend)

### Phase 2: High-Priority Tools (Tier 2)

- [ ] **[MBI-009] T4.1 Implement `pytest` tool in `src/yoker/builtin/pytest.py`**
  - `pytest(ctx, test_filter, flags, cwd, timeout_ms) -> ToolResult`
  - Build command list: `["pytest"]` + test_filter + flags; list args, no shell
  - Flag validation: reject shell metacharacters; PathGuardrail on cwd and test_filter
  - **Files:** `src/yoker/builtin/pytest.py` (new), `src/yoker/builtin/__init__.py` (manifest update)

- [ ] **[MBI-009] T4.2 `pytest` tool tests**
  - **Files:** `tests/test_builtin/test_pytest.py` (new)

- [ ] **[MBI-009] T5.1 Implement `file` tool in `src/yoker/builtin/file.py`**
  - Operations: `delete`, `copy`, `move`, `chmod`, `symlink`
  - `delete` on directories requires `recursive: bool = False` (explicit opt-in)
  - PathGuardrail on all paths; chmod validates mode; symlink target validated
  - Protected files cannot be deleted/moved/overwritten
  - **Files:** `src/yoker/builtin/file.py` (new), `src/yoker/builtin/__init__.py` (manifest update)

- [ ] **[MBI-009] T5.2 `file` tool tests**
  - **Files:** `tests/test_builtin/test_file.py` (new)

- [ ] **[MBI-009] T6.1 Implement `askuserquestion` tool as a static built-in**
  - Registered in `__YOKER_MANIFEST__` (not Session-injected)
  - Interactive mode (TTY): present question via UI handler; choices -> selection menu
  - Batch mode: read from stdin with timeout, or return default
  - Non-interactive (`yoker run`): return default immediately
  - Configurable: `tools.askuserquestion.enabled = false`
  - **Files:** `src/yoker/builtin/askuserquestion.py` (new), `src/yoker/builtin/__init__.py` (manifest update)

- [ ] **[MBI-009] T6.2 `askuserquestion` tests**
  - **Files:** `tests/test_builtin/test_askuserquestion.py` (new)

- [ ] **[MBI-009] T7.1 Implement `github` tool (per existing design)**
  - Read-only MVP: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view
  - `subprocess.run(["gh", ...], ...)` — list args, no shell
  - Operation allowlist (fixed enum, configurable per-project); subcommand blocking is the whole point
  - Timeout enforcement (default 30s); result count limits (max 100 for lists)
  - **Files:** `src/yoker/builtin/github.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Design:** `analysis/api-github-tool.md` and `analysis/security-github-tool.md`

- [ ] **[MBI-009] T7.2 `github` tool tests**
  - **Files:** `tests/test_builtin/test_github.py` (new)

- [ ] **[MBI-009] T8.1 Implement `lint` tool in `src/yoker/builtin/lint.py`**
  - Operations: `check` (ruff check), `format` (ruff format), `format_check` (ruff format --check), `typecheck` (mypy)
  - `subprocess.run(["ruff", ...])` or `subprocess.run(["mypy", ...])` — list args, no shell
  - PathGuardrail on paths and cwd; `fix: bool = False` for auto-fix
  - **Files:** `src/yoker/builtin/lint.py` (new), `src/yoker/builtin/__init__.py` (manifest update)

- [ ] **[MBI-009] T8.2 `lint` tool tests**
  - **Files:** `tests/test_builtin/test_lint.py` (new)

- [ ] **[MBI-009] T9.1 Implement `uv` tool in `src/yoker/builtin/uv.py`**
  - Operations: `sync`, `run`, `add`, `remove`, `lock`, `venv`
  - `subprocess.run(["uv", ...], ...)` — list args, no shell
  - Operation allowlist (fixed enum)
  - **Files:** `src/yoker/builtin/uv.py` (new), `src/yoker/builtin/__init__.py` (manifest update)

### Phase 3: Medium-Priority Enhancements (Tier 3)

- [ ] **[MBI-009] T10.1 Add `add` and `checkout` to git tool**
  - `add` operation with `pathspec` argument
  - `checkout` operation with `branch` and `create` arguments
  - **Files:** `src/yoker/builtin/git.py` (modify)

- [ ] **[MBI-009] T11.1 Add `prompt` parameter to `webfetch` tool**
  - If provided, use the agent's ModelBackend to extract/summarize content based on the prompt
  - Configurable: `tools.webfetch.summarization_backend = "agent"` (default)
  - **Files:** `src/yoker/builtin/webfetch.py` (modify)

- [ ] **[MBI-009] T12.1 Add `protected_files` to `PermissionsConfig`**
  - Denylist of files that cannot be written/updated by agents
  - Default: Makefile, makefile, GNUmakefile, Justfile, justfile, Taskfile.yml, pyproject.toml, tox.ini, setup.py, setup.cfg
  - Configurable per-project and per-user; empty list disables all protections
  - Applied to `write` and `update` tools via PathGuardrail
  - **Files:** `src/yoker/config/__init__.py` (modify), `src/yoker/tools/guardrails/path.py` (modify)
  - **Acceptance:** `write(path="Makefile", ...)` rejected; `update(path="pyproject.toml", ...)` rejected; `write(path="src/main.py", ...)` allowed; configurable; empty list disables

---

## MBI-005: Assistant Integration

**Goal:** Showcase yoker's capabilities with TWO complete example projects: (1) yoker-assistant — a personal assistant demonstrating setup check, custom looping logic (mail account integration), custom context builders, agent triggering, git integration, and mail responses; (2) yoker-writing-assistant — based on the c3:writing-assistant skill, demonstrating skill-based agent specialization.

**Design source of truth:** PLAN.md MBI-005 entry

**Milestone:** Users can run `uvx yoker-assistant` and `uvx yoker-writing-assistant` and experience how low-friction yoker is.

**Status:** Backlog (dependencies met: MBI-002, MBI-003, MBI-004 all complete)

### Tasks

- [ ] **[MBI-005] Create yoker-assistant package project**
  - Setup check with bootstrap trigger
  - Custom loop logic (mail account integration)
  - Custom context builder
  - Agent triggering and personalization
  - Git integration (commit/push)
  - Mail response handling

- [ ] **[MBI-005] Create yoker-writing-assistant package**
  - Based on c3:writing-assistant skill
  - Demonstrates skill-based agent specialization
  - Shows how to package a skill-based agent as an executable

- [ ] **[MBI-005] Documentation for both packages**
  - Comprehensive documentation explaining architecture and patterns
  - Tutorial and examples
  - Both projects serve as reference implementations

**Acceptance Criteria:**
- [ ] Users can run `uvx yoker-assistant` successfully
- [ ] Users can run `uvx yoker-writing-assistant` successfully
- [ ] yoker-assistant demonstrates all yoker capabilities
- [ ] yoker-writing-assistant demonstrates skill-based agent specialization
- [ ] Documentation explains architecture and patterns for both
- [ ] Both projects serve as reference implementations

---

## Maintenance Tasks

Unsorted improvements and fixes.

- [ ] **M.1 Rename yoker: plugin tools to builtin:**
  - Rename namespace from `yoker:` to `builtin:`
  - When listing tools (e.g. /tools), don't include the `builtin:` prefix
  - Update documentation
  **Priority:** P1 (in scope for 1.0.0)

- [ ] **M.2 Default Tools Behavior**
  - When agent has no explicit tools configuration, ALL tools should be available
  - Update agent initialization logic
  - Write unit tests
  **Priority:** P1 (in scope for 1.0.0)

- [ ] **M.3 Namespace from Plugin/Package**
  - Allow namespace configuration derived from the plugin/package, not from skill/agent frontmatter
  - Update SkillLoader and AgentLoader
  - Write unit tests
  **Priority:** P2 (in scope for 1.0.0)

- [ ] **M.4 Clean Up Duplicate Tests**
  - Review all tests for duplicates (e.g. tests/test_tools/test_base.py and tests/tools/test_base.py)
  - Consolidate duplicate tests
  - Ensure full coverage maintained
  **Priority:** P3 (in scope for 1.0.0)

---

## Launch Preparation: Public Announcement (On Hold)

**Source:** Email from Christophe, 2026-06-17
**Goal:** Prepare marketing materials and dedicated website for Yoker's public announcement.
**USP:** "Add LLM capabilities to your Python apps and modules without worrying about the agentic foundations. Agentic Functions."
**Status:** On hold — start only when owner signals implementation works is finalizing.

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

---

## Architecture Refactoring: Plugin Config Registration

**Goal:** Enable plugins to register configuration fields dynamically, allowing tool-specific settings without hardcoding in ToolsConfig.

**Related Analysis:**
- [Plugin Architecture](analysis/plugin-architecture.md)

### Phase 7: Config System Refactoring

**Status:** Backlog (in scope for 1.0.0)

**Priority:** P2

**Problem:** The current config system uses frozen dataclasses for `ToolsConfig`, which cannot be extended dynamically. Plugins added via `--with` need to register their own configuration fields (e.g., `[tools.pkgq]` settings). This requires architectural changes to the config system.

- [ ] **7.1 Plugin Config Registration System Design**
  - Analyze Clevis `register_field` mechanism
  - Design plugin config registration API
  - Determine how plugins register their config schema
  - Design config discovery and validation flow
  - Document interaction with existing `WebGuardrailConfig` duplication
  - **Priority:** P2 (in scope for 1.0.0)
  - **Estimated time:** 4-6 hours (design only)
  - **Note:** This is a design task. Implementation will be a separate task.

- [ ] **7.2 ToolsConfig Dynamic Extension**
  - Change `ToolsConfig` from frozen to mutable dataclass
  - Implement `register_tool_config(name: str, config_class: type)` API
  - Support config field injection at runtime
  - Update existing hardcoded tool configs to use registration pattern
  - **Depends on:** 7.1
  - **Priority:** P2 (in scope for 1.0.0)
  - **Estimated time:** 8-12 hours
  - **Note:** Requires Clevis support or local workaround

- [ ] **7.3 Consolidate WebGuardrailConfig Classes**
  - Remove `WebGuardrailConfig` duplication between `tools/web/guardrail.py` and `config/__init__.py`
  - Create single unified `WebGuardrailConfig` class
  - Update `WebSearchToolConfig` and `WebFetchToolConfig` to compose guardrail config
  - Ensure config passes guardrail settings directly to guardrails
  - Update `agent/_setup.py` to use consolidated config classes
  - **Depends on:** 7.2
  - **Priority:** P2 (in scope for 1.0.0)
  - **Estimated time:** 2-4 hours
  - **Note:** This task should NOT be done separately. It depends on the plugin config registration system being in place first, because:
    1. The duplication exists because `ToolsConfig` is frozen
    2. When plugins can register config fields, the pattern will change
    3. Hardcoded `WebSearchToolConfig`/`WebFetchToolConfig` will become anti-patterns
    4. Consolidating now would create a pattern that contradicts the plugin system design

**Rationale for Dependency Order:**
- Item 7.1 must complete first to establish the design
- Item 7.2 implements the mechanism that plugins will use
- Item 7.3 consolidates existing configs using the new mechanism
- Doing 7.3 before 7.2 would create throwaway code that contradicts the plugin architecture

**Related Issue:** The duplication in `WebGuardrailConfig` classes is currently intentional:
- `tools/web/guardrail.py::WebGuardrailConfig` is a runtime guardrail config (unfrozen)
- `config/__init__.py::WebSearchToolConfig`/`WebFetchToolConfig` are frozen TOML configs
- `agent/_setup.py` converts frozen configs to runtime configs
- This is a workaround that will be eliminated by proper plugin config registration

---

## Security Improvements

- [ ] **S.1 Secure API Key Storage with Keyring**
  - Use Python `keyring` library to securely store API keys instead of plain text in config files
  - During bootstrap wizard, use `keyring.set_password('yoker', '<provider>', api_key)` to store
  - On startup, retrieve with `keyring.get_password('yoker', '<provider>')`
  - Fallback to config file if keyring is unavailable or user opts out
  - Support all providers: Ollama, OpenAI, Anthropic, Gemini
  - Update `BootstrapWizard` to use keyring for API key collection
  - Update config loading to check keyring first, then config file
  - Document the keyring integration in security docs
  - Write unit tests with mocked keyring backend
  - **Priority:** P2 (in scope for 1.0.0)
  - **Reference:** User request 2026-07-01

---

## Subsumed by MBI-008 / MBI-009

These items are retained for history. They are now covered by the new MBIs and should not be worked on independently.

### Covered by MBI-009: Toolset Coverage for 1.0.0

- [x] **2.15 Python Tool** — **Covered by MBI-009** (T2: `read` enhancement with `package://` URLs covers the `inspect` use case; `exec` deferred to post-1.0.0)
  - Original: Python script execution functionality
  - Resolution: `inspect` folded into `read` tool as `package://` URL support; `exec` deferred to post-1.0.0 per owner decision
  - See `analysis/mbi-toolset-coverage.md` Section 7.2 and 7.4

- [x] **2.16 Pytest Tool** — **Covered by MBI-009** (T4: `pytest` tool)
  - Original: Test execution via pytest
  - Resolution: Implemented as `pytest` tool in MBI-009 Tier 2
  - See `analysis/mbi-toolset-coverage.md` Section 7.5

- [x] **2.17 AskUserQuestion Tool** — **Covered by MBI-009** (T6: `askuserquestion` tool)
  - Original: Interactive question asking capability
  - Resolution: Implemented as static built-in `askuserquestion` tool in MBI-009 Tier 2
  - See `analysis/mbi-toolset-coverage.md` Section 7.7

- [x] **2.18 Development Workflow Tools** — **Covered by MBI-009** (T1: `make` tool + T8: `lint` tool)
  - Original: RuffTool, MyPyTool, ToxTool, MakeTool, PyPiTool
  - Resolution: `make` tool in Tier 1; ruff+mypy consolidated into `lint` tool in Tier 2; ToxTool and PyPiTool not included for 1.0.0
  - See `analysis/mbi-toolset-coverage.md` Sections 7.1 and 7.11

- [x] **2.19 GitHub Tool** — **Covered by MBI-009** (T7: `github` tool)
  - Original: GitHub CLI wrapper tool
  - Resolution: Implemented as `github` tool with subcommand blocking in MBI-009 Tier 2
  - See `analysis/mbi-toolset-coverage.md` Section 7.8

- [x] **2.20 Add [start:stop] Arguments to Output-Heavy Tools** — **Covered by MBI-009** (T2: `read` offset/limit; T3: `search` enhancements)
  - Original: Extend offset/limit pattern to tools with large outputs
  - Resolution: `read` offset/limit in Tier 1; `search` enhancements in Tier 1; ListTool pagination deferred to post-1.0.0
  - See `analysis/mbi-toolset-coverage.md` Sections 7.2 and 7.3

- [x] **2.22 uv Tool** — **Covered by MBI-009** (T9: `uv` tool)
  - Original: uv CLI wrapper tool for Python package management
  - Resolution: Implemented as `uv` tool in MBI-009 Tier 2
  - See `analysis/mbi-toolset-coverage.md` Section 7.12

### Covered by MBI-008: Prompt Sets

- [x] **3.5 Prompt Sets Implementation** — **Covered by MBI-008**
  - Original: Create prompts/sets/default/, minimal/, detailed/; PromptTemplate with variable rendering
  - Resolution: Fully superseded by MBI-008 which externalizes all prompts into Jinja2 templates with 13 injection points and two prompt sets (Yoker default + Claude Code demo)
  - See `analysis/mbi-prompt-sets.md`

### Partially covered by MBI-008

- [x] **3.8 Context Reminders Implementation** — **Partially covered by MBI-008**
  - Original: ContextReminder protocol, SkillsReminder, ClaudeMdReminder, CurrentDateReminder, WorkingDirectoryReminder, GitContextReminder
  - Resolution: Partially superseded by MBI-008. The new injection points (IP-8 session start, IP-9 env info, IP-10 file change, IP-13 context update) cover the same ground as context reminders but through the prompt set framework rather than a separate ContextReminder protocol. The prompt set's `session_start.j2` template handles CLAUDE.md injection, current date, git status. The `env_info.j2` handles skills/agents listing. Remaining reminder concepts (working directory, git context) are available as template variables in the prompt set system.
  - See `analysis/mbi-prompt-sets.md` Section 2.2 (IP-8, IP-9, IP-10, IP-13)

---

## Deferred to Post-1.0.0

Items explicitly deferred until after the 1.0.0 release.

### Backend Integration (Deferred)

- [ ] **3.4 Configurable Components Infrastructure**
  - Create base classes (SetMetadata, ComponentSet, ComponentLoader)
  - Implement resolution strategy (additional_dirs override set)
  - Create directory structure (prompts/sets/, skills/sets/, agents/sets/)
  - Implement metadata.toml parsing
  - Add configuration support to Config schema
  - Write unit tests
  - See `analysis/configurable-components-design.md` for design
  - **Priority:** Post-1.0.0

- [ ] **3.6 Skills Sets Implementation**
  - Create skills/sets/default/ with core skills
  - Create skills/sets/minimal/ with essential skills
  - Implement Skill class with frontmatter parsing
  - Implement SkillLoader with set support
  - Integrate with SkillTool
  - Add skill discovery
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** Post-1.0.0

- [ ] **3.7 Agent Sets Implementation**
  - Create agents/sets/default/ with main.md, researcher.md, developer.md, reviewer.md
  - Create agents/sets/research/ with research-focused agents
  - Create agents/sets/development/ with development-focused agents
  - Implement AgentDefinition class with frontmatter parsing
  - Implement AgentLoader with set support
  - Integrate with existing agent.py
  - Add tool filtering per agent definition
  - Write unit tests
  - **Depends on:** 3.4
  - **Priority:** Post-1.0.0

- [ ] **3.9 Lazy Loading Implementation**
  - Implement LazyToolRegistry (load tools on first use)
  - Implement LazySkillLoader (load skills on demand)
  - Create core tools set (Read, List, Search, Existence)
  - Add tool caching after first load
  - Implement get_tools_for_request()
  - Add configuration for lazy vs eager loading
  - Write unit tests
  - **Depends on:** 3.4, 3.5, 3.6, 3.7
  - **Priority:** Post-1.0.0

### Future Features (Deferred)

- [ ] **2.13.1 Local WebSearch Backend**
  - Implement LocalWebSearchBackend using DDGS library
  - Support multiple search backends (bing, brave, ddg, google)
  - Add rate limiting and error handling
  - Integrate with WebSearchTool via plugin system
  - Write unit tests
  - Note: OllamaWebSearchBackend is working, this is for offline-first
  - **Priority:** Post-1.0.0

- [ ] **2.13.2 Local WebFetch Backend**
  - Implement LocalWebFetchBackend using httpx + Trafilatura
  - Implement content extraction with Trafilatura
  - Add SSRF protection and DNS rebinding defense
  - Integrate with WebFetchTool via plugin system
  - Write unit tests
  - Note: OllamaWebFetchBackend is working, this is for full control
  - **Priority:** Post-1.0.0

- [ ] **R.1 Hermes Agent Comparison**
  - Research Hermes Agent architecture and capabilities
  - Compare Hermes to Yoker architecture
  - Compare Hermes to C3 Agentic Harness approach
  - Document findings in research folder
  - Identify features worth incorporating
  - **Priority:** Post-1.0.0

- [ ] **F.1 Multi-Agent Chat Room Demo**
  - Design multi-agent chat room architecture
  - Implement spawn command in TUI to spawn agent from folder
  - Create agent folder structure for spawned agents
  - Implement agent-to-agent communication protocol
  - Create demonstration scenario
  - **Note:** Handled by ../yoker-chat
  - **Priority:** Post-1.0.0

### Deferred MBI Follow-ups

- [ ] **MBI-007 7.8.7 ListAgents tool** — Deferred to a follow-up MBI (PR #43 Clarification 6)
  - Session-injected tool returning (name, status) for active agents
  - Enables swarm/team-based discovery model
  - Revisit agent status semantics and naming authority

- [ ] **MBI-003 3.7 Auto-generate functions for detected skills/agents** — Deferred per design doc section 10
  - Auto-generate callable functions for detected skills/agents
  - `from package.skills import skill_name; skill_name("prompt")`