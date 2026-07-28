# UX Review: Back-port RichUIHandler Output Improvements to InteractiveUIHandler

**Task**: Back-port RichUIHandler output improvements to InteractiveUIHandler
**Date**: 2026-07-28
**Reviewer**: UI/UX Designer
**Status**: Review Complete — Approved with Required Adjustments

## Executive Summary

The proposed merge — RichUIHandler's stable, append-only `console.print` output + old InteractiveUIHandler's `prompt_toolkit` input (lazy `PromptSession`, `erase_when_done=True`, `output_prompt` Panel) — is the right UX direction. Treating the terminal like a stdout log (append-only, no re-rendering) is the dominant pattern in modern agent CLIs (Claude Code, Codex, Aider) precisely because it produces copy-pasteable, scroll-back-stable transcripts. The current Live-based InteractiveUIHandler re-renders the active region every 250 ms, which fights the terminal's own scrollback model and causes the well-known "disappearing output" bug when users scroll during a stream.

The direction is endorsed. The plan, however, drops two UX affordances the user currently relies on, and one of them (processing feedback) must be restored in some form before this can ship. The sections below call out the required adjustments and the cases where the proposed change actually regresses on the user's goal.

## Scope of Review

This review covers only the user-facing UX implications of the merge. It does not assess:
- API design or `UIHandler` protocol compliance (defer to API Architect)
- Security implications of the lazy `PromptSession` (defer to security reviewer)
- Test coverage

A coordination note for the API Architect is included at the end where the proposed change may surface a protocol gap.

## Confirmed Design Decisions — UX Verdict

### 1. RichUIHandler as base (append-only `console.print`, no Live region) — Endorsed

**Verdict**: Correct direction. This is the single biggest UX win in the proposal.

**Why it matches the user's goal**: The user wants "output to be more stable and behaving like basic stdout." Rich's `Live` region is the opposite of stdout — it rewrites the same screen lines each refresh tick. Once you stop streaming, the Live region collapses to whatever the final renderable was, and any intermediate state (in-progress chunks, partial tool args) is lost to scrollback. Append-only `console.print` writes each chunk as a permanent line, so:

- Scrolling during a stream no longer corrupts the display (the user can read what already arrived while the model keeps writing).
- Select-and-copy works mid-stream — the text is in scrollback, not in a re-renderable buffer.
- Piping output through `tee` or terminal capture produces a faithful transcript. With `Live`, captured output is often interleaved with ANSI repaint sequences.
- `tmux`/`screen` and `less` behave predictably.

**Where Live would have been valuable — and the honest trade-off**: Long streaming responses benefit from in-place updates so the user can see progress. The honest answer is that the current LiveDisplay does *not* actually deliver good in-place updates — it re-renders the whole grid every tick, which is why it's unstable. If progress feedback is the goal, it should be a separate, deliberately-designed affordance (see "Spinner removal" below), not a side-effect of the streaming buffer.

**Recommendation**: Keep the append-only model. Do *not* reintroduce `Live` for content/thinking streams. If you want a progress affordance, add it as an explicit, separate component.

### 2. Lazy `PromptSession` (created on first `get_input`, not in `__init__`) — Endorsed

**Verdict**: Correct. No UX impact, but enables the `erase_when_done` + `output_prompt` flow cleanly.

**Reasoning**: The session is only needed for interactive input. Creating it in `__init__` forced the old handler to allocate a `prompt_toolkit` application even for `yoker run` (non-interactive) and for the bootstrap wizard (which uses `output_info` + `get_secret_input` but never the multiline `PromptSession`). Lazy creation means `erase_when_done` can be set on the *first* interactive prompt call, after any bootstrap/wizard flow has finished — so the erase behavior does not eat wizard input.

