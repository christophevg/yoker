# MBI: Toolset Coverage for 1.0.0

**Date:** 2026-07-16 (revised 2026-07-16 — owner decision to defer `exec` entirely)
**Status:** Finalized — revision 5 (owner defers `exec` to post-1.0; Python tool reduced to `inspect`-only, folded into `read` enhancement; all open questions resolved)
**Research source:** `research/context-management` branch (tool-gap-analysis.md, context-management-analysis.md)
**Backlog source:** TODO.md items 2.15-2.22

---

## 1. Goal

Ensure Yoker's built-in toolset provides enough coverage for a typical agentic development workload (like a Yoker development session) to proceed without missing-tool friction, enabling a 1.0.0 release.

## 2. Value

Without a comprehensive toolset, agents stall on routine tasks — running tests, executing linters, managing files — and the user must intervene with manual shell commands. The research recording showed that 39.7% of all tool calls in a real development session were shell commands (Bash), representing the single largest gap. Closing this gap moves Yoker from "interesting framework" to "usable agentic platform for real development work."

**Design principle (owner-directed):** Yoker's founding principle is structured, controllable tools — not a general-purpose shell. The proposed `run` tool (a Bash-like command executor with an allowlist) was rejected by the owner as "exactly not what I wanted to introduce, because that is not possible to control. This was literally the very first reason to start working on Yoker." The revised approach uses specialized tools with fixed operation sets, each individually controllable, each using `subprocess.run` with list args (no `shell=True`).

## 3. Current Tool Inventory

Yoker currently ships 13 tools. Ten are registered in the `__YOKER_MANIFEST__`; two are Session-injected; one is a factory.

### 3.1 Static Tools (in `__YOKER_MANIFEST__`)

| Tool | File | Purpose | Key Limitations |
|------|------|---------|-----------------|
| `read` | `builtin/read.py` | Read file contents (supports `plugin://` URLs) | No `offset`/`limit` — reads entire file; no line count metadata; no `package://` URL support for installed-package introspection |
| `write` | `builtin/write.py` | Write file contents (create/overwrite, `create_parents`) | No append mode |
| `update` | `builtin/update.py` | Edit existing file (replace, insert_before, insert_after, delete) | No `replace_all` parameter; no multi-edit in one call |
| `list` | `builtin/list.py` | List directory contents (`max_depth`, `max_entries`, `pattern`) | No file metadata (size, permissions, dates); no offset/limit pagination |
| `mkdir` | `builtin/mkdir.py` | Create directories (`recursive` flag) | Complete |
| `existence` | `builtin/existence.py` | Check if files/folders exist | Complete |
| `search` | `builtin/search.py` | File and content search (regex content, glob filename) | No context lines (`-A`/`-B`/`-C`); no case-insensitive; no file-type filter; no count-only mode |
| `git` | `builtin/git.py` | Git operations (status, log, diff, branch, show, commit, push) | No `add` operation (staging); no `checkout` (branch switching); no `config` |
| `webfetch` | `builtin/webfetch.py` | Fetch web content (markdown, text, html) | No `prompt` parameter for content extraction/summarization |
| `websearch` | `builtin/websearch.py` | Search the web | Complete |

### 3.2 Session-Injected Tools

| Tool | File | Purpose | Notes |
|------|------|---------|-------|
| `agent` (SpawnAgent) | `session/tools.py` | Spawn a sub-agent and get its response | Session-injected; returns `agent_id` + response |
| `send_message` | `session/tools.py` | Inter-agent messaging | Session-injected; request-response pattern |

### 3.3 Factory Tools

| Tool | File | Purpose | Notes |
|------|------|---------|-------|
| `skill` | `builtin/skill.py` | Skill invocation via `make_skill_tool()` factory | Needs SkillRegistry at runtime; added per-agent |

### 3.4 What Is NOT Present

- **No project command execution tool** — cannot run `make check`, `pytest`, `ruff`, `mypy`, or any project command
- **No Python code execution tool** — `exec` deferred to post-1.0; `inspect` folded into `read` enhancement; `run_module` dropped entirely
- **No package management tool** — cannot run `uv sync`, `uv run`, `uv add`
- **No file operations tool** — cannot delete, copy, move, chmod, or create symlinks
- **No interactive question tool** — cannot ask the user a question mid-task
- **No GitHub-specific tool** — cannot view PRs, issues, or workflow runs in a structured way

---

## 4. Research Findings Summary

The research branch (`research/context-management`) contains a detailed analysis of a real Claude Code session working on the Yoker project itself (MBI-004 CLI implementation). The recording captured 1,203 unique tool calls across 1,078 API requests.

### 4.1 Tool Usage Frequency

