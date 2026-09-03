# TODO

## 0.12.0 Release Targets — "Reduce tool errors and retry loops"

Theme: tool errors cost a retry round trip + context re-evaluation. Eliminate
error classes, make first retry succeed, stop doomed loops. Track progress here.

### Tier 1 — error-class elimination (tool accepts what the model naturally sends)

- [x] **Bare-name tool dispatch** — add `resolve()` fallback to `_run_tool`
  (`core/_processing.py:1012`); exact-key miss with bare name resolves via
  `ToolRegistry.resolve()`; ambiguity → error listing full names (precedent:
  `AgentRegistry.resolve()`). Registry-level M.5 follow-up stays deferred.
  **Done 2026-09-03:** implemented + 12 unit tests, `make check` green,
  live-validated (bare `list` call dispatched correctly after restart).
- [x] **`write` tool: `create_parents` default → True** — kills the
  guaranteed "parent directory does not exist" → mkdir → retry loop.
- [ ] **#1: `github` tool: `repo` optional, defaults to current git repo** —
  align write ops with documented behavior; docs already promise the default.
- [ ] **#61: `list`/`search`: report visibility on "0 entries"** — "0 visible
  entries (N hidden by ignore rules)"; silent absence reads as absence.

### Tier 2 — self-correctable errors + fewer round trips

- [ ] **Descriptive invalid-argument errors** — schema-driven error stating
  what was wrong + valid set; converts N blind retries into 1 informed retry.
- [ ] **#65: `update` anchor-based insert (`insert_after`/`insert_before`)** —
  eliminates the "Search text not found" failure class; re-evaluate #63 after.
- [ ] **#62: `update`/`write` return a diff of the applied change** — removes
  the read-after-write round trip; makes failures audible.

### Tier 3 — behavioral (stop wasting loops on doomed strategies)

- [ ] **Agent boundary awareness** — strengthened agent-tool description,
  explicit no-shell-access + stop-and-ask instructions, retry-limit escalation
  in the tool loop (force escalation after N consecutive failures).

### Release hygiene