**Caveats**:
- The lazy session must be created *before* the first `get_secret_input` call too, or the wizard's masked prompts will not get `erase_when_done`. The proposal says "created on first `get_input`"; widen that to "first interactive prompt call (`get_input` or `get_secret_input`)".
- The `_input_source` path (scripted input via `set_input_messages`) must short-circuit *before* touching the lazy session — otherwise scripted/demo sessions will allocate a `PromptSession` they never use. The current `set_input_messages` already does this, but the merge must preserve it.

### 3. `erase_when_done=True` + `output_prompt` Panel — Endorsed, with a flicker risk to verify

**Verdict**: The pattern is good and matches the dominant agent-CLI convention (Claude Code's TUI erases the user's typed input and re-renders it in a styled box). It produces a clean transcript where user messages and assistant messages are visually symmetric — both are panels — and the user can scroll back to find their own prompts.

**UX flow analysis**:

1. User types `> explain this function` (visible inline at the prompt)
2. User presses Enter
3. prompt_toolkit erases the input line (`erase_when_done=True`)
4. Handler re-renders `explain this function` inside a `Panel(..., style=PROMPT_STYLE, box=box.SIMPLE_HEAD)`
5. Assistant response streams below the panel

**Flicker risk — must be tested on the target terminal**: The erase + Panel re-render happens in two separate write operations. On most modern terminals (iTerm2, Alacritty, kitty, Windows Terminal, Apple Terminal) this is fast enough that the user perceives a single repaint. But on slow terminals (SSH over high-latency links, WSL1, some CI capture buffers) there is a real risk of a one-frame "empty line" between the erase and the Panel render. The proposal does not mention this risk.

**Recommendation**: Verify empirically on at least:
- macOS Terminal.app (default)
- iTerm2
- A real SSH session (not local pseudo-tty)
- A non-interactive capture (`script(1)`) to confirm the transcript stays clean

If flicker is visible, the fix is a single `console.print()` call that emits the Panel *immediately after* the `prompt_async` returns, before any `await` yields control. The current RichUIHandler `output_prompt` does this synchronously, which is the right model — preserve it.

**Panel style concern**: `PROMPT_STYLE = Style(color="black", bgcolor="grey93")` uses `grey93` as a near-white background. On terminals with a light theme this is invisible; on dark themes it's a soft contrast block. This is fine for the default dark-theme experience, but check that the panel is still readable under the `NO_COLOR` env var (Rich should fall back gracefully, but `bgcolor="grey93"` may not — verify).

**Recommendation**: Also render the user's prompt with a leading label or icon inside the panel (e.g., `> explain this function` rather than just the bare text), so when scrollback is read out of context the user can tell their input from the model's output. RichUIHandler currently uses `Panel(text, ...)` with no title — add `title="you"` or prefix the text with `> `.

### 4. Remove LiveDisplay, spinner, state flags — Endorsed with one required restoration

**Verdict**: Removing the spinner is the one place where the proposal *regresses* on a real UX need, and the user explicitly called this out in the review focus. The old "Processing... N.Ns" line is not great — it lives inside the Live region, which is part of the instability problem — but it does serve a function: it tells the user "the model has not hung, work is in progress."

**The problem**: After the merge, the user presses Enter, sees their prompt re-rendered in a Panel, and then… nothing. No spinner, no progress indicator, no "Processing..." line. The terminal is silent for the entire first-token latency (which can be 2–10 seconds on a cold Ollama model load, longer for cloud providers under load). The user cannot tell whether:
- The model is still thinking (expected — wait)
- The request is queued (wait)
- The network dropped (restart)
- The model errored silently (broken)

This is a real UX regression, not a stylistic one. Users *will* Ctrl+C during long first-token latencies if they get no feedback, and they will report "it hangs" as a bug.

**Required adjustment**: Restore a single, append-safe processing affordance. Do *not* bring back the Live-based spinner. Two acceptable options:

**Option A (recommended): single "Processing…" line, replaced on first chunk**
- On `start_thinking_stream` or `start_content_stream` (whichever fires first), print `console.print("Processing…", style="dim", end="\r")`.
- On the first `stream_content` / `stream_thinking` chunk, print `console.print("\r" + " " * 12 + "\r", end="")` (clear the line) and then print the chunk normally.
- This uses the carriage return to update a single line — not Live — so it does not corrupt scrollback (the line is overwritten in place, then replaced by real output).
- This is the pattern Claude Code, Codex, and `gh` all use.

