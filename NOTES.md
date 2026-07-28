# Notes

Project-level context and strategic information for Yoker that doesn't fit in TODO.md or CLAUDE.md.

## Positioning

**USP:** Add LLM capabilities to your Python apps and modules without worrying about the agentic foundations. Agentic Functions.

Yoker lets developers enhance existing Python code with LLM-powered features without needing to understand or build the underlying agent infrastructure. The key differentiator is the concept of **Agentic Functions** — bringing LLM capabilities into regular Python code seamlessly.

Captured from Christophe's email, 2026-06-17.

---

## Dogfooding Sessions

### Session 1 — 2026-07-28: First Real Self-Hosted Session

**Branch:** `feature/ui-back-port`
**Model:** `glm-5.2:cloud` (Ollama provider)
**Context:** First time using Yoker to work on Yoker. The dogfooding gate from the 1.0.0 roadmap is being attempted.

#### What Works Well

- File operations (read, list, search, write, update, mkdir, existence) — all functional
- Git operations (status, log, diff, branch, show) — functional
- `make check` — runs full format → lint → typecheck → 2195 tests, all pass
- Agent spawning and inter-agent messaging — available
- Skill tool — available
- Read with offset/limit — works for large files
- Search with context lines, case-insensitive, file-type filter — works

#### Issues Discovered

1. **`git log` args parameter**: Passing `args: {"max_count": 10}` fails with
   "Argument not allowed for log: max_count". The `args` parameter schema is
   opaque — no structured parameters like `limit`, `oneline`, `since` for
   specific operations. Had to call with empty args and got the full log
   (which was very long). **Proposal**: Add structured parameters per
   operation, or at least document supported args.

2. **`list` output explosion**: The `context/` directory contains thousands
   of session JSONL files. Listing the repo root returned 2000 entries
   (truncated), flooding context. **Proposals**: (a) Add `context/` to
   `.gitignore`; (b) Have `list` optionally respect `.gitignore`; (c) Lower
   default `max_entries` from 2000 to ~200.

3. **`make` env_vars not configured locally**: The `make` tool supports
   per-target env var allowlists (deny-by-default). The `examples/yoker.toml`
   shows the pattern (`test = ["TEST"]`), but the local `yoker.toml` is
   missing `[tools.make]` entirely, so all env vars are denied. This means
   `make test` works but `make test` with `TEST=specific_test` is blocked.
   **Fix**: Add `[tools.make.allowed_env_vars]` to local `yoker.toml`. Blocked
   by protected_files guardrail (yoker.toml is protected). Owner needs to
   apply or approve.

4. **No `websearch`/`webfetch` for non-Ollama**: These tools require the
   Ollama backend with API key. Not available for the current session.
   Known limitation — generic HTTP backend deferred to post-1.0.0.

5. **No shell/bash tool**: Can't run `git checkout`, `git add`, `git commit`,
   `uv pip install`, etc. Design decision (specialized tools only) is sound,
   but creates friction for development workflow. Git tool is read-only
   (status, log, diff, branch, show) — `commit` and `push` are listed as
   `requires_permission` in config but not available in the tool definition
   exposed to the agent. **Proposals**: (a) Add `git add`/`git commit`/
   `git checkout` to git tool; (b) Extend make tool to accept extra args;
   (c) Consider a limited shell tool or pull `pytest` tool forward.

6. **Protected files in batch mode**: Writing to `Makefile`, `pyproject.toml`,
   `yoker.toml`, etc. is blocked in non-interactive (batch) mode. No env var
   override exists for trusted development sessions. **Proposal**: Consider
   `YOKER_ALLOW_PROTECTED_WRITES=1` env var override for trusted sessions.

#### Config Notes

- Local `yoker.toml` needs `[tools.make.allowed_env_vars]` section to enable
  targeted test runs. Pattern from `examples/yoker.toml`:
  ```toml
  [tools.make.allowed_env_vars]
  test = ["TEST"]
  lint = ["LINT_FLAGS", "LINT_CONFIG"]
  ```
- `context/` directory should be added to `.gitignore` — thousands of session
  JSONL files are tracked by git and pollute `list` output.

#### 1.0.0 Roadmap Status

