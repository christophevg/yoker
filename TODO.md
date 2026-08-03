# TODO

## Release Gate (0.10.0)

All items must be complete before public announcement. The version will likely be 0.10.0, not 1.0.0 — minor versioning continues until the backlog is exhausted.

### In Progress

- [ ] **MBI-005: Two Assistant Packages**
  - `yoker-assistant` — done (externally)
  - `yoker-writing-assistant` — actively being worked on (externally)
  - Documentation for both packages
  - **Acceptance:** `uvx yoker-assistant` and `uvx yoker-writing-assistant` both work; both serve as reference implementations
  - **Dependencies:** MBI-002 (Bootstrap) ✅, MBI-003 (Python API) ✅, MBI-004 (yoker Commands) ✅

- [ ] **Dogfooding Gate**
  - Continuous effort — using Yoker for all Yoker development work
  - Transitions seamlessly into normal usage over time
  - Gate is passed when owner can do full development workflow without falling back to Claude Code

### Ready to Start

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

---

## Pre-Release Work

Ordered by priority.

### P1: Post-Filter on All Tools

- [ ] **Post-filter "grep" pattern on all tool outputs**
  - Allow the LLM to specify a pattern to filter tool output before returning
  - Reduces context growth by limiting actual output returned to the LLM
  - Applies to all tools (read, search, list, make, git, etc.)
  - Head start on context management — reduces noise before formal context management is implemented

### P2: Context Management & Credit Usage

- [ ] **Usage Stats — Ollama usage API integration**
  - Implement Ollama usage API (`https://ollama.com/api/usage`)
  - Add to stats: total session/weekly cost, turn cost, cost per tokens
  - Track context size as a statistic alongside usage to find correlations
  - If a relation is found, context size may become a statistical parameter to track and act upon

- [ ] **Context Management — TTR, Forget Tool, /compact, Context Budget**
  - **TTR (time-to-remember):** per context item type, configurable turns before items are dropped (e.g. tool results: 3 turns, user messages: 5 turns). Maybe offer LLM option to manage this by itself.
  - **Forget tool:** allow LLM to explicitly choose to forget a context item
  - **/compact command:** manual context compaction
  - **Context budget visibility:** add remaining context budget to `/context` command
  - All needed before public announcement — long running sessions currently cost too much
  - May use usage stats as a trigger to automatically manage context

### P3: Bug Fixes & UX Polish

In priority order (high → low):

- [ ] **Bootstrap wizard models outdated** — update model list (e.g. GLM 5 → 5.2)
- [ ] **Tool call UI feedback delayed** — when a tool call is performed, the UI feedback showing the tool call is only shown after the result is available. With long-running tool calls, both call and result are shown at the end, making the chat seemingly blocked doing nothing.
- [ ] **Write tool result looks wrong** — tool result of a write operation shows inconsistent char counts (e.g. "686 chars" vs "25 chars")
- [ ] **Tool result output should render max 20 lines** — truncate all tool result output to 20 lines max
- [ ] **`yoker chat` initial prompt option** — accept an option to provide an initial prompt to start the chat with
- [ ] **Interactive UI handler Panel output** — the new interactive UI handler outputs responses in a Panel. This is okay for chat interactions but not for the bootstrap wizard.
- [ ] **Bootstrap wizard `--path` issue** — bootstrap wizard refers to `~/.yoker.toml`. If the wizard is used from `yoker init --path ./yoker.toml`, the reference is incorrect. `~/.yoker.toml` might exist, yet `init` tries to create a project-level config file.

### P4: Dogfooding Backlog (all pre-release)

If it blocks the full Yoker development workflow, it's not ready for public announcement.

#### High Priority

- [ ] **`git` tool: `git diff` fails for nested file paths**
  - `git diff` with `path` set to a deeply nested file (e.g. `src/yoker/builtin/make.py`) fails with "Not a Git repository"
  - Root cause: `_validate_repository_path` only checks `resolved.parent / ".git"` — for nested files, the parent has no `.git`
  - Fix: walk up the directory tree to find the repo root, or use `git rev-parse --show-toplevel`

- [ ] **`update` tool improvements** (merged: exact match brittleness + line-number-based mode)
  - `old_string` must match exactly including whitespace — frequently fails with "Search text not found" or "ambiguous match"
  - Evaluate during implementation: (a) line-number-based replace mode; (b) fuzzy/whitespace-insensitive matching; (c) better error messages showing closest match; (d) line-number-based insert mode
  - Line-number-based mode would also scope updates to a specific region, avoiding ambiguous matches in large files

- [ ] **`search` tool: accept file paths**
  - Currently only accepts directories. Agent must `read` the whole file and scan visually, wasting context window.
  - Allow `search` to accept a file path and search just that file

#### Medium Priority

- [ ] **`list` tool: reduce noise**
  - Respect `.gitignore` (optionally or by default)
  - Lower default `max_entries` from 2000 to ~200

#### Low Priority (all needed for full workflow)