**Option B (acceptable, simpler): one-shot "Processing…" line, not replaced**
- Print `console.print("Processing…", style="dim")` once on first stream start.
- Leave it in the transcript as a permanent marker.
- Simpler, but noisier in scrollback.

Either is acceptable. What is *not* acceptable is silence. Pick one before merging.

**State flags**: Removing `_thinking_shown`, `_content_shown`, `_streaming_content`, `_streaming_thinking` is fine — they were only there to manage the Live region's separators. The append-only model needs no inter-stream separator logic; a blank line is enough, and RichUIHandler's `start_thinking_stream` already prints one (`self.console.print()`). Endorsed.

### 5. Inline tool args (`⏺ tool_name(key=value, …)`) — Endorsed, but reconsider verbosity

**Verdict**: Showing all args inline is *better* for transparency and *worse* for signal-to-noise than the old filename-only display. The right answer is in between.

**Analysis of the two displays**:

Old (InteractiveUIHandler):
```
⏺ Read tool: example.py
  ✓ Success
```

New (RichUIHandler):
```
⏺ read(path=example.py, offset=0, limit=100)
  ✓ Success (1234 chars)
```

**What's better in the new version**:
- The tool name is lowercase and unquoted, matching the actual tool identifier the user can `/tools`-lookup or mention in a bug report. The old `_capitalize` ("Read tool") was lossy.
- Inline `key=value` is copy-pasteable as a tool invocation reference. Users debugging agent behavior will want to see *all* the args, not just the filename.
- The result size (`1234 chars`) is a useful sanity check — "did the read actually return content, or did it return empty?"

**What's worse**:
- For `write` and `update`, `content=<long string>` will dump the full file content inline on a single line. The current RichUIHandler `_format_tool_details` *does* have a guard:
  ```python
  def str_summary(value):
    if "\n" in value:
      return f"{len(value)} chars"
    return value
  ```
  But this only collapses multi-line strings. A 10 KB single-line string (minified JS, long base64) will still print in full inline, breaking the layout. This is a real bug, not a stylistic one.

- For `websearch`, the query is shown inline, which is good. But for `webfetch`, `url=<long url>` is fine and should be preserved.

**Recommendation**:
1. Keep the `key=value` inline format. Do not revert to filename-only.
2. Fix the long-value guard to cap *any* string value, not just multi-line ones. Suggested: `value if len(value) < 60 else f"{len(value)} chars"` — collapse anything over 60 chars regardless of newlines.
3. For `write`/`update`, suppress the `content`/`new_string`/`old_string` keys entirely from the inline summary — the diff is already shown by `output_tool_content` with proper line numbers and colors. Showing them inline is redundant and noisy. The display should be `⏺ write(path=example.py)`, with the content preview coming from `_show_full_content` / `_show_diff_content`.
4. Keep the result size on the success line — it's a useful affordance.

**Verbosity config**: A future enhancement (out of scope for this task) would be to make this configurable. The `ux-write-update-display.md` analysis already proposed a `DisplayConfig.tool_output_verbosity: "silent" | "summary" | "content"`. The inline-args display corresponds to "summary" mode. Recommend tracking this as a follow-up so users who want the old filename-only behavior can opt in.

### 6. Thinking display: `grey74` with blank lines — Endorsed

**Verdict**: The inline append-only approach is better for readability than the old Live-buffered `bright_black dim`.

**Reasoning**: The old handler accumulated thinking text in a `Text` object inside the Live region. Long thinking streams reflowed on every tick, making it impossible to read mid-stream. The new approach prints each chunk with `end=""`, so thinking text accumulates as permanent scrollback lines the user can read at their own pace.