- [ ] **Complete `Unreleased` changelog** (usage tracking, config summary,
  #71 fix) and rename section to 0.12.0 at release time.
- [ ] **Mark stale backlog items** — `/session` command (shipped in 0.11.0),
  agent-lifecycle item (ephemeral + `release_agent` shipped; per-type limits +
  capacity surfacing remain).

## Backlog
## Backlog

### Code Quality

- [ ] **PathGuardrail refactor — eliminate duplicated validation blocks between Read/Write**
  - `src/yoker/tools/guardrails/path.py`: `WritePathGuardrail.validate()` fully overrides `ReadPathGuardrail.validate()` (no `super()` call), producing large parallel blocks — empty-path check, null-byte check (added in 0.11.0), length/format checks etc. duplicated in both classes. Next safety check added to only one variant silently leaves the other unprotected (root cause of the Windows null-byte hole fixed in 0.11.0).
  - **Fix:** Factor shared validation into the base class (common checks: empty, null-byte, structure) with polymorphic plugin-URL policy ("allowed if configured" for read / "never for write"). Regression proof to preserve: platform-agnostic null-byte tests incl. `test_write_rejects_null_byte`, plus 4-case parametrized security test.
  - **Priority:** Medium
  - **Severity:** Medium — architecture-level duplication makes future divergent-guardrail bugs likely

### Tooling notes (from 0.11.0 release session)

- [ ] **Makefile: generalize `test-py310` into parameterized `test-py VERSION=...`** — single target forwarding to `uv run tox -e py$(VERSION)`; add same for a per-leg `check` variant if useful.
- [ ] **conftest.py plugin fallback is silent** — `tests/conftest.py` installs the demo plugin via subprocess with `check=False` and swallowed output (pytest-configure time); failures surface later as confusing `ModuleNotFoundError`/`PluginError` in tests. Make the fallback loud (fail with clear message) or remove it now that the plugin is a proper dev dependency.
- [ ] **`session`/`sleep` shadowing smell** — public API functions re-exported from `__init__.py` shadow same-named submodules (`yoker.session`, `yoker.builtin.sleep`); caused 3.10 mock-target failures (`patch("yoker.session.Agent")` resolves to the function). Product rename is a breaking change — evaluate for a future major version; meanwhile tests must patch via explicit module refs (done in 0.11.0).

### Agent Behavior & Instructions

- [ ] **Agent boundary awareness — stop guessing agents and seeking shell access**
  - Agents attempt to spawn non-existent agents to access capabilities they lack (e.g. shell commands)
  - Agents persistently try to find workarounds to run shell commands despite not having a shell tool
  - Agents attempt workarounds instead of escalating to the user when blocked
  - **Fix:** Strengthen `agent` tool description ("Only spawn agents from the list above. Do NOT guess agent names."); add explicit "no shell access" instruction to system prompt / env reminder; add "stop and ask" instruction ("If a tool fails or you cannot accomplish something with available tools, STOP. Do not try workarounds. Ask the user for direction."); consider a retry-limit mechanism in the tool loop that forces escalation after N consecutive failures
  - **Priority:** High
  - **Severity:** High — wastes tokens, causes repeated failures, degrades user experience

- [x] **Spawned agents released immediately — parent cannot send follow-up messages**
  - After a spawned agent completes its task, `spawn_agent` calls `session.release(child)` in a `finally` block, removing it from the active map. If the parent then tries `send_message` to the finished agent, it fails with "No active agent with id"
  - **Fix:** Don't auto-release spawned agents. Keep them in the active map until the session ends or an explicit release is called. The session's `__aexit__` already cleans up all outstanding agents
  - **Priority:** High
  - **Severity:** High — breaks the common "spawn → get result → ask follow-up" workflow

- [ ] **Agent lifecycle management — spawn mode, per-type limits, terminate tool, and best practices**
  - After the fix to keep spawned agents alive (see above), agents now spawn new agents until the session limit is reached, then fall back to sending messages. However, agents of a needed type may never have been spawned, leaving no active agent to send messages to. The agent lifecycle needs explicit controls and guidance.
  - **Fix (multi-part):**
    1. **Spawn mode flag** — add a `keep_alive` (or similar) boolean parameter to the `agent` (spawn) tool. When `True`, the agent persists in the active map for follow-up `send_message` calls (current behaviour). When `False`, the agent is a single-shot sub-agent that is automatically released after its first response (the old "fire-and-forget" behaviour). Default: `False` (single-shot) to prevent agents from consuming the agent limit unnecessarily.
    2. **Best practices & instructions** — update agent/system prompt guidance on when to use single-shot vs. keep-alive spawning, how to plan agent usage to avoid hitting limits, and when to prefer `send_message` to an existing agent over spawning a new one. Include examples of optimal multi-agent workflows.
    3. **Per-type agent limit** — consider a configurable per-type (agent definition) limit on concurrently active agents, so the global limit isn't exhausted by spawning many agents of the same type while a different type is needed.
    4. **Terminate tool** — add a `release_agent` (or `terminate_agent`) tool that lets the parent agent explicitly release a keep-alive agent when it's no longer needed, freeing the slot for other agents.
    5. **Other considerations:**
       - Auto-release keep-alive agents after a configurable idle timeout (no messages for N turns)
       - Surface active agent count and remaining capacity in the agent tool's result, so the LLM can make informed spawning decisions
       - Surface which agent types are already active (and their IDs) to help the LLM choose `send_message` over spawning a duplicate
  - **Priority:** High
  - **Severity:** High — agents hit the limit before spawning the right types, breaking multi-agent workflows
- [ ] **`/session` command — interactive overview of active agents in the session**
  - `/agents` is already taken and shows the registry of known agent definitions (the catalog). There is no way to see which agents are actually active in the running session, what their IDs are, or how many slots remain.
  - **Fix:** Add a `/session` slash command that shows: active agents (ID, agent definition name, status), remaining capacity vs. agent limit, and which agent types are currently available for `send_message`. This complements the lifecycle management work above by giving the user (and indirectly the LLM via tool results) visibility into session state.
  - **Priority:** High
  - **Severity:** Medium — no visibility into multi-agent session state; user cannot inspect or troubleshoot agent lifecycle issues


### Tool Enhancements

- [x] **`update` tool: infer `operation` from arguments when omitted**
  - Already implemented: `operation` defaults to `""`, inference logic handles replace/insert/append. Delete must always be explicit. Tests cover all inference paths.

- [ ] **#61: `list`/`search` tools: gitignored entries suppressed silently** — "0 entries" output reads as absence; fix by reporting visibility: "0 visible entries (N hidden by ignore rules)". **Priority:** High (owner: high value, small fix, solves a lot)

- [ ] **#65 (re-scoped): `update` tool: anchor-based insert — `insert_after`/`insert_before`**
  - Re-scoped 2026-09-01: commit 10100c1 fixed the `operation`-inference misfires, but the anchor-insert API is NOT implemented; the issue now covers only the missing API. (Related: #63 — ambiguous-anchor erroring is re-evaluated after this lands.)
  - **Priority:** Medium

- [ ] **#56: `github` tool: `workflow_view` output too large** — 20KB overflow; compact default + opt-in `fields`, mirroring the `pr_list`/`issue_list` pattern. **Priority:** Medium

- [ ] **#57: `git` tool: read-only ops on protected paths trigger write-approval prompts**
  - Owner ruling: as-designed; needs a design decision (label subcommands read/write internally). Kept in backlog — **Priority:** Medium — explicitly "not enough incidents yet, design-later".

- [ ] **#62: `update`/`write` tools: return a diff of the applied change** — **Priority:** Medium (bumped from Low 2026-09-02: rich feedback lets the caller validate the edit without a follow-up read, eliminating the read-after-write double tool call; commit 10100c1 already solved much of the corruption pain)

- [ ] **#63: `update` tool: ambiguous anchor should error** — re-evaluate AFTER the #65 outcome (owner: see related issues).

- [ ] **#67: bootstrap wizard intercepts `--help`/`--version`** — **Priority:** Low (owner: very low, needs more incidents)

- [ ] **#69: `git` tool: missing `stash` + branch deletion** — **Priority:** Low (owner: needs more incidents; permission-model design needed when picked up). Overlaps with the `git restore` / `git stash` line below.

- [ ] **`search` tool: `include_pattern` for directories** — cannot search within a specific subdirectory pattern
- [ ] **`read` tool: binary file detection** — reading a binary file returns garbled content. Should detect and warn/skip like `search` does
- [ ] **Tool dispatch: resolve bare (simple) tool names at call time**
  - Investigation (2026-09-01, dogfooding session): a model emitted bare names `list`/`search` instead of the namespaced schema names `yoker__list`/`yoker__search`; `_run_tool` (`src/yoker/core/_processing.py:1012`) does an exact-key `agent.tools.get(tool_name)` lookup on namespaced keys (`yoker:list`) with no fallback → `Error: Unknown tool 'list'`.
  - Inconsistency: `AgentRegistry.resolve()` and `SkillRegistry.resolve()` already implement bare-name fallback (match on `simple_name`, error with full-name list on ambiguity), but `ToolRegistry` has no `resolve()` at all. `_filter_tools_by_definition` (`src/yoker/core/__init__.py:666`) even accepts bare names at agent-definition time — so bare names work when *filtering* but not when *dispatching*.
  - **Fix:** Add `resolve()`-style fallback to tool dispatch, mirroring `SkillRegistry.resolve()`: on exact-key miss with no `:` in the name, match `spec.simple_name` (possibly trying the `yoker:` prefix first for builtins); on multiple matches, error listing full names (precedent: `AgentRegistry.resolve()`).
  - **Priority:** Low
  - Related: M.5 (registry-level bare-name resolution) — same problem, deeper fix at the registry level; this entry is the dispatch-level quick fix.
- [ ] **`git` tool: `git merge` operation** — complete the branch workflow (create → work → commit → switch → merge)
- [ ] **`git` tool: `git restore` / `git stash`** — `checkout` is done, but `restore` (discard changes) and `stash` (temporarily shelve work) are still missing
- [ ] **`write` tool: per-call `overwrite` flag** — **Decision: under investigation (2026-09-02).** Owner is testing with `allow_overwrite = true` (config) to evaluate the blast radius; will then decide between keeping config-only, per-call argument, or both. Previous "not implementing" ruling reverted. Note: `protected_files` guardrail remains the safety net in all variants.
- [ ] **`make` tool: arbitrary target args** — some Makefile targets need arguments that aren't env vars (e.g. `make clean V=1`). Consider `make_args` parameter with sanitization
- [ ] **`github` tool: `issue_create` operation** — currently read-only (except pr_create/pr_comment/release_create). Add issue creation with approval model
- [ ] **#1: `github` tool: `repo` argument optional, defaults to current git repo** — docs already promise "If omitted, uses current git repo", but write ops (`pr_create`, `issue_create`, `release_create`, `label_create`) reject a missing repo ("Parameter 'repo' is required for …"). Doc/behavior mismatch; align implementation with the documented behavior. **Priority:** Medium
- [ ] **`file` tool: `stat`/`info` sub-operation** — return file size, type, modification time without reading content
- [ ] **`file` tool: `diff` sub-operation** — compare two files without reading both into context
- [ ] **Tool framework: descriptive error messages for invalid arguments** — when a tool call fails on wrong/missing arguments, the error should state what was wrong and list the set of expected/valid arguments (schema-driven), so the caller can self-correct on the next attempt. Cross-cutting over all builtin tools. **Priority:** Medium
- [ ] **`write` tool: `create_parents` default → True** — failing on missing parent directories is the annoyance; creating them is harmless (per-call argument default change, independent of the `allow_overwrite` decision). **Priority:** Medium

### UX Polish

- [ ] **Config file permission errors produce raw stacktrace — add graceful error handling**
  - When `yoker.toml` has incorrect file permissions (not `0600`), Yoker crashes with a raw Python stacktrace instead of a clean, user-friendly error message
  - **Fix:** Catch the permission/security error during config loading and present a clean message: "Your config file at {path} has insecure permissions (expected 600). Run: chmod 600 {path}"
  - **Priority:** Medium

- [ ] **Git commit approval dialog shows raw data — format clean commit overview**
  - When the git commit operation requires interactive approval, the approval dialog shows raw internal commit data rather than a clean, human-readable summary of what files will change and what the commit message will be
  - **Fix:** Enhance the commit approval preview to show: staged files (list), commit message (formatted), and a clear Y/N prompt
  - **Priority:** Low

- [ ] **`yoker chat` initial prompt option** — accept an option to provide an initial prompt to start the chat with
- [ ] **Interactive UI handler Panel output** — the interactive UI handler outputs responses in a Panel. Fine for chat but not for the bootstrap wizard.

### Context Management & Usage

- [ ] **Context Management — TTR, Forget Tool, /compact, Context Budget**
  - TTR (time-to-remember): per context item type, configurable turns before items are dropped
  - Forget tool: allow LLM to explicitly choose to forget a context item
  - /compact command: manual context compaction
  - Context budget visibility: add remaining context budget to `/context` command
  - May use usage stats as a trigger to automatically manage context

- [ ] **Usage Stats — Ollama usage API improvements**
  - Continue improving Ollama usage API integration
  - Add to stats: total session/weekly cost, turn cost, cost per tokens
  - Track context size as a statistic alongside usage

### C3 Migration

- [ ] **C3 toolset evaluation**
  - Audit C3 agent/skill definitions against yoker toolset
  - Check if instructions are possible with current yoker tools
  - Result: report stating which tools/options are missing and how instructions can be rewritten
  - **Output:** `analysis/c3-toolset-evaluation.md`

- [ ] **C3 agents/skills porting**
  - Port C3 agents and skills to work with Yoker (or make C3 dual-compatible)
  - Include instructions to "ask for tools/more options" if yoker toolset limits the LLM
  - Open question: where to host yoker-specific vs claude-specific definitions
  - **Depends on:** C3 toolset evaluation

### Network Resilience

- [ ] **Network error retry** — on network error, retry with configurable time interval for a configurable number of attempts

### MBI-008: Prompt Sets (full)

All 13 injection points, 2 prompt sets (Yoker default + Claude Code demo), Jinja2 templates, plugin integration. Only IP-12 (context overflow management) was pulled into pre-release.

**Analysis:** `analysis/mbi-prompt-sets.md`

### MBI-009: Toolset Coverage (rest)

Remaining tools and enhancements not pulled into pre-release:
- `pytest` tool (Tier 2)
- `file` tool — chmod, symlink sub-operations (Tier 2)
- `askuserquestion` tool — static built-in, interactive (Tier 2)
- `lint` tool — consolidated ruff + mypy (Tier 2)
- `uv` tool — package management (Tier 2)
- `git` enhancement — add + checkout (Tier 3)
- `webfetch` enhancement — prompt parameter (Tier 3)
- `read` `package://` URL support (deferred from pre-release slice)
- `multi-write` tool — batch creation of multiple files in one tool call (optimization, post-release)

**Analysis:** `analysis/mbi-toolset-coverage.md`

### Maintenance

- [ ] **M.1 Rename `yoker:` plugin tools to `builtin:`** — rename namespace; hide `builtin:` prefix in `/tools` listing; update docs
- [ ] **M.3 Namespace from Plugin/Package** — allow namespace configuration derived from plugin/package, not from skill/agent frontmatter; update SkillLoader and AgentLoader
- [ ] **M.5 Bare-Name Resolution at Registry Level** — agent/skill definitions should register bare tool names as-is (no namespace prefixing at load time). Resolution should happen at the ToolRegistry/SkillRegistry level when the name is used (e.g. during `_filter_tools_by_definition`): look up the bare name across all namespaces; if exactly one match exists, use it; if multiple, raise an ambiguity error listing the full namespaced candidates. This eliminates the `_YOKER_BUILTIN_TOOLS` duplication hack (added as a hotfix for the release-manager tool loss bug) and the `_namespace_tools` function's builtin-detection branch. The registry becomes the single source of truth for what tools exist and how bare names resolve. **Depends on:** M.3 (namespace from plugin/package, not folder name — e.g. C3 agents/skills should get `c3:` not `agents:`/`skills:`)
- [ ] **M.4 Clean Up Duplicate Tests** — review all tests for duplicates; consolidate; maintain coverage

### S.1: Secure API Key Storage with Keyring

- [ ] **S.1 Secure API Key Storage with Keyring** — use Python `keyring` library; during bootstrap wizard store via keyring; fallback to config file if unavailable; support all providers

### 7.1-7.3: Plugin Config Registration

- [ ] **7.1 Plugin Config Registration System Design** — analyze Clevis `register_field` mechanism; design plugin config registration API; document flow
- [ ] **7.2 ToolsConfig Dynamic Extension** — change `ToolsConfig` from frozen to mutable; implement `register_tool_config` API; support config field injection at runtime. **Depends on:** 7.1
- [ ] **7.3 Consolidate WebGuardrailConfig Classes** — remove duplication; create unified class. **Depends on:** 7.2

### Other Deferred Items

- [ ] **3.4 Configurable Components Infrastructure** — base classes (SetMetadata, ComponentSet, ComponentLoader); resolution strategy; directory structure. See `analysis/configurable-components-design.md`
- [ ] **3.6 Skills Sets Implementation** — create skills/sets/default/ and skills/sets/minimal/; implement SkillLoader with set support. **Depends on:** 3.4
- [ ] **3.7 Agent Sets Implementation** — create agents/sets/default/; implement AgentLoader with set support. **Depends on:** 3.4
- [ ] **3.9 Lazy Loading Implementation** — LazyToolRegistry, LazySkillLoader, core tools set. **Depends on:** 3.4, 3.5, 3.6, 3.7
- [ ] **2.13.1 Local WebSearch Backend** — LocalWebSearchBackend using DDGS library (offline-first)
- [ ] **2.13.2 Local WebFetch Backend** — LocalWebFetchBackend using httpx + Trafilatura (full control)
- [ ] **R.1 Hermes Agent Comparison** — research Hermes architecture; compare to Yoker; document findings
- [ ] **F.1 Multi-Agent Chat Room Demo** — handled by ../yoker-chat
- [ ] **MBI-007 7.8.7 ListAgents tool** — session-injected tool returning (name, status) for active agents
- [ ] **MBI-003 3.7 Auto-generate functions for detected skills/agents** — deferred per design doc section 10
- [ ] **Evaluate basic instructions** — review examples like https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md
- [ ] **`yoker init` config generation option** — option to generate config that only includes default overriding values
- [ ] **yoker-memory** — set of functions available to LLM to store and retrieve information from long term memory. Based on research. Example starting point: GBrain -> https://github.com/garrytan/gbrain/blob/master/llms-full.txt
- [ ] **yoker-dashboard** — a web interface on top of a running yoker instance offering a visual, point and click interface to the running agentic team. Inspiration: https://github.com/Bennettxai/FounderOS-DEMO
- [ ] **Unknown config key detection — warn on removed/renamed settings**
  Clevis (via dacite) silently ignores TOML keys that don't map to dataclass fields. After the path guardrail redesign, old keys like `allowed_extensions`, `blocked_patterns`, `blocked_extensions`, and `protected_files` are silently dropped — the user gets no feedback that their config is stale. Investigate options: (a) post-load validation in Yoker that checks the raw TOML dict for known-removed keys and warns with migration guidance, or (b) upstream support in Clevis for a strict mode that rejects unknown keys.