- [ ] **`search` tool: `include_pattern` for directories** — cannot search within a specific subdirectory pattern
- [ ] **`read` tool: binary file detection** — reading a binary file returns garbled content. Should detect and warn/skip like `search` does
- [ ] **`git` tool: `git tag` operation** — list, create, delete tags. Useful for release workflows
- [ ] **`git` tool: `git merge` operation** — complete the branch workflow (create → work → commit → switch → merge)
- [ ] **`git` tool: `git restore` / `git stash`** — `checkout` is done, but `restore` (discard changes) and `stash` (temporarily shelve work) are still missing
- [ ] **`write` tool: per-call `overwrite` flag** — `allow_overwrite` is project-level config. Agent cannot overwrite even when it explicitly wants to (e.g. rewriting a generated file)
- [ ] **`make` tool: arbitrary target args** — some Makefile targets need arguments that aren't env vars (e.g. `make clean V=1`). Consider `make_args` parameter with sanitization
- [ ] **`github` tool: write operations** — currently read-only. Add `issue_create`, `pr_create` with approval model like `git` tool
- [ ] **`file` tool: `stat`/`info` sub-operation** — return file size, type, modification time without reading content. Useful for deciding whether to read a file
- [ ] **`file` tool: `diff` sub-operation** — compare two files without reading both into context

### P5: Launch Preparation (active, worked on externally in parallel)

- [ ] **L.1 Storyboard of Publications** — define sequence to announce Yoker on social media (LinkedIn, Instagram). Refer to website in all publications.
- [ ] **L.2 Publication Timeline** — prepare timeline for articles and posts. Investigate: how many posts, how long between posts, repeating schedule. **Depends on:** L.1
- [ ] **L.3 Website Structure Research** — research dedicated website structure for Yoker
- [ ] **L.4 Website Examples and Framework Comparisons** — research examples, create constructive comparison with other agent frameworks (Archon, other harness frameworks)
- [ ] **L.5 Strong Front Page** — research and design a strong front page with clear examples of all ways Yoker can be used (SDK, chat, package runner)
- [ ] **L.6 Clear Getting Started Guide** — research and design clear getting started guide
- [ ] **L.7 Best Practices Research** — learn from good examples for developer tool websites
- [ ] **L.8 Look and Feel Research** — research look and feel for the website
- [ ] **L.9 Low Entry / Bootstrapping Showcase** — show low entry barrier, highlight free Ollama account support
- [ ] **Website at yoker.dev** — GitHub Pages deployment, frontpage with examples, "why we built yoker" page (worked on externally, reported back for roadmap tracking)
- [ ] **CONTRIBUTING.md** — write clean CONTRIBUTING.md after quick research into best practices (high-level draft exists uncommitted in repo)

---

## Post-Release

Items deferred until after the 0.10.0 release. Further dogfooding may move some of these to pre-release.

### MBI-008: Prompt Sets (full)

All 13 injection points, 2 prompt sets (Yoker default + Claude Code demo), Jinja2 templates, plugin integration. Only IP-12 (context overflow management) is pulled into pre-release.

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

### Subsumed by MBI-008 / MBI-009

Retained for history. Covered by the new MBIs — do not work on independently.

- [x] **2.15 Python Tool** — Covered by MBI-009
- [x] **2.16 Pytest Tool** — Covered by MBI-009
- [x] **2.17 AskUserQuestion Tool** — Covered by MBI-009
- [x] **2.18 Development Workflow Tools** — Covered by MBI-009
- [x] **2.19 GitHub Tool** — Covered by MBI-009
- [x] **2.20 Add [start:stop] Arguments** — Covered by MBI-009
- [x] **2.22 uv Tool** — Covered by MBI-009
- [x] **3.5 Prompt Sets Implementation** — Covered by MBI-008
- [x] **3.8 Context Reminders Implementation** — Partially covered by MBI-008

---

## Completed (in git history)

Prior completed work is recorded in git history. See `git log -- TODO.md` for full task breakdowns.

Key completed items (PRs):
- M.2: Default Tools Behavior (PR #47)
- `make` tool (PR #48)
- `read` offset/limit (PR #49)
- `search` enhancements (PR #50)
- `github` tool (PR #51)
- Context overflow management (PR #52)
- `protected_files` guardrail (PR #53)
- Back-port RichUIHandler output (PR #54)
- Context Persistence Bug Fix (PR #55)
- Git write operations (add, commit, push) — first autonomous Yoker-on-Yoker commit
- Git checkout support
- Multi-line commit messages
- Individual file staging
- /context rendering of tool calls
- Rich markup bracket swallowing fixes
- Session resume support
- `make` tool: stdout on failure + verbose flag
- `context/` added to `.gitignore`
- Git tool schema enriched with per-operation arg descriptions
- `make` env_vars allowlist configured in local yoker.toml
- `file` tool: copy, move, delete operations (from C3 porting feedback)
- `git rm` operation with `--cached` support (from C3 porting feedback)
- `write` tool: improved `create_parents` documentation (from C3 porting feedback)