**Blank-line framing**: `start_thinking_stream` prints a blank line, `end_thinking_stream` prints another. This gives thinking a visual container — a "thinking block" framed by blank lines — which is easier to skim past than the old single-block Live region. Endorsed.

**Color concern**: `grey74` is a 256-color palette code. On terminals without 256-color support (rare today, but some CI capture environments), this falls back to the default foreground, making thinking text indistinguishable from content. `bright_black dim` (the old style) degrades more gracefully — it becomes a clearly-different "dim" style. Suggest keeping `grey74` as the primary (better on modern terminals) but verify it falls back acceptably under `TERM=vt100` or `NO_COLOR=1`. If it does not, fall back to `Style(color="bright_black", dim=True)`.

### 7. Banner: list tools in welcome banner — Endorsed, with a guard

**Verdict**: Useful for the user, with one caveat.

**Why it's useful**: Knowing which tools are loaded is the single most actionable piece of session metadata. The user can immediately see "oh, `websearch` is not loaded, I need to enable it" without running `/tools`. This is a real UX improvement over the old banner, which only showed model + harness + agent.

**Caveat**: The current RichUIHandler does `', '.join(list(agent.tools.keys()))` with no truncation. A loaded plugin set can easily reach 15–20 tools (read, write, update, list, mkdir, existence, search, git, github, make, webfetch, websearch, skill, agent, send_message, plus any plugin tools). On an 80-column terminal this wraps badly across multiple lines.

**Recommendation**: 
- Truncate the tool list to the first 8 tools, with `+N more` if there are more. `(use /tools to see all)` as a trailing hint.
- Or: print the tool count and defer the full list to `/tools` (`Tools: 15 available — type /tools to list`).
- The first option is slightly better — users can spot a specific tool they care about (e.g., `websearch`) without running a command.

## Missing UX Features — Regression Check

The proposal removes several UX affordances from the old InteractiveUIHandler. Each must be either preserved or consciously dropped.

### Lost and must be restored

1. **Processing feedback** (see section 4 above). Required.

### Lost and should be preserved

2. **`output_command_result`** — RichUIHandler stubs this as `pass`. Slash commands (`/help`, `/agents`, `/tools`, `/think`, `/context`, `/config`) print their output through this method. Stubbing it silently breaks every slash command in interactive mode. **Required fix**: implement it as `self.console.print(f"{result}\n")` (same as the old handler). This is a hard blocker — the merge cannot ship with slash commands producing no output.

3. **`output_step_title`** — RichUIHandler stubs this as `pass`. The bootstrap wizard calls this for every step. Stubbing it breaks the wizard's visual flow — the user sees step bodies with no step headers. **Required fix**: implement it the same way the old handler does (bold + underline + leading blank line for step > 1).

4. **`shutdown`** — RichUIHandler's `shutdown` is `pass`. The old handler prints `"\nGoodbye!"`. Not critical, but the "Goodbye!" line is a polite UX affordance that confirms the session ended cleanly (vs. crashed). **Recommendation**: preserve it.

5. **`get_secret_input`** with `is_password=True` — RichUIHandler stubs this as `pass`. The bootstrap wizard uses it to collect API keys. Stubbing it breaks wizard flows that need credentials. **Required fix**: implement it identically to the old handler, including the `is_password=False` reset on the regular `get_input` (the comment in the old handler explains why — `prompt_async` stores `is_password` as instance state).

### Lost and acceptable to drop

6. **`_print_wrapped` / `wrap_width`** — The old handler had a character-by-character wrapping helper. RichUIHandler does not wrap. This is acceptable — Rich's `Console` already wraps based on terminal width, and the manual wrapper was a workaround for the Live region's behavior. Dropping it is fine, but the `wrap_width` constructor parameter should remain accepted (and ignored, or forwarded to a `Console(width=wrap_width)` if set) for backward compatibility with code that constructs `InteractiveUIHandler(wrap_width=80)`.

