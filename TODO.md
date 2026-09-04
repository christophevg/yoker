# TODO

## Backlog

### Permission Annotations

- [ ] **Subcommand-aware permission annotations (deferred — fundamental redesign)**
  - `git`'s `path` is annotated `WritePath` because some operations consuming it
    are destructive (checkout, rm, pull) — worst-case semantics by design. This
    makes read-only operations (`git diff` on a protected file) fire the
    protected-path approval prompt. The annotation system cannot express
    "depends on subcommand" today; fixing it properly requires a fundamental
    redesign of the permission annotation system to take subcommands into
    account. Deferred as too big for now.
  - Related note: `git checkout` with a branch named like a file pathspec
    (e.g. `args={"branch": "Makefile"}`) would attempt a file restore — an
    operation-level approval question, unchanged by this issue.
  - **Priority:** Low (as-designed trade-off, UX cost only)
  - **Severity:** Low — prompt is honest (see git approval-prompt provider),
    but noisy for read operations


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
- [ ] **`demos/agent-tool.md`: review script** — currently produces too much output, and the generated `media/demo-agent-tool.svg` had to be reverted after regen (small rendering bug; not fixed in 0.12.0). Owner: review script output volume + bug later.

### Agent Behavior & Instructions

- [ ] **Agent lifecycle management — spawn mode, per-type limits, terminate tool, and best practices**
  - After the fix to keep spawned agents alive (fixed 0.11.0), agents now spawn new agents until the session limit is reached, then fall back to sending messages. However, agents of a needed type may never have been spawned, leaving no active agent to send messages to. The agent lifecycle needs explicit controls and guidance.
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
  - **Update 2026-09-03:** parts 1 (`ephemeral` spawn flag), 4 (`release_agent` tool) and the core of 2 (best-practice guidance in the agent tool descriptions, incl. fresh-context and slot-cost wording — `5a8932a`, shipped 0.11.0 + 0.12.0) are done. Still open: per-type limits (3), idle-timeout auto-release and capacity/type surfacing in results (5).

### Documentation & Analysis

- [ ] **First full run: consolidate legacy `analysis/` corpus into `analysis/functional.md`** — the analysis/ folder holds ~90 legacy analysis documents; per-release consolidation (release process R1) only merges documents newer than the last consolidation, so this one-time bulk run is needed first. After the run, per-release consolidation stays lightweight forever. If gaps are found, the deleted `research/` corpus remains recoverable from git history (pre-cleanup commit).
  - **Priority:** Medium — blocks nothing, but the per-release step assumes it
  - **Note:** new `research/` documents are consolidated at each release and deleted after consolidation (release process R1); this backlog item covers only the one-time legacy backlog.

### Tool Enhancements

- [ ] **#56: `github` tool: `workflow_view` output too large** — 20KB overflow; compact default + opt-in `fields`, mirroring the `pr_list`/`issue_list` pattern. **Priority:** Medium

- [ ] **#57: `git` tool: read-only ops on protected paths trigger write-approval prompts**
  - Owner ruling: as-designed; needs a design decision (label subcommands read/write internally). Kept in backlog — **Priority:** Medium — explicitly "not enough incidents yet, design-later".

- [ ] **#67: bootstrap wizard intercepts `--help`/`--version`** — **Priority:** Low (owner: very low, needs more incidents)

- [ ] **#69: `git` tool: missing `stash` + branch deletion** — **Priority:** Low (owner: needs more incidents; permission-model design needed when picked up). Overlaps with the `git restore` / `git stash` line below.

- [ ] **`search` tool: `include_pattern` for directories** — cannot search within a specific subdirectory pattern
- [ ] **`read` tool: binary file detection** — reading a binary file returns garbled content. Should detect and warn/skip like `search` does
- [ ] **`git` tool: `git merge` operation** — complete the branch workflow (create → work → commit → switch → merge)
- [ ] **`git` tool: `git restore` / `git stash`** — `checkout` is done, but `restore` (discard changes) and `stash` (temporarily shelve work) are still missing
- [ ] **`write` tool: per-call `overwrite` flag** — **Decision: under investigation (2026-09-02).** Owner is testing with `allow_overwrite = true` (config) to evaluate the blast radius; will then decide between keeping config-only, per-call argument, or both. Previous "not implementing" ruling reverted. Note: `protected_files` guardrail remains the safety net in all variants.
- [ ] **`make` tool: arbitrary target args** — some Makefile targets need arguments that aren't env vars (e.g. `make clean V=1`). Consider `make_args` parameter with sanitization
- [ ] **`file` tool: `stat`/`info` sub-operation** — return file size, type, modification time without reading content
- [ ] **`file` tool: `diff` sub-operation** — compare two files without reading both into context