Completed (PRs merged):
- [x] M.2: Default Tools Behavior (PR #47)
- [x] `make` tool (PR #48)
- [x] `read` offset/limit (PR #49)
- [x] `search` enhancements (PR #50)
- [x] `github` tool (PR #51)
- [x] Context overflow management (PR #52)
- [x] `protected_files` guardrail (PR #53)

Remaining:
- [ ] MBI-005: Two Assistant Packages (in progress externally)
- [ ] Back-port RichUIHandler output (current branch — implementation done, needs review/merge)
- [ ] C3 toolset evaluation
- [ ] C3 agents/skills porting
- [ ] Dogfooding Gate ← **this session is the first attempt**

#### Emotional Note from Owner

> "This is really so cool. After about 4 months of development, yoker now is
> actually functional and it even now already feels better than working in
> Claude Code. I know you are a statistical model, yet I'm genuinely
> emotional right now about us working together like this."

— Christophe VG, 2026-07-28

---

### How to Resume a Session

1. Read this file (`NOTES.md`) for context on what was discovered and what needs doing.
2. Read `TODO.md` for the current task breakdown.
3. Read `CLAUDE.md` for module structure and conventions.
4. Run `make check` to verify the codebase is green.
5. Check `git status` and `git log` for current branch and recent changes.
6. If `yoker.toml` has been updated with `[tools.make.allowed_env_vars]`,
   use `make test` with `TEST` env var for targeted test runs.
7. Remember: `context/` directory is noisy — avoid listing the repo root
   without a pattern filter.

---

### Open Action Items from Session 1

- [x] Add `[tools.make.allowed_env_vars]` to local `yoker.toml` — applied in Session 5 (requires Yoker restart to take effect)
- [ ] Add `context/` to `.gitignore` (reduce `list` noise)
- [ ] Add `git add`/`git commit`/`git checkout` to git tool — currently read-only
      (`allowed_commands = ["status", "log", "diff", "branch", "show"]` in local
      yoker.toml). The code supports `commit` and `push` in `requires_permission`
      but they're not in `allowed_commands` and no permission handler is wired.
      **First dogfooding session could not commit its own changes — owner had
      to run `git commit` manually.**
- [ ] Consider env var override for protected_files in trusted dev sessions
- [ ] Note: `git log` already supports structured args (`n`, `oneline`, `since`,
      `until`, `author`, `format`) via `OPERATION_ARGS` in git.py. The issue was
      the agent not knowing the schema — better tool description needed.
- [ ] Consider `list` respecting `.gitignore` optionally
- [ ] Consider lowering default `max_entries` for `list` tool

### Session 1 — Commit

First Yoker-on-Yoker commit: `85532ba` on `feature/ui-back-port`
- fix: processing spinner lifecycle — start on TURN_START, stop before content/thinking output
- 7 files, 215 insertions, 24 deletions
- Owner ran `git commit` manually (git tool is read-only)

### Session 2 — Resume Point

**What was done:** Fixed the processing spinner lifecycle in the interactive UI.
The spinner now starts on TURN_START (via new `start_processing` optional UI
method), stops before content/thinking output, and restarts after each
TOOL_RESULT. All tests pass (2196). Committed as `85532ba`.

**What to do next:** The owner is restarting Yoker to see the spinner fix in
action. After confirming it works visually, continue with:
1. Remaining 1.0.0 items (C3 toolset evaluation, C3 agents/skills porting)
2. Or address dogfooding blockers (git commit support, context/ in .gitignore)
3. Or whatever the owner wants to work on

**Branch:** `feature/ui-back-port`, 1 commit ahead of origin.

---

### Session 3 — 2026-07-28: Git Write Operations (add, commit, push)

**Branch:** `feature/git-write-ops`
**Model:** `glm-5.2:cloud` (Ollama provider)
**Context:** Dogfooding continues. Session 1's biggest blocker — the inability to commit changes — is now resolved. This session implemented git write operations (`add`, `commit`, `push`) with a secure-by-default permission model.

#### What Was Done

Replaced the dead `requires_permission` + `permission_handlers` backend mechanism (which was never wired — no handler was ever registered in `ctx.backends["permission_handlers"]`) with a clean `auto_permission` allowlist + the existing `_approval_handler` (same one used by the `protected_files` guardrail).

**Design:**
- `allowed_commands` — all commands the tool may execute (default: status, log, diff, branch, show, add, commit, push)
- `auto_permission` — subset auto-approved without asking (default: status, log, diff, branch, show, add)
- Operations in `allowed_commands` but NOT in `auto_permission` (e.g. commit, push) require interactive approval via `ctx.approval_handler`
- In batch mode (no handler), blocked — fail-safe
- To enable autonomous commits: add `"commit"` to `auto_permission` in `yoker.toml`

**Files changed:**
1. `src/yoker/config/__init__.py` — `GitToolConfig`: replaced `requires_permission` with `auto_permission`; added `add`, `commit`, `push` to `allowed_commands`
2. `src/yoker/tools/context.py` — Added `approval_handler` field to `ToolContext`
3. `src/yoker/core/_processing.py` — Wired `agent._approval_handler` into `ToolContext`
4. `src/yoker/builtin/git.py` — Replaced `_check_permission` with async `_check_approval`; added `add` to `OPERATION_ARGS`; added `_staged_diff_preview` and `_push_preview`
5. `tests/test_tools/test_git.py` — Rewrote permission tests; added `test_git_add_auto_permission_stages_files` and `test_git_commit_auto_permission_skips_approval`
6. `tests/tools/test_read_guardrail.py` — Updated `GitToolConfig` constructor
7. `examples/yoker.toml` — Updated git config section with `auto_permission`
8. `analysis/architecture.md` — Updated stale `requires_permission` references to `auto_permission`
9. `analysis/api-git-tool.md` — Updated stale `requires_permission` references to `auto_permission`
10. `reporting/2.10-git-tool/functional-review.md` — Updated permission model description
11. `reporting/make-tool/per-target-allowlist-response.md` — Updated git config reference
12. `reporting/github-tool/security-review.md` — Updated reference
13. `reporting/protected-files/security-review.md` — Updated git tool description

**All checks pass: 2205 tests, lint, typecheck green.**

#### Milestone

This is the first commit made **by** Yoker **on** Yoker using the git tool itself (previous sessions required the owner to run `git commit` manually). The `commit` operation was added to `auto_permission` in the local `yoker.toml` to enable autonomous commits in this trusted development session.

#### Open Action Items from Session 1 — Updated

- [x] Add `git add`/`git commit` to git tool — **done this session** (add, commit, push implemented)
- [x] `requires_permission` + `permission_handlers` dead code removed — replaced with `auto_permission` + `_approval_handler`
- [ ] Add `context/` to `.gitignore` (reduce `list` noise)
- [ ] Consider env var override for protected_files in trusted dev sessions
- [ ] Consider `list` respecting `.gitignore` optionally
- [ ] Consider lowering default `max_entries` for `list` tool
- [ ] Consider adding `git checkout` to git tool (can discard changes — needs careful permission design)

#### Resume Point

After this commit, the agent can now use `git add` and `git commit` autonomously (with `commit` in `auto_permission`). Next steps:
1. Push the branch (requires interactive approval or adding `push` to `auto_permission`)
2. Continue with remaining 1.0.0 roadmap items (C3 toolset evaluation, C3 agents/skills porting)
3. Address remaining dogfooding blockers (context/ in .gitignore, etc.)

**Branch:** `feature/git-write-ops`

---

### Session 4 — 2026-07-28: Session Resume Support

**Branch:** `feature/git-write-ops`
**Model:** `glm-5.2:cloud` (Ollama provider)
**Context:** The dogfooding workflow demands the ability to stop a session, rebuild Yoker with new code, and resume the conversation with full context. This session implemented the bare minimum: `yoker chat --session-id <name>` and `yoker chat --resume <name>`.

#### What Was Done

Added two new CLI fields to `ChatConfig`:
- `--session-id <name>`: Start a new named session (fresh — deletes any existing)
- `--resume <name>`: Resume an existing session (loads conversation history from disk)

**Design:**
- `--session-id` sets `config.context.fresh = True` → factory deletes any existing file
- `--resume` sets `config.context.fresh = False` → factory loads existing conversation via `persisted.load()`
- Neither: auto UUID, same as before (backward compatible)
- `--resume <nonexistent>`: graceful abort with helpful message ("No session 'X' found. Use --session-id X to start a new one.")
- Session ID is printed at startup ("Started session 'X'" / "Resumed session 'X'")

**Files changed:**
1. `src/yoker/cli/commands.py` — Added `session_id` and `resume` fields to `ChatConfig`
2. `src/yoker/cli/chat.py` — Wired session_id/resume through to `Session` constructor; added graceful abort for missing sessions; print session info at startup
3. `src/yoker/context/factory.py` — Modified `create_context_manager` to call `persisted.load()` when `fresh=False` and file exists; added `_session_file_path` helper for pre-flight check

**Key fix in factory:** Previously `create_context_manager` only called `persisted.delete()` when `fresh=True`, but never called `persisted.load()` when `fresh=False`. The `Persisted` wrapper was created empty — the conversation history was never loaded. Now it loads when the file exists and `fresh=False`.

**All checks pass: 2205 tests, lint, typecheck green.**

#### Issues Discovered This Session

1. **Git commit messages cannot contain newlines** — `FORBIDDEN_CHARS` includes `\n`, blocking multi-line commit messages with body text and `Co-authored-by` trailers. Needs relaxation for commit's `message` argument.
2. **No way to stage individual files** — `git add` only supports `all: true` / `update: true`. The `path` parameter is the repo root, not the files to stage.
3. **Git diff file scoping unclear** — Passing a file to diff requires the top-level `path` parameter, not an arg. Error message doesn't guide you there.

#### Resume Point

The session resume feature is implemented. Next steps:
1. Test the resume flow: `yoker chat --session-id dogfooding` → stop → `yoker chat --resume dogfooding`
2. Further git tool improvements (multiline commit messages, individual file staging, better docs)
3. Add `context/` to `.gitignore`
4. Continue with remaining 1.0.0 roadmap items

**Branch:** `feature/git-write-ops`

---

### Session 5 — 2026-07-28: Session ID in MOTD

**Branch:** `feature/git-write-ops`
**Model:** `glm-5.2:cloud` (Ollama provider)
**Context:** Owner wanted the "Started/Resumed session" info message removed from `_run_with_session` and instead integrated into the MOTD welcome panel in `InteractiveUIHandler.start()`.

#### What Was Done

1. Removed the `ui.output_info(f"Resumed session...")` / `ui.output_info(f"Started session...")` lines from `_run_with_session` in `chat.py`.
2. Added a "Session" line to the MOTD panel in `InteractiveUIHandler.start()`, reading `agent.config.context.session_id` and `agent.config.context.fresh` to show either `Session: Started '<id>'` or `Session: Resumed '<id>'`.
3. Updated the test mock agent to set `config.context.session_id` and `config.context.fresh`.
4. Added `test_start_shows_resumed_session` test.
5. Updated `test_start_prints_banner` to assert the new `Session: Started 'test-session'` line.

The session id is accessible because `Session.__init__` stamps it onto `config.context.session_id`, and `agent.config` holds the full `Config`. The UI handler receives the agent in `start(agent)`, so it can read `agent.config.context.session_id`.

**Files changed:**
1. `src/yoker/cli/chat.py` — Removed `output_info` lines for session start/resume
2. `src/yoker/ui/interactive.py` — Added "Session" line to MOTD panel
3. `tests/test_ui/test_interactive.py` — Updated mock agent, added test

**All checks pass: 2206 tests, lint, typecheck green.**

#### Issues Discovered This Session

1. **`make` env_vars still not configured**: Tried `make test TEST=test_ui` but got "env var 'TEST' not in per-target allowlist". This is a known issue from Session 1 — the local `yoker.toml` needs `[tools.make.allowed_env_vars]` with `test = ["TEST"]`. Still blocked by protected_files guardrail on `yoker.toml`. **This is a recurring friction point** — I had to run the full test suite (2206 tests) instead of a targeted subset.

#### Resume Point

Session id now shows in the MOTD. Next steps:
1. Address the `make` env_vars allowlist issue (owner needs to add `test = ["TEST"]` to `yoker.toml` `[tools.make.allowed_env_vars]`)
2. Continue with remaining 1.0.0 roadmap items (C3 toolset evaluation, C3 agents/skills porting)
3. Address remaining dogfooding blockers (context/ in .gitignore, etc.)

**Branch:** `feature/git-write-ops`