7. **`FileHistory`** — The old handler persisted command history to `~/.yoker_history`. The proposal does not mention whether the merged handler preserves this. **Required clarification**: The lazy `PromptSession` *must* still be created with `FileHistory` (or `InMemoryHistory` for the `"none"` case). The `history_file` constructor parameter and the `"none"` sentinel handling must be preserved. If the merge drops file history, that is a real regression — users will lose arrow-key recall of prior prompts across sessions. **Required fix**: preserve the full `_create_session` logic from the old handler, including the `FileHistory` / `InMemoryHistory` choice and the `mkdir(parents=True, exist_ok=True)` for the parent directory.

8. **Multi-line input (Esc+Enter for newline)** — The old handler's `KeyBindings` (`enter` to submit, `escape+enter` to insert a newline) must be preserved in the lazy `PromptSession`. RichUIHandler does not have this because it has no `PromptSession`. The merge must keep the old key bindings verbatim.

9. **`agent_spawned` / `agent_finished`** — The old handler prints `↳ Agent spawned: <name>` and `↳ Agent finished: <name>`. RichUIHandler does not implement them. These are optional protocol methods (the UIBridge guards with `getattr`), so dropping them does not break anything technically — but it does silently degrade the multi-agent UX. **Recommendation**: preserve them. They are two lines of code each and they give the user visibility into `Session.spawn()` / `Session.release()` lifecycle, which is otherwise invisible.

10. **`confirm_approval`** (protected-file interactive approval) — The old handler renders the diff and prompts y/N. RichUIHandler does not implement it. Per the protocol doc comment, this is the *only* path that prevents protected-file writes from being silently blocked in interactive mode. If the merged handler does not implement `confirm_approval`, every write to a protected file (`Makefile`, `pyproject.toml`, `yoker.toml`, etc.) will be silently blocked — the agent will appear to "fail to edit" files the user expected it to edit. **Required fix**: preserve the old `confirm_approval` implementation verbatim, including the `_show_diff_content` reuse and the `is_password=False` reset on the y/N prompt.

### Summary of regressions to address

| # | Feature | Severity | Action |
|---|---------|----------|--------|
| 1 | Processing feedback | **Blocker** | Restore (Option A or B above) |
| 2 | `output_command_result` | **Blocker** | Implement (slash commands need it) |
| 3 | `output_step_title` | **Blocker** | Implement (wizard needs it) |
| 5 | `get_secret_input` | **Blocker** | Implement (wizard needs it) |
| 7 | `FileHistory` | **Blocker** | Preserve from old handler |
| 8 | Multi-line key bindings | **Blocker** | Preserve from old handler |
| 10 | `confirm_approval` | **Blocker** | Preserve from old handler |
| 4 | `shutdown` "Goodbye!" | Minor | Preserve |
| 6 | `wrap_width` | Minor | Accept param, ignore or forward |
| 9 | `agent_spawned`/`finished` | Minor | Preserve (2 lines each) |

The proposal as written drops four blockers (items 2, 3, 5, 10) that the review focus did not flag — these are not in the "Confirmed design decisions" list but they are real regressions because RichUIHandler stubs them. The merge is not a literal "take RichUIHandler's output + old handler's input" — it must also take every method RichUIHandler stubs from the old handler.

## API Coordination Note

For the API Architect:

- **`output_command_result`, `output_step_title`, `get_secret_input`, `confirm_approval`, `agent_spawned`/`agent_finished`** are all in the `UIHandler` Protocol (or documented as optional). The merge does not change the Protocol. But the merged `InteractiveUIHandler` must implement all of them — RichUIHandler's stubs (`pass`) are not acceptable for the interactive handler. No Protocol change is needed; this is purely an implementation-completeness issue.

- **`output_prompt`** is *not* in the `UIHandler` Protocol. RichUIHandler defines it as a non-Protocol method called from `get_input`'s caller (presumably `cli/chat.py` or `__main__.py`). If the merge keeps `output_prompt`, the caller must be updated to invoke it after `get_input` returns. **Question for API Architect**: is `output_prompt` called by the chat loop, or is it intended to be called *inside* `get_input` (so the user-types-Enter → erase → Panel flow is encapsulated in the handler)? The latter is cleaner and keeps the chat loop handler-agnostic. Recommend the merge absorbs `output_prompt` into `get_input` and removes it from the public surface.