### UX Polish
- [ ] **Tool-call progress indicator `[#Turn/#Request/#ToolCall]` next to the timestamp** — scrolling bursts of tool calls give no sense of position or volume
  - Idea (2026-09-03, dogfooding session): compact progress tag on tool-call lines, e.g. `● 14:32:07 [#T2/R3/4/7] read(...)` — dim/styled to match `TOOL_STYLE`; optionally on result lines too.
  - Domain model (verified in code): a turn = 1..N server requests (`process_message` `while True` loop, `core/_processing.py:301`); each request may carry a batch of tool calls (`_execute_tool_calls`, `_processing.py:953`). Batch size known only at execution time (after dedup); no turn-wide total is knowable — the model decides turn-by-turn whether to continue. Honest counters only: per-batch `{x}/{N}`, running turn count `#k`, request index.
  - Counter sources: **#Turn** — bridge already forwards `TURN_START` (`bridge.py:108`), UI-side counting is free; **#Request** — must bubble from the core loop (no event fires between the last `TOOL_RESULT` of one batch and the first `TOOL_CALL` of the next, so the UI cannot infer request boundaries); **#ToolCall** — same core bubbling ride.
  - Implementation shape: append defaulted fields (`request_index`, `tool_index`, `tool_total`, `turn_tool_count`) to `ToolCallEvent`/`ToolResultEvent` (`events/types.py:146`); thread an iteration/running-count state object through `process_message` → `_execute_tool_calls` → `_execute_single_tool_call` (per-turn state pattern already exists: `_EscalationState`, `turn_start`, `_processing.py:290-299`); bridge passes fields through (`bridge.py:126-137`); new optional kwargs on `output_tool_call`/`output_tool_result` in the handler protocol + interactive/batch implementations. Persistence unaffected — generic `asdict` round-trip in `events/recorder.py` rides along. Estimate: ~6 files, mostly mechanical.
  - Constraint: counters maintained **per agent tag** — multi-agent sessions interleave sub-agent events in one stream; a global counter would jump meaninglessly. Bridge already passes `agent` to the UI methods.
  - Open design decision: `#ToolCall` flavor — A: running count within turn (`[#T2/R3/C14]`), B: batch position with total (`[#T2/R3/4/7]`, answers "how many still coming" per batch), or both. Lean: B first, `#k` as possible follow-up.
  - Related insight: every batch triggers a feedback request carrying the entire context — larger batches mean fewer round trips (execution within a batch is sequential, `_processing.py:980`).
  - **Priority:** Medium

- [ ] **Pause feature — Ctrl+C pauses at a stable point mid-turn, Ctrl+D exits**
  - Idea (2026-09-03, dogfooding session): a signal while everything is running that lets the turn finish to a stable point and then pauses — the user can interfere when a long-running process goes in the wrong direction, instead of waiting for the end of the turn.
  - Stable point (verified in code): end of the current tool batch in `process_message`'s `while True` loop (`core/_processing.py:301`) — all tool results recorded, tool-call/result pairing intact — before the next server request. Pause flag checked there; break cleanly, return partial content, agent stays alive, REPL returns to the prompt. The next user prompt IS the steering correction (full context; no resume machinery needed).
  - Context marking: inject a system note on pause ("[paused by user after this tool batch]") — precedent exists: `_maybe_inject_escalation` injects a system message at the same spot (`core/_processing.py:986`).
  - Interaction design (owner-confirmed): **Ctrl+C = pause** (single tap, any time); **Ctrl+D = exit** (at prompt — already existing behavior, `chat.py` `get_input()` returns None on EOF and the REPL breaks). No double-tap convention needed. At the input prompt Ctrl+C shows a hint ("No turn running — Ctrl+D exits") instead of exiting.
  - Implementation shape: core pause flag mirrors the idle-watchdog cancellation path (`core/__init__.py:388-427`, `_timed_out` + `_process_task.cancel()`) but returns normally instead of raising to the caller; SIGINT handler via `loop.add_signal_handler` sets the pause flag (Ctrl+C never kills anything — eliminates the double-tap problem at the root); `PauseEvent` (additive event, generic `asdict` serialization in `events/recorder.py` rides along) + UI indicator; REPL error handling mostly unchanged. Estimate: core ~50 lines + event/UI plumbing.
  - Windows caveat: `add_signal_handler` is unsupported for SIGINT on the Proactor loop — fallback: catch CancelledError from `process()` and convert to pause (Windows is a secondary target).
  - Open design question: multi-agent scope — v1 pauses the current agent only; team-wide pause (should sub-agents keep running?) is an open item.
  - **Priority:** Medium
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
