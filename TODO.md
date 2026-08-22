# TODO

## Backlog

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

### Tool Enhancements

- [x] **`update` tool: infer `operation` from arguments when omitted**
  - Already implemented: `operation` defaults to `""`, inference logic handles replace/insert/append. Delete must always be explicit. Tests cover all inference paths.

- [ ] **`search` tool: `include_pattern` for directories** — cannot search within a specific subdirectory pattern
- [ ] **`read` tool: binary file detection** — reading a binary file returns garbled content. Should detect and warn/skip like `search` does
- [ ] **`git` tool: `git merge` operation** — complete the branch workflow (create → work → commit → switch → merge)
- [ ] **`git` tool: `git restore` / `git stash`** — `checkout` is done, but `restore` (discard changes) and `stash` (temporarily shelve work) are still missing
- [ ] **`write` tool: per-call `overwrite` flag** — ~~`allow_overwrite` is project-level config. Agent cannot overwrite even when it explicitly wants to~~  — **Decision: not implementing.** Project-level config is the correct security boundary; per-call override would bypass it.
- [ ] **`make` tool: arbitrary target args** — some Makefile targets need arguments that aren't env vars (e.g. `make clean V=1`). Consider `make_args` parameter with sanitization
- [ ] **`github` tool: `issue_create` operation** — currently read-only (except pr_create/pr_comment/release_create). Add issue creation with approval model
- [ ] **`file` tool: `stat`/`info` sub-operation** — return file size, type, modification time without reading content
- [ ] **`file` tool: `diff` sub-operation** — compare two files without reading both into context

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