- **`start()` signature divergence**: RichUIHandler's `start(self, agent, title="Yoker", version=__version__)` adds two params not in the Protocol. The merge must drop these extras to match `UIHandler.start(self, agent)`. Hard-code `"Yoker"` and `__version__` inside the method body.

## Acceptance Criteria (UX)

The merge is acceptable from a UX standpoint when all of the following are true:

1. **Output stability**: Streaming a long response produces permanent scrollback lines. Scrolling up during a stream does not corrupt the visible region. Selecting text mid-stream and copying yields the actual streamed text.

2. **Processing feedback**: After the user submits a prompt, there is visible feedback within 200 ms that the model is working. Silence during first-token latency is not acceptable.

3. **Input → Panel flow**: After Enter, the typed input is erased and re-rendered in a Panel within a single repaint (no visible flicker on the target terminals listed in section 3).

4. **Slash commands work**: `/help`, `/agents`, `/tools`, `/think`, `/context`, `/config` all produce visible output via `output_command_result`.

5. **Bootstrap wizard works**: `output_step_title` renders step headers with bold+underline. `get_secret_input` masks API key input. The wizard flow does not erase typed input mid-flow.

6. **History recall works**: Up-arrow recalls prior prompts across sessions (via `FileHistory` at `~/.yoker_history`). Passing `history_file="none"` disables persistence.

7. **Multi-line input works**: Esc+Enter inserts a newline; Enter submits.

8. **Protected-file approval works**: Writing to `Makefile` triggers the diff-rendering y/N prompt. Empty Enter / EOF / Ctrl+C all deny.

9. **Tool call display**: Inline `key=value` format, with long values (>60 chars, not just multi-line) collapsed to `<N> chars`. `write`/`update` suppress `content`/`old_string`/`new_string` from the inline summary (the diff is shown separately).

10. **Banner**: Tool list is shown but truncated to 8 entries with `+N more` and a `/tools` hint.

11. **Thinking display**: Thinking is framed by blank lines, in `grey74` (or a graceful fallback under `NO_COLOR`).

12. **No Live, no spinner, no state flags**: `LiveDisplay`, `spinner.py` usage, and the four `_streaming_*` / `_shown` flags are gone from the merged handler. (`spinner.py` itself can stay in the codebase for now — removing the module is a separate cleanup task.)

13. **Agent lifecycle visible**: `↳ Agent spawned` and `↳ Agent finished` lines appear for sub-agent activity.

## Files Touched (UX-relevant)

| File | UX-relevant change |
|------|-------------------|
| `src/yoker/ui/interactive.py` | Full rewrite per the merge |
| `src/yoker/ui/__init__.py` | Exports unchanged (class name stays `InteractiveUIHandler`) |
| `src/yoker/cli/chat.py` | If `output_prompt` is absorbed into `get_input`, the chat loop's call to it (if any) must be removed. Verify with API Architect. |
| `src/yoker/__main__.py` | `_create_ui()` wiring unchanged — `InteractiveUIHandler` is still constructed the same way |
| `examples/custom_handler.py` | No change required (already implements full Protocol) |

## Recommendation

**Approve with required adjustments.** The direction is correct and the user's goal (stable, stdout-like output) is well-served by the append-only model. The proposal as written has four undocumented blockers (stubbed `output_command_result`, `output_step_title`, `get_secret_input`, `confirm_approval`) that must be filled in from the old handler before the merge can ship, plus one required restoration (processing feedback). Once those are addressed, the merge is a clear UX improvement over the current Live-based handler.

Track the processing-feedback restoration and the long-value guard in `_format_tool_details` as the two non-obvious action items — everything else is "preserve the old behavior for these methods."