| Tool | Count | % | Yoker Equivalent | Coverage |
|------|-------|---|------------------|----------|
| Bash | 477 | 39.7% | NONE | **Gap** |
| Read | 435 | 36.2% | `read` (missing offset/limit, package://) | Partial |
| Edit | 146 | 12.1% | `update` (close match) | Good |
| Agent | 51 | 4.2% | `agent` (SpawnAgent) | Covered |
| Write | 44 | 3.7% | `write` | Covered |
| Grep | 16 | 1.3% | `search` (missing features) | Partial |
| Skill | 14 | 1.2% | `skill` | Covered |
| WebFetch | 12 | 1.0% | `webfetch` (missing prompt) | Partial |
| AskUserQuestion | 4 | 0.3% | NONE | Gap (interactive) |
| MCP plugin | 2 | 0.2% | MCP-specific | Out of scope |
| Glob | 1 | 0.1% | `search` (filename type) | Covered |
| WebSearch | 1 | 0.1% | `websearch` | Covered |

### 4.2 Bash Command Breakdown (477 commands)

| Purpose | Count | % of Bash | Specialized Tool That Covers It | Coverage |
|---------|-------|-----------|--------------------------------|----------|
| `make` targets (make check/test/lint/format) | ~70 | 14.7% | `make` tool | 100% |
| `pytest` direct invocations | ~35 | 7.3% | `pytest` tool | 100% |
| `ruff` direct invocations | ~15 | 3.1% | `lint` tool (check/format) | 100% |
| `mypy` direct invocations | ~10 | 2.1% | `lint` tool (typecheck) | 100% |
| Python inspection (getsource, dir, help) | 40 | 8.4% | `read` enhancement (package://) | 100% |
| Python CLI testing (python -m yoker) | 37 | 7.8% | `pytest` + `make` tools | 100% |
| Python one-off scripts (python -c) | 4 | 0.8% | DEFERRED (exec → post-1.0) | 0% |
| `uv run` / `uv sync` / `uv add` | ~20 | 4.2% | `uv` tool | 100% |
| grep (content search) | 147 | 30.8% | `search` enhancement | 100% |
| ls (directory listing) | 50 | 10.5% | `list` (existing) | ~100% |
| git operations | 82 | 17.2% | `git` (existing + enhancement) | ~100% |
| gh CLI (GitHub) | 31 | 6.5% | `github` tool | 100% |
| cat (file reading) | 13 | 2.7% | `read` enhancement (offset/limit) | 100% |
| find (file search) | 7 | 1.5% | `search` (filename type, existing) | 100% |
| wc (line counting) | 4 | 0.8% | `read` enhancement (line count metadata) | 100% |
| file ops (rm/chmod/ln/zip) | 8 | 1.7% | `file` tool | 100% |
| echo/pwd/env | 7 | 1.5% | ToolContext metadata (pwd) | ~15% |
| sleep/process | 3 | 0.6% | Not needed for agentic work | 0% |

### 4.3 Key Finding

With specialized tools, **~96.6% of the 477 Bash commands are covered** — the same coverage as the rejected `run` tool approach, but with each tool being individually controllable, using `subprocess.run` with list args (no `shell=True`), and consistent with Yoker's founding design principle.

The uncovered commands are:
- Python one-off scripts (4 commands, 0.8%) — `exec` deferred to post-1.0 per owner decision; we need experience with the first toolset to see if this really blocks
- `echo/pwd/env` (7 commands, 1.5%) — `pwd` can be provided via ToolContext metadata; `echo`/`env` are not relevant for agentic work
- `sleep` (3 commands, 0.6%) — not relevant for agentic work; agents don't need to sleep

---

## 5. Gap Analysis

### 5.1 Gaps With Existing Backlog Coverage (TODO.md 2.15-2.22)

| Gap | Backlog Item | Status | Revised Priority |
|-----|-------------|--------|-------------------|
| Python package inspection | 2.15 Python Tool (P4) | `inspect` folded into `read` enhancement; `exec` deferred to post-1.0 | **P1** — covers 40 inspection calls via `read` package:// support |
| Pytest execution | 2.16 Pytest Tool (P4) | Backlog covers pytest specifically | **P2** — covers ~35 direct pytest calls + 37 CLI testing calls |
| Interactive questions | 2.17 AskUserQuestion Tool (P4) | Backlog covers this | **P2** — static built-in, interactive sessions |
| Dev workflow tools (make, ruff, mypy) | 2.18 Dev Workflow Tools (P4) | Backlog proposes specialized tools | **P1/P2** — make is P1, ruff+mypy consolidated into `lint` tool at P2 |
| GitHub operations | 2.19 GitHub Tool (P4) | Backlog covers structured GitHub ops | **P2** — covers 31 gh commands, subcommand blocking required |
| Search/list pagination | 2.20 [start:stop] Arguments (P4) | Partially covers search/list (NOT read) | **P3** — minor enhancement |
| uv CLI operations | 2.22 uv Tool (P4) | Backlog covers uv operations | **P2** — covers ~20 uv calls (moved up from P3 per owner) |

### 5.2 Gaps With NO Backlog Coverage

These gaps were identified by the research but have no corresponding TODO.md item:

| Gap | Research Section | Impact | Backlog Status |
|-----|-----------------|--------|----------------|
| **`file` tool** (delete, copy, move, chmod, symlink) | §3.10, Priority 4 | 8 Bash commands | **Completely missing** |
| **`read` offset/limit + package://** | §3.7, Priority 2 | 121 Read calls (28%) + 13 cat + 4 wc + 40 Python inspection | **Not covered by 2.20** |
| **`search` context lines + case-insensitive + file-type filter + count mode** | §3.3, Priority 3 | 147 grep commands | **Not covered by 2.20** |
| **`git` add + checkout operations** | §3.5, Priority 5 | ~15 git commands | **Not in backlog** |
| **`webfetch` prompt parameter** | §4 Priority 6 | 12 WebFetch calls | **Not in backlog** |
| **`update` replace_all** | §1 table | 146 Edit calls, some used replace_all | **Not in backlog** |

### 5.3 Coverage Summary

| Metric | Current | With Specialized Tools + Enhancements |
|--------|---------|---------------------------------------|
| Overall tool coverage | ~62% | ~97% |
| Bash coverage | ~35% | ~96.6% |
| Read coverage | ~72% | ~100% |

---

## 6. The Architectural Decision: Specialized Tools (Revised)

**Owner feedback (2026-07-16):** The proposed `run` tool (a general-purpose command execution tool with a command allowlist) was rejected. The owner's principle: Yoker exists precisely to provide structured, controllable tools — not a general shell. A `run` tool with `shell=True` and an allowlist is "exactly not what I wanted to introduce, because that is not possible to control."

### 6.1 The Revised Approach: Specialized Tools

Each Bash command category maps to a **specialized, purpose-built tool** with:
- A **fixed operation enum** (not an arbitrary command string)
- **Typed parameters** per operation (e.g., `target` for make, `test_filter` for pytest)
- `subprocess.run` with **list args** (no `shell=True`, no shell injection risk)
- **Per-tool guardrails** tuned to the domain
- **Self-documenting** tool names — the LLM sees `make(target="check")` not `run("make check")`

This is consistent with Yoker's existing tool philosophy: `git(operation="status")`, not `run("git status")`. The `git` tool already demonstrates this pattern with its `OPERATION_ARGS` dict.

### 6.2 Why Not a Single "devtools" Tool?

A single `devtools(operation="make"|"pytest"|"ruff"|"mypy", ...)` tool is technically possible, but:
- It conflates unrelated domains (test running vs. linting vs. type checking)
- Per-domain guardrails become harder to implement (one tool, many configs)
- The LLM has to parse a larger operation enum instead of recognizing distinct tools
- It doesn't match the existing pattern (`git` is separate from `read` is separate from `search`)

Separate tools are more consistent with Yoker's architecture. The cost is more tool descriptions for the LLM, but each description is simpler and clearer.

### 6.3 What About Pipes and Chaining?

The rejected `run` tool needed `shell=True` for pipes/chaining (82% of Bash commands use these). The specialized tools approach does NOT need shell features:

- `make check` — `subprocess.run(["make", "check"])` — no pipe needed
- `pytest tests/test_foo.py -x` — `subprocess.run(["pytest", "tests/test_foo.py", "-x"])` — no pipe needed
- `grep -n "pattern" file | head -20` — the `search` tool handles this natively (content search + max_results)
- `ls -la dir/` — the `list` tool handles this natively
- `cat file | head -80` — the `read` tool with `limit=80` handles this natively

The research showed that the pipes/chaining in the recorded session were workarounds for missing tools (grep, ls, cat, head). Once those tools exist with proper parameters, the shell pipe patterns disappear. The specialized dev tools (make, pytest, lint, uv) never need pipes — they run a single command.

### 6.4 Trade-Off Summary

| Aspect | `run` Tool (rejected) | Specialized Tools (revised) |
|--------|----------------------|----------------------------|
| Tool count | 1 new tool | 7 new tools (make, pytest, file, askuserquestion, github, lint, uv) |
| `shell=True` | Required (pipes/chaining) | Never used (list args only) |
| Injection risk | Present (shell parsing) | None (list args, no shell) |
| LLM clarity | `run("make check")` — opaque | `make(target="check")` — explicit |
| Per-domain guardrails | Coarse (allowlist prefixes) | Fine-grained (per tool, per operation) |
| Coverage | ~97% of Bash | ~96.6% of Bash |
| Implementation effort | 1 tool | 7 tools (but each is simpler) |
| Maintenance | 1 allowlist to curate | Each tool self-contained |
| Yoker design principle | Violates (general shell) | Honors (structured, controllable) |

---

## 6.5 Protected Files: Makefile Editing Security

**Owner concern (2026-07-16):** "If the agents can edit the make file, it can create its own targets, with arbitrary Bash support -> option is to block editing Makefile through config (to be discussed where to draw the line)"

**Owner decision (2026-07-16):** Accepted. The proposed `protected_files` denylist in `PermissionsConfig` is confirmed. The list includes Makefile, pyproject.toml, tox.ini, etc.

This is a critical security insight. If an agent can edit the Makefile via the `write` or `update` tool, it can add a target like:

```makefile
pwn:
	rm -rf /
```

...and then use the `make` tool to execute it: `make(target="pwn")`. This bypasses the entire controlled-tools philosophy — the `make` tool validates the target name, but it cannot know that the target itself runs arbitrary shell commands.

### The Attack Chain

```
Agent edits Makefile (via write/update tool)
  -> Agent adds malicious target with shell=True equivalent
  -> Agent calls make(target="malicious_target")
  -> make executes the target, which runs arbitrary shell commands
  -> Security model bypassed
```

### Which Files Should Be Protected?

The attack chain applies to any file that the `make` tool (or other command-execution tools) reads as configuration/instructions. The following files are "execution configuration" files that, if modified by an agent, could bypass the controlled-tools security model:

| File | Risk | Why |
|------|------|-----|
| `Makefile` | CRITICAL | Targets can run arbitrary shell commands |
| `makefile` | CRITICAL | Same as Makefile (GNU make accepts lowercase) |
| `GNUmakefile` | CRITICAL | Same as Makefile |
| `pyproject.toml` | HIGH | Can define scripts, entry points, build hooks that execute code |
| `tox.ini` | HIGH | Tox commands can run arbitrary shell |
| `setup.py` | HIGH | Python execution on install/build |
| `setup.cfg` | MEDIUM | Can define command aliases that run shell |
| `.env` | HIGH | Already blocked by `blocked_patterns` in ReadToolConfig |
| `Justfile` / `justfile` | CRITICAL | Just targets can run arbitrary shell commands |
| `Taskfile.yml` | CRITICAL | Task targets can run arbitrary shell commands |

### Where to Configure This

This is a **guardrail concern**, not a tool-specific config concern. The protection should be at the PathGuardrail level, applied to both `write` and `update` tools.

**Accepted approach:** Add a `protected_files` field to `PermissionsConfig`:

```toml
[permissions]
# Files that cannot be written/updated by agents
# These are execution-configuration files that could bypass
# the controlled-tools security model if modified
protected_files = [
  "Makefile",
  "makefile",
  "GNUmakefile",
  "Justfile",
  "justfile",
  "Taskfile.yml",
  "pyproject.toml",
  "tox.ini",
  "setup.py",
  "setup.cfg",
]
```

**Implementation:**
- The PathGuardrail already checks `blocked_patterns` for read operations (regex-based). The `protected_files` check would be a filename-based check (exact match or glob) applied to `write` and `update` tools.
- This is a denylist approach (block specific files) rather than an allowlist approach (only allow specific files). The denylist is appropriate here because:
  1. The set of execution-configuration files is small and well-known
  2. New file types are rare (a new build system would be a conscious addition)
  3. An allowlist would be too restrictive (agents need to write source files, tests, docs, etc.)

**Interaction with existing tools:**
- `write` tool: PathGuardrail already checks `blocked_extensions` (`.exe`, `.sh`, `.bat`). Add `protected_files` check before the extension check.
- `update` tool: PathGuardrail already validates paths for update. Add the same `protected_files` check.
- `read` tool: No change needed — reading these files is safe, only writing/updating them is dangerous.
- `make` tool: No change needed — the `make` tool validates target names, not the Makefile content. The protection is at the write/update layer, not the execution layer.

**The "line" to draw:**
- **Block:** Execution-configuration files (Makefile, pyproject.toml, tox.ini, setup.py, Justfile, Taskfile.yml) — these can run arbitrary commands if modified
- **Allow:** Source files, test files, documentation, config files that don't execute code (yoker.toml, .editorconfig, .gitignore) — these are safe for agents to modify
- **Edge case:** `yoker.toml` — this is Yoker's own config. If an agent modifies it, it could change tool settings (e.g., disable guardrails). This should probably be protected too, but it's a Yoker-specific decision. For now, leave it unprotected; the config system validates values on load.

**Configurability:**
- The `protected_files` list is configurable per-project and per-user (standard Clevis config cascade)
- Users can add project-specific files (e.g., `BUILD`, `WORKSPACE` for Bazel projects)
- Users can remove protections if they want agents to edit Makefiles (e.g., for a Makefile-generation task)
- A `protected_files: []` (empty list) disables all protections (explicit opt-out)

---

## 7. Tool-by-Tool Analysis

### 7.1 `make` Tool — CRITICAL (new)

**Purpose:** Execute Makefile targets in the project.

**Proposed interface:**
```python
async def make(
  target: str,            # Makefile target (e.g., "check", "test", "lint")
  ctx: ToolContext,
  cwd: Annotated[str, PathArg("Working directory")] = ".",
  timeout_ms: int = 300000,
) -> ToolResult:
  """Run a Makefile target and return its output."""
```

**Implementation:**
- `subprocess.run(["make", target], cwd=cwd, ...)` — list args, no shell
- PathGuardrail on `cwd` (must be within project root)
- Output truncation (default 100KB)
- Timeout enforcement (default 5 minutes)
- Target validation: reject targets with shell metacharacters (`;`, `|`, `&`, `$`, backticks)
- No env var injection (make reads its own environment)

**Why this is safe:**
- The `target` parameter is a single Makefile target name, not a command string
- List-args subprocess execution means no shell parsing
- Target validation rejects anything that isn't a valid Makefile target name
- The agent can only run targets that exist in the project's Makefile

**Coverage:** ~70 of 477 Bash commands (14.7%). Covers `make check`, `make test`, `make lint`, `make format`, `make build`, `make docs`, etc. In this project, `make check` runs the full quality gate (ruff + mypy + pytest).

**Design note:** This follows the existing `git` tool pattern — a fixed operation space with typed parameters. The `git` tool uses `OPERATION_ARGS`; the `make` tool uses Makefile targets as its operation space.

### 7.2 `read` Enhancement — CRITICAL (existing tool)

**Purpose:** Add `offset`, `limit`, line count metadata, and `package://` URL support for installed-package introspection.

**Proposed addition:**
```python
async def read(
  path: Annotated[str, PathArg("Path to the file to read, or package:// URL")],
  ctx: ToolContext,
  offset: int | None = None,   # Starting line number (1-indexed)
  limit: int | None = None,    # Maximum number of lines to read
) -> ToolResult:
```

**Behavior:**
- If `offset` is provided, skip to that line before reading
- If `limit` is provided, return at most that many lines
- Always return total line count in metadata so the agent knows if there are more lines
- Output format includes line numbers (matching Claude Code's `cat -n` format for offset/limit reads)
- If `path` starts with `package://`, resolve it to an installed package's source file:
  - `package://clevis` -> `clevis/__init__.py` (package root)
  - `package://clevis/get_config` -> the module containing `get_config`
  - Uses `importlib.util.find_spec()` to locate the package, then reads the source file
  - This replaces the `python(operation="inspect")` operation — read-only introspection with zero risk

**Why `package://` replaces a standalone `python` tool:**
- The `inspect` operation was the only surviving operation after `run_module` was dropped and `exec` was deferred
- `inspect` is fundamentally a READ operation: `inspect.getsource()` reads a file, `dir()` lists attributes, `help()` renders documentation
- The `read` tool already supports `plugin://` URLs — `package://` is a natural extension
- Folding `inspect` into `read` avoids a standalone `python` tool with a single operation
- The `python` tool (with `exec`) is deferred to post-1.0, when we have real-world experience to decide if code execution is needed

**Coverage:** 121 Read calls (28%) that used offset, 161 (37%) that used limit, plus 13 `cat | head -N` Bash commands, plus 4 `wc -l` Bash commands (line count metadata), plus 40 Python inspection commands (via `package://` URLs).

### 7.3 `search` Enhancement — CRITICAL (existing tool)

**Purpose:** Add context lines, case-insensitive search, file-type filtering, and count-only mode.

**Proposed additions:**
```python
async def search(
  path: Annotated[str, PathArg("Directory to search in")],
  ctx: ToolContext,
  pattern: str = "",
  type: str = "content",
  max_results: int | None = None,
  timeout_ms: int | None = None,
  # NEW parameters:
  case_insensitive: bool = False,          # -i flag
  context_before: int = 0,                 # -B flag (lines before match)
  context_after: int = 0,                  # -A flag (lines after match)
  include_pattern: str = "",               # --include="*.py"
  exclude_pattern: str = "",               # --exclude="*.pyc"
  count_only: bool = False,                # -c flag (return counts only)
) -> ToolResult:
```

**Coverage:** 147 grep commands (30.8% of Bash). This is the single largest Bash category. The existing `search` tool covers basic content/filename search; the enhancements cover context lines, case-insensitive, file-type filters, and count mode.

### 7.4 Python Tool — DEFERRED TO POST-1.0

**Owner decision (2026-07-16):** "defer exec... we need experience with the first toolset to see if this really blocks."

The Python tool ships with **NO standalone tool** for 1.0.0. The `inspect` operation (read-only introspection) has been folded into the `read` tool enhancement as `package://` URL support (Section 7.2). The `exec` operation is deferred to post-1.0. The `run_module` operation is dropped entirely.

#### 7.4.1 What Was Analyzed

The research recording contained 81 `python -c` or `python -m` invocations. They fell into three categories:

**Category A: Package/Source Inspection (40 commands, ~49%)**
- `uv run python -c "import clevis; print(clevis.__file__)"` — locate installed package
- `uv run python -c "import clevis, inspect; print(inspect.getsource(clevis.get_config))"` — view source code
- `uv run python -c "import clevis; print([a for a in dir(clevis) if not a.startswith('_')])"` — list public API

**Resolution for 1.0.0:** Covered by `read` tool with `package://` URL support. These are READ-ONLY operations — inspect code, no side effects. No standalone Python tool needed.

**Category B: CLI Testing (37 commands, ~46%)**
- `uv run python -m yoker --help` — test help output
- `uv run python -m yoker chat --help` — test subcommand help
- `uv run python -m yoker init --no-interactive --path /tmp/test.toml` — test init

**Resolution for 1.0.0:** Covered by `pytest` tool (write a test that invokes the CLI) and `make` tool (if a `run` target exists). CLI testing goes through `pytest` and `make` only.

**Category C: Actual One-Off Scripts (4 commands, ~5%)**
- `uv run python -c "from clevis import SecurityConfig, SecurityAction; sc=SecurityConfig(...); print(type(sc), sc, ...)"` — test config behavior
- `uv run python -c "import clevis; src=open(clevis.__file__).read(); import re; m=re.search(...); print(m.group(0))"` — regex search in source

**Resolution for 1.0.0:** NOT COVERED. One-off scripts are not supported in 1.0.0. The owner explicitly deferred this: "we need experience with the first toolset to see if this really blocks." If real-world experience shows this is a blocking gap, a `python` tool with `exec` (opt-in, 6-layer defense) will be added post-1.0.

#### 7.4.2 Security Analysis (Preserved for Post-1.0 Reference)

The owner was right to be concerned about code execution. A `python` tool that accepts arbitrary code is functionally equivalent to Bash:
- `python -c "import os; os.system('rm -rf /')"` == `rm -rf /`
- `python -c "import subprocess; subprocess.run(['make', 'publish'])"` == `make publish`
- `python -c "open('/etc/passwd').read()"` == `cat /etc/passwd`

The `run_module` attack vector (agent writes a malicious module, then runs it) was the decisive factor. `protected_files` can protect the Makefile but cannot protect all Python files — the agent's primary job is writing Python files. This attack vector is unpreventable without crippling the agent's ability to write code.

The `exec` operation has a variant of the same attack: the agent writes a malicious module, then calls `exec(code="import malicious_module")`. The AST validation of the inline code passes (the import statement is benign), but the imported module executes malicious code. Mitigation: the `exec` import allowlist would exclude project packages by default. But this limits `exec` to stdlib-only operations.

**Key insight:** All major agentic frameworks (Claude Code, Cursor, Aider, Devin, OpenHands, SWE-agent, AutoGPT, CrewAI) provide full, unrestricted code execution. None attempt to restrict what code the agent can run. Yoker's founding principle is deliberately more restrictive. The question of how far controlled tools can go before they've recreated Bash is answered: code execution is the one area where controlled tools cannot meaningfully restrict the agent, because the agent's primary job is to write code.

**The `pytest` parallel:** The `pytest` tool has the SAME attack vector — an agent can write a test file containing `import os; os.system("rm -rf /")` and run it through `pytest`. The difference is pragmatic: `pytest` is a necessary development tool (we accept the risk), while `run_module` is a convenience that can be replaced by other tools, and `exec` is a low-frequency operation (4 commands, 0.8% of Bash) that can wait for real-world validation.

#### 7.4.3 Post-1.0 Python Tool Design (If Needed)

If real-world experience shows that the 4 one-off script commands are a blocking gap, a `python` tool with `exec` will be added post-1.0:

```python
async def python(
  operation: str,          # "inspect" | "exec"
  ctx: ToolContext,
  # For operation="inspect":
  module: str = "",         # Module to inspect (e.g., "clevis")
  attribute: str = "",     # Specific attribute/function to inspect
  # For operation="exec":
  code: str = "",           # Python code to execute (only if exec_enabled=True)
  cwd: Annotated[str, PathArg("Working directory")] = ".",
  timeout_ms: int = 30000,
) -> ToolResult:
```

**Config:**
```toml
[tools.python]
enabled = true
exec_enabled = false       # Disabled by default — must opt in
allowed_imports = ["os", "sys", "json", "re", "datetime", "math", "inspect"]
timeout_ms = 30000
max_output_kb = 100
```

The `exec` operation would use the 6-layer defense model documented in `analysis/api-python-tool.md` (AST validation, import auditing, resource limits, subprocess isolation, path guardrail, network blocking). The import allowlist would default to stdlib only (NOT project packages) to prevent the write+import attack variant.

**Existing research preserved for post-1.0:**
- `analysis/api-python-tool.md` — 6-layer defense model for `exec` operation
- Section 7.4.3 of this document (revision 4) — deep analysis of `run_module` attack vector, 8 mitigation options, comparison with other frameworks

### 7.5 `pytest` Tool — HIGH (new)

**Purpose:** Run pytest with structured parameters.

**Proposed interface:**
```python
async def pytest(
  ctx: ToolContext,
  test_filter: str = "",        # Test file path or node ID (e.g., "tests/test_foo.py::TestClass::test_method")
  flags: list[str] | None = None,  # Additional pytest flags (e.g., ["-x", "--cov"])
  cwd: Annotated[str, PathArg("Working directory")] = ".",
  timeout_ms: int = 300000,
) -> ToolResult:
  """Run pytest and return its output."""
```

**Implementation:**
- Build command list: `["pytest"]` + `test_filter` (if provided) + `flags` (if provided)
- `subprocess.run(cmd_list, cwd=cwd, ...)` — list args, no shell
- PathGuardrail on `cwd` and `test_filter` (if it's a path)
- Flag validation: reject flags with shell metacharacters
- Output truncation (default 100KB)
- Timeout enforcement (default 5 minutes)

**Coverage:** ~35 of 477 Bash commands (7.3%) directly, plus 37 Python CLI testing commands (7.8%) that were previously served by `run_module`. Covers `pytest`, `pytest -v`, `pytest --cov`, `pytest tests/test_foo.py -x`, etc.

**Design note:** The `make` tool covers `make test` (which runs `pytest -v`), but agents often want to run specific test files or apply specific flags. The `pytest` tool provides this granularity without the `make` tool's all-or-nothing approach. It also serves as the primary path for CLI testing in 1.0.0 (write a test that invokes the CLI, run it through `pytest`).

### 7.6 `file` Tool — HIGH (new)

**Purpose:** File system operations beyond read/write/update: delete, copy, move, chmod, symlink.

**Owner confirmation (2026-07-16):** "defer extras" — file tool gets basic operations (delete, copy, move, chmod, symlink), defer archive/stat to post-1.0.

**Proposed interface:**
```python
async def file(
  operation: str,          # "delete" | "copy" | "move" | "chmod" | "symlink"
  path: Annotated[str, PathArg("Path to the file/directory")],
  ctx: ToolContext,
  target: str = "",        # Destination path (for copy/move/symlink)
  mode: str = "",          # Permission mode (for chmod, e.g., "755")
  recursive: bool = False, # For delete on directories
) -> ToolResult:
  """Perform file system operations."""
```

**Security:**
- All operations go through PathGuardrail
- `delete` on directories requires `recursive: bool = False` (explicit opt-in)
- `chmod` validates mode string (octal format)
- `symlink` target is validated (no symlink to escape paths)
- Protected files (see Section 6.5) cannot be deleted/moved/overwritten

**Coverage:** 8 Bash commands (1.7%). Low frequency but universally needed operations that an agent cannot perform at all today.

**Deferred to post-1.0:** `archive` (zip/unzip), `stat` (file metadata: size, dates, permissions).

### 7.7 `askuserquestion` Tool — HIGH (new, interactive, static built-in)

**Purpose:** Allow the agent to ask the user a question mid-task, with choice-based or open-ended options.

**Owner clarification (2026-07-16):** "AskUserQuestion is not session related, its available to the agent (unless disabled) in interactive sessions. You can't 'ask' when there is no 'user'."

**Tool placement:** This is a **static built-in tool** (in `__YOKER_MANIFEST__`), NOT a Session-injected tool. It is always available to the agent in interactive sessions, unless explicitly disabled via config. It does not need Session context — it needs UI handler access, which is available via `ToolContext`.

**Proposed interface:**
```python
async def askuserquestion(
  question: str,            # The question to ask
  ctx: ToolContext,
  choices: list[str] | None = None,  # If provided, present as a selection menu
  default: str = "",        # Default answer if user provides nothing
  timeout_s: int = 300,     # Timeout in seconds
) -> ToolResult:
  """Ask the user a question and wait for their response."""
```

**Integration:**
- In interactive mode (TTY): uses the UI handler to present the question
- In batch mode: reads from stdin (with timeout) or returns the default
- In non-interactive `yoker run` mode: returns the default immediately (no user present — "You can't 'ask' when there is no 'user'")
- Configurable: `tools.askuserquestion.enabled = false` disables the tool entirely

**Coverage:** 4 AskUserQuestion calls in the session (0.3%). Low frequency but enables interactive workflows that are impossible today.

### 7.8 `github` Tool — HIGH (new, existing design)

**Purpose:** Structured GitHub operations via `gh` CLI wrapper.

**Owner confirmation (2026-07-16):** "github is required, note that we need to be able to block certain subcommands (that's the whole point)."

**Status:** Detailed design already exists in `analysis/api-github-tool.md` and `analysis/security-github-tool.md`.

**Scope (MVP):** Read-only operations — repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view.

**Subcommand blocking:** The `github` tool must support configurable subcommand blocking. This is the whole point of structured tools vs Bash — allow `gh pr list` but block `gh repo delete`. The operation allowlist (fixed enum) provides this: only operations in the allowlist are permitted. Configurable per-project:

```toml
[tools.github]
allowed_operations = ["repo_view", "issue_list", "issue_view", "pr_list", "pr_view"]
# Operations not in this list are rejected — even if implemented
```

**Implementation:**
- `subprocess.run(["gh", "pr", "view", "--json", ...], ...)` — list args, no shell
- Operation allowlist (fixed enum of allowed operations, configurable)
- Timeout enforcement (default 30 seconds)
- Result count limits (max 100 for lists)
- Authentication handled by `gh auth login` (existing user setup)

**Coverage:** 31 Bash `gh` commands (6.5%). Without a `run` tool, the `github` tool is the ONLY way for agents to interact with GitHub in a structured, controllable manner. Subcommand blocking is the core value proposition — it's why this tool exists instead of just using Bash.

### 7.9 `git` Enhancement — MEDIUM (existing tool)

**Purpose:** Add `add` and `checkout` operations to the existing git tool.

**Proposed additions to `OPERATION_ARGS`:**
- `add` operation with `pathspec` argument (staging specific files)
- `checkout` operation with `branch` and `create` arguments (branch switching)

**Coverage:** ~15 uncovered git commands (standalone `add`, `checkout -b`).

### 7.10 `webfetch` Enhancement — MEDIUM (existing tool)

**Purpose:** Add a `prompt` parameter for content extraction/summarization.

**Owner clarification (2026-07-16):** "webfetch currently is only implemented for Ollama support? adding prompt would mean a prompt to summarize the fetched result? if we provide it, make it configurable, with default same as agent."

#### Current Implementation Analysis

The webfetch tool (`src/yoker/builtin/webfetch.py`) delegates to a `WebFetchBackend` (Protocol). The only implementation is `OllamaWebFetchBackend` (`src/yoker/tools/web/backend.py`), which uses Ollama's native `client.web_fetch()` SDK method. So yes, the current implementation is **Ollama-only**.

The `OllamaWebFetchBackend.fetch()` method calls `self._client.web_fetch(url)` which returns a `WebFetchResponse` with `.content` and `.title` attributes. The content is already extracted/summarized by Ollama's server-side processing — the backend does NOT do any client-side summarization. The `content_type` parameter ("markdown", "text", "html") is passed to the backend but the Ollama SDK returns markdown by default.

There is NO `prompt` parameter in the current implementation. The tool returns whatever Ollama's `web_fetch` returns — full page content in markdown format.

#### What "prompt" Would Mean

The `prompt` parameter would allow the agent to specify what information to extract from the fetched content. For example:
- `webfetch(url="https://docs.python.org/3/library/ast.html", prompt="What functions are available for AST validation?")` — extracts only the relevant section
- `webfetch(url="https://github.com/owner/repo", prompt="What is the README summary?")` — returns a summary

This is a **client-side summarization** step: fetch the full content, then use an LLM to extract/summarize based on the prompt. This is what Claude Code's WebFetch tool does — it fetches the page, then uses a small model to process the content against the prompt.

#### Proposed Implementation

```python
async def webfetch(
  url: Annotated[str, Url("URL to fetch")],
  ctx: ToolContext,
  content_type: str = "markdown",
  max_size_kb: int = 2048,
  prompt: str = "",   # If provided, extract/summarize this information from the content
) -> ToolResult:
```

**Behavior when `prompt` is provided:**
1. Fetch the full content (existing behavior)
2. If `prompt` is non-empty, use the configured backend to process the content against the prompt
3. Return the processed/summarized result instead of the raw content

**Backend for summarization (owner's direction: "default same as agent"):**
- **Default:** Use the same backend/model as the agent (the `ModelBackend` from `ToolContext`). This is the simplest approach and ensures consistency.
- **Configurable:** Add a `webfetch_summarization_backend` config option that allows using a different (lighter/cheaper) model for summarization:
  ```toml
  [tools.webfetch]
  summarization_backend = "agent"  # "agent" (default) | "ollama" | "litellm"
  summarization_model = ""         # Empty = use agent's model; or specify a lighter model
  ```

**Why "same as agent" as default:**
- Simplest implementation — reuse the existing `ModelBackend` from `ToolContext`
- No additional backend configuration needed
- The agent's model is already capable of summarization
- Cost concern: webfetch is low-frequency (12 calls in the session, 1% of tool calls), so the cost of using the agent's model for summarization is negligible

**Coverage:** 12 WebFetch calls in the research session (all used the `prompt` parameter for targeted extraction).

### 7.11 `lint` Tool — MEDIUM (new, consolidated from ruff + mypy)

**Purpose:** Run ruff and mypy with structured parameters via a single consolidated tool.

**Owner confirmation (2026-07-16):** Lint consolidation (ruff+mypy into `lint` tool) accepted.

**Proposed interface:**
```python
async def lint(
  operation: str,       # "check" | "format" | "format_check" | "typecheck"
  ctx: ToolContext,
  paths: list[str] | None = None,  # Paths to check/format (default: project root)
  fix: bool = False,    # Auto-fix issues (for "check" operation)
  cwd: Annotated[str, PathArg("Working directory")] = ".",
  timeout_ms: int = 60000,
) -> ToolResult:
  """Run code quality tools (ruff for lint/format, mypy for type checking)."""
```

**Operations:**
- `check` -> `subprocess.run(["ruff", "check", ...])` — lint check
- `format` -> `subprocess.run(["ruff", "format", ...])` — format code
- `format_check` -> `subprocess.run(["ruff", "format", "--check", ...])` — check formatting without applying
- `typecheck` -> `subprocess.run(["mypy", ...])` — type checking

**Why consolidated:** Ruff and mypy are both code quality tools with nearly identical interfaces (paths, cwd, timeout). The `operation` enum distinguishes them: `"check"` and `"format"` map to ruff, `"typecheck"` maps to mypy. The LLM sees `lint(operation="typecheck")` which is just as clear as `mypy()`. This reduces tool count by 1 and groups related functionality.

**Coverage:** ~25 of 477 Bash commands (5.2% — ruff 3.1% + mypy 2.1%). Often redundant with `make lint` and `make typecheck`, but useful for targeted checks on specific files.

### 7.12 `uv` Tool — MEDIUM (new)

**Purpose:** Run uv package management commands.

**Proposed interface:**
```python
async def uv(
  operation: str,       # "sync" | "run" | "add" | "remove" | "lock" | "venv"
  ctx: ToolContext,
  args: list[str] | None = None,  # Additional args (e.g., package name for "add")
  cwd: Annotated[str, PathArg("Working directory")] = ".",
  timeout_ms: int = 120000,
) -> ToolResult:
  """Run uv and return its output."""
```

**Coverage:** ~20 of 477 Bash commands (4.2%). Covers `uv run`, `uv sync`, `uv add`, `uv lock`.

### 7.13 `update` Enhancement — LOW (existing tool)

**Purpose:** Add `replace_all` parameter for replacing all occurrences in one call.

**Coverage:** Some of the 146 Edit calls used `replace_all`. Low frequency but standard text editing.

---

## 8. Prioritization for 1.0.0

### Tier 1: Critical (must-have for 1.0.0)

| Item | Type | Justification | Bash Coverage |
|------|------|---------------|---------------|
| `make` tool | New tool | 14.7% of Bash commands; agents cannot run the project quality gate without it | ~70 commands |
| `read` offset/limit + package:// | Enhancement | 28% of Read calls + 13 cat + 4 wc + 40 Python inspection commands; large files unreadable efficiently without it; package introspection folded in | ~178 commands |
| `search` enhancements | Enhancement | 30.8% of Bash commands; context lines and case-insensitive are standard search features | ~147 commands |
| Protected files (Section 6.5) | Guardrail | Prevents agents from bypassing the controlled-tools model by editing Makefile/pyproject.toml | Security invariant |

**Tier 1 covers ~395 of 477 Bash commands (82.8%) plus major Read tool improvements plus a critical security guardrail.**

### Tier 2: High (should-have for 1.0.0)

| Item | Type | Justification | Bash Coverage |
|------|------|---------------|---------------|
| `pytest` tool | New tool | 7.3% of Bash directly + 7.8% via CLI testing; agents often need to run specific tests, not the full suite | ~72 commands |
| `file` tool | New tool | Basic file operations (delete, copy, move) are universally needed; agents are blocked without them | ~8 commands |
| `askuserquestion` tool | New tool | Static built-in; enables interactive workflows; only 4 uses but high-value when needed | ~4 commands |
| `github` tool | New tool | 6.5% of Bash; without a `run` tool, this is the ONLY path for GitHub interaction; design already exists; subcommand blocking is the whole point | ~31 commands |
| `lint` tool | New tool | 5.2% of Bash (ruff + mypy); needed for projects without Makefiles; owner wants BOTH make and underlying commands | ~25 commands |
| `uv` tool | New tool | 4.2% of Bash; covers package management operations; needed for 1.0.0 | ~20 commands |

**Owner direction (2026-07-16):** "I'm a fan of Makefiles, but we should provide access to these underlying commands." The `lint` (ruff+mypy) and `uv` tools are NOT deferred to post-1.0 — they are part of the 1.0.0 toolset. The owner wants both the `make` tool (for Makefile-based projects) AND the underlying command tools (for projects without Makefiles or for targeted checks).

**Tier 1 + Tier 2 covers ~461 of 477 Bash commands (96.6%). The 37 Python CLI testing commands are covered by `pytest` (Tier 2) and `make` (Tier 1). The 40 Python inspection commands are covered by `read` with `package://` support (Tier 1).**

### Tier 3: Medium (nice-to-have for 1.0.0)

| Item | Type | Justification | Bash Coverage |
|------|------|---------------|---------------|
| `git` add + checkout | Enhancement | ~15 git commands; agents can work around with two calls, but less efficient | ~15 commands |
| `webfetch` prompt param | Enhancement | 12 calls; useful for context-efficient web content extraction; uses agent's model by default | ~12 commands |

**Tier 1 + Tier 2 + Tier 3 covers ~461 of 477 Bash commands (96.6%). The remaining ~3.4% is: 4 one-off Python scripts (exec deferred), 7 echo/pwd/env, 3 sleep.**

### Tier 4: Low (post-1.0.0)

| Item | Type | Justification |
|------|------|---------------|
| `python` tool (exec operation) | New tool | Deferred per owner decision — "we need experience with the first toolset to see if this really blocks" |
| `update` replace_all | Enhancement | Small quality-of-life improvement |
| `list` offset/limit (2.20) | Enhancement | Already has `max_entries`; pagination is a minor improvement |
| `search` offset/limit (2.20) | Enhancement | Already has `max_results`; pagination is a minor improvement |
| `file` tool: archive/stat | Enhancement | Deferred per owner confirmation — basic ops suffice for 1.0 |

**All tiers combined cover ~96.6% of Bash commands.** The remaining ~3.4% (4 one-off Python scripts, 7 echo/pwd/env, 3 sleep) are either deferred to post-1.0 (exec), covered by ToolContext metadata (pwd), or not relevant for agentic work (sleep, echo, env).

---

## 9. Acceptance Criteria

### 9.1 Functional Criteria

- [ ] An agent can run `make check` using the `make` tool
- [ ] An agent can run `make test TEST=tests/test_foo.py` using the `make` tool
- [ ] An agent can inspect an installed package's API using `read("package://clevis")`
- [ ] An agent can view source code of a specific function using `read("package://clevis/get_config")`
- [ ] There is NO standalone `python` tool in 1.0.0 (exec deferred to post-1.0)
- [ ] CLI testing is achievable via `pytest` (write a test) or `make` (if a `run` target exists)
- [ ] An agent can run `pytest tests/test_foo.py -x` using the `pytest` tool
- [ ] An agent can run `lint(operation="check", paths=["src/"])` to run ruff check
- [ ] An agent can run `lint(operation="typecheck", paths=["src/"])` to run mypy
- [ ] An agent can run `lint(operation="format", paths=["src/"])` to run ruff format
- [ ] An agent can run `uv sync` using the `uv` tool
- [ ] An agent can read a large file (3500+ lines) efficiently using `read` with `offset` and `limit`
- [ ] An agent can search for a pattern with context lines and case-insensitive flag
- [ ] An agent can delete a file, copy a file, and move a file using the `file` tool
- [ ] An agent cannot delete or modify protected files (Makefile, pyproject.toml) via `write`, `update`, or `file` tools
- [ ] An agent can stage files with `git add` and switch branches with `git checkout`
- [ ] An agent can ask the user a question in interactive mode using `askuserquestion`
- [ ] An agent can fetch a web page and extract specific information using `webfetch` with `prompt`
- [ ] An agent can view a GitHub PR using the `github` tool
- [ ] The `github` tool rejects operations not in the configured allowlist (subcommand blocking)
- [ ] The `make` tool rejects targets with shell metacharacters
- [ ] All command-execution tools truncate output exceeding the configured limit
- [ ] All command-execution tools enforce timeouts

### 9.2 Coverage Criteria

- [ ] Overall tool coverage of a representative development session reaches 95%+ (up from ~62%)
- [ ] Bash command coverage reaches 95%+ (up from ~35%)
- [ ] Read tool coverage reaches 100% (up from ~72%)
- [ ] No "missing tool" errors during a typical Yoker development session (except one-off Python scripts, which are explicitly deferred)

### 9.3 Quality Criteria

- [ ] All new tools have unit tests with 80%+ coverage
- [ ] All new tools have PathGuardrail or equivalent security validation
- [ ] All new tools have timeout enforcement
- [ ] All new tools have output truncation
- [ ] All command-execution tools use `subprocess.run` with list args (no `shell=True`)
- [ ] `make check` is green
- [ ] Tool descriptions are clear enough for an LLM to use without examples

### 9.4 Documentation Criteria

- [ ] All new tools are documented in README.md
- [ ] All new tools have usage examples
- [ ] Security model for each new tool is documented
- [ ] The `package://` URL scheme for `read` is documented
- [ ] The `protected_files` guardrail is documented
- [ ] The deferred `python` tool (exec) is noted in post-1.0 roadmap documentation

---

## 10. Task Breakdown

### Phase 1: Critical Tools (Tier 1)

#### T1: `make` tool — Makefile target execution

**Satisfies:** 1.0.0 critical gap (14.7% of Bash commands)
**Depends on:** —

- [ ] T1.1 Implement `make` tool in `src/yoker/builtin/make.py`
  - `make(target, ctx, cwd, timeout_ms) -> ToolResult`
  - Target validation (reject shell metacharacters: `;`, `|`, `&`, `$`, backticks)
  - PathGuardrail on `cwd`
  - `subprocess.run(["make", target], ...)` — list args, no shell
  - Output truncation (default 100KB)
  - Timeout enforcement (default 5 minutes)
  - Return exit code, stdout, stderr separately
  - **Files:** `src/yoker/builtin/make.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:**
    - `make(target="check")` executes and returns output
    - `make(target="test")` executes and returns output
    - `make(target="rm -rf /")` is rejected (shell metacharacter in target)
    - Output exceeding 100KB is truncated with a truncation notice
    - Timeout is enforced
    - `cwd` outside project root is rejected

- [ ] T1.2 Add `MakeToolConfig` to Config
  - `timeout_ms`: default timeout (5 minutes)
  - `max_output_kb`: output truncation limit (100KB)
  - **Files:** `src/yoker/config/__init__.py` (modify)
  - **Acceptance:**
    - `Config().tools.make` has sensible defaults
    - Existing TOML files load unchanged

- [ ] T1.3 `make` tool tests
  - Test target execution
  - Test shell metacharacter rejection
  - Test output truncation
  - Test timeout enforcement
  - Test cwd guardrail
  - **Files:** `tests/test_builtin/test_make.py` (new)
  - **Acceptance:** All tests pass

#### T2: `read` enhancement — offset/limit + package:// introspection

**Satisfies:** 1.0.0 critical gap (28% of Read calls + 40 Python inspection commands)
**Depends on:** —

- [ ] T2.1 Add `offset` and `limit` to `read` tool
  - Add `offset: int | None = None` and `limit: int | None = None` parameters
  - If `offset` provided, skip to that line (1-indexed)
  - If `limit` provided, return at most that many lines
  - Return total line count in metadata
  - When offset/limit used, format output with line numbers (`cat -n` style)
  - **Files:** `src/yoker/builtin/read.py` (modify)
  - **Acceptance:**
    - `read("large_file.py", offset=100, limit=50)` returns lines 100-149
    - `read("file.py")` (no offset/limit) returns full file (unchanged behavior)
    - Total line count is returned in metadata
    - Line numbers are included when offset/limit is used

- [ ] T2.2 Add `package://` URL support to `read` tool
  - If `path` starts with `package://`, resolve to installed package source file
  - `package://clevis` -> `clevis/__init__.py` (package root)
  - `package://clevis/get_config` -> module containing `get_config`
  - Uses `importlib.util.find_spec()` to locate the package
  - Read-only introspection — zero risk, no code execution
  - **Files:** `src/yoker/builtin/read.py` (modify)
  - **Acceptance:**
    - `read("package://clevis")` returns the source of `clevis/__init__.py`
    - `read("package://yoker/api")` returns the source of `yoker/api.py`
    - `read("package://nonexistent")` returns a clear error
    - Package resolution uses `importlib.util.find_spec()` (no code execution)

- [ ] T2.3 `read` enhancement tests
  - Test reading with offset only
  - Test reading with limit only
  - Test reading with both offset and limit
  - Test offset beyond file length
  - Test limit exceeding file length
  - Test total line count in metadata
  - Test `package://` URL resolution
  - Test `package://` with nonexistent package
  - **Files:** `tests/test_builtin/test_read.py` (extend)
  - **Acceptance:** All tests pass

#### T3: `search` enhancement — context lines, case-insensitive, file-type filter, count mode

**Satisfies:** 1.0.0 critical gap (30.8% of Bash commands)
**Depends on:** —

- [ ] T3.1 Add new parameters to `search` tool
  - `case_insensitive: bool = False`
  - `context_before: int = 0` (lines before match)
  - `context_after: int = 0` (lines after match)
  - `include_pattern: str = ""` (file-type filter, e.g., `*.py`)
  - `exclude_pattern: str = ""` (file-type exclusion)
  - `count_only: bool = False` (return counts only, not content)
  - Cap `context_before`/`context_after` at 20 lines to prevent output flooding
  - **Files:** `src/yoker/builtin/search.py` (modify)
  - **Acceptance:**
    - `search(".", pattern="foo", case_insensitive=True)` matches "Foo" and "foo"
    - `search(".", pattern="class", context_before=2, context_after=2)` returns 2 lines before/after each match
    - `search(".", pattern="TODO", include_pattern="*.py")` only searches .py files
    - `search(".", pattern="TODO", count_only=True)` returns match counts, not content

- [ ] T3.2 `search` enhancement tests
  - Test case-insensitive search
  - Test context lines (before, after, both)
  - Test include/exclude patterns
  - Test count-only mode
  - Test context line cap (max 20)
  - **Files:** `tests/test_builtin/test_search.py` (extend)
  - **Acceptance:** All tests pass

### Phase 2: High-Priority Tools (Tier 2)

#### T4: `pytest` tool — test runner

**Satisfies:** 1.0.0 high-priority gap (7.3% of Bash directly + 7.8% via CLI testing)
**Depends on:** —

- [ ] T4.1 Implement `pytest` tool in `src/yoker/builtin/pytest.py`
  - `pytest(ctx, test_filter, flags, cwd, timeout_ms) -> ToolResult`
  - Build command list: `["pytest"]` + test_filter + flags
  - `subprocess.run(cmd_list, ...)` — list args, no shell
  - Flag validation: reject flags with shell metacharacters
  - PathGuardrail on `cwd` and `test_filter` (if path-like)
  - Output truncation (default 100KB)
  - Timeout enforcement (default 5 minutes)
  - **Files:** `src/yoker/builtin/pytest.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:**
    - `pytest()` runs all tests
    - `pytest(test_filter="tests/test_foo.py")` runs one test file
    - `pytest(flags=["-x", "--cov"])` applies flags
    - Flags with shell metacharacters are rejected
    - Timeout is enforced

- [ ] T4.2 `pytest` tool tests
  - **Files:** `tests/test_builtin/test_pytest.py` (new)
  - **Acceptance:** All tests pass

#### T5: `file` tool — file system operations

**Satisfies:** 1.0.0 high-priority gap (file operations)
**Depends on:** —

- [ ] T5.1 Implement `file` tool in `src/yoker/builtin/file.py`
  - Operations: `delete`, `copy`, `move`, `chmod`, `symlink`
  - `delete` on directories requires `recursive: bool = False`
  - PathGuardrail on all path arguments
  - `chmod` validates mode string (octal format)
  - `symlink` target validated (no escaping project root)
  - Protected files (Section 6.5) cannot be deleted/moved/overwritten
  - **Files:** `src/yoker/builtin/file.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:**
    - `file("delete", "/path/to/file")` deletes the file
    - `file("delete", "/path/to/dir", recursive=True)` deletes a directory
    - `file("copy", "/src", target="/dst")` copies
    - `file("move", "/src", target="/dst")` moves
    - `file("chmod", "/path", mode="755")` changes permissions
    - `file("symlink", "/target", target="/link")` creates symlink
    - Paths outside project root are rejected
    - Protected files (Makefile, pyproject.toml) cannot be deleted/moved

- [ ] T5.2 `file` tool tests
  - **Files:** `tests/test_builtin/test_file.py` (new)
  - **Acceptance:** All tests pass

#### T6: `askuserquestion` tool — interactive questions (static built-in)

**Satisfies:** 1.0.0 high-priority gap (interactive workflows)
**Depends on:** —

- [ ] T6.1 Implement `askuserquestion` tool as a static built-in
  - Registered in `__YOKER_MANIFEST__` (not Session-injected)
  - Interactive mode (TTY): present question via UI handler
  - Batch mode: read from stdin with timeout, or return default
  - Non-interactive (`yoker run`): return default immediately (no user present)
  - `choices` parameter: if provided, present as selection menu
  - Support "Other" option for custom input when choices are provided
  - Configurable: `tools.askuserquestion.enabled = false` disables entirely
  - **Files:** `src/yoker/builtin/askuserquestion.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:**
    - In interactive mode, question is presented to the user and response is returned
    - With `choices`, a selection menu is presented
    - In batch mode, stdin is read with timeout
    - In non-interactive mode, the default is returned
    - Timeout returns the default
    - Tool is listed in `__YOKER_MANIFEST__`

- [ ] T6.2 `askuserquestion` tests
  - **Files:** `tests/test_builtin/test_askuserquestion.py` (new)
  - **Acceptance:** All tests pass

#### T7: `github` tool — structured GitHub operations with subcommand blocking

**Satisfies:** 1.0.0 high-priority gap (6.5% of Bash commands)
**Depends on:** —
**Design:** `analysis/api-github-tool.md` and `analysis/security-github-tool.md` (existing)

- [ ] T7.1 Implement `github` tool (per existing design)
  - Read-only MVP: repo_view, issue_list/view, pr_list/view, workflow_list/view, release_list/view
  - `subprocess.run(["gh", ...], ...)` — list args, no shell
  - Operation allowlist (fixed enum, configurable per-project)
  - Subcommand blocking: operations not in allowlist are rejected (the whole point)
  - Timeout enforcement (default 30s)
  - Result count limits (max 100 for lists)
  - **Files:** `src/yoker/builtin/github.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:**
    - `github(operation="pr_view", repo="owner/repo")` returns PR info
    - `github(operation="issue_list", repo="owner/repo")` returns issues
    - Operation not in allowlist is rejected
    - Operations can be disabled via config (`allowed_operations`)
    - Timeout is enforced

- [ ] T7.2 `github` tool tests
  - **Files:** `tests/test_builtin/test_github.py` (new)
  - **Acceptance:** All tests pass

#### T8: `lint` tool — consolidated ruff + mypy (code quality)

**Satisfies:** 1.0.0 gap (5.2% of Bash commands — ruff 3.1% + mypy 2.1%)
**Depends on:** —
**Consolidation:** Replaces separate `ruff` and `mypy` tools (see Section 14)

- [ ] T8.1 Implement `lint` tool in `src/yoker/builtin/lint.py`
  - Operations: `check` (ruff check), `format` (ruff format), `format_check` (ruff format --check), `typecheck` (mypy)
  - `subprocess.run(["ruff", ...])` or `subprocess.run(["mypy", ...])` based on operation — list args, no shell
  - PathGuardrail on paths and cwd
  - `fix: bool = False` for auto-fix (ruff check --fix)
  - **Files:** `src/yoker/builtin/lint.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:**
    - `lint(operation="check", paths=["src/"])` runs ruff check
    - `lint(operation="format", paths=["src/", "tests/"])` runs ruff format
    - `lint(operation="typecheck", paths=["src/"])` runs mypy
    - `lint(operation="check", paths=["src/"], fix=True)` runs ruff check --fix
    - Paths outside project root are rejected
    - Timeout is enforced

- [ ] T8.2 `lint` tool tests
  - **Files:** `tests/test_builtin/test_lint.py` (new)
  - **Acceptance:** All tests pass

#### T9: `uv` tool — package management

**Satisfies:** 1.0.0 gap (4.2% of Bash commands)
**Depends on:** —

- [ ] T9.1 Implement `uv` tool in `src/yoker/builtin/uv.py`
  - Operations: `sync`, `run`, `add`, `remove`, `lock`, `venv`
  - `subprocess.run(["uv", ...], ...)` — list args, no shell
  - Operation allowlist (fixed enum)
  - **Files:** `src/yoker/builtin/uv.py` (new), `src/yoker/builtin/__init__.py` (manifest update)
  - **Acceptance:** All tests pass

### Phase 3: Medium-Priority Enhancements (Tier 3)

#### T10: `git` enhancement — add and checkout operations

- [ ] T10.1 Add `add` and `checkout` to git tool
  - `add` operation with `pathspec` argument
  - `checkout` operation with `branch` and `create` arguments
  - **Files:** `src/yoker/builtin/git.py` (modify)
  - **Acceptance:** All tests pass

#### T11: `webfetch` enhancement — prompt parameter

- [ ] T11.1 Add `prompt` parameter to `webfetch` tool
  - If provided, use the agent's ModelBackend to extract/summarize content based on the prompt
  - Configurable: `tools.webfetch.summarization_backend = "agent"` (default) or specify a lighter model
  - **Files:** `src/yoker/builtin/webfetch.py` (modify)
  - **Acceptance:** All tests pass

#### T12: Protected files guardrail — Makefile editing security

- [ ] T12.1 Add `protected_files` to `PermissionsConfig`
  - Denylist of files that cannot be written/updated by agents
  - Default: Makefile, makefile, GNUmakefile, Justfile, justfile, Taskfile.yml, pyproject.toml, tox.ini, setup.py, setup.cfg
  - Configurable per-project and per-user
  - **Files:** `src/yoker/config/__init__.py` (modify), `src/yoker/tools/guardrails/path.py` (modify)
  - **Acceptance:**
    - `write(path="Makefile", content="...")` is rejected
    - `update(path="pyproject.toml", ...)` is rejected
    - `write(path="src/main.py", content="...")` is allowed
    - Protected files list is configurable
    - Empty `protected_files` list disables all protections

### Phase 4: Optional / Post-1.0

#### T13: `python` tool with `exec` (post-1.0.0)

- [ ] T13.1 Evaluate whether one-off Python scripts are a blocking gap based on real-world experience
- [ ] T13.2 If needed, implement `python` tool with `exec` operation (opt-in, 6-layer defense)
  - See Section 7.4.3 for the design preserved from revision 4
  - See `analysis/api-python-tool.md` for the 6-layer defense model

#### T14: `update` replace_all (post-1.0.0)

- [ ] T14.1 Add `replace_all: bool = False` to `update` tool

#### T15: `file` tool extras (post-1.0.0)

- [ ] T15.1 Add `archive` operation (zip/unzip) to `file` tool
- [ ] T15.2 Add `stat` operation (file metadata: size, dates, permissions) to `file` tool

#### T16: Backlog cleanup

- [ ] T16.1 Update TODO.md — reclassify 2.15 (Python Tool) as P1, `inspect` folded into `read` enhancement (T2), `exec` deferred to post-1.0
- [ ] T16.2 Update TODO.md — reclassify 2.16 (Pytest Tool) as P2, implemented in T4
- [ ] T16.3 Update TODO.md — reclassify 2.17 (AskUserQuestion) as P2, implemented in T6
- [ ] T16.4 Update TODO.md — reclassify 2.18 (Dev Workflow Tools) as P1/P2, implemented in T1/T8 (lint consolidation)
- [ ] T16.5 Update TODO.md — reclassify 2.19 (GitHub Tool) as P2, implemented in T7
- [ ] T16.6 Update TODO.md — reclassify 2.22 (uv Tool) as P2, implemented in T9
- [ ] T16.7 Update TODO.md — expand 2.20 to include `read` offset/limit + package:// (covered by T2)
- [ ] T16.8 Add new backlog items for gaps not previously tracked: `file` tool, `search` enhancements, `git` add/checkout, `webfetch` prompt, `make` tool, protected files guardrail, `lint` tool (ruff+mypy consolidation)

---

## 11. Open Questions — All Resolved

1. **Specialized tool set (Section 6):** **RESOLVED** — Owner agreed with the revised approach (specialized tools, not `run` tool). Confirmed in revision 2 feedback.

2. **Tier 1 scope (Section 8):** **RESOLVED** — Owner wants `ruff`/`mypy`/`uv` as part of 1.0.0 (not deferred). They are in Tier 2. The `make` tool remains Tier 1.

3. **`webfetch` prompt extraction (Section 7.10):** **RESOLVED** — Owner wants the `prompt` parameter to use the same model as the agent by default, with a configurable option to use a different/lighter model. Implementation: use the `ModelBackend` from `ToolContext` by default, configurable via `tools.webfetch.summarization_backend`.

4. **`askuserquestion` tool placement (Section 7.7):** **RESOLVED** — Owner clarified: "AskUserQuestion is not session related, its available to the agent (unless disabled) in interactive sessions. You can't 'ask' when there is no 'user'." It is a **static built-in tool** (in the manifest), not Session-injected. Available in interactive sessions, returns default in non-interactive mode.

5. **`github` tool importance (Section 7.8):** **RESOLVED** — Owner confirmed: "github is required, note that we need to be able to block certain subcommands (that's the whole point)." It is Tier 2 with configurable subcommand blocking via operation allowlist.

6. **`file` tool scope (Section 7.6):** **RESOLVED** — Owner said "defer extras." File tool gets basic operations (delete, copy, move, chmod, symlink). Archive/stat deferred to post-1.0.

7. **Tier 3 tools (Section 8):** **RESOLVED** — Owner said: "I'm a fan of Makefiles, but we should provide access to these underlying commands." `ruff`, `mypy`, and `uv` are NOT deferred — they are part of 1.0.0 (Tier 2). The owner wants both `make` and the underlying command tools.

8. **Priority confirmation (Section 8):** **RESOLVED** — Revised prioritization confirmed by owner feedback. Tier 1: make, read (offset/limit + package://), search, protected files. Tier 2: pytest, file, askuserquestion, github, lint (ruff+mypy), uv. Tier 3: git enhancement, webfetch prompt.

9. **Python tool security (Section 7.4):** **RESOLVED** — Owner decided: "defer exec... we need experience with the first toolset to see if this really blocks." The `python` tool is NOT part of 1.0.0. The `inspect` operation is folded into the `read` tool as `package://` URL support. The `exec` operation is deferred to post-1.0. The `run_module` operation is dropped entirely. CLI testing goes through `pytest` and `make` only. One-off scripts are not supported in 1.0.0.

10. **Makefile editing security (Section 6.5):** **RESOLVED** — Owner accepted the proposed `protected_files` denylist in `PermissionsConfig`. The list includes Makefile, makefile, GNUmakefile, Justfile, justfile, Taskfile.yml, pyproject.toml, tox.ini, setup.py, setup.cfg. Configurable per-project and per-user.

11. **Tool consolidation (Section 14):** **RESOLVED** — Owner accepted the consolidation of `ruff` + `mypy` into a single `lint` tool. Other tools remain separate due to different parameter semantics.

---

## 12. Dependencies

- **No external dependencies** — all tools use Python standard library (`subprocess`, `pathlib`, `re`, `ast`, `inspect`, `importlib`, etc.) and existing Yoker infrastructure (ToolContext, PathGuardrail, ToolResult)
- **Config changes** — `MakeToolConfig`, `PytestToolConfig`, `LintToolConfig`, `UvToolConfig`, `FileToolConfig`, `GitHubToolConfig`, `AskUserQuestionToolConfig` need to be added to the Config dataclass; `PermissionsConfig` needs `protected_files` field; this follows the existing pattern (`GitToolConfig`, `SearchToolConfig`, etc.)
- **Manifest update** — `__YOKER_MANIFEST__` needs to include `make`, `pytest`, `file`, `askuserquestion`, `github`, `lint`, `uv` (all static tools)
- **Guardrail update** — `PathGuardrail` needs `protected_files` check for `write` and `update` tools
- **Documentation** — README.md and tool docs need updates for all new/enhanced tools
- **Existing research** — `analysis/api-github-tool.md` (GitHub tool design, complete), `analysis/security-github-tool.md` (GitHub security analysis, complete). The `analysis/api-python-tool.md` (6-layer defense for exec) is preserved for post-1.0 reference.

---

## 13. What Changed from the Previous Draft

| Aspect | Revision 2 | Revision 3 | Revision 4 | Revision 5 (this draft — FINAL) |
|--------|------------|------------|------------|-------------------------------|
| Python tool | Monolithic `python(code=...)` with 6-layer defense | Two operations: `inspect` + `exec`; `run_module` dropped | `inspect` + `exec` (2 operations); `run_module` attack vector analyzed | **NO standalone Python tool for 1.0.0**. `inspect` folded into `read` as `package://` URLs. `exec` deferred to post-1.0. `run_module` dropped. |
| Python coverage | 63 commands (13.2%) | 44 directly + 37 via pytest/make | 44 directly + 37 via pytest/make | 40 via `read` package:// + 37 via pytest/make = 77/81 (95%). 4 one-off scripts deferred. |
| New tool count | 9 | 8 (ruff+mypy -> lint) | 8 | **7** (python tool removed from 1.0.0) |
| Makefile security | Not addressed | New Section 6.5 | `protected_files` denylist | **Accepted** — `protected_files` in `PermissionsConfig` |
| webfetch prompt | Open question | Answered: agent's model | Answered: agent's model | **Accepted** |
| askuserquestion | Open question | Static built-in | Static built-in | **Accepted** |
| file tool scope | Open question | Defer extras | Defer extras | **Accepted** |
| ruff/mypy/uv tier | Tier 3 (deferred) | Tier 2 | Tier 2 | **Accepted** — Tier 2 |
| Tool consolidation | Not analyzed | ruff+mypy -> lint | ruff+mypy -> lint | **Accepted** |
| Lint consolidation | Open question | Proposed | Proposed | **Accepted** |
| Open questions | 8 open | 3 open | 3 open | **ALL RESOLVED** |

### Revision 5 Changes (owner defers `exec` entirely)

| Aspect | Revision 4 | Revision 5 (FINAL) |
|--------|------------|---------------------|
| Python tool | `inspect` + `exec` (2 operations) | **NO standalone tool** — `inspect` folded into `read` as `package://` URLs; `exec` deferred to post-1.0 |
| New tool count | 8 | **7** (python tool removed) |
| Bash coverage | ~97.5% | **~96.6%** (4 one-off scripts now uncovered) |
| Python command coverage | 44/81 directly + 37 via pytest/make | 40/81 via `read` package:// + 37 via pytest/make = 77/81 (95%) |
| Open questions | 3 open (protected files, lint consolidation, Python tiered) | **ALL RESOLVED** |
| MBI scope | Draft | **Finalized** |

---

## 14. Tool Consolidation Analysis

**Owner question (2026-07-16):** "what tools could be consolidated do you think?"

**Owner decision (2026-07-16):** Lint consolidation accepted. All other tools remain separate.

### 14.1 Candidates for Consolidation

**`ruff` + `mypy` -> `lint` tool?**

Both are code quality tools that check Python code. A combined `lint` tool could have:
```python
async def lint(
  operation: str,       # "check" | "format" | "format_check" | "typecheck"
  ctx: ToolContext,
  paths: list[str] | None = None,
  fix: bool = False,    # Auto-fix (for ruff check)
  cwd: Annotated[str, PathArg("Working directory")] = ".",
  timeout_ms: int = 60000,
) -> ToolResult:
```

**Verdict: CONSOLIDATE (accepted).** Ruff and mypy are both code quality tools with nearly identical interfaces (paths, cwd, timeout). The `operation` enum distinguishes them: `"check"` and `"format"` map to ruff, `"typecheck"` maps to mypy. The LLM sees `lint(operation="typecheck")` which is just as clear as `mypy()`. The implementation dispatches to `subprocess.run(["ruff", ...])` or `subprocess.run(["mypy", ...])` based on the operation. This reduces tool count by 1 and groups related functionality.

**`make` + `pytest` + `lint` + `uv` -> single `dev` tool?**

**Verdict: DO NOT CONSOLIDATE.** These tools have different parameter signatures:
- `make` has `target` (string)
- `pytest` has `test_filter` (string) and `flags` (list)
- `lint` has `paths` (list) and `fix` (bool)
- `uv` has `args` (list) for package names

A single `dev` tool would need a union of all these parameters, most of which would be unused for any given operation. The LLM would have to parse a large operation enum AND a large parameter set. This is worse for LLM ergonomics than separate tools with small, focused parameter sets. The existing `git` tool works because all git operations share similar parameters (path, flags); the dev tools do not share this property.

**`pytest` into `make` tool?**

Could `make(target="test")` replace `pytest()`? No — `make test` runs the full suite, while `pytest(test_filter="tests/test_foo.py::TestClass")` runs a specific test. The `pytest` tool provides granularity that `make` cannot. They serve different use cases.

**`uv` into `python` tool?**

Not applicable — the `python` tool is deferred to post-1.0. `uv` is a package management tool, not a code execution tool.

**`file` into `write`/`update` tools?**

Could `write(operation="delete")` replace `file(operation="delete")`? No — `write` creates/overwrites files, `file` performs filesystem operations (delete, copy, move, chmod, symlink). Conflating them would make the `write` tool's semantics unclear ("write" implies creating content, not deleting files).

### 14.2 Recommended Consolidation

| Original Tools | Consolidated Tool | Operations | Verdict |
|----------------|-------------------|------------|---------|
| `ruff` + `mypy` | `lint` | `check`, `format`, `format_check`, `typecheck` | **Consolidate (accepted)** — similar interfaces, same domain |
| `make` + `pytest` | — | — | **Keep separate** — different parameter semantics |
| `make` + `lint` | — | — | **Keep separate** — `make` runs targets, `lint` checks files |
| `pytest` + `lint` | — | — | **Keep separate** — different parameter semantics |
| `uv` + anything | — | — | **Keep separate** — unique domain (package management) |
| `file` + `write` | — | — | **Keep separate** — different semantics |
| `github` + anything | — | — | **Keep separate** — unique domain with subcommand blocking |

### 14.3 Final Tool List for 1.0.0

After consolidation and the owner's decision to defer `exec`, the new tool count is **7**:

| Tool | Operations | Tier |
|------|------------|------|
| `make` | `target` | Tier 1 |
| `pytest` | `test_filter`, `flags` | Tier 2 |
| `file` | `delete`, `copy`, `move`, `chmod`, `symlink` | Tier 2 |
| `askuserquestion` | (interactive) | Tier 2 |
| `github` | `repo_view`, `issue_list`, `pr_view`, ... | Tier 2 |
| `lint` | `check`, `format`, `format_check`, `typecheck` | Tier 2 |
| `uv` | `sync`, `run`, `add`, `remove`, `lock`, `venv` | Tier 2 |

**7 new tools + 4 enhancements + 1 guardrail (protected files) = 12 work items for 1.0.0.**

### 14.4 Enhancements to Existing Tools

| Tool | Enhancement | Tier |
|------|------------|------|
| `read` | `offset`/`limit` + line count metadata + `package://` URL support | Tier 1 |
| `search` | context lines, case-insensitive, file-type filter, count mode | Tier 1 |
| `git` | `add` and `checkout` operations | Tier 3 |
| `webfetch` | `prompt` parameter for content extraction/summarization | Tier 3 |

### 14.5 Deferred to Post-1.0

| Item | Reason |
|------|--------|
| `python` tool with `exec` operation | Owner: "defer exec... we need experience with the first toolset to see if this really blocks" |
| `update` replace_all | Small quality-of-life improvement |
| `list` offset/limit pagination | Already has `max_entries`; minor improvement |
| `search` offset/limit pagination | Already has `max_results`; minor improvement |
| `file` tool: archive/stat | Owner: "defer extras" — basic ops suffice for 1.0 |

---

## 15. Final MBI Summary

### 15.1 Total New Tools for 1.0.0

**7 new tools:**
1. `make` — Makefile target execution (Tier 1)
2. `pytest` — test runner with structured parameters (Tier 2)
3. `file` — file system operations: delete, copy, move, chmod, symlink (Tier 2)
4. `askuserquestion` — interactive user questions, static built-in (Tier 2)
5. `github` — structured GitHub operations with subcommand blocking (Tier 2)
6. `lint` — consolidated ruff + mypy code quality tool (Tier 2)
7. `uv` — package management operations (Tier 2)

### 15.2 Total Enhancements to Existing Tools

**4 enhancements:**
1. `read` — `offset`/`limit` + line count metadata + `package://` URL support for package introspection (Tier 1)
2. `search` — context lines, case-insensitive, file-type filter, count mode (Tier 1)
3. `git` — `add` and `checkout` operations (Tier 3)
4. `webfetch` — `prompt` parameter for content extraction/summarization (Tier 3)

### 15.3 Guardrails

**1 guardrail:**
1. `protected_files` — denylist of execution-configuration files (Makefile, pyproject.toml, etc.) that cannot be written/updated by agents (Tier 1)

### 15.4 Final Tier Breakdown

| Tier | Items | Work Items |
|------|-------|------------|
| Tier 1 (Critical) | `make` tool, `read` enhancement, `search` enhancement, `protected_files` guardrail | 4 |
| Tier 2 (High) | `pytest` tool, `file` tool, `askuserquestion` tool, `github` tool, `lint` tool, `uv` tool | 6 |
| Tier 3 (Medium) | `git` enhancement, `webfetch` enhancement | 2 |
| **Total for 1.0.0** | | **12 work items** |

### 15.5 Final Coverage

| Metric | Before | After (1.0.0) |
|--------|--------|---------------|
| Overall tool coverage | ~62% | ~97% |
| Bash command coverage | ~35% | ~96.6% |
| Read tool coverage | ~72% | ~100% |

**Uncovered (3.4% of Bash):**
- 4 one-off Python scripts (0.8%) — `exec` deferred to post-1.0
- 7 echo/pwd/env (1.5%) — `pwd` via ToolContext metadata; `echo`/`env` not relevant
- 3 sleep (0.6%) — not relevant for agentic work

### 15.6 Explicitly Deferred to Post-1.0

| Item | Rationale |
|------|-----------|
| `python` tool with `exec` operation | Owner: "defer exec... we need experience with the first toolset to see if this really blocks." If real-world experience shows one-off scripts are a blocking gap, a `python` tool with `exec` (opt-in, 6-layer defense) will be added. Design preserved in Section 7.4.3 and `analysis/api-python-tool.md`. |
| `run_module` operation | Dropped entirely — unpreventable attack vector (agent writes malicious module, runs it). |
| `update` replace_all | Small quality-of-life improvement. |
| `list`/`search` offset/limit pagination | Already has `max_entries`/`max_results`; minor improvement. |
| `file` tool: archive/stat | Owner: "defer extras" — basic ops suffice for 1.0. |

### 15.7 Work Item Count

- **7 new tools** (make, pytest, file, askuserquestion, github, lint, uv)
- **4 enhancements** (read, search, git, webfetch)
- **1 guardrail** (protected_files)
- **= 12 work items for 1.0.0**